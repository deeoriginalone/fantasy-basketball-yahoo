$ErrorActionPreference = "Stop"
$install = Join-Path $env:LOCALAPPDATA "CourtIQ\Observer"
New-Item -ItemType Directory -Force -Path $install | Out-Null
$venv = Join-Path $install "venv"
$desktop = Join-Path $install "desktop.py"
# Replace only this installed agent; preserve Chrome, DPAPI configuration and pairing.
$agent = Join-Path $venv "Scripts\pythonw.exe"
Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -eq $agent -and $_.CommandLine -like "*`"$desktop`"*"
} | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction Stop }
$files = @("desktop.py", "observer.py", "picks.py", "requirements.txt", "Launch-YahooDraftChrome.ps1")
foreach ($name in $files) {
    $from = Join-Path $PSScriptRoot $name
    $to = Join-Path $install $name
    if ([IO.Path]::GetFullPath($from) -ne [IO.Path]::GetFullPath($to)) {
        Copy-Item -LiteralPath $from -Destination $to -Force
    }
}
if (-not (Test-Path (Join-Path $venv "Scripts\pythonw.exe"))) {
    & py -3 -m venv $venv
    if ($LASTEXITCODE) { throw "Install Python 3.11+ with the Python launcher, then rerun setup." }
}
$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --disable-pip-version-check -r (Join-Path $install "requirements.txt")
if ($LASTEXITCODE) { throw "Observer dependency setup failed." }
$pythonw = Join-Path $venv "Scripts\pythonw.exe"
$shell = New-Object -ComObject WScript.Shell
$menu = Join-Path ([Environment]::GetFolderPath("Programs")) "Court IQ"
New-Item -ItemType Directory -Force -Path $menu | Out-Null
foreach ($entry in @(
    @{Name="Court IQ Yahoo Chrome"; Arguments="`"$desktop`""},
    @{Name="Court IQ Observer Setup"; Arguments="`"$desktop`" --setup"},
    @{Name="Court IQ Observer Diagnostics"; Arguments="`"$desktop`" --diagnostic"}
)) {
    $shortcut = $shell.CreateShortcut((Join-Path $menu ($entry.Name + ".lnk")))
    $shortcut.TargetPath = $pythonw
    if ($entry.Name -eq "Court IQ Observer Diagnostics") { $shortcut.TargetPath = $python }
    $shortcut.Arguments = $entry.Arguments
    $shortcut.WorkingDirectory = $install
    $shortcut.Save()
}
# Current-user startup only. No service, administrator privileges or firewall rule.
$startup = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Startup")) "Court IQ Observer.lnk"))
$startup.TargetPath = $pythonw
$startup.Arguments = "`"$desktop`""
$startup.WorkingDirectory = $install
$startup.Save()
Start-Process -FilePath $pythonw -ArgumentList @("`"$desktop`"") -WindowStyle Hidden
