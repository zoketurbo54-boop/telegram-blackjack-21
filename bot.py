"""
Точка входа: установите переменную окружения BOT_TOKEN и запустите:

  $env:BOT_TOKEN = "ваш_токен"
  python bot.py

Если не удаётся подключиться к api.telegram.org (WinError 121, таймаут,
ClientConnectorError) — чаще всего блокировка или маршрут до Telegram.

  • Включите VPN или задайте прокси (пакет aiohttp-socks уже в requirements):

      $env:TELEGRAM_PROXY = "socks5://127.0.0.1:1080"

  • Явно хост и порт (удобно при сложном пароле):

      $env:TELEGRAM_PROXY_SCHEME = "socks5"
      $env:TELEGRAM_PROXY_HOST = "gate.example.com"
      $env:TELEGRAM_PROXY_PORT = "1080"
      $env:TELEGRAM_PROXY_USER = "логин"
      $env:TELEGRAM_PROXY_PASSWORD = "пароль"

  • При необходимости увеличьте таймаут (секунды):

      $env:TELEGRAM_REQUEST_TIMEOUT = "120"

  • Повторы проверки связи перед polling:

      $env:TELEGRAM_CONNECT_RETRIES = "8"
      $env:TELEGRAM_CONNECT_DELAY = "3"

  • На VPS часто ломается только IPv6 — по умолчанию включено подключение по IPv4:

      $env:TELEGRAM_FORCE_IPV4 = "1"

    Отключить (если нужен именно IPv6):

      $env:TELEGRAM_FORCE_IPV4 = "0"
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import sys
from pathlib import Path

from aiohttp import BasicAuth
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage

from handlers import router as blackjack_router
from payments_handlers import payments_router
from stats_db import stats_repo
from stats_handlers import stats_router
from subscription_db import sub_repo


def _parse_proxy_scheme(url: str, default: str = "socks5") -> str:
    if "://" in url:
        return url.split("://", 1)[0].strip().lower() or default
    return default


def _validate_proxy_host_port(url: str) -> None:
    """Проверяет, что после последнего ':' идёт числовой порт (иначе в URL затесался логин/пароль)."""
    if not url or "://" not in url:
        return
    _, rest = url.split("://", 1)
    if ":" not in rest:
        raise ValueError(
            "В TELEGRAM_PROXY нужен порт, например socks5://127.0.0.1:1080 "
            "или задайте TELEGRAM_PROXY_HOST и TELEGRAM_PROXY_PORT."
        )
    _host, port_s = rest.rsplit(":", 1)
    if not port_s.isdigit():
        raise ValueError(
            f"Некорректный TELEGRAM_PROXY: после последнего ':' должен быть порт (цифры), "
            f"а не {port_s!r}. Не пишите логин:пароль в одной строке без «@хост» — "
            "используйте TELEGRAM_PROXY_USER, TELEGRAM_PROXY_PASSWORD "
            "или TELEGRAM_PROXY_HOST + TELEGRAM_PROXY_PORT."
        )


def _build_proxy_endpoint_url() -> str | None:
    """
    Собирает URL вида socks5://host:port без учётных данных в строке
    (учётные данные передаются отдельно через BasicAuth).
    """
    scheme = (os.getenv("TELEGRAM_PROXY_SCHEME", "socks5").strip() or "socks5").lower()
    host = os.getenv("TELEGRAM_PROXY_HOST", "").strip()
    port_s = os.getenv("TELEGRAM_PROXY_PORT", "").strip()
    legacy = os.getenv("TELEGRAM_PROXY", "").strip()
    user = os.getenv("TELEGRAM_PROXY_USER", "").strip()

    if host:
        if not port_s:
            raise ValueError("Задан TELEGRAM_PROXY_HOST, но не задан TELEGRAM_PROXY_PORT.")
        if not port_s.isdigit():
            raise ValueError(f"TELEGRAM_PROXY_PORT должен быть числом, сейчас: {port_s!r}")
        return f"{scheme}://{host}:{int(port_s)}"

    if not legacy:
        return None

    if user and "@" in legacy:
        tail = legacy.rsplit("@", 1)[-1]
        sch = _parse_proxy_scheme(legacy, scheme)
        return f"{sch}://{tail}"

    return legacy


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on", "y"):
        return True
    if raw in ("0", "false", "no", "off", "n"):
        return False
    return default


class TelegramAiohttpSession(AiohttpSession):
    """
    Для прямого подключения (без прокси) добавляет TCPConnector(family=AF_INET),
    чтобы обойти типичные таймауты на VPS с нерабочим IPv6.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        force_ipv4 = _env_bool("TELEGRAM_FORCE_IPV4", True)
        if force_ipv4 and self._proxy is None:
            self._connector_init["family"] = socket.AF_INET
            logging.info("TCP к Telegram: только IPv4 (TELEGRAM_FORCE_IPV4=1).")
        elif self._proxy is not None:
            logging.info("Запросы к Telegram идут через прокси (TELEGRAM_PROXY).")


def _make_session() -> AiohttpSession:
    timeout = _env_float("TELEGRAM_REQUEST_TIMEOUT", 90.0)
    user = os.getenv("TELEGRAM_PROXY_USER", "").strip()
    password = os.getenv("TELEGRAM_PROXY_PASSWORD", "").strip()

    proxy_url = _build_proxy_endpoint_url()
    if proxy_url:
        _validate_proxy_host_port(proxy_url)

    proxy: str | tuple[str, BasicAuth] | None = proxy_url
    if proxy_url and user:
        proxy = (proxy_url, BasicAuth(login=user, password=password))

    return TelegramAiohttpSession(proxy=proxy, timeout=timeout)


async def _wait_for_telegram(bot: Bot) -> None:
    retries = max(1, _env_int("TELEGRAM_CONNECT_RETRIES", 6))
    delay = max(1.0, _env_float("TELEGRAM_CONNECT_DELAY", 3.0))
    last_exc: BaseException | None = None
    for attempt in range(1, retries + 1):
        try:
            me = await bot.get_me()
            logging.info("Подключение к Telegram OK, бот: @%s", me.username or me.id)
            return
        except TelegramNetworkError as exc:
            last_exc = exc
            logging.warning(
                "Попытка %s/%s: не удалось связаться с Telegram: %s",
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                await asyncio.sleep(delay)
    logging.error(
        "Не удаётся достучаться до api.telegram.org. "
        "На части хостингов исходящий трафик к Telegram режется — нужен внешний "
        "SOCKS/HTTP-прокси (TELEGRAM_PROXY), другой сервер или согласование с "
        "провайдером. Проверьте также время системы (SSL) и outbound 443. "
        "Последняя ошибка: %s",
        last_exc,
    )
    raise SystemExit(2) from last_exc


def _load_dotenv() -> None:
    """На сервере (Beget VPS) секреты обычно лежат в файле .env рядом с bot.py."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except ImportError:
        logging.warning("Установите python-dotenv для загрузки .env")


async def main() -> None:
    _load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        logging.error("Задайте BOT_TOKEN в окружении.")
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    session = _make_session()
    bot = Bot(
        token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(payments_router)
    dp.include_router(stats_router)
    dp.include_router(blackjack_router)

    await stats_repo.init()
    await sub_repo.init()
    await _wait_for_telegram(bot)
    try:
        await dp.start_polling(bot)
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
