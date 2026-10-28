$ErrorActionPreference = 'Stop'
$taskCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $taskCompiler)) {
    $taskCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
}
& $taskCompiler /nologo /target:winexe /platform:anycpu /optimize+ /reference:System.Windows.Forms.dll /win32icon:"$PSScriptRoot\DesktopKeys.ico" "/out:$PSScriptRoot\DesktopKeys.exe" "$PSScriptRoot\DesktopKeys.cs"
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
Get-Item -LiteralPath (Join-Path $PSScriptRoot 'DesktopKeys.exe') | Select-Object Name, Length
