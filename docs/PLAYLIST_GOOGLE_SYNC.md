# Playlist Google Sheets Integration Setup

This guide explains how to set up Google Sheets sync for your song playlist.

## Prerequisites

1. **Google Cloud Project** with Sheets API enabled
2. **Service Account** with JSON key file
3. **Google Sheet** to receive the playlist data

## Environment Variables

Add these to your `.env` file or system environment:

```
GOOGLE_SERVICE_ACCOUNT_JSON=C:\path\to\your\service-account-key.json
PLAYLIST_SPREADSHEET_ID=your-google-sheet-id-here
```

### Finding Your Spreadsheet ID

The spreadsheet ID is in the URL of your Google Sheet:
```
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID_HERE/edit
```

## Commands Added

### `!syncplaylist` (Moderator Only)
- Syncs the complete 205-song playlist to Google Sheets
- Creates columns: Number, Title, Artist, Duration, Play Count, YouTube URL, Request Command
- Overwrites the sheet for consistency

### `!plstats` (Everyone)
- Shows playlist statistics
- Total songs, duration, play counts, top artists

## Google Sheets Output

The sync creates a sheet with these columns:

| Number | Title | Artist | Duration | Play Count | YouTube URL | Request Command |
|--------|-------|--------|----------|------------|-------------|-----------------|
| 1 | Bohemian Rhapsody | Queen | 5:55 | 0 | https://... | !srx 1 |
| 2 | Smells Like Teen Spirit | Nirvana | 5:01 | 0 | https://... | !srx 2 |

## Usage

1. Set up environment variables
2. Create a Google Sheet and share it with your service account email
3. Use `!syncplaylist` to sync the playlist
4. Share the Google Sheet link with your viewers

## Benefits

- **Viewer Reference**: Viewers can browse all 205 songs
- **Easy Requests**: Clear !srx commands for each song
- **Search Friendly**: Viewers can search by artist, title, or genre
- **Always Updated**: Sync reflects current playlist state

## Example Viewer Experience

Viewers can now:
1. Open the Google Sheet
2. Search for "Metallica" to find all metal songs
3. See "!srx 18" for Enter Sandman
4. Type `!srx 18` in chat to request it

This makes song discovery much easier and encourages playlist usage over costly YouTube requests!