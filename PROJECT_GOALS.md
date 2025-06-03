# MeanGeneBot: Project Goals

This document outlines the high-level goals and features for the next generation of MeanGeneBot, designed for Twitch and Discord integration, real-time overlays, robust moderation, extensibility, and modern best practices.

---

## 1. Core Infrastructure

- **Modular codebase** for easy expansion, maintenance, and removal.
- Uniform command structure for Twitch, Discord, or both.
- Pin dependency versions (e.g., TwitchIO, discord.py).
- Load all secrets and tokens from `.env` files using `python-dotenv`—never hardcode sensitive data.
- Document setup steps and requirements.

---

## 2. Platform & Command Support

- **Multi-platform operation:**  
  Connect to Twitch and Discord, supporting platform-specific and cross-platform commands.
  - Cross-platform messaging (e.g., Discord minigames can send messages to Twitch chat and vice versa).
- **Legacy command recreation:**  
  Re-implement popular legacy commands: `!derpism`, `!quote`, `!raffle`, `!sfx`, `!dah`, `!tic`, `!so`/`!os`, etc.
- **Dynamic command discovery (future):**  
  GIF and SFX commands are auto-generated based on files in correct directories—no bot restart required.

---

## 3. Overlay & Visualization

- **Real-Time Overlay:**  
  Provide an `overlay.html` browser source for OBS, communicating with the bot via WebSocket (vanilla JS, no frontend framework).
  Overlay must support animation, API-driven updates, and ticker functionality.
  Ticker displays info (raffle, quotes, winners, stats, etc.) in an extendable way.
- **Grafana Dashboard:**  
  Integrate with Grafana using Prometheus to visualize real-time stats:
    - Viewer count
    - Commands issued (type/user/time)
    - Active games/raffles
    - Moderation actions
    - Other custom metrics as needed

---

## 4. Moderation & Safety

- **Mod-only features** via private Discord mods channel.
- **Automated moderation alerts:**  
  - New Twitch accounts joining (account age < 30 days)
  - Accounts with known bad reputation (if API-accessible)
- **Remote lockdown:**  
  Allow mods to remotely lock down (disable) the bot or selected features from Discord.

---

## 5. Logging & Monitoring

- **Separated logging:**  
  Write debug logs to a separate file (`debug.log`), keeping console output clean (info, warnings, high-level errors only).
  Allow configurable log levels (DEBUG, INFO, WARNING).
- **Real-time monitoring:**  
  Ensure stats and logs are accessible for review via console, file, and Grafana dashboard as appropriate.

---

## 6. Documentation & User Support

- **Documentation generation:**  
  Regenerate user/mod documentation here with Copilot, and provide links—no dedicated script for now.
- **Project documentation:**  
  Clear README for setup, configuration, adding commands, and common workflows.

---

## 7. Extensibility & Future-Proofing

- **Overlay/API extensibility:**  
  Design overlay/event APIs so new data types and events can be added easily.
- **Management UI (future):**  
  Develop an interface for managing bot settings, monitoring activity, and controlling features in real time (API/WebSocket, authentication/access control).

---

## 8. Deployment Strategy

- **Containerization:**  
  Start with Docker for reproducible builds and easier deployment.
- **Kubernetes (future):**  
  Structure project so that migration to Kubernetes is straightforward when/if needed. Prepare Dockerfiles and (later) k8s manifests.
- **Deployment documentation:**  
  Document both local (Docker) and Kubernetes (future) deployment processes.

---

## 9. Development Best Practices

- **Version control:**  
  Use branches for new features/experiments; only merge to main when stable.
- **Testing & staging:**  
  Include a `/tests` folder and basic test harness for unit/integration tests. Provide a means to test features/overlays locally before production deployment.
- **Security:**  
  Review and minimize permissions for all integrations and API keys.

---

## 10. OAuth Token Management

- **Automatic/Scripted Twitch OAuth Refresh:**  
  Provide a script (or simple CLI utility) to refresh Twitch OAuth tokens as needed, ensuring uninterrupted bot operation and easy token management.

---

## 11. Custom/Stretch Goals

- [ ] _____________________________
- [ ] _____________________________

---

**Note:** This list is prioritized for foundational stability, maintainability, and extensibility. Features marked (future) are aspirational and may be scheduled for later milestones.