# Discord Bot Setup Instructions

## Prerequisites
1. Create a Discord application at https://discord.com/developers/applications
2. Create a bot user and copy the bot token
3. Invite the bot to your Discord server with appropriate permissions
4. Get the channel ID where you want raffle messages posted

## Environment Variables
Add these to your `.env` file:

```
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here
```

## Bot Permissions Required
When inviting the bot to your server, ensure it has these permissions:
- Send Messages
- Read Message History
- View Channels

## Getting Channel ID
1. Enable Developer Mode in Discord (User Settings > Advanced > Developer Mode)
2. Right-click on the channel where you want messages posted
3. Select "Copy ID"

## Testing
1. Install dependencies: `pip install -r requirements.txt`
2. Set up environment variables in `.env`
3. Run the bot: `python bot/main.py`
4. Use `!raffle open` and `!raffle draw` commands in Twitch
5. Verify messages appear in your Discord channel

## Features Added
- Raffle open/close announcements in Discord
- Winner announcements with celebration emojis
- Bad beat notifications
- No winner/rollover notifications
- Jackpot increase notifications

## Error Handling
- Bot will work without Discord if token is not provided
- Error messages are logged if Discord connection fails
- Bot continues to function normally on Twitch even if Discord fails