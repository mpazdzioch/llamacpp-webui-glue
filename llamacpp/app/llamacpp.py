import os
import yaml
from flask import current_app as app

def get_defaults():
    #READ LLAMA CLI PARAM DEFAULTS
    defaults_path = os.getenv('DEFAULT_MODEL_CONFIG')
    defaults = {}
    if defaults_path and os.path.exists(defaults_path):
        with open(defaults_path, 'r') as stream:
            try:
                defaults = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                app.logger.error(exc)
                pass
    return defaults

#constructs model config from default params and model specific config (if available)
def get_model_config(model):
    defaults = get_defaults()
    yml_content = {'file': model['path'], 'llama-server': {"--gpu-layers":0}}
    yml_content['llama-server'].update(defaults['llama-server'])
    #check if yml exists for this gguf and read the config
    if os.path.exists(model['yml_path']):
        with open(model['yml_path'], 'r') as stream:
            try:
                model_yml = yaml.safe_load(stream)
                tmp = model_yml['llama-server'].copy()
                model_yml['llama-server']=yml_content['llama-server']
                model_yml['llama-server'].update(tmp)
                yml_content = model_yml
            except yaml.YAMLError as exc:
                app.logger.error(exc)
                pass
    return yml_content

def generate_cli_command(model, port):
    defaults = get_defaults()
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