import requests
import datetime

today = datetime.datetime.now().strftime('%Y-%m-%d')
url = f"https://nba.balldontlie.io/api/v1/games?dates[]={today}"

print(f"Request URL: {url}")

try:
    resp = requests.get(url)
    print(f"HTTP Status Code: {resp.status_code}")
    print("Headers:", resp.headers)
    print("First 200 chars of response text:")
    print(resp.text[:200])  # Print the first 200 characters of the response

    # Try to parse JSON
    data = resp.json()
    print(f"BALLEDONTLIE: NBA Games on {today}")
    for game in data.get('data', []):
        home = game['home_team']['full_name']
        away = game['visitor_team']['full_name']
        status = game['status']
        period = game['period']
        home_score = game['home_team_score']
        away_score = game['visitor_team_score']
        print(f"{away} at {home} | Status: {status} | Period: {period} | Score: {away_score}-{home_score}")
except Exception as e:
    print("\nERROR:")
    print(e)
    print("\nFull response text below:\n")
    print(resp.text)