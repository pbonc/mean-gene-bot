# Trading Card AFK Overlay Setup

## 📁 Card Image Storage
Place your trading card scans in the `/assets/cards/` directory:

### Recommended file structure:
```
assets/cards/
├── psa-slabs/
│   ├── jordan-1986-fleer-psa9.jpg
│   ├── lebron-2003-chrome-psa10.jpg
│   └── ...
├── bgs-slabs/
│   ├── brady-2000-bowman-bgs95.jpg
│   └── ...
├── sgc-slabs/
│   ├── jeter-1993-sp-sgc9.jpg
│   └── ...
└── raw-cards/
    ├── gretzky-1979-opc-raw.jpg
    ├── mahomes-2017-prizm-raw.jpg
    └── ...
```

### Image Requirements:
- **Format**: JPG, PNG, or WebP
- **Resolution**: 800x1100+ pixels (card ratio)
- **File size**: Under 2MB each for good loading performance
- **Naming**: Use descriptive names (player-year-set-condition.jpg)

## 🎮 How to Use

### 1. Access the Overlay
- **URL**: `http://localhost:8080/cards`
- **OBS Browser Source**: Use the above URL as your browser source
- **Resolution**: 1920x1080

### 2. Features
- **Grid Layout**: 5x3 grid showing 15 cards at once
- **Auto-Rotation**: Cards randomly flip and change every 8-15 seconds
- **Card Types**: 
  - 🔵 PSA Slabs (blue border)
  - 🔴 BGS Slabs (red border) 
  - 🟢 SGC Slabs (green border)
  - 🟡 Raw Cards (gold border)
- **Live Ticker**: Shows your current stream info at bottom
- **Floating Particles**: Subtle golden particle effects

### 3. Customizing Your Collection

Edit the `tradingCards` array in `/bot/overlay_static/cards_afk_overlay.html`:

```javascript
const tradingCards = [
  { 
    name: "Your Player Name", 
    year: "2023", 
    set: "Card Set", 
    grade: "PSA 10", 
    type: "psa-slab",  // psa-slab, bgs-slab, sgc-slab, raw-card
    rarity: "Rookie",
    image: "/cards/psa-slabs/your-card.jpg"  // Optional: specific image path
  },
  // Add more cards...
];
```

## 🎨 Visual Features

### Card Animation Effects:
- **Flip Animation**: 3D rotation effect when cards change
- **Glow Effects**: Cards have subtle glow based on type
- **Hover Effects**: Cards slightly lift when hovered (if interactive)
- **Staggered Loading**: Cards appear with slight delays for smooth entrance

### Color Coding:
- **PSA Slabs**: Blue gradient with blue border
- **BGS Slabs**: Light gradient with red border  
- **SGC Slabs**: Gray gradient with green border
- **Raw Cards**: Dark gradient with gold border

### Background:
- **Gradient**: Deep space-like gradient background
- **Particles**: Floating golden particles for premium feel
- **AFK Banner**: Animated gradient banner at top

## 🔧 Technical Details

### Performance:
- **Optimized Animations**: CSS3 hardware acceleration
- **Smart Rotation**: Only rotates 3-7 random cards at a time
- **Particle Management**: Auto-cleanup of particles to prevent memory leaks
- **WebSocket Integration**: Real-time ticker updates from your bot

### Browser Compatibility:
- **Chrome/Edge**: Full support with hardware acceleration
- **Firefox**: Full support
- **OBS Browser**: Optimized for OBS Studio browser sources

### Customization Options:
1. **Rotation Speed**: Adjust `rotationInterval` timing
2. **Grid Size**: Change grid-template-columns/rows in CSS
3. **Card Count**: Modify number of cards shown
4. **Particle Count**: Adjust particle density
5. **Color Themes**: Modify CSS gradient and color variables

## 🚀 Going Live

1. **Add Your Cards**: Place card images in `/assets/cards/`
2. **Update Card Data**: Edit the JavaScript array with your collection
3. **Test Locally**: Visit `http://localhost:8080/cards`
4. **Add to OBS**: Create browser source with the URL
5. **Set Scene**: Use for AFK, breaks, or card reveal segments

Your trading card overlay is ready to showcase your collection! 🎴✨