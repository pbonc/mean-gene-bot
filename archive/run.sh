#!/bin/bash

echo "Starting Mean Gene Bot..."

# Optional: activate a virtual environment
# source venv/bin/activate

# Run the bot
python3 main.py

# Capture exit code
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "Mean Gene Bot exited with code $EXIT_CODE"
else
  echo "Mean Gene Bot closed normally."
fi
