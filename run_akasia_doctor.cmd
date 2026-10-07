@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel% equ 0 (py -3 akasia_doctor.py & goto :end)
where python >nul 2>&1
if %errorlevel% equ 0 (python akasia_doctor.py & goto :end)
echo Python 3 was not found. Install Python 3 and try again.
pause
:end
endlocal

