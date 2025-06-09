"""
Unit tests for avena_commons.event_listener.types.supervisor module.

This module contains comprehensive tests for supervisor-related models:
- Waypoint: Represents robot waypoints with position and configuration
- Path: Collection of waypoints defining robot paths
- SupervisorMoveAction: Robot movement actions
- SupervisorGripperAction: Robot gripper actions
- SupervisorPumpAction: Robot pump actions

Test Coverage:
- Model validation and field constraints
- Serialization and deserialization
- Edge cases and boundary conditions
- Type safety and error handling
- Integration between related models
"""

import pytest
from pydantic import ValidationError

from avena_commons.event_listener.types.supervisor import Path, SupervisorGripperAction, SupervisorMoveAction, SupervisorPumpAction, Waypoint


class TestWaypoint:
    """Test suite for Waypoint model."""

    def test_init_minimal_required(self):
        """Test Waypoint initialization with minimal required fields."""
        waypoint = Waypoint(waypoint=[1.0, 2.0, 3.0])

        assert waypoint.waypoint == [1.0, 2.0, 3.0]
        assert waypoint.waypoint_name is None
        assert waypoint.joints is None
        assert waypoint.speed is None
        assert waypoint.blend_radius is None
        assert waypoint.watchdog_override is None

    def test_init_all_fields(self):
        """Test Waypoint initialization with all fields."""
        waypoint = Waypoint(
            waypoint_name="test_point",
            waypoint=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            joints=[10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            speed=50.5,
            blend_radius=0.1,
            watchdog_override=True,
        )

        assert waypoint.waypoint_name == "test_point"
        assert waypoint.waypoint == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        assert waypoint.joints == [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
        assert waypoint.speed == 50.5
        assert waypoint.blend_radius == 0.1
        assert waypoint.watchdog_override is True

    @pytest.mark.parametrize(
        "waypoint_coords",
        [
            [0.0, 0.0, 0.0],
            [1.0, 2.0, 3.0],
            [-1.0, -2.0, -3.0],
            [100.5, 200.7, 300.9],
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],  # 6DOF coordinates
            [0.0],  # Single coordinate
        ],
    )
    def test_waypoint_coordinates(self, waypoint_coords):
        """Test various waypoint coordinate configurations."""
        waypoint = Waypoint(waypoint=waypoint_coords)
        assert waypoint.waypoint == waypoint_coords

    @pytest.mark.parametrize(
        "joints_config",
        [[0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [10.0, 20.0, 30.0, 40.0, 50.0, 60.0], [-10.0, -20.0, -30.0, -40.0, -50.0, -60.0], [180.0, 90.0, 45.0, 30.0, 15.0, 10.0]],
    )
    def test_joints_configuration(self, joints_config):
        """Test various joint configurations."""
        waypoint = Waypoint(waypoint=[1.0, 2.0, 3.0], joints=joints_config)
        assert waypoint.joints == joints_config

    def test_missing_required_waypoint(self):
        """Test Waypoint without required waypoint field."""
        with pytest.raises(ValidationError) as exc_info:
            Waypoint()

        assert "Field required" in str(exc_info.value)

    def test_invalid_waypoint_type(self):
        """Test Waypoint with invalid waypoint type."""
        with pytest.raises(ValidationError):
            Waypoint(waypoint="invalid")

    def test_to_dict_method(self):
        """Test Waypoint to_dict method."""
        waypoint = Waypoint(waypoint_name="test", waypoint=[1.0, 2.0, 3.0], speed=25.0)

        result = waypoint.to_dict()
        expected = {"waypoint_name": "test", "waypoint": [1.0, 2.0, 3.0], "joints": None, "speed": 25.0, "blend_radius": None, "watchdog_override": None}

        assert result == expected

    def test_from_dict_method(self):
        """Test Waypoint from_dict method."""
        data = {"waypoint_name": "from_dict", "waypoint": [5.0, 6.0, 7.0], "speed": 75.0}

        waypoint = Waypoint.from_dict(data)

        assert waypoint.waypoint_name == "from_dict"
        assert waypoint.waypoint == [5.0, 6.0, 7.0]
        assert waypoint.speed == 75.0


class TestPath:
    """Test suite for Path model."""

    @pytest.fixture
    def sample_waypoints(self):
        """Fixture providing sample waypoints."""
        return [Waypoint(waypoint=[1.0, 2.0, 3.0]), Waypoint(waypoint=[4.0, 5.0, 6.0], speed=50.0), Waypoint(waypoint=[7.0, 8.0, 9.0], waypoint_name="end_point")]

    def test_init_minimal_required(self, sample_waypoints):
        """Test Path initialization with minimal required fields."""
        path = Path(waypoints=sample_waypoints)

        assert len(path.waypoints) == 3
        assert path.max_speed == 100  # default value
        assert path.start_position is None
        assert path.testing_move is False
        assert path.interruption_move is False
        assert path.interruption_duration is None

    def test_init_all_fields(self, sample_waypoints):
        """Test Path initialization with all fields."""
        start_waypoint = Waypoint(waypoint=[0.0, 0.0, 0.0])

        path = Path(waypoints=sample_waypoints, max_speed=75, start_position=start_waypoint, testing_move=True, interruption_move=True, interruption_duration=5.5)

        assert len(path.waypoints) == 3
        assert path.max_speed == 75
        assert path.start_position == start_waypoint
        assert path.testing_move is True
        assert path.interruption_move is True
        assert path.interruption_duration == 5.5

    def test_empty_waypoints_list(self):
        """Test Path with empty waypoints list."""
        path = Path(waypoints=[])
        assert path.waypoints == []

    def test_single_waypoint(self):
        """Test Path with single waypoint."""
        waypoint = Waypoint(waypoint=[1.0, 2.0, 3.0])
        path = Path(waypoints=[waypoint])

        assert len(path.waypoints) == 1
        assert path.waypoints[0] == waypoint

    @pytest.mark.parametrize("max_speed", [1, 50, 100, 200, 500])
    def test_max_speed_values(self, max_speed, sample_waypoints):
        """Test Path with various max_speed values."""
        path = Path(waypoints=sample_waypoints, max_speed=max_speed)
        assert path.max_speed == max_speed

    def test_interruption_duration_values(self, sample_waypoints):
        """Test Path with various interruption duration values."""
        path = Path(waypoints=sample_waypoints, interruption_move=True, interruption_duration=2.5)
        assert path.interruption_duration == 2.5

    def test_to_dict_method(self, sample_waypoints):
        """Test Path to_dict method."""
        path = Path(waypoints=sample_waypoints, max_speed=80)
        result = path.to_dict()

        assert "waypoints" in result
        assert "max_speed" in result
        assert result["max_speed"] == 80
        assert len(result["waypoints"]) == 3

    def test_from_dict_method(self):
        """Test Path from_dict method."""
        data = {"waypoints": [{"waypoint": [1.0, 2.0, 3.0]}, {"waypoint": [4.0, 5.0, 6.0]}], "max_speed": 90}

        path = Path.from_dict(data)

        assert len(path.waypoints) == 2
        assert path.max_speed == 90
        assert path.waypoints[0].waypoint == [1.0, 2.0, 3.0]


class TestSupervisorMoveAction:
    """Test suite for SupervisorMoveAction model."""

    def test_init_default_values(self):
        """Test SupervisorMoveAction initialization with defaults."""
        action = SupervisorMoveAction()

        assert action.path is None
        assert action.max_speed == 100

    def test_init_with_path(self):
        """Test SupervisorMoveAction with path."""
        waypoints = [Waypoint(waypoint=[1.0, 2.0, 3.0])]
        path = Path(waypoints=waypoints)

        action = SupervisorMoveAction(path=path, max_speed=50)

        assert action.path == path
        assert action.max_speed == 50

    @pytest.mark.parametrize("max_speed", [1, 25, 50, 75, 100, 200])
    def test_max_speed_values(self, max_speed):
        """Test SupervisorMoveAction with various max_speed values."""
        action = SupervisorMoveAction(max_speed=max_speed)
        assert action.max_speed == max_speed

    def test_to_dict_method(self):
        """Test SupervisorMoveAction to_dict method."""
        action = SupervisorMoveAction(max_speed=75)
        result = action.to_dict()

        expected = {"path": None, "max_speed": 75}

        assert result == expected

    def test_from_dict_method(self):
        """Test SupervisorMoveAction from_dict method."""
        data = {"max_speed": 85}

        action = SupervisorMoveAction.from_dict(data)

        assert action.max_speed == 85
        assert action.path is None


class TestSupervisorGripperAction:
    """Test suite for SupervisorGripperAction model."""

    def test_init_default_values(self):
        """Test SupervisorGripperAction initialization with defaults."""
        action = SupervisorGripperAction()

        assert action.qr is None
        assert action.qr_rotation is False
        assert action.waypoint is None
        assert action.try_number is None

    def test_init_all_fields(self):
        """Test SupervisorGripperAction with all fields."""
        waypoint = Waypoint(waypoint=[1.0, 2.0, 3.0, 5.0, 6.0])

        action = SupervisorGripperAction(qr=1, qr_rotation=True, waypoint=waypoint, try_number=3)

        assert action.qr == 1
        assert action.qr_rotation is True
        assert action.waypoint == waypoint
        assert action.try_number == 3

    @pytest.mark.parametrize("qr_value", [0, 1, 2, 5, 10, 100])
    def test_qr_values(self, qr_value):
        """Test SupervisorGripperAction with various QR values."""
        action = SupervisorGripperAction(qr=qr_value)
        assert action.qr == qr_value

    @pytest.mark.parametrize("qr_rotation", [True, False])
    def test_qr_rotation_values(self, qr_rotation):
        """Test SupervisorGripperAction with QR rotation values."""
        action = SupervisorGripperAction(qr_rotation=qr_rotation)
        assert action.qr_rotation == qr_rotation

    @pytest.mark.parametrize("try_number", [1, 2, 3, 5, 10])
    def test_try_number_values(self, try_number):
        """Test SupervisorGripperAction with various try numbers."""
        action = SupervisorGripperAction(try_number=try_number)
        assert action.try_number == try_number

    def test_with_waypoint(self):
        """Test SupervisorGripperAction with waypoint."""
        waypoint = Waypoint(waypoint=[1.0, 2.0, 3.0, 5.0, 6.0])
        action = SupervisorGripperAction(waypoint=waypoint)

        assert action.waypoint == waypoint
        assert action.waypoint.waypoint == [1.0, 2.0, 3.0, 5.0, 6.0]

    def test_to_dict_method(self):
        """Test SupervisorGripperAction to_dict method."""
        action = SupervisorGripperAction(qr=1, qr_rotation=True, try_number=2)
        result = action.to_dict()

        expected = {"qr": 1, "qr_rotation": True, "waypoint": None, "try_number": 2}

        assert result == expected

    def test_from_dict_method(self):
        """Test SupervisorGripperAction from_dict method."""
        data = {"qr": 2, "qr_rotation": False, "try_number": 1}

        action = SupervisorGripperAction.from_dict(data)

        assert action.qr == 2
        assert action.qr_rotation is False
        assert action.try_number == 1


class TestSupervisorPumpAction:
    """Test suite for SupervisorPumpAction model."""

    def test_init_default_value(self):
        """Test SupervisorPumpAction initialization with default."""
        action = SupervisorPumpAction()
        assert action.pressure_threshold == -10

    def test_init_custom_value(self):
        """Test SupervisorPumpAction with custom pressure threshold."""
        action = SupervisorPumpAction(pressure_threshold=100)
        assert action.pressure_threshold == 100

    @pytest.mark.parametrize("pressure", [-100, -50, -10, 0, 50, 100, 200])
    def test_pressure_threshold_values(self, pressure):
        """Test SupervisorPumpAction with various pressure values."""
        action = SupervisorPumpAction(pressure_threshold=pressure)
        assert action.pressure_threshold == pressure

    def test_negative_pressure_values(self):
        """Test SupervisorPumpAction with negative pressure values."""
        action = SupervisorPumpAction(pressure_threshold=-50)
        assert action.pressure_threshold == -50

    def test_to_dict_method(self):
        """Test SupervisorPumpAction to_dict method."""
        action = SupervisorPumpAction(pressure_threshold=75)
        result = action.to_dict()

        expected = {"pressure_threshold": 75}
        assert result == expected

    def test_from_dict_method(self):
        """Test SupervisorPumpAction from_dict method."""
        data = {"pressure_threshold": 150}

        action = SupervisorPumpAction.from_dict(data)
        assert action.pressure_threshold == 150


class TestSupervisorModelsValidation:
    """Test suite for validation across supervisor models."""

    def test_waypoint_invalid_waypoint_type(self):
        """Test Waypoint with invalid waypoint coordinate types."""
        with pytest.raises(ValidationError):
            Waypoint(waypoint=["invalid", "coordinates"])

    def test_path_invalid_waypoints_type(self):
        """Test Path with invalid waypoints type."""
        with pytest.raises(ValidationError):
            Path(waypoints="invalid")

    def test_path_invalid_max_speed_type(self):
        """Test Path with invalid max_speed type."""
        waypoints = [Waypoint(waypoint=[1.0, 2.0, 3.0])]
        with pytest.raises(ValidationError):
            Path(waypoints=waypoints, max_speed="invalid")

    def test_gripper_action_invalid_qr_type(self):
        """Test SupervisorGripperAction with invalid QR type."""
        with pytest.raises(ValidationError):
            SupervisorGripperAction(qr="invalid")

    def test_pump_action_invalid_pressure_type(self):
        """Test SupervisorPumpAction with invalid pressure type."""
        with pytest.raises(ValidationError):
            SupervisorPumpAction(pressure_threshold="invalid")


class TestSupervisorModelsIntegration:
    """Integration tests for supervisor models working together."""

    @pytest.fixture
    def complex_path(self):
        """Fixture providing a complex path with multiple waypoints."""
        waypoints = [
            Waypoint(waypoint_name="start", waypoint=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0], joints=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0], speed=25.0),
            Waypoint(waypoint_name="middle", waypoint=[100.0, 50.0, 25.0, 45.0, 90.0, 180.0], joints=[10.0, 20.0, 30.0, 40.0, 50.0, 60.0], speed=50.0, blend_radius=0.5),
            Waypoint(waypoint_name="end", waypoint=[200.0, 100.0, 50.0, 90.0, 180.0, 360.0], speed=75.0, watchdog_override=True),
        ]

        start_pos = Waypoint(waypoint=[-10.0, -10.0, -10.0])

        return Path(waypoints=waypoints, max_speed=100, start_position=start_pos, testing_move=False, interruption_move=True, interruption_duration=3.0)

    def test_move_action_with_complex_path(self, complex_path):
        """Test SupervisorMoveAction with complex path."""
        action = SupervisorMoveAction(path=complex_path, max_speed=80)

        assert action.path == complex_path
        assert action.max_speed == 80
        assert len(action.path.waypoints) == 3
        assert action.path.waypoints[0].waypoint_name == "start"

    def test_gripper_action_with_waypoint(self):
        """Test SupervisorGripperAction with detailed waypoint."""
        waypoint = Waypoint(waypoint_name="grip_position", waypoint=[150.0, 75.0, 30.0, 45.0, 90.0], speed=25.0, blend_radius=0.1)

        action = SupervisorGripperAction(qr=5, qr_rotation=True, waypoint=waypoint, try_number=2)

        assert action.waypoint.waypoint_name == "grip_position"
        assert action.waypoint.speed == 25.0
        assert action.qr == 5

    def test_complete_serialization_workflow(self, complex_path):
        """Test complete serialization workflow with all models."""
        # Create instances of all models
        move_action = SupervisorMoveAction(path=complex_path, max_speed=90)

        grip_waypoint = Waypoint(waypoint=[1.0, 2.0, 3.0, 4.0, 5.0])
        gripper_action = SupervisorGripperAction(qr=3, qr_rotation=True, waypoint=grip_waypoint, try_number=1)

        pump_action = SupervisorPumpAction(pressure_threshold=125)

        # Serialize all to dict
        move_dict = move_action.to_dict()
        gripper_dict = gripper_action.to_dict()
        pump_dict = pump_action.to_dict()

        # Deserialize back
        restored_move = SupervisorMoveAction.from_dict(move_dict)
        restored_gripper = SupervisorGripperAction.from_dict(gripper_dict)
        restored_pump = SupervisorPumpAction.from_dict(pump_dict)

        # Verify they match
        assert restored_move.max_speed == move_action.max_speed
        assert len(restored_move.path.waypoints) == len(complex_path.waypoints)

        assert restored_gripper.qr == gripper_action.qr
        assert restored_gripper.waypoint.waypoint == grip_waypoint.waypoint

        assert restored_pump.pressure_threshold == pump_action.pressure_threshold

    def test_json_compatibility_all_models(self):
        """Test JSON compatibility for all supervisor models."""
        import json

        # Create sample instances
        waypoint = Waypoint(waypoint=[1.0, 2.0, 3.0], speed=50.0)
        path = Path(waypoints=[waypoint], max_speed=100)
        move_action = SupervisorMoveAction(path=path, max_speed=75)
        gripper_action = SupervisorGripperAction(qr=1, qr_rotation=True)
        pump_action = SupervisorPumpAction(pressure_threshold=100)

        # Test JSON round-trip for each model
        models = [waypoint, path, move_action, gripper_action, pump_action]
        model_classes = [Waypoint, Path, SupervisorMoveAction, SupervisorGripperAction, SupervisorPumpAction]

        for model, model_class in zip(models, model_classes):
            # Serialize to JSON
            json_str = json.dumps(model.to_dict())

            # Parse back and create model
            parsed_dict = json.loads(json_str)
            restored_model = model_class.from_dict(parsed_dict)

            # Verify basic equality (some fields might not be directly comparable)
            assert type(restored_model) == type(model)

    def test_model_nesting_limits(self):
        """Test behavior with deeply nested model structures."""
        # Create a path with many waypoints
        waypoints = []
        for i in range(100):
            waypoints.append(Waypoint(waypoint_name=f"point_{i}", waypoint=[float(i), float(i * 2), float(i * 3)]))

        path = Path(waypoints=waypoints, max_speed=100)
        move_action = SupervisorMoveAction(path=path)

        # Should handle large numbers of waypoints
        assert len(move_action.path.waypoints) == 100
        assert move_action.path.waypoints[50].waypoint_name == "point_50"

        # Test serialization with large structure
        data_dict = move_action.to_dict()
        assert len(data_dict["path"]["waypoints"]) == 100
