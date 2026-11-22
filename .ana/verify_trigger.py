"""Reproduce the finding end to end: the exact 111-char system prefix is the trigger.

Everything here is re-verified in one run so the conclusion does not depend on the
earlier exploratory phases or their caches.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_copilot import STREAM_URL, headers  # noqa: E402

ANA = ROOT / ".ana"
MODEL = "deepseek-v4.1-flash"
CORE = ("Tokens prefixed with @ are paths the user explicitly referenced. "
        "Relative paths resolve from the workspace root")


def verdict(client, messages, *, model=MODEL, stream=True):
    body = {"stream": stream, "messages": messages}
    if model:
        body["model"] = model
    with client.stream("POST", STREAM_URL, json=body, headers=headers) as response:
        if response.status_code == 200:
            return "ok"
        raw = response.read().decode("utf-8", "replace")
    try:
        return f"code{json.loads(raw).get('code')}"
    except ValueError:
        return f"http{response.status_code}"


def system(text):
    return [{"role": "system", "content": text}]


def main():
    bad = json.loads((ANA / "bad_request.json").read_text(encoding="utf-8"))
    prompt = bad["messages"][0]["content"]
    assert CORE in prompt, "core text missing from the captured system prompt"

    cases = {
        "1. 原始 bad_request（全部 messages + 32 tools）": None,
        "2. 仅 system 消息": system(prompt),
        "3. 仅 system 里的那一段(407 chars)": system(CORE + ' A trailing slash marks a directory.'),
        "4. 111 chars 精确片段（触发）": system(CORE),
        "5. 同片段截短 1 字符（不触发）": system(CORE[:-1]),
        "6. 同片段换 1 字符（不触发）": system(CORE.replace("workspace", "workspase")),
        "7. 同片段但词序打乱（不触发）": system(
            " ".join([CORE.split()[i] for i in (1, 0, 3, 2, 5, 4, 7, 6, 9, 8, 11, 10, 13, 12, 15, 14, 16)])),
        "8. 同片段放进 user 消息（不触发）": [{"role": "user", "content": CORE}],
        "9. 同片段 + stream=false（不触发）": system(CORE),
        "10. 同片段 + 去掉 model（仍触发）": system(CORE),
    }

    with httpx.Client(verify=False, timeout=180.0) as client:
        for name, messages in cases.items():
            if messages is None:
                body = dict(bad)
                with client.stream("POST", STREAM_URL, json=body, headers=headers) as response:
                    if response.status_code == 200:
                        result = "ok"
                    else:
                        raw = response.read().decode("utf-8", "replace")
                        result = f"code{json.loads(raw).get('code')}"
                print(f"{name:<44} -> {result}")
                continue
            stream = name.startswith("9") is False
            model = None if name.startswith("10") else MODEL
            print(f"{name:<44} -> {verdict(client, messages, model=model, stream=stream)}")

        print("\n--- 三次重复，确认稳定性 ---")
        for _ in range(3):
            print("  ", verdict(client, system(CORE)), verdict(client, system(CORE[:-1])))


if __name__ == "__main__":
    main()
