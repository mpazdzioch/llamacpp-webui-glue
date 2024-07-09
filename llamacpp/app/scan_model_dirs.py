import os
import yaml
from shutil import copyfile

def scan_path_for_models(path, extension):
    model_paths = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(f'.{extension}'):
                model_paths.append(os.path.join(root, file))
    return model_paths

model_dirs = os.getenv('MODEL_DIRS').split(';')
model_paths = []
for model_dir in model_dirs:
    model_paths.extend(scan_path_for_models(model_dir, 'gguf'))

model_yml_paths = []
for model_path in model_paths:
    model_yml_path = os.path.join('/model-config', os.path.basename(model_path) + '.yml')
    model_yml_paths.append(model_yml_path)

    if not os.path.exists(model_yml_path):
        with open(model_yml_path, 'w') as f:
            yaml.dump({'file': model_path, 'llama-server': {'--seed': -1}}, f)
        print(f'Created {model_yml_path}')
    else:
        print(f'{model_yml_path} already exists, skipping')

default_set = []
for i, model_yml_path in enumerate(model_yml_paths):
    default_set.append({'file': model_yml_path, 'active': 1 if i == 0 else 0})

default_set_path = '/model-config/default-set.yml'
if not os.path.exists(default_set_path):
    with open(default_set_path, 'w') as f:
        yaml.dump(default_set, f)
else:
    print(f'{default_set_path} already exists, skipping')

default_config_path = '/model-config/default-config.yml'
if not os.path.exists(default_config_path):
    copyfile('/app/default-config.yml', default_config_path)
