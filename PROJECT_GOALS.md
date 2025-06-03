# MeanGeneBot: Project Goals

This document outlines the high-level goals and features for the next generation of MeanGeneBot, designed for Twitch and Discord integration, real-time overlays, robust moderation, extensibility, and modern best practices.

---

## 1. Core Infrastructure

- **1.1. Modular Codebase**
  - Organize features and commands for easy expansion, maintenance, and removal.
  - Use a uniform command structure so commands can be added for Twitch, Discord, or both with shared logic.
- **1.2. Dependency & Configuration Management**
  - Pin dependency versions (e.g., TwitchIO, discord.py).
  - Load all secrets and tokens from config or `.env` files—never hardcode sensitive data.
  - Document setup steps and requirements.

---

## 2. Platform & Command Support

- **2.1. Multi-Platform Operation**
  - Connect to Twitch and Discord, responding to test commands on each.
  - Allow for commands that are platform-specific or cross-platform.
  - Support cross-platform messaging (e.g., Discord minigames can send messages to Twitch chat and vice versa).
- **2.2. Legacy Command Recreation**
  - Re-implement popular legacy commands, including (but not limited to):  
    `!derpism`, `!quote`, `!raffle`, `!sfx`, `!dah`, `!tic`, `!so`/`!os`.
- **2.3. Dynamic Command Discovery (Future)**
  - GIF and SFX commands are auto-generated based on files present in the correct directories—no bot restart required.

---

## 3. Overlay & Visualization

- **3.1. Real-Time Overlay**
  - Provide an `overlay.html` browser source for OBS, communicating with the bot via WebSocket.
  - Overlay must support animation, API-driven updates, and ticker functionality.
  - Ticker logic displays various info (raffle, quotes, winners, stats, etc.) in an extendable, logical way.
- **3.2. Grafana Dashboard**
  - Integrate with Grafana (using Prometheus, InfluxDB, or similar) to visualize real-time stats:
    - Viewer count
    - Commands issued (type/user/time)
    - Active games/raffles
    - Moderation actions
    - Other custom metrics as needed

---

## 4. Moderation & Safety

- **4.1. Mod-Only Features**
  - Allow moderators to operate certain commands/features from a private Discord mods channel.
- **4.2. Automated Moderation Alerts**
  - Send alerts to Discord mods channel for:
    - New Twitch accounts joining (account age < 30 days)
    - Accounts with known bad reputation (if API-accessible)
- **4.3. Remote Lockdown**
  - Allow mods to remotely lock down (disable) the bot or selected features from Discord.

---

## 5. Logging & Monitoring

- **5.1. Separated Logging**
  - Write debug logs to a separate file (`debug.log`), keeping console output clean (info, warnings, high-level errors only).
  - Allow configurable log levels (e.g., DEBUG, INFO, WARNING).
- **5.2. Real-Time Monitoring**
  - Ensure stats and logs are accessible for review via console, file, and Grafana dashboard as appropriate.

---

## 6. Documentation & User Support

- **6.1. Auto-Generated Documentation**
  - Automatically generate and update:
    - User-level documentation (general features/commands)
    - Mod-level documentation (advanced/moderation features)
    - Documentation should cover complex features like the raffle minigame, and may be published (e.g., to Google Docs).
- **6.2. Project Documentation**
  - Provide a clear README for setup, configuration, adding commands, and common workflows.

---

## 7. Extensibility & Future-Proofing

- **7.1. Overlay/API Extensibility**
  - Design overlay/event APIs so new data types and events can be added easily.
- **7.2. Management UI (Future)**
  - Develop an interface for managing bot settings, monitoring activity, and controlling features in real time.
  - UI communicates with the bot backend (API/WebSocket) and includes authentication/access control.

---

## 8. Deployment Strategy

- **8.1. Containerization**
  - Discuss and decide whether to containerize the bot using Docker for reproducible builds and easier deployment.
- **8.2. Kubernetes Integration**
  - Consider deploying the bot to your Kubernetes cluster for high availability, auto-scaling, and advanced orchestration.
- **8.3. Dual Approach**
  - Optionally support both Docker for local/testing and Kubernetes for production.
- **8.4. Deployment Documentation**
  - Prepare and maintain Dockerfiles and/or Kubernetes manifests/charts.
  - Document the deployment process for both local and cluster environments.

---

## 9. Development Best Practices

- **9.1. Version Control**
  - Use branches for new features/experiments.
  - Only merge to main when stable.
- **9.2. Testing & Staging**
  - Provide a means to test features/overlays locally before production deployment.
- **9.3. Security**
  - Review and minimize permissions for all integrations and API keys.

---

## 10. Custom/Stretch Goals

- [ ] _____________________________
- [ ] _____________________________

---

**Note:** This list is prioritized for foundational stability, maintainability, and extensibility. Features marked (Future) are aspirational and may be scheduled for later milestones.