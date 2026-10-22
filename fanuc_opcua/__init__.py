"""Read and write FANUC robot data over the controller's built-in OPC UA server."""
from .addresses import Address, parse_address
from .client import FanucClient
from .errors import (
    AddressError, CommunicationError, FanucConnectionError, FanucError, NotConnectedError, ReadOnlyError,
)
from .nodes import DEFAULT_PORT, ROBOGUIDE_HOST
from .sync import FanucClientSync
from .types import (
    Config, ExecutionState, OperationState, Position, ProgramStatus, RobotInfo, RobotStatus,
)

__version__ = "0.3.0"

__all__ = [
    "FanucClient", "FanucClientSync",
    "Position", "Config", "RobotInfo", "RobotStatus", "ProgramStatus", "OperationState", "ExecutionState",
    "Address", "parse_address",
    "FanucError", "FanucConnectionError", "AddressError", "ReadOnlyError", "CommunicationError",
    "NotConnectedError",
    "ROBOGUIDE_HOST", "DEFAULT_PORT",
]
