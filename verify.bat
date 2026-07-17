@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=python"
where python >nul 2>&1 || set "PY=py"
where %PY% >nul 2>&1 || (
  echo [verify] Python not found. Please install Python 3.10+
  pause
  exit /b 1
)

echo [verify] 接入自检（读取 module.json capabilities 逐条探测）
echo [verify] 提示：请先启动服务（start_api.bat / start_web.bat），或用 --base 指定地址
echo.
%PY% verify.py %*
echo.
pause
