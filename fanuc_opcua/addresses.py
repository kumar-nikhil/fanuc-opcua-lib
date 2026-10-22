"""
Parsing of FANUC-style addresses ("DO[1]", "R[5]", "PR[G2:3].x", "POS", "$MCR.$GENOVERRIDE")
and the Modbus table layout from manual section 55.2.3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .errors import AddressError
from .nodes import ModbusNodes


@dataclass(frozen=True)
class IOArea:
    """Where one I/O type lives inside a Modbus table."""
    node: str
    modbus_address: int  # Modbus address of the signal with index `first`
    first: int
    last: int

    def array_index(self, index: int) -> int:
        return self.modbus_address - 1 + (index - self.first)


# Manual 55.2.3 "Correspondence of Modbus Address to Robot Data".
IO_AREAS = {
    "DI": IOArea(ModbusNodes.DISCRETE_INPUT, 1, 1, 10000),
    "RI": IOArea(ModbusNodes.DISCRETE_INPUT, 10001, 1, 10000),
    "UI": IOArea(ModbusNodes.DISCRETE_INPUT, 20001, 1, 1000),
    "UO": IOArea(ModbusNodes.DISCRETE_INPUT, 21001, 1, 999),
    "SI": IOArea(ModbusNodes.DISCRETE_INPUT, 22000, 0, 999),
    "SO": IOArea(ModbusNodes.DISCRETE_INPUT, 23000, 0, 1000),
    "WI": IOArea(ModbusNodes.DISCRETE_INPUT, 24001, 1, 1000),
    "WO": IOArea(ModbusNodes.DISCRETE_INPUT, 25001, 1, 1000),
    "WSI": IOArea(ModbusNodes.DISCRETE_INPUT, 26001, 1, 1000),
    "WSO": IOArea(ModbusNodes.DISCRETE_INPUT, 27001, 1, 1000),
    "DO": IOArea(ModbusNodes.COILS, 1, 1, 10000),
    "RO": IOArea(ModbusNodes.COILS, 10001, 1, 10000),
    "F": IOArea(ModbusNodes.COILS, 20001, 1, 10000),
    "GI": IOArea(ModbusNodes.INPUT_REGISTERS, 1, 1, 1000),
    "GO": IOArea(ModbusNodes.INPUT_REGISTERS, 1001, 1, 1000),
    "AI": IOArea(ModbusNodes.INPUT_REGISTERS, 2001, 1, 1000),
    "AO": IOArea(ModbusNodes.INPUT_REGISTERS, 3001, 1, 1000),
}

# Outputs that are read from a read-only table but can be written through a
# holding register assignment (manual 55.2.3 / 55.3.10).
HR_WRITABLE_IO = {"GO", "AO", "WO", "WSO"}
COIL_IO = {"DO", "RO", "F"}
BOOL_IO = {k for k, a in IO_AREAS.items() if a.node in (ModbusNodes.DISCRETE_INPUT, ModbusNodes.COILS)}

# Word offsets of position members inside the 50-word position block (manual 55.3.3).
POSITION_MEMBERS = {
    "x": 0, "y": 2, "z": 4, "w": 6, "p": 8, "r": 10,
    "e1": 12, "e2": 14, "e3": 16,
    **{f"j{n}": 26 + 2 * (n - 1) for n in range(1, 10)},
}

REGISTER_LIMITS = {"R": 10000, "PR": 10000, "SR": 10000}

_ADDRESS_RE = re.compile(
    r"^(?P<kind>[A-Z]+)(?:\[(?:G(?P<group>\d+):)?(?P<index>-?\d+)\])?(?:\.(?P<member>[A-Z0-9]+))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Address:
    kind: str                     # "DO", "R", "PR", "SR", "POS" or "$" for system variables
    index: int = 0
    group: int = 1
    member: Optional[str] = None  # position member such as "x" or "j1"
    name: str = ""                # system variable name when kind == "$"

    @property
    def var_name(self) -> str:
        """Robot data name in the $SNPX_ASG / SETASG $VAR_NAME format."""
        if self.kind == "$":
            return self.name
        group = f"G{self.group}:" if self.group != 1 else ""
        return f"{self.kind}[{group}{self.index}]"

    def __str__(self) -> str:
        return self.var_name + (f".{self.member}" if self.member else "")


def parse_address(text: str) -> Address:
    """Parse a FANUC address string. Raises AddressError when it is invalid."""
    if isinstance(text, Address):
        return text
    s = str(text).strip()
    if s.startswith("$"):
        if " " in s:
            raise AddressError(f"System variable name must not contain spaces: {text!r}")
        return Address("$", name=s)

    m = _ADDRESS_RE.match(s)
    if not m:
        raise AddressError(f"Cannot parse address {text!r}; expected e.g. 'DO[1]', 'R[5]', 'PR[1].x'")
    kind = m["kind"].upper()
    index = int(m["index"]) if m["index"] is not None else None
    group = int(m["group"]) if m["group"] else 1
    member = m["member"].lower() if m["member"] else None

    if kind == "POS":
        uframe = 0 if index is None else index
        if not -1 <= uframe <= 61:
            raise AddressError(f"POS user frame must be -1..61, got {uframe}")
        addr = Address("POS", uframe, group, member)
    elif index is None:
        raise AddressError(f"Address {text!r} needs an index, e.g. '{kind}[1]'")
    elif kind in IO_AREAS:
        area = IO_AREAS[kind]
        if not area.first <= index <= area.last:
            raise AddressError(f"{kind} index must be {area.first}..{area.last}, got {index}")
        addr = Address(kind, index, group, member)
    elif kind in REGISTER_LIMITS:
        if not 1 <= index <= REGISTER_LIMITS[kind]:
            raise AddressError(f"{kind} index must be 1..{REGISTER_LIMITS[kind]}, got {index}")
        addr = Address(kind, index, group, member)
    else:
        raise AddressError(f"Unsupported address type {kind!r} in {text!r}")

    if addr.group != 1 and addr.kind not in ("PR", "POS"):
        raise AddressError(f"Group prefix is only valid for PR and POS: {text!r}")
    if addr.member is not None:
        if addr.kind not in ("PR", "POS"):
            raise AddressError(f"Members like '.x' are only valid for PR and POS: {text!r}")
        if addr.member not in POSITION_MEMBERS:
            raise AddressError(f"Unknown position member {addr.member!r}; use one of {', '.join(POSITION_MEMBERS)}")
    return addr


def check_count(addr: Address, count: int) -> None:
    """Make sure `count` consecutive items starting at `addr` stay inside one area."""
    if count < 1:
        raise AddressError(f"count must be >= 1, got {count}")
    if count == 1:
        return
    if addr.kind in IO_AREAS:
        last = IO_AREAS[addr.kind].last
    elif addr.kind in REGISTER_LIMITS and addr.member is None:
        last = REGISTER_LIMITS[addr.kind]
    else:
        raise AddressError(f"count is not supported for {addr}")
    if addr.index + count - 1 > last:
        raise AddressError(f"{addr.kind}[{addr.index}] + {count} items runs past {addr.kind}[{last}]")
