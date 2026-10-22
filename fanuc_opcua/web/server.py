"""
Local web GUI for fanuc_opcua.

    fanuc-opcua web                 # http://127.0.0.1:8080, connects to ROBOGUIDE
    fanuc-opcua web --host 10.0.0.5 --read-only

The server holds one robot connection and exposes a small JSON API that the
single page in static/index.html uses. Needs the optional "web" extra (aiohttp).
"""
from __future__ import annotations

import asyncio
import collections
import logging
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from aiohttp import web

from ..addresses import IO_AREAS, POSITION_MEMBERS, REGISTER_LIMITS, parse_address
from ..cli import parse_assignment, to_jsonable
from ..client import SYSVAR_TYPES, FanucClient
from ..errors import CommunicationError, FanucConnectionError, FanucError, NotConnectedError
from ..nodes import DEFAULT_PORT, ROBOGUIDE_HOST

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).with_name("static")

IO_LABELS = {
    "DI": "Digital input", "DO": "Digital output", "RI": "Robot input", "RO": "Robot output",
    "UI": "UOP input", "UO": "UOP output", "SI": "SOP input", "SO": "SOP output",
    "WI": "Weld input", "WO": "Weld output", "WSI": "Wire stick input", "WSO": "Wire stick output",
    "F": "Flag", "GI": "Group input", "GO": "Group output", "AI": "Analog input", "AO": "Analog output",
}
WRITABLE_IO = {"DO", "RO", "F", "GO", "AO", "WO", "WSO"}

# System variables offered in the GUI's drop-down, checked on R-30iB Plus V9.40.
# "write" marks the ones the GUI lets you change; the rest are shown read only.
SYSVAR_PRESETS = [
    {"group": "Speed", "name": "$MCR.$GENOVERRIDE", "dtype": "int", "label": "Speed override (%)", "write": True},
    {"group": "Speed", "name": "$SCR.$RUNOVLIM", "dtype": "int", "label": "Max override when running (%)", "write": False},
    {"group": "Speed", "name": "$SCR.$JOGOVLIM", "dtype": "int", "label": "Max override when jogging (%)", "write": False},
    {"group": "Speed", "name": "$SCR.$COLDOVRD", "dtype": "int", "label": "Override after cold start (%)", "write": False},
    {"group": "Speed", "name": "$SCR.$FENCEOVRD", "dtype": "int", "label": "Override when fence is open (%)", "write": False},
    {"group": "Speed", "name": "$GROUP[1].$SPEED", "dtype": "real", "label": "Group 1 default speed (mm/s)", "write": False},
    {"group": "Frames", "name": "$MNUTOOLNUM[1]", "dtype": "int", "label": "Active tool frame number", "write": False},
    {"group": "Frames", "name": "$MNUFRAMENUM[1]", "dtype": "int", "label": "Active user frame number", "write": False},
    {"group": "Frames", "name": "$MNUTOOL[1,1]", "dtype": "pos", "label": "Tool frame 1", "write": False},
    {"group": "Frames", "name": "$MNUFRAME[1,1]", "dtype": "pos", "label": "User frame 1", "write": False},
    {"group": "Operation", "name": "$TP_DEFPROG", "dtype": "str", "label": "Selected TP program", "write": False},
    {"group": "Operation", "name": "$MCR.$DRY_RUN", "dtype": "bool", "label": "Dry run", "write": False},
    {"group": "Operation", "name": "$MCR_GRP[1].$MACHINELOCK", "dtype": "bool", "label": "Machine lock (group 1)", "write": False},
    {"group": "Operation", "name": "$MCR.$ENBL", "dtype": "bool", "label": "Motion enabled", "write": False},
    {"group": "Operation", "name": "$RMT_MASTER", "dtype": "int",
     "label": "Remote master (0 remote device, 1 CRT/KB, 2 host, 3 none)", "write": False},
    {"group": "Operation", "name": "$TIMER[1].$TIMER_VAL", "dtype": "int", "label": "Program timer 1", "write": False},
    {"group": "Controller", "name": "$SCR_GRP[1].$ROBOT_MODEL", "dtype": "str", "label": "Robot model (short)", "write": False},
    {"group": "Controller", "name": "$VERSION", "dtype": "str", "label": "Software version", "write": False},
    {"group": "Controller", "name": "$HOSTNAME", "dtype": "str", "label": "Controller host name", "write": False},
    {"group": "Controller", "name": "$SCR.$NUM_GROUP", "dtype": "int", "label": "Number of motion groups", "write": False},
    {"group": "Controller", "name": "$SCR.$MAXNUMTASK", "dtype": "int", "label": "Max. number of tasks", "write": False},
    {"group": "Controller", "name": "$FAST_CLOCK", "dtype": "int", "label": "Fast clock counter", "write": False},
    {"group": "OPC UA", "name": "$SNPX_ASG[1].$VAR_NAME", "dtype": "str",
     "label": "Static assignment 1: data name", "write": False},
    {"group": "OPC UA", "name": "$SNPX_ASG[1].$ADDRESS", "dtype": "int",
     "label": "Static assignment 1: start address", "write": False},
    {"group": "OPC UA", "name": "$SNPX_ASG[1].$SIZE", "dtype": "int", "label": "Static assignment 1: size", "write": False},
]


