import pynvml

def usage_info():
    pynvml.nvmlInit()
    gpu_count = pynvml.nvmlDeviceGetCount()
    gpu_info = []
    total_memory_free_sum = 0
    total_memory_sum = 0
    mbdiv = 1024 * 1024
    process_memory_usage = {}

    for i in range(gpu_count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
        process_info = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)

        process_details = []
        for process in process_info:
            process_dict = {
                'pid': process.pid,
                'used_memory': process.usedGpuMemory // mbdiv  # Convert to megabytes
            }
            process_details.append(process_dict)

            # Update process_memory_usage dictionary with total VRAM usage for each process
            if process.pid in process_memory_usage:
                process_memory_usage[process.pid] += process.usedGpuMemory // mbdiv
            else:
                process_memory_usage[process.pid] = process.usedGpuMemory // mbdiv

        gpu_dict = {
            'index': i,
            'name': pynvml.nvmlDeviceGetName(handle),
            'memory.total': info.total // mbdiv,  # Convert to megabytes
            'memory.used': info.used // mbdiv,    # Convert to megabytes
            'memory.free': info.free // mbdiv,    # Convert to megabytes
            'utilization.gpu': utilization.gpu,
            'processes': process_details
        }
        gpu_info.append(gpu_dict)
        total_memory_free_sum += info.free // mbdiv
        total_memory_sum += info.total // mbdiv

    pynvml.nvmlShutdown()

    r = {
        'gpu_info': gpu_info,
        'total_free_memory_mb': total_memory_free_sum,
        'total_memory_mb': total_memory_sum,
        'process_memory_usage_mb': process_memory_usage
    }
    return r