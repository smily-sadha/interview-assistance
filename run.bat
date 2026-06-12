@echo off
REM Double-click this file (or run it in a terminal) to start Glass Assistant.
REM It uses the project's own virtual-environment Python directly, so it
REM never accidentally runs on the wrong system Python.
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py
pause
