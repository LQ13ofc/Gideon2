#!/usr/bin/env python3
"""WP-6 measurements against a running llama-server on 127.0.0.1 (stdlib only; `python3 -I`).

Two independent views of each request:
  client  time to first content token (TTFT) and total time, measured on the socket.
  server  llama.cpp's own `timings` (prompt tokens/s, decode tokens/s), sent in the last SSE chunk.

Usage: python3 -I scripts/llm_bench.py --port 8080 [--runs 5] [--max-tokens 128]
Prints one JSON object. Prompts are fixed (BENCH_PROMPTS) so runs are comparable.
"""
import argparse
import http.client
import json
import statistics
import sys
import time

BENCH_PROMPTS = [
    "Explique em duas frases o que é um assistente de voz local.",
    "Liste três cuidados de segurança ao guardar uma chave de API no computador.",
    "Resuma em uma frase: o sol é uma estrela.",
    "Escreva uma pergunta curta que um usuário poderia fazer a um assistente pessoal.",
    "Quanto é 17 vezes 3? Responda só com o número.",
]
SYSTEM = "Você é um assistente local. Responda em português, de forma curta."


def stream_chat(port, messages, max_tokens, timeout=180):
    """One streamed chat. Returns the measurements and the text (never logged by callers)."""
    body = json.dumps({"model": "local", "messages": messages, "max_tokens": max_tokens,
                       "stream": True, "temperature": 0.0}).encode("utf-8")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    started = time.monotonic()
    conn.request("POST", "/v1/chat/completions", body=body,
                 headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    response = conn.getresponse()
    if response.status != 200:
        conn.close()
        raise RuntimeError("http_status_%d" % response.status)
    ttft = None
    parts = []
    timings = None
    finish = None
    buffer = b""
    while True:
        chunk = response.read1(65536)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                continue
            obj = json.loads(payload)
            if isinstance(obj.get("timings"), dict):
                timings = obj["timings"]
            for choice in obj.get("choices") or []:
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
                content = (choice.get("delta") or {}).get("content")
                if content:
                    if ttft is None:
                        ttft = time.monotonic() - started
                    parts.append(content)
    total = time.monotonic() - started
    conn.close()
    return {"ttft_s": ttft, "total_s": total, "text": "".join(parts), "finish": finish,
            "server_timings": timings}


def summarize(results):
    ttfts = [r["ttft_s"] for r in results if r["ttft_s"] is not None]
    decode = [r["server_timings"]["predicted_per_second"] for r in results
              if r["server_timings"] and r["server_timings"].get("predicted_per_second")]
    prompt = [r["server_timings"]["prompt_per_second"] for r in results
              if r["server_timings"] and r["server_timings"].get("prompt_per_second")]
    tokens = [r["server_timings"]["predicted_n"] for r in results
              if r["server_timings"] and r["server_timings"].get("predicted_n") is not None]
    out = {"runs": len(results), "ttft_s_median": round(statistics.median(ttfts), 3) if ttfts else None,
           "ttft_s_min": round(min(ttfts), 3) if ttfts else None,
           "ttft_s_max": round(max(ttfts), 3) if ttfts else None,
           "decode_tokens_per_s_median": round(statistics.median(decode), 2) if decode else None,
           "prompt_tokens_per_s_median": round(statistics.median(prompt), 2) if prompt else None,
           "generated_tokens_per_run": tokens}
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=128)
    args = parser.parse_args(argv)
    results = []
    for index in range(args.runs):
        prompt = BENCH_PROMPTS[index % len(BENCH_PROMPTS)]
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        result = stream_chat(args.port, messages, args.max_tokens)
        results.append(result)
    report = summarize(results)
    report["ok"] = True
    report["texts_chars"] = [len(r["text"]) for r in results]
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
