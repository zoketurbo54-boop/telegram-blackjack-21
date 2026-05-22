"""
Колода, подсчёт очков и ссылки на изображения карт (deckofcardsapi.com).

Код карты (англ.) = ранг + масть, без разделителя:
  - Ранг: A (туз), 2–9, 10, J (валет), Q (дама), K (король)
  - Масть: S (пики spades), H (червы hearts), D (бубны diamonds), C (трефы clubs)

Примеры кодов → URL PNG:
  AS  → https://deckofcardsapi.com/static/img/AS.png   (туз пик)
  2H  → https://deckofcardsapi.com/static/img/2H.png   (двойка червей)
  10D → https://deckofcardsapi.com/static/img/10D.png  (десятка бубен)
  KC  → https://deckofcardsapi.com/static/img/KC.png   (король треф)

Рубашка колоды на том же CDN:
  https://deckofcardsapi.com/static/img/back.png
"""
from __future__ import annotations

import random
from typing import Final

# Базовый URL статики deckofcardsapi (не требует API-ключа).
CARDS_CDN_BASE: Final[str] = "https://deckofcardsapi.com/static/img"

RANKS: Final[tuple[str, ...]] = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS: Final[tuple[str, ...]] = ("S", "H", "D", "C")


def build_full_deck() -> list[str]:
    """Возвращает новую колоду из 52 уникальных кодов карт."""
    return [f"{rank}{suit}" for rank in RANKS for suit in SUITS]


def shuffle_deck(deck: list[str]) -> None:
    """Перемешивает колоду на месте (random.shuffle)."""
    random.shuffle(deck)


def card_png_url(card_code: str) -> str:
    """Преобразует код карты (например, '10H') в прямую ссылку на PNG."""
    return f"{CARDS_CDN_BASE}/{card_code}.png"


def back_png_url() -> str:
    """Ссылка на изображение рубашки."""
    return f"{CARDS_CDN_BASE}/back.png"


def rank_of(card_code: str) -> str:
    """Извлекает ранг из кода ('10D' → '10', 'AS' → 'A')."""
    if card_code.startswith("10"):
        return "10"
    return card_code[0]


def hand_total(cards: list[str]) -> int:
    """
    Сумма очков по правилам «21»:
    2–10 по номиналу, J/Q/K = 10, туз = 11, пока сумма > 21 — тузы по одному считаются как 1.
    """
    total = 0
    aces = 0
    for code in cards:
        r = rank_of(code)
        if r == "A":
            aces += 1
            total += 11
        elif r in ("J", "Q", "K") or r == "10":
            total += 10
        else:
            total += int(r)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def is_bust(cards: list[str]) -> bool:
    return hand_total(cards) > 21
