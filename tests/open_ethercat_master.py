import os
import time
import traceback

import pysoem

FREQ = 2000


def get_network_interfaces():
    try:
        return [name for name in os.listdir("/sys/class/net")]
    except Exception as e:
        print(f"Error listing interfaces: {e}")
        return []


def check_ethercat(iface_name: str, device_check_loop: bool = False):
    try:
        try:
            master = pysoem.Master()
            master.open(str(iface_name))
        except Exception as e:
            print(f"Error opening interface {iface_name}: {e}")
            return
        number_of_slaves = (
            master.config_init()
        )  # odpytanie ile urzadzen jest w sieci #TODO: check

        if number_of_slaves <= 0:
            print("No slaves found.")  # tutaj zwraca błąd
            master.close()
            return
        else:
            print(f"Found {number_of_slaves} slaves.")

        for i, slave in enumerate(master.slaves):  # pokazuje co znalazl
            print(f"Slave {i} name='{slave.name}', state={slave.state}")

        for slave in master.slaves:  # zmiana trybu slave na mozliwe do konfiguracji
            slave.state = pysoem.PREOP_STATE
            slave.write_state()

        try:
            master.config_map()  # budowanie mapy komunikatow - pobranie od slave
        except Exception as e:
            print(f"Error: {e}")

        master.config_dc()  # konfiguracja urzadzen

        print("Config done")

        if (
            master.state_check(pysoem.SAFEOP_STATE, 50000) != pysoem.SAFEOP_STATE
        ):  # sprawdzamy czy wszystkie slave sa w trybie SAFEOP - gotowe do pracy
            print("Not all slaves reached SAFEOP.")
            for i, slave in enumerate(master.slaves):
                print(f"  Slave {i} '{slave.name}' state=0x{slave.state:X}")
            return

        master.state = pysoem.OP_STATE  # przejscie do trybu operacyjnego mastera
        master.write_state()

        if (
            master.state_check(pysoem.OP_STATE, 50000) != pysoem.OP_STATE
        ):  # sprawdzamy czy wszystkie slave sa w trybie operacyjnym
            print("Not all slaves reached OP. Changinkg state to OP for them all:")
            for i, slave in enumerate(master.slaves):
                print(f"  Slave {i} '{slave.name}' state=0x{slave.state:X}")

        if device_check_loop:
            for i, slave in enumerate(master.slaves):
                print(f"Slave {i} '{slave.name}' state=0x{slave.state:X}")
            print(master.read_state())
            tick = True
            freq = FREQ
            print_time = time.time()
            while True:
                start = time.time()

                ret = master.receive_processdata(10000)  # odczyt PDO - poczatek ticka
                print(f"Receive process data: {ret}")
                if time.time() - print_time > 1:
                    for i, slave in enumerate(master.slaves):
                        print(f"Slave {slave.name}_{i} state={slave.state}")
                        print(f"Slave {slave.name}_{i} output={slave.output}")
                        print(f"Slave {slave.name}_{i} input={slave.input}")
                        print("--------------------------------")
                    print_time = time.time()

                # if tick:
                #     master.slaves[0].output = b'\x00\x03'
                #     tick = False
                # else:
                #     master.slaves[0].output = b'\x00\x02'
                #     tick = True
                ret = master.send_processdata()  # --- koniec ticka
                print(f"Send process data: {ret}")

                state = master.read_state()
                if state != pysoem.OP_STATE:
                    print(f"Network state: {state}")
                    master.state = pysoem.OP_STATE
                    master.write_state()
                else:
                    print(f"Network state: {state}")

                end = time.time()
                if (end - start) < 1 / freq:
                    time.sleep(1 / freq - (end - start))
                else:
                    print(f"Overtime: {(end - start) * 1000} ms")
        else:
            print("EtherCAT is working on interface:", iface_name)
            for i, slave in enumerate(master.slaves):
                print(f"Slave {i} '{slave.name}' state=0x{slave.state:X}")
                print(f"Slave {i} '{slave.name}' output={slave.output}")
                print(f"Slave {i} '{slave.name}' input={slave.input}")
                # print("--------------------------------")
            master.close()
            return True

    except KeyboardInterrupt:
        print("KeyboardInterrupt, exiting...")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
    master.close()


if __name__ == "__main__":
    interfaces = get_network_interfaces()

    for interface in interfaces:
        print(f"Interface: {interface}")
        is_connected = check_ethercat(interface, device_check_loop=False)
        print("----------------------------------")
