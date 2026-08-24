@echo off
setlocal

set "CURRENT_DIR=%~dp0"
if exist "%CURRENT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON=%CURRENT_DIR%.venv\Scripts\python.exe"
) else if exist "%CURRENT_DIR%venv\Scripts\python.exe" (
    set "PYTHON=%CURRENT_DIR%venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON=py -3"
)

if not defined PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON=python"
)

if not defined PYTHON (
    echo Python 3.11 or newer was not found.
    exit /b 1
)

%PYTHON% "%CURRENT_DIR%update_toml.py" %*
exit /b %errorlevel%