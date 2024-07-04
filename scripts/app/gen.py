import csv
import yaml
import os
import sys

def read_model_set(yml_file):
    models = []
    yml = []
    if os.path.exists(yml_file):
        with open(yml_file, 'r') as stream:
            try:
                yml = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
    else:
        print(f"YAML file '{yml_file}' does not exist or bad format")
    for m in yml:
        if m['active'] != 1: continue
        if not os.path.exists(m['file']):
            print(f'cant find {m['file']}')
            continue
        if m['file'].lower().endswith('.yml'):
            with open(m['file'], 'r') as stream:
                try:
                    yml_content = yaml.safe_load(stream)
                    if 'llama-server' in m:
                        yml_content['llama-server'].update(m['llama-server'])
                    models.append(yml_content)
                except yaml.YAMLError as exc:
                    print(exc)
        if m['file'].lower().endswith('.gguf'):
            models.append(m)
        
    return models

def generate_llamacpp_command(model, port, defaults):
    cli = ['./llama-server', '-m', model['file'], '--host', '0.0.0.0', '--port', str(port)]
    args = {}
    if 'llama-server' in defaults:
        for k, v in defaults['llama-server'].items():
            args[k] = str(v)
    if 'llama-server' in model:
        for k, v in model['llama-server'].items():
            args[k] = str(v)
    for k, v in args.items():
        cli.append(str(k))
        if v !='no_value_flag': cli.append(v)
    return ' '.join(cli)

model_set_path = os.getenv('MODELS_TO_RUN')
if model_set_path is None:
    print('MODELS_TO_RUN env var is missing. Please set it with a path to config file')
    sys.exit(1)

gen_config_dir = os.getenv('GENERATED_CONFIG_DIR')
if gen_config_dir is None:
    print('GENERATED_CONFIG_DIR env var is missing.')
    sys.exit(1)

models = read_model_set(model_set_path)
print(f'generating config with {len(models)} models')

#READ LLAMA CLI PARAM DEFAULTS
defaults_path = os.getenv('DEFAULT_MODEL_CONFIG')
defaults = {}
if defaults_path and os.path.exists(defaults_path):
    with open(defaults_path, 'r') as stream:
        try:
            defaults = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)

#GENERATE SUPERVISORD CONFIG FILE
sconf_path = os.path.join(gen_config_dir,'supervisord.conf')
sconf = "[supervisord]\n\n"
port=8080
id=1
for model in models:
    name = f'llama{id}'
    model['port'] = port+id
    command = generate_llamacpp_command(model,port+id,defaults)
    sconf += f"""[program:{name}]
command={command}
directory=/
autorestart=false
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
redirect_stderr=true
startsecs=10
priority={id}
startretries=0

"""
    id += 1
with open(sconf_path, 'w') as file:
    file.write(sconf)
print(f'saved new supervisord config file to {sconf_path}')

#GENERATE WEBUI ENV VARS
webui_env_path = os.path.join(gen_config_dir,'env_webui')
api_urls = []
api_keys = []
for model in models:
    api_urls.append(f"http://llamacpp:{model['port']}/v1")
    api_keys.append('sk-124781258123')
webui_env = f"""OPENAI_API_BASE_URLS={';'.join(api_urls)}
OPENAI_API_KEYS={';'.join(api_keys)}
"""
with open(webui_env_path, 'w') as file:
    file.write(webui_env)
print(f'saved new webui env vars file to {webui_env_path}')