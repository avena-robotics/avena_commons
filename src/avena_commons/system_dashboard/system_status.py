import os
import psutil
import json
import time
import socket


def get_kernel_info():
    """
    Retrieves information about the system's kernel.

    :return: A dictionary containing kernel version, system name, node name, and machine type.
    """
    return {
        "kernel_version": os.uname().release,
        "system_name": os.uname().sysname,
        "node_name": os.uname().nodename,
        "machine": os.uname().machine,
    }


def get_memory_info():
    """
    Retrieves information about the system's memory usage.

    :return: A dictionary containing total, available, used memory in GB, and memory usage percentage.
    """
    return {
        "total_memory": psutil.virtual_memory().total / (1024.0**3),
        "available_memory": psutil.virtual_memory().available / (1024.0**3),
        "used_memory": psutil.virtual_memory().used / (1024.0**3),
        "memory_percentage": psutil.virtual_memory().percent,
    }


def get_cpu_info():
    """
    Retrieves information about the system's CPU usage.

    :return: A dictionary containing physical cores, total cores, processor speed, CPU usage per core, and total CPU usage.
    """
    return {
        "physical_cores": psutil.cpu_count(logical=False),
        "total_cores": psutil.cpu_count(logical=True),
        "processor_speed": psutil.cpu_freq().current,
        "cpu_usage_per_core": dict(
            enumerate(psutil.cpu_percent(percpu=True, interval=1))
        ),
        "total_cpu_usage": psutil.cpu_percent(interval=1),
    }


def get_disk_info():
    """
    Retrieves information about the system's disk usage.

    :return: A dictionary containing total, used, free space in GB, and usage percentage for each disk partition.
    """
    partitions = psutil.disk_partitions()
    disk_info = {}
    for partition in partitions:
        partition_usage = psutil.disk_usage(partition.mountpoint)
        disk_info[partition.mountpoint] = {
            "total_space": partition_usage.total / (1024.0**3),
            "used_space": partition_usage.used / (1024.0**3),
            "free_space": partition_usage.free / (1024.0**3),
            "usage_percentage": partition_usage.percent,
        }
    return disk_info


def get_network_info():
    """
    Retrieves information about the system's network usage.

    :return: A dictionary containing bytes sent, bytes received, and IP addresses.
    """

    def get_ip_addresses():
        for interface, snics in psutil.net_if_addrs().items():
            for snic in snics:
                if snic.family == socket.AF_INET:
                    yield (interface, snic.address)

    ipv4list = list(get_ip_addresses())
    net_io_counters = psutil.net_io_counters()
    return {
        "bytes_sent": net_io_counters.bytes_sent,
        "bytes_recv": net_io_counters.bytes_recv,
        "ip_addresses": ipv4list,
    }


def get_process_info():
    """
    Retrieves information about the system's running processes.

    :return: A list of dictionaries containing process details such as CPU number, PID, name, command line, memory percentage, and CPU percentage.
    """
    process_info = []
    for process in psutil.process_iter(
        ["cpu_num", "pid", "name", "cmdline", "memory_percent", "cpu_percent"]
    ):
        try:
            proc_info = process.info

            # Check the conditions for memory and CPU usage
            if (
                proc_info["memory_percent"] == 0.0 and proc_info["cpu_percent"] == 0.0
            ) or (
                proc_info["memory_percent"] <= 1.0 and proc_info["cpu_percent"] <= 1.0
            ):
                continue

            # Append process info if conditions are not met
            process_info.append(
                {
                    "cpu_num": proc_info["cpu_num"],
                    "pid": proc_info["pid"],
                    "name": proc_info["name"],
                    "cmdline": proc_info["cmdline"],
                    "memory_percent": proc_info["memory_percent"],
                    "cpu_percent": proc_info["cpu_percent"],
                }
            )

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Handle exceptions for processes that have ended or cannot be accessed
            pass

    return process_info


def is_program_running(program_name):
    """
    Checks if a specific program is currently running.

    :param program_name(str): The name of the program to check.
    :return: True if the program is running, False otherwise.
    """
    for proc in psutil.process_iter():
        if proc.name() == program_name:
            return proc.status() == psutil.STATUS_RUNNING
    return False


def get_load_average():
    """
    Retrieves the system's load average over 1, 5, and 15 minutes.

    :return: A dictionary containing load averages for 1, 5, and 15 minutes.
    """
    load_avg_1, load_avg_5, load_avg_15 = psutil.getloadavg()
    return {
        "load_average_1": load_avg_1,
        "load_average_5": load_avg_5,
        "load_average_15": load_avg_15,
    }


def get_disk_io_counters():
    """
    Retrieves the system's disk I/O counters.

    :return: A dictionary containing read and write counts, bytes, and times.
    """
    io_counters = psutil.disk_io_counters()
    return {
        "read_count": io_counters.read_count,
        "write_count": io_counters.write_count,
        "read_bytes": io_counters.read_bytes,
        "write_bytes": io_counters.write_bytes,
        "read_time": io_counters.read_time,
        "write_time": io_counters.write_time,
    }


def get_net_io_counters():
    """
    Retrieves the system's network I/O counters.

    :return: A dictionary containing bytes sent, bytes received, packets sent, packets received, and error/drop counts.
    """
    io_counters = psutil.net_io_counters()
    return {
        "bytes_sent": io_counters.bytes_sent,
        "bytes_recv": io_counters.bytes_recv,
        "packets_sent": io_counters.packets_sent,
        "packets_recv": io_counters.packets_recv,
        "errin": io_counters.errin,
        "errout": io_counters.errout,
        "dropin": io_counters.dropin,
        "dropout": io_counters.dropout,
    }


def get_system_uptime():
    """
    Retrieves the system's uptime.

    :return: A dictionary containing the system's uptime in days, hours, minutes, and seconds.
    """
    boot_time_timestamp = psutil.boot_time()
    current_time_timestamp = time.time()
    uptime_seconds = current_time_timestamp - boot_time_timestamp
    uptime_minutes = uptime_seconds // 60
    uptime_hours = uptime_minutes // 60
    uptime_days = uptime_hours // 24
    uptime_str = f"{int(uptime_days)} days, {int(uptime_hours % 24)} hours, {int(uptime_minutes % 60)} minutes, {int(uptime_seconds % 60)} seconds"
    return {"uptime": uptime_str}


if __name__ == "__main__":
    data = {
        "kernel_info": get_kernel_info(),
        "memory_info": get_memory_info(),
        "cpu_info": get_cpu_info(),
        "disk_info": get_disk_info(),
        "network_info": get_network_info(),
        "process_info": get_process_info(),
        "system_uptime": get_system_uptime(),
        "load_average": get_load_average(),
        "disk_io_counters": get_disk_io_counters(),
        "net_io_counters": get_net_io_counters(),
    }
    print("=" * 40)
    print("System Monitoring")
    print("=" * 40)
    print(json.dumps(data, indent=4))
