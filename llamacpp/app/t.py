import json
import gpu
import os
import yaml

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

f = scan_model_files()
print(json.dumps(f))