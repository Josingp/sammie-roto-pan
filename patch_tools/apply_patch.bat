@echo off
setlocal
cd /d "%~dp0"

set "APP="
set "TMPF=%TEMP%\sammie_pan_app.txt"
if exist "%TMPF%" del "%TMPF%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $l=Join-Path $d 'Sammie-Roto PAN.lnk'; if(Test-Path $l){(New-Object -ComObject WScript.Shell).CreateShortcut($l).WorkingDirectory}" > "%TMPF%" 2>nul
if exist "%TMPF%" set /p APP=<"%TMPF%"
if defined APP if exist "%APP%\.venv\Scripts\python.exe" goto found

:ask
echo.
echo Could not find the Sammie-Roto PAN folder automatically.
echo Drag the Sammie-Roto PAN install folder into this window, then press Enter.
set "APP="
set /p "APP=> "
set "APP=%APP:"=%"
if not exist "%APP%\.venv\Scripts\python.exe" (
    echo.
    echo Not a Sammie-Roto PAN install folder: %APP%
    pause
    exit /b 1
)

:found
set "PYTHONUTF8=1"
"%APP%\.venv\Scripts\python.exe" "%~dp0pan_patch.py" "%APP%" "%~dp0files"
echo.
pause
