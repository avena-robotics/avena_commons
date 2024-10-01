import os
import traceback


class Config:
    def __init__(self, config_file, read_only=True):
        # self.config_file= config_file
        self._read_only = read_only
        self._config_file_base, self._config_file_extenstion = os.path.splitext(
            config_file
        )

    def __remove_content_up_to_first_blank_line(self):
        # Odczytaj zawartość pliku i znajdź indeks pierwszej pustej linii
        with open(self.config_file(), "r") as file:
            lines = file.readlines()
            first_blank_line_index = None
            for i, line in enumerate(lines):
                # Sprawdź, czy linia jest pusta lub zawiera tylko białe znaki
                if line.strip() == "":
                    first_blank_line_index = i
                    break

            # Jeśli nie znaleziono pustej linii, nie ma nic do usunięcia
            if first_blank_line_index is None:
                return

        # Zapisz zawartość pliku, pomijając linie od początku do pierwszej pustej linii
        with open(self.config_file(), "w") as file:
            file.writelines(lines[first_blank_line_index + 1 :])

    def config_file(self):
        return self._config_file_base + self._config_file_extenstion

    def read_from_file(self):
        # Reading the config file
        self.config.read(self.config_file())
        return self

    def save_to_file(self):
        if not self._read_only:
            with open(self.config_file(), "w") as file:
                self.config.write(file)
            self.__remove_content_up_to_first_blank_line()

    def _dump_all(self):
        if not self._read_only:
            try:
                self.save_to_file()
                print(f"Configuration saved for {self._config_file_base}")
            except Exception as e:
                print(f"Failed to save configuration for {self._config_file_base}: {e}")
                traceback.print_exception(e)

    def __str__(self) -> str:
        out = ""
        for section in self.config.sections():
            out += f"[{section}]\n"
            for key in self.config[section]:
                out += f"{key} = {self.config[section][key]}\n"
            out += "\n"
        return out

    def __del__(self):
        self._dump_all()


##########################################################################################
##########################################################################################
##########################################################################################
##########################################################################################
# sys.path.append(os.path.expanduser('~') + '/controller/')
# from lib.util.logger import LogLevelType

# CONTROLLER_PATH=f"/home/{os.environ.get('USER')}/controller"
# RESOURCES_PATH=f"{CONTROLLER_PATH}/resources"
# URDF_PATH = f"{CONTROLLER_PATH}/urdf_janusz/robot.urdf" # path to urdf file

# PREC_COUNTER = 200 # kroków trajektorii dodatkowej precyzji
# PRECISE_RAMP_MAX = 0.1 # współczynnik rampy precyzji
# PRECISE_RAMP_START = 0.0001 # współczynnik rampy precyzji

# LOG_LEVEL = LogLevelType.INFO
