from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import Any, AsyncIterator, Dict, Iterable, List, Mapping, Optional, Union

from asyncua import Client, ua

from . import codec
from .addresses import (
    BOOL_IO, COIL_IO, HR_WRITABLE_IO, IO_AREAS, POSITION_MEMBERS,
    Address, check_count, parse_address,
)
from .errors import (
    AddressError, CommunicationError, FanucConnectionError, NotConnectedError, ReadOnlyError,
)
from .nodes import (
    DEFAULT_PORT, ENDPOINT_PATH, ROBOTICS_NS_DEFAULT, ROBOTICS_NS_URI,
    RobotInfoNodes, RoboticsNodes,
)
from .transport import AssignmentWindow, Transport
from .types import (
    ExecutionState, OperationState, Position, ProgramStatus, RobotInfo, RobotStatus,
)

logger = logging.getLogger(__name__)

AddressLike = Union[str, Address]

# Words and $MULTIPLY used to assign one system variable of each type (manual 55.3.8).
SYSVAR_TYPES = {
    "int": (2, 1),
    "real": (2, 0),
    "bool": (2, 1),
    "str": (codec.STRING_REGISTER_WORDS, 1),
    "pos": (codec.POSITION_WORDS, 0),
}


class FanucClient:
    """
    Asynchronous client for the OPC UA server of a FANUC robot controller.

    Example:
        async with FanucClient("127.0.0.2") as robot:   # ROBOGUIDE
            await robot.write("DO[1]", True)
            r5 = await robot.read("R[5]")
            pr = await robot.read("PR[1]")
    """

    def __init__(self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.endpoint = f"opc.tcp://{host}:{port}{ENDPOINT_PATH}"
        self._client: Optional[Client] = None
        self._transport: Optional[Transport] = None
        self._window: Optional[AssignmentWindow] = None
        self._robotics_ns: Optional[int] = None

    # ------------------------------------------------------------------ connection

    async def connect(self) -> None:
        """Connect to the controller's OPC UA server."""
        if self._client is not None:
            return
        logger.info("Connecting to %s", self.endpoint)
        client = Client(url=self.endpoint, timeout=self.timeout)
        try:
            await client.connect()
        except (OSError, asyncio.TimeoutError) as e:
            raise FanucConnectionError(
                f"Cannot reach {self.endpoint} ({type(e).__name__}{': ' + str(e) if str(e) else ''}). Is the OPC UA server enabled? "
                "ROBOGUIDE listens on 127.0.0.2, not 127.0.0.1."
            ) from e
        self._client = client
        self._transport = Transport(client)
        self._window = AssignmentWindow(self._transport)
        try:
            self._robotics_ns = await client.get_namespace_index(ROBOTICS_NS_URI)
        except ValueError:
            self._robotics_ns = None
        logger.info("Connected to %s", self.endpoint)

    async def disconnect(self) -> None:
        """Close the connection. Dynamic assignments are dropped by the controller."""
        if self._client is None:
            return
        client, self._client = self._client, None
        self._transport = self._window = None
        try:
            await client.disconnect()
        finally:
            logger.info("Disconnected from %s", self.endpoint)

    @property
    def connected(self) -> bool:
        return self._client is not None

    @property
    def transport(self) -> Transport:
        """Low-level access to the Modbus arrays and Command node."""
        self._require()
        return self._transport

    async def __aenter__(self) -> "FanucClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()

    def _require(self) -> None:
        if self._client is None:
            raise NotConnectedError("Not connected; call connect() or use 'async with'")

    # ------------------------------------------------------------------ read / write

    async def read(self, address: AddressLike, count: Optional[int] = None,
                   dtype: Optional[str] = None) -> Any:
        """
        Read one value, or a list of `count` consecutive values.

        Addresses: DI/DO/RI/RO/UI/UO/SI/SO/WI/WO/WSI/WSO/F[n] -> bool,
        GI/GO/AI/AO[n] -> int, R[n] -> float, SR[n] -> str,
        PR[n] / PR[Gg:n] / POS / POS[uf] -> Position, PR[n].x -> float,
        "$SYSTEM.$VAR" -> value of `dtype` ("int", "real", "bool", "str", "pos"; default "int").
        """
        self._require()
        addr = parse_address(address)
        n = 1 if count is None else count
        check_count(addr, n)
        if dtype is not None and addr.kind != "$":
            raise AddressError("dtype is only used for system variables")
        values = await self._read(addr, n, dtype or "int")
        return values if count is not None else values[0]

    async def read_many(self, addresses: Iterable[AddressLike]) -> Dict[str, Any]:
        """Read several addresses; returns {address: value}."""
        return {str(a): await self.read(a) for a in addresses}

    async def write(self, address: AddressLike, value: Any, dtype: Optional[str] = None) -> None:
        """
        Write a value. Pass a list to write consecutive items, e.g. write("DO[1]", [1, 0, 1]).

        Writable: DO/RO/F, GO/AO/WO/WSO, R (int or float), SR (str),
        PR (Position, {"x": .., "y": ..} or PR[n].x with a number) and system variables.
        """
        self._require()
        addr = parse_address(address)
        if dtype is not None and addr.kind != "$":
            raise AddressError("dtype is only used for system variables")
        await self._write(addr, value, dtype or "int")

    async def _read(self, addr: Address, n: int, dtype: str) -> List[Any]:
        t, kind = self._transport, addr.kind

        if kind in IO_AREAS:
            area = IO_AREAS[kind]
            raw = await t.read_array(area.node, area.array_index(addr.index), n)
            return [bool(v) for v in raw] if kind in BOOL_IO else [int(v) for v in raw]

        if kind == "R":
            words = await self._read_assigned(addr.var_name, 2 * n, 0)
            return codec.words_to_floats(words)

        if kind == "SR":
            size = codec.STRING_REGISTER_WORDS
            words = await self._read_assigned(addr.var_name, size * n, 1)
            return [codec.words_to_str(words[i:i + size]) for i in range(0, len(words), size)]

        if kind in ("PR", "POS"):
            if addr.member is not None:
                words = await self._read_assigned(self._member_var(addr), 2, 0)
                return [codec.words_to_float(*words)]
            size = codec.POSITION_WORDS
            words = await self._read_assigned(addr.var_name, size * n, 0)
            return [codec.decode_position(words[i:i + size]) for i in range(0, len(words), size)]

        if kind == "$":
            size, multiply = self._sysvar_type(dtype)
            words = await self._read_assigned(addr.name, size, multiply)
            return [self._decode_sysvar(words, dtype)]

        raise AddressError(f"Cannot read {addr}")

    async def _write(self, addr: Address, value: Any, dtype: str) -> None:
        t, kind = self._transport, addr.kind
        values = list(value) if isinstance(value, (list, tuple)) and kind != "$" else [value]
        check_count(addr, len(values))

        if kind in COIL_IO:
            area = IO_AREAS[kind]
            await t.write_array(area.node, area.array_index(addr.index),
                                [_to_bool(v) for v in values], ua.VariantType.Boolean)
            return

        if kind in HR_WRITABLE_IO:
            if kind in BOOL_IO:
                words = [int(_to_bool(v)) for v in values]
            else:
                words = [codec.to_int16(_to_int(v)) for v in values]
            await self._write_assigned(addr.var_name, len(words), 1, 0, words)
            return

        if kind in IO_AREAS or kind == "POS":
            raise ReadOnlyError(f"{kind} cannot be written over OPC UA")

        if kind == "R":
            if all(isinstance(v, int) and not isinstance(v, bool) for v in values):
                words, multiply = sum((codec.int32_to_words(v) for v in values), []), 1
            else:
                words, multiply = sum((codec.float_to_words(_to_float(v)) for v in values), []), 0
            await self._write_assigned(addr.var_name, len(words), multiply, 0, words)
            return

        if kind == "SR":
            size = codec.STRING_REGISTER_WORDS
            words = sum((codec.str_to_words(str(v), size) for v in values), [])
            await self._write_assigned(addr.var_name, len(words), 1, 0, words)
            return

        if kind == "PR":
            if len(values) != 1:
                raise AddressError("Write one position register at a time")
            if addr.member is not None:
                words = codec.float_to_words(_to_float(value))
                await self._write_assigned(self._member_var(addr), 2, 0, 0, words)
            else:
                await self._write_position(addr.var_name, value)
            return

        if kind == "$":
            size, multiply = self._sysvar_type(dtype)
            if dtype == "pos":
                await self._write_position(addr.name, value)
                return
            if dtype == "str":
                words = codec.str_to_words(str(value), size)
            elif dtype == "real":
                words = codec.float_to_words(_to_float(value))
            elif dtype == "bool":
                words = codec.int32_to_words(int(_to_bool(value)))
            else:
                words = codec.int32_to_words(_to_int(value))
            await self._write_assigned(addr.name, size, multiply, 0, words)
            return

        raise AddressError(f"Cannot write {addr}")

    async def _read_assigned(self, var_name: str, size: int, multiply: float) -> List[int]:
        async with self._window.assign(var_name, size, multiply) as base:
            return await self._transport.read_holding(base, size)

    async def _write_assigned(self, var_name: str, size: int, multiply: float,
                              offset: int, words: List[int]) -> None:
        async with self._window.assign(var_name, size, multiply) as base:
            await self._transport.write_holding(base + offset, words)

    async def _write_position(self, var_name: str, value: Any) -> None:
        size = codec.POSITION_WORDS
        async with self._window.assign(var_name, size, 0) as base:
            if isinstance(value, Mapping):
                current = codec.decode_position(await self._transport.read_holding(base, size))
                value = _merge_position(current, value)
            if not isinstance(value, Position):
                raise TypeError("Position registers take a Position or a dict like {'x': 500.0}")
            if value.representation == "joint":
                await self._transport.write_holding(base + 26, codec.encode_joints(value))
            else:
                await self._transport.write_holding(base, codec.encode_cartesian(value))

    @staticmethod
    def _member_var(addr: Address) -> str:
        # "@<start>.<size>" extracts one member of the 50-word structure (manual 55.3.3).
        return f"{addr.var_name}@{POSITION_MEMBERS[addr.member] + 1}.2"

    @staticmethod
    def _sysvar_type(dtype: str):
        try:
            return SYSVAR_TYPES[dtype]
        except KeyError:
            raise AddressError(f"dtype must be one of {', '.join(SYSVAR_TYPES)}, got {dtype!r}") from None

    @staticmethod
    def _decode_sysvar(words: List[int], dtype: str) -> Any:
        if dtype == "real":
            return codec.words_to_float(words[0], words[1])
        if dtype == "bool":
            return bool(codec.words_to_int32(words[0], words[1]))
        if dtype == "str":
            return codec.words_to_str(words)
        if dtype == "pos":
            return codec.decode_position(words)
        return codec.words_to_int32(words[0], words[1])

    # ------------------------------------------------------------------ robot state

    async def info(self) -> RobotInfo:
        """Model, serial number and software version."""
        self._require()
        t = self._transport
        return RobotInfo(
            model=await t.read_value(RobotInfoNodes.MODEL),
            serial_number=str(await t.read_value(RobotInfoNodes.SERIAL_NUMBER)).strip(),
            version=await t.read_value(RobotInfoNodes.VERSION),
            controller_model=_text(await self._read_robotics(RoboticsNodes.CONTROLLER_MODEL)),
            software_revision=_text(await self._read_robotics(RoboticsNodes.SOFTWARE_REVISION)),
        )

    async def status(self) -> RobotStatus:
        """Mode, servo, speed override, program state flags, alarms, joints and torque."""
        self._require()
        t = self._transport
        return RobotStatus(
            mode=await t.read_value(RobotInfoNodes.MODE_STATE),
            servo_on=bool(await t.read_value(RobotInfoNodes.SERVO_STATE)),
            speed_override=int(await t.read_value(RobotInfoNodes.PROGRAM_SPEED)),
            state=OperationState(await t.read_value(RobotInfoNodes.OPERATION_STATE)),
            alarms=await self.alarms(),
            joint_positions=[codec.tidy(v) for v in await t.read_value(RobotInfoNodes.POSITION) or []],
            torque=[codec.tidy(v) for v in await t.read_value(RobotInfoNodes.TORQUE) or []],
            uptime_minutes=int(await t.read_value(RobotInfoNodes.UPTIME)),
            protective_stop=_opt_bool(await self._read_robotics(RoboticsNodes.PROTECTIVE_STOP)),
        )

    async def alarms(self) -> List[str]:
        """Currently active alarms, e.g. ['SRVO-001 Operator panel E-stop']."""
        self._require()
        raw = await self._transport.read_value(RobotInfoNodes.ALARM)
        if not isinstance(raw, (list, tuple)):
            raw = [raw]
        return [str(a).strip() for a in raw if a and str(a).strip()]

    async def position(self, uframe: int = 0, group: int = 1) -> Position:
        """Current position in `uframe` (0 = world, -1 = active user frame)."""
        prefix = f"G{group}:" if group != 1 else ""
        return await self.read(f"POS[{prefix}{uframe}]")

    async def program_status(self, task: int = 1) -> ProgramStatus:
        """Running program name, line and state of task `task` (manual 55.3.7)."""
        self._require()
        words = await self._read_assigned(f"PRG[{task}]", codec.PROGRAM_STATUS_WORDS, 1)
        state = words[9] if words[9] in ExecutionState._value2member_map_ else 0
        return ProgramStatus(
            program=codec.words_to_str(words[0:8]),
            line=words[8],
            state=ExecutionState(state),
            parent_program=codec.words_to_str(words[10:18]),
        )

    async def watch(self, addresses: Iterable[AddressLike], interval: float = 0.5
                    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Poll `addresses` every `interval` seconds and yield {address: value} for
        the values that changed. The first iteration yields every value.
        """
        addresses = list(addresses)
        previous: Dict[str, Any] = {}
        while True:
            current = await self.read_many(addresses)
            changed = {k: v for k, v in current.items() if k not in previous or previous[k] != v}
            if changed:
                yield changed
            previous = current
            await asyncio.sleep(interval)

    async def _read_robotics(self, identifier: int) -> Any:
        """Read a node of the OPC UA Robotics model, or None if the controller lacks it."""
        ns = self._robotics_ns if self._robotics_ns is not None else ROBOTICS_NS_DEFAULT
        try:
            return await self._transport.read_value(f"ns={ns};i={identifier}")
        except CommunicationError:
            return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("1", "0", "on", "off", "true", "false"):
        return value.strip().lower() in ("1", "on", "true")
    raise ValueError(f"Expected a boolean (True/False, 1/0, 'on'/'off'), got {value!r}")


def _to_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"Expected an integer, got {value!r}")
    f = float(value)
    if not f.is_integer():
        raise ValueError(f"Expected an integer, got {value!r}")
    return int(f)


def _to_float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Expected a number, got {value!r}")
    return float(value)


def _merge_position(current: Position, changes: Mapping[str, Any]) -> Position:
    keys = {k.lower() for k in changes}
    unknown = keys - set(POSITION_MEMBERS) - {"config"}
    if unknown:
        raise AddressError(f"Unknown position members: {', '.join(sorted(unknown))}")
    joint_keys = {k for k in keys if k.startswith("j")}
    if joint_keys and joint_keys != keys:
        raise AddressError("Do not mix joint (j1..j9) and cartesian members in one write")
    changes = {k.lower(): v for k, v in changes.items()}

    if joint_keys:
        joints = list(current.joints or ())
        for k in joint_keys:
            n = int(k[1:])
            joints += [0.0] * (n - len(joints))
            joints[n - 1] = _to_float(changes[k])
        return dataclasses.replace(current, joints=tuple(joints), representation="joint")

    ext = list(current.ext)
    simple = {}
    for k, v in changes.items():
        if k.startswith("e"):
            ext[int(k[1:]) - 1] = _to_float(v)
        elif k == "config":
            simple["config"] = v
        else:
            simple[k] = _to_float(v)
    return dataclasses.replace(current, ext=tuple(ext), representation="cartesian", **simple)


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return getattr(value, "Text", None) or str(value)


def _opt_bool(value: Any) -> Optional[bool]:
    return None if value is None else bool(value)
