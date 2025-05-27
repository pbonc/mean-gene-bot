# Mean Gene Bot

Mean Gene Bot is a Python-based project designed for future extensibility and experimentation.  
This repository is under active development and currently serves as a clean slate, with legacy code preserved in the `archive/` directory.

## Project Structure

```
mean-gene-bot/
├── archive/           # Legacy or reference code
├── src/               # Source code for the bot
├── .env               # Environment variables (not tracked by git)
├── .gitignore         # Git ignored files
├── README.md          # Project documentation
└── requirements.txt   # Python dependencies
```

## Getting Started

1. **Clone the repository**
    ```sh
    git clone https://github.com/pbonc/mean-gene-bot.git
    cd mean-gene-bot
    ```

2. **Set up Python Environment**
    - Ensure you have Python 3.8+ installed.
    - (Optional but recommended) Create a virtual environment:
      ```sh
      python -m venv venv
      source venv/bin/activate  # On Windows: venv\Scripts\activate
      ```

3. **Install dependencies**
    ```sh
    pip install -r requirements.txt
    ```

4. **Environment Variables**
    - Copy `.env.example` to `.env` and fill in necessary environment variables (if applicable).

## How to Run

After activating your virtual environment, start the bot with:

```sh
python src/main.py
```

When started, Mean Gene Bot will output:
```
Welcome to the main event!
```
and begin connecting to both Twitch and Discord (once configured).

## Contributing

- Feel free to open issues or pull requests for ideas, bugs, or improvements.
- All legacy code is kept in the `archive/` folder for reference.

## Roadmap

- [ ] Define bot purpose and core features
- [ ] Implement initial bot skeleton in `src/`
- [ ] Add tests and CI setup
- [ ] Expand documentation
- [ ] **Multi-channel Support**
    - [ ] Connect to multiple Twitch channels, starting with:
        - [ ] Your own channel
        - [ ] The "iamdar" channel
    - [ ] Connect to multiple Discord channels, focusing first on:
        - [ ] Moderator (mods) channels
        - [ ] Additional channels as needed
- [ ] Configuration for channel management and authentication
- [ ] Role-based permissions (e.g., mods, admins)
- [ ] Logging, error reporting, and diagnostics

## License

[MIT](LICENSE) (or specify your license here)

---

*Maintained by [pbonc](https://github.com/pbonc).*