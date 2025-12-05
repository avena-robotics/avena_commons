from typing import List, Optional

from pydantic import BaseModel, Field

from avena_commons.event_listener.types import Path, Waypoint

from .enum import RobotControllerState


class CollisionLevels(BaseModel):
    """Represents collision levels for robot joints j1-j6"""

    j1: int = Field(default=10, ge=1, le=100)
    j2: int = Field(default=8, ge=1, le=100)
    j3: int = Field(default=10, ge=1, le=100)
    j4: int = Field(default=5, ge=1, le=100)
    j5: int = Field(default=3, ge=1, le=100)
    j6: int = Field(default=100, ge=1, le=100)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "CollisionLevels":
        """Create from dictionary for JSON deserialization"""
        return cls.model_validate(data)

    def __str__(self) -> str:
        return f"CollisionLevels(j1={self.j1}, j2={self.j2}, j3={self.j3}, j4={self.j4}, j5={self.j5}, j6={self.j6})"


class PathExecutionState(BaseModel):
    """Represents the state of the path execution in the supervisor system."""

    start_position: Optional[List[float]] = Field(default=None)
    remaining_waypoints: Optional[List[Waypoint]] = Field(default=[])
    current_waypoint: Optional[Waypoint] = Field(default=None)
    current_path: Optional[Path] = Field(default=None)
    interrupt: bool = False
    testing_move_check: bool = False
    watchdog_override: bool = False

    def __str__(self) -> str:
        start_pos_str = (
            f"[{', '.join(f'{p:.2f}' for p in self.start_position)}]"
            if self.start_position
            else "[]"
        )
        current_wp = self.current_waypoint.name if self.current_waypoint else "None"
        remaining_count = len(self.remaining_waypoints)
        path_name = self.current_path.name if self.current_path else "None"
        return f"PathExecution(start={start_pos_str}, current_wp={current_wp}, remaining={remaining_count}, path={path_name})"

    def model_dump(self, **kwargs) -> dict:
        """Custom serialization for complex objects"""
        data = super().model_dump(**kwargs)
        if self.current_waypoint:
            data["current_waypoint"] = self.current_waypoint.to_dict()
        if self.current_path:
            data["current_path"] = self.current_path.to_dict()
        if self.remaining_waypoints:
            data["remaining_waypoints"] = [
                wp.to_dict() for wp in self.remaining_waypoints
            ]
        return data

    @classmethod
    def model_validate(cls, data: dict) -> "PathExecutionState":
        """Custom deserialization for complex objects"""
        # Handle current_waypoint
        if "current_waypoint" in data and data["current_waypoint"]:
            data["current_waypoint"] = Waypoint.from_dict(data["current_waypoint"])

        # Handle current_path
        if "current_path" in data and data["current_path"]:
            data["current_path"] = Path.from_dict(data["current_path"])

        # Handle remaining_waypoints
        if "remaining_waypoints" in data and data["remaining_waypoints"]:
            data["remaining_waypoints"] = [
                Waypoint.from_dict(wp) for wp in data["remaining_waypoints"]
            ]

        return cls(**data)


