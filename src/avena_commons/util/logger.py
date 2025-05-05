import datetime
import multiprocessing
import os
import time
from enum import Enum
from pathlib import Path

import psutil
from colorify import *


class LoggerPolicyPeriod:
    NONE = 1e20
    LAST_1_MINUTE = 60
    LAST_15_MINUTES = LAST_1_MINUTE * 15
    LAST_HOUR = LAST_1_MINUTE * 60
    LAST_24_HOURS = LAST_HOUR * 24


class DataType(Enum):
    LOG = 0
    CSV = 1


# FIXME zmienic obsluge plikow na pathlib i dorobic automatyczne tworzenie sie podkatalogow:
# from pathlib import Path
# output_file = Path("/foo/bar/baz.txt")
# output_file.parent.mkdir(exist_ok=True, parents=True)
# output_file.write_text("FOOBAR")


class Logger_Receiver:
    def __init__(
        self,
        filename,
        clear_file=True,
        type=DataType.LOG,
        period=LoggerPolicyPeriod.NONE,
        files_count=1,
        create_symlinks=False,
        colors=True,
    ):
        self.base_filename, self.extenstion = os.path.splitext(filename)
        self.clear_file = clear_file
        self.last_file_change_time = time.time()
        self.period = period
        self.files_count = files_count
        self.files = []
        self.csv_header = []
        self.header_written: bool = False
        self.type = type
        self.create_symlinks: bool = create_symlinks
        self.__colors: bool = colors
    def _current_filename(self):
        # Tworzenie nazwy pliku z uwzględnieniem bieżącego czasu
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return f"{self.base_filename}_{timestamp}{self.extenstion}"

    def _create_new_file(self):
        current_filename = self._current_filename()
        link_name = self.base_filename + self.extenstion
        self.files.append(current_filename)
        if (
            self.create_symlinks and os.name != "nt"
        ):  # Only create symlinks on non-Windows systems
            try:
                if os.path.exists(link_name):
                    os.remove(link_name)
                os.symlink(current_filename, link_name)
            except Exception as e:
                print(f"Warning: Could not create symlink: {e}")
        return current_filename

    def run(self, pipe_in):
        # current_filename = self._current_filename()
        # self.files.append(current_filename)
        if self.clear_file:
            current_filename = self._create_new_file()
        else:
            current_filename = f"{self.base_filename}{self.extenstion}"
        try:
            while True:
                if (
                    time.time() - self.last_file_change_time >= self.period
                ):  # sprawdzenie czy nalezy wymienic plik na nowy
                    self.last_file_change_time = time.time()
                    current_filename = self._create_new_file()
                    # current_filename = self._current_filename()
                    # self.files.append(current_filename) # dopisanie do listy plikow
                    self.header_written = False

                if (
                    len(self.files) > self.files_count + 1
                ):  # chce zostawic jeden plik wiecej
                    file_to_delete = self.files.pop(0)
                    try:
                        os.remove(file_to_delete)
                        # print(f"Plik {file_to_delete} został usunięty.")
                    except FileNotFoundError:
                        print(f"Plik {file_to_delete} nie został znaleziony.")
                    except PermissionError:
                        print(f"Brak uprawnień do usunięcia pliku {file_to_delete}.")
                    except Exception as e:
                        print(f"Wystąpił błąd: {e}")

                logger_file = Path(current_filename)
                logger_file.parent.mkdir(exist_ok=True, parents=True)

                with open(current_filename, "a") as file:
                    data = pipe_in.recv()

                    if data == "STOP":
                        break

                    match self.type:
                        case DataType.LOG:
                            [level, message] = data
                            file.write(format_message(message, level, self.__colors) + "\n")

                        case DataType.CSV:
                            data_str = ",".join([str(x) for x in data])
                            if not self.header_written:
                                if (
                                    self.csv_header == []
                                ):  # nie ma jeszcze headera - zapamietuje 1 linie
                                    self.csv_header = data_str
                                else:  # header juz jest zapamietany, dodaje do nowego pliku
                                    file.write(self.csv_header + "\n")
                                self.header_written = True

                            file.write(data_str + "\n")

                    file.flush()

        except KeyboardInterrupt:
            pass


