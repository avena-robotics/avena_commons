#!/usr/bin/env python3
"""
Multi-Camera Pepper Benchmark - Scalable monitoring for N virtual cameras + Pepper.

Tests autonomous operation with multiple camera instances:
1. Load benchmark configuration with service list (cameras + pepper)
2. Start all services (send CMD_RUN events)
3. Monitor CPU usage for each service's core (from service config)
4. Report per-service statistics
5. Clean up (send CMD_STOPPED events)

Configuration:
- Benchmark config: tests/multi_camera_benchmark_config.json
- Service configs: tests/{service_name}_config.json (auto-loaded by EventListeners)

Usage:
    taskset -c 0-15 python tests/multi_camera_pepper_benchmark.py 120
    taskset -c 4-7 python tests/multi_camera_pepper_benchmark.py 60 --config tests/my_config.json
"""

import argparse
import asyncio
import json
import os
import sys
import threading
import time
from datetime import datetime

import psutil
import requests

from avena_commons.event_listener import (
    Event,
    EventListener,
    EventListenerState,
)


class MultiCameraPepperBenchmark:
    """Multi-camera monitoring benchmark for PepperCamera→Pepper pipeline."""

    def __init__(
        self,
        config_file: str = "tests/multi_camera_benchmark_config.json",
        gpu_mode: bool = False,
        duration_override: int = None,
    ):
        """Initialize multi-camera benchmark.

        Args:
            config_file: Path to benchmark configuration JSON
            gpu_mode: Enable GPU acceleration for benchmark
            duration_override: Override duration from config (for taskset usage)
        """
        # Load benchmark configuration
        self.config_file = config_file
        self.gpu_mode = gpu_mode
        self.benchmark_config = self._load_config(config_file)

        # Extract benchmark parameters
        bench_params = self.benchmark_config["benchmark"]
        self.duration_sec = duration_override or bench_params.get("duration_sec", 60)
        self.monitoring_frequency = bench_params.get(
            "monitoring_frequency", 10
        )  # Reduced from 30Hz to 10Hz for stability
        self.startup_delay = bench_params.get("startup_delay_sec", 5)
        self.monitoring_interval = 1.0 / self.monitoring_frequency

        # Extract services configuration
        self.services = self.benchmark_config["services"]

        # Load core assignments from service configs
        self.service_cores = self._extract_cores_from_configs()

        # Monitoring statistics
        self.stats = {
            "monitoring_timestamps": [],
            "memory_usage_mb": [],
            "system_cpu_usage": [],
            "system_cpu_temp": [],
            "total_monitoring_samples": 0,
            "autonomous_operation_time": 0,
            "gpu_mode": gpu_mode,
        }

        # Add per-service CPU tracking
        for service in self.services:
            service_name = service["name"]
            self.stats[f"{service_name}_cpu"] = []
            self.stats[f"{service_name}_core_temp"] = []

        # Add GPU memory tracking if GPU mode enabled
        if gpu_mode:
            self.stats["gpu_memory_mb"] = []
            self.stats["gpu_utilization"] = []

        # System monitoring
        self.process = psutil.Process()
        self.cpu_count = psutil.cpu_count()

        # Base URL for HTTP requests
        self.base_url = "http://127.0.0.1"

        # Control system EventListener
        self.listener = EventListener(name="benchmark_system", port=8000)
        thread1 = threading.Thread(target=self.listener.start)
        thread1.start()
        time.sleep(1)
        self.listener._change_fsm_state(EventListenerState.INITIALIZING)
        time.sleep(1)
        self.listener._change_fsm_state(EventListenerState.STARTING)
        time.sleep(1)

        # Results file path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results_file = f"temp/benchmark_results_{timestamp}.json"

        # Check temperature sensor availability
        self._temp_sensors_available = self._check_temperature_sensors()

    def _load_config(self, config_file: str) -> dict:
        """Load benchmark configuration from JSON file.

        Args:
            config_file: Path to configuration file

        Returns:
            Configuration dictionary
        """
        try:
            with open(config_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Configuration file not found: {config_file}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in configuration file: {e}")
            sys.exit(1)

    def _extract_cores_from_configs(self) -> dict:
        """Extract core assignments from each service's configuration.

        Returns:
            Dictionary mapping service name to core number
        """
        service_cores = {}

        for service in self.services:
            service_name = service["name"]
            config_file = f"{service_name}_config.json"

            try:
                with open(config_file, "r") as f:
                    service_config = json.load(f)

                # Try to find core in camera_configuration or pepper_configuration
                if "camera_configuration" in service_config:
                    core = service_config["camera_configuration"].get("core", 0)
                elif "pepper_configuration" in service_config:
                    core = service_config["pepper_configuration"].get("core", 0)
                else:
                    core = 0
                    print(f"⚠️  No core found in {config_file}, defaulting to 0")

                service_cores[service_name] = core

            except FileNotFoundError:
                print(f"⚠️  Config file not found: {config_file}, defaulting core to 0")
                service_cores[service_name] = 0
            except Exception as e:
                print(f"⚠️  Error loading {config_file}: {e}, defaulting core to 0")
                service_cores[service_name] = 0

        return service_cores

    def _check_temperature_sensors(self) -> bool:
        """Check if temperature sensors are available on the system."""
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                return True
            else:
                return False
        except Exception:
            return False

    def _get_cpu_temperatures(self) -> dict:
        """Get CPU core temperatures and overall CPU temperature."""
        temp_data = {"system_cpu_temp": None, "core_temps": {}}

        if not self._temp_sensors_available:
            return temp_data

        try:
            temps = psutil.sensors_temperatures()

            # Look for CPU temperature sensors (common names)
            cpu_sensor_names = ["coretemp", "cpu_thermal", "k10temp", "zenpower"]

            for sensor_name in cpu_sensor_names:
                if sensor_name in temps:
                    sensors = temps[sensor_name]

                    # Find overall CPU temperature (usually Package id 0 or first sensor)
                    for sensor in sensors:
                        if "Package id 0" in sensor.label or "Tctl" in sensor.label:
                            temp_data["system_cpu_temp"] = sensor.current
                            break

                    # If no package temp found, use first sensor as system temp
                    if temp_data["system_cpu_temp"] is None and sensors:
                        temp_data["system_cpu_temp"] = sensors[0].current

                    # Get individual core temperatures
                    for sensor in sensors:
                        if "Core" in sensor.label:
                            try:
                                # Extract core number from label like "Core 0", "Core 1", etc.
                                core_num = int(sensor.label.split()[-1])
                                temp_data["core_temps"][core_num] = sensor.current
                            except (ValueError, IndexError):
                                # If we can't parse core number, skip
                                continue

                    # If we found data, break from sensor search
                    if temp_data["system_cpu_temp"] is not None:
                        break

            # Fallback: try to get any available temperature
            if temp_data["system_cpu_temp"] is None:
                for sensor_name, sensors in temps.items():
                    if sensors and "cpu" in sensor_name.lower():
                        temp_data["system_cpu_temp"] = sensors[0].current
                        break

        except Exception:
            pass  # Silent failure, just return empty temp data

        return temp_data

    def get_system_stats(self):
        """Get current system resource usage with per-core data and temperatures."""
        try:
            # Use longer interval for stable CPU readings (minimum 0.1s for reliable per-core data)
            cpu_interval = max(0.1, self.monitoring_interval)

            # Get CPU usage per core with stable interval
            cpu_percpu = psutil.cpu_percent(percpu=True, interval=cpu_interval)

            # Get overall CPU usage
            system_cpu = psutil.cpu_percent(interval=0)

            # Get temperature data
            temp_data = self._get_cpu_temperatures()

            # Build stats dict
            stats = {
                "memory_mb": self.process.memory_info().rss / (1024 * 1024),
                "system_cpu": system_cpu,
                "system_cpu_temp": temp_data["system_cpu_temp"],
                "available_memory_gb": psutil.virtual_memory().available / (1024**3),
                "timestamp": time.perf_counter(),
            }

            # Add per-service core usage and temperature with validation
            for service_name, core_id in self.service_cores.items():
                if 0 <= core_id < len(cpu_percpu):
                    # Round to 1 decimal place to avoid micro-fluctuations
                    cpu_usage = round(cpu_percpu[core_id], 1)
                    stats[f"{service_name}_core"] = cpu_usage

                    # Add core temperature if available
                    core_temp = temp_data["core_temps"].get(core_id)
                    stats[f"{service_name}_core_temp"] = core_temp
                else:
                    stats[f"{service_name}_core"] = 0
                    stats[f"{service_name}_core_temp"] = None

            # Add GPU stats if GPU mode enabled
            if self.gpu_mode:
                try:
                    import pynvml

                    # Initialize NVML if not already done
                    if not hasattr(self, "_nvml_initialized"):
                        pynvml.nvmlInit()
                        self._nvml_initialized = True
                        self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)

                    # Get GPU memory usage
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                    stats["gpu_memory_mb"] = mem_info.used / (1024 * 1024)

                    # Get GPU utilization
                    utilization = pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
                    stats["gpu_utilization"] = utilization.gpu

                except ImportError:
                    # pynvml not available, try nvidia-smi fallback
                    try:
                        import subprocess

                        result = subprocess.run(
                            [
                                "nvidia-smi",
                                "--query-gpu=memory.used,utilization.gpu",
                                "--format=csv,noheader,nounits",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )
                        if result.returncode == 0:
                            mem_mb, util = result.stdout.strip().split(",")
                            stats["gpu_memory_mb"] = float(mem_mb)
                            stats["gpu_utilization"] = float(util)
                    except Exception:
                        pass  # GPU monitoring not available
                except Exception:
                    # GPU monitoring failed, continue without it
                    pass

            return stats

        except Exception:
            return {"timestamp": time.perf_counter()}

    async def setup_services(self):
        """Start all services by sending CMD_RUN events."""
        print("🚀 Starting services...")
        print(f"   Total services: {len(self.services)}")

        try:
            os.makedirs("temp", exist_ok=True)

            for service in self.services:
                service_name = service["name"]
                service_address = service["address"]
                service_port = service["port"]
                core = self.service_cores.get(service_name, 0)

                print(
                    f"   📡 Starting {service_name} on {service_address}:{service_port} (Core {core})"
                )

                event = Event(
                    source="benchmark_system",
                    source_port=8000,
                    destination=service_name,
                    destination_port=service_port,
                    event_type="CMD_RUN",
                    to_be_processed=False,
                    data={},
                )

                try:
                    response = requests.post(
                        f"{self.base_url}:{service_port}/event",
                        json=event.to_dict(),
                        timeout=5.0,
                    )
                    if response.status_code == 200:
                        print(f"      ✅ {service_name} started")
                    else:
                        print(
                            f"      ⚠️  {service_name} returned status {response.status_code}"
                        )
                except requests.exceptions.RequestException as e:
                    print(f"      ❌ Failed to start {service_name}: {e}")
                    return False

                # Small delay between service starts
                await asyncio.sleep(0.5)

            print("✅ All services started")
            return True

        except Exception as e:
            print(f"❌ Failed to setup services: {e}")
            import traceback

            traceback.print_exc()
            return False

    async def monitor_autonomous_operation(self):
        """Monitor autonomous operation of all services."""
        print(
            f"🔥 Starting monitoring for {self.duration_sec}s at {self.monitoring_frequency}Hz..."
        )
        print(f"   Monitored cores: {self.service_cores}")
        print(f"   CPU monitoring interval: {self.monitoring_interval:.3f}s")

        # Start timing
        start_time = time.perf_counter()
        next_sample_time = start_time
        sample_count = 0
        last_progress_time = start_time

        try:
            while time.perf_counter() - start_time < self.duration_sec:
                current_time = time.perf_counter()

                # Sample at monitoring frequency
                if current_time >= next_sample_time:
                    # Get system statistics
                    sys_stats = self.get_system_stats()

                    # Record common stats
                    self.stats["memory_usage_mb"].append(sys_stats.get("memory_mb", 0))
                    self.stats["system_cpu_usage"].append(
                        sys_stats.get("system_cpu", 0)
                    )
                    # Record system CPU temperature
                    system_temp = sys_stats.get("system_cpu_temp")
                    self.stats["system_cpu_temp"].append(
                        system_temp if system_temp is not None else 0
                    )

                    self.stats["monitoring_timestamps"].append(
                        sys_stats.get("timestamp", current_time)
                    )

                    # Record per-service CPU and temperature with validation
                    for service_name in self.service_cores.keys():
                        cpu_key = f"{service_name}_core"
                        temp_key = f"{service_name}_core_temp"

                        cpu_value = sys_stats.get(cpu_key, 0)
                        temp_value = sys_stats.get(temp_key)

                        # Only record if CPU value is reasonable (0-100%)
                        if 0 <= cpu_value <= 100:
                            self.stats[f"{service_name}_cpu"].append(cpu_value)
                        else:
                            self.stats[f"{service_name}_cpu"].append(0)

                        # Record temperature (can be None)
                        self.stats[f"{service_name}_core_temp"].append(
                            temp_value if temp_value is not None else 0
                        )

                    # Record GPU stats if available
                    if self.gpu_mode:
                        if "gpu_memory_mb" in sys_stats:
                            self.stats["gpu_memory_mb"].append(
                                sys_stats["gpu_memory_mb"]
                            )
                        if "gpu_utilization" in sys_stats:
                            self.stats["gpu_utilization"].append(
                                sys_stats["gpu_utilization"]
                            )

                    sample_count += 1
                    next_sample_time = current_time + self.monitoring_interval

                    # Progress reporting every 5 seconds (reduced frequency)
                    if current_time - last_progress_time >= 5.0:
                        elapsed = current_time - start_time
                        # Show up to 3 services in progress with temperature
                        core_stats = " | ".join([
                            f"{name} (Core {core}): {sys_stats.get(f'{name}_core', 0):.1f}%"
                            + (
                                f" {sys_stats.get(f'{name}_core_temp', 0):.1f}°C"
                                if sys_stats.get(f"{name}_core_temp") is not None
                                else ""
                            )
                            for name, core in list(self.service_cores.items())[:3]
                        ])

                        # Add system CPU temp to progress
                        sys_temp = sys_stats.get("system_cpu_temp")
                        temp_info = (
                            f" | CPU: {sys_temp:.1f}°C" if sys_temp is not None else ""
                        )

                        print(
                            f"📊 {elapsed:.0f}s | Samples: {sample_count} | {core_stats}{temp_info}"
                        )
                        last_progress_time = current_time

                # Adaptive sleep to maintain timing accuracy
                time_until_next = next_sample_time - time.perf_counter()
                if time_until_next > 0:
                    await asyncio.sleep(min(time_until_next, 0.01))
                else:
                    await asyncio.sleep(0.001)

        except Exception as e:
            print(f"❌ Monitoring error: {e}")
            import traceback

            traceback.print_exc()

        # Update final stats
        self.stats["total_monitoring_samples"] = sample_count
        self.stats["autonomous_operation_time"] = time.perf_counter() - start_time

    def save_results_to_file(self):
        """Save benchmark results to JSON and Markdown files."""
        try:
            os.makedirs("temp", exist_ok=True)

            # Prepare results data
            results = {
                "benchmark_info": {
                    "timestamp": datetime.now().isoformat(),
                    "config_file": self.config_file,
                    "duration_sec": self.duration_sec,
                    "monitoring_frequency": self.monitoring_frequency,
                    "gpu_mode": self.gpu_mode,
                    "services": self.services,
                    "service_cores": self.service_cores,
                },
                "raw_stats": self.stats,
                "summary": self._generate_summary(),
            }

            # Save JSON file
            with open(self.results_file, "w") as f:
                json.dump(results, f, indent=2)

            print(f"📁 Results saved to: {self.results_file}")

            # Save Markdown report
            md_file = self.results_file.replace(".json", ".md")
            self._save_markdown_report(md_file, results)
            print(f"📄 Report saved to: {md_file}")

        except Exception as e:
            print(f"❌ Failed to save results: {e}")

    def _generate_summary(self) -> dict:
        """Generate summary statistics for the results file."""
        summary = {}

        # Overall stats
        total_samples = self.stats["total_monitoring_samples"]
        operation_time = self.stats["autonomous_operation_time"]

        summary["overall"] = {
            "total_samples": total_samples,
            "operation_time_sec": operation_time,
            "actual_frequency": total_samples / operation_time
            if operation_time > 0
            else 0,
            "services_count": len(self.services),
        }

        # Per-service CPU and temperature statistics
        summary["cpu_per_service"] = {}
        for service_name, core_id in self.service_cores.items():
            cpu_data = self.stats.get(f"{service_name}_cpu", [])
            temp_data = self.stats.get(f"{service_name}_core_temp", [])

            service_summary = {
                "core": core_id,
            }

            if cpu_data:
                service_summary.update({
                    "avg_cpu": sum(cpu_data) / len(cpu_data),
                    "max_cpu": max(cpu_data),
                    "min_cpu": min(cpu_data),
                    "samples": len(cpu_data),
                })

            # Add temperature stats if available
            if temp_data and any(
                t > 0 for t in temp_data
            ):  # Filter out zero/None values
                valid_temps = [t for t in temp_data if t > 0]
                if valid_temps:
                    service_summary.update({
                        "avg_temp": sum(valid_temps) / len(valid_temps),
                        "max_temp": max(valid_temps),
                        "min_temp": min(valid_temps),
                    })

            summary["cpu_per_service"][service_name] = service_summary

        # System CPU and temperature
        if self.stats["system_cpu_usage"]:
            sys_cpu = self.stats["system_cpu_usage"]
            summary["system_cpu"] = {
                "avg_cpu": sum(sys_cpu) / len(sys_cpu),
                "max_cpu": max(sys_cpu),
                "min_cpu": min(sys_cpu),
            }

        # System temperature
        if self.stats["system_cpu_temp"]:
            sys_temps = [t for t in self.stats["system_cpu_temp"] if t > 0]
            if sys_temps:
                if "system_cpu" not in summary:
                    summary["system_cpu"] = {}
                summary["system_cpu"]["avg_temp"] = sum(sys_temps) / len(sys_temps)
                summary["system_cpu"]["max_temp"] = max(sys_temps)
                summary["system_cpu"]["min_temp"] = min(sys_temps)

        # System memory
        if self.stats["memory_usage_mb"]:
            memory = self.stats["memory_usage_mb"]
            summary["memory"] = {
                "avg_mb": sum(memory) / len(memory),
                "max_mb": max(memory),
                "min_mb": min(memory),
            }

        # GPU stats if available
        if self.gpu_mode and self.stats.get("gpu_memory_mb"):
            gpu_mem = self.stats["gpu_memory_mb"]
            gpu_util = self.stats.get("gpu_utilization", [])
            summary["gpu"] = {
                "avg_memory_mb": sum(gpu_mem) / len(gpu_mem) if gpu_mem else 0,
                "max_memory_mb": max(gpu_mem) if gpu_mem else 0,
                "avg_utilization": sum(gpu_util) / len(gpu_util) if gpu_util else 0,
                "max_utilization": max(gpu_util) if gpu_util else 0,
            }

        return summary

    def _save_markdown_report(self, filepath: str, results: dict):
        """Generate and save a human-readable Markdown report.

        Args:
            filepath: Path to save the Markdown file
            results: Dictionary containing benchmark results
        """
        with open(filepath, "w") as f:
            # Header
            f.write("# Multi-Camera Pepper Benchmark Results\n\n")

            # Benchmark Information
            info = results["benchmark_info"]
            f.write("## Benchmark Configuration\n\n")
            f.write(f"- **Timestamp**: {info['timestamp']}\n")
            f.write(f"- **Configuration File**: `{info['config_file']}`\n")
            f.write(f"- **Duration**: {info['duration_sec']}s\n")
            f.write(f"- **Monitoring Frequency**: {info['monitoring_frequency']}Hz\n")
            f.write(
                f"- **GPU Mode**: {'Enabled' if info['gpu_mode'] else 'Disabled'}\n"
            )
            f.write(f"- **Total Services**: {len(info['services'])}\n\n")

            # Services List
            f.write("### Services Configuration\n\n")
            f.write("| Service Name | Port | Core | Type |\n")
            f.write("|--------------|------|------|------|\n")
            for service in info["services"]:
                service_name = service["name"]
                port = service["port"]
                core = info["service_cores"].get(service_name, "N/A")
                service_type = (
                    "Camera" if "camera" in service_name.lower() else "Pepper"
                )
                f.write(f"| {service_name} | {port} | {core} | {service_type} |\n")
            f.write("\n")

            # Overall Summary
            summary = results["summary"]
            overall = summary.get("overall", {})
            f.write("## Overall Performance\n\n")
            f.write(f"- **Total Samples**: {overall.get('total_samples', 0):,}\n")
            f.write(
                f"- **Operation Time**: {overall.get('operation_time_sec', 0):.2f}s\n"
            )
            f.write(
                f"- **Actual Frequency**: {overall.get('actual_frequency', 0):.2f}Hz\n"
            )
            f.write(
                f"- **Frequency Accuracy**: {(overall.get('actual_frequency', 0) / info['monitoring_frequency'] * 100):.1f}%\n\n"
            )

            # CPU Usage per Service
            f.write("## CPU Usage per Service\n\n")
            f.write(
                "| Service Name | Core | Avg CPU % | Peak CPU % | Min CPU % | Stability | Avg Temp °C | Peak Temp °C |\n"
            )
            f.write(
                "|--------------|------|-----------|------------|-----------|-----------|-------------|-------------|\n"
            )

            cpu_per_service = summary.get("cpu_per_service", {})
            for service_name, stats in cpu_per_service.items():
                core = stats.get("core", "N/A")
                avg_cpu = stats.get("avg_cpu", 0)
                max_cpu = stats.get("max_cpu", 0)
                min_cpu = stats.get("min_cpu", 0)

                # Calculate stability
                samples = stats.get("samples", 0)
                if samples > 1:
                    # Simplified stability indicator
                    cpu_range = max_cpu - min_cpu
                    stability = "Stable" if cpu_range < 20 else "Variable"
                else:
                    stability = "N/A"

                avg_temp = stats.get("avg_temp", "")
                max_temp = stats.get("max_temp", "")
                avg_temp_str = f"{avg_temp:.1f}" if avg_temp else "-"
                max_temp_str = f"{max_temp:.1f}" if max_temp else "-"

                f.write(
                    f"| {service_name} | {core} | {avg_cpu:.1f} | {max_cpu:.1f} | {min_cpu:.1f} | {stability} | {avg_temp_str} | {max_temp_str} |\n"
                )
            f.write("\n")

            # System CPU
            sys_cpu = summary.get("system_cpu", {})
            if sys_cpu:
                f.write("## System CPU Usage\n\n")
                f.write(f"- **Average CPU**: {sys_cpu.get('avg_cpu', 0):.1f}%\n")
                f.write(f"- **Peak CPU**: {sys_cpu.get('max_cpu', 0):.1f}%\n")
                f.write(f"- **Min CPU**: {sys_cpu.get('min_cpu', 0):.1f}%\n")

                if "avg_temp" in sys_cpu:
                    f.write(f"- **Average Temperature**: {sys_cpu['avg_temp']:.1f}°C\n")
                    f.write(f"- **Peak Temperature**: {sys_cpu['max_temp']:.1f}°C\n")
                    f.write(f"- **Min Temperature**: {sys_cpu['min_temp']:.1f}°C\n")
                f.write("\n")

            # Memory Usage
            memory = summary.get("memory", {})
            if memory:
                f.write("## Memory Usage\n\n")
                f.write(f"- **Average**: {memory.get('avg_mb', 0):.1f} MB\n")
                f.write(f"- **Peak**: {memory.get('max_mb', 0):.1f} MB\n")
                f.write(f"- **Minimum**: {memory.get('min_mb', 0):.1f} MB\n")
                f.write(
                    f"- **Peak Increase**: {memory.get('max_mb', 0) - memory.get('min_mb', 0):.1f} MB\n\n"
                )

            # GPU Usage (if available)
            gpu = summary.get("gpu", {})
            if gpu and gpu.get("avg_memory_mb", 0) > 0:
                f.write("## GPU Usage\n\n")
                f.write(f"- **Average Memory**: {gpu.get('avg_memory_mb', 0):.1f} MB\n")
                f.write(f"- **Peak Memory**: {gpu.get('max_memory_mb', 0):.1f} MB\n")
                f.write(
                    f"- **Average Utilization**: {gpu.get('avg_utilization', 0):.1f}%\n"
                )
                f.write(
                    f"- **Peak Utilization**: {gpu.get('max_utilization', 0):.1f}%\n\n"
                )

                # GPU Assessment
                avg_util = gpu.get("avg_utilization", 0)
                if avg_util > 80:
                    f.write("**Assessment**: ✅ Excellent GPU utilization (>80%)\n\n")
                elif avg_util > 50:
                    f.write("**Assessment**: ⚠️ Moderate GPU utilization (50-80%)\n\n")
                else:
                    f.write("**Assessment**: ⚠️ Low GPU utilization (<50%)\n\n")

            # Temperature Assessment
            if self._temp_sensors_available:
                f.write("## Temperature Assessment\n\n")

                # Collect all temperatures
                all_temps = []
                for service_name in self.service_cores.keys():
                    temp_data = self.stats.get(f"{service_name}_core_temp", [])
                    valid_temps = [t for t in temp_data if t and t > 0]
                    all_temps.extend(valid_temps)

                sys_temps = [t for t in self.stats["system_cpu_temp"] if t > 0]
                all_temps.extend(sys_temps)

                if all_temps:
                    max_temp = max(all_temps)
                    avg_temp = sum(all_temps) / len(all_temps)

                    f.write(f"- **Overall Max Temperature**: {max_temp:.1f}°C\n")
                    f.write(f"- **Overall Avg Temperature**: {avg_temp:.1f}°C\n\n")

                    if max_temp > 90:
                        f.write("**Status**: ⚠️ HIGH TEMPERATURE (>90°C)\n\n")
                    elif max_temp > 80:
                        f.write("**Status**: 🔥 Elevated temperature (>80°C)\n\n")
                    elif max_temp > 70:
                        f.write("**Status**: ✅ Moderate temperature (70-80°C)\n\n")
                    else:
                        f.write("**Status**: ✅ Good temperature (<70°C)\n\n")

            # Benchmark Assessment
            f.write("## Benchmark Assessment\n\n")
            if (
                overall.get("total_samples", 0) > 0
                and overall.get("operation_time_sec", 0) > 0
            ):
                f.write("✅ **BENCHMARK SUCCESSFUL**\n\n")
                f.write("- All services monitored independently\n")
                f.write(
                    f"- Monitoring accuracy: {(overall.get('actual_frequency', 0) / info['monitoring_frequency'] * 100):.1f}% of target\n"
                )
                if info["gpu_mode"]:
                    f.write("- GPU acceleration enabled\n")
            else:
                f.write("❌ **MONITORING FAILED** - Insufficient data collected\n")

            # Footer
            f.write("\n---\n")
            f.write(f"*Generated by Multi-Camera Pepper Benchmark v1.0*\n")

    def analyze_results(self):
        """Analyze and display comprehensive benchmark results."""
        print("\n" + "=" * 80)
        print("📊 MULTI-CAMERA PEPPER BENCHMARK RESULTS")
        print("=" * 80)

        # Benchmark summary
        total_samples = self.stats["total_monitoring_samples"]
        operation_time = self.stats["autonomous_operation_time"]

        print(f"📈 Benchmark Configuration:")
        print(f"   Services:              {len(self.services)}")
        cameras = [s for s in self.services if "camera" in s["name"]]
        peppers = [s for s in self.services if "pepper" in s["name"]]
        print(f"   Cameras:               {len(cameras)}")
        print(f"   Pepper instances:      {len(peppers)}")
        print(f"   Monitoring duration:   {operation_time:.1f}s")
        print(f"   Monitoring frequency:  {self.monitoring_frequency}Hz")
        print(f"   Total samples:         {total_samples:,}")

        # CPU analysis per service with validation and temperature
        print(f"\n💻 CPU Usage per Service (Core + Temperature):")
        for service_name, core_id in self.service_cores.items():
            cpu_data = self.stats.get(f"{service_name}_cpu", [])
            temp_data = self.stats.get(f"{service_name}_core_temp", [])

            if cpu_data:
                avg_cpu = sum(cpu_data) / len(cpu_data)
                max_cpu = max(cpu_data)
                min_cpu = min(cpu_data)

                # Calculate stability (standard deviation)
                if len(cpu_data) > 1:
                    variance = sum((x - avg_cpu) ** 2 for x in cpu_data) / len(cpu_data)
                    std_dev = variance**0.5
                    stability = "Stable" if std_dev < 10 else "Variable"
                else:
                    stability = "Single sample"

                # Temperature stats
                valid_temps = [t for t in temp_data if t and t > 0]
                temp_info = ""
                if valid_temps:
                    avg_temp = sum(valid_temps) / len(valid_temps)
                    max_temp = max(valid_temps)
                    temp_info = f" | Temp: Avg {avg_temp:.1f}°C, Peak {max_temp:.1f}°C"

                print(
                    f"   {service_name:25s} (Core {core_id}): Avg {avg_cpu:5.1f}%, Peak {max_cpu:5.1f}%, Min {min_cpu:5.1f}% ({stability}){temp_info}"
                )
            else:
                print(f"   {service_name:25s} (Core {core_id}): No data collected")

        # System CPU with temperature
        if self.stats["system_cpu_usage"]:
            sys_cpu = self.stats["system_cpu_usage"]
            avg_sys_cpu = sum(sys_cpu) / len(sys_cpu)
            max_sys_cpu = max(sys_cpu)

            # System temperature
            sys_temps = [t for t in self.stats["system_cpu_temp"] if t > 0]
            temp_info = ""
            if sys_temps:
                avg_temp = sum(sys_temps) / len(sys_temps)
                max_temp = max(sys_temps)
                temp_info = f" | Temp: Avg {avg_temp:.1f}°C, Peak {max_temp:.1f}°C"

            print(f"\n🖥️  System CPU Usage:")
            print(
                f"   Average:               {avg_sys_cpu:.1f}%, Peak: {max_sys_cpu:.1f}%{temp_info}"
            )

        # Memory analysis
        if self.stats["memory_usage_mb"]:
            memory_usage = self.stats["memory_usage_mb"]
            avg_memory = sum(memory_usage) / len(memory_usage)
            max_memory = max(memory_usage)
            min_memory = min(memory_usage)

            print(f"\n💾 Memory Usage:")
            print(f"   Average:               {avg_memory:.1f} MB")
            print(f"   Min:                   {min_memory:.1f} MB")
            print(f"   Max:                   {max_memory:.1f} MB")
            print(f"   Peak increase:         {max_memory - min_memory:.1f} MB")

        # GPU analysis (if GPU mode enabled)
        if self.gpu_mode and self.stats.get("gpu_memory_mb"):
            gpu_memory = self.stats["gpu_memory_mb"]
            gpu_util = self.stats.get("gpu_utilization", [])

            avg_gpu_mem = sum(gpu_memory) / len(gpu_memory) if gpu_memory else 0
            max_gpu_mem = max(gpu_memory) if gpu_memory else 0
            avg_gpu_util = sum(gpu_util) / len(gpu_util) if gpu_util else 0
            max_gpu_util = max(gpu_util) if gpu_util else 0

            print(f"\n🎮 GPU Usage (GPU Acceleration Mode):")
            print(f"   Average Memory:        {avg_gpu_mem:.1f} MB")
            print(f"   Peak Memory:           {max_gpu_mem:.1f} MB")
            print(f"   Average Utilization:   {avg_gpu_util:.1f}%")
            print(f"   Peak Utilization:      {max_gpu_util:.1f}%")

            if avg_gpu_util > 80:
                print(f"   ✅ Excellent GPU utilization (>80%)")
            elif avg_gpu_util > 50:
                print(f"   ⚠️  Moderate GPU utilization (50-80%)")
            else:
                print(f"   ⚠️  Low GPU utilization (<50%) - batch size may be too small")

        # Temperature assessment
        if self._temp_sensors_available:
            print(f"\n🌡️  Temperature Assessment:")

            # Check for any concerning temperatures
            all_temps = []
            for service_name in self.service_cores.keys():
                temp_data = self.stats.get(f"{service_name}_core_temp", [])
                valid_temps = [t for t in temp_data if t and t > 0]
                all_temps.extend(valid_temps)

            # Add system temps
            sys_temps = [t for t in self.stats["system_cpu_temp"] if t > 0]
            all_temps.extend(sys_temps)

            if all_temps:
                max_temp = max(all_temps)
                avg_temp = sum(all_temps) / len(all_temps)

                print(f"   Overall Max Temperature: {max_temp:.1f}°C")
                print(f"   Overall Avg Temperature: {avg_temp:.1f}°C")

        # Operation assessment
        print(f"\n🎉 Benchmark Assessment:")
        if total_samples > 0 and operation_time > 0:
            actual_frequency = total_samples / operation_time
            frequency_accuracy = (actual_frequency / self.monitoring_frequency) * 100

            print(f"   ✅ BENCHMARK SUCCESSFUL")
            print(
                f"   ✅ Monitoring accuracy: {frequency_accuracy:.1f}% of target frequency"
            )
            print(f"   ✅ All services monitored independently")

            if self.gpu_mode:
                print(f"   🎮 GPU acceleration enabled - check GPU utilization above")
        else:
            print(f"   ❌ MONITORING FAILED - insufficient data")

        # Save results to file
        self.save_results_to_file()

    async def cleanup(self):
        """Clean up all services by sending CMD_STOPPED events."""
        print("\n🛑 Cleaning up services...")

        for service in self.services:
            service_name = service["name"]
            service_port = service["port"]

            print(f"   Stopping {service_name}...")

            event = Event(
                source="benchmark_system",
                source_port=8000,
                destination=service_name,
                destination_port=service_port,
                event_type="CMD_STOPPED",
                to_be_processed=False,
                data={},
            )

            try:
                response = requests.post(
                    f"{self.base_url}:{service_port}/event",
                    json=event.to_dict(),
                    timeout=5.0,
                )
                if response.status_code == 200:
                    print(f"      ✅ {service_name} stopped")
                else:
                    print(
                        f"      ⚠️  {service_name} stop returned status {response.status_code}"
                    )
            except Exception as e:
                print(f"      ⚠️  Error stopping {service_name}: {e}")

            await asyncio.sleep(0.2)

        print("✅ Cleanup completed")


def parse_args():
    """Parse command line arguments for taskset usage."""
    parser = argparse.ArgumentParser(
        description="Multi-Camera Pepper Benchmark - Monitor N virtual cameras + Pepper",
        epilog="""
Examples with taskset:
  taskset -c 0-15 python tests/multi_camera_pepper_benchmark.py 120
  taskset -c 4-7 python tests/multi_camera_pepper_benchmark.py 60 --config tests/my_config.json --gpu
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "duration",
        type=int,
        help="Duration to run benchmark in seconds (e.g., 60, 120, 300)",
    )

    parser.add_argument(
        "--config",
        type=str,
        default="tests/multi_camera_benchmark_config.json",
        help="Path to benchmark configuration file",
    )

    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Enable GPU acceleration for benchmark (requires CUDA)",
    )

    return parser.parse_args()


async def main():
    """Main benchmark execution."""
    args = parse_args()

    print("🌶️📷 Multi-Camera Pepper Benchmark")
    print(f"Duration: {args.duration}s")
    print(f"Configuration: {args.config}")
    print(f"GPU Mode: {'✅ ENABLED' if args.gpu else '❌ DISABLED (CPU only)'}")

    # Check CPU affinity if using taskset
    try:
        current_affinity = os.sched_getaffinity(0)
        if len(current_affinity) < psutil.cpu_count():
            print(
                f"🔧 CPU Affinity: Cores {sorted(current_affinity)} (taskset detected)"
            )
        else:
            print(f"🔧 CPU Affinity: All cores available")
    except Exception:
        print(f"🔧 CPU Affinity: Could not determine")

    # Check GPU availability if GPU mode requested
    if args.gpu:
        try:
            from avena_commons.util.gpu_utils import check_gpu_available

            gpu_available, gpu_info = check_gpu_available()
            if gpu_available:
                print(f"🎮 {gpu_info}")
            else:
                print(f"⚠️  GPU requested but not available: {gpu_info}")
                print(f"⚠️  Falling back to CPU mode")
                args.gpu = False
        except ImportError:
            print(f"⚠️  GPU utils not available, falling back to CPU")
            args.gpu = False
    print()

    # Create and run benchmark with duration override
    benchmark = MultiCameraPepperBenchmark(
        config_file=args.config, gpu_mode=args.gpu, duration_override=args.duration
    )

    try:
        # Setup services
        if not await benchmark.setup_services():
            print("❌ Failed to setup services, aborting benchmark")
            return

        # Allow services to fully initialize
        print(f"⏳ Waiting {benchmark.startup_delay}s for services to initialize...")
        await asyncio.sleep(benchmark.startup_delay)

        # Start monitoring
        await benchmark.monitor_autonomous_operation()

        # Analyze and report results
        benchmark.analyze_results()

    except KeyboardInterrupt:
        print("\n🛑 Benchmark interrupted by user")
    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await benchmark.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Benchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
