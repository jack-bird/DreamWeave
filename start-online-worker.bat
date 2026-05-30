@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "VENV_ACTIVATE=E:\ai_home\AI_Projects\llm_env\Scripts\activate.bat"
set "SERVER_WS=ws://47.101.67.241/ws/worker"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"

title DreamWeave Online Worker

echo [DreamWeave] Starting local AI Worker...
echo [DreamWeave] Project: %PROJECT_DIR%
echo [DreamWeave] Server:  %SERVER_WS%
echo [DreamWeave] Hugging Face offline cache mode enabled.
echo.

if not exist "%VENV_ACTIVATE%" (
  echo [ERROR] Python virtual environment not found:
  echo %VENV_ACTIVATE%
  echo.
  pause
  exit /b 1
)

cd /d "%PROJECT_DIR%"

call "%VENV_ACTIVATE%"
if errorlevel 1 (
  echo [ERROR] Failed to activate Python virtual environment.
  echo.
  pause
  exit /b 1
)

python ".\apps\local-ai-worker\main.py" connect --server "%SERVER_WS%"

echo.
echo [DreamWeave] Worker stopped.
pause
