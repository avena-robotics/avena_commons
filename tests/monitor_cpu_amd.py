#!/usr/bin/env python3
# (content truncated in chat; full code included in this file)
# See previous cell for detailed docstring.
import argparse, csv, glob, json, os, time, statistics as stats, subprocess
from pathlib import Path
from datetime import datetime

try:
    import psutil
except ImportError:
    raise SystemExit("Please install psutil:  pip install psutil")

TEMP_THRESHOLD_C = 90.0
UTIL_THRESHOLD_PCT = 85.0
DROP_PCT_THRESHOLD = 10.0
CONSEC_SECONDS = 5


def read_cur_freqs_mhz():
    freqs = []
    cpu_dirs = sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*"))
    for cpu_dir in cpu_dirs:
        for fn in ("scaling_cur_freq", "cpuinfo_cur_freq"):
            p = Path(cpu_dir) / "cpufreq" / fn
            if p.exists():
                try:
                    khz = int(p.read_text().strip())
                    if khz > 0:
                        freqs.append(khz / 1000.0)
                        break
                except Exception:
                    pass
    if freqs:
        return freqs
    try:
        mhz_vals = []
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "cpu MHz" in line:
                    mhz_vals.append(float(line.split(":")[1].strip()))
        return mhz_vals
    except Exception:
        return []


def read_ref_max_freq_mhz():
    max_mhz = 0.0
    for cpu_dir in glob.glob("/sys/devices/system/cpu/cpu[0-9]*"):
        for fn in ("cpuinfo_max_freq", "scaling_max_freq"):
            p = Path(cpu_dir) / "cpufreq" / fn
            if p.exists():
                try:
                    mhz = int(p.read_text().strip()) / 1000.0
                    max_mhz = max(max_mhz, mhz)
                except Exception:
                    pass
    return max_mhz or None


def read_amd_temps():
    res = {"tctl": None, "tdie": None, "ccd_max": None, "ccd_avg": None}
    hwmons = []
    for dev in glob.glob("/sys/class/hwmon/hwmon*"):
        name_p = Path(dev) / "name"
        if name_p.exists():
            name = name_p.read_text().strip().lower()
            if "k10temp" in name or "zenpower" in name:
                hwmons.append(dev)
    temps = []
    for dev in hwmons:
        for i in range(1, 32):
            tin = Path(dev) / f"temp{i}_input"
            if not tin.exists():
                continue
            try:
                val = int(tin.read_text().strip()) / 1000.0
            except Exception:
                continue
            tlabel = Path(dev) / f"temp{i}_label"
            label = tlabel.read_text().strip().lower() if tlabel.exists() else ""
            if "tctl" in label:
                res["tctl"] = val
            elif "tdie" in label:
                res["tdie"] = val
            elif "ccd" in label:
                temps.append(val)
            else:
                if res["tctl"] is None and i == 1 and not tlabel.exists():
                    res["tctl"] = val
                temps.append(val)
    if temps:
        res["ccd_max"] = max(temps)
        res["ccd_avg"] = sum(temps) / len(temps)
    return res


