param(
    [string]$PythonExe = "python",
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8765,
    [string]$ExpectedDevice = "RTX 3050"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrozenModelId = "Qwen/Qwen2.5-1.5B-Instruct"
$FrozenRevision = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
$ExpectedTransformers = "4.46.3"
$ExpectedTokenizers = "0.20.3"

function Pass([string]$Message) { Write-Host "PASS: $Message" -ForegroundColor Green }
function Warn([string]$Message) { Write-Host "WARN: $Message" -ForegroundColor Yellow }
function Fail([string]$Message) { Write-Host "FAIL: $Message" -ForegroundColor Red; $script:Failed = $true }

$script:Failed = $false
Write-Host "PlanCarry RTX3050 white-box bridge preflight (no model weights are loaded)."
Write-Host "Target: ${HostAddress}:$Port ; required device substring: $ExpectedDevice"

# Static artifacts required by the already-verified bounded bridge.
$RequiredFiles = @(
    (Join-Path $Root "whitebox_bridge.py"),
    (Join-Path $Root "whitebox_client.py"),
    (Join-Path $Root "start_whitebox_bridge_rtx3050.ps1"),
    (Join-Path $Root "requirements-whitebox-bridge.txt")
)
foreach ($Path in $RequiredFiles) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) { Pass "file exists: $Path" }
    else { Fail "missing required file: $Path" }
}

# Secrets are existence-checked only. Never echo or interpolate the token value.
if ([string]::IsNullOrWhiteSpace($env:PLANCARRY_WHITEBOX_TOKEN)) {
    Fail "PLANCARRY_WHITEBOX_TOKEN is not set. Set a fresh secret in this PowerShell session."
} else {
    Pass "PLANCARRY_WHITEBOX_TOKEN is set (value intentionally hidden)."
}

if ($env:PLANCARRY_WHITEBOX_MODEL_ID -ne $FrozenModelId) {
    Fail "PLANCARRY_WHITEBOX_MODEL_ID must equal $FrozenModelId exactly."
} else { Pass "frozen model ID matches." }

if ($env:PLANCARRY_WHITEBOX_REVISION -ne $FrozenRevision) {
    Fail "PLANCARRY_WHITEBOX_REVISION must equal $FrozenRevision exactly."
} else { Pass "frozen model revision matches." }

# Package/CUDA/device check only. Importing model libraries does not load model weights.
$env:PLANCARRY_EXPECTED_DEVICE = $ExpectedDevice
$ProbeCode = @'
import json, os
import torch, transformers, tokenizers
info = {
    "torch": torch.__version__,
    "transformers": transformers.__version__,
    "tokenizers": tokenizers.__version__,
    "cuda_available": bool(torch.cuda.is_available()),
    "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
}
print(json.dumps(info, sort_keys=True))
if transformers.__version__ != "4.46.3": raise SystemExit(21)
if tokenizers.__version__ != "0.20.3": raise SystemExit(22)
if not torch.cuda.is_available(): raise SystemExit(23)
if os.environ["PLANCARRY_EXPECTED_DEVICE"].lower() not in torch.cuda.get_device_name(0).lower(): raise SystemExit(24)
'@
try {
    $ProbeOutput = & $PythonExe -c $ProbeCode 2>&1
    if ($LASTEXITCODE -ne 0) {
        Fail "Python/package/CUDA/device preflight failed (exit $LASTEXITCODE): $ProbeOutput"
    } else {
        Pass "Python package versions and RTX3050 CUDA device match: $ProbeOutput"
    }
} catch {
    Fail "Unable to execute Python preflight: $($_.Exception.Message)"
}

# Diagnose whether the desired local bridge port is already occupied.
try {
    $Listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($Listeners.Count -gt 0) {
        Warn "TCP $Port is already LISTENING locally. If this is the bridge, run the health probe below; otherwise stop the conflicting process before launch."
    } else {
        Pass "TCP $Port is not currently occupied by a local listener."
    }
} catch {
    Warn "Could not inspect local TCP listeners with Get-NetTCPConnection: $($_.Exception.Message)"
}

# Read-only Windows Firewall inspection. This helper never creates/changes/removes rules.
$FirewallAllowsPort = $false
try {
    $AllowRules = @(Get-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -ErrorAction Stop)
    foreach ($Rule in $AllowRules) {
        $Filters = @($Rule | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue)
        foreach ($Filter in $Filters) {
            $Protocol = [string]$Filter.Protocol
            $LocalPort = [string]$Filter.LocalPort
            if (($Protocol -eq "TCP" -or $Protocol -eq "6") -and ($LocalPort -eq [string]$Port -or $LocalPort -eq "Any")) {
                $FirewallAllowsPort = $true
                break
            }
        }
        if ($FirewallAllowsPort) { break }
    }
    if ($FirewallAllowsPort) {
        Pass "An enabled inbound Allow firewall rule covers TCP $Port (or all TCP ports)."
    } else {
        Warn "No enabled inbound Allow firewall rule covering TCP $Port was detected."
        Write-Host 'If remote GPU-lab access still times out, an administrator may explicitly add a narrow rule, for example:'
        Write-Host ('  New-NetFirewallRule -DisplayName "PlanCarry Whitebox 8765" -Direction Inbound -Action Allow -Protocol TCP -LocalPort ' + $Port)
        Write-Host 'Review network scope/profile before running any firewall command; this helper does not execute it.'
    }
} catch {
    Warn "Firewall rules could not be inspected (often requires Windows permissions): $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Next commands (manual; no secret value is printed):"
Write-Host ('  & "' + $PythonExe + '" -m pip install -r "' + (Join-Path $Root 'requirements-whitebox-bridge.txt') + '"')
Write-Host ('  & "' + (Join-Path $Root 'start_whitebox_bridge_rtx3050.ps1') + '" -PythonExe "' + $PythonExe + '" -HostAddress "' + $HostAddress + '" -Port ' + $Port + ' -ExpectedDevice "' + $ExpectedDevice + '"')
Write-Host ('  Invoke-RestMethod -Headers @{ Authorization = ("Bearer " + $env:PLANCARRY_WHITEBOX_TOKEN) } -Uri "http://127.0.0.1:' + $Port + '/health"')

if ($script:Failed) {
    Write-Host "Preflight verdict: FAIL. Resolve FAIL items before starting the bridge." -ForegroundColor Red
    exit 2
}
Write-Host "Preflight verdict: PASS_WITH_POSSIBLE_WARNINGS. Start the bridge, run localhost /health, then verify remote 192.168.1.51:$Port from GPU-lab." -ForegroundColor Green
exit 0
