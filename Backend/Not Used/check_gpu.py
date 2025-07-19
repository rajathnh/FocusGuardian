# check_gpu.py
import torch

if torch.cuda.is_available():
    print("SUCCESS: PyTorch can see your GPU.")
    print(f"Device Count: {torch.cuda.device_count()}")
    print(f"Device Name: {torch.cuda.get_device_name(0)}")
    print(f"CUDA Version PyTorch was built with: {torch.version.cuda}")
else:
    print("FAILURE: PyTorch CANNOT see your GPU.")
    print("You need to reinstall PyTorch with the correct CUDA version.")