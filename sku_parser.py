#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 sellerMemo 解析 SKU 编码。"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

SKU_PATTERN = re.compile(r"[A-Za-z0-9-]+")


def parse_skus(
    memo: str,
    *,
    min_length: int = 2,
    allowlist_prefix: Sequence[str] | None = None,
) -> list[str]:
    """
    提取备注中的 SKU：字母/数字/横杠连续片段，且必须含 '-'。

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
        if not token or "-" not in token:
            continue
        if len(token) < min_length:
            continue
        if prefixes and not any(token.startswith(p) for p in prefixes):
            continue
        key = token.upper()
        if key in seen:
            continue
        seen.add(key)
        result.append(token)

    return result


def filter_new_skus(skus: Iterable[str], existing_codes: Iterable[str]) -> list[str]:
    """返回不在 existing_codes 中的 SKU（大小写不敏感比较）。"""
    existing = {c.upper() for c in existing_codes if c}
    return [s for s in skus if s.upper() not in existing]
