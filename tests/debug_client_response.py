import json
import threading
import time
from datetime import datetime

import requests
import uvicorn
from fastapi import FastAPI

from avena_commons.event_listener import Event, Result

# Serwer do odbierania odpowiedzi zwrotnych
response_app = FastAPI()
received_responses = []


@response_app.post("/event")
async def handle_response(event: Event):
    """Odbiera odpowiedzi zwrotne z danymi stanu"""
    global received_responses

    print(f"\n🎯 ODEBRANO ODPOWIEDŹ ZWROTNĄ:")
    print(f"   Source: {event.source}")
    print(f"   Event type: {event.event_type}")
    print(f"   Result: {event.result.result if event.result else 'None'}")

    if event.data:
        print(f"📊 DANE STANU KLIENTA ({len(event.data)} kluczy):")
        print(json.dumps(event.data, indent=2, ensure_ascii=False))
    else:
        print("❌ Brak danych w odpowiedzi")

    print("=" * 70)

    received_responses.append(event)
    return {"status": "ok"}


def start_response_server():
    """Uruchamia serwer odpowiedzi w osobnym wątku"""
    config = uvicorn.Config(
        response_app, host="127.0.0.1", port=9600, log_level="error", access_log=False
    )
    server = uvicorn.Server(config)
    server.run()


def get_client_internal_state(client_name, address, port):
    """
    Próbuje pobrać wewnętrzny stan klienta (self._state) wysyłając CMD_GET_STATE
    i czeka na odpowiedź.
    """
    url = f"http://{address}:{port}/event"

    event_data = {
        "source": "debug_client",
        "source_address": "127.0.0.1",
        "source_port": 9600,
        "destination": client_name,
        "destination_address": address,
        "destination_port": port,
        "event_type": "CMD_GET_STATE",
        "data": {},
        "to_be_processed": True,  # Wymaga przetworzenia
        "maximum_processing_time": 20.0,
        "timestamp": datetime.now().isoformat(),
        "id": int(time.time()),
    }

    print(f"=== POBIERANIE STANU KLIENTA {client_name} ===")
    print(f"URL: {url}")
    print(f"Wysyłanie CMD_GET_STATE...")

    try:
        response = requests.post(url, json=event_data, timeout=10)
        print(f"✅ Response status: {response.status_code}")

        if response.status_code == 200:
            print("✅ CMD_GET_STATE wysłane pomyślnie")
            print("⏳ Czekam na odpowiedź ze stanem...")
        else:
            print(f"❌ Błąd wysyłania CMD_GET_STATE: {response.status_code}")
            print(f"Response: {response.text}")

    except Exception as e:
        print(f"❌ Błąd podczas wysyłania CMD_GET_STATE: {e}")

    print("=" * 50)


# Test wszystkich klientów
clients = [
    ("test_9201", "127.0.0.1", 9201),
    ("test_9202", "127.0.0.1", 9202),
    ("test_9203", "127.0.0.1", 9203),
]

if __name__ == "__main__":
    print("🚀 URUCHAMIANIE SERWERA ODPOWIEDZI NA PORCIE 9600...")

    # Uruchom serwer odpowiedzi w osobnym wątku
    server_thread = threading.Thread(target=start_response_server, daemon=True)
    server_thread.start()

    # Poczekaj na uruchomienie serwera
    time.sleep(2)

    print("🔍 ROZPOCZYNANIE TESTÓW KLIENTÓW")
    print("=" * 70)

    for client_name, address, port in clients:
        print(f"\n🔍 TESTOWANIE KLIENTA: {client_name}")
        print("=" * 70)

        # Wyślij tylko jeden CMD_GET_STATE na klienta
        get_client_internal_state(client_name, address, port)
        time.sleep(2)  # Czas na odpowiedź

    print(f"\n📊 PODSUMOWANIE: Odebrano {len(received_responses)} odpowiedzi")
    print("⏳ Czekam jeszcze 5 sekund na późne odpowiedzi...")
    time.sleep(5)
    print(f"📊 FINALNE PODSUMOWANIE: Odebrano {len(received_responses)} odpowiedzi")
    print("\n✅ ZAKOŃCZONO WSZYSTKIE TESTY")
