# Sets up what Jarvis needs to run, without asking questions: Python (3.10 to 3.13), Jarvis's own Python
# environment in the .venv folder, and its packages. The installer (JarvisSetup.exe) runs it after copying the
# files, and the Start menu's "Repair Jarvis" runs it again. Everything goes into the Jarvis folder, except Python
# itself when it is missing (installed for this Windows user only, from winget or python.org).
#
#   powershell -ExecutionPolicy Bypass -File tools\setup-jarvis.ps1 [-Root <folder>] [-Version 2026.11.26] [-Voice] [-Releases] [-Files]
#   -Files (Repair Jarvis) also restores missing program files and brings back the ones an update would replace;
#   files you changed yourself are left alone.
#
# Exit codes: 0 ready, 1 no Python, 2 the environment could not be made, 3 the packages did not install.
# Keep this file ASCII: Windows PowerShell 5 reads scripts without a byte order mark in the local code page.
param(
    [string]$Root = "",
    [string]$Version = "",
    [switch]$Voice,
    [switch]$Releases,
    [switch]$Files
)
$ErrorActionPreference = "Continue"
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
$Root = (Resolve-Path $Root).Path
try { $Host.UI.RawUI.WindowTitle = "Jarvis setup" } catch {}
$data = Join-Path $Root "data"
New-Item -ItemType Directory -Force -Path $data | Out-Null
$log = Join-Path $data "install.log"

function Say([string]$text) {
    Write-Host $text
    try { Add-Content -Path $log -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $text) -Encoding UTF8 } catch {}
}

function Test-Python([string]$exe) {
    # 3.10 to 3.13: the newest Python often has no ready-made packages yet.
    if (-not $exe -or -not (Test-Path $exe) -or $exe -like "*\WindowsApps\*") { return $false }
    & $exe -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Find-Python {
    foreach ($v in "3.12", "3.13", "3.11", "3.10") {
        try {
            $exe = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe -and (Test-Python $exe.Trim())) { return $exe.Trim() }
        } catch {}
    }
    foreach ($v in "312", "313", "311", "310") {
        foreach ($base in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles", "${env:ProgramFiles(x86)}")) {
            $c = Join-Path $base "Python$v\python.exe"
            if (Test-Python $c) { return $c }
        }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and (Test-Python $cmd.Source)) { return $cmd.Source }
    return $null
}

function Install-Python {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "Installing Python 3.12 for this Windows user (winget)..."
        & winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
        $found = Find-Python
        if ($found) { return $found }
    }
    Say "Downloading Python 3.12 from python.org..."
    $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    $file = Join-Path $env:TEMP "python-3.12.10-amd64.exe"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $file -UseBasicParsing
        $sig = Get-AuthenticodeSignature $file
        if ($sig.Status -ne "Valid" -or $sig.SignerCertificate.Subject -notlike "*Python Software Foundation*") {
            Say "The downloaded Python installer is not signed by the Python Software Foundation, so it was not run."
            return $null
        }
        Start-Process -FilePath $file -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1", "Include_test=0" -Wait
    } catch {
        Say ("Could not download Python: " + $_.Exception.Message)
        return $null
    } finally {
        Remove-Item $file -ErrorAction SilentlyContinue
    }
    return Find-Python
}

Say "Setting up Jarvis in $Root"

# ---- 1. Python ----
$python = Find-Python
if (-not $python) { $python = Install-Python }
if (-not $python) {
    Say "Python 3.10 to 3.13 was not found and could not be installed. Install Python 3.12 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run 'Repair Jarvis' from the Start menu."
    exit 1
}
Say ("Python: " + $python)

# ---- 2. Jarvis's own environment (.venv) ----
$venv = Join-Path $Root ".venv"
$vpy = Join-Path $venv "Scripts\python.exe"
if ((Test-Path $vpy) -and -not (Test-Python $vpy)) {
    Say "The old environment uses a Python that does not suit Jarvis; making it again..."
    Remove-Item -Recurse -Force $venv -ErrorAction SilentlyContinue
}
if (-not (Test-Path $vpy)) {
    Say "Making Jarvis's own Python environment..."
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $vpy)) {
        Say "Could not make the environment in $venv."
        exit 2
    }
}

# ---- 2b. Program files (Repair Jarvis) ----
if ($Files) {
    Say "Checking Jarvis's program files against the newest version..."
    & $vpy (Join-Path $Root "filecheck.py") --update --yes
    if ($LASTEXITCODE -ne 0) { Say "Some program files could not be checked or restored (no internet?). Jarvis goes on with what it has." }
}

# ---- 3. Packages ----
Say "Installing the packages Jarvis uses (a few minutes the first time)..."
& $vpy -m pip install --disable-pip-version-check --upgrade pip 2>&1 | Out-Null
& $vpy -m pip install --disable-pip-version-check -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Say "The packages did not install. Check the internet connection, then run 'Repair Jarvis' from the Start menu."
    exit 3
}
if ($Voice) {
    Say "Adding speech recognition for the wake word and dictation (optional, about 150 MB)..."
    & $vpy -m pip install --disable-pip-version-check --upgrade faster-whisper av
    if ($LASTEXITCODE -ne 0) { Say "Speech recognition could not be added. Jarvis works without it; 'Repair Jarvis' tries again." }
}

# ---- 4. Where updates come from, and the version ----
if ($Releases) {
    $cfgPath = Join-Path $data "filecheck.json"
    $cfg = @{}
    if (Test-Path $cfgPath) {
        try { (Get-Content $cfgPath -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $cfg[$_.Name] = $_.Value } } catch {}
    }
    $cfg["channel"] = "releases"
    ($cfg | ConvertTo-Json) | Set-Content -Path $cfgPath -Encoding ASCII
}
if ($Version) {
    $tag = if ($Version.StartsWith("v")) { $Version } else { "v" + $Version }
    (@{ version = $Version.TrimStart("v"); tag = $tag; at = [int64](([DateTime]::UtcNow - [DateTime]'1970-01-01').TotalSeconds) } | ConvertTo-Json) | Set-Content -Path (Join-Path $data "version.json") -Encoding ASCII
}

Say "Jarvis is ready."
exit 0
