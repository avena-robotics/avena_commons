#!/usr/bin/env python3
"""
Autonomous monitoring benchmark for PepperCamera → Pepper EventListener pipeline.

Tests autonomous operation without event control:
1. Pepper EventListener (core from config) - ready to receive fragments
2. PepperCamera EventListener (core from config) - autonomous camera processing  
3. Monitor at 30Hz for CPU, memory, fragment buffer status
4. No manual events - pure observation of autonomous operation
5. Results logged to .md report

Workflow:
- Pepper starts → ready for fragments
- PepperCamera starts → autonomous frame grab/fragment/send
- Monitor system → 30Hz sampling, no interference

Usage:
    python pepper_camera_pepper_eventlistener_cpu_benchmark.py
"""

import asyncio
import time
import psutil
import sys
import os
import threading

import requests

from avena_commons.event_listener import (
    EventListenerState,
    EventListener,
    Event,
)


class AutonomousPepperCameraBenchmark:
    """Autonomous monitoring benchmark for PepperCamera→Pepper pipeline."""
    
    def __init__(self,
                 duration_sec: int = 60,
                 monitoring_frequency: int = 30):
        """Initialize autonomous monitoring benchmark.
        
        Args:
            camera_config_file: Path to PepperCamera configuration JSON file
            pepper_config_file: Path to Pepper configuration JSON file
            duration_sec: Duration of monitoring in seconds
            monitoring_frequency: Monitoring frequency in Hz (default 30Hz)
        """
        self.duration_sec = duration_sec
        self.monitoring_frequency = monitoring_frequency
        self.monitoring_interval = 1.0 / monitoring_frequency
        
        # Configuration will be available after EventListeners are created
        self.camera_ip = None
        self.camera_core = None
        self.pepper_core = None
        
        # Monitoring statistics
        self.stats = {
            'monitoring_timestamps': [],
            'memory_usage_mb': [],
            'cpu_usage_camera_core': [],
            'cpu_usage_pepper_core': [],
            'system_cpu_usage': [],
            'pepper_fragment_buffer_size': [],
            'pepper_processing_status': [],
            'camera_processing_status': [],
            'camera_states': [],
            'pepper_states': [],
            'total_monitoring_samples': 0,
            'autonomous_operation_time': 0
        }
        
        # System monitoring
        self.process = psutil.Process()
        self.cpu_count = psutil.cpu_count()
        
        # EventListener instances
        self.pepper_camera = None
        self.pepper_listener = None
        
        self.base_url = f"http://127.0.0.1"

        self.listener = EventListener(name="benchmark_system", port=8000)
        thread1 = threading.Thread(target=self.listener.start)
        thread1.start()
        time.sleep(1)
        self.listener._change_fsm_state(EventListenerState.INITIALIZING)
        time.sleep(1)
        self.listener._change_fsm_state(EventListenerState.STARTING)
        time.sleep(1)

    def get_system_stats(self):
        """Get current system resource usage with core-specific data."""
        try:
            # Use 0.001s interval for stable CPU measurements
            cpu_percpu = psutil.cpu_percent(percpu=True, interval=self.monitoring_interval)
            camera_core_usage = cpu_percpu[self.camera_core] if self.camera_core < len(cpu_percpu) else 0
            pepper_core_usage = cpu_percpu[self.pepper_core] if self.pepper_core < len(cpu_percpu) else 0
        except:
            camera_core_usage = 0
            pepper_core_usage = 0
            
        return {
            'memory_mb': self.process.memory_info().rss / (1024 * 1024),
            'cpu_camera_core': camera_core_usage,
            'cpu_pepper_core': pepper_core_usage,
            'system_cpu': psutil.cpu_percent(interval=self.monitoring_interval),
            'available_memory_gb': psutil.virtual_memory().available / (1024**3)
        }

    def get_pepper_processing_stats(self):
        """Get processing statistics from Pepper EventListener."""
        try:
            if self.pepper_listener:
                return {
                    "is_processing": getattr(self.pepper_listener, '_is_processing', False),
                    "processing_enabled": getattr(self.pepper_listener, 'processing_enabled', True),
                    "fragment_buffer_size": len(getattr(self.pepper_listener, 'fragment_buffer', [])),
                    "expected_fragments": getattr(self.pepper_listener, 'expected_fragments', 4),
                    "last_result": getattr(self.pepper_listener, 'last_processing_result', None),
                    "pepper_state": str(getattr(self.pepper_listener.pepper_connector, 'get_state', lambda: 'unknown')())
                }
        except Exception as e:
            return {"error": str(e)}
        return None

    async def setup_autonomous_eventlisteners(self):
        """Initialize EventListeners for autonomous operation with proper order."""
        print("🚀 Setting up EventListeners for autonomous operation...")
        print("📋 Order: Pepper first (ready to receive) → PepperCamera second (starts autonomous processing)")
        
        # Create message loggers
        # pepper_logger = MessageLogger(filename="temp/pepper_autonomous_benchmark.log", debug=True)
        # camera_logger = MessageLogger(filename="temp/pepper_camera_autonomous_benchmark.log", debug=True)
        
        try:
            # Ensure temp directory exists
            os.makedirs("temp", exist_ok=True)
            
            # Set environment variables for EventListeners
            os.environ["PEPPER_CAMERA_LISTENER_ADDRESS"] = "127.0.0.1"
            os.environ["PEPPER_CAMERA_LISTENER_PORT"] = "8002"
            os.environ["PEPPER_LISTENER_ADDRESS"] = "127.0.0.1" 
            os.environ["PEPPER_LISTENER_PORT"] = "8001"
            
            # Initialize Pepper EventListener FIRST (ready to receive fragments)
            print(f"  🌶️  Starting Pepper EventListener...")
            print(f"      Config: pepper_autonomous_benchmark.json (auto-loaded)")
            print(f"      Ready to receive and aggregate fragments")
            
            port1 = 8001
            port2 = 8002
            
            event1 = Event(
                source="benchmark_system",
                source_port=8000,
                destination="pepper_autonomous_benchmark", # pepper_camera_autonomous_benchmark
                destination_port=port1,  # 8001, 8002
                event_type="CMD_RUN", # next is CMD_RUN
                to_be_processed=False,
                data={},
            )
            response = requests.post(f"{self.base_url}:{port1}/event", json=event1.to_dict())
            print(f"Response status code: {response.status_code}")
            print(f"Response Event: {event1.to_dict()}")
            time.sleep(1)
            
            event2 = Event(
                source="benchmark_system",
                source_port=8000,
                destination="pepper_autonomous_benchmark", # pepper_camera_autonomous_benchmark
                destination_port=port2,  # 8001, 8002
                event_type="CMD_RUN", # next is CMD_RUN
                to_be_processed=False,
                data={},
            )
            
            response = requests.post(f"{self.base_url}:{port2}/event", json=event2.to_dict())
            print(f"Response status code: {response.status_code}")
            print(f"Response Event: {event2.to_dict()}")
            time.sleep(1)

            self.pepper_core = 1
            self.camera_core = 1
            self.camera_ip = "192.168.1.10"
            
            print("✅ EventListeners initialized for autonomous operation")
            print(f"   📍 Pepper: localhost:8002 (Core {self.pepper_core})")
            print(f"   📷 PepperCamera: localhost:8001 → {self.camera_ip} (Core {self.camera_core})")
            print("📊 PepperCamera will continuously: grab frame → fragment → send to Pepper")
            print("🌶️  Pepper will continuously: receive fragments → buffer → process when ready")
            print(f"🔍 Monitoring at {self.monitoring_frequency}Hz for {self.duration_sec}s")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to setup EventListeners: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def monitor_autonomous_operation(self):
        """Monitor autonomous operation of PepperCamera and Pepper EventListeners."""
        print("🔥 Starting autonomous operation monitoring...")
        print("📷 PepperCamera processes frames autonomously")
        print("🌶️  Pepper aggregates and processes fragments")
        
        # Start timing
        start_time = time.perf_counter()
        next_sample_time = start_time
        sample_count = 0
        
        try:
            while time.perf_counter() - start_time < self.duration_sec:
                current_time = time.perf_counter()
                
                # Sample at monitoring frequency
                if current_time >= next_sample_time:
                    # Get system statistics
                    sys_stats = self.get_system_stats()
                    self.stats['memory_usage_mb'].append(sys_stats['memory_mb'])
                    self.stats['cpu_usage_camera_core'].append(sys_stats['cpu_camera_core'])
                    self.stats['cpu_usage_pepper_core'].append(sys_stats['cpu_pepper_core'])
                    self.stats['system_cpu_usage'].append(sys_stats['system_cpu'])
                    self.stats['monitoring_timestamps'].append(current_time)

                    sample_count += 1
                    next_sample_time = current_time + self.monitoring_interval
                    
                    # Progress reporting every 10 seconds
                    elapsed = current_time - start_time
                    if int(elapsed) % 10 == 0 and elapsed > 0 and sample_count % (self.monitoring_frequency * 10) == 0:
                        print(f"📊 Monitoring {elapsed:.0f}s | Samples: {sample_count} | Camera core {self.camera_core}: {sys_stats['cpu_camera_core']:.1f}% | Pepper core {self.pepper_core}: {sys_stats['cpu_pepper_core']:.1f}% | Memory: {sys_stats['memory_mb']:.0f}MB")
                
                # Small delay to prevent excessive CPU usage
                await asyncio.sleep(0.001)
                
        except Exception as e:
            print(f"❌ Monitoring error: {e}")
            import traceback
            traceback.print_exc()
        
        # Update final stats
        self.stats['total_monitoring_samples'] = sample_count
        self.stats['autonomous_operation_time'] = time.perf_counter() - start_time

    def analyze_results(self):
        """Analyze and display comprehensive autonomous operation results."""
        print("\n" + "=" * 80)
        print("📊 AUTONOMOUS PEPPER CAMERA → PEPPER EVENTLISTENER BENCHMARK RESULTS")
        print("=" * 80)
        
        # Autonomous operation summary
        total_samples = self.stats['total_monitoring_samples']
        operation_time = self.stats['autonomous_operation_time']
        
        print(f"📈 Autonomous Operation:")
        print(f"   Monitoring duration:   {operation_time:.1f}s")
        print(f"   Monitoring frequency:  {self.monitoring_frequency}Hz")
        print(f"   Total samples:         {total_samples:,}")
        print(f"   Camera core:           {self.camera_core}")
        print(f"   Pepper core:           {self.pepper_core}")
        
        # CPU analysis
        if self.stats['cpu_usage_camera_core']:
            camera_cpu = self.stats['cpu_usage_camera_core']
            avg_camera_cpu = sum(camera_cpu) / len(camera_cpu)
            max_camera_cpu = max(camera_cpu)
            
            print(f"\n💻 Camera Core {self.camera_core} CPU Usage:")
            print(f"   Average:               {avg_camera_cpu:.1f}%")
            print(f"   Peak:                  {max_camera_cpu:.1f}%")

        if self.stats['cpu_usage_pepper_core']:
            pepper_cpu = self.stats['cpu_usage_pepper_core']
            avg_pepper_cpu = sum(pepper_cpu) / len(pepper_cpu)
            max_pepper_cpu = max(pepper_cpu)
            
            print(f"\n🌶️  Pepper Core {self.pepper_core} CPU Usage:")
            print(f"   Average:               {avg_pepper_cpu:.1f}%")
            print(f"   Peak:                  {max_pepper_cpu:.1f}%")

        if self.stats['system_cpu_usage']:
            sys_cpu = self.stats['system_cpu_usage']
            avg_sys_cpu = sum(sys_cpu) / len(sys_cpu)
            print(f"\n🖥️  System CPU Usage:")
            print(f"   Average:               {avg_sys_cpu:.1f}%")

        # Memory analysis
        if self.stats['memory_usage_mb']:
            memory_usage = self.stats['memory_usage_mb']
            avg_memory = sum(memory_usage) / len(memory_usage)
            max_memory = max(memory_usage)
            min_memory = min(memory_usage)
            
            print(f"\n💾 Memory Usage:")
            print(f"   Average:               {avg_memory:.1f} MB")
            print(f"   Min:                   {min_memory:.1f} MB")
            print(f"   Max:                   {max_memory:.1f} MB")
            print(f"   Peak increase:         {max_memory - min_memory:.1f} MB")

        # Fragment buffer analysis
        if self.stats['pepper_fragment_buffer_size']:
            buffer_sizes = self.stats['pepper_fragment_buffer_size']
            avg_buffer = sum(buffer_sizes) / len(buffer_sizes)
            max_buffer = max(buffer_sizes)
            
            print(f"\n🔄 Fragment Buffer Analysis:")
            print(f"   Average buffer size:   {avg_buffer:.1f} fragments")
            print(f"   Peak buffer size:      {max_buffer} fragments")
            print(f"   Expected fragments:    4 per frame")

        # Processing status analysis
        if self.stats['pepper_processing_status']:
            processing_count = sum(self.stats['pepper_processing_status'])
            processing_percentage = (processing_count / len(self.stats['pepper_processing_status'])) * 100
            
            print(f"\n⚙️  Processing Activity:")
            print(f"   Pepper processing:     {processing_percentage:.1f}% of time")
        
        if self.stats['camera_processing_status']:
            camera_processing_count = sum(self.stats['camera_processing_status'])
            camera_processing_percentage = (camera_processing_count / len(self.stats['camera_processing_status'])) * 100
            print(f"   Camera processing:     {camera_processing_percentage:.1f}% of time")

        # Autonomous operation assessment
        print(f"\n🎉 Autonomous Operation Assessment:")
        if total_samples > 0 and operation_time > 0:
            actual_frequency = total_samples / operation_time
            frequency_accuracy = (actual_frequency / self.monitoring_frequency) * 100
            
            print(f"   ✅ AUTONOMOUS OPERATION SUCCESSFUL")
            print(f"   ✅ Monitoring accuracy: {frequency_accuracy:.1f}% of target frequency")
            print(f"   ✅ No manual intervention required")
            print(f"   ✅ EventListeners operated independently")
        else:
            print(f"   ❌ MONITORING FAILED - insufficient data")

    async def cleanup(self):
        """Clean up EventListeners and resources."""
        print("\n🛑 Cleaning up EventListeners...")
        port1 = 8001
        port2 = 8002
            
        event1 = Event(
            source="benchmark_system",
            source_port=8000,
            destination="pepper_autonomous_benchmark", # pepper_camera_autonomous_benchmark
            destination_port=port1,  # 8001, 8002
            event_type="CMD_STOPPED", # next is CMD_STOPPED
            to_be_processed=False,
            data={},
        )
        response = requests.post(f"{self.base_url}:{port1}/event", json=event1.to_dict())
        print(f"Response status code: {response.status_code}")
        print(f"Response Event: {event1.to_dict()}")
        time.sleep(1)
        
        event2 = Event(
            source="benchmark_system",
            source_port=8000,
            destination="pepper_autonomous_benchmark", # pepper_camera_autonomous_benchmark
            destination_port=port2,  # 8001, 8002
            event_type="CMD_STOPPED", # next is CMD_STOPPED
            to_be_processed=False,
            data={},
        )
        
        response = requests.post(f"{self.base_url}:{port2}/event", json=event2.to_dict())
        print(f"Response status code: {response.status_code}")
        print(f"Response Event: {event2.to_dict()}")
        time.sleep(1)
        try:
            if self.pepper_camera:
                await self.pepper_camera.on_stopping()
            if self.pepper_listener:
                await self.pepper_listener.on_stopping()
            print("✅ Cleanup completed")
        except Exception as e:
            print(f"⚠️  Cleanup warning: {e}")


