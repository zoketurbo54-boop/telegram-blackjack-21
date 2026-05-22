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


def _is_admin(user_id: int) -> bool:
    admin = _admin_id()
    return admin is not None and user_id == admin


async def _reply_admin_denied(message: Message) -> None:
    """Почему /grant_premium не сработал (это не админка BotFather!)."""
    if not message.from_user:
        return
    uid = message.from_user.id
    admin = _admin_id()
    if admin is None:
        await message.answer(
            "❌ В <b>.env</b> на машине, где запущен бот, нет <code>TELEGRAM_ADMIN_ID</code>.\n\n"
            f"Ваш Telegram id: <code>{uid}</code> (узнать: /my_id или @userinfobot)\n\n"
            "1. Откройте .env рядом с bot.py\n"
            "2. Добавьте: <code>TELEGRAM_ADMIN_ID="
            f"{uid}</code>\n"
            "3. Перезапустите бота (systemctl restart или заново python bot.py)\n"
            "4. Снова: /grant_premium",
            parse_mode=ParseMode.HTML,
        )
        return
    await message.answer(
        "❌ Ваш id не совпадает с TELEGRAM_ADMIN_ID в .env.\n\n"
        f"Вы: <code>{uid}</code>\n"
        f"В .env: <code>{admin}</code>\n\n"
        "Исправьте .env и <b>перезапустите</b> бота. "
        "Админка в @BotFather к этому не относится.",
        parse_mode=ParseMode.HTML,
    )


@payments_router.message(Command("my_id"))
async def cmd_my_id(message: Message) -> None:
    if not message.from_user:
        return
    admin = _admin_id()
    admin_line = (
        f"TELEGRAM_ADMIN_ID в .env: <code>{admin}</code> ✅ совпадает"
        if admin == message.from_user.id
        else (
            f"TELEGRAM_ADMIN_ID в .env: <code>{admin}</code>"
            if admin is not None
            else "TELEGRAM_ADMIN_ID в .env: <b>не задан</b>"
        )
    )
    await message.answer(
        f"🆔 Ваш Telegram user_id: <code>{message.from_user.id}</code>\n"
        f"{admin_line}\n\n"
        "Этот id нужно вписать в .env и перезапустить бота, "
        "чтобы работали /grant_premium и /bot_stars.",
        parse_mode=ParseMode.HTML,
    )


@payments_router.message(Command("grant_premium"))
async def cmd_grant_premium(message: Message) -> None:
    """
    Выдать Premium без оплаты (только TELEGRAM_ADMIN_ID).

    /grant_premium — себе на 365 дней
    /grant_premium 30 — себе на 30 дней
    /grant_premium USER_ID 30 — другому пользователю на 30 дней
    """
    if not message.from_user:
        return
    if not _is_admin(message.from_user.id):
        await _reply_admin_denied(message)
        return

    parts = (message.text or "").split()
    target_id = message.from_user.id
    days = 365
    if len(parts) >= 2:
        if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
            target_id = int(parts[1])
            days = int(parts[2])
        elif parts[1].isdigit():
            days = int(parts[1])

    expires = int(time.time()) + days * 86400
    await sub_repo.activate(target_id, expires, charge_id="admin_grant")
    await message.answer(
        f"✅ Premium выдан\n"
        f"user_id: <code>{target_id}</code>\n"
        f"срок: <b>{days}</b> дн.\n"
        f"до: <b>{_format_expires(expires)}</b>",
        parse_mode=ParseMode.HTML,
    )


@payments_router.message(Command("revoke_premium"))
async def cmd_revoke_premium(message: Message) -> None:
    """Снять Premium (только админ). /revoke_premium или /revoke_premium USER_ID"""
    if not message.from_user:
        return
    if not _is_admin(message.from_user.id):
        await _reply_admin_denied(message)
        return

    parts = (message.text or "").split()
    target_id = message.from_user.id
    if len(parts) >= 2 and parts[1].isdigit():
        target_id = int(parts[1])

    await sub_repo.deactivate(target_id)
    await message.answer(
        f"❌ Premium снят для user_id <code>{target_id}</code>",
        parse_mode=ParseMode.HTML,
    )


@payments_router.message(Command("bot_stars"))
async def cmd_bot_stars(message: Message, bot: Bot) -> None:
    """Баланс звёзд на боте — только для TELEGRAM_ADMIN_ID в .env."""
    if not message.from_user:
        return
    if not _is_admin(message.from_user.id):
        if _admin_id() is None:
            await message.answer(
                "Задайте TELEGRAM_ADMIN_ID в .env (ваш id от @userinfobot)."
            )
        else:
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
