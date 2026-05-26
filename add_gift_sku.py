#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管易待审核订单：根据 sellerMemo 自动加赠 SKU。

用法:
  python add_gift_sku.py
  python add_gift_sku.py --dry-run
  python add_gift_sku.py --order-id 6952978354922788022
  python add_gift_sku.py --config /path/to/config.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dingtalk_notify import notify_run_result
from feishu_bitable import build_feishu_table_url, sync_to_feishu_bitable
from guanyi_auth import create_client_from_config
from guanyi_client import GuanyiApiError
from order_time import order_is_old_enough, parse_order_datetime
from sku_parser import filter_new_gift_skus, parse_gift_skus

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"
LOGS_DIR = Path(__file__).parent / "logs"


@dataclass
class SkuAction:
    sku: str
    status: str
    message: str = ""


def order_ref_matches(row: dict[str, Any], order_ref: str) -> bool:
    """按平台订单号 platformCode 匹配；兼容 uniqueTid、管易内部 id、系统单号 code。"""
    ref = order_ref.strip()
    if not ref:
        return False
    for key in ("platformCode", "uniqueTid", "id", "code"):
        val = row.get(key)
        if val is not None and str(val) == ref:
            return True
    return False


@dataclass
class OrderResult:
    order_id: str
    platform_code: str = ""
    code: str = ""
    seller_memo: str = ""
    parsed_gifts: list[dict[str, Any]] = field(default_factory=list)
    actions: list[SkuAction] = field(default_factory=list)


def _format_parsed_gifts(gifts: list[Any]) -> str:
    """如 AFL-0011×1, YHG-ZP-001×2"""
    parts = []
    for g in gifts:
        code = g.code if hasattr(g, "code") else g["code"]
        qty = g.qty if hasattr(g, "qty") else g.get("qty", 1)
        parts.append(f"{code}×{qty}" if qty > 1 else code)
    return ", ".join(parts)


@dataclass
class RunSummary:
    orders_scanned: int = 0
    orders_with_skus: int = 0
    added: int = 0
    skipped_exists: int = 0
    skipped_no_sku: int = 0
    failed: int = 0
    approved: int = 0
    skipped_too_recent: int = 0
    order_results: list[OrderResult] = field(default_factory=list)


def _sku_actions_for_skus(result: OrderResult, skus: list[str]) -> list[SkuAction]:
    sku_set = set(skus)
    return [a for a in result.actions if a.sku in sku_set]


def should_approve_order(result: OrderResult, skus: list[str], cfg: dict[str, Any]) -> bool:
    """加赠流程结束后是否提交审核。"""
    if not cfg.get("auto_approve", True):
        return False
    sku_actions = _sku_actions_for_skus(result, skus)
    if not sku_actions:
        return False
    bad = {"failed", "product_not_found", "ambiguous_product"}
    if any(a.status in bad for a in sku_actions):
        return False
    if any(a.status == "added" for a in sku_actions):
        return True
    if cfg.get("approve_when_ready", True):
        ok = {"added", "skipped_already_exists"}
        return all(a.status in ok for a in sku_actions)
    return False


def try_approve_order(
    client: GuanyiClient,
    result: OrderResult,
    order_id: str,
    skus: list[str],
    cfg: dict[str, Any],
    *,
    dry_run: bool,
    platform_code: str,
    code: str,
) -> None:
    if not should_approve_order(result, skus, cfg):
        return

    label = platform_code or code or order_id
    if dry_run:
        result.actions.append(
            SkuAction("", "dry_run_would_approve", "加赠完成后将提交审核")
        )
        return

    try:
        body = client.approve_order(order_id)
        msg = ""
        if isinstance(body, dict):
            msg = str(body.get("message") or body.get("msg") or "审核已提交")
        result.actions.append(SkuAction("", "approved", msg))
        logger.info("订单 %s 已提交审核", label)
    except GuanyiApiError as exc:
        result.actions.append(SkuAction("", "approve_failed", str(exc)))
        logger.error("订单 %s 审核失败: %s", label, exc)


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"配置文件不存在: {path}\n请复制 config.example.json 为 config.json 并填写 guanyi 账号"
        )
    with path.open(encoding="utf-8") as f:
        cfg = json.load(f)
    guanyi = cfg.get("guanyi") or {}
    if not guanyi.get("username") or not guanyi.get("password"):
        raise ValueError("请在 config.json 的 guanyi 中配置 username 与 password")
    return cfg


