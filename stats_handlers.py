"""Команды /stats, /reset_stats и инлайн-меню статистики."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from stats_db import stats_repo

logger = logging.getLogger(__name__)

stats_router = Router(name="stats")


def _plural_win(n: int) -> str:
    n_abs = abs(n) % 100
    n1 = n_abs % 10
    if 11 <= n_abs <= 19:
        return "побед"
    if n1 == 1:
        return "победа"
    if 2 <= n1 <= 4:
        return "победы"
    return "побед"


def _kb_stats_root() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Моя статистика", callback_data="st:mine")],
            [InlineKeyboardButton(text="🔥 Текущая серия побед", callback_data="st:streak")],
            [InlineKeyboardButton(text="📈 Средний результат", callback_data="st:avg")],
            [InlineKeyboardButton(text="🏆 Рекорды", callback_data="st:rec")],
            [InlineKeyboardButton(text="🔙 Назад в игру", callback_data="st:back")],
        ]
    )


def _kb_reset_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, сбросить", callback_data="rst:yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data="rst:no"),
            ],
        ]
    )


def _format_my_stats(row) -> str:
    tg = row.total_games
    if tg == 0:
        return (
            "🎰 <b>Ваша статистика в 21 очко</b>\n\n"
            "Пока нет сыгранных партий. Нажмите «Начать игру»!"
        )
    wr = 100.0 * row.wins / tg
    avg_p = row.total_points_scored / tg
    avg_d = row.total_points_conceded / tg
    streak_word = _plural_win(row.current_win_streak)
    max_word = _plural_win(row.max_win_streak)
    return (
        "🎰 <b>Ваша статистика в 21 очко</b>\n\n"
        f"🎲 Всего игр: {tg}\n"
        f"✅ Побед: {row.wins}\n"
        f"❌ Поражений: {row.losses}\n"
        f"🤝 Ничьих: {row.draws}\n\n"
        f"📊 Процент побед: {wr:.1f}%\n\n"
        f"🔥 Серия сейчас: {row.current_win_streak} {streak_word} подряд\n"
        f"🏆 Рекордная серия: {row.max_win_streak} {max_word}\n\n"
        f"⭐ Средний счёт игрока: {avg_p:.1f}\n"
        f"🃃 Средний счёт дилера: {avg_d:.1f}"
    )


def _format_streak(row) -> str:
    if row.total_games == 0:
        return "🔥 Пока не сыграно ни одной партии — серии нет."
    cur = row.current_win_streak
    mx = row.max_win_streak
    left = max(0, mx - cur)
    wcur = _plural_win(cur)
    wleft = _plural_win(left)
    wmx = _plural_win(mx)
    return (
        f"🔥 <b>Твоя активная серия:</b> {cur} {wcur} подряд!\n\n"
        f"🎯 Осталось до рекорда: {left} {wleft}\n"
        f"(Рекорд: {mx} {wmx})"
    )


def _format_avg(row) -> str:
    tg = row.total_games
    if tg == 0:
        return "📈 Нет данных для средних — сыграйте хотя бы одну партию."
    avg_p = row.total_points_scored / tg
    avg_d = row.total_points_conceded / tg
    diff = avg_p - avg_d
    if diff > 0:
        tail = f"➕ Разница: <b>+{diff:.1f}</b> в твою пользу"
    elif diff < 0:
        tail = f"➖ Разница: <b>{diff:.1f}</b> (дилер в среднем выше)"
    else:
        tail = "➕ Разница: <b>0</b>"
    return (
        "📈 <b>Средние показатели за все игры:</b>\n\n"
        f"🎲 В среднем набираешь: <b>{avg_p:.1f}</b> очков\n"
        f"🃃 Дилер набирает против тебя: <b>{avg_d:.1f}</b> очков\n"
        f"{tail}"
    )


def _format_records(row) -> str:
    if row.total_games == 0:
        return "🏆 Рекорды появятся после первых партий."

    if row.best_win_quality >= 0:
        best = f"выиграл с {row.best_win_ps} очками (счёт {row.best_win_ps}-{row.best_win_ds})"
    else:
        best = "—"
    if row.sour_loss_valid:
        sour = f"проиграл при {row.sour_loss_ps} очках (счёт {row.sour_loss_ps}-{row.sour_loss_ds})"
    else:
        sour = "ещё не было «упорного» поражения (без перебора)"
    cards = row.max_cards_in_hand
    return (
        "🏆 <b>Твои рекорды:</b>\n\n"
        f"🔥 Максимальная серия побед: {row.max_win_streak}\n"
        f"🎯 Самая крупная победа: {best}\n"
        f"💔 Самое обидное поражение: {sour}\n"
        f"🃏 Самая длинная игра: {cards} карт на руке"
    )


@stats_router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not message.from_user:
        return
    await message.answer(
        "Выберите раздел:",
        reply_markup=_kb_stats_root(),
        parse_mode=ParseMode.HTML,
    )


@stats_router.message(Command("reset_stats"))
async def cmd_reset_stats(message: Message) -> None:
    if not message.from_user:
        return
    await message.answer(
        "⚠️ <b>Сбросить всю статистику и достижения для вашего аккаунта?</b>\n"
        "Это действие нельзя отменить.",
        reply_markup=_kb_reset_confirm(),
        parse_mode=ParseMode.HTML,
    )


@stats_router.callback_query(F.data == "game:stats")
async def cb_game_stats(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    await callback.message.answer(
        "📊 Статистика — выберите раздел:",
        reply_markup=_kb_stats_root(),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@stats_router.callback_query(F.data == "st:open")
async def cb_st_open(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    await callback.message.answer(
        "Выберите раздел:",
        reply_markup=_kb_stats_root(),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@stats_router.callback_query(F.data == "st:mine")
async def cb_st_mine(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    row = await stats_repo.get_row(callback.from_user.id)
    if row is None:
        text = (
            "🎰 <b>Ваша статистика в 21 очко</b>\n\n"
            "Пока нет сыгранных партий. Нажмите «Начать игру»!"
        )
    else:
        text = _format_my_stats(row)
    try:
        await callback.message.edit_text(
            text,
            reply_markup=_kb_stats_root(),
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("edit_text: %s", exc)
        await callback.message.answer(
            text,
            reply_markup=_kb_stats_root(),
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@stats_router.callback_query(F.data == "st:streak")
async def cb_st_streak(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    row = await stats_repo.get_row(callback.from_user.id)
    text = _format_streak(row) if row else "🔥 Пока не сыграно ни одной партии — серии нет."
    try:
        await callback.message.edit_text(
            text,
            reply_markup=_kb_stats_root(),
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("edit_text: %s", exc)
        await callback.message.answer(
            text,
            reply_markup=_kb_stats_root(),
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@stats_router.callback_query(F.data == "st:avg")
async def cb_st_avg(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    row = await stats_repo.get_row(callback.from_user.id)
    text = _format_avg(row) if row else "📈 Нет данных для средних — сыграйте хотя бы одну партию."
    try:
        await callback.message.edit_text(
            text,
            reply_markup=_kb_stats_root(),
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:  # noqa: BLE001
        await callback.message.answer(
            text,
            reply_markup=_kb_stats_root(),
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@stats_router.callback_query(F.data == "st:rec")
async def cb_st_rec(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    row = await stats_repo.get_row(callback.from_user.id)
    text = _format_records(row) if row else "🏆 Рекорды появятся после первых партий."
    try:
        await callback.message.edit_text(
            text,
            reply_markup=_kb_stats_root(),
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:  # noqa: BLE001
        await callback.message.answer(
            text,
            reply_markup=_kb_stats_root(),
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@stats_router.callback_query(F.data == "st:back")
async def cb_st_back(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    try:
        await callback.message.edit_text(
            "Выберите раздел:",
            reply_markup=_kb_stats_root(),
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("edit_text: %s", exc)
    await callback.answer("Меню обновлено.")


@stats_router.callback_query(F.data == "rst:yes")
async def cb_rst_yes(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await stats_repo.reset_user(callback.from_user.id)
    try:
        await callback.message.edit_text(
            "✅ Статистика и достижения сброшены.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:  # noqa: BLE001
        await callback.message.answer(
            "✅ Статистика и достижения сброшены.",
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@stats_router.callback_query(F.data == "rst:no")
async def cb_rst_no(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    try:
        await callback.message.edit_text("❌ Сброс отменён.", parse_mode=ParseMode.HTML)
    except Exception as exc:  # noqa: BLE001
        await callback.message.answer("❌ Сброс отменён.", parse_mode=ParseMode.HTML)
    await callback.answer()
