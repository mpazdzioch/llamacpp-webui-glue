local vars = require("vars")
local cjson = require("cjson")
local io = require("io")
local os = require("os")

local function scan_gguf_files(premature)

    local models_dir = os.getenv("MODEL_DIR")
    if not models_dir then
        return cjson.encode({
            error = "MODEL_DIR environment variable is not set"
        })
    end

    local command = "ls -1 " .. models_dir .. "/*.gguf"
    local pipe = io.popen(command)
    if not pipe then
        return cjson.encode({
            error = "Failed to execute ls command"
        })
    end

    local data = {}
    table.insert(data, {
        id = vars.ROUTER_MODEL_NAME,
        object = "model",
        created = os.time(),
        owned_by = "organization-owner"
    })
    for gguf_file in pipe:lines() do
        -- Extract the filename from the full path
        -- local filename = string.match(gguf_file, "[^/]+$")
        table.insert(data, {
            id = gguf_file,
            object = "model",
            created = os.time(),
            owned_by = "organization-owner"
        })
    end
    pipe:close()

    local serialized_data = cjson.encode({
        object = "list",
        data = data
    })
    local llmd = ngx.shared.llm
    llmd:set('api_v1_models',serialized_data)
end

--initialize some dict values
local llmd = ngx.shared.llm
llmd:set('current_model','none')

scan_gguf_files()
ngx.timer.every(5,scan_gguf_files) 