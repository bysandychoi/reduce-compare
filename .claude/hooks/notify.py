#!/usr/bin/env python3
"""Notification(permission_prompt): 승인 요청이 오면 팝업을 띄운다."""
import os

from _common import PROJECT, config, popup, read_input


def main():
    data = read_input()
    cfg = config().get("popup", {})
    if not cfg.get("on_permission", True):
        return
    msg = data.get("message") or (data.get("notification_data") or {}).get("message") or "승인이 필요한 작업이 있습니다."
    popup(f"Claude Code · {os.path.basename(PROJECT)} · 승인 요청", msg, cfg.get("style", "notification"))


if __name__ == "__main__":
    main()
