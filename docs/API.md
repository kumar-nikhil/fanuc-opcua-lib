# fanuc-opcua Python API Reference

Version 0.3.0 · Python library API. For the command line and the browser GUI see the [README](../README.md).

**Contents:** [Overview](#overview) · [Addresses](#addresses) · [FanucClient](#fanucclient) ·
[Robot state](#robot-state) · [FanucClientSync](#fanucclientsync) · [Data types](#data-types) ·
[Errors](#errors) · [Limits and safety](#limits-and-safety)

## Overview

`fanuc_opcua` reads and writes FANUC robot data (I/O, registers, position registers, string registers,
system variables and robot status) through the controller's built-in OPC UA server, using teach-pendant
addresses such as `DO[1]`, `R[5]` or `PR[1].x`. It is tested against ROBOGUIDE on an R-30iB Plus with
software V9.40P.

```python
import asyncio
from fanuc_opcua import FanucClient

async def main():
    async with FanucClient("192.168.1.10") as robot:
        await robot.write("DO[1]", True)
        await robot.write("R[5]", 12.5)
        print(await robot.read("PR[1]"))
        print((await robot.status()).state_flags)

asyncio.run(main())
```

### Install

| What | Command |
| --- | --- |
| Library | `pip install git+https://github.com/kumar-nikhil/fanuc-opcua-lib.git` |
| A specific release | append `@v0.2.0` (or a later tag) to the URL |
| Import name | `import fanuc_opcua` (package name `fanuc-opcua`) |

Requires Python 3.9 or later and `asyncua` 1.0.5 or later (installed automatically).

### Controller requirements

| Requirement | Detail |
| --- | --- |
| OPC UA server function | Software 7DF1 series P19 or later (FANUC manual B-83284EN-2, chapter 55) |
| Status nodes used by `info()` and `status()` | 7DF1/P28 or later, or 7DF3/P06 or later |
| Option with North America setting (R650) | HMI Device (R553) |
| Ethernet port | CD38A or CD38B; CD38C does not support OPC UA |
| ROBOGUIDE | 7DF1 (V9.10) P24+ or 7DF3 (V9.30) P04+ |

### Connecting

The server URL is `opc.tcp://<host>:4880/FANUC/NanoUaServer`, with no user name or password. Pass only
the host (and port if it is not 4880); the library builds the URL.

| Target | Host |
| --- | --- |
| Real controller | the robot's IP address, for example `192.168.1.10` |
| ROBOGUIDE | `127.0.0.2` (not `127.0.0.1`); available as `fanuc_opcua.ROBOGUIDE_HOST` |

The PC must be on the robot's subnet and allow outgoing TCP port 4880.

## Addresses

Every read and write takes a teach-pendant address string; letters are case-insensitive and spaces around
it are ignored.

| Address | Index range | Python type | Read | Write | Notes |
| --- | --- | --- | --- | --- | --- |
| `DO[n]` `RO[n]` | 1–10000 | `bool` | yes | yes | Digital / robot outputs |
| `F[n]` | 1–10000 | `bool` | yes | yes | Flags |
| `DI[n]` `RI[n]` | 1–10000 | `bool` | yes | no | Inputs cannot be written over OPC UA |
| `UI[n]` | 1–1000 | `bool` | yes | no | UOP inputs |
| `UO[n]` | 1–999 | `bool` | yes | no | UOP outputs |
| `SI[n]` | 0–999 | `bool` | yes | no | SOP inputs (start at 0) |
| `SO[n]` | 0–1000 | `bool` | yes | no | SOP outputs (start at 0) |
| `WI[n]` `WSI[n]` | 1–1000 | `bool` | yes | no | Weld / wire-stick inputs |
| `WO[n]` `WSO[n]` | 1–1000 | `bool` | yes | yes | Weld / wire-stick outputs |
| `GI[n]` `AI[n]` | 1–1000 | `int` | yes | no | Group / analog inputs |
| `GO[n]` `AO[n]` | 1–1000 | `int` | yes | yes | Group / analog outputs, 0–65535 |
| `R[n]` | 1–10000 | `float` | yes | yes | Write an `int` to store an integer, a `float` to store a real |
| `SR[n]` | 1–10000 | `str` | yes | yes | Up to 79 characters |
| `PR[n]`, `PR[Gg:n]` | 1–10000 | `Position` | yes | yes | Group prefix `G2:` for motion group 2 |
| `PR[n].x` | 1–10000 | `float` | yes | yes | One member: `x y z w p r`, `e1`–`e3`, `j1`–`j9` |
| `POS`, `POS[uf]`, `POS[Gg:uf]` | uf −1–61 | `Position` | yes | no | Current position; `uf` 0 = world (default), −1 = active user frame |
| `POS.z`, `POS[uf].x` | | `float` | yes | no | One member of the current position |
| `$VAR.$NAME` | | per `dtype` | yes | yes | System variable, e.g. `$MCR.$GENOVERRIDE` |

The index ranges are the library's limits; the controller may have fewer (for example 25 string registers
by default). An index or system variable that does not exist on the controller reads as 0 or an empty
string, and writes to it are ignored without an error.

### Several items at once

Pass `count` to read consecutive items, or a list to write them:

```python
await robot.read("DO[1]", count=8)       # [False, True, False, ...]
await robot.read("R[1]", count=10)       # [0.0, 12.5, ...]
await robot.read("PR[1]", count=5)       # [Position, Position, ...]
await robot.write("DO[1]", [1, 0, 1])    # DO[1], DO[2], DO[3]
await robot.write("R[1]", [1, 2, 3])     # R[1..3] as integers
```

`count` works for I/O, `R`, `SR` and `PR` (not for `POS`, members such as `PR[1].x`, or system variables)
and may not run past the last index of that type.

## FanucClient

`FanucClient` is the asynchronous client; every method below is a coroutine and must be awaited. One
instance holds one OPC UA session.

### Constructor

```python
FanucClient(host: str, port: int = 4880, timeout: float = 5.0)
```

| Parameter | Meaning |
| --- | --- |
| `host` | Robot IP or host name; `127.0.0.2` for ROBOGUIDE |
| `port` | OPC UA port (default 4880) |
| `timeout` | Seconds to wait for the connection and each request |

Attributes: `host`, `port`, `timeout`, `endpoint` (the full `opc.tcp://` URL), `connected` (bool) and
`transport` (low-level access, see below).

### Connecting

```python
async with FanucClient("192.168.1.10") as robot:   # connects, then disconnects on exit
    ...

robot = FanucClient("192.168.1.10")
await robot.connect()        # raises FanucConnectionError if the server cannot be reached
await robot.disconnect()     # safe to call when already disconnected
```

Calling any other method before `connect()` raises `NotConnectedError`. `connect()` on an already
connected client does nothing.

### read

```python
await robot.read(address, count=None, dtype=None)
```

Returns one value, or a list of `count` values when `count` is given (even `count=1`). The type follows
the address table: `bool`, `int`, `float`, `str` or `Position`.

| Parameter | Meaning |
| --- | --- |
| `address` | A teach-pendant address string, e.g. `"UI[1]"`, `"PR[3].z"`, `"$MCR.$GENOVERRIDE"` |
| `count` | Number of consecutive items to read |
| `dtype` | System variables only: `"int"` (default), `"real"`, `"bool"`, `"str"` or `"pos"`; must match the variable's type on the controller |

```python
await robot.read("DO[1]")                          # True
await robot.read("UI[1]", count=8)                 # [True, True, True, False, ...]
await robot.read("R[5]")                           # 12.5
await robot.read("SR[1]")                          # 'hello'
await robot.read("PR[1].x")                        # 500.0
await robot.read("$MCR.$GENOVERRIDE")              # 100
await robot.read("$GROUP[1].$SPEED", dtype="real") # 300.0
```

Raises `AddressError` for an invalid address, index, `count` or `dtype`, and `CommunicationError` when the
controller rejects the request.

### read_many

```python
await robot.read_many(["DO[1]", "R[1]", "PR[1].z"])
# {'DO[1]': False, 'R[1]': 0.0, 'PR[1].z': 400.0}
```

Reads each address in turn and returns a dict keyed by the address strings as given. The first error stops
the call.

### write

```python
await robot.write(address, value, dtype=None)
```

Writes one value, or consecutive values when `value` is a list. Returns `None`.

| Address type | Accepted `value` |
| --- | --- |
| `DO` `RO` `F` `WO` `WSO` | `True`/`False`, `1`/`0`, or `"on"`/`"off"`/`"true"`/`"false"` |
| `GO` `AO` | whole number 0–65535 (or −32768–32767) |
| `R` | `int` stores an integer register, `float` a real; a list of all ints is written as integers |
| `SR` | `str`, at most 79 characters |
| `PR[n]` | a `Position`, or a dict of members such as `{"z": 450}` (only those members change) |
| `PR[n].x` etc. | a number |
| `$VAR` | a value matching `dtype`: `int` (default), `real`, `bool`, `str` or `pos` (a `Position` or member dict) |

```python
await robot.write("DO[1]", True)
await robot.write("DO[1]", [1, 0, 1])                       # DO[1..3]
await robot.write("GO[1]", 42)
await robot.write("R[5]", 3)                                # integer register
await robot.write("R[5]", 2.5)                              # real register
await robot.write("SR[1]", "hello")
await robot.write("PR[1]", Position.cartesian(500, 0, 400, 180, 0, 0))
await robot.write("PR[1]", Position.joint(0, 10, -20, 0, -70, 0))
await robot.write("PR[1]", {"z": 450})
await robot.write("PR[1].x", 510.5)
await robot.write("$MCR.$GENOVERRIDE", 50)
```

Raises `ReadOnlyError` for inputs and `POS`, `ValueError` for a value of the wrong kind (e.g. `2` for a DO,
`1.5` for a GO, an 80-character string), `AddressError` for a dict that mixes joint and cartesian members,
and `CommunicationError` when the controller rejects the request.

### transport (advanced)

`robot.transport` gives raw access to the Modbus-style arrays: `read_array(node_id, start, count)`,
`write_array(node_id, start, values, variant_type)`, `read_holding(start, count)`,
`write_holding(start, words)`, `read_value(node_id)` and `write_command(text)`. Node ids are in
`fanuc_opcua.nodes.ModbusNodes`. Most users never need it.

## Robot state

These `FanucClient` methods return ready-made objects for the information an operator usually wants;
their types are described under [Data types](#data-types).

| Method | Returns | Needs status nodes |
| --- | --- | --- |
| `await robot.info()` | `RobotInfo` — model, serial number, software version, controller model | yes |
| `await robot.status()` | `RobotStatus` — mode, servo, speed override, state flags, alarms, joints, torque, uptime | yes |
| `await robot.alarms()` | `list[str]` of active alarms, e.g. `['SRVO-001 Operator panel E-stop']`; empty when none | yes |
| `await robot.position(uframe=0, group=1)` | `Position` of the current position; `uframe` −1 = active user frame, 0 = world, 1–61 = that user frame | no |
| `await robot.program_status(task=1)` | `ProgramStatus` — program name, line, state, parent program of that task | no |
| `robot.watch(addresses, interval=0.5)` | async iterator of `dict` with the values that changed | no |

"Needs status nodes" means the controller must have software 7DF1/P28+ or 7DF3/P06+; on older software those
methods raise `CommunicationError`, while the rest of the API works.

```python
info = await robot.info()
print(info.model, info.software_revision)       # CRX-10iA/L 7DF5/89 (V9.40P/89 )

status = await robot.status()
if status.fault:
    print("Alarms:", status.alarms)
print(status.mode, status.speed_override, status.state_flags)   # Auto 100 ['PAUSED', 'FAULT']

here = await robot.position()                   # world frame
print(here.x, here.y, here.z, here.config)

prog = await robot.program_status()
print(prog.program, prog.line, prog.state.name) # MAIN 12 RUNNING
```

### watch

`watch()` polls the addresses every `interval` seconds. The first item it yields contains every value;
after that it yields only the addresses whose value changed. It runs until you stop iterating.

```python
async for changed in robot.watch(["DO[1]", "R[1]", "PR[1].x"], interval=0.5):
    print(changed)              # {'DO[1]': True}
    if changed.get("DO[1]") is False:
        break
```

It uses polling rather than OPC UA subscriptions, so it works for every address type, including registers
and position registers.

## FanucClientSync

`FanucClientSync` has the same methods as `FanucClient` but blocks until each one finishes, for scripts that
do not use `asyncio`. It runs a `FanucClient` on a background thread.

```python
from fanuc_opcua import FanucClientSync

with FanucClientSync("192.168.1.10") as robot:
    robot.write("DO[1]", True)
    print(robot.read("R[1]", count=5))
    print(robot.status().state_flags)
    for changed in robot.watch(["DO[1]", "R[1]"], interval=0.5):
        print(changed)
```

| Member | Notes |
| --- | --- |
| `FanucClientSync(host, port=4880, timeout=5.0)` | Same parameters as `FanucClient` |
| `connect()`, `disconnect()` | As in `FanucClient` |
| `close()` | Disconnects and stops the background thread; called by `with` on exit |
| `read`, `read_many`, `write` | Same parameters and results, no `await` |
| `info`, `status`, `alarms`, `position`, `program_status` | Same results, no `await` |
| `watch(addresses, interval=0.5)` | A normal generator; stop it with `break` or Ctrl+C |
| `endpoint`, `connected` | Read-only properties |

Without `with`, call `close()` when done so the background thread ends. Do not call `FanucClientSync`
methods from inside a running asyncio event loop; use `FanucClient` there.

## Data types

All types are importable from `fanuc_opcua` and are plain dataclasses or enums.

### Position

A position register, current position or POSITION system variable. A read fills both representations when
the controller can convert them.

| Field | Type | Meaning |
| --- | --- | --- |
| `x` `y` `z` | `float` | Cartesian position, mm |
| `w` `p` `r` | `float` | Orientation, degrees |
| `ext` | `tuple` of 3 `float` | Extended axes E1–E3 |
| `config` | `Config` | Arm configuration |
| `joints` | `tuple` of `float` or `None` | J1–J6, up to J9 when extra axes are non-zero; degrees or mm |
| `uf`, `ut` | `int` | User and tool frame; −1 (shown as F) for position registers |
| `valid_cartesian`, `valid_joint` | `bool` | `False` when that part is uninitialized or cannot be converted |
| `representation` | `str` | `"cartesian"` or `"joint"`: which part a write sends |
| `xyzwpr` | property | `(x, y, z, w, p, r)` |

Build one to write with `Position.cartesian(x, y, z, w, p, r, config=None, ext=())` or
`Position.joint(j1, j2, ...)` (1 to 9 values). Values read back are rounded to 7 significant digits, so
`538.1` reads as `538.1`, not `538.0999755859375`. `str(position)` prints both representations, or
`<uninitialized position>`.

### Config

| Field | Default | Meaning |
| --- | --- | --- |
| `flip` | `False` | F (flip) or N (no flip) |
| `left` | `False` | L (left) or R (right) |
| `up` | `True` | U (up) or D (down) |
| `front` | `True` | T (front) or B (back) |
| `turn4` `turn5` `turn6` | `0` | Turn numbers of J4–J6 (−128 to 127) |

`str(config)` gives the teach-pendant form, e.g. `N R U T, 0, 0, 0`.

### RobotInfo

| Field | Type | Example |
| --- | --- | --- |
| `model` | `str` | `CRX-10iA/L` |
| `serial_number` | `str` | `F00000` |
| `version` | `str` | `7DF5/89` |
| `controller_model` | `str` or `None` | `R-30iB Plus` |
| `software_revision` | `str` or `None` | `7DF5/89 (V9.40P/89 )` |

### RobotStatus

| Field | Type | Meaning |
| --- | --- | --- |
| `mode` | `str` | `"Auto"`, `"T1"` or `"T2"` |
| `servo_on` | `bool` | Servo power on |
| `speed_override` | `int` | Speed override, % |
| `state` | `OperationState` | Bit flags, see below |
| `alarms` | `list[str]` | Active alarms |
| `joint_positions` | `list[float]` | Group 1, up to 6 axes |
| `torque` | `list[float]` | Q-phase motor current per axis, A |
| `uptime_minutes` | `int` | Total power-on time, minutes |
| `protective_stop` | `bool` or `None` | Fence, deadman, overtravel and similar stops; `None` when not reported |

Properties: `state_flags` (list of set flag names, e.g. `['PAUSED', 'FAULT']`), and `e_stop`, `running`,
`paused`, `held`, `fault`, `tp_enabled`, `busy` (each a `bool`).

### OperationState

An `enum.IntFlag`; `RobotStatus.state` is the sum of the set bits.

| Flag | Value | Set when |
| --- | --- | --- |
| `E_STOP` | 1 | Any emergency stop (SOP, TP or external) is pressed |
| `ABORTED` | 2 | No program running and none paused |
| `RUNNING` | 4 | A program is running (UO PROGRUN) |
| `PAUSED` | 8 | A program is paused |
| `HELD` | 16 | Hold is active |
| `FAULT` | 32 | An alarm is active |
| `TP_ENABLED` | 64 | The teach pendant is enabled |
| `BATTERY_ALARM` | 128 | Battery alarm |
| `BUSY` | 256 | The controller is busy |

### ProgramStatus and ExecutionState

| Field | Type | Meaning |
| --- | --- | --- |
| `program` | `str` | Running program, or the sub-program when one is called; empty when aborted |
| `line` | `int` | Executing line |
| `state` | `ExecutionState` | `ABORTED` (0), `PAUSED` (1) or `RUNNING` (2) |
| `parent_program` | `str` | The program that was started |

## Errors

Every error the library raises on purpose derives from `FanucError`, so one `except FanucError` handles
them all.

| Exception | Also a | Raised when |
| --- | --- | --- |
| `FanucError` | `Exception` | Base class of all the errors below |
| `FanucConnectionError` | `ConnectionError` | `connect()` could not reach the OPC UA server |
| `NotConnectedError` | | A method was called before `connect()` or after `disconnect()` |
| `AddressError` | `ValueError` | Bad address, index, `count` or `dtype` |
| `ReadOnlyError` | | `write()` to an input (DI, UI, GI and so on) or to `POS` |
| `CommunicationError` | | The controller rejected a request; `.status` holds the OPC UA status name |

A value of the wrong kind in `write()` (for example `2` for a DO or text for an `R`) raises a plain
`ValueError` or `TypeError`, not a `FanucError`. `CommunicationError.status` holds the OPC UA status name,
such as `BadWriteNotSupported`.

```python
import asyncio
from fanuc_opcua import FanucClient, FanucError, FanucConnectionError, ReadOnlyError

async def main():
    try:
        async with FanucClient("192.168.1.10") as robot:
            await robot.write("DI[1]", True)
    except FanucConnectionError as e:
        print("Robot not reachable:", e)
    except ReadOnlyError as e:
        print("Not writable:", e)          # DI cannot be written over OPC UA
    except FanucError as e:
        print("Other robot error:", e)

asyncio.run(main())
```

## Limits and safety

| Topic | What to know |
| --- | --- |
| Clients | The controller accepts at most 10 OPC UA clients at a time |
| Speed | One request per address (the server reads one node per request); typically 3–18 ms on a real controller, 100 ms or more under load, about 1 ms on ROBOGUIDE |
| Real-time motion | Not suitable for streaming positions; use FANUC's High Speed Position Output function |
| Registers and positions | Reached by mapping them into holding registers for your session only (`CLRASG`/`SETASG`); other clients and the controller's `$SNPX_ASG` settings are not changed |
| Silent no-ops | Indexes or system variables that do not exist read as 0 and ignore writes; a position register locked with `LOCK PREG` ignores writes |
| Output writes | DO/RO writes switch the real outputs wired to them; a running program may overwrite them |
| Position and system variable writes | Change what robot programs do; read back after writing and test on ROBOGUIDE first |

### Example: log robot state every second

```python
import asyncio, csv, time
from fanuc_opcua import FanucClient, FanucError

async def main():
    with open("robot_log.csv", "w", newline="") as f:
        log = csv.writer(f)
        log.writerow(["time", "mode", "flags", "program", "line", "x", "y", "z", "alarms"])
        async with FanucClient("192.168.1.10") as robot:
            while True:
                status = await robot.status()
                prog = await robot.program_status()
                pos = await robot.position()
                log.writerow([time.strftime("%H:%M:%S"), status.mode, "|".join(status.state_flags),
                              prog.program, prog.line, pos.x, pos.y, pos.z, "; ".join(status.alarms)])
                f.flush()
                await asyncio.sleep(1)

try:
    asyncio.run(main())
except FanucError as e:
    print("Robot error:", e)
```

### Example: hand-shake with a robot program (blocking)

```python
from fanuc_opcua import FanucClientSync, Position

with FanucClientSync("192.168.1.10") as robot:
    robot.write("PR[10]", Position.cartesian(500, 0, 300, 180, 0, 0))   # target for the TP program
    robot.write("R[20]", 1)                                            # request: program waits for R[20]=1
    for changed in robot.watch(["R[20]"], interval=0.2):
        if changed.get("R[20]") == 0:                                   # program resets R[20] when done
            print("Robot finished the move")
            break
```
