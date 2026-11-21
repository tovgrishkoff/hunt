#!/usr/bin/env python3

# POLICY: +1 phones -> only US proxies 196.19.*/ResZcz; never 170.168.*
"""
Assign proxies to all promotion_* accounts in accounts_config.json (round-robin),
sync them to DB, and (optionally) restart services.

This is intended for already-authorized accounts: we only change `proxy`, not sessions.

Supported proxy inputs:
  - MTProxy/MTProto: IP:PORT:SECRET or tg://proxy?... or mtproxy://...
  - HTTP raw tuple (provider): HOST:PORT:USER:PASS  -> converted to http://USER:PASS@HOST:PORT
  - HTTP URL: http://USER:PASS@HOST:PORT
  - SOCKS5 URL: socks5://USER:PASS@HOST:PORT

Examples:
  python3 scripts/assign_proxies_round_robin.py \\
    --proxy \"193.8.8.244:443:SECRET\" \\
    --proxy \"178.171.42.53:9735:Vu9TDx:0zumuH\" \\
    --apply-db \\
    --restart
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from shared.telegram.client_manager import TelegramClientManager


def _normalize_proxy(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        raise ValueError("Empty proxy string")

    # Provider "host:port:user:pass" -> http://user:pass@host:port
    m = re.match(r"^(?P<host>[^:\s]+):(?P<port>\d+):(?P<user>[^:\s]+):(?P<pw>\S+)$", s)
    if m:
        return f"http://{m.group('user')}:{m.group('pw')}@{m.group('host')}:{m.group('port')}"

    return s


def _load_accounts_config(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("accounts_config.json must be a list")
    return data


def _save_accounts_config(path: Path, accounts: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(accounts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Round-robin proxy assignment for promotion_*.")
    parser.add_argument(
        "--proxy",
        action="append",
        default=[],
        help="Proxy string (repeatable).",
    )
    parser.add_argument(
        "--apply-db",
        action="store_true",
        help="After updating accounts_config.json, sync to DB via update_all_accounts_from_config.py.",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart Bali services after DB sync (requires --apply-db).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned mapping without writing files.",
    )
    args = parser.parse_args()

    proxies_in = [_normalize_proxy(p) for p in args.proxy]
    if not proxies_in:
        print("Provide at least one --proxy", file=sys.stderr)
        return 2

    mgr = TelegramClientManager(sessions_dir="/tmp")
    bad: List[str] = []
    for p in proxies_in:
        cfg = mgr.parse_proxy(p)
        if not isinstance(cfg, dict) or cfg.get("proxy_type") not in ("mtproto", "http", "socks5"):
            bad.append(p)
    if bad:
        print("These proxies are not recognized as mtproto/http/socks5:", file=sys.stderr)
        for p in bad:
            print(f"  - {p}", file=sys.stderr)
        return 3

    cfg_path = ROOT_DIR / "accounts_config.json"
    accounts = _load_accounts_config(cfg_path)
    promo_idxs = [i for i, a in enumerate(accounts) if str(a.get("session_name", "")).startswith("promotion_")]
    promo_names = [accounts[i].get("session_name") for i in promo_idxs]
    promo_names_sorted = sorted(promo_names)

    # Make assignment stable: alphabetical by session_name.
    name_to_idx = {accounts[i].get("session_name"): i for i in promo_idxs}
    planned: List[Tuple[str, str, str]] = []
    for n_i, name in enumerate(promo_names_sorted):
        idx = name_to_idx[name]
        new_proxy = proxies_in[n_i % len(proxies_in)]
        old_proxy = str(accounts[idx].get("proxy") or "")
        planned.append((name, old_proxy, new_proxy))

    print("Planned proxy assignment (round-robin):")
    changes = 0
    for name, old, new in planned:
        changed = old != new
        if changed:
            changes += 1
        print(f"  - {name}: {'CHANGE' if changed else 'same'}")
        if changed:
            print(f"      old: {old}")
            print(f"      new: {new}")

    if args.dry_run:
        print("\nDry-run: no files/DB updated.")
        return 0

    if changes == 0:
        print("\nNo changes needed in accounts_config.json.")
    else:
        for name, _old, new in planned:
            idx = name_to_idx[name]
            accounts[idx]["proxy"] = new
        _save_accounts_config(cfg_path, accounts)
        print("\n✅ Updated accounts_config.json")

    if args.apply_db:
        updater = ROOT_DIR / "scripts" / "update_all_accounts_from_config.py"
        print("\n🔄 Syncing config -> DB ...")
        res = subprocess.run([sys.executable, str(updater)], cwd=str(ROOT_DIR))
        if res.returncode != 0:
            return res.returncode
        print("✅ DB synced.")

        if args.restart:
            print("\n🔄 Restarting services ...")
            res2 = subprocess.run(
                ["docker-compose", "restart", "account-manager", "marketer", "activity", "secretary"],
                cwd=str(ROOT_DIR),
            )
            if res2.returncode != 0:
                return res2.returncode
            print("✅ Services restarted.")
    elif args.restart:
        print("--restart requires --apply-db", file=sys.stderr)
        return 4

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

