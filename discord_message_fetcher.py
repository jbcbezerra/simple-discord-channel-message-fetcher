import customtkinter as ctk
import requests
import threading
import time
import random
import json
import calendar
import os
import re
import subprocess
import csv
from datetime import datetime, timezone, date
from tkinter import filedialog, messagebox

# Path to the persistent message cache, stored alongside the script
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "message_cache.json")

# Regex to detect URLs in message content
URL_PATTERN = re.compile(r'https?://[^\s]+')

# --- Discord Snowflake Helper ---
# Discord uses "Snowflakes" (time-based IDs) to paginate messages.
# We convert your start/end dates into snowflakes to tell the API exactly where to look.
DISCORD_EPOCH = 1420070400000

def date_to_snowflake(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        timestamp_ms = int(dt.timestamp() * 1000)
        return (timestamp_ms - DISCORD_EPOCH) << 22
    except ValueError:
        return None

def format_timestamp(ts_str):
    # Converts Discord's ISO timestamp to a readable format
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d %H:%M")

# --- Date Picker Widget ---
class CTkDatePicker(ctk.CTkToplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.title("Select Date")
        self.geometry("370x330")
        self.attributes("-topmost", True)
        # Defer grab_set until window is fully mapped (CTkToplevel async init on Linux)
        self.after(150, self._safe_grab)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.current_date = date.today()

        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.grid(row=0, column=0, pady=10)

        self.prev_btn = ctk.CTkButton(self.top_frame, text="<", width=30, command=self.prev_month)
        self.prev_btn.pack(side="left", padx=5)

        self.month_year_lbl = ctk.CTkLabel(self.top_frame, text="", width=120)
        self.month_year_lbl.pack(side="left", padx=5)

        self.next_btn = ctk.CTkButton(self.top_frame, text=">", width=30, command=self.next_month)
        self.next_btn.pack(side="left", padx=5)

        self.cal_frame = ctk.CTkFrame(self)
        self.cal_frame.grid(row=1, column=0, pady=5, padx=10, sticky="nsew")

        # Column 0 = week number, columns 1-7 = days
        self.cal_frame.grid_columnconfigure(0, weight=0, minsize=28)
        for i in range(1, 8):
            self.cal_frame.grid_columnconfigure(i, weight=1)

        # Header row
        ctk.CTkLabel(self.cal_frame, text="Wk", text_color="gray50",
                     font=ctk.CTkFont(size=10)).grid(row=0, column=0, padx=(2, 4))
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, day in enumerate(days):
            ctk.CTkLabel(self.cal_frame, text=day).grid(row=0, column=i + 1)

        # Week-number labels and day buttons
        self.week_labels = []
        self.day_buttons = []
        for r in range(1, 7):
            wk_lbl = ctk.CTkLabel(self.cal_frame, text="", text_color="gray50",
                                   font=ctk.CTkFont(size=10), width=24)
            wk_lbl.grid(row=r, column=0, padx=(2, 4))
            self.week_labels.append(wk_lbl)

            row_btns = []
            for c in range(7):
                btn = ctk.CTkButton(self.cal_frame, text="", width=30, height=30,
                                    command=lambda row=r, col=c: self.select_day(row, col))
                btn.grid(row=r, column=c + 1, padx=2, pady=2)
                row_btns.append(btn)
            self.day_buttons.append(row_btns)

        self.update_calendar()

    def _safe_grab(self):
        try:
            self.grab_set()
        except Exception:
            pass  # Non-fatal: modal grab failed but window still works

    def prev_month(self):
        m = self.current_date.month - 1
        y = self.current_date.year
        if m == 0:
            m = 12
            y -= 1
        self.current_date = self.current_date.replace(year=y, month=m, day=1)
        self.update_calendar()

    def next_month(self):
        m = self.current_date.month + 1
        y = self.current_date.year
        if m == 13:
            m = 1
            y += 1
        self.current_date = self.current_date.replace(year=y, month=m, day=1)
        self.update_calendar()

    def _build_grid(self, year, month):
        """Return a 6×7 list of date objects anchored to Mon–Sun weeks."""
        from datetime import timedelta
        first = date(year, month, 1)
        # Rewind to the Monday of the week containing the 1st
        start = first - timedelta(days=first.weekday())
        grid = []
        cur = start
        for _ in range(6):
            week = [cur + timedelta(days=i) for i in range(7)]
            grid.append(week)
            cur += timedelta(days=7)
        return grid

    def update_calendar(self):
        self.month_year_lbl.configure(text=self.current_date.strftime("%B %Y"))

        today = date.today()
        grid = self._build_grid(self.current_date.year, self.current_date.month)
        self._date_grid = grid  # store for select_day

        for r, week in enumerate(grid):
            # ISO week number from the first day of the row
            iso_wk = week[0].isocalendar()[1]
            self.week_labels[r].configure(text=str(iso_wk))

            for c, d in enumerate(week):
                btn = self.day_buttons[r][c]
                is_current = (d.month == self.current_date.month)
                is_today   = (d == today)

                btn.configure(
                    text=str(d.day),
                    state="normal",
                    command=lambda row=r, col=c: self.select_day(row, col),
                )

                if is_today:
                    # Accent pill for today
                    btn.configure(
                        fg_color="#1565c0",
                        hover_color="#1e88e5",
                        text_color="white",
                        border_width=0,
                        corner_radius=15,
                    )
                elif is_current:
                    # Regular day in the viewed month
                    btn.configure(
                        fg_color="transparent",
                        hover_color="#2a2d2e",
                        text_color="#e0e0e0",
                        border_width=0,
                        corner_radius=6,
                    )
                else:
                    # Overflow day from adjacent month — dimmed
                    btn.configure(
                        fg_color="transparent",
                        hover_color="#222426",
                        text_color="#4a4f54",
                        border_width=0,
                        corner_radius=6,
                    )

    def select_day(self, r, c):
        selected = self._date_grid[r][c]
        self.callback(selected.strftime("%Y-%m-%d"))
        self.grab_release()
        self.destroy()



class DiscordFetcherApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Discord Message Fetcher")
        self.geometry("800x600")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.is_fetching = False
        self.fetched_messages = []

        self.setup_ui()
        self._configure_tags()
        self._load_cache()

    def setup_ui(self):
        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # 1. Inputs: Token & Channel
        self.token_entry = ctk.CTkEntry(self, placeholder_text="User Token", show="*")
        self.token_entry.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        self.channel_entry = ctk.CTkEntry(self, placeholder_text="Channel ID")
        self.channel_entry.grid(row=0, column=1, padx=10, pady=(10, 5), sticky="ew")

        # 2. Inputs: Dates
        self.start_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.start_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.start_frame.grid_columnconfigure(0, weight=1)
        self.start_date_entry = ctk.CTkEntry(self.start_frame, placeholder_text="Start Date (YYYY-MM-DD)")
        self.start_date_entry.grid(row=0, column=0, sticky="ew", padx=(0,5))
        self.start_cal_btn = ctk.CTkButton(self.start_frame, text="📅", width=30, command=lambda: self.open_calendar(self.start_date_entry))
        self.start_cal_btn.grid(row=0, column=1)

        self.end_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.end_frame.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        self.end_frame.grid_columnconfigure(0, weight=1)
        self.end_date_entry = ctk.CTkEntry(self.end_frame, placeholder_text="End Date (YYYY-MM-DD)")
        self.end_date_entry.grid(row=0, column=0, sticky="ew", padx=(0,5))
        self.end_cal_btn = ctk.CTkButton(self.end_frame, text="📅", width=30, command=lambda: self.open_calendar(self.end_date_entry))
        self.end_cal_btn.grid(row=0, column=1)

        # 3. Controls
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=2, column=0, columnspan=2, pady=10)

        self.fetch_btn = ctk.CTkButton(self.btn_frame, text="Start Fetching", command=self.start_fetching)
        self.fetch_btn.pack(side="left", padx=10)

        self.export_btn = ctk.CTkButton(self.btn_frame, text="Export Messages", command=self.export_messages, state="disabled", fg_color="green", hover_color="darkgreen")
        self.export_btn.pack(side="left", padx=10)

        self.clear_btn = ctk.CTkButton(self.btn_frame, text="Clear", command=self.clear_messages, fg_color="#8B0000", hover_color="#5a0000")
        self.clear_btn.pack(side="left", padx=10)

        self.status_label = ctk.CTkLabel(self.btn_frame, text="Ready", text_color="gray")
        self.status_label.pack(side="left", padx=10)

        # 4. Text View
        self.text_view = ctk.CTkTextbox(self, state="disabled", font=("Consolas", 13))
        self.text_view.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="nsew")

    def open_calendar(self, entry_widget):
        def set_date(d):
            entry_widget.delete(0, "end")
            entry_widget.insert(0, d)
        CTkDatePicker(self, set_date)

    def _configure_tags(self):
        """Configure syntax-highlight tags on the underlying tk.Text widget."""
        tw = self.text_view._textbox
        tw.tag_configure("timestamp", foreground="#4dd0e1")          # cyan
        tw.tag_configure("username",  foreground="#ffd54f")          # amber/gold
        tw.tag_configure("url",       foreground="#64b5f6",          # light blue
                         underline=True)

    def _insert_highlighted(self, text):
        """Insert one message line with inline colour tags applied."""
        tw = self.text_view._textbox
        # Expected format: [YYYY-MM-DD HH:MM] username: content
        ts_match = re.match(r'^(\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\])(\s)(\S+)(:\s?)(.*)', text, re.DOTALL)
        if ts_match:
            ts_part, sp, user_part, colon, content = ts_match.groups()
            tw.insert("end", ts_part, "timestamp")
            tw.insert("end", sp)
            tw.insert("end", user_part, "username")
            tw.insert("end", colon)
            # Highlight URLs inside the content
            last = 0
            for m in URL_PATTERN.finditer(content):
                if m.start() > last:
                    tw.insert("end", content[last:m.start()])
                tw.insert("end", m.group(), "url")
                last = m.end()
            if last < len(content):
                tw.insert("end", content[last:])
        else:
            # Fallback: just highlight any URLs in raw line
            last = 0
            for m in URL_PATTERN.finditer(text):
                if m.start() > last:
                    tw.insert("end", text[last:m.start()])
                tw.insert("end", m.group(), "url")
                last = m.end()
            if last < len(text):
                tw.insert("end", text[last:])
        tw.insert("end", "\n")

    def update_status(self, text, color="white"):
        # UI updates must be scheduled securely from the background thread
        self.after(0, lambda: self.status_label.configure(text=text, text_color=color))

    def append_message_to_view(self, display_text):
        self.after(0, self._append_text, display_text)

    def _append_text(self, text):
        self.text_view.configure(state="normal")
        self._insert_highlighted(text)
        self.text_view.see("end")
        self.text_view.configure(state="disabled")

    # --- Persistence ---

    def _save_cache(self):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.fetched_messages, f, ensure_ascii=False)
        except Exception:
            pass  # Non-fatal: cache save failure should not crash the app

    def _load_cache(self):
        if not os.path.exists(CACHE_FILE):
            return
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list) or not data:
                return
            self.fetched_messages = data
            self.text_view.configure(state="normal")
            for msg in self.fetched_messages:
                author    = msg.get("author", {}).get("username", "Unknown")
                content   = msg.get("content", "")
                timestamp = format_timestamp(msg.get("timestamp", ""))
                if msg.get("attachments"):
                    content += " [Attachments included]"
                self._insert_highlighted(f"[{timestamp}] {author}: {content}")
            self.text_view.see("end")
            self.text_view.configure(state="disabled")
            self.export_btn.configure(state="normal")
            self.update_status(f"Loaded {len(self.fetched_messages)} cached messages.", "gray")
        except Exception:
            pass  # Corrupt cache — silently ignore

    def clear_messages(self):
        if not self.fetched_messages and not os.path.exists(CACHE_FILE):
            return
        self.fetched_messages.clear()
        # Remove cache file
        try:
            if os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
        except Exception:
            pass
        # Clear the text view
        self.text_view.configure(state="normal")
        self.text_view.delete("1.0", "end")
        self.text_view.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.update_status("Cleared.", "gray")

    def start_fetching(self):
        if self.is_fetching:
            return

        token = self.token_entry.get().strip()
        channel = self.channel_entry.get().strip()
        start = self.start_date_entry.get().strip()
        end = self.end_date_entry.get().strip()

        if not all([token, channel, start, end]):
            messagebox.showerror("Error", "Please fill in all fields.")
            return

        start_sf = date_to_snowflake(start)
        end_sf = date_to_snowflake(end)

        if not start_sf or not end_sf:
            messagebox.showerror("Error", "Invalid date format. Use YYYY-MM-DD")
            return

        # Prepare UI for fetching
        self.is_fetching = True
        self.fetch_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.text_view.configure(state="normal")
        self.text_view.delete("1.0", "end")
        self.text_view.configure(state="disabled")
        self.fetched_messages.clear()

        # Start background thread to prevent UI freezing
        threading.Thread(target=self.fetch_worker, args=(token, channel, start_sf, end_sf), daemon=True).start()

    def fetch_worker(self, token, channel_id, start_sf, end_sf):
        headers = {
            "Authorization": token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        base_url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
        current_after = start_sf

        self.update_status("Starting fetch...", "yellow")

        try:
            while self.is_fetching:
                # 1. Randomize limit (10 or 20)
                limit = random.choice([10, 20])
                
                params = {
                    "limit": limit,
                    "after": current_after
                }

                # 2. Make the API request
                res = requests.get(base_url, headers=headers, params=params)

                if res.status_code == 401:
                    self.update_status("Error: Invalid Token", "red")
                    break
                elif res.status_code == 403:
                    self.update_status("Error: Missing Access to Channel", "red")
                    break
                elif res.status_code == 429:
                    # Respect Discord's strict rate limits if we hit them accidentally
                    retry_after = res.json().get("retry_after", 5)
                    self.update_status(f"Rate limited. Waiting {retry_after}s...", "orange")
                    time.sleep(retry_after)
                    continue
                elif res.status_code != 200:
                    self.update_status(f"Error {res.status_code}: {res.text}", "red")
                    break

                messages = res.json()
                if not messages:
                    self.update_status("Finished! No more messages.", "green")
                    break

                # Sort chronologically (Discord's 'after' returns lists in various orders sometimes)
                messages = sorted(messages, key=lambda x: int(x['id']))
                max_id = int(messages[-1]['id'])

                # 3. Filter and Display Messages
                for msg in messages:
                    msg_id = int(msg['id'])
                    
                    if start_sf <= msg_id <= end_sf:
                        self.fetched_messages.append(msg)

                        author    = msg.get("author", {}).get("username", "Unknown")
                        content   = msg.get("content", "")
                        timestamp = format_timestamp(msg.get("timestamp", ""))

                        # Add attachments indicator if present
                        if msg.get("attachments"):
                            content += " [Attachments included]"

                        display_text = f"[{timestamp}] {author}: {content}"
                        self.append_message_to_view(display_text)

                        # Auto-append to CSV while fetching
                        try:
                            csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_fetch_log.csv")
                            needs_header = not os.path.exists(csv_path)
                            with open(csv_path, "a", encoding="utf-8", newline='') as cf:
                                cw = csv.writer(cf)
                                if needs_header:
                                    cw.writerow(["datetime", "user", "message"])
                                cw.writerow([timestamp, author, content])
                        except Exception:
                            pass

                # Check if we have passed the end date
                if max_id > end_sf:
                    self.update_status("Reached end date. Finished!", "green")
                    break

                current_after = str(max_id)

                # 4. Apply the large, randomized human-like delay
                delay = random.randint(5, 60)
                self.update_status(f"Sleeping for {delay} seconds...", "lightblue")
                time.sleep(delay)

        except Exception as e:
            self.update_status(f"Exception: {str(e)}", "red")

        finally:
            self.is_fetching = False
            self.after(0, lambda: self.fetch_btn.configure(state="normal"))
            if self.fetched_messages:
                self.after(0, lambda: self.export_btn.configure(state="normal"))
                self._save_cache()

            if self.status_label.cget("text_color") not in ["red", "green"]:
                self.update_status("Stopped.", "white")

            # Trigger OS sound notification (specifically for Linux Mint/Ubuntu)
            try:
                subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"], 
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def export_messages(self):
        if not self.fetched_messages:
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv"), ("JSON file", "*.json"), ("Text file", "*.txt")],
            title="Export Messages"
        )

        if not file_path:
            return

        try:
            if file_path.endswith(".json"):
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(self.fetched_messages, f, indent=4, ensure_ascii=False)
            elif file_path.endswith(".txt"):
                with open(file_path, "w", encoding="utf-8") as f:
                    for msg in self.fetched_messages:
                        author = msg.get("author", {}).get("username", "Unknown")
                        content = msg.get("content", "")
                        timestamp = format_timestamp(msg.get("timestamp", ""))
                        f.write(f"[{timestamp}] {author}: {content}\n")
            else:
                # Default to CSV export
                with open(file_path, "w", encoding="utf-8", newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["datetime", "user", "message"])
                    for msg in self.fetched_messages:
                        author = msg.get("author", {}).get("username", "Unknown")
                        content = msg.get("content", "")
                        timestamp = format_timestamp(msg.get("timestamp", ""))
                        if msg.get("attachments"):
                            content += " [Attachments included]"
                        writer.writerow([timestamp, author, content])
            
            messagebox.showinfo("Success", f"Exported {len(self.fetched_messages)} messages successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {str(e)}")

if __name__ == "__main__":
    app = DiscordFetcherApp()
    app.mainloop()