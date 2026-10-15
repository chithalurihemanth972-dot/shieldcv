# SHIELD-CV — create/update the Desktop icon.
# Run once (right-click > Run with PowerShell) or via:
#   powershell -ExecutionPolicy Bypass -File install_desktop_icon.ps1
# What it does: creates ~/Desktop/SHIELD-CV.lnk pointing at the project .venv
# pythonw.exe with SHIELD-CV.pyw, using assets/shield.ico. Re-running only
# overwrites that one .lnk — nothing else on the system is touched.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPy = Join-Path $Root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $VenvPy)) {
  # No venv (e.g. fresh clone): fall back to system pythonw for the .pyw.
  $VenvPy = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
  if (-not $VenvPy) { $VenvPy = (Get-Command python -ErrorAction SilentlyContinue).Source }
  if (-not $VenvPy) { throw "No Python found. Install Python 3.10+ and retry." }
}
$Target = Join-Path $Root "SHIELD-CV.pyw"
$Icon = Join-Path $Root "assets\shield.ico"
$Desktop = [Environment]::GetFolderPath("Desktop")
$Link = Join-Path $Desktop "SHIELD-CV.lnk"

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($Link)
$Shortcut.TargetPath = $VenvPy
$Shortcut.Arguments = "`"$Target`""
$Shortcut.WorkingDirectory = $Root
$Shortcut.Description = "SHIELD-CV Defence CV Integrity Dashboard (offline)"
if (Test-Path -LiteralPath $Icon) { $Shortcut.IconLocation = $Icon }
$Shortcut.Save()

Write-Host "Desktop icon ready: $Link"
Write-Host "Target: $($Shortcut.TargetPath) $($Shortcut.Arguments)"
