#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管易云 C-ERP 模拟登录，获取 sessionId 并组装 API 所需 Cookie。

Cookie 仅保留：loginAppkey、userId、shiroCookie（shiroCookie = sessionId）

设备标识 device_id / _ati 用于跳过二次验证，可写在 config.json 的 guanyi 段
或同目录 device_config.json。
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

import requests
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

logger = logging.getLogger(__name__)

RSA_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEApV/oFZVdyiPzT1uFoMve
TCWpGODndiBGZaiQMGWP9bAgvaiOMgJF2f92NmD2lwdzOtOmBRADg13lXyiRJjfg
mLjAgp6TLmcUnOCiQruisz8iBI5Lj7ZfPGd0OlPq3TU9cKL46xYHtWVy/2amoYB
qgBQWPogHtvpJ/wOC2tSSHDhv64N21NcH/6d+jYTx9gvnB67NcQAG97uCQ8fJ+kq
ktbHh2EFmli915cIDYUKvobYNzvP0e7au0bLaOEOMAOBKZzhARSgn5QJNE6zj/IP
fM2gXmzfS5TlaGQSmAr9+7nd2AD/CCYXrA0vtKOS8DXnNjY9s2yp6l/6VqfvA+Eh
DAQIDAQAB
-----END PUBLIC KEY-----"""

DEFAULT_APP_KEY = "21226717"
DEFAULT_DEVICE_ID = (
    "EIMY7LHVHZMJDMPR3AD5KVWGPYZEVLPHZJZ5TAEU6EAPG3FZPCZAW4PKUVPYQ72"
    "ADHCIPSMWW42AYLYHTCGFYW4PLE"
)
DEFAULT_ATI = "1570860693343"

_PROJECT_DIR = Path(__file__).resolve().parent


def load_device_config(cfg: dict[str, Any] | None = None) -> tuple[str, str]:
    """从 device_config.json 或 config.guanyi 读取 device_id、ati。"""
    device_id = DEFAULT_DEVICE_ID
    ati = DEFAULT_ATI

    guanyi = (cfg or {}).get("guanyi") or {}
    if guanyi.get("device_id"):
        device_id = str(guanyi["device_id"])
    if guanyi.get("ati"):
        ati = str(guanyi["ati"])

    config_path = _PROJECT_DIR / "device_config.json"
    if config_path.is_file():
        with config_path.open(encoding="utf-8") as f:
            file_cfg = json.load(f)
        device_id = file_cfg.get("device_id", device_id)
        ati = file_cfg.get("ati", ati)

    return device_id, ati


def encrypt_password(password: str) -> str:
    key = RSA.import_key(RSA_PUBLIC_KEY)
    cipher = PKCS1_v1_5.new(key)
    encrypted = cipher.encrypt(password.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def build_cookie_string(
    *,
    login_appkey: str,
    user_id: str,
    session_id: str,
) -> str:
    """仅保留管易 API 需要的三个 Cookie 字段。"""
    return (
        f"loginAppkey={login_appkey}; "
        f"userId={user_id}; "
        f"shiroCookie={session_id}"
    )


def guanyi_login(
    username: str,
    password: str,
    *,
    login_appkey: str = DEFAULT_APP_KEY,
    device_id: str | None = None,
    ati: str | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """
    模拟管易登录，返回 getTaobaoSign 的 data（含 sessionId、userId 等）。
    """
    if device_id is None or ati is None:
        did, at = load_device_config()
        device_id = device_id or did
        ati = ati or at

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    login_cookies = {
        "loginAppkey": login_appkey,
        "env": "cerpv2",
        "ERPLanguage": "zh",
        "appKey": login_appkey,
        "_ati": ati,
        "device_id": device_id,
    }
    for domain in ("login.guanyierp.com", "v2.guanyierp.com"):
        for name, value in login_cookies.items():
            session.cookies.set(name, value, domain=domain)

    encrypted_pwd = encrypt_password(password)
    login_payload = {
        "email": username,
        "pwd": encrypted_pwd,
        "kaptcha": None,
        "redirectUrl": "https://v2.guanyierp.com/login",
        "webType": "main",
        "authCode": "",
    }

    resp = session.post(
        "https://login.guanyierp.com/login/loginDispatch",
        json=login_payload,
        headers={
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": "https://login.guanyierp.com",
            "Referer": (
                "https://login.guanyierp.com/login?webType=main"
                "&redirectUrl=http%3A%2F%2Fv2.guanyierp.com%2Flogin"
            ),
        },
        timeout=60,
    )
    resp.raise_for_status()
    login_result = resp.json()
    if login_result.get("status") != 200:
        msg = login_result.get("message", "未知错误")
        if login_result.get("needSecondFactor") or "二次验证" in str(msg):
            raise RuntimeError(
                "管易登录需要二次验证：请从浏览器复制 device_id 和 _ati，"
                "写入 device_config.json 或 config.json 的 guanyi 段"
            )
        raise RuntimeError(f"管易登录失败: {msg}")

    redirect_url = login_result["redirectUrl"]
    if not quiet:
        logger.info("管易登录验证通过")

    session.cookies.set("_ati", ati, domain="v2.guanyierp.com")
    session.cookies.set("device_id", device_id, domain="v2.guanyierp.com")
    session.cookies.set("loginAppkey", login_appkey, domain="v2.guanyierp.com")

    resp = session.get(redirect_url, allow_redirects=False, timeout=60)
    if resp.status_code not in (301, 302, 303, 307, 308):
        raise RuntimeError(f"金蝶会话绑定失败, status={resp.status_code}")

    resp = session.get("https://v2.guanyierp.com/index", timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"主站访问失败, status={resp.status_code}")

    resp = session.post(
        "https://v2.guanyierp.com/tc/trade/trade_order_header/getTaobaoSign",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=60,
    )
    resp.raise_for_status()
    sign_result = resp.json()
    if sign_result.get("status") != 200:
        raise RuntimeError(f"获取 sessionId 失败: {sign_result}")

    data = sign_result["data"]
    if not quiet:
        logger.info("管易 sessionId 获取成功 userId=%s", data.get("userId"))
    return data


def resolve_cookie_from_config(cfg: dict[str, Any]) -> str:
    """根据 config 登录并返回精简 Cookie 字符串。"""
    guanyi = cfg.get("guanyi") or {}
    username = guanyi.get("username") or cfg.get("guanyi_username")
    password = guanyi.get("password") or cfg.get("guanyi_password")
    if not username or not password:
        raise ValueError(
            "请在 config.json 的 guanyi 中配置 username 与 password（已移除 cookie 配置）"
        )

    login_appkey = str(guanyi.get("login_appkey") or DEFAULT_APP_KEY)
    session_data = guanyi_login(
        str(username),
        str(password),
        login_appkey=login_appkey,
        quiet=True,
    )
    session_id = str(session_data["sessionId"])
    user_id = str(session_data["userId"])
    return build_cookie_string(
        login_appkey=login_appkey,
        user_id=user_id,
        session_id=session_id,
    )


def create_client_from_config(cfg: dict[str, Any]):
    """登录并构造 GuanyiClient。"""
    from guanyi_client import GuanyiClient

    cookie = resolve_cookie_from_config(cfg)
    return GuanyiClient(
        cookie,
        request_delay_sec=float(cfg.get("request_delay_sec", 0.4)),
        stop_on_auth_error=bool(cfg.get("stop_on_auth_error", True)),
    )


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) == 3:
        uname, pwd = sys.argv[1], sys.argv[2]
    else:
        cfg_path = _PROJECT_DIR / "config.json"
        if cfg_path.is_file():
            with cfg_path.open(encoding="utf-8") as f:
                cfg = json.load(f)
            guanyi = cfg.get("guanyi") or {}
            uname = guanyi.get("username") or input("请输入用户名(手机号): ")
            pwd = guanyi.get("password") or input("请输入密码: ")
        else:
            uname = input("请输入用户名(手机号): ")
            pwd = input("请输入密码: ")

    try:
        data = guanyi_login(uname, pwd, quiet=False)
        cookie = build_cookie_string(
            login_appkey=DEFAULT_APP_KEY,
            user_id=str(data["userId"]),
            session_id=str(data["sessionId"]),
        )
        print("\n===== 登录结果 =====")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("\n===== API Cookie（仅三字段）=====")
        print(cookie)
    except Exception as exc:
        print(f"\n登录失败: {exc}")
        sys.exit(1)
