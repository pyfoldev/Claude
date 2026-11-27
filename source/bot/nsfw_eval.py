"""Оценка качества фильтра 18+ по размеченным примерам: точность/полнота по порогам и рекомендация порога."""
from __future__ import annotations

from typing import Iterable


def confusion(safe: list[float], nsfw: list[float], threshold: float) -> dict:
    tp = sum(1 for s in nsfw if s >= threshold)
    fn = len(nsfw) - tp
    fp = sum(1 for s in safe if s >= threshold)
    tn = len(safe) - fp
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall}


def sweep(safe: list[float], nsfw: list[float], thresholds: Iterable[float]) -> list[dict]:
    return [{"threshold": t, **confusion(safe, nsfw, t)} for t in thresholds]


def recommend(safe: list[float], nsfw: list[float], min_precision: float = 0.95,
              thresholds: Iterable[float] = range(5, 100, 5)) -> dict | None:
    """Самый низкий порог (максимум полноты), при котором точность не ниже min_precision."""
    for row in sweep(safe, nsfw, sorted(thresholds)):
        if row["precision"] >= min_precision and row["tp"] > 0:
            return row
    return None
