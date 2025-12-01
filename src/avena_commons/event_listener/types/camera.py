from typing import Optional

from pydantic import BaseModel

from .supervisor import Waypoint


class CameraAction(BaseModel):
    qr: Optional[int] = None  # np 1
    qr_rotation: Optional[bool] = False  # np True
    waypoint: Optional[Waypoint] = None  # np {"waypoint": [1, 2, 3, 5, 6]}
    try_number: Optional[int] = None  # np 1
    supervisor_number: Optional[int] = None  # np 1

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "CameraAction":
        return cls(**data)
