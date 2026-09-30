#!/usr/bin/env python3
"""Notification(Claude)/PermissionRequest(Codex): 승인 요청이 오면 팝업만 띄운다.

승인 여부를 결정하지 않는다 (아무 decision도 내보내지 않고 조용히 끝난다) —
이 훅은 순수 알림용이라 사람이 보던 승인 흐름을 그대로 둔다.
"""
import os

from common import PROJECT, config, popup, read_input


def build_message(data):
    msg = data.get("message") or (data.get("notification_data") or {}).get("message")
    if msg:
        return msg
    ti = data.get("tool_input") or {}
    tool = data.get("tool_name")
    desc = ti.get("description")
    cmd = ti.get("command")
    if desc:
        return f"{tool or '작업'} 승인 필요: {desc}"
    if cmd:
        short = cmd.strip().splitlines()[0][:100]
        return f"{tool or '작업'} 승인 필요: {short}"
    return "승인이 필요한 작업이 있습니다."


def main():
    data = read_input()
    cfg = config().get("popup", {})
    if not cfg.get("on_permission", True):
        return
    popup(f"{os.path.basename(PROJECT)} · 승인 요청", build_message(data), cfg.get("style", "notification"))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001, S110 - notification failure must never block work
        pass
