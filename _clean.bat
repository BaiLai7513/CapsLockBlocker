@echo off
setlocal
cd /d "%~dp0"
echo Cleaning build, dist and __pycache__...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "__pycache__" rmdir /s /q "__pycache__"
if exist "tests\__pycache__" rmdir /s /q "tests\__pycache__"
echo Done. Source files and user files were not touched.
pause
