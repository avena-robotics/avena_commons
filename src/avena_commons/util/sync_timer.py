"""Synchronization timer utilities for grid-based timing.

Provides tools for synchronized periodic execution across multiple processes
using CLOCK_MONOTONIC for drift-free operation.

Key features:
- Grid-based synchronization (all processes sync to same time grid)
- Multiple overrun handling modes
- Nanosecond precision
- No drift accumulation

Exposes:
- now_ns(): Get current monotonic time in nanoseconds
- periodic_loop(): Execute callback on synchronized grid
"""

import gc
import signal
import time


def now_ns() -> int:
    """Get current CLOCK_MONOTONIC time in nanoseconds.

    Returns:
        int: Current monotonic time in nanoseconds
    """
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def _sleep_until_ns(target_ns: int):
    """Active wait until target time.

    Uses short sleeps to avoid busy-waiting while maintaining precision.

    Args:
        target_ns (int): Target time in nanoseconds
    """
    while now_ns() < target_ns:
        time.sleep(0.0001)  # 100us sleep to reduce CPU usage


def periodic_loop(
    hz: float,
    phase_ns: int = 0,
    on_tick=lambda k, t_ns: None,
    max_ticks: int | None = None,
    warmup_disable_gc: bool = True,
    overrun_mode: str = "burst",
    max_burst: int = 32,
):
    """Execute callback on synchronized time grid without drift.

    Processes starting at different times synchronize to the same grid (hz, phase_ns).

    Args:
        hz (float): Frequency in Hz (e.g., 30.0 for 30Hz)
        phase_ns (int): Phase offset in nanoseconds (default: 0)
        on_tick (callable): Callback(tick_number, time_ns) executed at each grid point
        max_ticks (int | None): Maximum number of ticks (None = infinite)
        warmup_disable_gc (bool): Disable GC during execution for stability
        overrun_mode (str): How to handle late ticks:
            - 'burst': Catch up immediately (up to max_burst ticks)
            - 'skip_all': Skip to next future grid point
            - 'skip_one': Skip exactly 1 tick and align to next grid
        max_burst (int): Max number of burst ticks when catching up

    Example:
        >>> def my_callback(tick, time_ns):
        ...     print(f"Tick {tick} at {time_ns}")
        >>> periodic_loop(30.0, on_tick=my_callback, max_ticks=100)
    """
    if warmup_disable_gc:
        gc.disable()

    period_ns = int(round(1_000_000_000 / hz))
    k = 0

    # Calculate first grid point after current time
    n0 = now_ns()
    next_ns = ((n0 - phase_ns) // period_ns + 1) * period_ns + phase_ns

    # Handle SIGINT gracefully
    signal.signal(signal.SIGINT, lambda *_: exit(0))

    try:
        while True:
            # Wait until grid point
            _sleep_until_ns(next_ns)
            t = now_ns()

            # Execute tick at planned grid point
            on_tick(k, t)
            k += 1
            next_ns += period_ns

            # Handle overrun (late execution)
            n = now_ns()
            if n > next_ns:
                if overrun_mode == "burst":
                    # Execute missed ticks immediately (burst mode)
                    burst_done = 0
                    while n >= next_ns and burst_done < max_burst:
                        on_tick(k, n)
                        k += 1
                        next_ns += period_ns
                        burst_done += 1
                        n = now_ns()

                    # If still behind after max_burst, align to future grid
                    if n > next_ns:
                        missed = max(0, (n - next_ns + period_ns - 1) // period_ns)
                        if missed:
                            next_ns += missed * period_ns
                            k += missed

                elif overrun_mode == "skip_all":
                    # Skip all missed ticks, jump to next future grid
                    missed = max(0, (n - next_ns + period_ns - 1) // period_ns)
                    next_ns += missed * period_ns
                    k += missed
                    if n >= next_ns:
                        next_ns += period_ns
                        k += 1

                elif overrun_mode == "skip_one":
                    # Skip exactly one tick and align to next grid
                    next_ns = ((n - phase_ns) // period_ns + 1) * period_ns + phase_ns
                    k = (next_ns - phase_ns) // period_ns

            # Check max ticks limit
            if max_ticks is not None and k >= max_ticks:
                break

    finally:
        if warmup_disable_gc:
            gc.enable()