class Logger:
    def __init__(
        self,
        filename,
        type,
        clear_file: bool = True,
        period=LoggerPolicyPeriod.NONE,
        files_count: int = 1,
        create_symlinks: bool = False,
        colors: bool = False,
    ):
        self.filename = filename
        self.type = type
        self.clear_file = clear_file
        self.pipe_out, pipe_in = multiprocessing.Pipe()
        self.process = multiprocessing.Process(
            target=self.run_receiver, args=(pipe_in,)
        )

        self.period = period
        self.files_count = files_count
        self.create_symlinks: bool = create_symlinks
        self.__colors: bool = colors
        self.process.start()
        p = psutil.Process(self.process.pid)

        # Set CPU affinity in a cross-platform way
        try:
            if os.name == "nt":  # Windows
                # On Windows, we use a different CPU core number scheme
                p.cpu_affinity([0])  # Use first CPU as fallback
            else:
                p.cpu_affinity([10])
        except Exception as e:
            print(f"Warning: Could not set CPU affinity: {e}")

    def run_receiver(self, pipe_in):
        # Set process priority only on Unix systems
        if os.name == "posix":  # Unix-like systems
            os.nice(40)

        receiver = Logger_Receiver(
            filename=self.filename,
            clear_file=self.clear_file,
            type=self.type,
            period=self.period,
            files_count=self.files_count,
            create_symlinks=self.create_symlinks,
            colors=self.__colors,
        )
        receiver.run(pipe_in)

    def __del__(self):
        try:
            if self.process.is_alive():
                self.pipe_out.send("STOP")
                self.pipe_out.close()
                self.process.join()
        except BrokenPipeError:
            pass  # Pipe jest już zamknięty, ignorujemy błąd
        except Exception as e:
            print(f"Wystąpił wyjątek przy zamykaniu: {e}")


class DataLogger(Logger):
    def __init__(
        self, filename, clear_file=True, period=LoggerPolicyPeriod.NONE, files_count=1
    ):
        super().__init__(
            filename,
            type=DataType.CSV,
            clear_file=clear_file,
            period=period,
            files_count=files_count,
            create_symlinks=False,
        )
        self.header = []
        self.data = []
        self.row = []

    def store(self, value):
        if isinstance(value, list):
            self.row.extend(value)
        else:
            self.row.append(value)

    def end_row(self):
        if len(self.row) == 0:
            return  # nie zapisuj pustych wierszy
        self.data.append(self.row)
        self.row = []

    def get_count_rows(self):
        return len(self.data)

    def dump_rows(self, rows: int) -> int:
        if rows <= 0:
            return 0

        rows = self.get_count_rows() if rows > self.get_count_rows() else rows

        rows_to_dump = self.data[
            :rows
        ]  # Pobieramy odpowiednią liczbę wierszy do zapisu
        self.data = self.data[rows:]  # Usuwamy zapisane wiersze

        for row in rows_to_dump:
            self.pipe_out.send(row)
            # self.f.write(self._row_to_string(row))
        # self.f.flush()
        return rows

    def _row_to_string(self, row):
        return ",".join([str(x) for x in row]) + "\n"

    def _dump_all_rows(self):
        for row in self.data:
            # self.f.write(self._row_to_string(row))
            self.pipe_out.send(row)

    def __del__(self):
        self._dump_all_rows()
        super().__del__()


class MessageLogger(Logger):
    def __init__(
        self,
        filename,
        clear_file=True,
        period=LoggerPolicyPeriod.NONE,
        files_count=4,
        debug=True,
        colors: bool = False,
    ):
        super().__init__(
            filename,
            type=DataType.LOG,
            clear_file=clear_file,
            period=period,
            files_count=files_count,
            create_symlinks=True,
            colors=colors,
        )
        self.__debug = debug

    def error(self, message):
        self.pipe_out.send([LogLevelType.error, message])

    def warning(self, message):
        self.pipe_out.send([LogLevelType.warning, message])

    def info(self, message):
        self.pipe_out.send([LogLevelType.info, message])

    def debug(self, message):
        if self.__debug:
            self.pipe_out.send([LogLevelType.debug, message])

    def set_debug(self, debug: bool):
        self.__debug = debug


class LogLevelType(Enum):
    debug = 0
    info = 1
    warning = 2
    error = 3


def generate_timestamp():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S.%f")


def format_message(message: str, level: LogLevelType = LogLevelType.info, colors: bool = True):
    match level:
        case LogLevelType.debug:
            return f"{generate_timestamp()} [{colorify(level.name, C.blue) if colors else level.name}] {message}"
        case LogLevelType.info:
            return f"{generate_timestamp()} [{colorify(level.name, C.blue) if colors else level.name}] {message}"
        case LogLevelType.warning:
            return f"{generate_timestamp()} [{colorify(level.name, C.orange) if colors else level.name}] {message}"
        case LogLevelType.error:
            return f"{generate_timestamp()} [{colorify(level.name, C.red) if colors else level.name}] {message}"
        case _:
            return f"{generate_timestamp()} [{colorify('NONE', C.red) if colors else 'NONE'}] {message}"


def debug(message: str, message_logger: MessageLogger = None, colors: bool = True):
    if message_logger is not None:
        message_logger.debug(message)
    else:
        print(format_message(message, LogLevelType.debug, colors))


def info(message: str, message_logger: MessageLogger = None, colors: bool = True):
    if message_logger is not None:
        message_logger.info(str(message))
    else:
        print(format_message(message, LogLevelType.info, colors))


def warning(message: str, message_logger: MessageLogger = None, colors: bool = True):
    if message_logger is not None:
        message_logger.warning(message)
    else:
        print(format_message(message, LogLevelType.warning, colors))


def error(message: str, message_logger: MessageLogger = None, colors: bool = True):
    if message_logger is not None:
        message_logger.error(message)
    else:
        print(format_message(message, LogLevelType.error, colors))
