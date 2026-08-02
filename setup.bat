@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo Rehost Migration Tool - Initial Setup
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo Install Python 3.11 or newer and enable "Add Python to PATH".
    goto :failed
)

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm was not found in PATH.
    echo Install the Node.js LTS version and try again.
    goto :failed
)

if not exist "backend\.venv\Scripts\python.exe" (
    echo [1/3] Creating the Python virtual environment...
    python -m venv "backend\.venv"
    if errorlevel 1 goto :failed
) else (
    echo [1/3] Python virtual environment already exists.
)

echo [2/3] Installing backend dependencies...
"backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 goto :failed

echo [3/3] Installing frontend dependencies...
pushd "frontend"
call npm ci
if errorlevel 1 (
    popd
    goto :failed
)
popd

> ".setup-complete" echo Setup completed successfully.
echo.
echo Setup completed successfully.
echo You can now double-click start.bat.
if /I not "%~1"=="--auto" pause
exit /b 0

:failed
echo.
echo Setup could not be completed. Review the error above and try again.
if /I not "%~1"=="--auto" pause
exit /b 1
