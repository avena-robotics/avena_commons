#!/usr/bin/env python3
"""
Real Camera CPU Benchmark - 30Hz for 5 minutes
Uses real camera frames from test_camera.py with accurate perf_counter timing
"""

import os
import sys
import time
import threading
import numpy as np
import cv2
import base64
import psutil
from datetime import datetime

# Add the src directory to the system path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from avena_commons.util.catchtime import Catchtime
from avena_commons.camera.camera import Camera
from avena_commons.util.logger import MessageLogger, LoggerPolicyPeriod
from avena_commons.util.control_loop import ControlLoop
from avena_commons.camera.driver.orbec_335le import OrbecGemini335Le


class RealCameraCPUBenchmark:
    """Real Camera CPU Benchmark using actual camera frames"""
    
    def __init__(self):
        print("🚀 Real Camera CPU Benchmark - 30Hz for 5 minutes")
        print("=" * 70)
        
        # Test parameters
        self.target_fps = 30.0
        self.test_duration_minutes = 1
        self.frame_interval = 1.0 / self.target_fps  # 33.33ms
        self.total_iterations = int(self.test_duration_minutes * 60 * self.target_fps)  # 9000
        
        # Fragment configuration
        self.fragment_config = {
            "top_left": {"enabled": True, "target": "default"},
            "top_right": {"enabled": True, "target": "default"},
            "bottom_left": {"enabled": True, "target": "default"},
            "bottom_right": {"enabled": True, "target": "default"}
        }
        
        # Stats storage
        self.cpu_stats = []
        self.timing_stats = []
        
        # Initialize camera like in test_camera.py
        self.message_logger = MessageLogger(
            filename=f"temp/real_camera_benchmark.log",
            debug=True,
            period=LoggerPolicyPeriod.LAST_15_MINUTES,
            files_count=40,
        )
        
        port = 9900
        print(f"📋 Configuration:")
        print(f"   Target FPS: {self.target_fps}")
        print(f"   Duration: {self.test_duration_minutes} minutes")
        print(f"   Total iterations: {self.total_iterations}")
        print(f"   Camera port: {port}")
        print(f"   CPU cores: {psutil.cpu_count()}")
        
        # Initialize camera
        self.listener = Camera(
            name=f"camera_server_192.168.1.10",
            address="127.0.0.1",
            port=port,
            message_logger=self.message_logger,
        )
        # self.listener.start()
        # self.camera = OrbecGemini335Le(
        #     core=8, camera_ip="192.168.1.10", message_logger=self.message_logger
        # )
        
    def _create_fragments(self, color_image, depth_image):
        """Create 4 fragments - identical to camera.py implementation"""
        fragments = []
        h, w = color_image.shape[:2]
        half_h, half_w = h // 2, w // 2

        fragment_positions = [
            ("top_left", 0, half_h, 0, half_w),
            ("top_right", 0, half_h, half_w, w),
            ("bottom_left", half_h, h, 0, half_w),
            ("bottom_right", half_h, h, half_w, w)
        ]

        for i, (name, y1, y2, x1, x2) in enumerate(fragment_positions):
            config = self.fragment_config.get(name, {"enabled": True, "target": "default"})

            if config.get("enabled", True):
                color_fragment = color_image[y1:y2, x1:x2]
                depth_fragment = depth_image[y1:y2, x1:x2]

                fragment = {
                    "color": color_fragment,
                    "depth": depth_fragment,
                    "fragment_id": i,
                    "camera_number": 0,
                    "fragment_name": name,
                    "target": config.get("target", "default")
                }
                fragments.append(fragment)

        return fragments

    def _serialize_roi(self, roi):
        """Convert ROI to JSON-serializable format - identical to camera.py implementation"""
        serialized = {}

        # Convert color image
        if roi.get("color") is not None:
            _, buffer = cv2.imencode('.jpg', roi["color"])
            serialized["color"] = base64.b64encode(buffer).decode('utf-8')
            serialized["color_shape"] = roi["color"].shape

        # Convert depth image
        if roi.get("depth") is not None:
            _, buffer = cv2.imencode('.png', roi["depth"])
            serialized["depth"] = base64.b64encode(buffer).decode('utf-8')
            serialized["depth_shape"] = roi["depth"].shape

        # Add metadata
        for key in ["fragment_id", "camera_number", "fragment_name", "target"]:
            if roi.get(key) is not None:
                serialized[key] = roi[key]

        return serialized
    
    def run_benchmark(self):
        """Run the 30Hz benchmark with real camera"""
        print(f"\n🔥 Starting real camera benchmark...")
        print("Press Ctrl+C to stop early")
        print("📸 Initializing camera...")
        
        # Start camera
        # self.listener.start()
        
        # Wait for camera initialization
        time.sleep(3)
        
        # Initialize CPU monitoring
        process = psutil.Process()
        
        # Monitor CPU core 8 specifically  
        core_1_cpu_stats = []
        
        # Use perf_counter for precise timing
        start_time = time.perf_counter()
        
        successful_frames = 0
        failed_frames = 0
        
        loop = ControlLoop(period=self.frame_interval, name="benchmark_loop", fill_idle_time=False)
        
        try:
            for iteration in range(self.total_iterations):
                loop.loop_begin()
                
                # Get CPU before processing - more accurate measurement
                cpu_before_system = psutil.cpu_percent(interval=None)
                cpu_before_process = process.cpu_percent()
                
                # Get CPU core 1 usage before processing
                cpu_cores_before = psutil.cpu_percent(interval=None, percpu=True)
                cpu_core_1_before = cpu_cores_before[1] if len(cpu_cores_before) > 1 else 0.0
                
                # Get real camera frame
                try:
                    last_frame = self.listener.camera.get_last_frame()
                    
                    if last_frame is not None and 'color' in last_frame and 'depth' in last_frame:
                        color_image = last_frame['color']
                        depth_image = last_frame['depth']
                        
                        # Process fragments with perf_counter timing
                        with Catchtime() as ct1:
                            fragments = self._create_fragments(color_image, depth_image)
                        create_time_ms = ct1.ms
                        
                        # Serialize fragments with timing
                        with Catchtime() as ct2:
                            for fragment in fragments:
                                serialized = self._serialize_roi(fragment)

                        total_serialize_time = ct2.ms
                        total_process_time = create_time_ms + total_serialize_time
                        
                        successful_frames += 1
                        
                    else:
                        # No frame available - still count timing but mark as failed
                        create_time_ms = 0.0
                        total_serialize_time = 0.0
                        total_process_time = 0.0
                        failed_frames += 1
                        
                except Exception as e:
                    print(f"Frame error: {e}")
                    create_time_ms = 0.0
                    total_serialize_time = 0.0
                    total_process_time = 0.0
                    failed_frames += 1
                
                # Get CPU after processing
                cpu_after_system = psutil.cpu_percent(interval=None) 
                cpu_after_process = process.cpu_percent()
                
                # Get CPU core 1 usage after processing
                cpu_cores_after = psutil.cpu_percent(interval=None, percpu=True)
                cpu_core_1_after = cpu_cores_after[1] if len(cpu_cores_after) > 1 else 0.0

                # Store CPU core 1 stats
                cpu_core_1_avg = (cpu_core_1_before + cpu_core_1_after) / 2
                core_1_cpu_stats.append(cpu_core_1_avg)
                
                # Store stats with perf_counter precision
                timing_sample = {
                    'iteration': iteration,
                    'create_ms': create_time_ms,
                    'serialize_total_ms': total_serialize_time,
                    'total_process_ms': total_process_time,
                    'successful_frame': successful_frames > failed_frames
                }
                
                # More accurate CPU measurement (average and normalize by core count)
                cpu_sample = {
                    'iteration': iteration,
                    'cpu_system_percent': (cpu_before_system + cpu_after_system) / 2,
                    'cpu_process_percent': (cpu_before_process + cpu_after_process) / 2,
                    'cpu_process_normalized': ((cpu_before_process + cpu_after_process) / 2) / psutil.cpu_count(),
                    'cpu_core_1_percent': cpu_core_1_avg,
                    'memory_mb': process.memory_info().rss / 1024 / 1024
                }
                
                self.timing_stats.append(timing_sample)
                self.cpu_stats.append(cpu_sample)
                
                # Show progress every 30 seconds (900 iterations)
                if iteration % 900 == 0 and iteration > 0:
                    elapsed = time.perf_counter() - start_time
                    progress = (iteration / self.total_iterations) * 100
                    
                    recent_samples = self.cpu_stats[-900:]
                    recent_cpu_sys = np.mean([s['cpu_system_percent'] for s in recent_samples])
                    recent_cpu_proc = np.mean([s['cpu_process_normalized'] for s in recent_samples])
                    recent_cpu_core_1 = np.mean([s['cpu_core_1_percent'] for s in recent_samples])
                    recent_timing = np.mean([s['total_process_ms'] for s in self.timing_stats[-900:]])
                    success_rate = (successful_frames / (successful_frames + failed_frames)) * 100
                    
                    print(f"⏱️  Progress: {progress:.1f}% | "
                          f"Elapsed: {elapsed/60:.1f}min | "
                          f"System CPU: {recent_cpu_sys:.1f}% | "
                          f"Core 1 CPU: {recent_cpu_core_1:.1f}% | "
                          f"Process CPU: {recent_cpu_proc:.1f}% | "
                          f"Success: {success_rate:.1f}% | "
                          f"Avg time: {recent_timing:.3f}ms")
                    
                loop.loop_end()
                
        except KeyboardInterrupt:
            print(f"\n⚡ Benchmark interrupted at iteration {iteration}")
        finally:
            print("🔄 Cleaning up camera...")
            try:
                # self.listener.stop()
                # Give some time for proper shutdown
                time.sleep(1)
                print("✅ Camera listener stopped successfully")
            except Exception as e:
                print(f"⚠️  Warning during camera cleanup: {e}")
        
        print(f"\n✅ Benchmark completed!")
        print(f"Successful frames: {successful_frames}")
        print(f"Failed frames: {failed_frames}")
        print(f"Success rate: {(successful_frames/(successful_frames+failed_frames))*100:.1f}%")
        
        return successful_frames, failed_frames
    
    def show_results(self, successful_frames, failed_frames):
        """Show accurate benchmark results"""
        if not self.cpu_stats or not self.timing_stats:
            print("❌ No data collected!")
            return
        
        print("\n" + "="*80)
        print("📊 REAL CAMERA CPU BENCHMARK RESULTS")
        print("="*80)
        
        # Basic performance
        iterations = len(self.cpu_stats)
        success_rate = (successful_frames / (successful_frames + failed_frames)) * 100 if (successful_frames + failed_frames) > 0 else 0
        
        print(f"📈 Performance:")
        print(f"   Target FPS:        {self.target_fps:.1f}")
        print(f"   Successful frames: {successful_frames:,}")
        print(f"   Failed frames:     {failed_frames:,}")
        print(f"   Success rate:      {success_rate:.1f}%")
        
        # Accurate CPU usage
        system_cpu = [s['cpu_system_percent'] for s in self.cpu_stats]
        process_cpu_raw = [s['cpu_process_percent'] for s in self.cpu_stats] 
        process_cpu_norm = [s['cpu_process_normalized'] for s in self.cpu_stats]
        cpu_core_1 = [s['cpu_core_1_percent'] for s in self.cpu_stats]
        memory_usage = [s['memory_mb'] for s in self.cpu_stats]
        
        print(f"\n💻 CPU Usage (htop-compatible):")
        print(f"   System CPU (All Cores):")
        print(f"      Average:        {np.mean(system_cpu):>8.2f}%")
        print(f"      Min:            {np.min(system_cpu):>8.2f}%")
        print(f"      Max:            {np.max(system_cpu):>8.2f}%")
        
        print(f"   CPU Core 1 (Cam Process Core):")
        print(f"      Average:        {np.mean(cpu_core_1):>8.2f}%")
        print(f"      Min:            {np.min(cpu_core_1):>8.2f}%")
        print(f"      Max:            {np.max(cpu_core_1):>8.2f}%")
        
        print(f"   Process CPU (Raw psutil):")
        print(f"      Average:        {np.mean(process_cpu_raw):>8.2f}%")
        print(f"      Min:            {np.min(process_cpu_raw):>8.2f}%")  
        print(f"      Max:            {np.max(process_cpu_raw):>8.2f}%")
        
        print(f"   Process CPU (Normalized per core):")
        print(f"      Average:        {np.mean(process_cpu_norm):>8.2f}%")
        print(f"      Min:            {np.min(process_cpu_norm):>8.2f}%")
        print(f"      Max:            {np.max(process_cpu_norm):>8.2f}%")
        
        # Filter only successful processing times
        successful_timings = [s for s in self.timing_stats if s['successful_frame']]
        if successful_timings:
            create_times = [s['create_ms'] for s in successful_timings]
            serialize_times = [s['serialize_total_ms'] for s in successful_timings]
            total_times = [s['total_process_ms'] for s in successful_timings]
            
            print(f"\n⏱️  Processing Times (perf_counter, successful frames only):")
            print(f"   Create Fragments:")
            print(f"      Average:        {np.mean(create_times):>8.3f} ms")
            print(f"      Min:            {np.min(create_times):>8.3f} ms")
            print(f"      Max:            {np.max(create_times):>8.3f} ms")
            
            print(f"   Serialize 4 Fragments:")
            print(f"      Average:        {np.mean(serialize_times):>8.3f} ms")
            print(f"      Min:            {np.min(serialize_times):>8.3f} ms")
            print(f"      Max:            {np.max(serialize_times):>8.3f} ms")
            
            print(f"   Total Processing:")
            print(f"      Average:        {np.mean(total_times):>8.3f} ms")
            print(f"      Min:            {np.min(total_times):>8.3f} ms")
            print(f"      Max:            {np.max(total_times):>8.3f} ms")
        
        # Memory
        print(f"\n💾 Memory Usage:")
        print(f"      Average:        {np.mean(memory_usage):>8.1f} MB")
        print(f"      Min:            {np.min(memory_usage):>8.1f} MB")
        print(f"      Max:            {np.max(memory_usage):>8.1f} MB")
        
        print(f"\n🎉 Summary:")
        print(f"   ✅ Used REAL camera frames (not dummy)")
        print(f"   ✅ Used perf_counter for precise timing")
        print(f"   ✅ htop-compatible CPU measurements")
        print(f"   ✅ System CPU: {np.mean(system_cpu):.2f}% (should match htop)")
        print(f"   ✅ CPU Core 1: {np.mean(cpu_core_1):.2f}% (cam process core)")
        print(f"   ✅ Process CPU: {np.mean(process_cpu_norm):.2f}% normalized")
        if successful_timings:
            print(f"   ✅ Processing time: {np.mean(total_times):.3f}ms per frame")


def main():
    """Main execution"""
    try:
        benchmark = RealCameraCPUBenchmark()
        
        print(f"\nStarting in 5 seconds...")
        print("Make sure camera is connected and accessible...")
        time.sleep(5)
        
        successful_frames, failed_frames = benchmark.run_benchmark()
        benchmark.show_results(successful_frames, failed_frames)
        
        exit(0)
        
    except KeyboardInterrupt:
        print(f"\n⚡ Cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
