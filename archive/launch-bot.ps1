while ($true) {
    Write-Host "=== Launching Mean Gene Bot ==="
    try {
        python .\bot\main.py
    }
    catch {
        Write-Host "=== BOT CRASHED ==="
        Write-Host "Error: $($_.Exception.Message)"
        Write-Host "Stack Trace:"
        $_.Exception | Format-List * -Force
    }
    Write-Host ""
    Write-Host "Restarting in 5 seconds..."
    Start-Sleep -Seconds 5
}
