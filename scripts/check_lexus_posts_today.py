#!/usr/bin/env python3
"""Проверка постов Lexus за сегодня"""
import json
from pathlib import Path
from datetime import datetime

history_file = Path('logs/group_post_history.json')
if history_file.exists() and history_file.stat().st_size > 0:
    with open(history_file, 'r') as f:
        data = json.load(f)
    
    today = datetime.now().date()
    today_posts = 0
    
    for group, accounts in data.items():
        if isinstance(accounts, dict):
            for account, timestamps in accounts.items():
                if isinstance(timestamps, list):
                    for ts in timestamps:
                        try:
                            post_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            if post_time.date() == today:
                                today_posts += 1
                        except:
                            pass
    
    print(f"Lexus posts today: {today_posts}")
else:
    print("0")
