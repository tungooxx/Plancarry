$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($env:PLANCARRY_WHITEBOX_TOKEN)) { throw "PLANCARRY_WHITEBOX_TOKEN must be set and non-empty" }
python "$Here\preflight.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python "$Here\whitebox_bridge.py" `
  --host 0.0.0.0 `
  --port 8765 `
  --allow-remote `
  --model-id "Qwen/Qwen2.5-1.5B-Instruct" `
  --revision "989aa7980e4cf806f80c7fef2b1adb7bc71aa306" `
  --device cuda `
  --dtype float16 `
  --expected-device-substring "RTX 3050"
exit $LASTEXITCODE
