#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从管易订单操作日志判断是否已加赠商品。"""

from __future__ import annotations

import re
from typing import Any, Iterable

# 示例：新增商品 商品代码AFL-0011，规格名称；
ITEM_CODE_IN_MEMO = re.compile(r"商品代码\s*([A-Za-z0-9-]+)", re.IGNORECASE)


def parse_gift_skus_from_log(log_rows: Iterable[dict[str, Any]]) -> list[str]:
    """
    从操作日志中提取已通过「修改/新增商品」加入的商品编码。

    条件：action 为「修改」且 memo 含「新增商品」与「商品代码」。
    """
    seen: set[str] = set()
    result: list[str] = []

    for row in log_rows:
        if str(row.get("action") or "") != "修改":
            continue
        memo = str(row.get("memo") or "")
        if "新增商品" not in memo:
            continue
        for match in ITEM_CODE_IN_MEMO.finditer(memo):
            code = match.group(1).strip()
            if not code:
                continue
            key = code.upper()
            if key in seen:
                continue
            seen.add(key)
            result.append(code)

    return result
