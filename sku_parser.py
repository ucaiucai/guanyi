#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 sellerMemo 解析 SKU 编码。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

SKU_PATTERN = re.compile(r"[A-Za-z0-9-]+")
_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"[0-9]")

# 数量 + 单位：两组、2个、×3
_QTY_UNITS = "组个件支套瓶盒袋只份台把条根块片粒颗包"
_QTY_PATTERN = re.compile(
    rf"(?:"
    rf"(\d+)\s*[{_QTY_UNITS}]"
    rf"|([两俩双])\s*[{_QTY_UNITS}]"
    rf"|([一二三四五六七八九十]+)\s*[{_QTY_UNITS}]"
    rf"|(?:×|\*|x)\s*(\d+)"
    rf")",
    re.IGNORECASE,
)

# 容量/重量规格（非商品编码）：66ml、133ml、500g、1L
_VOLUME_UNITS = (
    "ml",
    "l",
    "g",
    "kg",
    "mg",
    "oz",
    "mm",
    "cm",
    "m",
)
_VOLUME_SPEC = re.compile(
    rf"^\d+(?:\.\d+)?(?:{'|'.join(_VOLUME_UNITS)})$",
    re.IGNORECASE,
)

_CN_DIGIT = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "俩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "双": 2,
}


@dataclass(frozen=True)
class GiftSku:
    code: str
    qty: int = 1


def _is_volume_spec(token: str) -> bool:
    """数字 + 容量/重量单位，如 66ml、133ML、500g。"""
    return bool(_VOLUME_SPEC.match(token.strip()))


def _is_valid_sku_token(token: str, *, min_length: int) -> bool:
    """
    有效 SKU 片段：
    - 含 '-'（如 AFL-0011、YHG-ZP-001），或
    - 无 '-' 但同时含字母与数字（如 2406NCZ、WT26004）
    - 排除容量规格（如 66ml、133ml）
    """
    if len(token) < min_length:
        return False
    if _is_volume_spec(token):
        return False
    if "-" in token:
        return True
    return bool(_HAS_LETTER.search(token) and _HAS_DIGIT.search(token))


def parse_skus(
    memo: str,
    *,
    min_length: int = 2,
    allowlist_prefix: Sequence[str] | None = None,
) -> list[str]:
    """
    提取备注中的 SKU：字母/数字/横杠组成的连续片段。

    :param memo: sellerMemo 文本
    :param min_length: 最短有效长度（去首尾横杠后）
    :param allowlist_prefix: 非空时仅保留以任一前缀开头的 SKU
    """
    if not memo or not memo.strip():
        return []

    seen: set[str] = set()
    result: list[str] = []
    prefixes = tuple(allowlist_prefix) if allowlist_prefix else ()

    for raw in SKU_PATTERN.findall(memo):
        token = raw.strip("-")
        if not token or not _is_valid_sku_token(token, min_length=min_length):
            continue
        if prefixes and not any(token.startswith(p) for p in prefixes):
            continue
        key = token.upper()
        if key in seen:
            continue
        seen.add(key)
        result.append(token)

    return result


def _chinese_num_to_int(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in _CN_DIGIT:
        return _CN_DIGIT[text]
    if "十" in text:
        if text == "十":
            return 10
        parts = text.split("十", 1)
        high = _CN_DIGIT.get(parts[0], 1) if parts[0] else 1
        low = _CN_DIGIT.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return high * 10 + low
    total = 0
    for ch in text:
        if ch in _CN_DIGIT:
            total = total * 10 + _CN_DIGIT[ch]
        else:
            return None
    return total if total > 0 else None


def _qty_from_match(match: re.Match[str]) -> int:
    g1, g2_cn, g3_ch, g4_mul = match.groups()
    if g1:
        return max(1, int(g1))
    if g2_cn:
        return 2
    if g3_ch:
        n = _chinese_num_to_int(g3_ch)
        return max(1, n) if n else 1
    if g4_mul:
        return max(1, int(g4_mul))
    return 1


def qty_in_text_segment(segment: str) -> int:
    """从 SKU 前的备注片段解析数量，取最近一条匹配，默认 1。"""
    matches = list(_QTY_PATTERN.finditer(segment))
    if not matches:
        return 1
    return _qty_from_match(matches[-1])


def parse_gift_skus(
    memo: str,
    *,
    min_length: int = 2,
    allowlist_prefix: Sequence[str] | None = None,
    max_qty: int = 99,
) -> list[GiftSku]:
    """
    解析备注中的 SKU 及各自加赠数量。

    数量取自每个 SKU **之前** 的片段，如「加赠 两组 火石 2406NCZ」→ 2406NCZ ×2。
    """
    if not memo or not memo.strip():
        return []

    prefixes = tuple(allowlist_prefix) if allowlist_prefix else ()
    seen: set[str] = set()
    found: list[tuple[int, str]] = []

    for match in SKU_PATTERN.finditer(memo):
        token = match.group(0).strip("-")
        if not token or not _is_valid_sku_token(token, min_length=min_length):
            continue
        if prefixes and not any(token.startswith(p) for p in prefixes):
            continue
        key = token.upper()
        if key in seen:
            continue
        seen.add(key)
        found.append((match.start(), token))

    if not found:
        return []

    result: list[GiftSku] = []
    prev_end = 0
    for pos, token in found:
        qty = min(max_qty, max(1, qty_in_text_segment(memo[prev_end:pos])))
        result.append(GiftSku(code=token, qty=qty))
        prev_end = pos + len(token)

    return result


def filter_new_skus(skus: Iterable[str], existing_codes: Iterable[str]) -> list[str]:
    """返回不在 existing_codes 中的 SKU（大小写不敏感比较）。"""
    existing = {c.upper() for c in existing_codes if c}
    return [s for s in skus if s.upper() not in existing]


def filter_new_gift_skus(
    gifts: Iterable[GiftSku],
    existing_codes: Iterable[str],
) -> list[GiftSku]:
    """返回操作日志中尚未出现的新增记录对应的 GiftSku。"""
    existing = {c.upper() for c in existing_codes if c}
    return [g for g in gifts if g.code.upper() not in existing]
