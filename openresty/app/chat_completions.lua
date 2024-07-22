local vars = require("vars")
local cjson = require("cjson")
local api = require("api")

local function load_model(pdata)

    local llmd = ngx.shared.llm
    local ami = cjson.decode(llmd:get('api_model_info'))
    for _, item in ipairs(ami) do
        if item.id == pdata.model and item.status == "active" then
            ngx.log(ngx.INFO, "found model already loaded: ", pdata.model)
            return item.host
        end
    end
    ngx.log(ngx.INFO, "model needs loading: ", pdata.model)
    
    --run new model
    local d = {model=pdata["model"]}
    local result, err = api.call('/llamacpp/new',d)
    ngx.sleep(2)

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

    llmd:set('api_model_info',cjson.encode(result.processes))
    for _, item in ipairs(result.processes) do
        ngx.log(ngx.INFO, 'result debug: ', item.id, ':',item.status)
        if item.id == pdata.model and item.status == "active" then
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