from flask import Flask, jsonify, request
import yaml
import os
import sys
import subprocess
import signal
import csv
import json
import time
import gpu

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
                if 'llama-server' in defaults:
                    yml_content['llama-server'].update(defaults['llama-server'])
            except yaml.YAMLError as exc:
                print(exc)
    
    file_size_bytes = os.path.getsize(model['path'])
    file_size_mb = file_size_bytes / (1024 * 1024)# Convert bytes to megabytes
    ctx_percent = 10
    model_size_with_ctx = file_size_mb+file_size_mb*(ctx_percent/100)
    #only check available vram if model is configured to use it
    if 'llama-server' in yml_content and yml_content['llama-server']['--gpu-layers']>0:

        gpu_data = gpu.usage_info()
        if gpu_data['total_memory_mb']<=model_size_with_ctx:
            message = f"cant fit {model_size_with_ctx}MB model in {gpu_data['total_memory_mb']}MB VRAM"
            app.logger.error(message)
            r = {'processes': llama_processes, 'status':'error', 'message': message}
            return jsonify(r)
        
        if gpu_data['total_free_memory_mb']<=model_size_with_ctx:
            #kill some processes to make room for new model
            #remove largest first
            vram_to_free = model_size_with_ctx-gpu_data['total_free_memory_mb']
            active_procs = [d for d in llama_processes if d['status'] == 'active']
            active_procs = sorted(active_procs, key=lambda k: k['file_size_mb'], reverse=True)
            total_mem_size = 0
            selected_procs = []

            # Iterate through the sorted list of active processes
            for proc in active_procs:
                total_mem_size += proc['mem_size']
                selected_procs.append(proc)
                if total_mem_size >= vram_to_free:
                    break

            for lp in selected_procs:
                try:
                    os.kill(lp['pid'], signal.SIGTERM)
                    app.logger.debug(f"Process {lp['file']} with PID {lp['pid']} has been terminated.")
                    lp['status']='killed'
                except OSError:
                    app.logger.error(f"Process {lp['file']} with PID {lp['pid']} does not exist.")

        #recheck after killing
        gpu_data = gpu.usage_info()
        if gpu_data['total_free_memory_mb']<=model_size_with_ctx:
            message = f"tried to kill some llama processes to free up vram but still not enough. avail mem {gpu_data['total_free_memory_mb']} but need {model_size_with_ctx}"
            app.logger.error(message)
            r = {'processes': llama_processes, 'status':'error', 'message': message}
            return jsonify(r)

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

    #get real mem footprint of the model after loading
    time.sleep(2)
    gpu_data_fresh = gpu.usage_info()
    #find new process pid on host (different than the one from inside container)
    gpu_info = {gpu['index']: gpu['processes'] for gpu in gpu_data['gpu_info']}
    gpu_info_fresh = {gpu['index']: gpu['processes'] for gpu in gpu_data_fresh['gpu_info']}

    # Find process IDs that are in fresh data but not in original data
    new_pids = []

    for index, processes in gpu_info_fresh.items():
        for process in processes:
            if process['pid'] not in [p['pid'] for p in gpu_info[index]]:
                new_pids.append(process['pid'])
    host_pid = 0
    if len(new_pids)>0:
        new_pids.sort()
        host_pid = new_pids[-1]

    mem_size = None

    for gpu_info in gpu_data_fresh['gpu_info']:
        for process_info in gpu_info['processes']:
            if process_info['pid'] == host_pid:
                mem_size = process_info['used_memory']
                break
        if mem_size is not None:
            break

    if mem_size is None:
        app.logger.error(f"Process with PID {host_pid} not found in GPU usage information.")
    else:
        app.logger.debug(f"Estimated mem size {model_size_with_ctx} vs real {mem_size} for {model_id}")
        model_size_with_ctx = mem_size

    lp = {'pid': pid, 'host_pid':host_pid, 'id':model_id ,'host': f"http://llamacpp:{port}", 'logfile': logfile,'command': ' '.join(command), 'file': model['path'], 'status':'active', 'file_size_mb':file_size_mb, 'mem_size': model_size_with_ctx}
    llama_processes.append(lp)
    r = {'processes': llama_processes, 'status':'success'}
    return jsonify(r)

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')