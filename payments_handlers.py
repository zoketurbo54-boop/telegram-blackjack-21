"""
Подписка Premium за Telegram Stars (50 ⭐ / 30 дней, автопродление).

Звёзды зачисляются на баланс БОТА (аккаунт владельца в @BotFather / Fragment),
не на личный кошелёк пользователя, который платит.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
)

from billing import (
    SUBSCRIPTION_DESCRIPTION,
    SUBSCRIPTION_PAYLOAD,
    SUBSCRIPTION_PERIOD_SEC,
    SUBSCRIPTION_STARS,
)
from premium_gate import create_subscription_pay_url
from subscription_db import sub_repo

logger = logging.getLogger(__name__)

payments_router = Router(name="payments")


def _admin_id() -> int | None:
    raw = os.getenv("TELEGRAM_ADMIN_ID", "").strip()
    if not raw.isdigit():
        return None
    return int(raw)


def _kb_subscribe_menu(invoice_url: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if invoice_url:
        rows.append([InlineKeyboardButton(text="⭐ Оплатить 50 / месяц", url=invoice_url)])
    rows.append([InlineKeyboardButton(text="📋 Статус подписки", callback_data="sub:status")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_expires(expires_at: int) -> str:
    if expires_at <= 0:
        return "не активна"
    return datetime.fromtimestamp(expires_at).strftime("%d.%m.%Y %H:%M")


@payments_router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, bot: Bot) -> None:
    if not message.from_user:
        return
    link = await create_subscription_pay_url(bot)
    active = await sub_repo.is_active(message.from_user.id)
    status = "✅ Premium активен" if active else "Подписка не оформлена"
    await message.answer(
        f"<b>Premium за {SUBSCRIPTION_STARS} ⭐ в месяц</b>\n\n"
        f"{SUBSCRIPTION_DESCRIPTION}\n\n"
        f"Статус: {status}\n\n"
        "<b>Без подписки игра недоступна.</b>\n\n"
        "💡 Звёзды списываются у плательщика и "
        "<b>зачисляются на баланс бота</b> (@BotFather → Monetization / Fragment).",
        reply_markup=_kb_subscribe_menu(link),
        parse_mode=ParseMode.HTML,
    )


@payments_router.callback_query(F.data == "sub:open")
async def cb_sub_open(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    link = await create_subscription_pay_url(bot)
    active = await sub_repo.is_active(callback.from_user.id)
    status = "✅ Premium активен" if active else "оформите подписку"
    await callback.message.answer(
        f"<b>Premium — {SUBSCRIPTION_STARS} ⭐ / месяц</b>\n"
        f"Статус: {status}",
        reply_markup=_kb_subscribe_menu(link),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@payments_router.callback_query(F.data == "sub:status")
async def cb_sub_status(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    row = await sub_repo.get(callback.from_user.id)
    now = int(time.time())
    if row and row.expires_at > now:
        text = (
            "✅ <b>Premium активен</b>\n"
            f"Действует до: {_format_expires(row.expires_at)}\n\n"
            "Отменить автопродление: Настройки Telegram → "
            "«Мои звёзды» / подписки на ботов."
        )
    else:
        text = (
            "❌ Premium не активен.\n"
            "Нажмите «Оплатить 50 ⭐», чтобы оформить подписку."
        )
    await callback.message.answer(text, parse_mode=ParseMode.HTML)
    await callback.answer()


@payments_router.callback_query(F.data == "sub:pay")
async def cb_sub_pay(callback: CallbackQuery, bot: Bot) -> None:
    """Кнопка оплаты из paywall (ссылка на счёт)."""
    if not callback.message:
        await callback.answer()
        return
    link = await create_subscription_pay_url(bot)
    await callback.message.answer(
        f"Оплата <b>{SUBSCRIPTION_STARS} ⭐</b> / месяц:",
        reply_markup=_kb_subscribe_menu(link),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@payments_router.pre_checkout_query(F.invoice_payload == SUBSCRIPTION_PAYLOAD)
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@payments_router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    if not message.from_user or not message.successful_payment:
        return
    sp = message.successful_payment
    if sp.invoice_payload != SUBSCRIPTION_PAYLOAD:
        return

    uid = message.from_user.id
    expires = sp.subscription_expiration_date
    if not expires:
        expires = int(time.time()) + SUBSCRIPTION_PERIOD_SEC

    await sub_repo.activate(
        uid,
        expires_at=expires,
        charge_id=sp.telegram_payment_charge_id,
    )

    renew = " (продление)" if sp.is_recurring else ""
    first = " 🎉" if sp.is_first_recurring else ""
    await message.answer(
        f"✅ Premium активирован{renew}{first}\n"
        f"Действует до: <b>{_format_expires(expires)}</b>\n\n"
        "Спасибо! Теперь можно играть — нажмите «▶️ Начать игру» в /start.",
        parse_mode=ParseMode.HTML,
    )
    logger.info(
        "Premium user=%s expires=%s charge=%s recurring=%s",
        uid,
        expires,
        sp.telegram_payment_charge_id,
        sp.is_recurring,
    )


@payments_router.message(Command("bot_stars"))
async def cmd_bot_stars(message: Message, bot: Bot) -> None:
    """Баланс звёзд на боте — только для TELEGRAM_ADMIN_ID в .env."""
    if not message.from_user:
        return
    admin = _admin_id()
    if admin is None:
        await message.answer(
            "Команда для владельца: задайте TELEGRAM_ADMIN_ID в окружении "
            "(ваш числовой Telegram user id)."
        )
        return
    if message.from_user.id != admin:
        await message.answer("Недостаточно прав.")
        return
    balance = await bot.get_my_star_balance()
    amount = balance.amount
    await message.answer(
        f"⭐ <b>Баланс звёзд бота:</b> {amount}\n\n"
        "Вывод и детали — в @BotFather (Monetization) и на "
        "<a href=\"https://fragment.com\">Fragment</a> для разработчиков.",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
