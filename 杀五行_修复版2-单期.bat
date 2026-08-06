@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not "%~1"=="" goto run_args
set "PERIOD="
echo Input target period, for example: 211
set /p "PERIOD=Period: "
if "%PERIOD%"=="" goto missing_period
py -3 -m cli.single "%PERIOD%"
goto done

:run_args
py -3 -m cli.single %*
goto done

:missing_period
echo Period is required. Cancelled.
:done
pause
