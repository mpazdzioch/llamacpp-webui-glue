from flask import Flask, jsonify, request
import yaml
import os
import sys
import subprocess
import signal
import csv
import json
import time

last_port_used = 8080
process_counter = 0
llama_processes = []
models = {}
app = Flask(__name__)

def generate_llamacpp_command(model, port, defaults):
    cli = ['/llama-server', '-m', model['file'], '--host', '0.0.0.0', '--port', str(port)]
    args = {}
    if 'llama-server' in defaults:
        for k, v in defaults['llama-server'].items():
            args[k] = str(v)
    if 'llama-server' in model and len(model['llama-server'])>0:
        for k, v in model['llama-server'].items():
            args[k] = str(v)
    for k, v in args.items():
        cli.append(str(k))
        if v !='no_value_flag': cli.append(v)
    #return ' '.join(cli)
    return cli

def scan_gguf_files():
    models_dir = os.getenv("MODEL_DIR")
    if not models_dir:
        return json.dumps({"error": "MODEL_DIR environment variable is not set"})
    try:
        gguf_files = [os.path.join(models_dir, f) for f in os.listdir(models_dir) if f.endswith('.gguf')]
    except Exception as e:
        return json.dumps({"error": str(e)})
    
    gguf_models = {}
    counter = {}
    for gguf_file in gguf_files:
        fname = os.path.basename(gguf_file)
        mname = fname 
        # Check if the base name already exists in the counter
        base_name = fname
        count = counter.get(base_name, 0)
        # Append the count to the base name if it's not unique
        while mname in gguf_models:
            count += 1
            mname = f"{base_name}_{count}"

        counter[base_name] = count
        gguf_models[mname] = {'path': gguf_file, 'id': mname, 'yml_path': f"/model-config/{fname}.yml"}
    return gguf_models

def scan_yml_files():
    yml_dirs = ['/model-config',os.getenv("MODEL_DIR")]
    yml_files = []
    for dir in yml_dirs:
        try:
            yml_files.extend([os.path.join(dir, f) for f in os.listdir(dir) if f.endswith('.yml')])
        except Exception as e:
            return json.dumps({"error": str(e)})
    yml_models = {}
    counter = {}
    for yml_file in yml_files:
        fname = os.path.basename(yml_file)
        mname = fname 
        # Check if the base name already exists in the counter
        base_name = fname
        count = counter.get(base_name, 0)
        # Append the count to the base name if it's not unique
        while mname in yml_models:
            count += 1
            mname = f"{base_name}_{count}"

        counter[base_name] = count
        #read yml file
        with open(yml_file, 'r') as stream:
            try:
                yml_content = yaml.safe_load(stream)
                if 'file' not in yml_content:
                    continue
                if fname.rstrip('.yml')==os.path.basename(yml_content['file']):
                    continue
            except yaml.YAMLError as exc:
                print(exc)
            yml_models[mname] = {'path': yml_content['file'], 'id': mname, 'yml_path':yml_file}

    return yml_models

@app.route('/api/v1/models', methods=['GET'])
def get_available_models():
    global models

    models = scan_yml_files()
    models.update(scan_gguf_files())

    active_models = [lp['id'] for lp in llama_processes if lp['status'] == 'active']
    data = []
    # Add active models to the data list
    for m in models.values():
        if m['id'] in active_models:
            data.append({
                "id": m['id'],
                "object": "model",
                "created": int(time.time()),
                "owned_by": "organization-owner"
            })
    # Add inactive models to the data list
    for m in models.values():
        if m['id'] not in active_models:
            data.append({
                "id": m['id'],
                "object": "model",
                "created": int(time.time()),
                "owned_by": "organization-owner"
            })

    return json.dumps({"object": "list", "data": data})

@app.route('/api/llamacpp/new', methods=['POST'])
def new_llama():
    global process_counter
    global llama_processes
    global last_port_used
    global models

    data = request.json
    model_id = data.get('model') #this is model id/key from 'global models'
    model = models[model_id]
    app.logger.debug(json.dumps(model))

    file_size_bytes = os.path.getsize(model['path'])
    file_size_mb = file_size_bytes / (1024 * 1024)# Convert bytes to megabytes
    ctx_percent = 10
    model_size_with_ctx = file_size_mb+file_size_mb*(ctx_percent/100)

    # Get the GPU information
    result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'], stdout=subprocess.PIPE)
    # Decode the output
    output = result.stdout.decode('utf-8')
    # Convert the CSV output to a list of dictionaries
    gpu_info = list(csv.DictReader(output.splitlines(), fieldnames=['index', 'name', 'memory.total', 'memory.used', 'memory.free', 'utilization.gpu']))
    total_memory_free_sum = sum(int(item["memory.free"]) for item in gpu_info)

    if total_memory_free_sum<=model_size_with_ctx:
        #one process at a time now
        #kill if any active processes running
        for lp in llama_processes:
            if lp['status']!='active': continue
            try:
                os.kill(lp['pid'], 0)
            except OSError:
                print(f"Process {lp['file']} with PID {lp['pid']} does not exist.")
            else:
                os.kill(lp['pid'], signal.SIGTERM)
                print(f"Process {lp['file']} with PID {lp['pid']} has been terminated.")
                lp['status']='killed'

    yml_content = {'file': model['path'], 'llama-server':[]}

    #READ LLAMA CLI PARAM DEFAULTS
    defaults_path = os.getenv('DEFAULT_MODEL_CONFIG')
    defaults = {}
    if defaults_path and os.path.exists(defaults_path):
        with open(defaults_path, 'r') as stream:
            try:
                defaults = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)

    #check if yml exists for this gguf and read the config
    if os.path.exists(model['yml_path']):
        with open(model['yml_path'], 'r') as stream:
            try:
                yml_content = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)

    last_port_used += 1
    port = last_port_used
    command = generate_llamacpp_command(yml_content,port,defaults)
    logfile = f'/llamacpp-logs/log_{process_counter}.txt'
    with open(logfile, 'w') as log_file:
        process = subprocess.Popen(command, 
                                stdout=log_file, 
                                stderr=log_file, 
                                stdin=subprocess.PIPE, 
                                close_fds=True, 
                                start_new_session=True)
    pid = process.pid
    process_counter = process_counter + 1
    lp = {'pid': pid, 'id':model_id ,'host': f"http://llamacpp:{port}", 'logfile': logfile,'command': ' '.join(command), 'file': model['path'], 'status':'active', 'file_size_mb':file_size_mb}
    llama_processes.append(lp)
    
    return jsonify(llama_processes)

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')