def find_product_exact(
    client: GuanyiClient,
    sku: str,
    warehouse_id: str,
) -> dict[str, Any] | None:
    result = client.search_product(sku, warehouse_id=warehouse_id)
    rows = result.get("rows") or []
    if not rows:
        return None

    for row in rows:
        if str(row.get("itemCode", "")).upper() == sku.upper():
            return row

    # 模糊搜索仅一条时采用
    if len(rows) == 1:
        return rows[0]

    codes = [r.get("itemCode") for r in rows]
    raise GuanyiApiError(
        f"商品匹配歧义 sku={sku}，候选 itemCode: {codes[:5]}",
        payload=rows,
    )


def process_order(
    client: GuanyiClient,
    row: dict[str, Any],
    cfg: dict[str, Any],
    *,
    dry_run: bool,
) -> OrderResult:
    order_id = str(row["id"])
    platform_code = str(row.get("platformCode") or "")
    code = str(row.get("code") or "")
    seller_memo = str(row.get("sellerMemo") or "")
    warehouse_id = str(row.get("warehouseId") or cfg["warehouse_id"])

    allowlist = cfg.get("sku_allowlist_prefix") or []
    if allowlist == []:
        allowlist = None

    max_qty = int(cfg.get("gift_max_qty", 99))
    gift_skus = parse_gift_skus(
        seller_memo,
        min_length=int(cfg.get("sku_min_length", 2)),
        allowlist_prefix=allowlist,
        max_qty=max_qty,
    )
    sku_codes = [g.code for g in gift_skus]

    result = OrderResult(
        order_id=order_id,
        platform_code=platform_code,
        code=code,
        seller_memo=seller_memo,
        parsed_gifts=[{"code": g.code, "qty": g.qty} for g in gift_skus],
    )

    if not gift_skus:
        result.actions.append(
            SkuAction("", "skipped_no_sku", "备注未解析到 SKU")
        )
        return result

    log_rows = int(cfg.get("log_query_rows", 50))
    log_added_skus = client.fetch_log_added_skus(order_id, rows_per_page=log_rows)
    to_add = filter_new_gift_skus(gift_skus, log_added_skus)
    to_add_codes = {g.code.upper() for g in to_add}
    label = platform_code or code or order_id
    logger.info(
        "订单 %s 解析 %d 个加赠 SKU: %s",
        label,
        len(gift_skus),
        _format_parsed_gifts(gift_skus),
    )
    if log_added_skus:
        logger.debug("订单 %s 日志已加赠: %s", label, log_added_skus)

    for gift in gift_skus:
        sku = gift.code
        if sku.upper() not in to_add_codes:
            result.actions.append(
                SkuAction(sku, "skipped_already_exists", "操作日志已有新增商品记录")
            )
            continue

        qty_label = f"×{gift.qty}" if gift.qty > 1 else ""

        if dry_run:
            result.actions.append(
                SkuAction(
                    sku,
                    "dry_run_would_add",
                    f"将加赠 {gift.qty} 件 warehouse={warehouse_id}",
                )
            )
            continue

        try:
            product = find_product_exact(client, sku, warehouse_id)
            if product is None:
                result.actions.append(
                    SkuAction(sku, "product_not_found", "商品库未找到")
                )
                continue

            client.get_trade_detail(order_id)
            client.update_order_detail(order_id, product, qty=gift.qty)
            log_added_skus.append(sku)
            to_add_codes.discard(sku.upper())
            result.actions.append(
                SkuAction(
                    sku,
                    "added",
                    f"{qty_label} {product.get('itemName', '')} "
                    f"(itemCode={product.get('itemCode')}, qty={gift.qty})",
                )
            )
            label = platform_code or code or order_id
            logger.info("订单 %s 已加赠 %s %s", label, sku, qty_label or "×1")
        except GuanyiApiError as exc:
            status = "ambiguous_product" if "歧义" in str(exc) else "failed"
            result.actions.append(SkuAction(sku, status, str(exc)))
            label = platform_code or code or order_id
            logger.error("订单 %s SKU %s 失败: %s", label, sku, exc)

    try_approve_order(
        client,
        result,
        order_id,
        sku_codes,
        cfg,
        dry_run=dry_run,
        platform_code=platform_code,
        code=code,
    )
    return result


