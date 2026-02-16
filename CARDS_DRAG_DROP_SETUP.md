# Trading Cards Drag-and-Drop System

## Overview
The trading cards AFK overlay now supports automatic card detection through filename parsing. Simply drop your card images into the `/assets/cards/` directory and the system will automatically populate the overlay based on the filenames.

## How It Works

### Filename Format
Use hyphens to separate card information in this order:
```
player-year-set-grade.extension
```

### Examples
- `jordan-1986-fleer-psa9.jpg` → Michael Jordan, 1986 Fleer, PSA 9
- `gretzky-1979-opc.jpg` → Wayne Gretzky, 1979 OPC, Raw (no grade = raw card)
- `brady-2000-bowman_chrome-bgs95.jpg` → Tom Brady, 2000 Bowman Chrome, BGS 9.5

### Directory Structure (Optional)
You can organize cards in subdirectories for better organization:
- `/assets/cards/psa/` - PSA graded cards
- `/assets/cards/bgs/` - BGS/Beckett graded cards  
- `/assets/cards/sgc/` - SGC graded cards
- `/assets/cards/raw/` - Raw/ungraded cards

The system automatically detects card type from directory names and filenames.

## Supported Formats

### Grading Companies
- **PSA**: Use `psa9`, `psa10`, etc.
- **BGS/Beckett**: Use `bgs9`, `bgs95` (for 9.5), etc.
- **SGC**: Use `sgc9`, `sgc10`, etc.
- **Raw**: No grade suffix or place in `/raw/` directory

### Image Extensions
- `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`

### Special Rarity Keywords
The system auto-detects these keywords in filenames:
- `rookie`, `rc`, `rook` → Rookie card
- `auto`, `autograph`, `sig` → Autograph card
- `patch`, `jersey`, `relic` → Memorabilia card
- `refractor`, `prizm`, `chrome` → Parallel card

### Filename Tips
- Use underscores for multi-word sets: `bowman_chrome`, `upper_deck`
- Use hyphens to separate main card info: `player-year-set-grade`
- Avoid spaces in filenames
- Be consistent with naming for best results

## Usage

1. **Add Cards**: Drop image files into `/assets/cards/` or subdirectories
2. **Naming**: Follow the `player-year-set-grade.jpg` format
3. **Refresh**: The overlay automatically loads cards when opened
4. **Organization**: Use subdirectories to organize by grading company

## API Endpoint

The system exposes card data at: `http://localhost:8080/api/cards`

This returns JSON with parsed card information:
```json
{
  "cards": [
    {
      "name": "Michael Jordan",
      "year": "1986", 
      "set": "Fleer",
      "grade": "PSA 9",
      "type": "psa-slab",
      "rarity": "Rookie",
      "image": "/cards/psa/jordan-1986-fleer-psa9.jpg"
    }
  ]
}
```

## Overlay URL

Access the trading cards overlay at: `http://localhost:8080/cards`

The overlay will automatically load and display your cards with:
- 5x3 rotating grid layout
- Card type styling (PSA/BGS/SGC/Raw)
- Automatic card rotation animations
- Live ticker integration
- Professional card showcase presentation

## Troubleshooting

### No Cards Showing
- Check that image files are in `/assets/cards/` directory
- Verify filenames follow the hyphen-separated format
- Check browser console for API errors
- Ensure overlay server is running on port 8080

### Card Info Not Parsing Correctly  
- Use hyphens (not spaces or underscores) to separate main info
- Follow the player-year-set-grade order
- Check for typos in grade format (psa9, bgs95, etc.)

### Images Not Loading
- Verify image files are valid and not corrupted
- Check file extensions are supported (.jpg, .png, etc.)
- Ensure proper permissions on files/directories
- Check browser network tab for 404 errors