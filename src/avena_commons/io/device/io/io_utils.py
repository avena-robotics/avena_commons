"""Utility functions for device initialization."""


def init_device_di(cls, first_index=0, count=16):
    """Initialize digital input properties for a device class.

    Creates properties di0, di1, ... diN on the class for easy access to digital inputs.

    Args:
        cls: The device class to add properties to
        first_index: Starting index for digital inputs (default: 0)
        count: Number of digital inputs to create (default: 16)
    """
    for i in range(count):

        def getter(self, idx=first_index + i):
            return self.di(idx)

        setattr(cls, f"di{first_index + i}", property(getter))


def init_device_do(cls, first_index=0, count=16):
    """Initialize digital output properties for a device class.

    Creates properties do0, do1, ... doN on the class for easy access to digital outputs.

    Args:
        cls: The device class to add properties to
        first_index: Starting index for digital outputs (default: 0)
        count: Number of digital outputs to create (default: 16)
    """
    for i in range(count):

        def getter(self, idx=first_index + i):
            return self.do(idx)

        def setter(self, value, idx=first_index + i):
            return self.do(idx, value)

        setattr(cls, f"do{first_index + i}", property(getter, setter))
