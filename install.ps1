# Install ccx from this clone (Windows). Usage: .\install.ps1 [-Hub D:\path\to\hub]
param([string]$Hub = "")
# "Continue", not "Stop": Windows PowerShell 5.1 turns a native program's stderr into an error once output is
# redirected (.\install.ps1 > log.txt), and pipx writes its progress there. Exit codes are checked instead.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 'ccx needs Python 3.11+')"
if ($LASTEXITCODE -ne 0) { exit 1 }
$pipxFailed = $false
if (Get-Command pipx -ErrorAction SilentlyContinue) {
  pipx install --force --editable .
  if ($LASTEXITCODE -ne 0) {
    $pipxFailed = $true
    Write-Host "pipx install failed (see above). ccx still works from this folder: python ccx.py ..." -ForegroundColor Yellow
  }
} else {
  Write-Host "pipx not found: add $PSScriptRoot\bin to PATH to use 'ccx' (or: python -m pip install --user -e .)"
}
if ($Hub) { python -X utf8 ccx.py init --hub $Hub } else { python -X utf8 ccx.py init }
if ($LASTEXITCODE -ne 0) { exit 1 }
python -X utf8 ccx.py doctor
Write-Host "`nNext: python ccx.py setup   (guided: explains each step and asks before changing anything)"
if ($pipxFailed) { exit 1 }
