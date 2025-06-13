"""
Module implementing an event system for event-driven architecture.

This module provides fundamental classes for handling events in the system:
- Result: represents the outcome of an operation or event
- Event: represents a system event

Events are used for communication between different system components,
enabling asynchronous processing and information transfer.
Each event has a specified source, destination, priority, and can contain
additional data and processing result information.

The event-driven architecture implemented here follows the publisher-subscriber pattern,
where components can emit events (publishers) and other components can listen and react
to these events (subscribers). This decoupling allows for better scalability and
maintainability of the system.

Example:
    >>> # Creating a new event
    >>> event = Event(
    ...     source="sensor",
    ...     source_port=5000,
    ...     destination="controller",
    ...     destination_port=5001,
    ...     event_type="measurement",
    ...     data={"temperature": 25.5}
    ... )
    >>>
    >>> # Adding a result to the event
    >>> event.result = Result(
    ...     result="success",
    ...     error_code=None,
    ...     error_message=None
    ... )
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ResultValue(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TEST_FAILED = "test_failed"
    ERROR = "error"


class Result(BaseModel):
    """
    Model representing the result of an operation or event in the system.

    This class uses Pydantic for data validation and type checking.
    All fields are optional, allowing flexible reporting of both
    successful operations and various types of failures.

    Attributes:
        result (Optional[str]): Operation status (e.g., "success", "failure")
        error_code (Optional[int]): Error code in case of failure (e.g., 1)
        error_message (Optional[str]): Detailed error description

    Examples:
        >>> # Success example
        >>> success_result = Result(result="success")
        >>>
        >>> # Error example
        >>> error_result = Result(
        ...     result="failure",
        ...     error_code=1,
        ...     error_message="Nieprawidłowe dane wejściowe"
        ... )
    """

    result: Optional[str] = None  # np "success", "failure"
    error_code: Optional[int] = None  # np 1
    error_message: Optional[str] = None  # np "error message"


class Event(BaseModel):
    """
    Model representing an event in the system.

    This class uses Pydantic for data validation and type checking.
    It serves as a message carrier between system components in the event-driven architecture.

    Attributes:
        source (str): Name of the event source
        source_port (int): Port number of the source
        destination (str): Name of the event destination
        destination_port (int): Port number of the destination
        event_type (str): Event type defining its nature
        timestamp (datetime): Event creation timestamp
        data (dict): Event-related data
        result (Optional[Result]): Optional event processing result
        is_processing (bool): Flag indicating if the event is currently being processed
        is_cumulative (bool): Flag indicating if the event is cumulative
        maximum_processing_time (Optional[int]): Maximum processing time in seconds

    The Event class is thread-safe and can be safely used in concurrent processing
    scenarios. The is_processing flag helps prevent duplicate processing of the same event.
    """

    source: str
    source_address: str
    source_port: int
    destination: str
    destination_address: str
    destination_port: int
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.now)
    data: dict
    payload: int = 1
    id: Optional[int] = None
    result: Optional[Result] = None
    to_be_processed: bool = False
    is_processing: bool = False
    is_cumulative: bool = False
    maximum_processing_time: Optional[float] = None  # w sekundach

    def __init__(
        self,
        source: str = "default",
        source_address: str = "127.0.0.1",
        source_port: int = 0,
        destination: str = "default",
        destination_address: str = "127.0.0.1",
        destination_port: int = 0,
        event_type: str = "default",
        data: dict = {},
        id: Optional[int] = None,
        to_be_processed: bool = False,
        is_processing: bool = False,
        is_cumulative: bool = False,
        payload: int = 1,
        result: Optional[Result] = None,
        maximum_processing_time: Optional[float] = 20,
        timestamp: Optional[datetime] = None,  # Dodajemy opcjonalny parametr timestamp
    ):
        """
        Initializes a new event.

        Args:
            source (str): Name of the event source
            source_port (int): Port number of the source
            destination (str): Name of the event destination
            destination_port (int): Port number of the destination
            event_type (str): Event type
            data (dict): Event-related data
            result (Optional[Result], optional): Event processing result. Defaults to None

        Note:
            The timestamp is automatically set to the current time
            when the event is created.
        """
        super().__init__(
            source=source,
            source_address=source_address,
            source_port=source_port,
            destination=destination,
            destination_address=destination_address,
            destination_port=destination_port,
            event_type=event_type,
            data=data,
            id=id,
            payload=payload,
            result=result,
            to_be_processed=to_be_processed,
            is_processing=is_processing,
            is_cumulative=is_cumulative,
            maximum_processing_time=maximum_processing_time,
            timestamp=timestamp
            if timestamp is not None
            else datetime.now(),  # Używamy istniejącego timestamp lub tworzymy nowy
        )

    def to_dict(self) -> dict:
        """
        Converts the event to a dictionary.

        Returns:
            dict: A dictionary containing all event data, where:
                - result is serialized to JSON format if it exists
        """
        return {
            "source": self.source,
            "source_address": self.source_address,
            "source_port": self.source_port,
            "destination": self.destination,
            "destination_address": self.destination_address,
            "destination_port": self.destination_port,
            "event_type": self.event_type,
            "data": self.data,
            "id": self.id,
            "payload": self.payload,
            "to_be_processed": self.to_be_processed,
            "is_processing": self.is_processing,
            "is_cumulative": self.is_cumulative,
            "maximum_processing_time": self.maximum_processing_time,
            "timestamp": str(self.timestamp),
            "result": self.result.model_dump() if self.result is not None else None,
        }

    def __str__(self) -> str:
        """
        Returns a string representation of the event.

        Returns:
            str: Formatted text containing basic event information:
                source, destination, event type, data and result
        """
        return f"Event(source={self.source}, source_address={self.source_address}, source_port={self.source_port}, destination={self.destination}, destination_address={self.destination_address}, destination_port={self.destination_port}, cumulative={self.is_cumulative}, payload={self.payload}, event_type={self.event_type}, data={self.data}, timestamp={self.timestamp}, MPT={self.maximum_processing_time:.2f}) result={self.result}"
