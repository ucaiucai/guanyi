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

from guanyi_client import GuanyiApiError, GuanyiClient
from sku_parser import filter_new_skus, parse_skus

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"


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
    actions: list[SkuAction] = field(default_factory=list)


@dataclass
class RunSummary:
    orders_scanned: int = 0
    orders_with_skus: int = 0
    added: int = 0
    skipped_exists: int = 0
    skipped_no_sku: int = 0
    failed: int = 0
    order_results: list[OrderResult] = field(default_factory=list)


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"配置文件不存在: {path}\n请复制 config.example.json 为 config.json 并填写 Cookie"
        )
    with path.open(encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("cookie") or "<" in str(cfg.get("cookie", "")):
        raise ValueError("请在 config.json 中配置有效的 cookie")
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

    skus = parse_skus(
        seller_memo,
        min_length=int(cfg.get("sku_min_length", 2)),
        allowlist_prefix=allowlist,
    )

    result = OrderResult(
        order_id=order_id,
        platform_code=platform_code,
        code=code,
        seller_memo=seller_memo,
    )

    if not skus:
        result.actions.append(
            SkuAction("", "skipped_no_sku", "备注未解析到含横杠的 SKU")
        )
        return result

    detail_resp = client.get_order_details(order_id)
    detail_rows = detail_resp.get("rows") or []
    existing_codes = [
        str(d["itemCode"]) for d in detail_rows if d.get("itemCode")
    ]
    to_add = filter_new_skus(skus, existing_codes)

    for sku in skus:
        if sku not in to_add:
            result.actions.append(
                SkuAction(sku, "skipped_already_exists", "订单明细已存在")
            )
            continue

        if dry_run:
            result.actions.append(
                SkuAction(sku, "dry_run_would_add", f"将加赠 warehouse={warehouse_id}")
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
            client.update_order_detail(order_id, product)
            existing_codes.append(sku)
            to_add = [s for s in to_add if s != sku]
            result.actions.append(
                SkuAction(
                    sku,
                    "added",
                    f"{product.get('itemName', '')} (itemCode={product.get('itemCode')})",
                )
            )
            label = platform_code or code or order_id
            logger.info("订单 %s 已加赠 %s", label, sku)
        except GuanyiApiError as exc:
            status = "ambiguous_product" if "歧义" in str(exc) else "failed"
            result.actions.append(SkuAction(sku, status, str(exc)))
            label = platform_code or code or order_id
            logger.error("订单 %s SKU %s 失败: %s", label, sku, exc)

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


def print_summary(run: RunSummary, *, dry_run: bool) -> None:
    mode = "【试运行】" if dry_run else "【正式执行】"
    print(f"\n{mode} 汇总")
    print(f"  扫描订单: {run.orders_scanned}")
    print(f"  含可解析 SKU: {run.orders_with_skus}")
    print(f"  加赠成功: {run.added}")
    print(f"  已存在跳过: {run.skipped_exists}")
    print(f"  无 SKU 跳过: {run.skipped_no_sku}")
    print(f"  失败/未找到: {run.failed}")
    print("\n明细:")
    for order in run.order_results:
        if all(a.status == "skipped_no_sku" for a in order.actions):
            continue
        memo_preview = order.seller_memo[:80] + ("…" if len(order.seller_memo) > 80 else "")
        order_label = order.platform_code or order.code or order.order_id
        print(f"  订单 {order_label} | 备注: {memo_preview}")
        for a in order.actions:
            if a.status != "skipped_no_sku":
                print(f"    {a.sku or '-'}: {a.status} — {a.message}")


def save_run_log(run: RunSummary, *, dry_run: bool) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(__file__).parent / f"run_log_{ts}.json"
    payload = {
        "dry_run": dry_run,
        "summary": {
            "orders_scanned": run.orders_scanned,
            "orders_with_skus": run.orders_with_skus,
            "added": run.added,
            "skipped_exists": run.skipped_exists,
            "skipped_no_sku": run.skipped_no_sku,
            "failed": run.failed,
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
    client = GuanyiClient(
        cfg["cookie"],
        request_delay_sec=float(cfg.get("request_delay_sec", 0.4)),
        stop_on_auth_error=bool(cfg.get("stop_on_auth_error", True)),
    )

    run_summary = RunSummary()
    shop_ids = str(cfg["shop_ids"])
    page_size = int(cfg.get("page_size", 50))
    max_pages = cfg.get("max_pages")
    list_filters = cfg.get("list_filters") or {}

    def handle_row(row: dict[str, Any]) -> None:
        run_summary.orders_scanned += 1
        memo = str(row.get("sellerMemo") or "")
        skus = parse_skus(
            memo,
            min_length=int(cfg.get("sku_min_length", 2)),
            allowlist_prefix=cfg.get("sku_allowlist_prefix") or None,
        )
        if not skus and not order_id:
            return

        if order_id and not order_ref_matches(row, order_id):
            return

        if skus:
            run_summary.orders_with_skus += 1

        if not skus and order_id:
            logger.warning("指定订单 %s 备注未解析到 SKU: %s", order_id, memo)
            return

        if not skus:
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

    try:
        summary = run(cfg, dry_run=dry_run, order_id=args.order_id)
    except GuanyiApiError as exc:
        logger.error("运行中止: %s", exc)
        return 1

    print_summary(summary, dry_run=dry_run)
    log_path = save_run_log(summary, dry_run=dry_run)
    print(f"\n运行日志已写入: {log_path}")

    return 1 if summary.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
