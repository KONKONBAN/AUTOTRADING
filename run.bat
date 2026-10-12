@echo off
setlocal EnableExtensions
title AutoTrading VN
cd /d "%~dp0"
echo ================================================================
echo   AutoTrading VN - dang khoi dong...
echo ================================================================

if not exist "backend\requirements.txt" (
  echo [LOI] Khong tim thay ma nguon ung dung.
  echo       Hay giai nen TOAN BO file ZIP: chuot phai - Extract All, roi chay run.bat trong thu muc vua giai nen.
  goto :fail
)

rem ------------------------------------------------------------------
rem  1. Tim Python 3.10 tro len: py launcher, python tren PATH, thu muc cai mac dinh
rem ------------------------------------------------------------------
set PYCMD=
for %%C in ("py -3.13" "py -3.12" "py -3.11" "py -3.14" "py -3.10" "py -3" "python" "python3") do call :trypy %%C
for %%V in (313 312 311 314 310) do call :trypath "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
for %%V in (313 312 311 314 310) do call :trypath "%ProgramFiles%\Python%%V\python.exe"

if not defined PYCMD (
  echo.
  echo [!] May tinh chua co Python 3.10 tro len - phan mem can thiet de chay ung dung.
  where winget >nul 2>&1
  if errorlevel 1 goto :nopython
  choice /C YN /M "Tu dong cai Python 3.12 tu Microsoft winget? Y = Co, N = Khong"
  if errorlevel 2 goto :nopython
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  call :trypath "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PYCMD goto :nopython
%PYCMD% --version

rem ------------------------------------------------------------------
rem  2. Moi truong rieng .venv - tao lai neu bi hong
rem ------------------------------------------------------------------
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
  if errorlevel 1 rmdir /s /q ".venv"
)
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Tao moi truong Python rieng cho ung dung...
  %PYCMD% -m venv .venv
  if errorlevel 1 (
    echo [LOI] Khong tao duoc moi truong .venv.
    goto :fail
  )
)

rem ------------------------------------------------------------------
rem  3. Cai thu vien - chi khi lan dau hoac khi danh sach thu vien thay doi
rem ------------------------------------------------------------------
fc /b "backend\requirements.txt" ".venv\requirements.installed" >nul 2>&1
if errorlevel 1 (
  echo [2/3] Cai dat thu vien - lan dau mat 2-5 phut, can ket noi Internet...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "backend\requirements.txt"
  if errorlevel 1 (
    echo.
    echo [LOI] Cai thu vien that bai. Kiem tra ket noi Internet roi chay lai run.bat.
    echo       Neu van loi, thu xoa thu muc .venv roi chay lai.
    goto :fail
  )
  copy /y "backend\requirements.txt" ".venv\requirements.installed" >nul
)

rem ------------------------------------------------------------------
rem  4. Giao dien da build san trong frontend\dist - khong can Node.js
rem ------------------------------------------------------------------
if not exist "frontend\dist\index.html" (
  echo [LOI] Thieu giao dien frontend\dist. Hay tai lai ma nguon day du tu GitHub: Code - Download ZIP.
  goto :fail
)

rem ------------------------------------------------------------------
rem  5. Loi tat tren Desktop - hoi mot lan
rem ------------------------------------------------------------------
if not exist ".venv\shortcut.asked" (
  echo asked> ".venv\shortcut.asked"
  choice /C YN /T 20 /D N /M "Tao loi tat AutoTrading VN tren Desktop de lan sau bam mo nhanh? Y = Co, N = Khong"
  if not errorlevel 2 powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\make-shortcut.ps1" -AppDir "%~dp0."
)

echo [3/3] Khoi dong may chu - trinh duyet se tu mo...
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 goto :fail
exit /b 0

:trypy
if defined PYCMD exit /b 0
%~1 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set PYCMD=%~1
exit /b 0

:trypath
if defined PYCMD exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set PYCMD="%~1"
exit /b 0

:nopython
echo.
echo [LOI] Chua co Python. Cach cai:
echo   1. Mo https://www.python.org/downloads/ va tai Python 3.12 hoac 3.13 cho Windows.
echo   2. Khi cai, TICK o "Add python.exe to PATH" roi bam Install Now.
echo   3. Cai xong, bam dup lai run.bat.
goto :fail

:fail
echo.
echo Cua so nay se giu nguyen de ban doc loi. Neu can ho tro, chup man hinh gui lai.
pause
exit /b 1
