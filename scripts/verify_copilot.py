import argparse
import json
import sys
from pathlib import Path

import httpx

STREAM_URL = 'https://copilot.tencent.com/v2/chat/completions'
DEFAULT_BODY = Path(__file__).resolve().parents[1] / '.ana' / 'bad_request.json'


headers = {
    'x-stainless-arch': 'x64',
    'x-stainless-lang': 'js',
    'x-stainless-os': 'Linux',
    'x-stainless-package-version': '7.39.0',
    'x-stainless-retry-count': '0',
    'x-stainless-runtime': 'node',
    'x-stainless-runtime-version': 'v24.21.0',
    'X-Agent-Intent': 'craft',
    'X-Agent-Purpose': 'conversation',
    'X-Agent-Type': 'main',
    'X-Private-Data': 'false',
    'X-CodeBuddy-Request': '1',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Authorization': 'Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6Im15ZkV6cDc4M0tpX0pDeDhWbmMzWF9peDZqWnJiNkNmNU9Na0daTVBJM3MiLCJ0eXAiOiJKV1QiLCJ2ZXIiOiJ2MiJ9.eyJhY3IiOiIwIiwiYWxsb3dlZC1vcmlnaW5zIjpbIioiXSwiYXBwX3R5cGUiOiJjb2RlYnVkZHkiLCJhdWQiOiJhY2NvdW50IiwiYXV0aF90aW1lIjoxNzkyODIwNjkxLCJhenAiOiJjb25zb2xlIiwiZW1haWwiOiIiLCJlbWFpbF92ZXJpZmllZCI6ZmFsc2UsImV4cCI6MTc5NzczMjkxNCwiZmVkZXJhdGVkIjp7fSwiaWF0IjoxNzk1MzEzNzE0LCJpc3MiOiJodHRwczovL3d3dy5jb2RlYnVkZHkuY24vYXV0aC9yZWFsbXMvY29waWxvdCIsImp0aSI6IjJlZDA2ZmJkLWU3ZTMtNDY3MC1hMDM0LWVkODI2Y2U5NDhjMiIsIm5pY2tuYW1lIjoi5pS-5YGH55qE54iG57Gz6IqxIiwib25laWRfdW5pb25faWQiOiIiLCJwcmVmZXJyZWRfdXNlcm5hbWUiOiIxNTg5NTgwODcwNSIsInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyJvZmZsaW5lX2FjY2VzcyIsImRlZmF1bHQtcm9sZXMiLCJ1bWFfYXV0aG9yaXphdGlvbiJdfSwicmVzb3VyY2VfYWNjZXNzIjp7ImFjY291bnQiOnsicm9sZXMiOlsidmlldy1wcm9maWxlIiwibWFuYWdlLWFjY291bnQtbGlua3MiLCJtYW5hZ2UtYWNjb3VudCJdfX0sInNjb3BlIjoiYWNyIG9mZmxpbmVfYWNjZXNzIHByb2ZpbGUgYmFzaWMgcm9sZXMgZW1haWwgd2ViLW9yaWdpbnMiLCJzZXNzaW9uX3N0YXRlIjoiNDk1MTcxMWUtNzg0My00OThkLWEyZTEtYTgxM2YwMDc5OTI3Iiwic2lkIjoiNDk1MTcxMWUtNzg0My00OThkLWEyZTEtYTgxM2YwMDc5OTI3Iiwic3ViIjoiZjQ2MmMxMTctYTU2OS00YmNiLWFjYzEtNTM4OTkyODJhMGM1Iiwic3ViX3R5cGUiOiJ1c2VyIiwidG9rZW5fc291cmNlIjoiZW50ZXJwcmlzZV9zd2l0Y2giLCJ0eXAiOiJCZWFyZXIifQ.nWJsvIK0vyoryBg9vFUR1v26tmcY9n9hjk7lGzYrsCrF2KrLhj06fA7BUbpX86nyXMH90fr74T8_NJfGU978ZhL8M-8U79De1bKph43K2LhVm6Rlb3LLPSrzrDm03SocBN4K05eTLFAba3RLbjptVSyg7tjUvJAD0hW4b5JbN7dcx5j4aWeJujXA3Z0xSBEAmijk5wy4vftGe_oDaTRP1v6dsaG2mQ-GOX_GJKz-EnPMoQ2N4sqGIJcr5ECovlUx8SgS_eOF8vo0o2j_-gD6dnrFnYoSwhIq-3l1wg8UKIDaE0r7AZntKV1vvf7mUtKcqXTVGFwuc3L4wJYLOMYDWw',
    'X-User-Id': 'f462c117-a569-4bcb-acc1-53899282a0c5',
    'X-Enterprise-Id': '',
    'X-Tenant-Id': '',
    'X-Domain': 'www.codebuddy.cn',
    'X-Product': 'SaaS',
    'X-Requested-With': 'XMLHttpRequest',
    'User-Agent': 'CLI/2.179.3 CodeBuddy/2.179.3',
    'X-IDE-Type': 'CLI',
    'X-IDE-Name': 'CLI',
    'X-IDE-Version': '2.179.3',
    'X-Auth-Method': 'enterprise_switch',
    'X-Userinfo': 'eyJ1aW4iOiJmNDYyYzExNy1hNTY5LTRiY2ItYWNjMS01Mzg5OTI4MmEwYzUiLCJ0b2tlbl9zb3VyY2UiOiJlbnRlcnByaXNlX3N3aXRjaCJ9',
    'X-Agent-Runtime': 'other',
    'X-Conversation-ID': 'c164fb4a-6501-9f60-e80f-5c9779c36400',
    'X-Request-ID': 'dc3e1dd533274aa6841296aeaec35cb1',
    'X-Conversation-Message-ID': 'dc3e1dd533274aa6841296aeaec35cb1',
    'X-Conversation-Request-ID': 'a557760b5d797c4fac676f3dea7d0649',
    'X-Root-Request-ID': 'a557760b5d797c4fac676f3dea7d0649',
    'X-Trace-ID': 'a557760b5d797c4fac676f3dea7d0649',
    'traceparent': '00-a557760b5d797c4fac676f3dea7d0649-e48c5e1ee5a00a60-01',
    'b3': 'a557760b5d797c4fac676f3dea7d0649-e48c5e1ee5a00a60-1-2ec6d6b42b8d9fd3',
    'X-B3-TraceId': 'a557760b5d797c4fac676f3dea7d0649',
    'X-B3-SpanId': 'e48c5e1ee5a00a60',
    'X-B3-ParentSpanId': '2ec6d6b42b8d9fd3',
    'X-B3-Sampled': '1',
    'Accept-Encoding': 'identity'
}


