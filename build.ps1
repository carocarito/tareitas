$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m pip install -r requirements.txt
$buildRoot = Join-Path $env:LOCALAPPDATA 'TareitasTkBuild'
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "Tareitas" --workpath "$buildRoot\work" --specpath "$buildRoot\spec" --distpath "$buildRoot\dist" main.py
Write-Host "Listo: $buildRoot\dist\Tareitas.exe"
