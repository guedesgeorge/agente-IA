@echo off
title LexAI
color 0A

echo.
echo  ========================================
echo   LexAI - Agente Juridico Inteligente
echo  ========================================
echo.

set PROJETO=C:\Users\User\Downloads\lexai-agente-juridico-v4\lexai

if "%ANTHROPIC_API_KEY%"=="" (
  echo  Digite sua chave da Anthropic:
  set /p ANTHROPIC_API_KEY=  Chave: 
  echo.
)

echo  Iniciando backend...
start "Backend" cmd /k "cd /d %PROJETO%\backend && set ANTHROPIC_API_KEY=%ANTHROPIC_API_KEY% && python -m uvicorn main:app --port 8000 --host 0.0.0.0"

echo  Aguardando...
timeout /t 10 /nobreak > nul

echo  Iniciando frontend...
start "Frontend" cmd /k "cd /d %PROJETO%\frontend && python -m http.server 3000"

timeout /t 3 /nobreak > nul

echo  Abrindo navegador...
start http://127.0.0.1:3000

echo.
echo  LexAI rodando em http://127.0.0.1:3000
echo  Para encerrar: feche as duas janelas
echo.
pause
