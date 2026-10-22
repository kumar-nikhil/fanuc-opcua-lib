from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Config:
    """Arm configuration of a cartesian position (manual 55.3.3)."""
    flip: bool = False
    left: bool = False
    up: bool = True
    front: bool = True
    turn4: int = 0
    turn5: int = 0
    turn6: int = 0

    def __str__(self) -> str:
        return (f"{'F' if self.flip else 'N'} {'L' if self.left else 'R'} "
                f"{'U' if self.up else 'D'} {'T' if self.front else 'B'}, "
                f"{self.turn4}, {self.turn5}, {self.turn6}")


@dataclass
class Position:
    """
    A position register, current position or POSITION system variable.

    Reading returns both representations when the controller can convert them.
    Writing uses `representation`: "cartesian" writes x..r, extended axes and config,
    "joint" writes the joint values. Use Position.cartesian() / Position.joint() to build one.
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 0.0
    p: float = 0.0
    r: float = 0.0
    ext: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    config: Config = field(default_factory=Config)
    joints: Optional[Tuple[float, ...]] = None
    uf: int = -1
    ut: int = -1
    valid_cartesian: bool = True
    valid_joint: bool = True
    representation: str = "cartesian"

    @classmethod
    def cartesian(cls, x: float, y: float, z: float, w: float, p: float, r: float,
                  config: Optional[Config] = None, ext: Tuple[float, ...] = ()) -> "Position":
        ext3 = tuple(float(e) for e in ext) + (0.0,) * (3 - len(ext))
        return cls(x, y, z, w, p, r, ext=ext3[:3], config=config or Config(), representation="cartesian")

    @classmethod
    def joint(cls, *joints: float) -> "Position":
        if not 1 <= len(joints) <= 9:
            raise ValueError("A joint position needs 1 to 9 joint values")
        return cls(joints=tuple(float(j) for j in joints), representation="joint")

    @property
    def xyzwpr(self) -> Tuple[float, float, float, float, float, float]:
        return (self.x, self.y, self.z, self.w, self.p, self.r)

    def __str__(self) -> str:
        parts = []
        if self.valid_cartesian:
            parts.append("X {:.3f}  Y {:.3f}  Z {:.3f}  W {:.3f}  P {:.3f}  R {:.3f}  [{}]".format(
                *self.xyzwpr, self.config))
        if self.joints is not None and self.valid_joint:
            parts.append("  ".join(f"J{i} {j:.3f}" for i, j in enumerate(self.joints, 1)))
        if not parts:
            return "<uninitialized position>"
        return "\n".join(parts)


class OperationState(enum.IntFlag):
    """Bits of the RobotInformation/OperationState node (manual 55.5.1)."""
    E_STOP = 1
    ABORTED = 2
    RUNNING = 4
    PAUSED = 8
    HELD = 16
    FAULT = 32
    TP_ENABLED = 64
    BATTERY_ALARM = 128
    BUSY = 256


@dataclass
class RobotInfo:
    model: str
    serial_number: str
    version: str
    controller_model: Optional[str] = None
    software_revision: Optional[str] = None


@dataclass
class RobotStatus:
    mode: str                      # "Auto", "T1" or "T2"
    servo_on: bool
    speed_override: int            # percent
    state: OperationState
    alarms: List[str]
    joint_positions: List[float]   # group 1, up to 6 axes
    torque: List[float]            # Q-phase current per axis (A)
    uptime_minutes: int
    protective_stop: Optional[bool] = None

    @property
    def state_flags(self) -> List[str]:
        """Names of the set state bits, e.g. ['PAUSED', 'FAULT'] for state 40."""
        return [f.name for f in OperationState if f in self.state]

    @property
    def e_stop(self) -> bool:
        return OperationState.E_STOP in self.state

    @property
    def running(self) -> bool:
        return OperationState.RUNNING in self.state

    @property
    def paused(self) -> bool:
        return OperationState.PAUSED in self.state

    @property
    def held(self) -> bool:
        return OperationState.HELD in self.state

    @property
    def fault(self) -> bool:
        return OperationState.FAULT in self.state

    @property
    def tp_enabled(self) -> bool:
        return OperationState.TP_ENABLED in self.state

    @property
    def busy(self) -> bool:
        return OperationState.BUSY in self.state


class ExecutionState(enum.IntEnum):
    ABORTED = 0
    PAUSED = 1
    RUNNING = 2


@dataclass
class ProgramStatus:
    """Program execution status of one task (manual 55.3.7)."""
    program: str
    line: int
    state: ExecutionState
    parent_program: str
