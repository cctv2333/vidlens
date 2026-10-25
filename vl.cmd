@echo off
setlocal
set HERE=%~dp0
if not exist "%HERE%.venv\Scripts\python.exe" (
  echo [error] run install.cmd first
  exit /b 1
)
"%HERE%.venv\Scripts\python.exe" "%HERE%vidlens.py" %*
