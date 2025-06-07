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
import model_files
import time

last_port_used = 8080
process_counter = 0
llama_processes = []
models = {}
app = Flask(__name__)

def cleanup_processes():
    global llama_processes
    running_processes = []
    current_time = int(time.time())  # Get the current Unix timestamp

    for lp in llama_processes:
        pid = lp['pid']
        status = lp['status']
        timestamp = lp['timestamp']

        if status == 'pending' and pid == 0:
            # Check if the process is older than 10 minutes
            if current_time - timestamp > 600:  # 600 seconds = 10 minutes
                app.logger.debug(f"Process {lp['id']} with PID {pid} is pending and older than 10 minutes. Removing from list.")
                lp['status'] = 'terminated'
            else:
                running_processes.append(lp)
        else:
            try:
                # Send signal 0 to check if the process is still running
                os.kill(pid, 0)
                # If no exception is raised, the process is still running
                running_processes.append(lp)
            except OSError:
                # If an OSError is raised, the process is not running
                app.logger.debug(f"Process {lp['id']} with PID {pid} is no longer running. Removing from list.")
                lp['status'] = 'terminated'
                # Optionally, you can log or handle the terminated process here

    # Update the llama_processes list with only the running processes
    llama_processes = running_processes

def launch_new_llama(model_id):
    global process_counter
    global llama_processes
    global last_port_used
    global models

    model = models[model_id]
    yml_content = llamacpp.get_model_config(model)

    file_size_mb = model['size_bytes'] / (1024 * 1024)
    ctx_percent = 10
    model_size_with_ctx = file_size_mb+file_size_mb*(ctx_percent/100)

    #only check available vram if model is configured to use it
    if 'llama-server' in yml_content and yml_content['llama-server']['--gpu-layers']>0:
        gpu_data = gpu.usage_info()
        #update vram mem usage for each running model in llama_processes
        for p in llama_processes:
            pid = str(p['pid'])
            if pid in gpu_data['process_memory_usage_mb']:
                p['mem_size'] = gpu_data['process_memory_usage_mb'][pid]
        app.logger.debug(json.dumps(llama_processes))
        
        min_vram_mb = model_size_with_ctx
        if 'min-vram-gb' in yml_content:
            min_vram_mb = yml_content['min-vram-gb']*1000

        if gpu_data['total_memory_mb']<=min_vram_mb:
            message = f"cant fit {model_size_with_ctx}MB model in {gpu_data['total_memory_mb']}MB VRAM. Need at least {min_vram_mb}MB in VRAM"
            app.logger.error(message)
            r = {'processes': llama_processes, 'status':'error', 'message': message}
            return jsonify(r)
        
        if gpu_data['total_free_memory_mb']<=min_vram_mb:
            #kill some processes to make room for new model
            #remove largest first
            app.logger.debug(f"we need {min_vram_mb}MB VRAM but only {gpu_data['total_free_memory_mb']} available. trying to free some memory now.")
            vram_to_free = min_vram_mb-gpu_data['total_free_memory_mb']
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
        if gpu_data['total_free_memory_mb']<=min_vram_mb:
            message = f"tried to kill some llama processes to free up vram but still not enough. avail mem {gpu_data['total_free_memory_mb']} but need {min_vram_mb}"
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
    current_timestamp = int(time.time())

    # Cleanup: Remove any items with the same model_id and status='pending'
    llama_processes = [p for p in llama_processes if not (p['id'] == model_id and p['status'] == 'pending')]

    lp = {'pid': pid, 'id':model_id ,'host': f"http://llamacpp:{port}", 'logfile': logfile,'command': ' '.join(command), 'file': model['path'], 'status':'active', 'file_size_mb':file_size_mb, 'mem_size': 0, 'timestamp': current_timestamp}
    app.logger.debug(json.dumps(lp))
    llama_processes.append(lp)

@app.route('/api/v1/models', methods=['GET'])
def get_available_models():
    global models

    models = model_files.scan()

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
    cleanup_processes()

    process = next((p for p in llama_processes if p['id'] == model_id), None)
    if process:
        print(f"{model_id} already running at {process['host']}")
    else:
        print(f"Launching new process for {model_id}")
        current_timestamp = int(time.time())  # Get the current Unix timestamp
        llama_processes.append({'pid': 0, 'id':model_id ,'host': f"none", 'logfile': '','command': ' ', 'file': '', 'status':'pending', 'file_size_mb':0, 'mem_size': 0, 'timestamp': current_timestamp})
        launch_new_llama(model_id)

    r = {'processes': llama_processes, 'status':'success'}
    return jsonify(r)

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')