@echo off
setlocal
cd /d "%~dp0"
where poetry >nul 2>&1
if errorlevel 1 (
    echo Poetry was not found. Install Poetry to build the executable.
    exit /b 1
)

poetry install --with build
if errorlevel 1 exit /b 1

poetry run python -m PyInstaller --noconfirm --clean --onefile --console --collect-data textual --name AkasiaDoctor --specpath build --workpath build --distpath dist akasia_doctor.py
if errorlevel 1 exit /b 1

echo Built: %~dp0dist\AkasiaDoctor.exe
endlocal