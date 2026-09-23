@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 run_mira.py
    goto done
)
where python >nul 2>nul
if not errorlevel 1 (
    python run_mira.py
    goto done
)
echo Python 3.11 or newer was not found.
echo Install Python from https://www.python.org/downloads/ and try again.
pause
exit /b 1

:done
if errorlevel 1 (
    echo Mira could not start. Read the error above or open README.md.
    pause
)
