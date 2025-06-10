import mmap
import os
import pickle

import posix_ipc


class AvenaComm:
    """
    Main Communication Module. It utilizes a shared memory buffer synchronized using semaphores.

    comm_name: str = name for shm and semaphore connection
    semaphore_timeout: float = timeout for semaphore lock
    shm_size: int = size of the shm buffers
    data: any = data to be saved in the shared memory buffer

    save_and_unlock(): -> returns boolean

    lock_and_read(): -> returns boolean, data

    print_errors(): -> prints lock, and other errors
    """

    def __init__(
        self,
        comm_name,
        shm_size=0,
        semaphore_timeout=1,
        data=[],
        message_logger=None,
        use_pickle=1,
        debug=False,
    ):
        self.comm_name = "/" + comm_name
        self.comm_name_lock = self.comm_name + "_semaphore"
        self.comm_name_shm = self.comm_name + "_shm"
        self.shm_size = shm_size
        self.semaphore_timeout = semaphore_timeout
        self.lock_acquired = False
        self.lock_counter = 0
        self.error_counter = 0
        self.message_logger = message_logger
        # self.use_pickle = use_pickle
        self.data = data
        self._debug = debug
        format_shm = False

        try:
            self.semaphore = posix_ipc.Semaphore(self.comm_name_lock)
            self._info(f"An existing semaphore has been found: {self.comm_name_lock}")
        except posix_ipc.ExistentialError:
            self.semaphore = posix_ipc.Semaphore(
                self.comm_name_lock, posix_ipc.O_CREX, initial_value=1, mode=0o777
            )
            self._info("New semaphore created: " + self.comm_name_lock)

        try:
            self.shm = posix_ipc.SharedMemory(self.comm_name_shm)
            self._info(
                "An existing shared memory has been found: " + self.comm_name_shm
            )
        except posix_ipc.ExistentialError:
            self.shm = posix_ipc.SharedMemory(
                self.comm_name_shm, posix_ipc.O_CREX, size=self.shm_size, mode=0o777
            )
            self._info("new shared memory created: " + self.comm_name_shm)
            format_shm = True

        # MMap the shared memory
        self.mmap = mmap.mmap(self.shm.fd, self.shm_size)

        os.close(self.shm.fd)

        if int.from_bytes(self.mmap[:4], byteorder="big") == 0:
            format_shm = True

        if format_shm:
            self._info(f"No data in {self.comm_name_shm} shared memory, formating...")
            if self.semaphore_lock():
                self._send_to_shm(data)
                self.semaphore_unlock()

    def _check_length(self, length):
        if length > self.shm_size:
            self.error_counter += 1
            return False
        else:
            return True

    def _serialize_data(self, data):
        try:
            serialized_data = pickle.dumps(data, protocol=5)
            if serialized_data == False:
                self._error("Error while serializing data")
            return True, serialized_data
        except (pickle.PickleError, EOFError):
            self.error_counter += 1
            self._error(f"Error while serializing data [{data}]")
            return False, None

    def _deserialize_data(self, data):
        try:
            deserialized_data = pickle.loads(data)
            return True, deserialized_data
        except Exception as e:
            self.error_counter += 1
            self._error(f"Error while deserializing data [{data}]: {e}")
            return False, []

    def semaphore_lock(self) -> bool:
        try:
            self.semaphore.acquire(timeout=self.semaphore_timeout)
            self.lock_acquired = True
            return True
        except (posix_ipc.BusyError, posix_ipc.SignalError):
            self.lock_counter += 1
            self.lock_acquired = False
            return False

    def semaphore_unlock(self):
        if self.lock_acquired:
            self.semaphore.release()
            self.lock_acquired = False

    def _send_to_shm(self, data):
        """
        Save serialized data to shared memory buffer.
        """
        serialization_ok, serialized_data = self._serialize_data(data)
        length = len(serialized_data)

        if serialization_ok == False:
            raise Exception("Error while serializing data")

        if self._check_length(length) and serialization_ok:
            self.mmap[0:4] = length.to_bytes(4, byteorder="big")
            self.mmap[4 : 4 + length] = serialized_data
            self.mmap.flush()
            return True
        return False

    def _recv_from_shm(self):
        """
        Receive and deserialize data from shared memory buffer.

        return bool, data
        """
        length = int.from_bytes(self.mmap[:4], byteorder="big")
        if self._check_length(length):
            data = self.mmap[4 : 4 + length]
            deserialization_ok, data_deserialized = self._deserialize_data(data)
            if deserialization_ok:
                return True, data_deserialized
        return False, []

    def lock_and_read(self):
        """
        Lock semaphore and read data from shared memory buffer.

        return bool, data
        """
        if self.semaphore_lock():
            read_ok, data = self._recv_from_shm()
            return read_ok, data
        else:
            return False, []

    def save_and_unlock(self, data):
        """
        Save data to shared memory buffer and unlock semaphore.
        """
        save_ok = self._send_to_shm(data)
        self.semaphore_unlock()
        return save_ok

    def clear(self):
        self.mmap.close()
        posix_ipc.unlink_shared_memory(self.comm_name_shm)
        self.semaphore.release()
        self.semaphore.unlink()

    def print_errors(self):
        self._info(
            f"Connection: {self.comm_name_shm} - lock_counter: {self.lock_counter}, error_counter: {self.error_counter}"
        )

    def _info(self, message):
        if self._debug:
            if self.message_logger:
                self.message_logger.info(message)
            else:
                print(message)

    def _error(self, message):
        if self.message_logger:
            self.message_logger.error(message)
        else:
            print(message)

    def __str__(self):
        return f"Connection: {self.comm_name_shm} - lock_counter: {self.lock_counter}, error_counter: {self.error_counter}"

    def __del__(self):
        """Unlock Sempahore on object deletion."""
        self.semaphore_unlock()
