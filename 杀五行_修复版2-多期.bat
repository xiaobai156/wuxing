@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3.10 -m cli.multi %*
pause
