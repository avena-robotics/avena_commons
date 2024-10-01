import psutil
import time
import curses
import argparse


class PCMonitor:
    """
    Monitor CPU core, disk, and network usage.

    :param cores: The CPU cores to monitor.
    :type cores: list
    :param threshold: The CPU usage threshold to print (default: 50%).
    :type threshold: float
    :param interval: The sampling interval in seconds (default: 1).
    :type interval: int
    :param disk_threshold: The disk free space threshold to warn (default: 10%).
    :type disk_threshold: float
    :param core_warning_threshold: The CPU core usage threshold to warn (default: 80%).
    :type core_warning_threshold: float
    :param last_update_time: The last time the monitor was updated.
    :type last_update_time: float
    :param largest_disk: The largest disk found.
    :type largest_disk: tuple
    """

    def __init__(
        self,
        cores,
        threshold=50,
        interval=1,
        disk_threshold=10,
        core_warning_threshold=50,
        message_logger=None,
    ):
        """Initialize PCMonitor class."""
        self.cores = cores
        # self.suffix = 1 # default first and only one robot``
        self.threshold = threshold
        self.interval = interval
        self.disk_threshold = disk_threshold
        self.core_warning_threshold = core_warning_threshold
        self.last_update_time = time.time()
        self.largest_disk = self.get_largest_disk()

    @staticmethod
    def get_largest_disk():
        """Get the largest disk found."""
        disks = psutil.disk_partitions()
        largest_disk = None
        max_size = 0
        for disk in disks:
            if "cdrom" in disk.opts or disk.fstype == "":
                continue
            usage = psutil.disk_usage(disk.mountpoint)
            if usage.total > max_size:
                max_size = usage.total
                largest_disk = (
                    disk.device,
                    usage.total,
                    usage.used,
                    usage.free,
                    usage.percent,
                    disk.mountpoint,
                )
        return largest_disk

    @staticmethod
    def format_size(bytes):
        """Format the size in bytes to a human-readable format."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes < 1024.0:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.2f} PB"

    @staticmethod
    def get_initial_network_stats():
        """Get the initial network statistics."""
        net_io = psutil.net_io_counters(pernic=True)
        return {
            iface: (stats.bytes_sent, stats.bytes_recv)
            for iface, stats in net_io.items()
        }

    @staticmethod
    def check_network_usage(initial_stats, interval):
        """Check the network usage."""
        net_io = psutil.net_io_counters(pernic=True)
        network_usage = []
        for iface, stats in net_io.items():
            if iface.startswith("enp"):
                old_sent, old_recv = initial_stats.get(iface, (0, 0))
                sent_diff = stats.bytes_sent - old_sent
                recv_diff = stats.bytes_recv - old_recv
                initial_stats[iface] = (stats.bytes_sent, stats.bytes_recv)

                # Convert bytes to megabits
                sent_mbps = (sent_diff * 8) / (interval * 1024 * 1024)
                recv_mbps = (recv_diff * 8) / (interval * 1024 * 1024)

                # Calculate percentage usage based on 1000 Mbps connection
                sent_percentage = (sent_mbps / 1000) * 100
                recv_percentage = (recv_mbps / 1000) * 100

                network_usage.append((iface, sent_percentage, recv_percentage))
        return network_usage

    @staticmethod
    def monitor_cores_and_disk_usage(
        stdscr,
        cores,
        threshold=50,
        interval=1,
        disk_threshold=10,
        core_warning_threshold=50,
    ):
        """
        Monitor CPU core, disk, and network usage.

        :param stdscr: The standard screen object.
        :type stdscr: curses.window
        :param cores: The CPU cores to monitor.
        :type cores: list
        :param threshold: The CPU usage threshold to print (default: 50%).
        :type threshold: float
        :param interval: The sampling interval in seconds (default: 1).
        :type interval: int
        :param disk_threshold: The disk free space threshold to warn (default: 10%).
        :type disk_threshold: float
        :param core_warning_threshold: The CPU core usage threshold to warn (default: 80%).
        :type core_warning_threshold: float
        :raises Exception: If an error occurs.
        :return: None
        """
        curses.curs_set(0)  # Hide the cursor
        stdscr.nodelay(1)  # Make getch non-blocking
        stdscr.timeout(0)  # Set non-blocking mode for getch

        largest_disk = PCMonitor.get_largest_disk()
        initial_network_stats = PCMonitor.get_initial_network_stats()

        if largest_disk is None:
            stdscr.addstr(0, 0, "No valid disk found.")
            stdscr.refresh()
            time.sleep(3)
            return

        device, total, used, free, percent, mountpoint = largest_disk

        last_update_time = time.time()

        while True:
            current_time = time.time()
            if current_time - last_update_time >= interval:
                last_update_time = current_time
                stdscr.clear()
                try:
                    height, width = stdscr.getmaxyx()
                    stdscr.addstr(
                        0,
                        0,
                        f"Monitoring CPU cores {cores} usage above {threshold}%, largest disk space usage, and network usage",
                    )
                    stdscr.addstr(
                        1,
                        0,
                        f"{'Time':<10} {'Core':<5} {'Usage (%)':<15} {'Warning':<15}",
                    )
                    stdscr.addstr(2, 0, "=" * 65)

                    # Measure CPU usage
                    cpu_usages = psutil.cpu_percent(interval=0, percpu=True)
                    current_time_str = time.strftime("%H:%M:%S")
                    row = 3
                    for core in cores:
                        core_usage = cpu_usages[core]
                        msg = f"{current_time_str:<10} {core:<5} {core_usage:<15}"
                        warning_msg = f" WARNING: Core {core} usage above {core_warning_threshold}%!"
                        if core_usage >= threshold:
                            if core_usage >= core_warning_threshold:
                                msg += warning_msg
                            stdscr.addstr(row, 0, msg)
                            row += 1

                    if (
                        row + 5 < height
                    ):  # Ensure there is enough space for the disk usage section
                        stdscr.addstr(row, 0, "\nLargest Disk Usage:")
                        row += 2
                        stdscr.addstr(
                            row,
                            0,
                            f"{'Device':<20} {'Total':<10} {'Used':<10} {'Free':<10} {'Usage (%)':<10}",
                        )
                        row += 1
                        stdscr.addstr(row, 0, "=" * 65)
                        row += 1

                        # Get the updated usage of the largest disk
                        usage = psutil.disk_usage(mountpoint)
                        free_percent = (usage.free / usage.total) * 100
                        stdscr.addstr(
                            row,
                            0,
                            f"{device:<20} {PCMonitor.format_size(usage.total):<10} {PCMonitor.format_size(usage.used):<10} {PCMonitor.format_size(usage.free):<10} {usage.percent:<10}%",
                        )
                        row += 1

                        # Check if free space is below the threshold and display a warning if it is
                        if free_percent < disk_threshold:
                            stdscr.addstr(
                                row,
                                0,
                                f"WARNING: Free space below {disk_threshold}% on {device}!",
                                curses.A_BLINK | curses.A_BOLD,
                            )

                    row += 2  # Add some space before network usage section

                    if (
                        row + 5 < height
                    ):  # Ensure there is enough space for the network usage section
                        stdscr.addstr(row, 0, "\nNetwork Usage:")
                        row += 2
                        stdscr.addstr(
                            row,
                            0,
                            f"{'Interface':<15} {'Bytes Sent':<15} {'Bytes Received':<15}",
                        )
                        row += 1
                        stdscr.addstr(row, 0, "=" * 65)
                        row += 1

                        # Check network usage
                        network_usage = PCMonitor.check_network_usage(
                            initial_network_stats, interval
                        )
                        for iface, sent_percentage, recv_percentage in network_usage:
                            stdscr.addstr(
                                row,
                                0,
                                f"{iface:<15} {sent_percentage:<15.2f} {recv_percentage:<15.2f}",
                            )
                            row += 1

                    stdscr.refresh()
                except curses.error:
                    pass  # Ignore curses errors due to small terminal size

            # Add a small delay to reduce CPU usage
            time.sleep(0.1)

            # Check for user input to exit
            if stdscr.getch() != -1:
                return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Monitor CPU core, disk, and network usage."
    )
    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=0,
        help="CPU usage threshold to print (default: 50%).",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=1,
        help="Sampling interval in seconds (default: 1).",
    )
    parser.add_argument(
        "--disk-threshold",
        "-dt",
        type=float,
        default=10,
        help="Disk free space threshold to warn (default: 10%).",
    )
    parser.add_argument(
        "--core-warning-threshold",
        "-cwt",
        type=float,
        default=80,
        help="CPU core usage threshold to warn (default: 80%).",
    )
    args = parser.parse_args()

    # Specify the cores to monitor (0 to 10)
    cores_to_monitor = list(range(11))  # cores 0 to 10

    curses.wrapper(
        PCMonitor.monitor_cores_and_disk_usage,
        cores_to_monitor,
        args.threshold,
        args.interval,
        args.disk_threshold,
        args.core_warning_threshold,
    )
