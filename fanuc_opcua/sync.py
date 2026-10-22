"""
Blocking wrapper around FanucClient for scripts that do not use asyncio.

    from fanuc_opcua import FanucClientSync

    with FanucClientSync("127.0.0.2") as robot:
        robot.write("DO[1]", True)
        print(robot.read("R[1]"))
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Coroutine, Dict, Iterable, Iterator, List, Optional

from .client import AddressLike, FanucClient
from .nodes import DEFAULT_PORT
from .types import Position, ProgramStatus, RobotInfo, RobotStatus


class FanucClientSync:
    """Same API as FanucClient, but every method blocks until it is done."""

    def __init__(self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="fanuc-opcua", daemon=True)
        self._thread.start()
        self._client = FanucClient(host, port, timeout)

    def _run(self, coro: Coroutine) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    @property
    def endpoint(self) -> str:
        return self._client.endpoint

    @property
    def connected(self) -> bool:
        return self._client.connected

    def connect(self) -> None:
        self._run(self._client.connect())

    def disconnect(self) -> None:
        self._run(self._client.disconnect())

    def close(self) -> None:
        """Disconnect and stop the background event loop."""
        if self._loop.is_closed():
            return
        try:
            self.disconnect()
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
            self._loop.close()

    def __enter__(self) -> "FanucClientSync":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def read(self, address: AddressLike, count: Optional[int] = None, dtype: Optional[str] = None) -> Any:
        return self._run(self._client.read(address, count, dtype))

    def read_many(self, addresses: Iterable[AddressLike]) -> Dict[str, Any]:
        return self._run(self._client.read_many(list(addresses)))

    def write(self, address: AddressLike, value: Any, dtype: Optional[str] = None) -> None:
        self._run(self._client.write(address, value, dtype))

    def info(self) -> RobotInfo:
        return self._run(self._client.info())

    def status(self) -> RobotStatus:
        return self._run(self._client.status())

    def alarms(self) -> List[str]:
        return self._run(self._client.alarms())

    def position(self, uframe: int = 0, group: int = 1) -> Position:
        return self._run(self._client.position(uframe, group))

    def program_status(self, task: int = 1) -> ProgramStatus:
        return self._run(self._client.program_status(task))

    def watch(self, addresses: Iterable[AddressLike], interval: float = 0.5) -> Iterator[Dict[str, Any]]:
        """Poll and yield {address: value} for values that changed (all values first)."""
        addresses = list(addresses)
        previous: Dict[str, Any] = {}
        while True:
            current = self.read_many(addresses)
            changed = {k: v for k, v in current.items() if k not in previous or previous[k] != v}
            if changed:
                yield changed
            previous = current
            time.sleep(interval)
