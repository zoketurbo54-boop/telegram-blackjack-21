# Загрузка бота на Beget VPS с нуля

Репозиторий: **https://github.com/zoketurbo54-boop/telegram-blackjack-21**

---

## Шаг 0. Что нужно заранее

1. **VPS на Beget** (не обычный хостинг для сайтов) — панель **Облако → VPS**, Ubuntu 22.04 или 24.04.
2. **Токен бота** от [@BotFather](https://t.me/BotFather).
3. **Ваш Telegram ID** (число) — узнать у [@userinfobot](https://t.me/userinfobot), для `/bot_stars`.
4. Данные SSH из письма Beget или панели: **IP**, **логин**, **пароль** (или SSH-ключ).

На VPS **не нужен VPN**, если `curl` до `api.telegram.org` проходит.

---

## Шаг 1. Подключиться к серверу по SSH

### Windows (PowerShell или PuTTY)

```powershell
ssh ЛОГИН@IP_СЕРВЕРА
```

Пример: `ssh root@123.45.67.89` — подставьте свои данные из панели Beget.

При первом входе спросит пароль — вставьте из письма Beget (символы при вставке в SSH часто не видны — это нормально).

---

## Шаг 2. Установить Python и Git

На сервере (после входа по SSH):

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
python3 --version
```

Нужно Python **3.10+** (на Ubuntu 22/24 обычно 3.10–3.12).

---

## Шаг 3. Скачать проект с GitHub

```bash
cd ~
git clone https://github.com/zoketurbo54-boop/telegram-blackjack-21.git
cd telegram-blackjack-21
ls
```

Должны быть файлы: `bot.py`, `requirements.txt`, `deploy/`, и т.д.

---

## Шаг 4. Виртуальное окружение и зависимости

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

Ожидайте 1–3 минуты, пока установится aiogram и остальное.

---

## Шаг 5. Файл с секретами `.env`

```bash
cp .env.example .env
nano .env
```

В редакторе **nano**:

- Стрелки — перемещение.
- Впишите токен и ID (без кавычек лишних пробелов):

```env
BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_ADMIN_ID=123456789
TELEGRAM_FORCE_IPV4=1
```

Сохранить: **Ctrl+O**, Enter. Выход: **Ctrl+X**.

Прокси на Beget VPS обычно **не нужен** — строки `TELEGRAM_PROXY` оставьте закомментированными.

---

## Шаг 6. Проверка запуска вручную

```bash
cd ~/telegram-blackjack-21
.venv/bin/python bot.py
```

В логах должно появиться что-то вроде:

- `База статистики готова`
- `Подключение к Telegram OK, бот: @имя_бота`

В Telegram откройте бота → `/start`.

**Остановить тест:** `Ctrl+C`.

Если ошибка `Cannot connect to api.telegram.org` — на сервере:

```bash
curl -I --connect-timeout 5 https://api.telegram.org
```

Если не отвечает — напишите в поддержку Beget или добавьте прокси в `.env`.

---

## Шаг 7. Автозапуск (бот всегда включён)

Узнайте имя пользователя Linux:

```bash
whoami
```

Допустим, ответ `root` или `ubuntu`. Подставьте в команды ниже вместо `USER`.

```bash
cd ~/telegram-blackjack-21
chmod +x deploy/start.sh
nano deploy/blackjack21.service
```

Замените **все** вхождения:

| Было | Стало (пример) |
|------|----------------|
| `YOUR_LINUX_USER` | `root` |
| `/home/YOUR_LINUX_USER/blackjack21` | `/root/telegram-blackjack-21` |

Если `whoami` выдал не `root`, путь будет `/home/ИМЯ/telegram-blackjack-21`.

Установка службы:

```bash
sudo cp deploy/blackjack21.service /etc/systemd/system/blackjack21.service
sudo systemctl daemon-reload
sudo systemctl enable blackjack21
sudo systemctl start blackjack21
sudo systemctl status blackjack21
```

Должно быть: **`Active: active (running)`**.

Логи в реальном времени:

```bash
journalctl -u blackjack21 -f
```

Выход из логов: **Ctrl+C**.

---

## Шаг 8. На своём компьютере

**Выключите бота на ПК**, если он там ещё запущен — с одним токеном должен работать **только сервер**, иначе будут конфликты.

---

## Обновление бота после изменений на GitHub

```bash
cd ~/telegram-blackjack-21
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart blackjack21
sudo systemctl status blackjack21
```

---

## Полезные команды

| Действие | Команда |
|----------|---------|
| Перезапуск | `sudo systemctl restart blackjack21` |
| Остановка | `sudo systemctl stop blackjack21` |
| Статус | `sudo systemctl status blackjack21` |
| Логи | `journalctl -u blackjack21 -n 50` |
| Бэкап БД | `cp ~/telegram-blackjack-21/stats.db ~/stats.db.bak` |

---

## Альтернатива без Git (SFTP)

1. Скачайте ZIP с GitHub: **Code → Download ZIP**.
2. В панели Beget откройте **Файловый менеджер** VPS или WinSCP.
3. Загрузите распакованную папку в `~/telegram-blackjack-21`.
4. Дальше с **шага 4** (venv, `.env`, systemd).

Не загружайте папку `.venv` с Windows — на сервере создайте venv заново.

---

## Безопасность

- Файл `.env` только на сервере, не в GitHub.
- Не публикуйте токен бота в чатах и скриншотах.
