#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析待审核订单时间，用于按下单时长过滤。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

# 优先用下单/创建时间
_TIME_FIELD_PRIORITY = (
    "createDate",
    "dealDate",
    "paytime",
    "planDeliveryDate",
)

_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
)


def parse_order_datetime(row: dict[str, Any]) -> datetime | None:
    """从列表行解析订单时间（本地时间，无时区）。"""
    for key in _TIME_FIELD_PRIORITY:
        val = row.get(key)
        if val is None or val == "":
            continue
        parsed = _parse_value(val)
        if parsed is not None:
            return parsed
    return None


def _parse_value(val: Any) -> datetime | None:
    if isinstance(val, (int, float)):
        return _from_timestamp(val)
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        if s.isdigit() or (s.replace(".", "", 1).isdigit() and s.count(".") <= 1):
            try:
                return _from_timestamp(float(s))
            except (ValueError, OSError):
                pass
        for fmt in _DATETIME_FORMATS:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def _from_timestamp(ts: float) -> datetime | None:
    try:
        if ts < 1e12:
            ts *= 1000
        return datetime.fromtimestamp(ts / 1000)
    except (ValueError, OSError):
        return None


def order_is_old_enough(row: dict[str, Any], min_age_minutes: int) -> bool:
    """
    订单是否已满 min_age_minutes（即创建时间早于 now - min_age）。

    无法解析时间时返回 True（仍处理，避免误跳过）。
    """
    if min_age_minutes <= 0:
        return True
    order_dt = parse_order_datetime(row)
    if order_dt is None:
        return True
    cutoff = datetime.now() - timedelta(minutes=min_age_minutes)
    return order_dt <= cutoff
