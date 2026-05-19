#!/usr/bin/env python3
import asyncio
import ssl
import sys
import argparse
from pathlib import Path

DEFAULT_TIMEOUT = 5.0
DEFAULT_CONCURRENCY = 50

async def probe_sni(sni, ip, port, timeout):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    reader, writer = None, None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host=ip, port=port, ssl=ctx, server_hostname=sni),
            timeout=timeout
        )
        return sni, True
    except:
        return sni, False
    finally:
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass

def render_progress_bar(done, total, current_sni, status, bar_length=20):
    if total == 0:
        return
    fraction = done / total
    filled_length = int(bar_length * fraction)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    percent = int(fraction * 100)
    
    display_sni = (current_sni[:30] + '..') if len(current_sni) > 30 else current_sni
    output = f"\r\033[K {bar} {percent:3}% | {done}/{total} | {display_sni} -> {status}"
    sys.stdout.write(output)
    sys.stdout.flush()

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ip")
    parser.add_argument("port", type=int)
    parser.add_argument("--sni-path", default="sni.txt")
    parser.add_argument("--out", default="valid_snis.txt")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    
    args = parser.parse_args()

    path = Path(args.sni-path)
    domains = []
    if path.is_file():
        domains = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    elif path.is_dir():
        for f in path.glob("*.txt"):
            domains.extend([ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")])
    
    domains = list(set(domains))
    total = len(domains)
    if not domains:
        print("Список SNI пуст.")
        return

    print(f"Цель: {args.ip}:{args.port} | Потоков: {args.concurrency}\n")
    
    queue = asyncio.Queue()
    for d in domains:
        queue.put_nowait(d)

    processed = 0
    valid_snis = []
    lock = asyncio.Lock()

    async def worker():
        nonlocal processed
        while True:
            try:
                sni = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            
            res_sni, is_ok = await probe_sni(sni, args.ip, args.port, args.timeout)
            processed += 1
            
            status_text = "OK" if is_ok else "FAIL"
            render_progress_bar(processed, total, sni, status_text)
            
            if is_ok:
                async with lock:
                    valid_snis.append(res_sni)
            
            queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(args.concurrency)]
    
    await asyncio.gather(*workers)
    
    with open(args.out, "w", encoding="utf-8") as f:
        for sni in valid_snis:
            f.write(f"{sni}\n")
                
    print(f"\n\nЗавершено! Найдено рабочих: {len(valid_snis)}")
    print(f"Результат: {args.out}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПрервано.")
