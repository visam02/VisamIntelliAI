@echo off
REM ============================================
REM  VisaMintelli AI - Launcher
REM  Edit your API key below, then double-click
REM ============================================

REM --- EDIT THIS LINE WITH YOUR GROQ KEY ---
set LLM_API_KEY=<YOUR_GROQ_API_KEY>
set LLM_BASE_URL=https://api.groq.com/openai/v1
set LLM_MODEL=llama-3.3-70b-versatile

REM Point Python to local dependencies
set PYTHONPATH=%~dp0lib;%PYTHONPATH%

echo ==================================================
echo   VisaMintelli AI - Starting...
echo ==================================================

python main.py

pause
