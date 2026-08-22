# PlanCarry RTX3050 white-box bridge bundle

This bundle is deployment-only. It does not contain or run ALFWorld science.

1. Install a CUDA-enabled PyTorch build appropriate for the RTX3050 host. Do not rely on this requirements file to choose a torch wheel.
2. `python -m pip install -r requirements.txt`
3. Set a strong `PLANCARRY_WHITEBOX_TOKEN` environment variable.
4. Windows: `powershell -ExecutionPolicy Bypass -File .\launch_windows.ps1`
   Linux: `./launch_linux.sh`
5. From the lab/client side, set the same token and run `python probe.py --url http://192.168.1.51:8765`.
6. Only after provenance passes, run `python smoke.py --url http://192.168.1.51:8765` (synthetic protocol text only).

The launcher hard-pins model/revision/FP16/CUDA/RTX3050 and has no Ollama or alternate-GPU fallback.
