#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钉钉自定义机器人通知（加签）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests

from feishu_bitable import SKU_ACTION_STATUSES, _audit_status, build_feishu_table_url

logger = logging.getLogger(__name__)

# 写入钉钉「处理明细」的 SKU / 审核相关 action
# 仅对「SKU 动作」出明细行；整单审核结果由订单 actions 汇总得出
DETAIL_ACTION_STATUSES = SKU_ACTION_STATUSES
DETAIL_LINE_LIMIT = 30


def _signed_webhook(webhook_url: str, secret: str) -> str:
    """钉钉加签：timestamp + sign 拼到 URL。"""
    timestamp = str(round(time.time() * 1000))
    secret_str = secret.strip()
    string_to_sign = f"{timestamp}\n{secret_str}"
    sign = base64.b64encode(
        hmac.new(
            secret_str.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    sign_encoded = urllib.parse.quote_plus(sign)
    sep = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{sep}timestamp={timestamp}&sign={sign_encoded}"


def _order_label(order: Any) -> str:
    return order.platform_code or order.code or order.order_id


def _audit_result_label(order: Any, action: Any, *, dry_run: bool) -> str:
    """与飞书多维表审核状态列一致的中文结果。"""
    order_approved = any(a.status == "approved" for a in order.actions)
    approve_failed = any(a.status == "approve_failed" for a in order.actions)
    if action.status in SKU_ACTION_STATUSES:
        return _audit_status(
            action.status,
            dry_run=dry_run,
            order_approved=order_approved,
            approve_failed=approve_failed,
        )
    return action.status


def _order_audit_label(order: Any, *, dry_run: bool) -> str:
    """按整单汇总审核结果：拒绝 > 待审核 > 通过。"""
    actions = list(getattr(order, "actions", []) or [])
    if not actions:
        return "待审核"

    order_approved = any(a.status == "approved" for a in actions)
    approve_failed = any(a.status == "approve_failed" for a in actions)

    sku_actions = [a for a in actions if a.status in SKU_ACTION_STATUSES]
    if not sku_actions:
        # 非 SKU 动作不出现在「处理明细」里；这里给个兜底
        return "已通过" if order_approved else "待审核"

    labels = [
        _audit_status(
            a.status,
            dry_run=dry_run,
            order_approved=order_approved,
            approve_failed=approve_failed,
        )
        for a in sku_actions
    ]
    if "已拒绝" in labels:
        return "已拒绝"
    if "待审核" in labels:
        return "待审核"
    if order_approved:
        return "已通过"
    return "待审核"


def _build_detail_lines(order_results: list[Any], *, dry_run: bool) -> list[str]:
    lines: list[str] = []
    for order in order_results:
        if all(a.status == "skipped_no_sku" for a in order.actions):
            continue
        label = _order_label(order)
        sku_set: set[str] = set()
        for action in order.actions:
            if action.status not in DETAIL_ACTION_STATUSES:
                continue
            if action.sku:
                sku_set.add(action.sku)
        if not sku_set:
            continue
        sku_text = ", ".join(sorted(sku_set))
        audit = _order_audit_label(order, dry_run=dry_run)
        lines.append(f"- {label} | {sku_text} | {audit}")
    return lines


def build_summary_markdown(
    summary: Any,
    *,
    dry_run: bool,
    log_path: Path | None = None,
    error_msg: str | None = None,
    feishu_cfg: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """返回 (title, markdown_text)。"""
    mode = "试运行" if dry_run else "正式执行"
    title = f"管易自动加赠品 · {mode}"

    lines = [
        f"### 管易自动加赠品 · {mode}",
        "",
        f"- 扫描订单: {summary.orders_scanned}",
        f"- 含可解析 SKU: {summary.orders_with_skus}",
        f"- 加赠成功: {summary.added}",
        f"- 已存在跳过: {summary.skipped_exists}",
        f"- 无 SKU 跳过: {summary.skipped_no_sku}",
        f"- 提交审核: {summary.approved}",
        f"- 半小时内跳过: {summary.skipped_too_recent}",
        f"- 失败/未找到: {summary.failed}",
    ]

    detail_lines = _build_detail_lines(
        getattr(summary, "order_results", []),
        dry_run=dry_run,
    )
    if detail_lines:
        lines.extend(["", "#### 处理明细"])
        lines.extend(detail_lines[:DETAIL_LINE_LIMIT])
        if len(detail_lines) > DETAIL_LINE_LIMIT:
            lines.append(f"- …共 {len(detail_lines)} 条")

    if error_msg:
        lines.extend(["", f"**异常中止**: {error_msg}"])

    fail_lines: list[str] = []
    for order in getattr(summary, "order_results", []):
        for action in order.actions:
            if action.status in (
                "failed",
                "product_not_found",
                "ambiguous_product",
                "approve_failed",
            ):
                label = order.platform_code or order.code or order.order_id
                fail_lines.append(
                    f"- {label} | {action.sku or '-'}: {action.status} — {action.message[:80]}"
                )
    if fail_lines:
        lines.extend(["", "#### 失败明细", *fail_lines[:15]])
        if len(fail_lines) > 15:
            lines.append(f"- …共 {len(fail_lines)} 条")

    table_url = build_feishu_table_url(feishu_cfg or {})
    if table_url:
        lines.extend(["", f"[所有明细见飞书表格]({table_url})"])

    return title, "\n".join(lines)


def send_dingtalk_markdown(
    webhook_url: str,
    secret: str,
    title: str,
    text: str,
) -> None:
    url = _signed_webhook(webhook_url, secret)
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("errcode") != 0:
        raise RuntimeError(f"钉钉发送失败: {body}")


def notify_run_result(
    summary: Any | None,
    dingtalk_cfg: dict[str, Any],
    *,
    dry_run: bool,
    log_path: Path | None = None,
    error_msg: str | None = None,
    feishu_cfg: dict[str, Any] | None = None,
) -> bool:
    """
    发送钉钉通知。返回是否发送成功。
    """
    if not dingtalk_cfg.get("enabled", True):
        logger.info("钉钉通知已关闭 (dingtalk.enabled=false)")
        return False

    if dry_run and not dingtalk_cfg.get("notify_on_dry_run", False):
        logger.info("试运行不发送钉钉 (dingtalk.notify_on_dry_run=false)")
        return False

    webhook = dingtalk_cfg.get("webhook_url") or dingtalk_cfg.get("webhook")
    secret = dingtalk_cfg.get("secret")
    if not webhook or not secret:
        logger.warning("未配置 dingtalk.webhook_url 或 dingtalk.secret，跳过通知")
        return False

    feishu = feishu_cfg or {}
    table_url = build_feishu_table_url(feishu)

    if summary is None:
        title = "管易自动加赠品 · 异常中止"
        text = f"### 管易自动加赠品\n\n**异常**: {error_msg or '未知错误'}"
        if table_url:
            text += f"\n\n[所有明细见飞书表格]({table_url})"
    else:
        detail_lines = _build_detail_lines(
            getattr(summary, "order_results", []),
            dry_run=dry_run,
        )
        if not detail_lines and not error_msg:
            logger.info("无处理明细，跳过钉钉通知")
            return False

        title, text = build_summary_markdown(
            summary,
            dry_run=dry_run,
            log_path=log_path,
            error_msg=error_msg,
            feishu_cfg=feishu,
        )

    try:
        send_dingtalk_markdown(str(webhook), str(secret), title, text)
        logger.info("钉钉通知已发送")
        return True
    except Exception as exc:
        logger.error("钉钉通知失败: %s", exc)
        return False


if __name__ == "__main__":
    notify_run_result(None, {
        "enabled": True,
        "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=2ae8de40c6aaf6116b223a5d97ffaaa48432e60f1bf8ec52edd3e43fc49cc9bb",
        "secret": "SECbf67348b27d7138028337ee0b68a15f6b0cec47d5fe513f1cb3f0106dcebd2d2",
        "notify_on_dry_run": False
    }, dry_run=True)