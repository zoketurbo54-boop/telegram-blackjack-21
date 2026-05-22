"""Подписка Premium (Stars) — срок действия в SQLite."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

DB_PATH = Path(__file__).resolve().parent / "stats.db"


@dataclass
class PremiumRow:
    user_id: int
    expires_at: int
    last_payment_charge_id: str | None


class SubscriptionRepository:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS premium_subscriptions (
                    user_id INTEGER PRIMARY KEY,
                    expires_at INTEGER NOT NULL DEFAULT 0,
                    last_payment_charge_id TEXT
                )
                """
            )
            await db.commit()

    async def activate(
        self,
        user_id: int,
        expires_at: int,
        charge_id: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO premium_subscriptions (user_id, expires_at, last_payment_charge_id)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    expires_at = excluded.expires_at,
                    last_payment_charge_id = excluded.last_payment_charge_id
                """,
                (user_id, expires_at, charge_id),
            )
            await db.commit()

    async def get(self, user_id: int) -> PremiumRow | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT user_id, expires_at, last_payment_charge_id "
                "FROM premium_subscriptions WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
        if not row:
            return None
        return PremiumRow(
            user_id=row["user_id"],
            expires_at=row["expires_at"],
            last_payment_charge_id=row["last_payment_charge_id"],
        )

    async def is_active(self, user_id: int) -> bool:
        row = await self.get(user_id)
        if not row:
            return False
        return row.expires_at > int(time.time())

    async def deactivate(self, user_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE premium_subscriptions SET expires_at = 0 WHERE user_id = ?",
                (user_id,),
            )
            await db.commit()


sub_repo = SubscriptionRepository()
