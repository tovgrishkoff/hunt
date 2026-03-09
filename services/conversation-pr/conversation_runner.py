"""
Партизанский PR: диалоги в группах (вопрос → рекомендация → поддержка).
Один аккаунт спрашивает, другой рекомендует @marisha_lovephoto, третий поддерживает.
"""
import asyncio
import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.database.session import SessionLocal
from shared.database.models import Account, Group
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    ChannelPrivateError,
    ChatForbiddenError,
    ChatGuestSendForbiddenError,
    UserBannedInChannelError,
    ChannelBannedError,
)

logger = logging.getLogger(__name__)

CONFIG_PATHS = [
    Path("/app/config/bali_conversations.json"),
    Path(__file__).resolve().parent.parent.parent / "config" / "bali_conversations.json",
    Path("config/bali_conversations.json"),
]
LOG_FILE_PATHS = [
    Path("/app/data/conversation_pr_log.json"),
    Path(__file__).resolve().parent.parent.parent / "data" / "conversation_pr_log.json",
    Path("data/conversation_pr_log.json"),
]


def load_conversations_config() -> Dict[str, Any]:
    """Загрузить config/bali_conversations.json."""
    for p in CONFIG_PATHS:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load {p}: {e}")
    return {}


def load_log() -> Dict[str, str]:
    """Загрузить лог последних запусков по группам (username -> ISO datetime)."""
    for p in LOG_FILE_PATHS:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load log {p}: {e}")
    return {}


def save_log(log_data: Dict[str, str]) -> None:
    """Сохранить лог."""
    for p in LOG_FILE_PATHS:
        if p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(log_data, f, ensure_ascii=False, indent=2)
                return
            except Exception as e:
                logger.warning(f"Failed to save log to {p}: {e}")
            break


def get_eligible_groups(
    db,
    niche: str,
    exclude_usernames: set,
    limit: int = 50,
    only_warmed: bool = False,
) -> List[Group]:
    """
    Группы, готовые к постингу (active/joined).
    only_warmed=True: только прогретые — warm_up_until уже прошёл и can_post=True.
    only_warmed=False: warm-up пройден или не задан, can_post True или не задан.
    """
    from sqlalchemy import or_

    now = datetime.utcnow()
    if only_warmed:
        # Только группы из базы, уже прогретые: warm_up прошёл, можно постить
        filters = [
            Group.niche == niche,
            Group.status.in_(["active", "joined"]),
            Group.warm_up_until.isnot(None),
            Group.warm_up_until <= now,
            Group.can_post.is_(True),
        ]
    else:
        filters = [
            Group.niche == niche,
            Group.status.in_(["active", "joined"]),
            or_(Group.warm_up_until.is_(None), Group.warm_up_until <= now),
            or_(Group.can_post.is_(None), Group.can_post.is_(True)),
        ]
    if exclude_usernames:
        filters.append(Group.username.notin_(list(exclude_usernames)))
    q = (
        db.query(Group)
        .filter(*filters)
        .order_by(Group.members_count.desc().nullslast())
        .limit(limit)
        .all()
    )
    return q


def get_bali_session_names(db) -> List[str]:
    """Список session_name аккаунтов с niche=bali и status=active.
    Fallback: если мало — берём active из bali_accounts_config (role_* в сценариях)."""
    rows = (
        db.query(Account.session_name)
        .filter(Account.niche == "bali", Account.status == "active")
        .all()
    )
    result = [r[0] for r in rows]
    if len(result) >= 3:
        return result
    # Fallback: все аккаунты из role_ask/reply/support сценариев, которые active
    import json
    from pathlib import Path
    config_paths = [
        Path("/app/bali_accounts_config.json"),
        Path(__file__).resolve().parent.parent.parent / "bali_accounts_config.json",
        Path("bali_accounts_config.json"),
    ]
    allowed = set()
    for p in config_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    allowed = set(json.load(f).get("allowed_accounts", []))
                break
            except Exception:
                pass
    if not allowed:
        return result
    active_rows = (
        db.query(Account.session_name)
        .filter(Account.status == "active", Account.session_name.in_(list(allowed)))
        .all()
    )
    fallback = [r[0] for r in active_rows]
    return fallback if len(fallback) > len(result) else result


