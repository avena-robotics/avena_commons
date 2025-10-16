#!/usr/bin/env python3
"""Porownanie dzialania ControlLoop w trybie zsynchronizowanym i luznym."""

from __future__ import annotations

import argparse
import multiprocessing as mp
import queue
import sys
import threading
import time
from dataclasses import dataclass
from statistics import mean
from typing import Iterable, List, Tuple

from avena_commons.util.control_loop import ControlLoop  # type: ignore  # noqa: E402
from avena_commons.util.loop_sync import LoopSynchronizer  # type: ignore  # noqa: E402


@dataclass
class LoopResult:
    """Przechowuje wyniki pojedynczej pętli."""

    name: str
    period_ns: int
    timestamps_ns: List[int]

    def deltas_ns(self) -> List[int]:
        """Zwraca różnice czasów startów między kolejnymi iteracjami."""
        return [
            self.timestamps_ns[idx] - self.timestamps_ns[idx - 1]
            for idx in range(1, len(self.timestamps_ns))
        ]

    def expected_ns(self) -> List[int]:
        """Buduje idealny harmonogram startów dla zadanej częstotliwości."""
        base = self.timestamps_ns[0]
        return [base + idx * self.period_ns for idx in range(len(self.timestamps_ns))]


def _format_series(values_ns: Iterable[int]) -> str:
    values_us = [v / 1_000 for v in values_ns]
    return ", ".join(f"{val:+.3f}" for val in values_us[:10])


def _run_loop(
    name: str,
    iterations: int,
    period_s: float,
    synchronizer: LoopSynchronizer | None,
    collector: "queue.Queue[LoopResult]",
    workload_ratio: float,
    auto_synchronizer: bool = True,
) -> None:
    loop = ControlLoop(
        name, period_s, synchronizer=synchronizer, auto_synchronizer=auto_synchronizer
    )
    timestamps: List[int] = []
    period_ns = int(period_s * 1e9)
    workload_s = period_s * workload_ratio
    for _ in range(iterations):
        loop.loop_begin()
        if workload_s:
            time.sleep(workload_s)
        timestamps.append(loop.last_start_ns)
        loop.loop_end()
    collector.put(LoopResult(name, period_ns, timestamps))


def _print_stats(results: List[LoopResult], title: str) -> None:
    print(f"\n=== {title} ===")
    warmup = 2
    ordered = sorted(results, key=lambda r: r.name)
    for result in ordered:
        trimmed = result.timestamps_ns[warmup:]
        expected = result.expected_ns()[warmup:]
        jitter = [actual - exp for actual, exp in zip(trimmed, expected, strict=True)]
        jitter_cycle = [
            (d - result.period_ns) for d in result.deltas_ns()[warmup - 1 :]
        ]
        max_jitter_ms = max(abs(j) for j in jitter) / 1e6 if jitter else 0.0
        mean_jitter_ms = mean(abs(j) for j in jitter) / 1e6 if jitter else 0.0
        print(
            f"{result.name}: "
            f"max_phase_error={max_jitter_ms:.3f} ms, "
            f"mean_phase_error={mean_jitter_ms:.3f} ms, "
            f"cycle_jitter(us)={_format_series(jitter_cycle)}"
        )
    same_period = len({res.period_ns for res in ordered}) == 1
    if same_period and len(ordered) >= 2:
        diffs = [
            (a - b)
            for a, b in zip(
                ordered[0].timestamps_ns[warmup:],
                ordered[1].timestamps_ns[warmup:],
                strict=True,
            )
        ]
        print(
            f"Delta między {ordered[0].name} i {ordered[1].name} (us): {_format_series(diffs)}"
        )
    elif len(ordered) >= 2:
        print("Uwaga: pętle mają różne okresy, różnice faz podano osobno.")


def threaded_demo(
    periods: Tuple[float, float], iterations: int, sync: bool, workload: float
) -> None:
    label = "Synchronizowane" if sync else "Bez synchronizacji"
    synchronizer = LoopSynchronizer() if sync else None
    collector: "queue.Queue[LoopResult]" = queue.Queue()

    threads = [
        threading.Thread(
            target=_run_loop,
            args=(
                f"thread-{idx}",
                iterations,
                period,
                synchronizer,
                collector,
                workload,
                sync,
            ),
            daemon=True,
        )
        for idx, period in enumerate(periods)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    results = [collector.get_nowait() for _ in threads]
    _print_stats(results, f"Wątki: {label}")


def _process_worker(
    name: str,
    iterations: int,
    period_s: float,
    workload_ratio: float,
    base_time_ns: int,
    barrier: mp.Barrier,
    queue_: mp.Queue,
) -> None:
    loop = ControlLoop(name, period_s)
    barrier.wait()
    timestamps: List[int] = []
    period_ns = int(period_s * 1e9)
    workload_s = period_s * workload_ratio
    for _ in range(iterations):
        loop.loop_begin()
        if workload_s:
            time.sleep(workload_s)
        timestamps.append(loop.last_start_ns)
        loop.loop_end()
    queue_.put(LoopResult(name, period_ns, timestamps))


def multiprocess_demo(period: float, iterations: int, workload: float) -> None:
    print("\n=== Procesy: Synchronizowane wspólną epoką ===")
    now_ns = time.perf_counter_ns()
    period_ns = int(period * 1e9)
    base_time_ns = ((now_ns + period_ns * 5) // period_ns) * period_ns

    queue_: mp.Queue = mp.Queue()
    barrier = mp.Barrier(3)
    processes = [
        mp.Process(
            target=_process_worker,
            args=(
                f"proc-{idx}",
                iterations,
                period,
                workload,
                base_time_ns,
                barrier,
                queue_,
            ),
            daemon=True,
        )
        for idx in range(2)
    ]

    for proc in processes:
        proc.start()
    barrier.wait()
    for proc in processes:
        proc.join()

    results = [queue_.get(timeout=5) for _ in processes]
    _print_stats(results, "Procesy: Wspólny takt")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--iterations",
        type=int,
        default=40,
        help="Liczba kroków na pętlę (domyślnie: 40)",
    )
    parser.add_argument(
        "--periods",
        type=float,
        nargs=2,
        default=(0.01, 0.01),
        help="Okresy (s) dwóch pętli w obrębie procesu (domyślnie: 10 ms, 10 ms)",
    )
    parser.add_argument(
        "--show-unsync",
        action="store_true",
        help="Pokaż również scenariusz bez synchronizacji (porównanie).",
    )
    parser.add_argument(
        "--process-period",
        type=float,
        default=0.005,
        help="Okres (s) przy demonstracji wieloprocesowej (domyślnie: 5 ms).",
    )
    parser.add_argument(
        "--workload-ratio",
        type=float,
        default=0.25,
        help="Udział czasu okresu przeznaczony na symulowane obciążenie (0..1).",
    )
    args = parser.parse_args(argv)

    if args.show_unsync:
        threaded_demo(
            tuple(args.periods),
            args.iterations,
            sync=False,
            workload=args.workload_ratio,
        )

    threaded_demo(
        tuple(args.periods), args.iterations, sync=True, workload=args.workload_ratio
    )
    multiprocess_demo(
        args.process_period, args.iterations, workload=args.workload_ratio
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