def build_catalog() -> List[Dict[str, Any]]:
    """Address types for the GUI's drop-down menus."""
    items = []
    for kind, area in IO_AREAS.items():
        numeric = kind in ("GI", "GO", "AI", "AO")
        items.append({
            "kind": kind, "label": f"{IO_LABELS[kind]} {kind}[ ]", "group": "Numeric I/O" if numeric else "Digital I/O",
            "type": "int" if numeric else "bool", "first": area.first, "last": area.last,
            "writable": kind in WRITABLE_IO, "count": True,
        })
    items += [
        {"kind": "R", "label": "Numeric register R[ ]", "group": "Registers", "type": "number",
         "first": 1, "last": REGISTER_LIMITS["R"], "writable": True, "count": True},
        {"kind": "SR", "label": "String register SR[ ]", "group": "Registers", "type": "string",
         "first": 1, "last": REGISTER_LIMITS["SR"], "writable": True, "count": True},
        {"kind": "PR", "label": "Position register PR[ ]", "group": "Positions", "type": "position",
         "first": 1, "last": REGISTER_LIMITS["PR"], "writable": True, "count": True},
        {"kind": "POS", "label": "Current position POS[user frame]", "group": "Positions", "type": "position",
         "first": -1, "last": 61, "writable": False, "count": False},
        {"kind": "$", "label": "System variable $...", "group": "System", "type": "sysvar",
         "writable": True, "count": False},
    ]
    return items


