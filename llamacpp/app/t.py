import json
import gpu

d = gpu.usage_info()
print(json.dumps(d, indent=4))