#!/bin/bash

# Simple setup and run script for the Discord Message Fetcher

# Use the absolute path if needed, but assuming running from project dir
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "Checking for Python 3..."
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3 and try again."
    exit 1
fi

# The app requires tkinter which is often a separate system package on linux
echo "Checking for tkinter (python3-tk)..."
if ! python3 -c "import tkinter" &> /dev/null; then
    echo "Warning: tkinter is missing. CustomTkinter requires tkinter."
    echo "On Ubuntu/Debian, you can install it with: sudo apt install python3-tk"
    echo "You may need to install it for the app to run correctly."
    echo ""
fi

# Setup python virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "Checking and installing dependencies..."
pip install -r requirements.txt --upgrade

# Run the app
echo "Starting the app..."
python3 discord_message_fetcher.py