class Stats:
    """Request counters and latency history shown in the GUI."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.requests = 0
        self.reads = 0
        self.writes = 0
        self.errors = 0
        self.total_ms = 0.0
        self.last_ms: Optional[float] = None
        self.max_ms = 0.0
        self.history: collections.deque = collections.deque(maxlen=60)   # (time, ms, op, ok)
        self.recent: collections.deque = collections.deque(maxlen=2000)  # request times

    def record(self, ms: float, kind: str, ok: bool, op: str = "manual") -> None:
        now = time.time()
        self.requests += 1
        self.reads += kind == "read"
        self.writes += kind == "write"
        self.errors += not ok
        self.total_ms += ms
        self.last_ms = ms
        self.max_ms = max(self.max_ms, ms)
        self.history.append((now, round(ms, 2), op, ok))
        self.recent.append(now)

    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        per_sec = sum(1 for t in self.recent if now - t <= 5) / 5
        return {
            "requests": self.requests, "reads": self.reads, "writes": self.writes, "errors": self.errors,
            "last_ms": None if self.last_ms is None else round(self.last_ms, 2),
            "avg_ms": round(self.total_ms / self.requests, 2) if self.requests else None,
            "max_ms": round(self.max_ms, 2),
            "per_sec": round(per_sec, 1),
            # Each entry is one operation: [ms, op, ok, seconds ago]. op is "status",
            # "program", "position" (dashboard refresh) or "manual" (reads/writes from the page).
            "history": [[ms, op, ok, round(now - t, 1)] for t, ms, op, ok in self.history],
        }


class RobotSession:
    """The one robot connection shared by all browser tabs."""

    def __init__(self, host: str, port: int, read_only: bool, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.read_only = read_only
        self.timeout = timeout
        self.robot: Optional[FanucClient] = None
        self.info: Optional[Dict[str, Any]] = None
        self.connected_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.stats = Stats()
        self.unsupported: Dict[str, str] = {}  # dashboard parts this controller lacks
        self._connect_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self.robot is not None and self.robot.connected

    async def connect(self, host: str, port: int) -> None:
        async with self._connect_lock:
            await self._drop()
            robot = FanucClient(host, port, self.timeout)
            await robot.connect()
            self.host, self.port, self.robot = host, port, robot
            self.connected_at = time.time()
            self.last_error = None
            self.stats.reset()
            self.unsupported = {}
            self.info = await self._read_info()

    async def _read_info(self) -> Dict[str, Any]:
        """Robot info; falls back to system variables on software without RobotInformation nodes."""
        robot = self.robot
        try:
            return to_jsonable(await self.call(robot.info))
        except CommunicationError:
            pass
        info: Dict[str, Any] = {"note": "RobotInformation nodes need 7DF1/P28+ or 7DF3/P06+; read from system variables"}
        for key, name in (("model", "$SCR_GRP[1].$ROBOT_MODEL"), ("version", "$VERSION"),
                          ("serial_number", "$HOSTNAME")):
            try:
                info[key] = await self.call(lambda n=name: robot.read(n, dtype="str"))
            except FanucError:
                info[key] = None
        return info

    async def disconnect(self) -> None:
        async with self._connect_lock:
            await self._drop()

    async def _drop(self) -> None:
        robot, self.robot = self.robot, None
        self.info = None
        self.connected_at = None
        if robot is not None:
            try:
                await robot.disconnect()
            except Exception:  # noqa: BLE001 - the link may already be gone
                pass

    async def call(self, func: Callable[[], Awaitable[Any]], kind: str = "read", op: str = "manual") -> Any:
        """Run one robot operation, timing it and dropping the link if it broke."""
        if not self.connected:
            raise NotConnectedError("Not connected to a robot")
        start = time.perf_counter()
        try:
            result = await func()
        except (FanucError, ValueError, TypeError) as e:
            self.stats.record((time.perf_counter() - start) * 1000, kind, False, op)
            if isinstance(e, CommunicationError) and "BadSessionIdInvalid" in str(e):
                await self._lost(e)
            raise
        except (OSError, asyncio.TimeoutError, ConnectionError) as e:
            self.stats.record((time.perf_counter() - start) * 1000, kind, False, op)
            await self._lost(e)
            raise FanucConnectionError(f"Connection to robot lost ({type(e).__name__})") from e
        except Exception as e:  # asyncua raises its own types when the session dies
            self.stats.record((time.perf_counter() - start) * 1000, kind, False, op)
            if self.robot is not None and not await self._alive():
                await self._lost(e)
                raise FanucConnectionError(f"Connection to robot lost ({type(e).__name__})") from e
            raise FanucError(f"{type(e).__name__}: {e}") from e
        self.stats.record((time.perf_counter() - start) * 1000, kind, True, op)
        return result

    async def _alive(self) -> bool:
        try:
            await asyncio.wait_for(self.robot.alarms(), 2)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def _lost(self, error: BaseException) -> None:
        self.last_error = f"Connection lost: {type(error).__name__} {error}".strip()
        logger.warning(self.last_error)
        await self._drop()

    def describe(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "host": self.host,
            "port": self.port,
            "endpoint": f"opc.tcp://{self.host}:{self.port}/FANUC/NanoUaServer",
            "read_only": self.read_only,
            "info": self.info,
            "connected_for_s": round(time.time() - self.connected_at) if self.connected_at else None,
            "last_error": self.last_error,
            "stats": self.stats.snapshot(),
        }


# ---------------------------------------------------------------------- handlers

SESSION = web.AppKey("session", RobotSession)


def _ok(**data: Any) -> web.Response:
    return web.json_response({"ok": True, **data})


def _fail(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)


async def _body(request: web.Request) -> Dict[str, Any]:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text="Request body must be JSON")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Request body must be a JSON object")
    return data


def _session(request: web.Request) -> RobotSession:
    return request.app[SESSION]


@web.middleware
async def errors_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except NotConnectedError as e:
        return _fail(str(e), 409)
    except FanucConnectionError as e:
        return _fail(str(e), 503)
    except (FanucError, ValueError, TypeError) as e:
        return _fail(str(e), 400)


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})


async def catalog(request: web.Request) -> web.Response:
    return _ok(items=build_catalog(), members=list(POSITION_MEMBERS), dtypes=list(SYSVAR_TYPES),
               sysvars=SYSVAR_PRESETS)


async def session_info(request: web.Request) -> web.Response:
    return _ok(**_session(request).describe())


async def connect(request: web.Request) -> web.Response:
    s = _session(request)
    data = await _body(request)
    host = str(data.get("host") or s.host).strip()
    port = int(data.get("port") or s.port)
    await s.connect(host, port)
    return _ok(**s.describe())


async def disconnect(request: web.Request) -> web.Response:
    s = _session(request)
    await s.disconnect()
    return _ok(**s.describe())


async def live(request: web.Request) -> web.Response:
    """Everything the dashboard shows, in one call."""
    s = _session(request)
    robot = s.robot
    if not s.connected:
        return _ok(**s.describe(), status=None)
    start = time.perf_counter()
    parts: Dict[str, Any] = {}
    # Each part is read on its own so a controller without the status nodes
    # (older than 7DF1/P28) still shows program and position. A part that
    # failed once is not asked for again until the next connect.
    for key, func in (("status", robot.status), ("program", robot.program_status), ("position", robot.position)):
        parts[key] = None
        if key in s.unsupported:
            continue
        try:
            parts[key] = to_jsonable(await s.call(func, op=key))
        except CommunicationError as e:
            s.unsupported[key] = str(e)
    cycle_ms = round((time.perf_counter() - start) * 1000, 1)
    return _ok(**s.describe(), **parts, unavailable=s.unsupported, cycle_ms=cycle_ms)


async def read(request: web.Request) -> web.Response:
    s = _session(request)
    data = await _body(request)
    address = str(data.get("address", "")).strip()
    count = data.get("count")
    count = int(count) if count not in (None, "", 1, "1") else None
    dtype = data.get("dtype") or None
    parse_address(address)
    start = time.perf_counter()
    value = await s.call(lambda: s.robot.read(address, count, dtype))
    return _ok(address=address, value=to_jsonable(value), ms=round((time.perf_counter() - start) * 1000, 2))


async def read_many(request: web.Request) -> web.Response:
    """Read a list of addresses; one bad address does not fail the others."""
    s = _session(request)
    data = await _body(request)
    values: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    for address in data.get("addresses", [])[:100]:
        try:
            values[address] = to_jsonable(await s.call(lambda a=address: s.robot.read(a)))
        except FanucConnectionError:
            raise
        except (FanucError, ValueError, TypeError) as e:
            errors[address] = str(e)
    return _ok(values=values, errors=errors)


async def write(request: web.Request) -> web.Response:
    s = _session(request)
    if s.read_only:
        return _fail("The GUI was started with --read-only; writes are disabled", 403)
    data = await _body(request)
    address = str(data.get("address", "")).strip()
    dtype = data.get("dtype") or None
    raw = data.get("value")
    addr = parse_address(address)

    if addr.kind == "PR" and addr.member is None:
        if not isinstance(raw, dict) or not raw:
            raise ValueError("Send position members as an object, e.g. {\"x\": 500}")
        value: Any = {k: float(v) for k, v in raw.items()}
    else:
        if isinstance(raw, bool):
            raw = "on" if raw else "off"
        _, value = parse_assignment(f"{address}={raw}", dtype)

    start = time.perf_counter()
    await s.call(lambda: s.robot.write(address, value, dtype), "write")
    ms = round((time.perf_counter() - start) * 1000, 2)
    readback = to_jsonable(await s.call(lambda: s.robot.read(address, dtype=dtype)))
    return _ok(address=address, written=to_jsonable(value), readback=readback, ms=ms)


def create_app(host: str = ROBOGUIDE_HOST, port: int = DEFAULT_PORT, read_only: bool = False,
               auto_connect: bool = True, session: Optional[RobotSession] = None,
               timeout: float = 5.0) -> web.Application:
    app = web.Application(middlewares=[errors_middleware])
    app[SESSION] = session or RobotSession(host, port, read_only, timeout)
    app.router.add_get("/", index)
    app.router.add_get("/api/catalog", catalog)
    app.router.add_get("/api/session", session_info)
    app.router.add_post("/api/connect", connect)
    app.router.add_post("/api/disconnect", disconnect)
    app.router.add_get("/api/live", live)
    app.router.add_post("/api/read", read)
    app.router.add_post("/api/read_many", read_many)
    app.router.add_post("/api/write", write)

    async def on_startup(app: web.Application) -> None:
        if auto_connect:
            s = app[SESSION]
            try:
                await s.connect(s.host, s.port)
            except FanucError as e:
                s.last_error = str(e)
                logger.warning("Could not connect at startup: %s", e)

    async def on_cleanup(app: web.Application) -> None:
        await app[SESSION].disconnect()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def run(robot_host: str = ROBOGUIDE_HOST, robot_port: int = DEFAULT_PORT, bind: str = "127.0.0.1",
        http_port: int = 8080, read_only: bool = False, open_browser: bool = True,
        timeout: float = 5.0) -> None:
    url = f"http://{'127.0.0.1' if bind in ('0.0.0.0', '::') else bind}:{http_port}/"
    app = create_app(robot_host, robot_port, read_only, timeout=timeout)
    print(f"FANUC OPC UA GUI on {url}  (robot {robot_host}:{robot_port}"
          f"{', read only' if read_only else ''}) - press Ctrl+C to stop")
    if bind in ("0.0.0.0", "::"):
        print("Warning: the GUI is reachable from other computers on this network and has no login.")
    if open_browser:
        import webbrowser

        async def open_page(app: web.Application) -> None:
            asyncio.get_running_loop().call_later(0.5, webbrowser.open, url)

        app.on_startup.append(open_page)
    web.run_app(app, host=bind, port=http_port, print=None)
