# VisaMintelli AI - Launcher (Silent)
# Run: powershell -ExecutionPolicy Bypass -File launch.ps1

Get-Process -Name "python","pythonw" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

$env:LLM_API_KEY = "<YOUR_GROQ_API_KEY>"
$env:LLM_BASE_URL = "https://api.groq.com/openai/v1"
$env:LLM_MODEL = "llama-3.3-70b-versatile"

# Use pythonw to run WITHOUT a console window (fully silent)
pythonw main.py
