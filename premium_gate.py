"""Проверка Premium перед игрой и показ оплаты."""
from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from billing import (
    SUBSCRIPTION_DESCRIPTION,
    SUBSCRIPTION_PAYLOAD,
    SUBSCRIPTION_PERIOD_SEC,
    SUBSCRIPTION_STARS,
    SUBSCRIPTION_TITLE,
)
from subscription_db import sub_repo
from aiogram.types import LabeledPrice


async def create_subscription_pay_url(bot: Bot) -> str:
    return await bot.create_invoice_link(
        title=SUBSCRIPTION_TITLE,
        description=SUBSCRIPTION_DESCRIPTION,
        payload=SUBSCRIPTION_PAYLOAD,
        currency="XTR",
        prices=[LabeledPrice(label="XTR", amount=SUBSCRIPTION_STARS)],
        provider_token="",
        subscription_period=SUBSCRIPTION_PERIOD_SEC,
    )


def _kb_pay() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Оплатить 50 / месяц", callback_data="sub:pay")],
            [InlineKeyboardButton(text="📋 Статус подписки", callback_data="sub:status")],
        ]
    )


async def send_paywall(bot: Bot, chat_id: int) -> None:
    await bot.send_message(
        chat_id,
        f"<b>Игра доступна только с Premium</b>\n\n"
        f"{SUBSCRIPTION_DESCRIPTION}\n\n"
        f"Стоимость: <b>{SUBSCRIPTION_STARS} ⭐</b> в месяц.\n"
        "Нажмите кнопку ниже — откроется счёт Telegram.",
        reply_markup=_kb_pay(),
        parse_mode=ParseMode.HTML,
    )


async def is_premium(user_id: int) -> bool:
    return await sub_repo.is_active(user_id)


async def ensure_premium_callback(callback: CallbackQuery) -> bool:
    """False — подписки нет, игру продолжать нельзя."""
    if not callback.from_user:
        await callback.answer("Ошибка пользователя.", show_alert=True)
        return False
    if await sub_repo.is_active(callback.from_user.id):
        return True
    await callback.answer(
        "Нужна подписка Premium (50 ⭐/мес). Оформите ниже.",
        show_alert=True,
    )
    if callback.message:
        await send_paywall(callback.bot, callback.message.chat.id)
    return False


async def ensure_premium_message(message: Message) -> bool:
    if not message.from_user:
        return False
    if await sub_repo.is_active(message.from_user.id):
        return True
    await message.answer(
        "<b>Игра доступна только с Premium</b> — оформите подписку:",
        reply_markup=_kb_pay(),
        parse_mode=ParseMode.HTML,
    )
    return False
