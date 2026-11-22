"""Second phase: bisect the triggering system paragraph itself.

Phase one reduced the whole request to one system paragraph; this narrows the text
itself, checks whether the paragraph is a *necessary* condition inside the full
captured request, and separates "this exact wording" from "any long system prompt".
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / ".ana"))

import httpx  # noqa: E402

from bisect_channel import _cache, _save_cache, describe, load, probe  # noqa: E402
from verify_copilot import headers  # noqa: E402

ANA = ROOT / ".ana"
MODEL = "deepseek-v4.1-flash"


def body_with(system=None, user=None, *, model=True, stream=True):
    messages = []
    if system is not None:
        messages.append({"role": "system", "content": system})
    if user is not None:
        messages.append({"role": "user", "content": user})
    body = {"stream": stream, "messages": messages}
    if model:
        body["model"] = MODEL
    return body


def run(variants, jobs, cache):
    with httpx.Client(verify=False, timeout=180.0) as client:
        width = max(len(name) for name in variants)
        rows = {}
        for name, body in variants.items():
            result = probe(client, body, cache)
            rows[name] = result
            print(f"{name:<{width}}  {result['verdict']}", flush=True)
    _save_cache(cache)
    return rows


def sentences(text):
    parts = []
    for line in text.split("\n"):
        parts.extend(piece.strip() for piece in line.split(". ") if piece.strip())
    return parts


def ddmin_text(text, probe_text, label="text"):
    """Greedy delta debugging over sentences, then over words."""
    def channel(candidate):
        result = probe_text(candidate)
        print(f"  {label}: {result['verdict']} ({len(candidate)} chars)", flush=True)
        return result["verdict"] == "CHANNEL"

    current = sentences(text)
    for unit in ("sentence", "word"):
        if unit == "word":
            current = " ".join(current).split()
        granularity = 2
        steps = 0
        while len(current) >= 2:
            size = max(1, len(current) // granularity)
            chunks = [current[i:i + size] for i in range(0, len(current), size)]
            reduced = False
            for chunk in chunks:
                candidate = [item for item in current if item not in chunk]
                if not candidate:
                    continue
                joiner = ". " if unit == "sentence" else " "
                steps += 1
                if channel(joiner.join(candidate)):
                    current = candidate
                    granularity = max(2, granularity - 1)
                    reduced = True
                    break
            if not reduced:
                if granularity >= len(current):
                    break
                granularity = min(len(current), granularity * 2)
    return (". " if isinstance(current[0], str) and current and " " in current[0] else " ").join(current)


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "variants"
    bad = load("bad_request")
    trigger = json.loads((ANA / "channel_min.json").read_text(encoding="utf-8"))["messages"][0]["content"] \
        if (ANA / "channel_min.json").exists() else None
    if trigger is None:
        raise SystemExit("[!] 先运行 ddmin 阶段生成 .ana/channel_min.json")

    cache = _cache()
    with httpx.Client(verify=False, timeout=180.0) as client:
        probe_text = lambda text: probe(client, body_with(text), cache)  # noqa: E731

        if phase == "variants":
            benign = ("The quick brown fox jumps over the lazy dog while the assistant keeps a steady tone "
                      "and answers plainly without any special vocabulary or formatting.") * 3
            variants = {
                "trigger.system": body_with(trigger),
                "trigger.user": body_with(None, trigger),
                "trigger.no_model": body_with(trigger, model=False),
                "trigger.stream_false": body_with(trigger, stream=False),
                "trigger.word_repeat": body_with(" ".join(trigger.split()[:60])),
                "benign.system.same_len": body_with(benign[:len(trigger)]),
                "benign.system.4000": body_with((benign * 4)[:4000]),
                "official_system": body_with(load("official_request")["messages"][0]["content"]),
                "prompt_no_at": body_with(trigger.replace("@", "")),
                "prompt_no_read_tool": body_with(trigger.replace("read tool", "reader")),
                "prompt_only_at_strip": body_with('@"..." quotes a path containing spaces.'),
                "prompt_only_read_tool": body_with(
                    "Anything else is a file: use the read tool when its contents are needed."),
            }
            run(variants, 4, cache)
            return

        if phase == "necessary":
            variants = {}
            system_text = bad["messages"][0]["content"]
            without = system_text.replace(trigger, "").strip()
            assert without != system_text, "trigger not found in the captured system prompt"
            variants["bad.full"] = bad
            variants["bad.system_minus_trigger"] = {**bad, "messages": [
                {"role": "system", "content": without}, *bad["messages"][1:]]}
            variants["bad.system_only_minus_trigger"] = {
                **{k: bad[k] for k in ("stream", "max_completion_tokens", "stream_options",
                                       "reasoning_effort", "model")},
                "messages": [{"role": "system", "content": without}]}
            run(variants, 3, cache)
            return

        if phase == "text":
            final = ddmin_text(trigger, probe_text)
            print("\n=== minimal trigger text ===")
            print(json.dumps(final, ensure_ascii=False))
            print("\nrecheck:")
            for label, text in (("minimal", final), ("minimal+wrapper", "Tokens " + final)):
                print(f"  {label}: {probe_text(text)['verdict']}")
            (ANA / "channel_trigger.txt").write_text(final, encoding="utf-8")
            return

    raise SystemExit(f"[!] 未知阶段 {phase}")


if __name__ == "__main__":
    main()
