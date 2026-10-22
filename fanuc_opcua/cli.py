"""
Command line interface.

    fanuc-opcua info
    fanuc-opcua status
    fanuc-opcua read DO[1] R[5] PR[1] --count 4
    fanuc-opcua write DO[1]=on R[5]=3.5 SR[1]="hello" PR[1].x=500
    fanuc-opcua watch DO[1] R[1] UI[1] --interval 0.5
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import enum
import json
import os
import sys
from typing import Any, List, Optional, Tuple

from .addresses import BOOL_IO, IO_AREAS, parse_address
from .client import SYSVAR_TYPES, FanucClient, _to_bool
from .errors import FanucError
from .nodes import DEFAULT_PORT, ROBOGUIDE_HOST
from .types import Position, RobotStatus

HOST_ENV = "FANUC_HOST"


def to_jsonable(value: Any) -> Any:
    if isinstance(value, RobotStatus):
        # Keep the raw "state" number and add readable flag names next to it.
        data = {k: to_jsonable(v) for k, v in dataclasses.asdict(value).items()}
        items = list(data.items())
        at = [k for k, _ in items].index("state") + 1
        return dict(items[:at] + [("state_flags", value.state_flags)] + items[at:])
    if dataclasses.is_dataclass(value):
        return {k: to_jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, enum.Enum):
        return value.name if not isinstance(value, enum.IntFlag) else int(value)
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    return value


def _format(value: Any) -> str:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, Position):
        return "\n  " + str(value).replace("\n", "\n  ")
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format(v) for v in value) + "]"
    return str(value)


def parse_assignment(text: str, dtype: Optional[str]) -> Tuple[str, Any]:
    """Turn 'DO[1]=on' or 'R[5]=3.5' into ('DO[1]', True) / ('R[5]', 3.5)."""
    if "=" not in text:
        raise FanucError(f"Expected ADDRESS=VALUE, got {text!r}")
    address, raw = text.split("=", 1)
    addr = parse_address(address)
    kind = addr.kind
    if kind in BOOL_IO:
        value: Any = _to_bool(raw)
    elif kind in IO_AREAS:
        value = int(raw, 0)
    elif kind == "R":
        value = int(raw) if raw.lstrip("+-").isdigit() else float(raw)
    elif kind == "SR":
        value = raw
    elif kind == "PR" and addr.member is not None:
        value = float(raw)
    elif kind == "PR":
        raise FanucError("Write position members one by one, e.g. PR[1].x=500 PR[1].y=0")
    elif kind == "$":
        dtype = dtype or "int"
        if dtype == "real":
            value = float(raw)
        elif dtype == "str":
            value = raw
        elif dtype == "pos":
            raise FanucError("POSITION system variables cannot be written from the CLI")
        else:
            value = _to_bool(raw) if dtype == "bool" else int(raw, 0)
    else:
        raise FanucError(f"{kind} cannot be written")
    return address, value


async def _run(args: argparse.Namespace) -> int:
    async with FanucClient(args.host, args.port, args.timeout) as robot:
        if args.command == "info":
            _emit(args, await robot.info())
        elif args.command == "status":
            status = await robot.status()
            if args.json:
                _emit(args, status)
            else:
                print(f"mode            {status.mode}")
                print(f"servo           {'ON' if status.servo_on else 'OFF'}")
                print(f"speed override  {status.speed_override}%")
                print(f"state           {', '.join(status.state_flags) or '-'}")
                print(f"protective stop {status.protective_stop}")
                print(f"alarms          {'; '.join(status.alarms) or '-'}")
                print(f"joints          {status.joint_positions}")
                print(f"uptime          {status.uptime_minutes} min")
                prog = await robot.program_status()
                print(f"program         {prog.program or '-'} line {prog.line} ({prog.state.name})")
        elif args.command == "read":
            results = {}
            for address in args.addresses:
                results[address] = await robot.read(address, args.count, args.type)
            _emit(args, results)
        elif args.command == "write":
            pairs: List[Tuple[str, Any]] = [parse_assignment(a, args.type) for a in args.assignments]
            for address, value in pairs:
                await robot.write(address, value, args.type)
                if not args.json:
                    print(f"{address} <- {_format(value)}")
            if args.json:
                _emit(args, {a: v for a, v in pairs})
        elif args.command == "watch":
            async for changed in robot.watch(args.addresses, args.interval):
                _emit(args, changed)
    return 0


def _emit(args: argparse.Namespace, value: Any) -> None:
    if args.json:
        print(json.dumps(to_jsonable(value)), flush=True)
    elif isinstance(value, dict):
        for k, v in value.items():
            print(f"{k} = {_format(v)}", flush=True)
    elif dataclasses.is_dataclass(value):
        for k, v in dataclasses.asdict(value).items():
            print(f"{k:<18}{v}")
    else:
        print(_format(value))


def _common_options(suppress: bool) -> argparse.ArgumentParser:
    # Added to the main parser and every subcommand so options work before or after
    # the subcommand; subcommand copies use SUPPRESS so they don't overwrite earlier values.
    def default(value: Any) -> Any:
        return argparse.SUPPRESS if suppress else value

    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--host", default=default(os.environ.get(HOST_ENV, ROBOGUIDE_HOST)),
                   help=f"controller IP (default: ${HOST_ENV} or {ROBOGUIDE_HOST} for ROBOGUIDE)")
    p.add_argument("--port", type=int, default=default(DEFAULT_PORT), help=f"OPC UA port (default {DEFAULT_PORT})")
    p.add_argument("--timeout", type=float, default=default(5.0), help="connection timeout in seconds")
    p.add_argument("--json", action="store_true", default=default(False), help="print JSON")
    return p


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fanuc-opcua",
        description="Read and write FANUC robot data over OPC UA.",
        epilog="Addresses: DO[1] DI[1] RO[1] F[1] UI[1] GI[1] GO[1] R[1] SR[1] PR[1] PR[1].x POS $MCR.$GENOVERRIDE",
        parents=[_common_options(suppress=False)],
    )
    common = _common_options(suppress=True)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("info", parents=[common], help="model, serial number and software version")
    sub.add_parser("status", parents=[common], help="mode, servo, program state, alarms")

    r = sub.add_parser("read", parents=[common], help="read one or more addresses")
    r.add_argument("addresses", nargs="+", metavar="ADDRESS")
    r.add_argument("-n", "--count", type=int, help="read COUNT consecutive items from each address")
    r.add_argument("-t", "--type", choices=list(SYSVAR_TYPES), help="data type of system variables (default int)")

    w = sub.add_parser("write", parents=[common], help="write ADDRESS=VALUE pairs")
    w.add_argument("assignments", nargs="+", metavar="ADDRESS=VALUE")
    w.add_argument("-t", "--type", choices=list(SYSVAR_TYPES), help="data type of system variables (default int)")

    m = sub.add_parser("watch", parents=[common], help="print values whenever they change (Ctrl+C to stop)")
    m.add_argument("addresses", nargs="+", metavar="ADDRESS")
    m.add_argument("-i", "--interval", type=float, default=0.5, help="poll interval in seconds")

    g = sub.add_parser("web", parents=[common], help="start the browser GUI (needs: pip install fanuc-opcua[web])")
    g.add_argument("--http-port", type=int, default=None, help="port of the GUI web page (default 8080, or the next free one)")
    g.add_argument("--bind", default="127.0.0.1",
                   help="interface to serve on; use 0.0.0.0 to allow other computers (no login!)")
    g.add_argument("--read-only", action="store_true", help="disable all writes in the GUI")
    g.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    return p


def _run_web(args: argparse.Namespace) -> int:
    try:
        from .web.server import run
    except ImportError as e:
        print(f"error: the GUI needs aiohttp ({e}). Install it with: pip install \"fanuc-opcua[web]\"",
              file=sys.stderr)
        return 1
    run(args.host, args.port, bind=args.bind, http_port=args.http_port,
        read_only=args.read_only, open_browser=not args.no_browser, timeout=args.timeout)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "web":
        return _run_web(args)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130
    except (FanucError, ValueError, TypeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
