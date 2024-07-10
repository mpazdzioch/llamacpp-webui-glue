import subprocess
import csv
import json

# Get the GPU information
result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'], stdout=subprocess.PIPE)

# Decode the output
output = result.stdout.decode('utf-8')

# Convert the CSV output to a list of dictionaries
gpu_info = list(csv.DictReader(output.splitlines(), fieldnames=['index', 'name', 'memory.total', 'memory.used', 'memory.free', 'utilization.gpu']))

# Convert the list of dictionaries to JSON format
json_gpu_info = json.dumps(gpu_info, indent=4)

print(json_gpu_info)

total_memory_free_sum = sum(int(item["memory.free"]) for item in gpu_info)
print(total_memory_free_sum)