class ConversationPRRunner:
    """Запуск одного или нескольких диалогов (вопрос → ответ → поддержка) в группах."""

    def __init__(self, client_manager):
        self.client_manager = client_manager
        self.config = load_conversations_config()
        self.min_days = int(self.config.get("min_days_between_same_group", 7))
        self.max_per_run = int(self.config.get("max_conversations_per_run", 8))
        self.scenarios = self.config.get("scenarios", [])

    def _log_path(self) -> Path:
        for p in LOG_FILE_PATHS:
            if p.parent.exists() or p == LOG_FILE_PATHS[1]:
                return p.parent / "conversation_pr_log.json"
        return Path("data/conversation_pr_log.json")

    def _groups_eligible_for_run(self) -> List[tuple]:
        """Группы, в которых не было диалога последние min_days дней."""
        db = SessionLocal()
        try:
            log_data = load_log()
            cutoff_dt = datetime.utcnow() - timedelta(days=self.min_days)
            exclude = set()
            for username, last in log_data.items():
                try:
                    last_dt = datetime.fromisoformat(last)
                except Exception:
                    continue
                if last_dt >= cutoff_dt:
                    exclude.add(username)

            # Сначала мягкий фильтр: active/joined, warm_up пройден или не задан (максимум групп для партизанского PR)
            groups = get_eligible_groups(db, "bali", exclude, limit=100, only_warmed=False)
            if groups:
                logger.info(f"Using {len(groups)} eligible groups (active/joined, warm-up relaxed)")
            if not groups:
                # Фоллбек: только active/joined без доп. условий
                logger.info("No eligible groups, using fallback (active/joined only)")
                from sqlalchemy import and_
                groups = (
                    db.query(Group)
                    .filter(
                        and_(
                            Group.niche == "bali",
                            Group.status.in_(["active", "joined"]),
                        )
                    )
                    .order_by(Group.members_count.desc().nullslast())
                    .limit(100)
                    .all()
                )
            return [(g.username, g.title) for g in groups]
        finally:
            db.close()

    def _pick_accounts(
        self,
        scenario: Dict,
        available_sessions: List[str],
    ) -> Optional[tuple]:
        """Выбрать трёх разных аккаунтов: ask, reply, support."""
        ask_list = [s for s in scenario.get("role_ask", []) if s in available_sessions]
        reply_list = [s for s in scenario.get("role_reply", []) if s in available_sessions]
        support_list = [s for s in scenario.get("role_support", []) if s in available_sessions]
        if not ask_list or not reply_list or not support_list:
            return None
        ask = random.choice(ask_list)
        reply = random.choice([s for s in reply_list if s != ask])
        support = random.choice([s for s in support_list if s not in (ask, reply)])
        if not support and support_list:
            support = random.choice(support_list)
        return (ask, reply, support)

    async def run_one_conversation(
        self,
        group_username: str,
        scenario: Dict,
        ask_session: str,
        reply_session: str,
        support_session: str,
    ) -> bool:
        """Отправить один диалог из 3 сообщений в группу."""
        ask_t = random.choice(scenario.get("ask_templates", ["Кто порекомендует фотографа на Бали?"]))
        reply_t = random.choice(scenario.get("reply_templates", []))
        support_t = random.choice(scenario.get("support_templates", []))
        min_d = scenario.get("min_delay_sec", 45)
        max_d = scenario.get("max_delay_sec", 180)
        delay1 = random.randint(min_d, max_d)
        delay2 = random.randint(min_d, max_d)

        username_clean = group_username.lstrip("@")
        clients = self.client_manager.clients

        for label, session_name, text in [
            ("ASK", ask_session, ask_t),
            ("REPLY", reply_session, reply_t),
            ("SUPPORT", support_session, support_t),
        ]:
            client = clients.get(session_name)
            if not client or not client.is_connected():
                logger.warning(
                    f"  ⚠️ [{label}] Client {session_name} не загружен в контейнере — ответ не отправлен. "
                    "Проверь: niche=bali, string_session в БД, логи при старте conversation-pr."
                )
                return False
            try:
                entity = await client.get_entity(username_clean)
                await client.send_message(entity, text)
                logger.info(f"  ✅ [{label}] {session_name} → {group_username}: отправлено")
            except FloodWaitError as e:
                wait = getattr(e, "seconds", 60) or 60
                logger.warning(f"  ⏳ FloodWait {wait}s for {session_name}, waiting...")
                await asyncio.sleep(min(wait, 300))
                try:
                    entity = await client.get_entity(username_clean)
                    await client.send_message(entity, text)
                    logger.info(f"  ✅ [{label}] {session_name} → {group_username}: отправлено (после wait)")
                except Exception as e2:
                    logger.error(f"  ❌ [{label}] {session_name}: {e2}")
                    return False
            except (
                ChatWriteForbiddenError,
                ChannelPrivateError,
                ChatForbiddenError,
                ChatGuestSendForbiddenError,
                UserBannedInChannelError,
                ChannelBannedError,
            ) as e:
                logger.warning(
                    f"  ⚠️ [{label}] {session_name} в {group_username}: нет прав / бан — {e}. "
                    "В группе виден только вопрос (ASK), ответы не отправлены."
                )
                return False
            except Exception as e:
                logger.warning(f"  ⚠️ [{label}] {session_name} → {group_username}: {e}")
                return False
            if label == "ASK":
                await asyncio.sleep(delay1)
            elif label == "REPLY":
                await asyncio.sleep(delay2)
        return True

    async def run_cycle(self) -> Dict[str, int]:
        """Один цикл: выбрать группы и сценарии, отправить до max_per_run диалогов."""
        result = {"sent": 0, "skipped": 0}
        if not self.scenarios:
            logger.warning("No scenarios in config")
            return result

        db = SessionLocal()
        try:
            available_sessions = get_bali_session_names(db)
        finally:
            db.close()

        available_set = set(self.client_manager.clients.keys())
        available_sessions = [s for s in available_sessions if s in available_set]
        if len(available_sessions) < 3:
            logger.warning("Need at least 3 Bali accounts loaded")
            return result

        eligible = self._groups_eligible_for_run()
        if not eligible:
            logger.info("No eligible groups (all used recently)")
            return result

        log_data = load_log()
        random.shuffle(eligible)

        for _ in range(self.max_per_run):
            if not eligible:
                break
            group_username, title = eligible.pop(0)
            scenario = random.choice(self.scenarios)
            triple = self._pick_accounts(scenario, available_sessions)
            if not triple:
                result["skipped"] += 1
                continue
            ask_s, reply_s, support_s = triple
            logger.info(f"💬 Диалог в {group_username} ({title[:40]}...): ask={ask_s}, reply={reply_s}, support={support_s}")
            try:
                ok = await self.run_one_conversation(
                    group_username, scenario, ask_s, reply_s, support_s
                )
                if ok:
                    result["sent"] += 1
                    log_data[group_username] = datetime.utcnow().isoformat()
                    save_log(log_data)
                else:
                    result["skipped"] += 1
            except Exception as e:
                logger.warning(f"  ⚠️ Группа {group_username} пропущена (ошибка): {e}")
                result["skipped"] += 1
            await asyncio.sleep(random.randint(30, 90))

        return result
