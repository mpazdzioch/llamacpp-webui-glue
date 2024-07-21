local http = require("resty.http")
local cjson = require("cjson")

local api_url = "http://llamacpp:5000/api"

local _M = {}

function _M.call(uri_path, post_vars)
    local httpc = http.new()
    local method = "GET"
    local body = nil
    local full_url = api_url .. (uri_path:sub(1, 1) == '/' and '' or '/') .. uri_path
    ngx.log(ngx.INFO, "calling api url: ", full_url)
    if post_vars and next(post_vars) ~= nil then
        method = "POST"
        body = cjson.encode(post_vars)
    end
    local res, err = httpc:request_uri(
        full_url,
        {method = method,
        headers = {
            ["Content-Type"] = "application/json"
        },
        body = body}
    )

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

return _M