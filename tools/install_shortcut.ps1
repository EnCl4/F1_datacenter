# T042 -- create the desktop shortcut.
#
# FR-025 requires starting a recording in a single action, from the desktop, with no
# command line. This makes a .lnk that runs the launcher through pythonw.exe, so no
# console window appears.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\install_shortcut.ps1
#   powershell -ExecutionPolicy Bypass -File tools\install_shortcut.ps1 -StartMenu

[CmdletBinding()]
param(
    [string]$Name = "F1 Data Center",
    [string]$DataDir = "",
    [switch]$StartMenu,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$targetDir = if ($StartMenu) {
    Join-Path ([Environment]::GetFolderPath("Programs")) ""
} else {
    [Environment]::GetFolderPath("Desktop")
}
$linkPath = Join-Path $targetDir "$Name.lnk"

if ($Remove) {
    if (Test-Path $linkPath) { Remove-Item $linkPath; Write-Output "removed $linkPath" }
    else { Write-Output "no shortcut at $linkPath" }
    exit 0
}

# Prefer pythonw.exe from a local venv, so the shortcut keeps working without
# an activated environment; fall back to whatever python is on PATH.
$venvPythonw = Join-Path $repoRoot ".venv\Scripts\pythonw.exe"
if (Test-Path $venvPythonw) {
    $pythonw = $venvPythonw
} else {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) { throw "python not found on PATH and no .venv present" }
    $pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
    if (-not (Test-Path $pythonw)) { $pythonw = $python }
}

$arguments = "-m f1dc.cli.main launch"
if ($DataDir) { $arguments += " --data-dir `"$DataDir`"" }

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $repoRoot
$shortcut.Description = "Start recording F1 23 telemetry"
$shortcut.WindowStyle = 1
$icon = Join-Path $repoRoot "assets\f1dc.ico"
if (Test-Path $icon) { $shortcut.IconLocation = $icon }
$shortcut.Save()

Write-Output "created $linkPath"
Write-Output "  target: $pythonw $arguments"
Write-Output ""
Write-Output "Double-click it before you start playing. It records every session until closed."
