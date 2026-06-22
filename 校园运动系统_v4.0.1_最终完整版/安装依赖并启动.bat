@echo off
chcp 65001 >nul
title 校园运动健康数据中台 v4.0.1
cd /d "%~dp0"

echo ==============================================
echo   校园运动健康数据中台 v4.0.1
echo ==============================================
echo.
echo [1/2] 正在安装或检查依赖，请稍候...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo 依赖安装失败，请确认电脑已安装 Python 3.10 或更高版本。
    pause
    exit /b 1
)

echo.
echo [2/2] 正在启动程序...
python main.py
if errorlevel 1 (
    echo.
    echo 程序运行出错，请截图本窗口中的错误信息。
)
pause
