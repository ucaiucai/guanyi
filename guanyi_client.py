#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""管易 ERP v2 订单加赠相关 HTTP 接口封装。"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://v2.guanyierp.com"

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": BASE_URL,
    "bx-v": "2.5.11",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    ),
}


class GuanyiApiError(Exception):
    """管易接口业务或网络错误。"""

    def __init__(self, message: str, *, status: str | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class GuanyiClient:
    def __init__(
        self,
        cookie: str,
        *,
        request_delay_sec: float = 0.4,
        stop_on_auth_error: bool = True,
    ):
        self.request_delay_sec = request_delay_sec
        self.stop_on_auth_error = stop_on_auth_error
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.session.headers["Cookie"] = cookie.strip()

    def _sleep(self) -> None:
        if self.request_delay_sec > 0:
            time.sleep(self.request_delay_sec)

    def _post(self, path: str, data: dict[str, Any], *, referer_path: str) -> Any:
        url = f"{BASE_URL}{path}"
        headers = {"Referer": f"{BASE_URL}{referer_path}"}
        self._sleep()
        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise GuanyiApiError(f"请求失败 {path}: {exc}") from exc

        try:
            body = resp.json()
            # print(body)
        except ValueError as exc:
            raise GuanyiApiError(f"响应非 JSON {path}: {resp.text[:200]}") from exc

        if isinstance(body, dict):
            status = str(body.get("status", ""))
            if status and status not in ("200", "0"):
                msg = body.get("message") or body.get("msg") or body
                if self.stop_on_auth_error and status in ("401", "403", "302"):
                    raise GuanyiApiError(f"认证可能失效: {msg}", status=status, payload=body)
                raise GuanyiApiError(f"接口错误 {path}: {msg}", status=status, payload=body)

        return body

    def list_approve_orders(
        self,
        *,
        shop_ids: str,
        page: int = 1,
        limit: int = 50,
        start: int = 0,
        list_filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        filters = list_filters or {}
        data = {
            "page": page,
            "limit": limit,
            "start": start,
            "shopIds": shop_ids,
            "cod": filters.get("cod", ""),
            "chkMemo": filters.get("chkMemo", ""),
            "hasInvoice": filters.get("hasInvoice", ""),
            "refund": filters.get("refund", ""),
            "financeReject": filters.get("financeReject", ""),
            "error":0
        }
        return self._post(
            "/tc/trade/trade_order_approve/data/list",
            data,
            referer_path="/tc/trade/trade_order_approve",
        )

    def iter_approve_orders(
        self,
        *,
        shop_ids: str,
        page_size: int = 50,
        max_pages: int | None = None,
        list_filters: dict[str, str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """分页迭代待审核订单列表中的 rows。"""
        page = 1
        start = 0
        pages_fetched = 0

        while True:
            result = self.list_approve_orders(
                shop_ids=shop_ids,
                page=page,
                limit=page_size,
                start=start,
                list_filters=list_filters,
            )
            rows = result.get("rows") or []
            for row in rows:
                yield row

            total = int(result.get("total") or 0)
            start += len(rows)
            pages_fetched += 1

            if not rows or start >= total:
                break
            if max_pages is not None and pages_fetched >= max_pages:
                logger.info("已达 max_pages=%s，停止拉取", max_pages)
                break
            page += 1

    def get_order_details(self, pid: str, *, rows: int = 1000) -> dict[str, Any]:
        return self._post(
            "/tc/trade/trade_order_header/data/detail_page",
            {"pid": pid, "rows": rows},
            referer_path="/tc/trade/trade_order_approve",
        )

    def search_product(
        self,
        like_code: str,
        *,
        warehouse_id: str,
        page: int = 1,
        rows: int = 20,
    ) -> dict[str, Any]:
        data = {
            "page": page,
            "rows": rows,
            "start": 0,
            "load": 0,
            "disable": "false",
            "warehouseId": warehouse_id,
            "categoryId": "",
            "likeCode": like_code,
            "name": "",
            "skuCode": "",
            "skuName": "",
            "sName": "",
            "combine": "",
        }
        return self._post(
            "/ic/select_product/data/list",
            data,
            referer_path="/tc/trade/trade_order_approve",
        )

    def get_trade_detail(self, tid: str) -> dict[str, Any]:
        return self._post(
            "/tc/trade/trade_order_header/data/tradeDetail",
            {"tid": tid},
            referer_path="/tc/trade/trade_order_approve",
        )

    def update_order_detail(self, order_id: str, product: dict[str, Any]) -> dict[str, Any]:
        detail_line = {
            "skuId": str(product["id"]),
            "itemSkuId": product.get("itemSkuId"),
            "itemId": str(product["itemId"]),
            "itemSkuCode": product.get("itemSkuCode"),
            "itemSkuName": product.get("itemSkuName"),
            "discount": 1,
            "qty": 1,
            "originPrice": 0,
            "price": 0,
            "originAmount": 0,
            "amount": 0,
            "costPrice": product.get("costPrice") or 0,
            "type": "Item",
            "presale": False,
            "oid": "",
            "platformItemName": "",
            "platformSkuName": "",
            "del": "",
            "tradeDetailId": "",
            "pid": "",
            "cancel": "",
            "warehouseId": "",
            "giftSourceView": "",
            "weight": product.get("weight") or 0,
            "combineDetailId": "",
            "bmsStatus": "",
            "platformCode": "",
            "storeCode": "",
            "cycle": "",
            "proxy": "",
            "discountFee": 0,
            "postFee": 0,
            "otherServiceFee": 0,
        }
        trade_info = {"id": str(order_id), "tradeOrderDetailList": [detail_line]}
        payload = f"tradeInfo={quote(json.dumps(trade_info, ensure_ascii=False))}"
        self._sleep()
        url = f"{BASE_URL}/tc/trade/trade_order_header/updateDetail"
        headers = {
            "Referer": f"{BASE_URL}/tc/trade/trade_order_approve",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            resp = self.session.post(url, data=payload, headers=headers, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise GuanyiApiError(f"updateDetail 请求失败: {exc}") from exc

        try:
            body = resp.json()
        except ValueError as exc:
            raise GuanyiApiError(f"updateDetail 响应非 JSON: {resp.text[:200]}") from exc

        status = str(body.get("status", ""))
        message = str(body.get("message", ""))
        if status != "200" or "保存成功" not in message:
            raise GuanyiApiError(
                f"加赠保存失败: {message or body}",
                status=status,
                payload=body,
            )
        return body

    def approve_order(self, order_id: str) -> dict[str, Any]:
        """提交订单审核（ids 为管易内部订单 id）。"""
        body = self._post(
            "/tc/trade/trade_order_approve/approve",
            {"ids": str(order_id)},
            referer_path="/tc/trade/trade_order_approve",
        )
        if isinstance(body, dict):
            status = str(body.get("status", ""))
            message = str(body.get("message") or body.get("msg") or "")
            if status and status not in ("200", "0"):
                raise GuanyiApiError(
                    f"审核失败: {message or body}",
                    status=status,
                    payload=body,
                )
            if message and "成功" not in message and status not in ("200", "0", ""):
                raise GuanyiApiError(f"审核失败: {message}", payload=body)
        return body if isinstance(body, dict) else {"raw": body}
