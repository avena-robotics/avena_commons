from typing import Optional, Union

from pydantic import BaseModel


class IoSignal(BaseModel):  # Zwrotki z czujników
    device_type: str  # np "tor_pieca"
    device_id: int  # np 1
    signal_name: str  # np "in"
    signal_value: Union[bool, int]  # np True

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "IoSignal":
        return cls(**data)


class IoAction(BaseModel):
    device_type: str  # np "tor_pieca"
    device_id: Optional[int] = None  # np None
    subdevice_id: Optional[int] = None  # np None

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "IoAction":
        return cls(**data)
