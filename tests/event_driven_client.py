import argparse
import os
import sys
import threading
import time

from dotenv import load_dotenv

load_dotenv()

# import numpy as np
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from avena_commons.event_listener import Event, EventListener
from avena_commons.event_listener.types import IoAction, IoSignal, KdsAction

# import psycopg
# from dotenv import load_dotenv
# from lib.munchies.path_generator import *

# load_dotenv(override=True)

# db_host = os.getenv("DB_HOST")
# db_port = os.getenv('DB_PORT')
# db_name = os.getenv("DB_NAME")
# db_user = os.getenv("DB_USER")
# db_password = os.getenv("DB_PASSWORD")
# db_connection = psycopg.connect(host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_password)
# path_generator = PathGenerator(db_connection=db_connection)

# Default port value
DEFAULT_PORT = 8002
DESTINATION_NAME = "io"

# python3 tools/event_driven_client.py --port 8002 --name --event 2

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Event-driven client for Munchies algorithm"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Port number for the destination (default: 8002)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=DESTINATION_NAME,
        help="Name of the destination (default: io2)",
    )
    parser.add_argument(
        "--event",
        type=int,
        default=0,
        help="Event number to send: 1=block_for_client, 2=unblock_for_client, 3=block_chamber, 4=unblock_chamber, 5=partition_up, 6=partition_down, 7=is_product_present, 8=is_sauce_present, 9=oven_start, 10=oven_restart, 22=wydawka_move (default: 0)",
    )
    args = parser.parse_args()

    PORT = args.port
    event_number = args.event

    base_url = f"http://127.0.0.1:{PORT}"

    listener = EventListener(name="munchies_algo", port=8000)
    thread1 = threading.Thread(target=listener.start)
    thread1.start()
    time.sleep(1)

    event1 = "chamber_block_for_client"
    event2 = "chamber_unblock_for_client"
    event3 = "chamber_block_chamber"
    event4 = "chamber_unblock_chamber"
    event5 = "chamber_partition_up"
    event6 = "chamber_partition_down"
    event7 = "chamber_is_product_present"
    event8 = "chamber_is_sauce_present"
    event9 = "oven_start"
    event10 = "oven_restart"
    event11 = "oven_sensor_state"
    event12 = "oven_open"
    event30 = "oven_emergency_drop"
    event31 = "oven_emergency_drop_up"

    event17 = "feeder_place_tray"
    event18 = "wydawka_move"
    event19 = "chamber_initialize"
    event22 = "pastransmisyjny_move"

    event23 = "sauce_rebase"
    event24 = "sauce_run"
    event25 = "sauce_is_present"
    event26 = "sauce_run_back"
    event27 = "test_sauce"

    event69 = "wydawka_move"  # nie kończący się ruch

    event115 = "oven_read_temperature"  # FIXME BRAKUJE GO

    event66 = "order_update"

    event70 = "3 feedery wydają tackę i wydawki robią ruch"

    event80 = "pump_on"
    event81 = "pump_off"

    event90 = "take_photo_qr"
    event91 = "take_photo_box"
    event92 = "current_position"

    event150 = "nayax_charge"

    event200 = "CMD_INITIALIZED"
    event201 = "CMD_RUN"
    event300 = "CMD_HEALTH_CHECK"
    event307 = "CMD_ACK"
    event404 = "CMD_PAUSE"
    event500 = "CMD_STOPPED"
    event501 = "CMD_RESTART"

    if event_number > 0:
        # Convert event number to event name
        data_origin = {"device_id": 2, "sauce_id": 33}  # TUTAJ ZMIENIASZ DEVICE_ID
        data = data_origin.copy()
        event_name = None
        is_processed = True

        if event_number == 1:
            event_name = event1
        elif event_number == 2:
            event_name = event2
        elif event_number == 3:
            event_name = event3
        elif event_number == 4:
            event_name = event4
        elif event_number == 5:
            event_name = event5
        elif event_number == 6:
            event_name = event6
        elif event_number == 7:
            event_name = event7
            data = IoSignal(
                device_type="",
                device_id=data["device_id"],
                signal_name="is_product_present",
                signal_value=0,
            ).to_dict()
            is_processed = False
        elif event_number == 8:
            data = IoSignal(
                device_type="",
                device_id=data["sauce_id"],
                signal_name="is_sauce_present",
                signal_value=0,
            ).to_dict()
            is_processed = False
            event_name = event8
        elif event_number == 9:
            event_name = event9
            data = IoAction(device_type="oven", device_id=1).to_dict()
            is_processed = True
        elif event_number == 10:
            event_name = event10
            data = IoAction(device_type="oven", device_id=1).to_dict()
            is_processed = True

        elif event_number == 11:
            event_name = event11
            data = IoSignal(
                device_type="oven",
                device_id=data["device_id"],
                signal_name="OOC1",
                signal_value=0,
            ).to_dict()
            is_processed = False
        elif event_number == 12:
            event_name = event11
            data = IoSignal(
                device_type="oven",
                device_id=data["device_id"],
                signal_name="OOC2",
                signal_value=0,
            ).to_dict()
            is_processed = False
        elif event_number == 13:
            event_name = event11
            data = IoSignal(
                device_type="oven",
                device_id=data["device_id"],
                signal_name="OOC3",
                signal_value=0,
            ).to_dict()
            is_processed = False
        elif event_number == 14:
            event_name = event11
            data = IoSignal(
                device_type="oven",
                device_id=data["device_id"],
                signal_name="OIC1",
                signal_value=0,
            ).to_dict()
            is_processed = False
        elif event_number == 15:
            event_name = event11
            data = IoSignal(
                device_type="oven",
                device_id=data["device_id"],
                signal_name="OIC2",
                signal_value=0,
            ).to_dict()
            is_processed = False
        elif event_number == 16:
            event_name = event11
            data = IoSignal(
                device_type="oven",
                device_id=data["device_id"],
                signal_name="OIC3",
                signal_value=0,
            ).to_dict()
            is_processed = False
        elif event_number == 17:
            event_name = event17
            data = IoAction(device_type="feeder", device_id=data["device_id"]).to_dict()
            is_processed = True
        elif event_number == 18:
            event_name = event18
            data = IoAction(
                device_type="wydawka", device_id=data["device_id"]
            ).to_dict()
            is_processed = True
        elif event_number == 19:
            event_name = event19
            data = IoAction(device_type="", device_id=data["device_id"]).to_dict()
            is_processed = True
        elif event_number == 22:
            event_name = event22
            data = IoAction(
                device_type="wydawka", device_id=data["device_id"]
            ).to_dict()
            is_processed = True
        elif event_number == 23:
            event_name = event23
            data = IoAction(device_type="sauce", device_id=data["sauce_id"]).to_dict()
            is_processed = True
        elif event_number == 24:
            event_name = event24
            data = IoAction(device_type="sauce", device_id=data["sauce_id"]).to_dict()
            is_processed = True
        elif event_number == 25:
            event_name = event25
            data = IoAction(device_type="sauce", device_id=data["sauce_id"]).to_dict()
            is_processed = False
        elif event_number == 26:
            event_name = event26
            data = IoAction(device_type="sauce", device_id=data["sauce_id"]).to_dict()
            is_processed = True
        elif event_number == 30:
            event_name = event30
            data = IoAction(device_type="oven", device_id=1).to_dict()
            is_processed = True
        elif event_number == 31:
            event_name = event31
            data = IoAction(device_type="oven", device_id=1).to_dict()
            is_processed = True
        elif event_number == 66:
            event_name = event66
            data = KdsAction(
                order_number=None, pickup_number=1, message="ODBIERAJ"
            ).to_dict()

        elif event_number == 150:
            event_name = event150
            data = {"charge": 0.09}
        elif event_number == 200:
            event_name = event200
            data = {}
        elif event_number == 201:
            event_name = event201
            data = {}
        elif event_number == 300:
            event_name = event300
            data = {}
        elif event_number == 307:
            event_name = event307
            data = {}
        elif event_number == 404:
            event_name = event404
            data = {}
        elif event_number == 500:
            event_name = event500
            data = {}
        elif event_number == 501:
            event_name = event501
            data = {}

        elif event_number == 69:
            event_name = event69
            data = IoAction(
                device_type="wydawka", device_id=data["device_id"]
            ).to_dict()
            is_processed = True

        elif event_number == 27:
            data = IoAction(device_type="sauce", device_id=data["sauce_id"]).to_dict()

            for i in range(31, 50):
                print("~~~~~~~~~~~~")
                print(f"Test sauce event iteration: {i + 1}/50")
                # event rebase
                try:
                    event = Event(
                        source="munchies_algo",
                        source_port=8000,
                        destination=args.name,
                        destination_port=PORT,
                        event_type="sauce_rebase",
                        to_be_processed=True,
                        data=data,
                    )
                    print(f"Rebase number: {i + 1}")
                    response = requests.post(f"{base_url}/event", json=event.to_dict())
                    if response.status_code != 200:
                        print(f"Response status code: {response.status_code}")

                    time.sleep(2.5)
                except KeyboardInterrupt:
                    print("Stopping sauce_rebase event loop.")
                    print(f"Numer rebase przy którym przerwano: {i + 1}")
                except Exception as e:
                    print(f"Error during sauce_rebase event: {e}")

                try:
                    event = Event(
                        source="munchies_algo",
                        source_port=8000,
                        destination=args.name,
                        destination_port=PORT,
                        event_type="sauce_run",
                        to_be_processed=True,
                        data=data,
                    )
                    print(f"Sauce run number: {i + 1}")
                    response = requests.post(f"{base_url}/event", json=event.to_dict())
                    if response.status_code != 200:
                        print(f"Response status code: {response.status_code}")
                    time.sleep(11.5)
                except KeyboardInterrupt:
                    print("Stopping sauce_run event loop.")
                    print(f"Numer sauce run przy którym przerwano: {i + 1}")
                except Exception as e:
                    print(f"Error during sauce_run event: {e}")

            print("Test sauce event completed.")

            event_name = event23
            data = data_origin.copy()
            data = IoAction(device_type="sauce", device_id=data["sauce_id"]).to_dict()
            is_processed = True

        elif event_number == 80:
            event_name = event80
            data = {}
            is_processed = True
        elif event_number == 81:
            event_name = event81
            data = {}
            is_processed = True
        elif event_number == 90:
            event_name = "take_photo_qr"
            data = {
                "qr": 0,
                "qr_rotation": False,
                "try_number": 1,
                "supervisor_number": 1,
            }
            is_processed = True
        elif event_number == 91:
            event_name = "take_photo_box"
            data = {
                "try_number": 2,
                "supervisor_number": 1,
            }
            is_processed = True
        elif event_number == 92:
            event_name = "current_position"
            data = {}
            is_processed = True

        if event_name == event69 and event_number == 69:
            try:
                while True:
                    event = Event(
                        source="munchies_algo",
                        source_port=8000,
                        destination=args.name,
                        destination_port=PORT,
                        event_type=event_name,
                        to_be_processed=is_processed,
                        data=data,
                    )
                    response = requests.post(f"{base_url}/event", json=event.to_dict())
                    print(f"Response status code: {response.status_code}")
                    print(f"Response Event: {event.to_dict()}")
                    time.sleep(10)
            except KeyboardInterrupt:
                print("Stopping wydawka_move event loop.")

        elif event_number == 70:
            try:
                feeder_1_succes = 1099  # Best 1099
                feeder_2_succes = 1040  # Best 1040
                feeder_3_succes = 1002  # Best 1002
                licznik_pentli = 1  # while True:
                for _ in range(100):  ### ILOŚĆ POWTÓRZEŃ
                    for device_id in range(1, 4):
                        # device_id = 2
                        data = {"device_id": device_id, "sauce_id": 1}
                        event = Event(
                            source="munchies_algo",
                            source_port=8000,
                            destination=args.name,
                            destination_port=PORT,
                            event_type=event17,
                            to_be_processed=True,
                            data=data,
                        )
                        response = requests.post(
                            f"{base_url}/event", json=event.to_dict()
                        )

                    # print(f"Response status code: {response.status_code}")
                    # print(f"Response Event: {event.to_dict()}")

                    time.sleep(6)
                    for device_id in range(1, 4):
                        # device_id = 2
                        data = {"device_id": device_id, "sauce_id": 2}
                        event = Event(
                            source="munchies_algo",
                            source_port=8000,
                            destination=args.name,
                            destination_port=PORT,
                            event_type=event18,
                            to_be_processed=True,
                            data=data,
                        )
                        response = requests.post(
                            f"{base_url}/event", json=event.to_dict()
                        )
                        print(f"Response status code: {response.status_code}")
                        print(f"Response Event: {event.to_dict()}")
                        if response:
                            if device_id == 1:
                                feeder_1_succes += 1
                            if device_id == 2:
                                feeder_2_succes += 1
                            if device_id == 3:
                                feeder_3_succes += 1

                        print(f"Feeder 1 success count: {feeder_1_succes}")
                        print(f"Feeder 2 success count: {feeder_2_succes}")
                        print(f"Feeder 3 success count: {feeder_3_succes}")
                        print(f"Loop count: {licznik_pentli}")
                    licznik_pentli += 1
                    time.sleep(3.5)
            except KeyboardInterrupt:
                print("Stopping wydawka_move event loop.")

        elif event_name == event66:
            event = Event(
                source="munchies_algo",
                source_port=8000,
                destination=args.name,
                destination_address=os.getenv("KDS_LISTENER_ADDRESS"),
                destination_port=os.getenv("KDS_LISTENER_PORT"),
                event_type=event_name,
                data=data,
            )
            response = requests.post(f"{base_url}/event", json=event.to_dict())
            print(f"Response status code: {response.status_code}")
            print(f"Response Event: {event.to_dict()}")
            time.sleep(1)

        elif event_name is not None:
            event = Event(
                source="munchies_algo",
                source_port=8000,
                destination=args.name,
                destination_port=PORT,
                event_type=event_name,
                to_be_processed=is_processed,
                data=data,
                # priority=EventPriority.HIGH,
            )
            response = requests.post(f"{base_url}/event", json=event.to_dict())
            print(f"Response status code: {response.status_code}")
            print(f"Response Event: {event.to_dict()}")
            time.sleep(1)

        else:
            print(
                f"Invalid event number: {event_number}. Please choose proper event number."
            )
    else:
        print("No event specified. Use --event parameter to send an event (1-5)")
