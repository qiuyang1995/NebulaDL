@echo off
REM NebulaDL Build Script
REM 使用 PyInstaller 打包为单文件 EXE

echo ========================================
echo   NebulaDL Build Script
echo ========================================
echo.

REM 检查 PyInstaller 是否安装
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller not found. Installing...
    pip install pyinstaller
)

echo [INFO] Starting build...
echo.

REM 清理旧的构建文件
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

REM 运行 PyInstaller
pyinstaller NebulaDL.spec --noconfirm

echo.
if exist "dist\NebulaDL.exe" (
    echo ========================================
    echo   Build Successful!
    echo   Output: dist\NebulaDL.exe
    echo ========================================
) else (
    echo [ERROR] Build failed. Check the output above.
)

pause
