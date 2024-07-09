local vars = require("vars")
local cjson = require("cjson")

local function generateUniqueString()
    local timestamp = os.time()
    local random_number = math.random(1, 10000)
    local characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    local unique_string = ""

    for i = 1, 10 do
        local random_index = math.random(1, #characters)
        unique_string = unique_string .. characters:sub(random_index, random_index)
    end
    return tostring(timestamp) .. tostring(random_number) .. unique_string
end

local function test_chunked(data)
    local ts = os.time()
    local id = generateUniqueString()
    local d1 = {
        choices = {
            {
                finish_reason = cjson.null,
                index = 0,
                delta = {
                    content = "fojer🔥🔥🔥🔥fojer"
                }
            }
        },
        created = ts,
        id = id,
        model = data["model"],
        object = "chat.completion.chunk"
    }
    local json = cjson.encode(d1)
    ngx.header["Content-Type"] = "text/event-stream"
    ngx.header["Cache-Control"] = "no-cache"
    ngx.header["Connection"] = "keep-alive"
    ngx.print("data: " .. json .. "\n\n")
    ngx.flush()

    local d3 = {
        choices = {
            {
                finish_reason = "stop",
                index = 0,
                delta = {}
            }
        },
        created = ts,
        id = id,
        model = data["model"],
        object = "chat.completion.chunk",
        usage = {
            prompt_tokens = 1,
            completion_tokens = 1,
            total_tokens = 1
        }
    }
    local json = cjson.encode(d3)
    ngx.print("data: " .. json .. "\n\n")
    ngx.flush()
end

local function test(data)
    local data = {
        id = data["model"],
        object = "chat.completion",
        created = os.time(),
        model = data["model"],
        system_fingerprint = "uuuuu",
        choices = {
            {
                index = 0,
                message = {
                    role = "assistant",
                    content = "🔥🔥🔥🔥fojer",
                },
                logprobs = nil,
                finish_reason = "stop"
            }
        },
        usage = {
            prompt_tokens = 1,
            completion_tokens = 1,
            total_tokens = 1
        }
    }
    local json = cjson.encode(data)
    ngx.header["Content-Type"] = "text/event-stream"
    ngx.header["Cache-Control"] = "no-cache"
    ngx.header["Connection"] = "keep-alive"
    ngx.print("data: " .. json .. "\n\n")
end

ngx.req.read_body()
local data, err = cjson.decode(ngx.req.get_body_data())
if not data then
    ngx.log(ngx.ERR, "Failed to decode JSON: ", err)
    ngx.exit(ngx.HTTP_BAD_REQUEST)
end

if data["stream"] == false then
    test(data)
else
    test_chunked(data)
end