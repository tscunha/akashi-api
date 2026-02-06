@echo off
REM AKASHI MAM - Debug Dashboard Launcher
REM Abre 3 terminais: API, DB Monitor, Folder Watcher

echo =============================================
echo    AKASHI MAM - Debug Dashboard
echo =============================================
echo.

set PROJECT_DIR=%~dp0..
set VENV_PYTHON=%PROJECT_DIR%\venv\Scripts\python.exe

REM Verificar se venv existe
if not exist "%VENV_PYTHON%" (
    echo ERRO: venv nao encontrado em %PROJECT_DIR%\venv
    echo Execute: python -m venv venv ^&^& venv\Scripts\pip install -e .
    pause
    exit /b 1
)

REM Criar pastas se nao existirem
if not exist "D:\AKASHI_INGEST" mkdir "D:\AKASHI_INGEST"
if not exist "D:\AKASHI_PROCESSED" mkdir "D:\AKASHI_PROCESSED"

echo Iniciando servicos...
echo.

REM Terminal 1: API FastAPI
echo [1/3] Iniciando API...
start "AKASHI API" cmd /k "cd /d %PROJECT_DIR% && %VENV_PYTHON% -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

REM Esperar API subir
timeout /t 3 /nobreak > nul

REM Terminal 2: DB Monitor
echo [2/3] Iniciando DB Monitor...
start "AKASHI DB Monitor" cmd /k "cd /d %PROJECT_DIR% && %VENV_PYTHON% scripts\db_monitor.py"

REM Terminal 3: Folder Watcher
echo [3/3] Iniciando Folder Watcher...
start "AKASHI Folder Watcher" cmd /k "cd /d %PROJECT_DIR% && %VENV_PYTHON% scripts\folder_watcher.py"

echo.
echo =============================================
echo    Todos os servicos iniciados!
echo =============================================
echo.
echo URLS:
echo   API:    http://localhost:8000
echo   Docs:   http://localhost:8000/docs
echo   MinIO:  http://localhost:9001
echo.
echo PASTAS:
echo   Ingest:     D:\AKASHI_INGEST
echo   Processados: D:\AKASHI_PROCESSED
echo.
echo Para testar, copie um arquivo de video para D:\AKASHI_INGEST
echo.
pause
