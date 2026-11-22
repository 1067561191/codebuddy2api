"""Locate the minimal content that trips the upstream channel check (code 11128).

Every probe replays the captured client request with parts of it removed, so the
verdict table reads like a控制变量 experiment: one dimension changes at a time,
never the headers. Results are cached by body hash so rerunning a phase is free.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_copilot import STREAM_URL, headers  # noqa: E402

ANA = ROOT / ".ana"
CACHE_PATH = ANA / "bisect_cache.json"
PARAM_KEYS = ("stream", "max_completion_tokens", "stream_options", "reasoning_effort", "model")


def load(name):
    return json.loads((ANA / f"{name}.json").read_text(encoding="utf-8"))


def _cache():
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def _code(raw):
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    return payload.get("code") if isinstance(payload, dict) else None


def verdict(status, raw):
    if status == 200:
        return "ok"
    code = _code(raw)
    if code == 11128:
        return "CHANNEL"
    return f"other({code})"


def probe(client, body, cache):
    key = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    if key in cache:
        return cache[key]
    try:
        with client.stream("POST", STREAM_URL, json=body, headers=headers) as response:
            status = response.status_code
            if status == 200:
                raw = ""
            else:
                raw = response.read().decode("utf-8", "replace")
    except httpx.HTTPError as error:
        result = {"verdict": f"error({type(error).__name__})", "status": 0, "code": None}
    else:
        result = {"verdict": verdict(status, raw), "status": status, "code": _code(raw)}
    cache[key] = result
    return result


def blocks(message):
    content = message.get("content")
    if not isinstance(content, str):
        return [""]
    return content.split("\n\n")


def atom_list(base):
    """Every removable unit: one param, one message block, one tool."""
    atoms = [{"kind": "param", "key": key} for key in PARAM_KEYS if key in base]
    for index, message in enumerate(base.get("messages") or []):
        for offset, _ in enumerate(blocks(message)):
            atoms.append({"kind": "msg", "index": index, "block": offset})
    for index, _ in enumerate(base.get("tools") or []):
        atoms.append({"kind": "tool", "index": index})
    return atoms


def rebuild(base, atoms):
    body = {}
    for atom in atoms:
        if atom["kind"] == "param":
            body[atom["key"]] = base[atom["key"]]
    picked = {}
    for atom in atoms:
        if atom["kind"] == "msg":
            picked.setdefault(atom["index"], []).append(atom["block"])
    messages = []
    for index in sorted(picked):
        source = base["messages"][index]
        text = "\n\n".join(blocks(source)[offset] for offset in sorted(picked[index]))
        messages.append({**{k: v for k, v in source.items() if k != "content"}, "content": text})
    body["messages"] = messages
    tools = [base["tools"][atom["index"]] for atom in atoms if atom["kind"] == "tool"]
    if tools:
        body["tools"] = tools
    return body


def describe(body):
    params = " ".join(f"{key}={body[key]!r}" for key in PARAM_KEYS if key in body)
    messages = [(m["role"], len(m["content"]) if isinstance(m.get("content"), str) else "?")
                for m in body.get("messages") or []]
    return f"{params} | messages={messages} tools={len(body.get('tools') or [])}"


def trim(base, *, messages=None, tools=None, system=None, keep_params=True):
    """Copy ``base`` keeping only the requested message/tool indexes."""
    body = {key: base[key] for key in PARAM_KEYS if key in base} if keep_params else {}
    if "model" not in body:
        body["model"] = base["model"]
    chosen = []
    for index in (range(len(base["messages"])) if messages is None else messages):
        message = {"role": base["messages"][index]["role"], "content": base["messages"][index]["content"]}
        chosen.append(message)
    if system is not None:
        chosen = [{"role": "system", "content": system}] + [m for m in chosen if m["role"] != "system"]
    body["messages"] = chosen
    if tools is None:
        if base.get("tools"):
            body["tools"] = base["tools"]
    else:
        picked = [base["tools"][index] for index in tools]
        if picked:
            body["tools"] = picked
    return body


def coarse(bad, official, good):
    """One dimension at a time, then the cross combinations that keep the trigger visible."""
    all_messages = list(range(len(bad["messages"])))
    all_tools = list(range(len(bad["tools"])))
    variants = {
        "baseline.bad": trim(bad, messages=all_messages, tools=all_tools),
        "baseline.official": dict(official),
        "baseline.good": dict(good),
        "bad.no_tools": trim(bad, messages=all_messages, tools=[]),
        "bad.no_messages": {**{k: bad[k] for k in PARAM_KEYS if k in bad}, "messages": [bad["messages"][1]]},
        "bad.only_system": trim(bad, messages=[0], tools=[]),
        "bad.only_reminders": trim(bad, messages=[1, 2, 3, 4], tools=[]),
        "bad.only_tools": trim(bad, messages=[1], tools=all_tools),
        "bad.params_only": {**{k: bad[k] for k in PARAM_KEYS if k in bad}, "messages": [bad["messages"][1]]},
        "bad.sys_short": trim(bad, messages=all_messages, tools=all_tools, system="You are WorkBuddy, a powerful AI assistant."),
        "bad.tools_no_system": trim(bad, messages=[1], tools=all_tools, system="You are WorkBuddy, a powerful AI assistant."),
        "official.plus_bad_tools": {**official, "messages": official["messages"], "tools": bad["tools"]},
        "official.plus_bad_messages": {**official, "messages": bad["messages"]},
    }
    return variants


def run(variants, jobs):
    cache = _cache()
    rows = []
    with httpx.Client(verify=False, timeout=180.0) as client:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {name: pool.submit(probe, client, body, cache) for name, body in variants.items()}
            for name, future in futures.items():
                result = future.result()
                rows.append((name, result, variants[name]))
    _save_cache(cache)
    width = max(len(name) for name, _, _ in rows)
    for name, result, body in rows:
        print(f"{name:<{width}}  {result['verdict']:<14} {describe(body)}")
    return rows


def ddmin(base, jobs):
    """Greedy delta debugging: drop as much as possible while the channel check stays."""
    cache = _cache()
    atoms = atom_list(base)
    with httpx.Client(verify=False, timeout=180.0) as client:
        current = list(atoms)
        granularity = 2
        steps = 0
        while len(current) >= 2:
            size = max(1, len(current) // granularity)
            chunks = [current[i:i + size] for i in range(0, len(current), size)]
            reduced = False
            for chunk in chunks:
                candidate = [atom for atom in current if atom not in chunk]
                if not any(atom["kind"] == "msg" for atom in candidate):
                    continue
                body = rebuild(base, candidate)
                steps += 1
                result = probe(client, body, cache)
                print(f"  step {steps}: keep {len(candidate)}/{len(current)} atoms -> {result['verdict']}", flush=True)
                if result["verdict"] == "CHANNEL":
                    current = candidate
                    granularity = max(2, granularity - 1)
                    reduced = True
                    break
            if not reduced:
                if granularity >= len(current):
                    break
                granularity = min(len(current), granularity * 2)
    _save_cache(cache)
    body = rebuild(base, current)
    print("\n=== minimal channel-triggering body ===")
    print(describe(body))
    print(json.dumps(body, ensure_ascii=False, indent=1)[:4000])
    return body


def main():
    parser = argparse.ArgumentParser(description="定位触发上游渠道校验的最小内容")
    parser.add_argument("--phase", default="coarse", choices=("coarse", "ddmin"))
    parser.add_argument("--body", default="bad_request", help="ddmin 的起始请求体")
    parser.add_argument("--jobs", type=int, default=4, help="并行请求数")
    parser.add_argument("--out", default=None, help="把变体结果写入 JSON")
    args = parser.parse_args()

    bad, official, good = load("bad_request"), load("official_request"), load("good_request")
    if args.phase == "coarse":
        rows = run(coarse(bad, official, good), args.jobs)
        if args.out:
            payload = {name: result for name, result, _ in rows}
            Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        ddmin(load(args.body), args.jobs)


if __name__ == "__main__":
    main()
