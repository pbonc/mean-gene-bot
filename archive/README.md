# Mean Gene Bot

**Mean Gene Bot** is a Twitch chat bot designed for interactive and entertaining live streams.  
This project is deployed using Kubernetes and managed with Jenkins pipelines.

## Project Structure

mean-gene-bot/
├── bot/ # Twitch bot source code (WIP)
├── pipelines/ # Jenkins pipelines
│ ├── update-hardware/
│ └── deploy-bot/
├── targets.json # Target systems for deployment (e.g., meangenebrain, meanpi)


## Systems

- **meangenebrain**: Kubernetes controller (micro PC)
- **meanpi**: Secondary Kubernetes node (Raspberry Pi)
- **Big Box**: Development PC

## Goals

- Modular bot with commands and Twitch API integration
- Deployed via Jenkins on Kubernetes
- Real-time Twitch metrics (via Grafana, optional)

## Status

🔧 Initial setup phase  
☐ TwitchIO bot skeleton  
☐ Dockerized bot  
☐ Kubernetes manifest  
☐ CI/CD integration  