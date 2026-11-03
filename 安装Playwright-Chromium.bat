@echo off
setlocal
cd /d "%~dp0"
title PaddleOCR CPU and Playwright Chromium Installer

echo [1/3] Installing PaddlePaddle CPU...
py -3.10 -m pip install --index-url https://www.paddlepaddle.org.cn/packages/stable/cpu/ paddlepaddle==3.2.0
if errorlevel 1 goto :install_failed

echo.
echo [2/3] Installing Python dependencies...
py -3.10 -m pip install -r requirements-playwright.txt
if errorlevel 1 goto :install_failed

echo.
echo [3/3] Installing Playwright Chromium...
py -3.10 -m playwright install chromium
if errorlevel 1 goto :install_failed

echo.
echo Verifying Python imports and PaddlePaddle CPU build...
py -3.10 -c "import paddle, paddleocr, playwright; assert hasattr(paddle, 'is_compiled_with_cuda') and not paddle.is_compiled_with_cuda(); print('PaddlePaddle CPU build verified')"
if errorlevel 1 goto :install_failed

echo.
echo Playwright Chromium and PaddleOCR CPU installation completed.
echo.
pause
endlocal
exit /b 0

:install_failed
set "INSTALL_ERROR=%errorlevel%"
echo.
echo Installation failed. Error code: %INSTALL_ERROR%
echo Keep this window open and check the Python or network error above.
echo.
pause
endlocal & exit /b %INSTALL_ERROR%
