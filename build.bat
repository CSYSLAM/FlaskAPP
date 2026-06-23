@echo off
chcp 65001 >nul
echo ========================================
echo   FlaskAPP 打包脚本
echo ========================================
echo.

:: 检查PyInstaller
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo 正在安装 PyInstaller...
    pip install pyinstaller
)

:: 清理旧的打包文件
if exist "dist\FlaskAPP" (
    echo 清理旧的打包文件...
    rmdir /s /q "dist\FlaskAPP"
)
if exist "build" (
    rmdir /s /q "build"
)

echo.
echo 开始打包...
echo.

:: 使用spec文件打包
pyinstaller FlaskAPP.spec --noconfirm

if errorlevel 1 (
    echo.
    echo 打包失败！
    pause
    exit /b 1
)

echo.
echo ========================================
echo   打包完成！
echo ========================================
echo.
echo 正在复制data目录到输出目录...

:: 创建data目录并复制文件
if not exist "dist\FlaskAPP\data" mkdir "dist\FlaskAPP\data"
xcopy /e /i /y "data" "dist\FlaskAPP\data"

:: 创建instance目录并复制数据库
if not exist "dist\FlaskAPP\instance" mkdir "dist\FlaskAPP\instance"
if exist "instance\game1.db" copy /y "instance\game1.db" "dist\FlaskAPP\instance\"

echo.
echo ========================================
echo   全部完成！
echo ========================================
echo.
echo 输出目录: dist\FlaskAPP
echo 可执行文件: dist\FlaskAPP\FlaskAPP.exe
echo 数据目录: dist\FlaskAPP\data (可修改json文件)
echo 数据库目录: dist\FlaskAPP\instance (存放数据库)
echo.
echo 使用方法:
echo   1. 进入 dist\FlaskAPP 目录
echo   2. 双击运行 FlaskAPP.exe
echo   3. 打开浏览器访问 http://127.0.0.1:5000
echo   4. 修改 data 目录下的 json 文件可改变游戏配置
echo.
pause