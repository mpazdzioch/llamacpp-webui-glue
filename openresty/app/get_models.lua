local cjson = require("cjson")
local api = require("api")
local vars = require("vars")
local llmd = ngx.shared.llm

local models = api.call('/v1/models',nil)
--insert local router element to GGUF models list returned from API
-- table.insert(models.data,1, {
--     id = vars.ROUTER_MODEL_NAME,
--     object = "model",
--     created = os.time(),
--     owned_by = "organization-owner"
-- })

ngx.say(cjson.encode(models))