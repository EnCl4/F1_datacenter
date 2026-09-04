# Create the desktop shortcuts.
#
# FR-025 requires starting a recording in a single action, from the desktop, with no
# command line. Two shortcuts are made, because the driver has two separate intents:
#
#   "F1 Data Center - Record"    start capturing, before playing
#   "F1 Data Center - Library"   interpret new recordings and open the browser
#
# The recorder runs through pythonw.exe so no console appears -- it has its own window.
# The library runs through python.exe on purpose: it is a local server, and the console
# window IS the "it is running, close me to stop" affordance.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\install_shortcut.ps1
#   powershell -ExecutionPolicy Bypass -File tools\install_shortcut.ps1 -StartMenu
#   powershell -ExecutionPolicy Bypass -File tools\install_shortcut.ps1 -Remove

[CmdletBinding()]
param(
    [string]$DataDir = "",
    [switch]$StartMenu,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$targetDir = if ($StartMenu) {
    [Environment]::GetFolderPath("Programs")
} else {
    [Environment]::GetFolderPath("Desktop")
}

$names = @("F1 Data Center - Record", "F1 Data Center - Library")

if ($Remove) {
    foreach ($name in $names) {
        $path = Join-Path $targetDir "$name.lnk"
        if (Test-Path $path) { Remove-Item $path; Write-Output "removed $path" }
    }
    exit 0
}

# Prefer a local venv so the shortcuts keep working without an activated environment.
$venvDir = Join-Path $repoRoot ".venv\Scripts"
if (Test-Path (Join-Path $venvDir "python.exe")) {
    $python = Join-Path $venvDir "python.exe"
    $pythonw = Join-Path $venvDir "pythonw.exe"
} else {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) { throw "python was not found on PATH, and there is no .venv in $repoRoot" }
    $pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
    if (-not (Test-Path $pythonw)) { $pythonw = $python }
}

# Fail loudly here rather than leaving a shortcut that silently does nothing.
& $python -c "import f1dc" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "f1dc is not installed for $python. Run:  $python -m pip install -e `"$repoRoot`""
}

$suffix = ""
if ($DataDir) { $suffix = " --data-dir `"$DataDir`"" }

$shell = New-Object -ComObject WScript.Shell

function New-Shortcut($name, $exe, $arguments, $description) {
    $path = Join-Path $targetDir "$name.lnk"
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $exe
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $repoRoot
    $shortcut.Description = $description
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    Write-Output "  $name"
    Write-Output "      $exe $arguments"
}

Write-Output "created in $targetDir :"
New-Shortcut $names[0] $pythonw "-m f1dc.cli.main launch$suffix" `
    "Start recording F1 23 telemetry. Open this before you play."
New-Shortcut $names[1] $python "-m f1dc.cli.main open$suffix" `
    "Interpret new recordings and browse your sessions."

Write-Output ""
Write-Output "Before playing:  double-click 'F1 Data Center - Record'"
Write-Output "To see the data: double-click 'F1 Data Center - Library'"
