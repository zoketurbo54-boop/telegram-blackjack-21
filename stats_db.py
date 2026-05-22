"""
Асинхронная SQLite-статистика (stats.db): партии, серии, рекорды, достижения.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent / "stats.db"

# Коды достижений → подписи для пользователя
ACHIEVEMENT_LABELS: dict[str, str] = {
    "first_win": "Первая победа",
    "streak_5": "5 побед подряд",
    "streak_10": "10 побед подряд",
    "score_21": "Набрал 21 очко",
    "win_5_cards": "Выиграл с 5 картами на руке",
}


def _win_quality_tuple(player_score: int, dealer_score: int) -> tuple[int, int, int]:
    """
    Сравнение «крупности» победы для рекорда.
    Дилер перебрал — отдельный «ярус»; иначе приоритет большей разницы ps - ds.
    """
    if dealer_score > 21:
        return (2_000 + player_score, player_score, -dealer_score)
    return (1_000 + (player_score - dealer_score), player_score, -dealer_score)


def _sour_loss_tuple(player_score: int, dealer_score: int) -> tuple[int, int]:
    """Поражение без перебора: чем выше счёт игрока и ниже у дилера — тем «обиднее»."""
    return (player_score, -dealer_score)


def _classify_outcome(player_busted: bool, ps: int, ds: int) -> str:
    if player_busted:
        return "loss"
    if ds > 21:
        return "win"
    if ps > ds:
        return "win"
    if ps < ds:
        return "loss"
    return "draw"


@dataclass
class PlayerStatsRow:
    user_id: int
    total_games: int
    wins: int
    losses: int
    draws: int
    current_win_streak: int
    max_win_streak: int
    total_points_scored: int
    total_points_conceded: int
    best_win_ps: int
    best_win_ds: int
    best_win_quality: int
    sour_loss_ps: int
    sour_loss_ds: int
    sour_loss_valid: int
    max_cards_in_hand: int


class StatsRepository:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS player_stats (
                    user_id INTEGER PRIMARY KEY,
                    total_games INTEGER NOT NULL DEFAULT 0,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    draws INTEGER NOT NULL DEFAULT 0,
                    current_win_streak INTEGER NOT NULL DEFAULT 0,
                    max_win_streak INTEGER NOT NULL DEFAULT 0,
                    total_points_scored INTEGER NOT NULL DEFAULT 0,
                    total_points_conceded INTEGER NOT NULL DEFAULT 0,
                    best_win_quality INTEGER NOT NULL DEFAULT -1,
                    best_win_ps INTEGER NOT NULL DEFAULT 0,
                    best_win_ds INTEGER NOT NULL DEFAULT 0,
                    sour_loss_ps INTEGER NOT NULL DEFAULT 0,
                    sour_loss_ds INTEGER NOT NULL DEFAULT 0,
                    sour_loss_valid INTEGER NOT NULL DEFAULT 0,
                    max_cards_in_hand INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS unlocked_achievements (
                    user_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    PRIMARY KEY (user_id, code)
                );

                CREATE INDEX IF NOT EXISTS idx_ach_user ON unlocked_achievements(user_id);
                """
            )
            await db.commit()
        logger.info("База статистики готова: %s", self._db_path)

    async def _fetch_row(self, db: aiosqlite.Connection, user_id: int) -> dict[str, Any] | None:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM player_stats WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_row(self, user_id: int) -> PlayerStatsRow | None:
        async with aiosqlite.connect(self._db_path) as db:
            raw = await self._fetch_row(db, user_id)
        if not raw:
            return None
        return PlayerStatsRow(
            user_id=raw["user_id"],
            total_games=raw["total_games"],
            wins=raw["wins"],
            losses=raw["losses"],
            draws=raw["draws"],
            current_win_streak=raw["current_win_streak"],
            max_win_streak=raw["max_win_streak"],
            total_points_scored=raw["total_points_scored"],
            total_points_conceded=raw["total_points_conceded"],
            best_win_ps=raw["best_win_ps"],
            best_win_ds=raw["best_win_ds"],
            best_win_quality=raw["best_win_quality"],
            sour_loss_ps=raw["sour_loss_ps"],
            sour_loss_ds=raw["sour_loss_ds"],
            sour_loss_valid=raw["sour_loss_valid"],
            max_cards_in_hand=raw["max_cards_in_hand"],
        )

    async def _has_achievement(self, db: aiosqlite.Connection, user_id: int, code: str) -> bool:
        cur = await db.execute(
            "SELECT 1 FROM unlocked_achievements WHERE user_id = ? AND code = ? LIMIT 1",
            (user_id, code),
        )
        return await cur.fetchone() is not None

    async def _grant_achievement(
        self, db: aiosqlite.Connection, user_id: int, code: str, fresh: list[str]
    ) -> None:
        if code not in ACHIEVEMENT_LABELS:
            return
        try:
            await db.execute(
                "INSERT INTO unlocked_achievements (user_id, code) VALUES (?, ?)",
                (user_id, code),
            )
            fresh.append(ACHIEVEMENT_LABELS[code])
        except sqlite3.IntegrityError:
            pass

    async def record_round(
        self,
        user_id: int,
        *,
        player_busted: bool,
        player_score: int,
        dealer_score: int,
        player_cards: int,
    ) -> list[str]:
        """
        Записывает завершённый раунд. Возвращает подписи НОВЫХ достижений (для поздравлений).
        """
        outcome = _classify_outcome(player_busted, player_score, dealer_score)
        new_badges: list[str] = []

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO player_stats (user_id) VALUES (?)",
                (user_id,),
            )

            raw = await self._fetch_row(db, user_id)
            if not raw:
                return new_badges

            tg = raw["total_games"] + 1
            wins = raw["wins"]
            losses = raw["losses"]
            draws = raw["draws"]
            streak = raw["current_win_streak"]
            max_streak = raw["max_win_streak"]
            tps = raw["total_points_scored"] + player_score
            tpc = raw["total_points_conceded"] + dealer_score

            best_q = raw["best_win_quality"]
            best_ps, best_ds = raw["best_win_ps"], raw["best_win_ds"]
            sour_ok = raw["sour_loss_valid"]
            sour_ps, sour_ds = raw["sour_loss_ps"], raw["sour_loss_ds"]
            max_cards = max(raw["max_cards_in_hand"], player_cards)

            if outcome == "win":
                wins += 1
                streak += 1
                max_streak = max(max_streak, streak)
                cand_t = _win_quality_tuple(player_score, dealer_score)
                old_t = _win_quality_tuple(best_ps, best_ds) if best_q >= 0 else (-1, 0, 0)
                if best_q < 0 or cand_t > old_t:
                    best_ps, best_ds = player_score, dealer_score
                    best_q = cand_t[0]
            elif outcome == "loss":
                losses += 1
                streak = 0
                if not player_busted:
                    cand = _sour_loss_tuple(player_score, dealer_score)
                    if sour_ok == 0:
                        sour_ok = 1
                        sour_ps, sour_ds = player_score, dealer_score
                    else:
                        old = _sour_loss_tuple(sour_ps, sour_ds)
                        if cand > old:
                            sour_ps, sour_ds = player_score, dealer_score
            else:
                draws += 1

            await db.execute(
                """
                UPDATE player_stats SET
                    total_games = ?, wins = ?, losses = ?, draws = ?,
                    current_win_streak = ?, max_win_streak = ?,
                    total_points_scored = ?, total_points_conceded = ?,
                    best_win_quality = ?, best_win_ps = ?, best_win_ds = ?,
                    sour_loss_ps = ?, sour_loss_ds = ?, sour_loss_valid = ?,
                    max_cards_in_hand = ?
                WHERE user_id = ?
                """,
                (
                    tg,
                    wins,
                    losses,
                    draws,
                    streak,
                    max_streak,
                    tps,
                    tpc,
                    best_q,
                    best_ps,
                    best_ds,
                    sour_ps,
                    sour_ds,
                    sour_ok,
                    max_cards,
                    user_id,
                ),
            )

            # Достижения
            if outcome == "win" and wins == 1:
                await self._grant_achievement(db, user_id, "first_win", new_badges)
            if streak >= 5:
                await self._grant_achievement(db, user_id, "streak_5", new_badges)
            if streak >= 10:
                await self._grant_achievement(db, user_id, "streak_10", new_badges)
            if player_score == 21:
                await self._grant_achievement(db, user_id, "score_21", new_badges)
            if outcome == "win" and player_cards >= 5:
                await self._grant_achievement(db, user_id, "win_5_cards", new_badges)

            await db.commit()

        return new_badges

    async def reset_user(self, user_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM player_stats WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM unlocked_achievements WHERE user_id = ?", (user_id,))
            await db.commit()


stats_repo = StatsRepository()
