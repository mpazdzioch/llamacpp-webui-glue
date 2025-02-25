import os
import re
import yaml

MODEL_DIR = os.getenv("MODEL_DIR")
MODEL_CONFIG_DIR = "/model-config"

def get_base_name(fname):
    if match := re.search(r'(.*?)-\d+-of-\d+\.gguf$', fname):
        return match.group(1)
    return fname.replace('.gguf', '')

def get_total_size(base_path):
    if not os.path.exists(base_path):
        return None
    base_dir = os.path.dirname(base_path)
    base_name = os.path.basename(base_path)
    if match := re.search(r'(.*?)-(\d+)-of-(\d+)\.gguf$', base_name):
        pattern = f"{match.group(1)}-\d+-of-{match.group(3)}\.gguf$"
        related_files = [
            os.path.join(base_dir, f)
            for f in os.listdir(base_dir)
            if re.match(pattern, f)
        ]
        if not all(os.path.exists(f) for f in related_files):
            return None
        return sum(os.path.getsize(f) for f in related_files)
    return os.path.getsize(base_path)

def process_files(file_list, models, yml_paths, file_type):
    counter = {}
    for file in file_list:
        fname = os.path.basename(file)
        base_name = get_base_name(fname) if file_type == 'gguf' else fname
        mname = base_name
        count = counter.get(base_name, 0)
        while mname in models:
            count += 1
            mname = f"{base_name}_{count}"
        counter[base_name] = count
        default_yml_path = f"{MODEL_CONFIG_DIR}/{fname}.yml" if file_type == 'gguf' else file
        yml_paths.append(default_yml_path)
        size_bytes = get_total_size(file)
        if size_bytes is None:
            print(f"Warning: Model file not found or incomplete: {file}")
            continue
        models[mname] = {'path': file, 'id': mname, 'yml_path': default_yml_path, 'size_bytes': size_bytes}

def scan():
    if not MODEL_DIR:
        raise Exception("MODEL_DIR environment variable is not set")
    
    gguf_files = [os.path.join(MODEL_DIR, f) for f in os.listdir(MODEL_DIR) if f.endswith('.gguf')]
    yml_dirs = [MODEL_CONFIG_DIR, MODEL_DIR]
    yml_files = []
    for dir in yml_dirs:
        if not os.path.exists(dir):
            continue
        yml_files.extend([os.path.join(dir, f) for f in os.listdir(dir) if f.endswith('.yml')])
    
    models = {}
    yml_paths = []
    
    # Process GGUF files
    process_files(gguf_files, models, yml_paths, 'gguf')
    
    # Process YML files
    for yml_file in yml_files:
        if yml_file in yml_paths:
            continue
        with open(yml_file, 'r') as stream:
            try:
                yml_content = yaml.safe_load(stream)
                if 'file' not in yml_content:
                    continue
                mname = yml_content.get('model-id', os.path.basename(yml_file))
                size_bytes = get_total_size(yml_content['file'])
                if size_bytes is None:
                    print(f"Warning: Model file not found or incomplete: {yml_content['file']} (referenced in {yml_file})")
                    continue
                models[mname] = {'path': yml_content['file'], 'id': mname, 'yml_path': yml_file, 'size_bytes': size_bytes}
            except yaml.YAMLError as exc:
                print(f"Warning: Error parsing YML file {yml_file}: {exc}")
    
    return models