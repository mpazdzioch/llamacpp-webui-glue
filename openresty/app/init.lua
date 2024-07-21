local vars = require("vars")

--initialize some dict values
local llmd = ngx.shared.llm
llmd:set('current_model','none')
llmd:set('api_model_info','{}')
