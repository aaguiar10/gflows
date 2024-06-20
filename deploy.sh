#!/bin/bash

set -e

LOG_PATH="/var/log/deploy.log"

echo "Deployment started at $(date)" >> "$LOG_PATH"

cd /root/gflows_git/gflows

echo "Activating virtual environment..." >> "$LOG_PATH"
source venv/bin/activate

echo "Pulling latest code from Git repository..." >> "$LOG_PATH"
git pull origin main

echo "Installing dependencies..." >> "$LOG_PATH"
pip install -r requirements.txt

echo "Deployment completed at $(date)" >> "$LOG_PATH"
