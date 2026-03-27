# Discord Message Fetcher

A lightweight, zero-dependency customized local Python GUI to fetch and export Discord messages historically.

## Features
- **Fetch by Time Range**: Supports precise start/end fetching intervals with an integrated calendar picker.
- **Robust Delay & Stealth**: Implements 5-60s jittered sleeping delays between page fetches alongside browser spoofing to mitigate ratelimits.
- **Persistence**: Remembers your fetched items internally. It autosaves the current scraping run in realtime to `auto_fetch_log.csv` and a local JSON cache so even force-closes won't lose data.
- **CSV Export Tools**: Downloads all scraped messages cleanly using native RFC-compliant Python CSV.
- **User Highlighting**: Features a CustomTkinter sleek native dark view.

## Usage
Simply run:
```bash
./start.sh
```
This automatically initiates Python's Virtual environment processing, auto-installs `requests` and `customtkinter` (tkinter system prerequisites apply), and safely runs the application.
