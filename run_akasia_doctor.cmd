@echo off
setlocal
cd /d "%~dp0"
if exist "dist\AkasiaDoctor.exe" ("dist\AkasiaDoctor.exe" %* & goto :end)
where poetry >nul 2>&1
if %errorlevel% equ 0 (poetry run python akasia_doctor.py %* & goto :end)
echo Install Poetry and run poetry install, or build the executable first.
pause
:end
endlocal

