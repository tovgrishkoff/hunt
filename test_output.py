#!/usr/bin/env python3
"""Тест вывода в консоль"""

import sys
import time

print("=" * 60, flush=True)
print("Тест вывода в консоль", flush=True)
print("=" * 60, flush=True)

for i in range(5):
    print(f"Сообщение {i+1}/5", flush=True)
    time.sleep(1)

print("\n✅ Тест завершен!", flush=True)
