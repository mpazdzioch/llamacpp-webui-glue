import os
import yaml

model_dir = os.environ.get('MODEL_DIR')
model_paths = [os.path.join(model_dir, f) for f in os.listdir(model_dir) if f.endswith('.gguf')]

model_config_dir = '/model-config'
model_yml_paths = []

for model_path in model_paths:
    model_name = os.path.basename(model_path)
    model_yml_path = os.path.join(model_config_dir, model_name.replace('.gguf', '.gguf.yml'))

    if not os.path.exists(model_yml_path):
        config = {
            'file': model_path,
            'llama-server': {'--seed': -1}
        }

        with open(model_yml_path, 'w') as f:
            yaml.dump(config, f)

        print(f"Created {model_yml_path}")
    else:
        print(f"{model_yml_path} already exists. Skipped.")

    model_yml_paths.append(model_yml_path)