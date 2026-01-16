#!/usr/bin/env python3
"""Быстрая пометка проблемных Lexus групп"""
import sys
from pathlib import Path
import subprocess
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Group

# Группы из ваших логов с ошибками
problem_groups = [
    '@avto_ua_bu',
    '@avto_barakholkav', 
    '@go1000dos',
    '@avto_group_dnepr',
    '@olxde',
    '@avtobazar_odessa_oblast',
    '@baraholka_kiev_ukraina',
    '@dream_cars_kyiv',
    '@avtobazar_avtorynok_ukraina',
    '@Auto_Ukrainec',
    '@CAR_SELLLLL',
    '@avtorynokLviv',
    '@abandonedkiev',
    '@exclusive_cars_odessa_music'
]

init_db()
db = SessionLocal()
try:
    marked = 0
    for username in problem_groups:
        group = db.query(Group).filter(Group.username == username).first()
        if group and group.status != 'banned':
            group.status = 'banned'
            group.can_post = False
            db.commit()
            marked += 1
            print(f"🚫 {username}")
    print(f"\n✅ Помечено: {marked} групп")
finally:
    db.close()
