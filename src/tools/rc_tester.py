#!/usr/bin/env python3
import argparse
import json
import socket
import time
from json import JSONDecodeError

def extract_json_objects(buffer: str):
    """Yield consecutive JSON objects from a string, ignoring whitespace between them."""
    dec = json.JSONDecoder()
    i, n = 0, len(buffer)
    while True:
        while i < n and buffer[i].isspace():
            i += 1
        if i >= n:
            return
        obj, end = dec.raw_decode(buffer, i)
        yield obj
        i = end

def iter_messages_from_file(path: str, mode: str):
    """
    mode='line': yield raw lines (stripped), skipping empties.
    mode='json': parse and re-serialize each JSON object into a single line.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()

    if mode == "line":
        for ln in data.splitlines():
            msg = ln.strip()
            if msg:
                yield msg
    else:
        # mode == "json"
        for obj in extract_json_objects(data):
            # Re-serialize compact (single line); keep non-ASCII as UTF-8
            yield json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

def send_and_recv_once(host: str, port: int, payload: str, timeout: float = 5.0):
    """
    Opens a TCP connection, sends payload + '\n', reads until server closes
    the connection (or timeout). Returns (elapsed_seconds, response_text).
    """
    start = time.time()
    buf = bytearray()
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(payload.encode("utf-8") + b"\n")
        # server is expected to close after replying
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
            except socket.timeout:
                break
    elapsed = time.time() - start
    return elapsed, buf.decode("utf-8", errors="replace").rstrip("\r\n")

def main():
    ap = argparse.ArgumentParser(description="Rendezvous server tester (one connection per message).")
    ap.add_argument("file", help="Path to test sequence file")
    ap.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    ap.add_argument("--port", type=int, default=5000, help="Server port (default: 5000)")
    ap.add_argument("--mode", choices=["line", "json"], default="line",
                    help="Read mode: 'line' sends each line verbatim; 'json' extracts concatenated JSONs")
    ap.add_argument("--delay", type=float, default=0.0, help="Delay (seconds) between requests")
    ap.add_argument("--timeout", type=float, default=5.0, help="Socket timeout in seconds (default: 5)")
    args = ap.parse_args()

    total = ok = err = 0
    for i, msg in enumerate(iter_messages_from_file(args.file, args.mode), start=1):
        total += 1
        print(f"\n[{i}] ➜ Sending: {msg}")
        try:
            t, resp = send_and_recv_once(args.host, args.port, msg, timeout=args.timeout)
        except Exception as e:
            err += 1
            print(f"[{i}] ✖ Connection error: {e}")
            if args.delay > 0:
                time.sleep(args.delay)
            continue

        print(f"[{i}] ⇦ Received ({t*1000:.1f} ms): {resp}")

        # Try to parse response to check status
        try:
            j = json.loads(resp)
            status = j.get("status")
            if status == "OK":
                ok += 1
            else:
                err += 1
        except JSONDecodeError:
            err += 1

        if args.delay > 0:
            time.sleep(args.delay)

    print("\n==== Summary ====")
    print(f"Total: {total} | OK: {ok} | Errors: {err}")

if __name__ == "__main__":
    main()
