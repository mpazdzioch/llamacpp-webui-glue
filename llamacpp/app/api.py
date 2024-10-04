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
import llamacpp

last_port_used = 8080
process_counter = 0
llama_processes = []
models = {}
app = Flask(__name__)

def scan_model_files():
    #GGUF files first
    models_dir = os.getenv("MODEL_DIR")
    if not models_dir:
        raise Exception("MODEL_DIR environment variable is not set")
    gguf_files = [os.path.join(models_dir, f) for f in os.listdir(models_dir) if f.endswith('.gguf')]
    
    models = {}
    counter = {}
    yml_paths = []
    for gguf_file in gguf_files:
        fname = os.path.basename(gguf_file)
        mname = fname 
        # Check if the base name already exists in the counter
        base_name = fname
        count = counter.get(base_name, 0)
        # Append the count to the base name if it's not unique
        while mname in models:
            count += 1
            mname = f"{base_name}_{count}"

        counter[base_name] = count
        default_yml_path = f"/model-config/{fname}.yml"
        yml_paths.append(default_yml_path)
        models[mname] = {'path': gguf_file, 'id': mname, 'yml_path': default_yml_path}

    #now check YMLs
    yml_dirs = ['/model-config',os.getenv("MODEL_DIR")]
    yml_files = []
    for dir in yml_dirs:
        yml_files.extend([os.path.join(dir, f) for f in os.listdir(dir) if f.endswith('.yml')])

    counter = {}
    for yml_file in yml_files:
        if yml_file in yml_paths:
            continue
        fname = os.path.basename(yml_file)
        mname = fname 
        # Check if the base name already exists in the counter
        base_name = fname
        count = counter.get(base_name, 0)
        # Append the count to the base name if it's not unique
        while mname in models:
            count += 1
            mname = f"{base_name}_{count}"

        counter[base_name] = count
        #read yml file
        with open(yml_file, 'r') as stream:
            try:
                yml_content = yaml.safe_load(stream)
                if 'file' not in yml_content:
                    continue
            except yaml.YAMLError as exc:
                print(exc)
            models[mname] = {'path': yml_content['file'], 'id': mname, 'yml_path':yml_file}

    return models

@app.route('/api/v1/models', methods=['GET'])
def get_available_models():
    global models

    models = scan_model_files()

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

    yml_content = llamacpp.get_model_config(model)

    file_size_bytes = os.path.getsize(model['path'])
    file_size_mb = file_size_bytes / (1024 * 1024)# Convert bytes to megabytes
    ctx_percent = 10
    model_size_with_ctx = file_size_mb+file_size_mb*(ctx_percent/100)

    gpu_data = gpu.usage_info()
    #update vram mem usage for each running model in llama_processes
    for p in llama_processes:
        pid = str(p['pid'])
        if pid in gpu_data['process_memory_usage_mb']:
            p['mem_size'] = gpu_data['process_memory_usage_mb'][pid]
    app.logger.debug(json.dumps(llama_processes))

    #only check available vram if model is configured to use it
    if 'llama-server' in yml_content and yml_content['llama-server']['--gpu-layers']>0:
        
        if gpu_data['total_memory_mb']<=model_size_with_ctx:
            message = f"cant fit {model_size_with_ctx}MB model in {gpu_data['total_memory_mb']}MB VRAM"
            app.logger.error(message)
            r = {'processes': llama_processes, 'status':'error', 'message': message}
            return jsonify(r)
        
        if gpu_data['total_free_memory_mb']<=model_size_with_ctx:
            #kill some processes to make room for new model
            #remove largest first
            app.logger.debug(f"model size is {model_size_with_ctx} but only {gpu_data['total_free_memory_mb']} available. trying to free some memory now.")
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
                    app.logger.debug(f"Process {lp['id']} with PID {lp['pid']} has been terminated.")
                    lp['status']='killed'
                except OSError:
                    app.logger.error(f"Process {lp['id']} with PID {lp['pid']} does not exist.")

        #recheck after killing
        time.sleep(3)
        gpu_data = gpu.usage_info()
        if gpu_data['total_free_memory_mb']<=model_size_with_ctx:
            message = f"tried to kill some llama processes to free up vram but still not enough. avail mem {gpu_data['total_free_memory_mb']} but need {model_size_with_ctx}"
            app.logger.error(message)
            r = {'processes': llama_processes, 'status':'error', 'message': message}
            return jsonify(r)

    last_port_used += 1
    port = last_port_used
    command = llamacpp.generate_cli_command(yml_content,port)
    logfile = f'/llamacpp-logs/log_{process_counter}.txt'
    with open(logfile, 'w') as log_file:
        process = subprocess.Popen(command, 
                                cwd="/",
                                stdout=log_file, 
                                stderr=log_file, 
                                stdin=subprocess.PIPE, 
                                close_fds=True, 
                                start_new_session=True)
    pid = process.pid
    process_counter = process_counter + 1

    lp = {'pid': pid, 'id':model_id ,'host': f"http://llamacpp:{port}", 'logfile': logfile,'command': ' '.join(command), 'file': model['path'], 'status':'active', 'file_size_mb':file_size_mb, 'mem_size': 0}
    app.logger.debug(json.dumps(lp))
    llama_processes.append(lp)
    r = {'processes': llama_processes, 'status':'success'}
    return jsonify(r)

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')