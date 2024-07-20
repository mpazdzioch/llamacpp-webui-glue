local vars = require("vars")
local cjson = require("cjson")
local http = require ("resty.http")

local function call_api(model_path)
    local httpc = http.new()
    local res, err = httpc:request_uri("http://llamacpp:5000/api/llamacpp/new", {
        method = "POST",
        headers = {
            ["Content-Type"] = "application/json"
        },
        body = cjson.encode({
            model = model_path
        })
    })

    if not res then
        ngx.log(ngx.ERR, "Failed to make request: ", err)
        return nil, err
    end

    if res.status ~= 200 then
        ngx.log(ngx.ERR, "Unexpected status: ", res.status)
        return nil, "Unexpected status: " .. res.status
    end

    local body = res.body
    local result, err = cjson.decode(body)
    if not result then
        ngx.log(ngx.ERR, "Failed to decode JSON: ", err)
        return nil, err
    end

    return result, nil
end

local function load_model(pdata)

    local llmd = ngx.shared.llm
    local ami = cjson.decode(llmd:get('api_model_info'))
    for _, item in ipairs(ami) do
        if item.file == pdata.model and item.status == "active" then
            ngx.log(ngx.INFO, "found model already loaded: ", pdata.model)
            return item.host
        end
    end
    ngx.log(ngx.INFO, "model needs loading: ", pdata.model)
    
    --run new model
    local model_path = pdata["model"]
    local result, err = call_api(model_path)
    ngx.sleep(2)

    if err then
        ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
        ngx.say("Error: ", err)
        return 
    end
    llmd:set('api_model_info',cjson.encode(result))
    for _, item in ipairs(result) do
        ngx.log(ngx.INFO, 'result debug: ', item.file, ':',item.status)
        if item.file == pdata.model and item.status == "active" then
            ngx.log(ngx.INFO, "found model already loaded: ", pdata.model)
            return item.host
        end
    end

end

ngx.req.read_body()
local data, err = cjson.decode(ngx.req.get_body_data())
if err then
    ngx.log(ngx.ERR, "failed to decode json: ", err)
    ngx.exit(ngx.HTTP_BAD_REQUEST)
end

if data["model"] == vars.ROUTER_MODEL_NAME then
    ngx.log(ngx.INFO, "doing router cli")
    return ngx.exec("@router_cli")
else
    local host = load_model(data)
    ngx.var.llamaurl = host .. "/v1/chat/completions"
    ngx.log(ngx.INFO, "going to ",ngx.var.llamaurl)
end