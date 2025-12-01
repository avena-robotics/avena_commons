import json
import multiprocessing as mp
import queue
import threading
import time
from statistics import mean

import pytest

from avena_commons.util.control_loop import ControlLoop
from avena_commons.util.loop_sync import LoopSynchronizer


def _run_threaded_loop(
    name: str,
    iterations: int,
    period_s: float,
    workload_s: float,
    synchronizer: LoopSynchronizer,
    output_queue: "queue.Queue[list[int]]",
) -> None:
    loop = ControlLoop(name, period_s, synchronizer=synchronizer)
    timestamps: list[int] = []
    for _ in range(iterations):
        loop.loop_begin()
        if workload_s > 0:
            time.sleep(workload_s)
        timestamps.append(loop.last_start_ns)
        loop.loop_end()
    output_queue.put(timestamps)


def test_threaded_loops_align_within_tolerance():
    iterations = 40
    period_s = 0.01  # 100 Hz
    synchronizer = LoopSynchronizer()

    results: "queue.Queue[list[int]]" = queue.Queue()

    threads = [
        threading.Thread(
            target=_run_threaded_loop,
            args=(f"loop-{idx}", iterations, period_s, 0.001, synchronizer, results),
            daemon=True,
        )
        for idx in range(2)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    data = [results.get(timeout=2) for _ in threads]
    for timestamps in data:
        assert len(timestamps) == iterations

    # Ignore a couple of initial warm-up cycles.
    warmup = 2
    trimmed = [timestamps[warmup:] for timestamps in data]

    per_iteration_diffs = [
        abs(a - b) for a, b in zip(trimmed[0], trimmed[1], strict=True)
    ]
    max_diff_ns = max(per_iteration_diffs)
    assert max_diff_ns < 1_000_000, f"threads drifted by {max_diff_ns} ns"


def _process_worker(
    name: str,
    iterations: int,
    period_s: float,
    workload_s: float,
    base_time_ns: int,
    queue_: mp.Queue,
) -> None:
    synchronizer = LoopSynchronizer(base_time_ns=base_time_ns)
    loop = ControlLoop(name, period_s, synchronizer=synchronizer)
    timestamps: list[int] = []
    for _ in range(iterations):
        loop.loop_begin()
        if workload_s > 0:
            time.sleep(workload_s)
        timestamps.append(loop.last_start_ns)
        loop.loop_end()
    queue_.put((name, timestamps))


@pytest.mark.parametrize("period_s", [0.005, 0.0025])
def test_processes_share_base_time(period_s):
    iterations = 30
    workload_s = period_s / 4
    period_ns = int(period_s * 1e9)

    now_ns = time.perf_counter_ns()
    base_time_ns = ((now_ns + period_ns * 10) // period_ns) * period_ns

    result_queue: mp.Queue = mp.Queue()
    processes = [
        mp.Process(
            target=_process_worker,
            args=(
                f"proc-{idx}",
                iterations,
                period_s,
                workload_s,
                base_time_ns,
                result_queue,
            ),
            daemon=True,
        )
        for idx in range(2)
    ]

    for proc in processes:
        proc.start()
    for proc in processes:
        proc.join(timeout=15)

    results = {}
    while len(results) < len(processes):
        name, timestamps = result_queue.get(timeout=5)
        results[name] = timestamps

    assert all(len(ts) == iterations for ts in results.values())

    warmup = 2
    expected_sequence = [
        base_time_ns + period_ns * (idx + 1) for idx in range(iterations)
    ][warmup:]
    jitters = []
    for timestamps in results.values():
        trimmed = timestamps[warmup:]
        diffs = [abs(t - e) for t, e in zip(trimmed, expected_sequence, strict=True)]
        jitters.extend(diffs)
    max_jitter_ns = max(jitters)
    mean_jitter_ns = mean(jitters)

    assert max_jitter_ns < 1_500_000, f"max jitter {max_jitter_ns} ns too high"
    assert mean_jitter_ns < 500_000, f"mean jitter {mean_jitter_ns} ns too high"

    ordered = [timestamps for _, timestamps in sorted(results.items())]
    first, second = ordered
    per_iter_diff = [
        abs(a - b) for a, b in zip(first[warmup:], second[warmup:], strict=True)
    ]
    assert max(per_iter_diff) < 1_200_000, "processes diverged more than tolerance"


def test_mixed_frequencies_share_phase():
    synchronizer = LoopSynchronizer()
    coarse_period = 0.01  # 100 Hz
    fine_period = 0.002  # 500 Hz
    coarse_iterations = 20
    ratio = int(coarse_period / fine_period)
    fine_iterations = coarse_iterations * ratio

    results: "queue.Queue[tuple[str, list[int]]]" = queue.Queue()
    barrier = threading.Barrier(3)

    def worker(name: str, period: float, iterations: int) -> None:
        loop = ControlLoop(name, period, synchronizer=synchronizer)
        barrier.wait()
        stamps: list[int] = []
        for _ in range(iterations):
            loop.loop_begin()
            stamps.append(loop.last_start_ns)
            loop.loop_end()
        results.put((name, stamps))

    threads = [
        threading.Thread(
            target=worker,
            args=("coarse", coarse_period, coarse_iterations),
            daemon=True,
        ),
        threading.Thread(
            target=worker, args=("fine", fine_period, fine_iterations), daemon=True
        ),
    ]

    for t in threads:
        t.start()
    barrier.wait()
    for t in threads:
        t.join(timeout=10)

    collected = dict(results.get(timeout=2) for _ in threads)
    coarse = collected["coarse"]
    fine = collected["fine"]

    warmup = 2
    coarse_trimmed = coarse[warmup:]
    fine_period_ns = int(fine_period * 1e9)
    offset_slots = max(0, round((coarse[0] - fine[0]) / fine_period_ns))
    fine_start = offset_slots + warmup * ratio
    expected_from_fine = fine[
        fine_start : fine_start + len(coarse_trimmed) * ratio : ratio
    ]
    paired_length = min(len(coarse_trimmed), len(expected_from_fine))
    diffs = [
        abs(a - b) for a, b in zip(coarse_trimmed[:paired_length], expected_from_fine)
    ]
    assert max(diffs) < 800_000, f"phase misalignment {max(diffs)} ns"


def test_default_epoch_file_shared(tmp_path, monkeypatch):
    epoch_file = tmp_path / "epoch.json"
    monkeypatch.setenv("CONTROL_LOOP_EPOCH_FILE", str(epoch_file))

    loop_a = ControlLoop("loop-a", 0.01)
    loop_b = ControlLoop("loop-b", 0.02)

    assert epoch_file.exists()
    payload = json.loads(epoch_file.read_text())
    stored_epoch = int(payload["epoch_ns"])
    assert loop_a.synchronizer.base_time_ns == stored_epoch
    assert loop_b.synchronizer.base_time_ns == stored_epoch


def test_auto_synchronizer_can_be_disabled(tmp_path, monkeypatch):
    epoch_file = tmp_path / "epoch.json"
    monkeypatch.setenv("CONTROL_LOOP_EPOCH_FILE", str(epoch_file))

    loop = ControlLoop("loop-local", 0.005, auto_synchronizer=False)

    assert loop.synchronizer is None
    assert not epoch_file.exists()

    loop.loop_begin()
    time.sleep(loop.period / 2)
    loop.loop_end()


def test_catch_up_strategy_backlog_slots():
    period = 0.005
    sync = LoopSynchronizer(base_time_ns=0)
    sync.register("loop", period)

    first_deadline = sync.reserve_slot("loop")
    period_ns = int(period * 1e9)
    now_ns = first_deadline + (period_ns * 5 // 2)  # 2.5 okresu po pierwszym slocie

    missed = sync.catch_up_after_overrun("loop", now_ns)
    assert missed == 2

    deadlines = [sync.reserve_slot("loop") for _ in range(missed)]
    assert all(d <= now_ns for d in deadlines)
    assert deadlines[1] - deadlines[0] == period_ns

    next_deadline = sync.reserve_slot("loop")
    assert next_deadline > now_ns


def test_invalid_overrun_strategy():
    with pytest.raises(ValueError):
        ControlLoop("loop-invalid", 0.01, overrun_strategy="unknown")
