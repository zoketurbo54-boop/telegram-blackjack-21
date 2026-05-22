"""Inline-клавиатуры для игры в «21»."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def kb_start_game() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Начать игру (Premium)", callback_data="game:new")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="st:open")],
            [InlineKeyboardButton(text="⭐ Premium 50/мес", callback_data="sub:open")],
        ]
    )


def kb_player_turn() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Ещё карту", callback_data="game:hit"),
                InlineKeyboardButton(text="✋ Оставить", callback_data="game:stand"),
            ],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="game:stats")],
        ]
    )


def kb_new_round() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Новая игра", callback_data="game:new")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="game:stats")],
        ]
    )
