"""
Thin layer over asyncua for the requests the FANUC server understands.

The NanoUaServer accepts only one node per Read/Write request (MaxNodesPerRead = 1),
and its Modbus nodes are large arrays, so every array access uses an IndexRange.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, List, Optional, Sequence

from asyncua import Client, ua

from .errors import CommunicationError
from .nodes import ModbusNodes

COMMAND_MAX_CHARS = 128


def _index_range(start: int, count: int) -> str:
    return str(start) if count == 1 else f"{start}:{start + count - 1}"


class Transport:
    def __init__(self, client: Client):
        self._client = client

    async def read_value(self, node_id: str, index_range: Optional[str] = None) -> Any:
        rv = ua.ReadValueId()
        rv.NodeId = ua.NodeId.from_string(node_id)
        rv.AttributeId = ua.AttributeIds.Value
        if index_range is not None:
            rv.IndexRange = index_range
        params = ua.ReadParameters()
        params.NodesToRead = [rv]
        result = (await self._client.uaclient.read(params))[0]
        if not result.StatusCode.is_good():
            raise CommunicationError(f"Read of {node_id}[{index_range}] failed", result.StatusCode.name)
        return result.Value.Value if result.Value is not None else None

    async def write_value(self, node_id: str, value: Any, variant_type: ua.VariantType,
                          index_range: Optional[str] = None) -> None:
        wv = ua.WriteValue()
        wv.NodeId = ua.NodeId.from_string(node_id)
        wv.AttributeId = ua.AttributeIds.Value
        if index_range is not None:
            wv.IndexRange = index_range
        wv.Value = ua.DataValue(ua.Variant(value, variant_type))
        params = ua.WriteParameters()
        params.NodesToWrite = [wv]
        status = (await self._client.uaclient.write(params))[0]
        if not status.is_good():
            raise CommunicationError(f"Write of {node_id}[{index_range}] failed", status.name)

    async def read_array(self, node_id: str, start: int, count: int) -> List[Any]:
        """Read `count` elements starting at 0-based `start`."""
        value = await self.read_value(node_id, _index_range(start, count))
        return list(value) if isinstance(value, (list, tuple)) else [value]

    async def write_array(self, node_id: str, start: int, values: Sequence[Any],
                          variant_type: ua.VariantType) -> None:
        await self.write_value(node_id, list(values), variant_type, _index_range(start, len(values)))

    async def read_holding(self, start: int, count: int) -> List[int]:
        return await self.read_array(ModbusNodes.HOLDING_REGISTERS, start, count)

    async def write_holding(self, start: int, words: Sequence[int]) -> None:
        await self.write_array(ModbusNodes.HOLDING_REGISTERS, start, words, ua.VariantType.Int16)

    async def write_command(self, text: str) -> None:
        if len(text) > COMMAND_MAX_CHARS:
            raise ValueError(f"Command longer than {COMMAND_MAX_CHARS} characters: {text!r}")
        await self.write_value(ModbusNodes.COMMAND, text, ua.VariantType.String)


def _format_multiply(multiply: float) -> str:
    return str(int(multiply)) if float(multiply).is_integer() else repr(float(multiply))


class AssignmentWindow:
    """
    Dynamic holding register assignment (manual 55.4).

    The library maps whatever robot data an operation needs to holding register
    address 1 with "CLRASG + SETASG" on the Command node, then reads or writes the
    window. Assignments live only as long as the connection, so they are re-sent
    after a reconnect. Note that CLRASG also hides the controller's static
    $SNPX_ASG mapping for this connection.
    """
    START_ADDRESS = 1
    MAX_WORDS = 16384

    def __init__(self, transport: Transport):
        self._transport = transport
        self._lock = asyncio.Lock()
        self._current: Optional[str] = None

    def reset(self) -> None:
        self._current = None

    @asynccontextmanager
    async def assign(self, var_name: str, size: int, multiply: float) -> AsyncIterator[int]:
        """Assign `size` words of `var_name`; yields the 0-based array index of the window."""
        if not 1 <= size <= self.MAX_WORDS:
            raise ValueError(f"Assignment size must be 1..{self.MAX_WORDS}, got {size}")
        spec = f"SETASG {self.START_ADDRESS} {size} {var_name} {_format_multiply(multiply)}"
        async with self._lock:
            if spec != self._current:
                self._current = None
                await self._transport.write_command(f"CLRASG\n{spec}")
                self._current = spec
            yield self.START_ADDRESS - 1
