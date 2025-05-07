Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

cd .\bot
.\venv\Scripts\Activate.ps1

while ($true) {
    python main.py
    Write-Host "`nBot crashed. Restarting in 5 seconds..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}
