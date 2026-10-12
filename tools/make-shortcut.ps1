# Tạo lối tắt "AutoTrading VN" trên Desktop trỏ tới run.bat (gọi từ run.bat, chỉ hỏi một lần).
param([Parameter(Mandatory = $true)][string]$AppDir)
$AppDir = [IO.Path]::GetFullPath($AppDir).TrimEnd('\')
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path $desktop 'AutoTrading VN.lnk'))
$lnk.TargetPath = Join-Path $AppDir 'run.bat'
$lnk.WorkingDirectory = $AppDir
$ico = Join-Path $AppDir 'tools\autotrading.ico'
if (Test-Path $ico) { $lnk.IconLocation = $ico }
$lnk.Description = 'AutoTrading VN - Phan tich co phieu va AI quan tri tai san'
$lnk.Save()
Write-Host 'Da tao loi tat AutoTrading VN tren Desktop.'
