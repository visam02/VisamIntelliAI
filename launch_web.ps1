# ParakeetAI - Web Server Launcher (Stealth Mode)
# Run: powershell -ExecutionPolicy Bypass -File launch_web.ps1
# Opens in an invisible overlay window (hidden from screen capture)

$env:LLM_API_KEY = "<YOUR_GROQ_API_KEY>"
$env:LLM_BASE_URL = "https://api.groq.com/openai/v1"
$env:LLM_MODEL = "llama-3.3-70b-versatile"

Write-Host "=================================================="
Write-Host "  ParakeetAI - Stealth Web Server"
Write-Host "=================================================="
Write-Host "  Mode: STEALTH (invisible to screen capture)"
Write-Host "  The overlay window will NOT appear in screenshots"
Write-Host "  or screen sharing (Zoom, Teams, etc.)"
Write-Host "=================================================="

python web_server.py --stealth

