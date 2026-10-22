"""
Step-by-step connection test shown in the GUI before switching robots:
ping, TCP port, then a real OPC UA session that reads the robot model.
Each failed step carries a hint about the usual cause.
"""
from __future__ import annotations

import asyncio
import locale
import re
import sys
import time
from typing import Any, Dict, Optional

from ..client import FanucClient
from ..errors import FanucError

_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,252}$")
_PING_MS_RE = re.compile(r"[=<]\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE)


def validate_host(host: str) -> str:
    """Accept an IPv4 address or host name; reject anything else (it is passed to ping)."""
    host = (host or "").strip()
    if not _HOST_RE.match(host):
        raise ValueError(f"Not a valid IP address or host name: {host!r}")
    return host


def _step(name: str, ok: Optional[bool], ms: Optional[float], detail: str, hint: str = "") -> Dict[str, Any]:
    return {"name": name, "ok": ok, "ms": None if ms is None else round(ms, 1), "detail": detail,
            "hint": "" if ok else hint}


async def ping(host: str, timeout: float = 1.0) -> Dict[str, Any]:
    """One ICMP echo with the system ping command. ok=None when ping is not available."""
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
        flags = {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout))), host]
        flags = {}
    start = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, **flags)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout + 3)
    except (OSError, asyncio.TimeoutError) as e:
        return _step("Ping", None, None, f"ping could not run ({type(e).__name__}); skipped")
    elapsed = (time.perf_counter() - start) * 1000
    text = out.decode(locale.getpreferredencoding(False), errors="replace")
    # Windows ping exits 0 even for "Destination host unreachable"; a real reply has a TTL.
    if proc.returncode == 0 and "ttl=" in text.lower():
        m = _PING_MS_RE.search(text)
        ms = float(m.group(1).replace(",", ".")) if m else elapsed
        return _step("Ping", True, ms, f"{host} replied")
    return _step(
        "Ping", False, None, f"no reply from {host}",
        "Check the IP address, that this PC is on the robot's subnet (for example 192.168.1.x with mask "
        "255.255.255.0), that the cable is on port CD38A or CD38B, and that Wi-Fi is not taking the traffic. "
        "Some networks block ping, so the next checks still run.")


async def tcp_port(host: str, port: int, timeout: float = 3.0) -> Dict[str, Any]:
    """Open and close a TCP connection to the OPC UA port."""
    start = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except ConnectionRefusedError:
        return _step(
            "OPC UA port", False, None, f"{host} refused port {port}",
            f"The computer answered but nothing listens on port {port}. The OPC UA server is not available "
            "(needs software 7DF1/P19 or later; with the North America setting also option R553) or the port "
            "is different. In ROBOGUIDE use 127.0.0.2 and the port shown in the controller window.")
    except (OSError, asyncio.TimeoutError) as e:
        return _step(
            "OPC UA port", False, None, f"no answer on port {port} ({type(e).__name__})",
            f"Nothing answered on port {port} within {timeout:g} s: wrong IP, robot switched off, or a firewall "
            "or VLAN between this PC and the robot blocks the port.")
    ms = (time.perf_counter() - start) * 1000
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return _step("OPC UA port", True, ms, f"port {port} is open")


async def opcua_session(host: str, port: int, timeout: float = 5.0) -> Dict[str, Any]:
    """Open a separate OPC UA session and read the robot model, then close it."""
    start = time.perf_counter()
    client = FanucClient(host, port, timeout)
    try:
        await client.connect()
        try:
            info = await client.info()
            model, version = info.model, info.version
        except FanucError:
            # Software older than 7DF1/P28 has no RobotInformation nodes.
            model = await client.read("$SCR_GRP[1].$ROBOT_MODEL", dtype="str")
            version = await client.read("$VERSION", dtype="str")
    except Exception as e:  # noqa: BLE001 - report any failure as a test result
        return _step(
            "OPC UA session", False, None, f"{type(e).__name__}: {e}",
            "The port is open but the OPC UA session failed. Check that this is a FANUC controller with the "
            "OPC UA server function, and that fewer than 10 clients are already connected.")
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    ms = (time.perf_counter() - start) * 1000
    return _step("OPC UA session", True, ms, f"{model or 'FANUC robot'} · {version or ''}".strip(" ·"))


async def run_test(host: str, port: int, timeout: float = 5.0) -> Dict[str, Any]:
    """Run all steps. The OPC UA session is only tried when the port is open."""
    host = validate_host(host)
    if not 1 <= int(port) <= 65535:
        raise ValueError(f"Port must be 1..65535, got {port}")
    steps = [await ping(host), await tcp_port(host, port, min(timeout, 3.0))]
    if steps[1]["ok"]:
        steps.append(await opcua_session(host, port, timeout))
    else:
        steps.append(_step("OPC UA session", None, None, "skipped because the port is not open"))
    return {"host": host, "port": port, "passed": bool(steps[1]["ok"] and steps[2]["ok"]), "steps": steps}
