from enum import Enum


class RobotControllerState(Enum):
    """
    Enumeration class representing the different states of the Supervisor.
    """

    STOPPED = 0
    INITIALIZING = 1
    IDLE = 2
    IN_MOVE = 3
    MOVEMENT_FINISHED = 4
    WAITING_FOR_GRIPPER_INFO = 7
    GRIPPER_FINISHED = 8
    WAITING = 9
    WATCHDOG_ERROR = 254
    ERROR = 255


class CommandEnum(Enum):
    """
    Klasa wyliczeniowa reprezentująca różne komendy, które mogą być wysyłane do Supervisora.

    Attributes:
        PUMP_ON (int): Komenda włączenia pompy.
        PUMP_OFF (int): Komenda wyłączenia pompy.
        TAKE_PHOTO (int): Komenda wykonania zdjęcia.
        CORRECTION (int): Komenda korekty pozycji.
        PRESSURE (int): Komenda sprawdzenia ciśnienia.
    """

    PUMP_ON = 1
    PUMP_OFF = 2
    CORRECTION = 3
    PRESSURE = 4


class MoveType(Enum):
    """
    Klasa wyliczeniowa reprezentująca różne typy ruchów, które mogą być wykonywane przez Supervisor.

    Attributes:
        MOVEJ (int): Ruch stawów (joint move).
        MOVEL (int): Ruch liniowy (linear move).
        MOVEL_WITH_BLEND (int): Ruch liniowy z mieszaniem (linear move with blending).
    """

    MOVEJ = 1
    MOVEL = 2
    MOVEL_WITH_BLEND = 3


class PostCollisionStrategy(Enum):
    """
    Klasa wyliczeniowa reprezentująca różne strategie, które mogą być użyte po kolizji.

    Attributes:
        REPORT_ERROR_AND_PAUSE (int): Zgłoś błąd i wstrzymaj działanie.
        KEEP_RUNNING (int): Kontynuuj działanie mimo kolizji.
        ERROR_STOP (int): Zatrzymaj działanie w przypadku błędu.
        HEAVY_MOMENT_MODE (int): Tryb pracy z dużym momentem.
        SHOCK_RESPONSE_MODE (int): Tryb reakcji na wstrząs.
        IMPACT_REBOUND_MODE (int): Tryb odbicia po uderzeniu.
    """

    REPORT_ERROR_AND_PAUSE = 0
    KEEP_RUNNING = 1
    ERROR_STOP = 2
    HEAVY_MOMENT_MODE = 3
    SHOCK_RESPONSE_MODE = 4
    IMPACT_REBOUND_MODE = 5