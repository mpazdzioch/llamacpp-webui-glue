from flask import Flask, jsonify, request
import yaml
import os
import sys
import subprocess
import signal

process_counter = 0
llama_processes = {}
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

@app.route('/api/llamacpp/new', methods=['POST'])
def new_llama():
    global process_counter
    global llama_processes

    #one process at a time now
    #kill if any active processes running
    for pid, name in llama_processes.items():
        try:
            os.kill(pid, 0)
        except OSError:
            print(f"Process {name} with PID {pid} does not exist.")
        else:
            os.kill(pid, signal.SIGTERM)
            print(f"Process {name} with PID {pid} has been terminated.")

    data = request.json
    model = data.get('model') #this is gguf modelfile path
    file_gguf = os.path.basename(model)
    file_yml = file_gguf+".yml"

    yml_content = {'file': model, 'llama-server':[]}

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
    yml_path = os.path.join('/model-config',file_yml)
    if os.path.exists(yml_path):
        with open(yml_path, 'r') as stream:
            try:
                yml_content = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
    port = 8081
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
    llama_processes[pid] = file_gguf
    
    return jsonify({'pid': pid, 'url': f"http://llamacpp:{port}/v1", 'logfile': logfile,'command': ' '.join(command)})

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')  # Listen on port 8080