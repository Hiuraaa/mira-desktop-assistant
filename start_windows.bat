@echo off
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 run_mira.py
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        python run_mira.py
    ) else (
        echo Chua tim thay Python. Hay cai Python 3.11 tro len va bat Add Python to PATH.
        pause
        exit /b 1
    )
)
if errorlevel 1 pause
