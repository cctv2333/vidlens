@echo off
setlocal
set HERE=%~dp0
set MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
where python >nul 2>nul
if errorlevel 1 (
  echo [error] python not found in PATH. Install Python 3.9+ first.
  exit /b 1
)
if not exist "%HERE%.venv" (
  echo [1/3] creating venv...
  python -m venv "%HERE%.venv" || exit /b 1
) else (
  echo [1/3] venv exists
)
echo [2/3] upgrading pip...
"%HERE%.venv\Scripts\python.exe" -m pip install -q -U pip -i %MIRROR%
echo [3/3] installing deps...
"%HERE%.venv\Scripts\python.exe" -m pip install -q -r "%HERE%requirements.txt" -i %MIRROR% || exit /b 1
echo.
echo done.
echo   test:  vl.cmd probe demo\meeting.mp4
echo   try:   vl.cmd report your.mp4 --lang zh
