#!/usr/bin/env python3
"""
Skrypt do uruchamiania wszystkich testowych usług jednocześnie.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


class ServiceManager:
    """Zarządza procesami testowych usług."""

    def __init__(self):
        self.processes = {}
        self.project_root = Path(__file__).parent.parent.parent
        self.services_dir = Path(__file__).parent

    def start_service(self, service_name: str, script_path: str, args: list = None) -> bool:
        """
        Uruchamia pojedynczą usługę w osobnym procesie.

        Args:
            service_name: Nazwa usługi do wyświetlania
            script_path: Ścieżka do skryptu usługi
            args: Dodatkowe argumenty dla skryptu

        Returns:
            True jeśli uruchomiono pomyślnie
        """
        try:
            # Przygotuj środowisko
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root / "src")

            # Przygotuj komendę
            cmd = [sys.executable, script_path]
            if args:
                cmd.extend(args)

            print(f"🚀 Uruchamianie {service_name}...")

            # Uruchom proces
            process = subprocess.Popen(cmd, env=env, cwd=str(self.services_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True)

            self.processes[service_name] = process

            # Sprawdź czy proces się uruchomił
            time.sleep(0.5)
            if process.poll() is None:
                print(f"✅ {service_name} uruchomiony (PID: {process.pid})")
                return True
            else:
                stdout, stderr = process.communicate()
                print(f"❌ {service_name} nie uruchomił się")
                if stderr:
                    print(f"   Błąd: {stderr}")
                return False

        except Exception as e:
            print(f"❌ Błąd uruchamiania {service_name}: {e}")
            return False

    def start_all_services(self) -> bool:
        """
        Uruchamia wszystkie testowe usługi.

        Returns:
            True jeśli wszystkie usługi uruchomiono pomyślnie
        """
        print("=" * 60)
        print("🎯 Uruchamianie testowych usług dla Orchestratora")
        print("=" * 60)

        # Lista usług do uruchomienia
        services = [
            ("IO Service (port 8001)", "io_service.py"),
            ("Supervisor 1 (port 8002)", "supervisor_service.py", ["1"]),
            ("Supervisor 2 (port 8003)", "supervisor_service.py", ["2"]),
            ("MunchiesAlgo (port 8004)", "munchies_algo_service.py"),
        ]

        success_count = 0
        for service_info in services:
            service_name = service_info[0]
            script_name = service_info[1]
            args = service_info[2] if len(service_info) > 2 else None

            script_path = self.services_dir / script_name
            if self.start_service(service_name, str(script_path), args):
                success_count += 1

            time.sleep(1)  # Odstęp między uruchamianiem usług

        print("\n" + "=" * 60)
        if success_count == len(services):
            print(f"🎉 Wszystkie {len(services)} usług uruchomiono pomyślnie!")
            print("\n📋 Porty usług:")
            print("   - IO Service:      http://127.0.0.1:8001")
            print("   - Supervisor 1:    http://127.0.0.1:8002")
            print("   - Supervisor 2:    http://127.0.0.1:8003")
            print("   - MunchiesAlgo:    http://127.0.0.1:8004")
            print("\n🔧 Możesz teraz uruchomić Orchestrator na porcie 8000")
            print("=" * 60)
            return True
        else:
            print(f"⚠️  Uruchomiono tylko {success_count}/{len(services)} usług")
            print("=" * 60)
            return False

    def stop_all_services(self):
        """Zatrzymuje wszystkie uruchomione usługi."""
        print("\n🛑 Zatrzymywanie wszystkich usług...")

        for service_name, process in self.processes.items():
            try:
                if process.poll() is None:  # Proces nadal działa
                    print(f"   Zatrzymywanie {service_name}...")
                    process.terminate()

                    # Czekaj na graceful shutdown
                    try:
                        process.wait(timeout=5)
                        print(f"   ✅ {service_name} zatrzymany")
                    except subprocess.TimeoutExpired:
                        print(f"   ⚠️  {service_name} - wymuś zamknięcie...")
                        process.kill()
                        process.wait()
                        print(f"   💀 {service_name} zabity")
                else:
                    print(f"   ℹ️  {service_name} już zatrzymany")

            except Exception as e:
                print(f"   ❌ Błąd zatrzymywania {service_name}: {e}")

        self.processes.clear()
        print("🏁 Wszystkie usługi zatrzymane")

    def show_status(self):
        """Pokazuje status wszystkich usług."""
        print("\n📊 Status usług:")
        print("-" * 40)

        if not self.processes:
            print("   Brak uruchomionych usług")
            return

        for service_name, process in self.processes.items():
            if process.poll() is None:
                print(f"   ✅ {service_name} - działa (PID: {process.pid})")
            else:
                print(f"   ❌ {service_name} - zatrzymany")

    def wait_for_services(self):
        """Czeka na zatrzymanie wszystkich usług."""
        try:
            print("\n⌛ Usługi działają... (Naciśnij Ctrl+C aby zatrzymać)")

            while True:
                time.sleep(1)

                # Sprawdź czy jakieś procesy się zatrzymały
                stopped_services = []
                for service_name, process in self.processes.items():
                    if process.poll() is not None:
                        stopped_services.append(service_name)

                # Usuń zatrzymane usługi
                for service_name in stopped_services:
                    del self.processes[service_name]
                    print(f"⚠️  {service_name} zatrzymał się niespodziewanie")

                # Jeśli wszystkie usługi się zatrzymały
                if not self.processes:
                    print("ℹ️  Wszystkie usługi zatrzymały się")
                    break

        except KeyboardInterrupt:
            print("\n🛑 Otrzymano sygnał przerwania...")


def main():
    """Główna funkcja."""
    manager = ServiceManager()

    # Obsługa sygnału przerwania
    def signal_handler(sig, frame):
        print("\n🛑 Otrzymano sygnał zatrzymania...")
        manager.stop_all_services()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Sprawdź argumenty wiersza poleceń
        if len(sys.argv) > 1:
            command = sys.argv[1].lower()

            if command == "status":
                manager.show_status()
                return
            elif command == "stop":
                manager.stop_all_services()
                return
            elif command in ["help", "-h", "--help"]:
                print("Użycie:")
                print("  python run_all_services.py          # Uruchom wszystkie usługi")
                print("  python run_all_services.py status   # Pokaż status")
                print("  python run_all_services.py stop     # Zatrzymaj wszystkie")
                print("  python run_all_services.py help     # Pokaż pomoc")
                return

        # Uruchom wszystkie usługi
        if manager.start_all_services():
            manager.wait_for_services()
        else:
            print("⚠️  Nie udało się uruchomić wszystkich usług")
            manager.stop_all_services()
            sys.exit(1)

    except Exception as e:
        print(f"❌ Nieoczekiwany błąd: {e}")
        manager.stop_all_services()
        sys.exit(1)
    finally:
        manager.stop_all_services()


if __name__ == "__main__":
    main()
