param(
    [string]$Origin = "https://192.168.0.85:18002",
    [ValidateRange(1024,65535)][int]$Port = 9222
)
$ErrorActionPreference = "Stop"
$observer = Join-Path $PSScriptRoot "observer.py"
$parser = Join-Path $PSScriptRoot "picks.py"
if (-not (Test-Path -LiteralPath $parser)) { throw "Copy picks.py into this folder first." }
$observerArgs = @(
    "-3", $observer, "--inspect-picks", "--open-picks", "--watch",
    "--origin=$Origin", "--port=$Port"
)
& py @observerArgs
exit $LASTEXITCODE
