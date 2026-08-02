@echo off
setlocal
cd /d "%~dp0"

if not exist ".setup-complete" (
    echo First run detected. Installing required dependencies...
    call "%~dp0setup.bat" --auto
    if errorlevel 1 (
        echo.
        echo The application could not be started because setup failed.
        pause
        exit /b 1
    )
)

if not exist "backend\.venv\Scripts\python.exe" (
    echo The backend environment is missing. Running setup again...
    call "%~dp0setup.bat" --auto
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

if not exist "frontend\node_modules" (
    echo Frontend dependencies are missing. Running setup again...
    call "%~dp0setup.bat" --auto
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

echo Starting backend...
start "Rehost Backend" cmd /k "cd /d ""%~dp0backend"" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

echo Starting frontend...
start "Rehost Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev -- --host localhost --port 5173 --strictPort"

echo Opening the application in your browser...
timeout /t 5 /nobreak >nul
start "" "http://localhost:5173"

exit /b 0