def summarize(run: RunSummary) -> None:
    for order in run.order_results:
        for action in order.actions:
            if action.status == "added":
                run.added += 1
            elif action.status == "skipped_already_exists":
                run.skipped_exists += 1
            elif action.status == "skipped_no_sku":
                run.skipped_no_sku += 1
            elif action.status in ("failed", "product_not_found", "ambiguous_product"):
                run.failed += 1
            elif action.status in ("approved", "dry_run_would_approve"):
                run.approved += 1
            elif action.status == "approve_failed":
                run.failed += 1


def print_summary(run: RunSummary, *, dry_run: bool) -> None:
    mode = "【试运行】" if dry_run else "【正式执行】"
    print(f"\n{mode} 汇总")
    print(f"  扫描订单: {run.orders_scanned}")
    print(f"  含可解析 SKU: {run.orders_with_skus}")
    print(f"  加赠成功: {run.added}")
    print(f"  已存在跳过: {run.skipped_exists}")
    print(f"  无 SKU 跳过: {run.skipped_no_sku}")
    print(f"  提交审核: {run.approved}")
    print(f"  半小时内跳过: {run.skipped_too_recent}")
    print(f"  失败/未找到: {run.failed}")
    print("\n明细:")
    for order in run.order_results:
        if all(a.status == "skipped_no_sku" for a in order.actions):
            continue
        memo_preview = order.seller_memo[:80] + ("…" if len(order.seller_memo) > 80 else "")
        order_label = order.platform_code or order.code or order.order_id
        gifts_line = _format_parsed_gifts(order.parsed_gifts)
        print(f"  订单 {order_label} | 加赠 SKU: {gifts_line} | 备注: {memo_preview}")
        for a in order.actions:
            if a.status != "skipped_no_sku":
                print(f"    {a.sku or '-'}: {a.status} — {a.message}")


