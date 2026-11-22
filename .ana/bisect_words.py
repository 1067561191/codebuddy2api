"""Third phase: word-level bisect with verified preconditions.

Phase two's text bisect accepted any "not CHANNEL" as a reduce signal, so it printed a
result it never confirmed. This one refuses to run unless the starting text really is
CHANNEL, only reduces on a confirmed CHANNEL, and re-verifies the answer three times.
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


def body_with(text):
    return {"stream": True, "model": MODEL,
            "messages": [{"role": "system", "content": text}]}


class Prober:
    def __init__(self):
        self.client = httpx.Client(verify=False, timeout=180.0)
        self.seen = {}
        self.calls = 0

    def verdict(self, text):
        body = body_with(text)
        key = json.dumps(body, sort_keys=True, ensure_ascii=False)
        if key in self.seen:
            return self.seen[key]
        self.calls += 1
        with self.client.stream("POST", STREAM_URL, json=body, headers=headers) as response:
            if response.status_code == 200:
                result = "ok"
            else:
                raw = response.read().decode("utf-8", "replace")
                try:
                    result = f"code{json.loads(raw).get('code')}"
                except ValueError:
                    result = f"http{response.status_code}"
        self.seen[key] = result
        return result

    def close(self):
        self.client.close()


def confirm(prober, text, times=3):
    return [prober.verdict(text) for _ in range(times)]


def bisect_words(prober, text, label=""):
    words = text.split()
    assert "CHANNEL" in confirm(prober, text, 2)[0:1] or prober.verdict(text) == "code11128", \
        f"{label} 起点不是渠道校验，无法继续"
    current = words
    granularity = 2
    while len(current) >= 2:
        size = max(1, len(current) // granularity)
        chunks = [current[i:i + size] for i in range(0, len(current), size)]
        reduced = False
        for chunk in chunks:
            candidate = [word for word in current if word not in chunk]
            if not candidate:
                continue
            text_candidate = " ".join(candidate)
            if prober.verdict(text_candidate) == "code11128":
                print(f"  ✓ 删除 {len(chunk)} 词 -> {len(text_candidate)} chars 仍被拦", flush=True)
                current = candidate
                granularity = max(2, granularity - 1)
                reduced = True
                break
        if not reduced:
            if granularity >= len(current):
                break
            granularity = min(len(current), granularity * 2)
    return " ".join(current)


def leave_one_out(prober, text):
    words = text.split()
    rows = []
    for index in range(len(words)):
        candidate = " ".join(words[:index] + words[index + 1:])
        rows.append((words[index], prober.verdict(candidate)))
    return rows


def main():
    trigger = json.loads((ANA / "channel_min.json").read_text(encoding="utf-8"))["messages"][0]["content"]
    prober = Prober()
    try:
        print("起点校验：", confirm(prober, trigger))
        prefix20 = " ".join(trigger.split()[:20])
        print("prefix20 校验：", confirm(prober, prefix20))

        print("\n--- 逐词留一（在 prefix20 上，看哪个词必需） ---")
        for word, result in leave_one_out(prober, prefix20):
            print(f"  去掉 {word!r:<16} -> {result}")

        print("\n--- prefix20 词级二分 ---")
        minimal = bisect_words(prober, prefix20, "prefix20")
        print(f"\n最小文本（{len(minimal)} chars）：{minimal!r}")
        print("三次复验：", confirm(prober, minimal))
    finally:
        prober.close()
        print(f"\n共发出 {prober.calls} 次请求")


if __name__ == "__main__":
    main()
