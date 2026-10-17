# Builds dist\VOE Explorer.exe and dist\VOE-Explorer-<version>.zip (exe + «Як запустити.png").
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    py -m venv .venv
    & $py -m pip install -q -e ".[dev]"
}

$version = & $py -c "import voe_explorer; print(voe_explorer.__version__)"

& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "VOE Explorer" `
    --paths (Join-Path $root "src") `
    --add-data "$(Join-Path $root 'src\voe_explorer\ui');voe_explorer/ui" `
    --distpath (Join-Path $root "dist") --workpath (Join-Path $root "build") --specpath (Join-Path $root "build") `
    (Join-Path $root "packaging\launcher.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$stage = Join-Path $root "build\zip"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item "dist\VOE Explorer.exe" $stage
& $py packaging/make_howto.py (Join-Path $stage "Як запустити.png")
if ($LASTEXITCODE -ne 0) { throw "make_howto failed" }

$zip = Join-Path $root "dist\VOE-Explorer-$version.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip
Write-Host "Built $zip"
