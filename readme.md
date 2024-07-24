## Description

This repo links [llama.cpp](https://github.com/ggerganov/llama.cpp) and [open-webui](https://github.com/open-webui/open-webui) in single docker-compose.yml project with simple python API in the middle to launch/kill llama-server instances on demand. The api has bare-bones VRAM management too so it will remove older models from VRAM when there's not enough for new models.
There is no such functionality for RAM, also no CPU only inference setup but I will add it soon.

Services:

- `webui` is a stock docker image from [open-webui](https://github.com/open-webui/open-webui)
- `openresty` is a stock docker image for openresty to proxy openAI api requests from webui to api. Some functionality is implemented as LUA scripts
- `llamacpp` for launching multiple llama-server instances through python Flask API. Dockerfile for this service is based on official llamacpp dockerfile + python for the API.

## Quick start

It's developed and tested on linux. Not tested on other OSs

### Get the Code

```bash
git clone --recurse-submodules https://github.com/mpazdzioch/llamacpp-webui-glue.git
cd llamacpp-webui-glue
```

### 1. Set env vars in .env file

Copy the template file to *.env*: 
```bash
cp env_template .env
```
Edit the *.env* file filling all missing values for your system. In most cases pointing the `MODEL_DIR` to your gguf files folder is all you need to do.

### 2. Run the project
This step may take a while because docker images have to be built. First launch of webui also does some init stuff. 
```bash
docker compose up
```
The webui interface will be available on [localhost:7777](http://localhost:7777). If the ui loads but there's no models to choose from the dropdown list, check the docker compose logs. Both webui and llama instances log everything to stdout of docker compose.

## Common problems

1. There are no models to choose from the dropdown list in webui:
   - Check the logs from llamacpp container for details. For some reason llama-server failed to load the model(s)

## Model configuration details

- You only need folder with .gguf file(s) to use this project. Settings from `./model-config/defaul-config.yml` will be aplied to all models. This file contains default llama-server cli options.

- However, when you want to define custom llama-server options for some models, for example custom GPU split or context size or anything else that llama-server allows using cli options - create a .yml file in `./model-config`. When your model file is named `codestral:22b-v0.1-q8_0.gguf`, create `./model-config/codestral:22b-v0.1-q8_0.gguf.yml` and options from this file will be automatically used when launching this model.

  Example `codestral:22b-v0.1-q8_0.gguf.yml`:
  ```yaml
  file: /home/models/codestral:22b-v0.1-q8_0.gguf
  llama-server:
    --seed: 1337
    --temp: 0
    --ctx-size: 4096
    --mlock: no_value_flag
  ```
  - `file` points to .gguf path
  - `llama-server` is simply a list of cli args to pass to `llama-server`. For options that have no value we use *no_value_flag*. 
  - To get available cli args: 
    ```bash
    docker compose run llamacpp /llama-server -h
    ```

## Folders

- `data`
  - `llamacpp-logs`: log files for each running llama-server process
  - `restylogs`: logs from openresty proxy and LUA scripts
  - `webui-data`: data folder for webui

- `llamacpp`
  - `app`: python API for starting/stopping llama-server instances
  - `llama.cpp`: llama.cpp github repo as submodule. Whenever you want to update to newer version of llamacpp - just pull inside this repo and `docker compose build llamacpp`

- `openresty`: nginx configuration and couple of LUA scripts to proxy openAI api requests to flask API

- `model-config`: we keep all .yml files with custom model configs here

## Scripts

### scan_model_dirs.py
```bash
docker compose run llamacpp python3 scan_model_dirs.py
```
This script will look for .gguf files in path set in `MODEL_DIR` env var in docker-compose.yml
It will generate .yml file for each .gguf file so it's easier to add custom llamacpp configuration for each model. All files are saved to `./model-config` folder.