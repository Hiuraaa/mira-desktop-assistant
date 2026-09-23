@echo off
cd /d "%~dp0"
py -3 run_mira.py
if errorlevel 1 pause
