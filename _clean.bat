@echo off
del /q "D:\Administrator\administartor\Pictures\*" 2>nul
for /d %%i in ("D:\Administrator\administartor\Pictures\*") do rmdir /s /q "%%i" 2>nul
echo done
