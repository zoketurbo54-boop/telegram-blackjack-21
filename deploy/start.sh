#!/usr/bin/env bash
# Запуск бота (вызывается из systemd). Путь к проекту подставьте свой.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/USER/blackjack21}"
cd "$APP_DIR"

if [[ ! -d .venv ]]; then
  echo "Нет .venv в $APP_DIR — сначала: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

exec .venv/bin/python bot.py
