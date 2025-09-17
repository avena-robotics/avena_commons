import os
import sys

# Add the src directory to the system path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from dotenv import load_dotenv
from pupil_apriltags import Detector

from avena_commons.camera.camera import Camera
from avena_commons.camera.driver.general import CameraState
from avena_commons.event_listener import EventListenerState
from avena_commons.util.logger import (
    LoggerPolicyPeriod,
    MessageLogger,
    debug,
    error,
    info,
)
from avena_commons.util.timing_stats import global_timing_stats


def show_intermediate_stats():
    """Pokaż statystyki w trakcie działania."""
    print("\n📊 Statystyki w trakcie działania:")
    operations = global_timing_stats.get_operation_names()
    if operations:
        for op in operations:
            stats = global_timing_stats.get_stats(op)
            if stats and stats["count"] > 0:
                print(f"   {op}: {stats['mean']:.1f}ms ({stats['count']} próbek)")
    else:
        print("   Brak statystyk...")


if __name__ == "__main__":
    try:
        message_logger = MessageLogger(
            filename=f"temp/test_camera.log",
            debug=True,
            period=LoggerPolicyPeriod.LAST_15_MINUTES,
            files_count=40,
        )
        load_dotenv(override=True)

        port = 9900

        print("port: ", port)
        listener = Camera(
            name=f"camera_server_192.168.1.10",
            address="127.0.0.1",
            port=port,
            message_logger=message_logger,
        )
        listener.start()

        # Pozwól na zebranie kilku pomiarów
        import time

        print("⏳ Czekam 10 sekund na zebranie statystyk...")

        # Pokaż statystyki co 2 sekundy
        for i in range(5):
            time.sleep(2)
            print(f"   ... {(i + 1) * 2}s ...")
            show_intermediate_stats()

        # Wyświetl statystyki po zakończeniu testu
        print("\n" + "=" * 60)
        print("📊 STATYSTYKI TIMING Z TESTU KAMERY")
        print("=" * 60)
        global_timing_stats.print_summary()

        # Szczegółowe informacje o konkretnych operacjach
        operations = global_timing_stats.get_operation_names()
        if operations:
            print(f"\n🔍 Zebrano statystyki dla {len(operations)} operacji:")
            for op in operations:
                stats = global_timing_stats.get_stats(op)
                if stats:
                    print(
                        f"   {op}: {stats['mean']:.1f}ms średnio ({stats['count']} próbek)"
                    )
        else:
            print(
                "\n❌ Brak zebranych statystyk - prawdopodobnie test zakończył się zbyt szybko"
            )

    except Exception as e:
        # del message_logger
        error(f"Nieoczekiwany błąd w głównym wątku: {e}", message_logger=None)
        # Wyświetl statystyki nawet przy błędzie
        print("\n📊 Statystyki timing (z błędem):")
        global_timing_stats.print_summary()
    except KeyboardInterrupt:
        print("\n⚡ Test przerwany przez użytkownika")
        print("\n" + "=" * 60)
        print("📊 FINALNE STATYSTYKI TIMING")
        print("=" * 60)
        global_timing_stats.print_summary()

        # Szczegółowa analiza
        operations = global_timing_stats.get_operation_names()
        if operations:
            print(f"\n🔍 Analiza {len(operations)} operacji:")
            for op in operations:
                stats = global_timing_stats.get_stats(op)
                if stats:
                    print(f"   {op}:")
                    print(f"      Średnia: {stats['mean']:>8.1f} ms")
                    print(f"      Min:     {stats['min']:>8.1f} ms")
                    print(f"      Max:     {stats['max']:>8.1f} ms")
                    print(f"      Próbek:  {stats['count']:>8}")
                    if stats["count"] > 1:
                        variance = (stats["max"] - stats["min"]) * 1000
                        stability = (
                            1 - (stats["max"] - stats["min"]) / stats["mean"]
                        ) * 100
                        print(f"      Rozrzut: {variance:>8.1f} ms")
                        print(f"      Stabil.: {stability:>8.1f} %")
    finally:
        # Zawsze wyświetl podsumowanie na koniec
        operation_count = len(global_timing_stats.get_operation_names())
        print(f"\n🏁 Test zakończony. Dostępne operacje timing: {operation_count}")

        # Jeśli test zakończył się normalnie (nie przez Ctrl+C), pokaż statystyki tutaj też
        if operation_count > 0:
            print("\n" + "=" * 60)
            print("📊 STATYSTYKI TIMING (końcowe)")
            print("=" * 60)
            global_timing_stats.print_summary()
