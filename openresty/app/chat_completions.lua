local vars = require("vars")
local cjson = require("cjson")
local api = require("api")

local function load_model(pdata)

    local d = {model=pdata["model"]}
    local result, err = api.call('/llamacpp/new',d)

    if err then
        ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
        ngx.say("Error: ", err)
        return 
    end
    if result.status == 'error' then
        ngx.log(ngx.ERR, "error on model loading from API: ", cjson.encode(result))
        ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
        ngx.say("Error: ", result.message)
        return 
    end
    return result
end

local function get_model(pdata)

    local max_attempts = 60
    for attempt = 1, max_attempts do
        local timestamp = os.time()
        local result = load_model(pdata)
        for _, item in ipairs(result.processes) do
            local model_age = timestamp-item.timestamp
            --ngx.log(ngx.INFO, 'result debug: ', item.id, ':',item.status)
            if item.id == pdata.model and item.status == "active" and model_age>3 then
                --ngx.log(ngx.INFO, "model age in seconds: "..model_age)
                return item.host
            end
        end
        ngx.sleep(1)
    end
end

ngx.req.read_body()
local body = ngx.req.get_body_data()
if body == nil then
    local file = ngx.req.get_body_file()
    if file then
        local file_handle, err = io.open(file, "r")
        if not file_handle then
            ngx.log(ngx.ERR, "failed to open body file: ", err)
            ngx.exit(ngx.HTTP_BAD_REQUEST)
        end
        body = file_handle:read("*a")
        file_handle:close()
    else
        ngx.log(ngx.ERR, "failed to read request body")
        ngx.exit(ngx.HTTP_BAD_REQUEST)
    end
end
local data, err = cjson.decode(body)
if err then
    ngx.log(ngx.ERR, "failed to decode json: ", err)
    ngx.exit(ngx.HTTP_BAD_REQUEST)
end

if data["model"] == vars.ROUTER_MODEL_NAME then
    ngx.log(ngx.INFO, "doing router cli")
    return ngx.exec("@router_cli")
else
    local host = get_model(data)
    ngx.var.llamaurl = host .. "/v1/chat/completions"
    ngx.log(ngx.INFO, "going to ",ngx.var.llamaurl)
end