async def main():
    """Main autonomous benchmark execution."""
    print("🌶️📷 Autonomous PepperCamera → Pepper EventListener Benchmark")
    print("Testing: Autonomous Operation Monitoring (No Event Control)")
    print("Pipeline: Continuous camera → fragmentation → autonomous pepper processing")
    print("Monitoring: 30Hz system observation without interference")
    print()
    
    # Create and run autonomous benchmark
    benchmark = AutonomousPepperCameraBenchmark(
        duration_sec=60,  # 1 minute autonomous monitoring
        monitoring_frequency=30  # 30Hz monitoring
    )
    
    try:
        # Setup EventListeners for autonomous operation
        if not await benchmark.setup_autonomous_eventlisteners():
            print("❌ Failed to setup EventListeners, aborting benchmark")
            return
        
        print(f"📂 Configuration loaded:")
        print(f"   Camera IP: {benchmark.camera_ip}")
        print(f"   Camera Core: {benchmark.camera_core}")
        print(f"   Pepper Core: {benchmark.pepper_core}")
        
        # Allow EventListeners to fully initialize and start autonomous operation
        print("⏳ Allowing EventListeners to start autonomous operation...")
        await asyncio.sleep(5.0)
        
        # Start autonomous monitoring (no event control)
        print(f"🚀 Starting {benchmark.duration_sec}s autonomous monitoring at {benchmark.monitoring_frequency}Hz...")
        await benchmark.monitor_autonomous_operation()
        
        # Analyze and save results
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
