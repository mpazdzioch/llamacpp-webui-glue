local cjson = require("cjson")
local llmd = ngx.shared.llm

local function get_models()
    local models_data, err = llmd:get('api_v1_models')
    if not models_data then
        ngx.status = ngx.HTTP_INTERNAL_SERVER_ERROR
        ngx.say(cjson.encode({ error = "Failed to retrieve models data from shared dictionary" }))
        return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
    end

    if models_data == ngx.null then
        ngx.status = ngx.HTTP_NO_CONTENT
        ngx.say(cjson.encode({ message = "No models available" }))
        return ngx.exit(ngx.HTTP_NO_CONTENT)
    end

    ngx.status = ngx.HTTP_OK
    ngx.say(models_data)
end

get_models()