from avena_commons.util.logger import MessageLogger


class EtherCatSlave:
    def __init__(
        self, master, address, message_logger: MessageLogger | None = None, debug=True
    ):
        self.address = address
        self.message_logger = message_logger
        self.debug = debug
        self.master = master
        self.master.slaves[self.address].config_func = self._config_function

    def _config_function(self, slave_pos):
        pass

    def _read_pdo(self):
        pass

    def _write_pdo(self):
        pass

    def _process(self):
        pass


class EtherCatDevice:
    def __init__(
        self,
        bus,
        vendor_code,
        product_code,
        address,
        configuration,
        message_logger: MessageLogger | None = None,
        debug=True,
    ):
        self.bus = bus
        self.vendor_code = vendor_code
        self.product_code = product_code
        self.address = address
        self.message_logger = message_logger
        self.debug = debug
        self.configuration = configuration
