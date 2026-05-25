#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试管易登录网关。"""

import json
from pathlib import Path

from guanyi_auth import build_cookie_string, guanyi_login, resolve_cookie_from_config

CONFIG_PATH = Path(__file__).parent / "config.json"


def main() -> None:
    if CONFIG_PATH.is_file():
        cookie = resolve_cookie_from_config(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        print("Cookie:", cookie)
        return

    # 无 config 时手动传参（仅本地调试）
    session = guanyi_login("username", "password")
    print(session)
    print(
        build_cookie_string(
            login_appkey="21226717",
            user_id=str(session["userId"]),
            session_id=str(session["sessionId"]),
        )
    )


if __name__ == "__main__":
    main()
