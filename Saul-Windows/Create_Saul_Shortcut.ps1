param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDirectory
)
$ErrorActionPreference = 'Stop'
$launcher = Join-Path $InstallDirectory 'Launch_Saul.vbs'
$icon = Join-Path $InstallDirectory 'saul.ico'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Saul launcher is missing.' }
if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) { throw 'Saul icon is missing.' }
$desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($desktop)) { throw 'Windows Desktop folder is unavailable.' }
$shell = New-Object -ComObject WScript.Shell
$scriptArg = '"' + $launcher + '"'
$shortcutPath = Join-Path $desktop 'Saul Aura.lnk'
if (Test-Path -LiteralPath $shortcutPath) {
    $existing = $shell.CreateShortcut($shortcutPath)
    if ($existing.Arguments -ne $scriptArg) {
        $shortcutPath = Join-Path $desktop 'Saul Aura (Orynth).lnk'
        if (Test-Path -LiteralPath $shortcutPath) {
            $existing = $shell.CreateShortcut($shortcutPath)
            if ($existing.Arguments -ne $scriptArg) {
                throw 'The Saul Aura shortcut names are used by another application.'
            }
        }
    }
}
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\wscript.exe'
$shortcut.Arguments = $scriptArg
$shortcut.WorkingDirectory = $InstallDirectory
$shortcut.IconLocation = "$icon,0"
$shortcut.Description = 'Saul Aura voice assistant'
$shortcut.Save()
Write-Output "Saul desktop shortcut: $shortcutPath"