def save_run_log(run: RunSummary, *, dry_run: bool) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = LOGS_DIR / f"run_log_{ts}.json"
    payload = {
        "dry_run": dry_run,
        "summary": {
            "orders_scanned": run.orders_scanned,
            "orders_with_skus": run.orders_with_skus,
            "added": run.added,
            "skipped_exists": run.skipped_exists,
            "skipped_no_sku": run.skipped_no_sku,
            "failed": run.failed,
            "approved": run.approved,
            "skipped_too_recent": run.skipped_too_recent,
        },
        "orders": [
            {
                **{k: v for k, v in asdict(o).items() if k != "actions"},
                "actions": [asdict(a) for a in o.actions],
            }
            for o in run.order_results
            if any(a.status != "skipped_no_sku" for a in o.actions)
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run(cfg: dict[str, Any], *, dry_run: bool, order_id: str | None) -> RunSummary:
    logger.info("正在登录管易…")
    client = create_client_from_config(cfg)

    run_summary = RunSummary()
    shop_ids = str(cfg["shop_ids"])
    page_size = int(cfg.get("page_size", 50))
    max_pages = cfg.get("max_pages")
    list_filters = cfg.get("list_filters") or {}

    min_age_minutes = int(cfg.get("min_order_age_minutes", 30))

    def handle_row(row: dict[str, Any]) -> None:
        run_summary.orders_scanned += 1

        if min_age_minutes > 0 and not order_id:
            if not order_is_old_enough(row, min_age_minutes):
                run_summary.skipped_too_recent += 1
                label = row.get("platformCode") or row.get("id")
                order_dt = parse_order_datetime(row)
                logger.debug(
                    "跳过 %s 分钟内订单 %s (createDate=%s)",
                    min_age_minutes,
                    label,
                    order_dt,
                )
                return

        memo = str(row.get("sellerMemo") or "")
        gift_skus = parse_gift_skus(
            memo,
            min_length=int(cfg.get("sku_min_length", 2)),
            allowlist_prefix=cfg.get("sku_allowlist_prefix") or None,
            max_qty=int(cfg.get("gift_max_qty", 99)),
        )
        if not gift_skus and not order_id:
            return

        if order_id and not order_ref_matches(row, order_id):
            return

        if gift_skus:
            run_summary.orders_with_skus += 1

        if not gift_skus and order_id:
            logger.warning("指定订单 %s 备注未解析到 SKU: %s", order_id, memo)
            return

        if not gift_skus:
            return

        order_result = process_order(client, row, cfg, dry_run=dry_run)
        run_summary.order_results.append(order_result)

    if order_id:
        found = False
        for row in client.iter_approve_orders(
            shop_ids=shop_ids,
            page_size=page_size,
            max_pages=max_pages,
            list_filters=list_filters,
        ):
            if order_ref_matches(row, order_id):
                found = True
                handle_row(row)
                break
        if not found:
            raise GuanyiApiError(
                f"在待审核列表中未找到订单 platformCode={order_id}，"
                "请确认 shop_ids、列表筛选及订单是否在待审核页"
            )
    else:
        n = 0
        for row in client.iter_approve_orders(
            shop_ids=shop_ids,
            page_size=page_size,
            max_pages=max_pages,
            list_filters=list_filters,
        ):
            handle_row(row)

    summarize(run_summary)
    return run_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="管易待审核订单自动加赠 SKU")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="配置文件路径（默认 config.json）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析并打印将处理的 SKU，不调用 updateDetail",
    )
    parser.add_argument(
        "--order-id",
        type=str,
        default=None,
        help="仅处理指定订单：平台订单号 platformCode（也兼容管易内部 id）",
    )
    parser.add_argument(
        "--no-approve",
        action="store_true",
        help="加赠后不自动提交审核",
    )
    parser.add_argument(
        "--no-feishu",
        action="store_true",
        help="不同步结果到飞书多维表",
    )
    parser.add_argument(
        "--no-dingtalk",
        action="store_true",
        help="不发送钉钉通知",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="DEBUG 日志",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1

    dry_run = args.dry_run or bool(cfg.get("dry_run", False))
    if args.no_approve:
        cfg = {**cfg, "auto_approve": False}
    if args.no_feishu:
        cfg = {
            **cfg,
            "feishu": {**(cfg.get("feishu") or {}), "enabled": False},
        }
    if args.no_dingtalk:
        cfg = {
            **cfg,
            "dingtalk": {**(cfg.get("dingtalk") or {}), "enabled": False},
        }

    summary = None
    log_path: Path | None = None
    exit_code = 0

    try:
        summary = run(cfg, dry_run=dry_run, order_id=args.order_id)
    except GuanyiApiError as exc:
        logger.error("运行中止: %s", exc)
        notify_run_result(
            None,
            cfg.get("dingtalk") or {},
            dry_run=dry_run,
            error_msg=str(exc),
            feishu_cfg=cfg.get("feishu") or {},
        )
        return 1

    print_summary(summary, dry_run=dry_run)
    log_path = save_run_log(summary, dry_run=dry_run)
    print(f"\n运行日志已写入: {log_path}")

    feishu_cfg = cfg.get("feishu") or {}
    try:
        n = sync_to_feishu_bitable(
            summary.order_results,
            feishu_cfg,
            dry_run=dry_run,
        )
        if n:
            table_url = build_feishu_table_url(feishu_cfg) or feishu_cfg.get("wiki_url", "")
            print(f"飞书多维表已同步 {n} 条: {table_url}")
    except Exception as exc:
        logger.error("飞书同步失败: %s", exc)
        exit_code = 1

    if notify_run_result(
        summary,
        cfg.get("dingtalk") or {},
        dry_run=dry_run,
        log_path=log_path,
        feishu_cfg=feishu_cfg,
    ):
        print("钉钉通知已发送")

    if summary.failed > 0 and exit_code == 0:
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
