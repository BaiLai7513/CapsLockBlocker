@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CapsLock Mapper - source runner

fltmc >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator privileges...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "PY_EXE="
set "PY_ARGS="

where py >nul 2>&1
if not errorlevel 1 (
    py -3.11 -c "import sys, tkinter" >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=py"
        set "PY_ARGS=-3.11"
    )
)
if not defined PY_EXE (
    py -3 -c "import sys, tkinter" >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=py"
        set "PY_ARGS=-3"
    )
)
if not defined PY_EXE (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys, tkinter" >nul 2>&1
        if not errorlevel 1 set "PY_EXE=python"
    )
)
if not defined PY_EXE (
    echo [ERROR] Python 3 with tkinter not found.
    pause
    exit /b 1
)

"%PY_EXE%" %PY_ARGS% caps_lock_blocker.py %*
if errorlevel 1 (
    echo.
    echo Program exited with an error.
    pause
)
