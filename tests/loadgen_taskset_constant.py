#!/usr/bin/env python3
import argparse, os, re, sys, time, subprocess

WORKER_CODE = r"""
import time, sys, signal, math
running = True
def handler(signum, frame):
    global running
    running = False
import signal
signal.signal(signal.SIGTERM, handler)
signal.signal(signal.SIGINT, handler)

MIN_REST_US = 800
FRAME_US    = 10_000

def compute_slices(base_load):
    base_load = max(0.0, min(100.0, base_load))
    load_frac = base_load/100.0
    rest_us = int((1.0 - load_frac) * FRAME_US)
    if rest_us < MIN_REST_US and load_frac < 0.999:
        FRAME2 = int(math.ceil(MIN_REST_US / (1.0 - load_frac)))
        work_us = int(load_frac * FRAME2)
        rest_us = FRAME2 - work_us
        return work_us, rest_us
    work_us = FRAME_US - rest_us
    return work_us, rest_us

def run(seconds: int, base_load: float):
    work_us, rest_us = compute_slices(base_load)
    t_end = time.time() + seconds
    while running and time.time() < t_end:
        t0 = time.perf_counter_ns()
        while (time.perf_counter_ns() - t0) < (work_us * 1000):
            pass
        if rest_us > 0:
            sleep_s = max(0.0, (rest_us - 300) / 1_000_000)
            if sleep_s > 0:
                time.sleep(sleep_s)
            t1 = time.perf_counter_ns()
            while (time.perf_counter_ns() - t1) < (300 * 1000):
                pass

if __name__ == "__main__":
    seconds    = int(sys.argv[1])
    base_load  = float(sys.argv[2])
    run(seconds, base_load)
"""


def parse_cores(spec: str):
    cores = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)-(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            cores.extend(range(min(a, b), max(a, b) + 1))
        else:
            cores.append(int(part))
    return sorted(set(cores))


def cpus_allowed_list(pid: int) -> str:
    with open(f"/proc/{pid}/status", "r") as f:
        for line in f:
            if line.startswith("Cpus_allowed_list"):
                return line.split(":")[1].strip()
    return ""


def main():
    ap = argparse.ArgumentParser(
        description="Constant per-core CPU load via taskset (no bursts)."
    )
    ap.add_argument("--seconds", type=int, default=3600)
    ap.add_argument("--cores", type=str, required=True, help="CPU list like 0-9,12,14")
    ap.add_argument(
        "--load", type=float, default=95.0, help="Target load percent (e.g., 95.0)"
    )
    args = ap.parse_args()

    if not shutil.which("taskset"):
        print("ERROR: 'taskset' not found. Install 'util-linux'.", file=sys.stderr)
        sys.exit(2)

    cores = parse_cores(args.cores)
    if not cores:
        print("No cores parsed from --cores", file=sys.stderr)
        sys.exit(2)

    procs = []
    try:
        for c in cores:
            cmd = [
                "taskset",
                "-c",
                str(c),
                sys.executable,
                "-u",
                "-c",
                WORKER_CODE,
                str(args.seconds),
                str(args.load),
            ]
            p = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(0.05)
            allowed = cpus_allowed_list(p.pid)
            if allowed not in (str(c), f"{c}-{c}"):
                raise RuntimeError(
                    f"Worker PID {p.pid} NOT pinned to CPU {c} (Cpus_allowed_list={allowed})"
                )
            print(f"[OK] PID {p.pid} pinned to CPU {c} (Cpus_allowed_list={allowed})")
            procs.append(p)

        t_end = time.time() + args.seconds
        while time.time() < t_end:
            time.sleep(0.5)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=1.0)
            except Exception:
                p.kill()
        sys.exit(1)
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=1.0)
            except Exception:
                p.kill()


if __name__ == "__main__":
    import shutil

    main()
