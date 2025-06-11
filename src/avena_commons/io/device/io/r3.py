from avena_commons.util.logger import MessageLogger, debug

from .EtherCatSlave import EtherCatDevice, EtherCatSlave


# TODO: CHECK IF THIS IS CORRECT
class R3_Slave(EtherCatSlave):
    def __init__(
        self, master, address, message_logger: MessageLogger | None = None, debug=True
    ):
        super().__init__(master, address, message_logger, debug)
        self.inputs_ports = [0 for _ in range(16)]
        self.outputs_ports = [0 for _ in range(16)]

    def _config_function(self, slave_pos):
        debug(
            f"Configuring {self.address} {slave_pos}",
            message_logger=self.message_logger,
        )

    def _read_pdo(self):
        # Get the input bytes from the slave
        input_bytes = self.master.slaves[self.address].input

        # Convert the 2 bytes into a 16-bit integer
        input_value = int.from_bytes(input_bytes, byteorder="little")

        # Convert each bit into a boolean value (0 or 1)
        for i in range(16):
            self.inputs_ports[i] = (input_value >> i) & 1

    def _write_pdo(self):
        output_bytes = bytes([self.outputs_ports[i] for i in range(16)])
        self.master.slaves[self.address].output = output_bytes

    def _process(self):
        # TODO: Add logic to process the inputs and outputs
        pass

    def read_input(self, port: int):
        return self.inputs_ports[port]

    def write_output(self, port: int, value: bool):
        self.outputs_ports[port] = value


class R3(EtherCatDevice):
    def __init__(
        self, bus, address, message_logger: MessageLogger | None = None, debug=True
    ):
        product_code = 4353  # TODO: CHANGE THIS
        vendor_code = 2965  # TODO: CHANGE THIS
        super().__init__(bus, vendor_code, product_code, address, message_logger, debug)
        self.inputs_ports = [0 for _ in range(16)]
        self.outputs_ports = [0 for _ in range(16)]

    def read_input(self, port: int):
        self.inputs_ports[port] = self.bus.read_input(self.address, port)
        return self.inputs_ports[port]

    def read_output(self, port: int):
        print(f"read_output {port}")
        return self.outputs_ports[port]

    def write_output(self, port: int, value: bool):
        self.outputs_ports[port] = value
        self.bus.write_output(self.address, port, value)
