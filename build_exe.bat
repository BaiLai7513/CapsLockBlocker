@echo off

:: ============================================================
:: 防止双击闪退 —— 检测到外层调用时，用 cmd /k 重开自己
:: ============================================================
if not defined BUILD_EXE_INNER (
    set BUILD_EXE_INNER=1
    start "" /wait cmd /k "%~f0" %*
    exit /b
)

title CapsLock 打包工具
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   CapsLock 锁定工具 - EXE 打包脚本
echo   含 UAC 提权（管理员权限）
echo ========================================
echo.

:: ---- 自动查找 Python（优先 venv，其次 PATH） ----
set PYTHON_EXE=
set PIP_EXE=

:: 候选路径（从近到远）
if exist "..\venv\Scripts\python.exe" (
    set PYTHON_EXE=..\venv\Scripts\python.exe
    set PIP_EXE=..\venv\Scripts\pip.exe
)
if not defined PYTHON_EXE if exist "%USERPROFILE%\venv\Scripts\python.exe" (
    set PYTHON_EXE=%USERPROFILE%\venv\Scripts\python.exe
    set PIP_EXE=%USERPROFILE%\venv\Scripts\pip.exe
)
:: 回退到系统 PATH
if not defined PYTHON_EXE (
    where python >nul 2>&1 && set PYTHON_EXE=python
)
if not defined PIP_EXE (
    where pip >nul 2>&1 && set PIP_EXE=pip
)
if not defined PYTHON_EXE (
    echo [错误] 未找到 Python，请先安装 Python 3.6+
    pause
    exit /b 1
)

echo [1/3] 检查 Python 环境...
"%PYTHON_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Python 执行失败
    pause
    exit /b 1
)
echo         Python 环境正常  [%PYTHON_EXE%]

echo [2/3] 检查 PyInstaller...
"%PIP_EXE%" show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo         PyInstaller 未安装，正在安装...
    "%PIP_EXE%" install pyinstaller -i https://pypi.org/simple --trusted-host pypi.org --trusted-host files.pythonhosted.org
    if %errorlevel% neq 0 (
        echo [错误] PyInstaller 安装失败，请检查网络连接
        pause
        exit /b 1
    )
) else (
    echo         PyInstaller 已安装
)

:: 找到 pyinstaller.exe 的位置
for /f "delims=" %%i in ('"%PIP_EXE%" show pyinstaller ^| findstr "Location:"') do set _PYI_LOC=%%i
set _PYI_LOC=%_PYI_LOC:Location: =%
set PYI_EXE=%_PYI_LOC%\pyinstaller.exe
if not exist "%PYI_EXE%" set PYI_EXE=%_PYI_LOC%\Scripts\pyinstaller.exe
if not exist "%PYI_EXE%" (
    where pyinstaller >nul 2>&1 && set PYI_EXE=pyinstaller
)

echo [3/3] 开始打包（含 UAC manifest）...
echo.
echo         打包参数说明:
echo           --onefile   : 打包为单个 EXE 文件
echo           --windowed  : 不显示控制台窗口（GUI 模式）
echo           --manifest  : 嵌入 UAC requireAdministrator（在 spec 中配置）
echo           --clean     : 清理旧构建
echo.

"%PYI_EXE%" ^
    --clean ^
    "CapsLock锁定工具.spec"

if %errorlevel% neq 0 (
    echo.
    echo [错误] 打包失败，请检查上方错误信息
    pause
    exit /b 1
)

echo.
echo ========================================
echo   打包完成！
echo.
echo   EXE 文件位置: dist\CapsLock锁定工具.exe
echo.
echo   特性:
echo     - 双击运行时自动弹出 UAC 提权窗口
echo     - 获得管理员权限后，键盘钩子更稳定
echo ========================================
echo.
echo 提示: 如果杀毒软件报毒，请将 dist 目录加入白名单
echo.
pause