@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CapsLock Mapper Builder

echo ========================================
echo   CapsLock Mapper - build EXE
echo ========================================
echo.

set "PY_EXE="
set "PY_ARGS="
set "NEED_PYI="

call :probe "%~dp0venv\Scripts\python.exe" ""
call :probe "%~dp0.venv\Scripts\python.exe" ""
call :probe "py" "-3.11"
call :probe "py" "-3.12"
call :probe "py" "-3.13"
call :probe "py" "-3.10"
call :probe "py" "-3.14"
call :probe "py" "-3"
call :probe "python" ""

if not defined PY_EXE (
    call :probe_any "%~dp0venv\Scripts\python.exe" ""
    call :probe_any "%~dp0.venv\Scripts\python.exe" ""
    call :probe_any "py" "-3.11"
    call :probe_any "py" "-3.12"
    call :probe_any "py" "-3.13"
    call :probe_any "py" "-3.10"
    call :probe_any "py" "-3.14"
    call :probe_any "py" "-3"
    call :probe_any "python" ""
)

if not defined PY_EXE goto :no_python

echo [1/3] Python: %PY_EXE% %PY_ARGS%
"%PY_EXE%" %PY_ARGS% -c "import sys, tkinter" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] tkinter is missing in this Python installation.
    pause
    exit /b 1
)

if defined NEED_PYI (
    echo [2/3] PyInstaller not found; installing...
    "%PY_EXE%" %PY_ARGS% -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo [ERROR] PyInstaller installation failed.
        echo Run manually:
        echo   "%PY_EXE%" %PY_ARGS% -m pip install pyinstaller
        pause
        exit /b 1
    )
) else (
    echo [2/3] PyInstaller OK
)

set "SPEC_FILE="
for %%F in ("%~dp0*.spec") do if not defined SPEC_FILE set "SPEC_FILE=%%~fF"
if not defined SPEC_FILE (
    echo [ERROR] No .spec file found next to this script.
    pause
    exit /b 1
)

echo [3/3] Building onedir package...
if exist "dist" rmdir /s /q "dist"
"%PY_EXE%" %PY_ARGS% -m PyInstaller --clean --noconfirm "%SPEC_FILE%"
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

set "OUT_EXE="
for /r "%~dp0dist" %%I in (*.exe) do if not defined OUT_EXE set "OUT_EXE=%%~fI"
if not defined OUT_EXE (
    echo [ERROR] No EXE found under dist after build.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Build complete
echo   EXE: %OUT_EXE%
for %%I in ("%OUT_EXE%") do echo   Size: %%~zI bytes
echo.
echo   Keep the whole dist\GameCapslockMapper folder together.
echo   Do not move the exe out of its _internal folder.
echo ========================================
echo.
echo Tip: add the whole GameCapslockMapper folder to your antivirus whitelist.
pause
exit /b 0

:probe
if defined PY_EXE exit /b 0
"%~1" %~2 -c "import sys, tkinter" >nul 2>&1
if errorlevel 1 exit /b 0
"%~1" %~2 -m pip show pyinstaller >nul 2>&1
if errorlevel 1 exit /b 0
set "PY_EXE=%~1"
set "PY_ARGS=%~2"
exit /b 0

:probe_any
if defined PY_EXE exit /b 0
"%~1" %~2 -c "import sys, tkinter" >nul 2>&1
if errorlevel 1 exit /b 0
set "PY_EXE=%~1"
set "PY_ARGS=%~2"
set "NEED_PYI=1"
exit /b 0

:no_python
echo [ERROR] No Python 3 with tkinter found.
echo Install Python 3.8+ and enable "Add Python to PATH".
pause
exit /b 1