class RobotModel(BaseModel):
    """Represents the state of the robot in the supervisor system."""

    enable_state: int = 0  # robot.robot_state_pkg.robot_mode, 0 = disabled, 1 = enabled
    mode_state: int = 0  # robot.robot_state_pkg.robot_state, 0 = automatic, 1 = manual
    current_position: List[float] = Field(default=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    joint_current_torque: List[float] = Field(default=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    collision_levels: CollisionLevels = Field(default=CollisionLevels())
    gripper_pump_holding: bool = False  # czy pompa trzyma ciśnienie
    gripper_pressure: float = 0.0  # aktualne ciśnienie w chwili odczytu

    def __str__(self) -> str:
        pos_str = (
            f"[{', '.join(f'{p:.2f}' for p in self.current_position)}]"
            if self.current_position
            else "[]"
        )
        torque_str = (
            f"[{', '.join(f'{t:.2f}' for t in self.joint_current_torque)}]"
            if self.joint_current_torque
            else "[]"
        )
        collision_str = (
            f" collision_levels={self.collision_levels}"
            if self.collision_levels
            else ""
        )
        return f"RobotState (enable={self.enable_state}, mode={self.mode_state}, pos={pos_str}, torque={torque_str}{collision_str})"

    def model_dump(self, **kwargs) -> dict:
        """Custom serialization for collision_levels"""
        data = super().model_dump(**kwargs)

        # Handle collision_levels object
        if self.collision_levels:
            data["collision_levels"] = self.collision_levels.model_dump()

        return data

    @classmethod
    def model_validate(cls, data: dict) -> "RobotModel":
        """Custom deserialization for collision_levels"""
        # Handle collision_levels
        if "collision_levels" in data and data["collision_levels"]:
            data["collision_levels"] = CollisionLevels.model_validate(
                data["collision_levels"]
            )

        return cls(**data)


class SupervisorModel(BaseModel):
    """Represents the state of the Supervisor and it's modules."""

    id: int
    current_error: str = ""

    # gripper_state: GripperModel = Field(default=GripperModel())
    robot_state: RobotModel = Field(default=RobotModel())
    path_execution_state: PathExecutionState = Field(default=PathExecutionState())

    pump_watchdog_failure: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        # Initialize _state as a private attribute
        self._state = RobotControllerState.STOPPED.name

    @property
    def state(self) -> RobotControllerState:
        return RobotControllerState[self._state]

    @state.setter
    def state(self, value: RobotControllerState):
        self._state = value.name

    # Add missing properties referenced in __str__
    @property
    def interrupt(self) -> bool:
        return (
            self.path_execution_state.interrupt if self.path_execution_state else False
        )

    @property
    def collision_detected(self) -> bool:
        return False

    @property
    def testing_move_check(self) -> bool:
        return (
            self.path_execution_state.testing_move_check
            if self.path_execution_state
            else False
        )

    @property
    def watchdog_override(self) -> bool:
        return (
            self.path_execution_state.watchdog_override
            if self.path_execution_state
            else False
        )

    def __str__(self) -> str:
        flags = []
        if self.interrupt:
            flags.append("INTERRUPT")
        if self.collision_detected:
            flags.append("COLLISION")
        if not self.testing_move_check:
            flags.append("TEST_MOVE_FAILED")
        if self.watchdog_override:
            flags.append("WATCHDOG_OVERRIDE")

        flags_str = f" [{', '.join(flags)}]" if flags else ""

        return f"Supervisor(id={self.id}, state={self.state}{flags_str})"

    def __repr__(self) -> str:
        return f"Supervisor(id={self.id}, state={self.state}, robot={self.robot_state}, path={self.path_execution_state}, error={self.current_error})"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "SupervisorModel":
        """Create from dictionary for JSON deserialization"""
        return cls.model_validate(data)

    def model_dump(self, **kwargs) -> dict:
        """Custom serialization"""
        data = super().model_dump(**kwargs)

        # Add state to serialized data
        data["state"] = self._state

        # Handle nested objects
        # data["gripper_state"] = self.gripper_state.model_dump()
        data["robot_state"] = self.robot_state.model_dump()
        data["path_execution_state"] = self.path_execution_state.model_dump()

        return data

    @classmethod
    def model_validate(cls, data: dict) -> "SupervisorModel":
        """Custom deserialization"""
        id = data.pop("id", 1)
        # Extract state from data before passing to constructor
        state_value = data.pop("state", RobotControllerState.STOPPED.name)
        
        if "robot_state" in data:
            data["robot_state"] = RobotModel.model_validate(data["robot_state"])

        if "path_execution_state" in data:
            data["path_execution_state"] = PathExecutionState.model_validate(
                data["path_execution_state"]
            )

        return cls(**data, id=id)
