@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not "%~1"=="" goto run
echo 请输入失败 TXT 完整路径
set /p "FAILURE_TXT=失败TXT: "
if "%FAILURE_TXT%"=="" goto done
:run
py -3.10 -m cli.retry_failed %*
:done
pause