def percentiles(values, ps=(50, 90, 95, 99)):
    if not values:
        return {}
    res = {}
    for p in ps:
        k = (len(values) - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, len(values) - 1)
        if f == c:
            val = values[f]
        else:
            d0 = values[f] * (c - k)
            d1 = values[c] * (k - f)
            val = d0 + d1
        res[p] = val
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=3600)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--csv", type=str, default="")
    ap.add_argument("--md", type=str, default="")
    ap.add_argument("--tag", type=str, default="")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = Path(args.csv or f"./cpu_monitor_amd_{ts}.csv").resolve()
    md_path = Path(args.md or f"./cpu_report_amd_{ts}.md").resolve()

    psutil.cpu_percent(interval=None, percpu=True)

    fields = [
        "time",
        "cpu_total_percent",
        "avg_freq_mhz",
        "tctl_c",
        "tdie_c",
        "ccd_max_c",
        "ccd_avg_c",
        "freq_drop_pct",
    ]
    rows = []

    total_series, freq_series, drop_series = [], [], []
    tctl_s, tdie_s, tccdm_s, tccda_s = [], [], [], []

    ref_max_freq = read_ref_max_freq_mhz()
    observed_max_avg_freq = 0.0

    consec = 0
    events = []
    in_event = False
    cur_event = {"start": None, "max_drop": 0.0, "peak_temp": 0.0}

    t0 = time.time()
    next_sample = t0
    while True:
        now = time.time()
        if now >= t0 + args.seconds:
            break

        per_core = psutil.cpu_percent(interval=None, percpu=True)
        total = (
            sum(per_core) / len(per_core)
            if per_core
            else psutil.cpu_percent(interval=None)
        )

        freqs = read_cur_freqs_mhz()
        avg_freq = sum(freqs) / len(freqs) if freqs else None
        if avg_freq and avg_freq > observed_max_avg_freq:
            observed_max_avg_freq = avg_freq
        ref = ref_max_freq or (
            observed_max_avg_freq if observed_max_avg_freq > 0 else None
        )
        drop_pct = None
        if ref and avg_freq:
            drop_pct = max(0.0, (ref - avg_freq) / ref * 100.0)

        temps = read_amd_temps()
        tctl, tdie, tccdm, tccda = (
            temps["tctl"],
            temps["tdie"],
            temps["ccd_max"],
            temps["ccd_avg"],
        )

        rows.append({
            "time": datetime.now().isoformat(),
            "cpu_total_percent": round(total, 2),
            "avg_freq_mhz": round(avg_freq, 1) if avg_freq else "",
            "tctl_c": round(tctl, 1) if isinstance(tctl, (int, float)) else "",
            "tdie_c": round(tdie, 1) if isinstance(tdie, (int, float)) else "",
            "ccd_max_c": round(tccdm, 1) if isinstance(tccdm, (int, float)) else "",
            "ccd_avg_c": round(tccda, 1) if isinstance(tccda, (int, float)) else "",
            "freq_drop_pct": round(drop_pct, 2)
            if isinstance(drop_pct, (int, float))
            else "",
        })

        if isinstance(total, (int, float)):
            total_series.append(float(total))
        if isinstance(avg_freq, (int, float)):
            freq_series.append(float(avg_freq))
        if isinstance(drop_pct, (int, float)):
            drop_series.append(float(drop_pct))
        if isinstance(tctl, (int, float)):
            tctl_s.append(float(tctl))
        if isinstance(tdie, (int, float)):
            tdie_s.append(float(tdie))
        if isinstance(tccdm, (int, float)):
            tccdm_s.append(float(tccdm))
        if isinstance(tccda, (int, float)):
            tccda_s.append(float(tccda))

        temp_for_heur = (
            tdie
            if isinstance(tdie, (int, float))
            else (tctl if isinstance(tctl, (int, float)) else None)
        )
        cond = (
            isinstance(temp_for_heur, (int, float))
            and temp_for_heur >= TEMP_THRESHOLD_C
            and isinstance(total, (int, float))
            and total >= UTIL_THRESHOLD_PCT
            and isinstance(drop_pct, (int, float))
            and drop_pct >= DROP_PCT_THRESHOLD
        )
        if cond:
            consec += 1
            if not in_event and consec >= CONSEC_SECONDS:
                in_event = True
                cur_event = {
                    "start": datetime.now().isoformat(),
                    "max_drop": drop_pct,
                    "peak_temp": temp_for_heur,
                }
            elif in_event:
                cur_event["max_drop"] = max(cur_event["max_drop"], drop_pct)
                cur_event["peak_temp"] = max(cur_event["peak_temp"], temp_for_heur)
        else:
            consec = 0
            if in_event:
                in_event = False
                cur_event["end"] = datetime.now().isoformat()
                events.append(cur_event)
                cur_event = {"start": None, "max_drop": 0.0, "peak_temp": 0.0}

        next_sample += args.interval
        time.sleep(max(0.0, next_sample - time.time()))

    if in_event and cur_event.get("start"):
        cur_event["end"] = datetime.now().isoformat()
        events.append(cur_event)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    def summarize(series):
        if not series:
            return None
        ss = sorted(series)
        return {
            "avg": sum(series) / len(series),
            "max": max(series),
            "min": min(series),
            "stdev": stats.pstdev(series) if len(series) > 1 else 0.0,
            "p": percentiles(ss, (50, 90, 95, 99)),
        }

    s_total = summarize(total_series)
    s_freq = summarize(freq_series)
    s_drop = summarize(drop_series)
    s_tctl = summarize(tctl_s)
    s_tdie = summarize(tdie_s)
    s_tccdm = summarize(tccdm_s)
    s_tccda = summarize(tccda_s)

    total_event_seconds = 0
    worst_drop = 0.0
    for e in events:
        try:
            t_start = datetime.fromisoformat(e["start"])
            t_end = datetime.fromisoformat(e["end"])
            total_event_seconds += max(0, int((t_end - t_start).total_seconds()))
            worst_drop = max(worst_drop, e.get("max_drop", 0.0))
        except Exception:
            pass

    lines = []
    lines.append("# CPU Test Report (AMD)\n")
    lines.append(f"- Timestamp: `{datetime.now().isoformat()}`")
    lines.append(
        f"- Duration: `{len(rows)} samples @ {args.interval}s` ≈ `{len(rows) * args.interval:.1f}s`"
    )
    if args.tag:
        lines.append(f"- Tag: `{args.tag}`")
    ref_max = read_ref_max_freq_mhz()
    if ref_max:
        lines.append(f"- Reference max frequency: `{ref_max:.1f} MHz` (sysfs)")
    lines.append(f"- CSV: `{csv_path}`\n")

    def block(title, s, unit):
        if not s:
            return [f"## {title}\n\n*(no data)*\n"]
        p = s["p"]
        return [
            f"## {title}\n",
            "| Metric | Value |",
            "|---|---:|",
            f"| avg | {s['avg']:.2f}{unit} |",
            f"| max | {s['max']:.2f}{unit} |",
            f"| min | {s['min']:.2f}{unit} |",
            f"| stdev | {s['stdev']:.2f}{unit} |",
            f"| p50 | {p.get(50, float('nan')):.2f}{unit} |",
            f"| p90 | {p.get(90, float('nan')):.2f}{unit} |",
            f"| p95 | {p.get(95, float('nan')):.2f}{unit} |",
            f"| p99 | {p.get(99, float('nan')):.2f}{unit} |",
            "",
        ]

    lines += block("CPU total utilization (%)", s_total, "%")
    lines += block("Average CPU frequency (MHz)", s_freq, " MHz")
    lines += block("AMD Tctl (°C)", s_tctl, "°C")
    lines += block("AMD Tdie (°C)", s_tdie, "°C")
    lines += block("AMD CCD max (°C)", s_tccdm, "°C")
    lines += block("AMD CCD avg (°C)", s_tccda, "°C")

    lines.append("## AMD thermal downclock heuristic\n")
    lines.append(
        f"- Conditions: temp ≥ {TEMP_THRESHOLD_C}°C, CPU ≥ {UTIL_THRESHOLD_PCT}%, freq drop ≥ {DROP_PCT_THRESHOLD}% for ≥ {CONSEC_SECONDS}s.\n"
    )
    if events:
        lines.append(
            f"- Events detected: **{len(events)}**, total time: **{total_event_seconds}s**, worst drop: **{worst_drop:.2f}%**\n"
        )
        lines.append("| Start | End | Duration [s] | Max drop [%] | Peak temp [°C] |")
        lines.append("|---|---|---:|---:|---:|")
        for e in events:
            try:
                t_start = datetime.fromisoformat(e["start"])
                t_end = datetime.fromisoformat(e["end"])
                dur = int((t_end - t_start).total_seconds())
            except Exception:
                dur = ""
            lines.append(
                f"| {e.get('start', '')} | {e.get('end', '')} | {dur} | {e.get('max_drop', 0.0):.2f} | {e.get('peak_temp', 0.0):.1f} |"
            )
        lines.append("")
    else:
        lines.append("- No AMD downclock events matched the heuristic.\n")

    lines.append("## Notes\n")
    lines.append(
        "- Temps read from `/sys/class/hwmon` (k10temp/zenpower). If empty, check BIOS/UEFI sensor exposure or kernel modules."
    )
    lines.append(
        "- `sudo sensors-detect` may help assign labels, but is not required.\n"
    )

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"CSV: {csv_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
