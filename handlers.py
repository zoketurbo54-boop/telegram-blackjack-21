"""
Обработчики команд и колбэков игры «21».

Отрисовка: альбомы InputMediaPhoto по URL deckofcardsapi; перед новой
отрисовкой удаляются сохранённые message_id (если delete не удался — игнор).
"""
from __future__ import annotations

import logging
from typing import Iterable

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from deck import (
    back_png_url,
    build_full_deck,
    card_png_url,
    hand_total,
    is_bust,
    shuffle_deck,
)
from game_storage import storage
from keyboards import kb_new_round, kb_player_turn, kb_start_game
from premium_gate import ensure_premium_callback
from stats_db import stats_repo

logger = logging.getLogger(__name__)

router = Router(name="blackjack")


class BJStates(StatesGroup):
    """FSM: отмечаем, что пользователь в активной партии (данные руки — в storage)."""

    playing = State()


async def _safe_delete_messages(bot, chat_id: int, message_ids: Iterable[int]) -> None:
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id, mid)
        except TelegramBadRequest:
            pass
        except Exception as exc:  # noqa: BLE001 — не роняем хендлер из‑за чужого сообщения
            logger.debug("delete_message failed chat=%s mid=%s: %s", chat_id, mid, exc)


async def _send_photo_album(
    bot,
    chat_id: int,
    urls: list[str],
    caption: str | None,
) -> list[int]:
    """
    Отправляет до 10+10 фото одним или двумя альбомами.
    caption ставится только на первое фото первого альбома (ограничение Telegram).
    """
    if not urls:
        msg = await bot.send_message(chat_id, caption or "")
        return [msg.message_id]

    ids: list[int] = []
    first_batch = urls[:10]
    media: list[InputMediaPhoto] = []
    for i, u in enumerate(first_batch):
        cap = caption if i == 0 else None
        media.append(InputMediaPhoto(media=u, caption=cap))
    try:
        sent = await bot.send_media_group(chat_id, media=media)
        ids.extend(m.message_id for m in sent)
    except Exception as exc:  # noqa: BLE001 — статический CDN, но на всякий случай
        logger.warning("send_media_group failed: %s", exc)
        fallback = await bot.send_message(
            chat_id,
            f"⚠️ Не удалось отправить изображения карт. Проверьте сеть / URL.\n{caption or ''}",
        )
        return [fallback.message_id]

    rest = urls[10:]
    if rest:
        try:
            media2 = [InputMediaPhoto(media=u) for u in rest[:10]]
            sent2 = await bot.send_media_group(chat_id, media=media2)
            ids.extend(m.message_id for m in sent2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("send_media_group (2nd) failed: %s", exc)
    return ids


def _ensure_deck(gs) -> None:
    if len(gs.deck) < 1:
        gs.deck = build_full_deck()
        shuffle_deck(gs.deck)


def _draw(gs) -> str:
    _ensure_deck(gs)
    return gs.deck.pop()


async def _purge_board(bot, chat_id: int, gs) -> None:
    await _safe_delete_messages(bot, chat_id, gs.bot_message_ids)
    gs.bot_message_ids.clear()


def _outcome_text(player_score: int, dealer_score: int, player_busted: bool) -> str:
    if player_busted:
        verdict = "Проиграли (перебор)"
    elif dealer_score > 21:
        verdict = "Вы выиграли (у дилера перебор)"
    elif player_score > dealer_score:
        verdict = "Вы выиграли"
    elif player_score < dealer_score:
        verdict = "Проиграли"
    else:
        verdict = "Ничья"
    return (
        f"🏆 <b>Вы набрали:</b> {player_score}\n"
        f"🃃 <b>Дилер набрал:</b> {dealer_score}\n"
        f"➡️ <b>Итог:</b> {verdict}"
    )


async def _send_dealer_partial(bot, chat_id: int, open_card: str, caption: str) -> list[int]:
    urls = [card_png_url(open_card), back_png_url()]
    return await _send_photo_album(bot, chat_id, urls, caption)


async def _send_dealer_full(bot, chat_id: int, cards: list[str], caption: str) -> list[int]:
    urls = [card_png_url(c) for c in cards]
    return await _send_photo_album(bot, chat_id, urls, caption)


async def _send_player_board(bot, chat_id: int, cards: list[str], caption: str) -> list[int]:
    urls = [card_png_url(c) for c in cards]
    return await _send_photo_album(bot, chat_id, urls, caption)


async def _render_active_turn(bot, chat_id: int, gs) -> Message:
    """Рука игрока + дилер с рубашкой + текст хода с кнопками."""
    await _purge_board(bot, chat_id, gs)

    p_cap = (
        "🃏 <b>Ваши карты:</b>\n"
        f"💥 <b>Ваши очки:</b> {hand_total(gs.player)}"
    )
    gs.bot_message_ids.extend(await _send_player_board(bot, chat_id, gs.player, p_cap))

    d_cap = (
        "🃃 <b>Карты дилера:</b> открытая карта + 🂠 рубашка\n"
        f"<i>Код открытой карты:</i> <code>{gs.dealer[0]}</code>"
    )
    gs.bot_message_ids.extend(await _send_dealer_partial(bot, chat_id, gs.dealer[0], d_cap))

    ctrl = await bot.send_message(
        chat_id,
        "Сделайте ход:",
        reply_markup=kb_player_turn(),
    )
    gs.bot_message_ids.append(ctrl.message_id)
    return ctrl


async def _render_finished(
    bot,
    chat_id: int,
    user_id: int,
    gs,
    player_busted: bool,
) -> None:
    """Полные руки, итог, «Новая игра» + запись статистики и достижений."""
    await _purge_board(bot, chat_id, gs)

    p_cap = (
        "🃏 <b>Ваши карты:</b>\n"
        f"💥 <b>Ваши очки:</b> {hand_total(gs.player)}"
    )
    gs.bot_message_ids.extend(await _send_player_board(bot, chat_id, gs.player, p_cap))

    d_cap = (
        "🃃 <b>Карты дилера (все открыты):</b>\n"
        f"💥 <b>Очки дилера:</b> {hand_total(gs.dealer)}"
    )
    gs.bot_message_ids.extend(await _send_dealer_full(bot, chat_id, gs.dealer, d_cap))

    ps = hand_total(gs.player)
    ds = hand_total(gs.dealer)
    result = await bot.send_message(
        chat_id,
        _outcome_text(ps, ds, player_busted),
        reply_markup=kb_new_round(),
    )
    gs.bot_message_ids.append(result.message_id)

    new_badges: list[str] = []
    try:
        new_badges = await stats_repo.record_round(
            user_id,
            player_busted=player_busted,
            player_score=ps,
            dealer_score=ds,
            player_cards=len(gs.player),
        )
    except Exception:
        logger.exception("Не удалось записать статистику")

    for title in new_badges:
        try:
            msg = await bot.send_message(
                chat_id,
                f"🏆 Ты получил достижение: <b>{title}</b>",
            )
            gs.bot_message_ids.append(msg.message_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось отправить поздравление о достижении: %s", exc)


async def _dealer_play(gs) -> None:
    while hand_total(gs.dealer) < 17:
        gs.dealer.append(_draw(gs))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user:
        storage.reset(message.from_user.id)
    await message.answer(
        "Привет! Это «21 очко» (упрощённый блэкджек).\n\n"
        "🎮 <b>Играть можно только с Premium</b> — 50 ⭐ в месяц "
        "(кнопка «⭐ Premium» или /subscribe).\n\n"
        "Команды: /stats, /subscribe, /my_id (ваш id для настройки бота).",
        reply_markup=kb_start_game(),
    )


@router.callback_query(F.data == "game:new")
async def cb_new_game(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer("Нет данных пользователя.", show_alert=True)
        return
    if not await ensure_premium_callback(callback):
        return
    uid = callback.from_user.id
    chat_id = callback.message.chat.id
    gs = storage.get(uid)

    await _purge_board(callback.bot, chat_id, gs)
    gs.phase = "player_turn"
    gs.player.clear()
    gs.dealer.clear()
    gs.deck = build_full_deck()
    shuffle_deck(gs.deck)

    for _ in range(2):
        gs.player.append(_draw(gs))
    for _ in range(2):
        gs.dealer.append(_draw(gs))

    await state.set_state(BJStates.playing)

    if is_bust(gs.player):
        gs.phase = "finished"
        await state.clear()
        await _render_finished(callback.bot, chat_id, uid, gs, player_busted=True)
        await callback.answer()
        return

    await _render_active_turn(callback.bot, chat_id, gs)
    await callback.answer()


@router.callback_query(F.data == "game:hit", StateFilter(BJStates.playing))
async def cb_hit(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    if not await ensure_premium_callback(callback):
        await state.clear()
        return
    uid = callback.from_user.id
    chat_id = callback.message.chat.id
    gs = storage.get(uid)

    if gs.phase != "player_turn":
        await callback.answer("Сначала начните игру кнопкой «Начать игру».", show_alert=True)
        return

    gs.player.append(_draw(gs))
    if is_bust(gs.player):
        gs.phase = "finished"
        await state.clear()
        await _render_finished(callback.bot, chat_id, uid, gs, player_busted=True)
    else:
        await _render_active_turn(callback.bot, chat_id, gs)
    await callback.answer()


@router.callback_query(F.data == "game:hit")
async def cb_hit_inactive(callback: CallbackQuery) -> None:
    await callback.answer("Нет активной партии. Нажмите «Начать игру».", show_alert=True)


@router.callback_query(F.data == "game:stand", StateFilter(BJStates.playing))
async def cb_stand(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    if not await ensure_premium_callback(callback):
        await state.clear()
        return
    uid = callback.from_user.id
    chat_id = callback.message.chat.id
    gs = storage.get(uid)

    if gs.phase != "player_turn":
        await callback.answer("Сначала начните игру кнопкой «Начать игру».", show_alert=True)
        return

    await _dealer_play(gs)
    gs.phase = "finished"
    await state.clear()
    await _render_finished(callback.bot, chat_id, uid, gs, player_busted=False)
    await callback.answer()


@router.callback_query(F.data == "game:stand")
async def cb_stand_inactive(callback: CallbackQuery) -> None:
    await callback.answer("Нет активной партии. Нажмите «Начать игру».", show_alert=True)
