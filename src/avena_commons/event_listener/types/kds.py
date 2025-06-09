from typing import Optional

from pydantic import BaseModel


class KdsAction(BaseModel):
    order_number: Optional[int] = None  # np 100
    pickup_number: Optional[int] = None  # np 100
    message: Optional[str] = None  # np "kds_order_number"

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "KdsAction":
        return cls(**data)