def iter_chunks(response):
    """Yield decoded SSE payloads, stopping at the [DONE] sentinel."""
    for line in response.iter_lines():
        line = line.strip()
        if not line or not line.startswith('data:'):
            continue
        data = line[5:].strip()
        if data == '[DONE]':
            return
        try:
            chunk = json.loads(data)
        except ValueError:
            print(f'\n[!] 非法 SSE 帧，已跳过：{data[:200]}', file=sys.stderr)
            continue
        if not isinstance(chunk, dict):
            print(f'\n[!] SSE 帧不是对象，已跳过：{data[:200]}', file=sys.stderr)
            continue
        yield chunk


def collect(response, *, raw_path=None, reasoning=False):
    """Stream the reply to the terminal and return the merged result."""
    raw = raw_path.open('w', encoding='utf-8') if raw_path else None
    state = {'model': None, 'usage': None, 'finish_reason': None, 'error': None,
             'content': [], 'reasoning': [], 'tools': {}}
    try:
        for chunk in iter_chunks(response):
            if raw is not None:
                raw.write(json.dumps(chunk, ensure_ascii=False) + '\n')
            if chunk.get('error') is not None:
                state['error'] = chunk['error']
                print(f'\n[!] 上游返回错误帧：{json.dumps(chunk["error"], ensure_ascii=False)}',
                      file=sys.stderr)
                break
            state['model'] = chunk.get('model') or state['model']
            state['usage'] = chunk.get('usage') or state['usage']
            for choice in chunk.get('choices') or []:
                state['finish_reason'] = choice.get('finish_reason') or state['finish_reason']
                delta = choice.get('delta') or {}
                if delta.get('content'):
                    state['content'].append(delta['content'])
                    sys.stdout.write(delta['content'])
                    sys.stdout.flush()
                if delta.get('reasoning_content'):
                    state['reasoning'].append(delta['reasoning_content'])
                    if reasoning:
                        sys.stderr.write(delta['reasoning_content'])
                        sys.stderr.flush()
                for call in delta.get('tool_calls') or []:
                    slot = state['tools'].setdefault(
                        call.get('index', 0), {'id': None, 'name': None, 'arguments': ''})
                    slot['id'] = call.get('id') or slot['id']
                    function = call.get('function') or {}
                    slot['name'] = function.get('name') or slot['name']
                    if isinstance(function.get('arguments'), str):
                        slot['arguments'] += function['arguments']
                    elif function.get('arguments'):
                        slot['arguments'] += json.dumps(function['arguments'], ensure_ascii=False)
    finally:
        if raw is not None:
            raw.close()
    return state


def summarize(state):
    print('\n' + '-' * 60)
    print(f"model:         {state['model']}")
    print(f"finish_reason: {state['finish_reason']}")
    print(f"content:       {len(''.join(state['content']))} chars")
    print(f"reasoning:     {len(''.join(state['reasoning']))} chars")
    if state['tools']:
        for index in sorted(state['tools']):
            call = state['tools'][index]
            print(f"tool[{index}]:      {call['name']} args={len(call['arguments'])} chars")
    else:
        print('tool_calls:    none')
    if state['usage'] is not None:
        print('usage:         ' + json.dumps(state['usage'], ensure_ascii=False))
    else:
        print('usage:         none（流式响应需 stream_options.include_usage）')
    if state['error'] is not None:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description='验证 CodeBuddy 上游流式 chat/completions 响应')
    parser.add_argument('--body', type=Path, default=DEFAULT_BODY, help='请求体 JSON 路径')
    parser.add_argument('--out', type=Path, default=None, help='把每帧 JSON 落盘，便于比对')
    parser.add_argument('--reasoning', action='store_true', help='把 reasoning_content 也打到终端')
    parser.add_argument('--timeout', type=float, default=600.0, help='读超时秒数')
    args = parser.parse_args()

    body = json.loads(args.body.read_text(encoding='utf-8'))
    if not body.get('stream'):
        raise SystemExit('[!] 请求体里 stream 不是 true，拿到的会是一次性 JSON 而不是流')

    timeout = httpx.Timeout(connect=20.0, read=args.timeout, write=60.0, pool=20.0)
    with httpx.Client(verify=False, timeout=timeout) as client, \
            client.stream('POST', STREAM_URL, json=body, headers=headers) as response:
        if response.status_code >= 400:
            response.read()
            print(f'[!] HTTP {response.status_code} {response.reason_phrase}', file=sys.stderr)
            print(response.text, file=sys.stderr)
            raise SystemExit(1)
        state = collect(response, raw_path=args.out, reasoning=args.reasoning)
    summarize(state)


if __name__ == '__main__':
    main()
