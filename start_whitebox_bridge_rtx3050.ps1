param(
    [string]$PythonExe = "python",
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8765,
    [string]$ExpectedDevice = "RTX 3050"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $env:PLANCARRY_WHITEBOX_TOKEN) { throw "Set PLANCARRY_WHITEBOX_TOKEN to a fresh secret before starting the bridge." }
if (-not $env:PLANCARRY_WHITEBOX_MODEL_ID) { throw "Set PLANCARRY_WHITEBOX_MODEL_ID to the frozen model ID/path." }
if (-not $env:PLANCARRY_WHITEBOX_REVISION) { throw "Set PLANCARRY_WHITEBOX_REVISION to the frozen exact model commit/revision." }
Write-Host "Checking CUDA/model dependencies without loading model weights..."
$env:PLANCARRY_EXPECTED_DEVICE = $ExpectedDevice
& $PythonExe -c "import os, torch, transformers, tokenizers; assert torch.cuda.is_available(); n=torch.cuda.get_device_name(0); needle=os.environ['PLANCARRY_EXPECTED_DEVICE']; print({'torch':torch.__version__,'transformers':transformers.__version__,'tokenizers':tokenizers.__version__,'device':n}); assert needle.lower() in n.lower(), (needle,n)"
if ($LASTEXITCODE -ne 0) { throw "CUDA/dependency/device preflight failed." }
Write-Host "Starting bounded PlanCarry white-box bridge on RTX3050 host. Auth token will not be printed."
& $PythonExe (Join-Path $Root "whitebox_bridge.py") `
  --host $HostAddress `
  --port $Port `
  --allow-remote `
  --model-id $env:PLANCARRY_WHITEBOX_MODEL_ID `
  --revision $env:PLANCARRY_WHITEBOX_REVISION `
  --device cuda `
  --dtype float16 `
  --expected-device-substring $ExpectedDevice
exit $LASTEXITCODE
