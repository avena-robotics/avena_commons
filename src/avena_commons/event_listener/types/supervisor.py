from typing import List, Optional

from pydantic import BaseModel


class Waypoint(BaseModel):
    waypoint_name: Optional[str] = None
    waypoint: List[float]  # poza kartezjanska
    joints: Optional[List[float]] = None  # konfiguracja
    speed: Optional[float] = None
    blend_radius: Optional[float] = None
    watchdog_override: Optional[bool] = None

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "Waypoint":
        return cls(**data)


class Path(BaseModel):
    waypoints: List[Waypoint]
    max_speed: int = 100
    start_position: Optional[Waypoint] = None
    testing_move: Optional[bool] = False
    interruption_move: Optional[bool] = False
    interruption_duration: Optional[float] = None
    collision_override: Optional[bool] = False

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "Path":
        return cls(**data)


class SupervisorMoveAction(BaseModel):
    path: Optional[Path] = None
    max_speed: int = 100

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "SupervisorMoveAction":
        return cls(**data)


class SupervisorGripperAction(BaseModel):
    qr: Optional[int] = None  # np 1
    qr_rotation: Optional[bool] = False  # np True
    waypoint: Optional[Waypoint] = None  # np {"waypoint": [1, 2, 3, 5, 6]}
    try_number: Optional[int] = None  # np 1

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "SupervisorGripperAction":
        return cls(**data)


class SupervisorPumpAction(BaseModel):
    pressure_threshold: Optional[int] = -10  # np 100

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "SupervisorPumpAction":
        return cls(**data)
