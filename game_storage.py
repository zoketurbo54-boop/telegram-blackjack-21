"""
Хранение состояния игры по user_id (в памяти процесса).

При перезапуске бота партии сбрасываются. Для SQLite можно заменить
реализацию тем же интерфейсом (get/set/delete).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Phase = Literal["idle", "player_turn", "finished"]


@dataclass
class GameState:
    phase: Phase = "idle"
    deck: list[str] = field(default_factory=list)
    player: list[str] = field(default_factory=list)
    dealer: list[str] = field(default_factory=list)
    # id сообщений бота для удаления перед следующей отрисовкой руки
    bot_message_ids: list[int] = field(default_factory=list)


class InMemoryGameStorage:
    def __init__(self) -> None:
        self._games: dict[int, GameState] = {}

    def get(self, user_id: int) -> GameState:
        if user_id not in self._games:
            self._games[user_id] = GameState()
        return self._games[user_id]

    def reset(self, user_id: int) -> None:
        self._games[user_id] = GameState()


storage = InMemoryGameStorage()
