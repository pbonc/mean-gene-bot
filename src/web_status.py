from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

status_data = {
    "twitch": {"status": "disconnected", "channels": []},
    "discord": {"status": "disconnected", "channels": []}
}

@app.get("/", response_class=HTMLResponse)
def root():
    return f"""
    <html>
    <head><title>Mean Gene Bot Status</title></head>
    <body>
        <h1>Mean Gene Bot Status</h1>
        <h2>Twitch</h2>
        <p>Status: {status_data['twitch']['status']}</p>
        <p>Channels: {', '.join(status_data['twitch']['channels'])}</p>
        <h2>Discord</h2>
        <p>Status: {status_data['discord']['status']}</p>
        <p>Channels: {', '.join(status_data['discord']['channels'])}</p>
    </body>
    </html>
    """

# For integration: update status_data in your bots as you connect/disconnect/etc.