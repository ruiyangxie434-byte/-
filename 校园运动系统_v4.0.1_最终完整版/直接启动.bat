@echo off
chcp 65001 >nul
title 校园运动健康数据中台 v4.0.1
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo 启动失败。如尚未安装依赖，请先双击“安装依赖并启动.bat”。
)
pause
