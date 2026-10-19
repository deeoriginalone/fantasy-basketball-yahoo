param(
    [Parameter(Mandatory=$true)][string]$PracticeSession,
    [string]$Origin = "https://192.168.0.85:18002",
    [ValidateRange(1024,65535)][int]$Port = 9222
)
$ErrorActionPreference = "Stop"
$parsedSession = [guid]::Empty
if (-not [guid]::TryParse($PracticeSession, [ref]$parsedSession)) {
    throw "Supply the disposable Court IQ practice session ID, never a Yahoo URL."
}
$secure = Read-Host "Dedicated Court IQ observer secret (not a Yahoo credential)" -AsSecureString
$env:COURT_IQ_OBSERVER_SECRET = [System.Net.NetworkCredential]::new("", $secure).Password
try {
    $observer = Join-Path $PSScriptRoot "observer.py"
    $observerArgs = @("-3", $observer, "--inspect-picks", "--watch", "--practice",
        "--practice-session=$PracticeSession", "--origin=$Origin", "--port=$Port")
    # Picks is already open. Do not click or reload Yahoo while starting the bridge.
    & py @observerArgs
    $result = $LASTEXITCODE
} finally {
    Remove-Item Env:\COURT_IQ_OBSERVER_SECRET -ErrorAction SilentlyContinue
}
exit $result
