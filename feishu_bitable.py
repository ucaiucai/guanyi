#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将管易加赠执行结果写入飞书多维表格。"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# 默认：wiki 订单记录表 https://doubleline.feishu.cn/wiki/TosvwRZ7lifUu9kIuKgcjuNqnTw
DEFAULT_WIKI_URL = "https://doubleline.feishu.cn/wiki/TosvwRZ7lifUu9kIuKgcjuNqnTw"
DEFAULT_BASE_TOKEN = "FCAjbZmc2a31DSspNfccp3gWnVg"
DEFAULT_TABLE_ID = "tblhIMTiGuxeF52t"
DEFAULT_VIEW_ID = "vewjs9j8KZ"


def build_feishu_table_url(feishu_cfg: dict[str, Any]) -> str | None:
    """
    生成飞书多维表在 Wiki 中的打开链接。
    优先 table_url；否则由 wiki_url + table_id + view_id 拼接。
    """
    explicit = (feishu_cfg.get("table_url") or "").strip()
    if explicit:
        return explicit

    wiki = (feishu_cfg.get("wiki_url") or DEFAULT_WIKI_URL).strip()
    table_id = (feishu_cfg.get("table_id") or DEFAULT_TABLE_ID).strip()
    if not wiki:
        return None
    if not table_id:
        return wiki

    sep = "&" if "?" in wiki else "?"
    url = f"{wiki}{sep}table={table_id}"
    view_id = (feishu_cfg.get("view_id") or DEFAULT_VIEW_ID).strip()
    if view_id:
        url = f"{url}&view={view_id}"
    return url

FIELD_ORDER = [
    "订单号",
    "备注",
    "加赠商品编码",
    "加赠商品名称",
    "加赠商品规格",
    "审核状态",
    "审核时间",
]

# lark-cli 调用身份：写入需协作者「可编辑」权限（链接只读不够）
VALID_AS = frozenset({"user", "bot"})
DEFAULT_AS = "user"

_PERM_HINT = (
    "表已改为「链接只读、仅协作者可写」。请把执行 lark-cli 的身份（config.feishu.as）"
    "加为该多维表格协作者且权限为「可编辑」：user=本机 auth login 的用户；"
    "bot=飞书应用机器人（需用 open_id 添加协作者）。"
)

SKU_ACTION_STATUSES = frozenset(
    {
        "added",
        "skipped_already_exists",
        "dry_run_would_add",
        "product_not_found",
        "failed",
        "ambiguous_product",
    }
)


def _parse_product_name(message: str) -> str:
    """从 '商品名 (itemCode=XXX)' 提取名称。"""
    if not message:
        return ""
    if " (itemCode=" in message:
        return message.split(" (itemCode=", 1)[0].strip()
    return message.strip()


def _audit_status(
    action_status: str,
    *,
    dry_run: bool,
    order_approved: bool,
    approve_failed: bool,
) -> str:
    if dry_run:
        return "待审核"
    if action_status in ("product_not_found", "failed", "ambiguous_product"):
        return "已拒绝"
    if action_status == "skipped_already_exists":
        return "已通过" if order_approved else "待审核"
    if action_status == "added":
        if order_approved:
            return "已通过"
        if approve_failed:
            return "待审核"
        return "待审核"
    if action_status == "dry_run_would_add":
        return "待审核"
    return "待审核"


def build_bitable_rows(
    order_results: list[Any],
    *,
    dry_run: bool,
) -> list[list[Any]]:
    """从 OrderResult 列表生成多维表 rows（与 FIELD_ORDER 列序一致）。"""
    rows: list[list[Any]] = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for order in order_results:
        platform_code = getattr(order, "platform_code", "") or getattr(order, "order_id", "")
        seller_memo = getattr(order, "seller_memo", "") or ""
        actions = getattr(order, "actions", [])

        order_approved = any(a.status == "approved" for a in actions)
        approve_failed = any(a.status == "approve_failed" for a in actions)

        for action in actions:
            if action.status not in SKU_ACTION_STATUSES:
                continue

            audit = _audit_status(
                action.status,
                dry_run=dry_run,
                order_approved=order_approved,
                approve_failed=approve_failed,
            )
            audit_time = now_str if audit == "已通过" else None
            spec = action.message or action.status
            if approve_failed and action.status == "added":
                spec = f"{spec}；审核提交失败"

            rows.append(
                [
                    platform_code,
                    seller_memo,
                    action.sku,
                    _parse_product_name(action.message),
                    spec,
                    audit,
                    audit_time,
                ]
            )

    return rows


def sync_to_feishu_bitable(
    order_results: list[Any],
    feishu_cfg: dict[str, Any],
    *,
    dry_run: bool,
) -> int:
    """
    批量写入飞书多维表。返回写入行数；无数据时返回 0。
    """
    if not feishu_cfg.get("enabled", True):
        logger.info("飞书同步已关闭 (feishu.enabled=false)")
        return 0

    if dry_run and not feishu_cfg.get("sync_on_dry_run", False):
        logger.info("试运行不同步飞书（feishu.sync_on_dry_run=false）")
        return 0

    rows = build_bitable_rows(order_results, dry_run=dry_run)
    if not rows:
        logger.info("无需要同步的订单明细，跳过飞书写入")
        return 0

    base_token = feishu_cfg.get("base_token") or DEFAULT_BASE_TOKEN
    table_id = feishu_cfg.get("table_id") or DEFAULT_TABLE_ID
    batch_size = int(feishu_cfg.get("batch_size", 200))
    as_identity = (feishu_cfg.get("as") or DEFAULT_AS).strip().lower()
    if as_identity not in VALID_AS:
        raise ValueError(f"feishu.as 须为 user 或 bot，当前: {as_identity!r}")

    written = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        payload = {"fields": FIELD_ORDER, "rows": chunk}
        cmd = [
            "lark-cli",
            "base",
            "+record-batch-create",
            "--as",
            as_identity,
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps(payload, ensure_ascii=False),
        ]
        logger.debug("飞书 batch-create: %s 行", len(chunk))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            if any(
                x in err
                for x in ("permission", "Permission", "230013", "1061002", "无权限", "forbidden")
            ):
                raise RuntimeError(f"飞书写入失败（权限）: {err}\n{_PERM_HINT}")
            raise RuntimeError(f"飞书写入失败: {err}")

        try:
            out = json.loads(result.stdout)
        except json.JSONDecode(json.JSONDecodeError, ValueError):
            out = {}

        if isinstance(out, dict) and out.get("ok") is False:
            raise RuntimeError(f"飞书写入失败: {out}")

        ids = []
        if isinstance(out, dict):
            data = out.get("data") or {}
            ids = data.get("record_id_list") or []
        written += len(ids) if ids else len(chunk)
        logger.info("已写入飞书 %s 条记录", len(ids) if ids else len(chunk))

    return written
