param([ValidateRange(1024,65535)][int]$Port = 9222)
$ErrorActionPreference = "Stop"
$existing = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
if ($existing.Count) { throw "Port already in use. Close the dedicated browser or choose another port." }
$locations = @(
    (Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" -ErrorAction SilentlyContinue).'(default)',
    (Get-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" -ErrorAction SilentlyContinue).'(default)',
    (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe"),
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe")
)
$chrome = $locations | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $chrome) { throw "Chrome not found. Install Chrome or locate its registered executable." }
$profile = Join-Path $env:LOCALAPPDATA "CourtIQ\YahooDraftChrome"
$process = Start-Process -FilePath $chrome -ArgumentList @(
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=$Port",
    "--user-data-dir=`"$profile`""
) -PassThru
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($listeners.Count) {
        if (@($listeners | Where-Object { $_.LocalAddress -ne "127.0.0.1" }).Count) {
            Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
            throw "Unsafe CDP bind detected; dedicated browser stopped. Do not add a firewall rule."
        }
        Write-Host "CDP verified: 127.0.0.1:$Port only. Sign in and open Yahoo mock manually."
        exit 0
    }
}
throw "No verified loopback CDP listener. Do not run the observer."
