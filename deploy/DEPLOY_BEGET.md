# Запуск бота «21» на Beget (VPS)

## Важно: какой тариф нужен

| Тариф | Подойдёт? |
|-------|-----------|
| **VPS / Cloud** (Ubuntu) | ✅ Да — бот работает 24/7 через `systemd` |
| Обычный **виртуальный хостинг** (сайты) | ❌ Нет — нельзя держать постоянный процесс `python bot.py` |

В панели Beget: **Облако → VPS** (или Cloud). Минимум: 1 vCPU, 1 GB RAM, Ubuntu 22.04 / 24.04.

На VPS из Европы обычно **доступен** `api.telegram.org` без VPN — прокси в `.env` чаще не нужен.

---

## 1. Подготовка на компьютере

Залейте проект на GitHub (без `.env` и без `.venv` — они в `.gitignore`).

Или упакуйте папку (без `.venv`) и загрузите на сервер через SFTP / файловый менеджер Beget.

---

## 2. SSH на VPS

В панели Beget: **Облако → ваш VPS → SSH** (логин, IP, пароль из письма support@beget.ru).

Windows: PuTTY или `ssh user@IP`.

```bash
ssh USER@SERVER_IP
```

---

## 3. Установка проекта

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

mkdir -p ~/blackjack21
cd ~/blackjack21
```

**Вариант A — git:**

```bash
git clone https://github.com/ВАШ_ЛОГИН/ВАШ_РЕПО.git .
```

**Вариант B — уже залили файлы по SFTP** — просто `cd ~/blackjack21`.

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env
```

В `.env` обязательно:

```env
BOT_TOKEN=токен_от_BotFather
TELEGRAM_ADMIN_ID=ваш_числовой_id
TELEGRAM_FORCE_IPV4=1
```

Проверка вручную:

```bash
cd ~/blackjack21
.venv/bin/python bot.py
```

В Telegram: `/start`. Остановка: `Ctrl+C`.

Проверка связи с Telegram:

```bash
curl -I --connect-timeout 5 https://api.telegram.org
```

---

## 4. Автозапуск (systemd)

```bash
chmod +x deploy/start.sh
nano deploy/blackjack21.service
```

Замените `YOUR_LINUX_USER` и пути на свои (например `root` или пользователь из панели Beget).

```bash
sudo cp deploy/blackjack21.service /etc/systemd/system/blackjack21.service
sudo systemctl daemon-reload
sudo systemctl enable blackjack21
sudo systemctl start blackjack21
sudo systemctl status blackjack21
```

Логи:

```bash
journalctl -u blackjack21 -f
```

После обновления кода:

```bash
cd ~/blackjack21
git pull   # если используете git
.venv/bin/pip install -r requirements.txt
sudo systemctl restart blackjack21
```

---

## 5. База и звёзды

- Файл **`stats.db`** создаётся сам в папке бота (статистика + подписки). Делайте бэкап: `cp stats.db stats.db.bak`.
- Звёзды от подписок приходят на **баланс бота** — смотрите в @BotFather (Monetization) или команда `/bot_stars` (нужен `TELEGRAM_ADMIN_ID`).

---

## 6. Частые проблемы на Beget

| Проблема | Решение |
|----------|---------|
| `Cannot connect to api.telegram.org` | Проверить `curl`; при блокировке — `TELEGRAM_PROXY` в `.env` |
| Бот не стартует после reboot | `sudo systemctl enable blackjack21` |
| `BOT_TOKEN` пустой | Файл `.env` в той же папке, что `bot.py` |
| Два экземпляра бота | Остановить локальный ПК-бот; на сервере только один `systemd` сервис |

---

## 7. Безопасность

- Не коммитьте `.env` в git.
- Токен бота только в `.env` на сервере.
- SSH по ключу вместо пароля — в панели Beget можно добавить ключ.
