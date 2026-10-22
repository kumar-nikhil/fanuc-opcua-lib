# fanuc-opcua

Read and write FANUC robot data — I/O, registers, position registers, string registers,
system variables and robot status — over the controller's **built-in OPC UA server**,
from Python or the command line. Tested against ROBOGUIDE (R-30iB Plus, V9.40P).

```python
import asyncio
from fanuc_opcua import FanucClient

async def main():
    async with FanucClient("127.0.0.2") as robot:      # ROBOGUIDE; use the robot IP for a real controller
        await robot.write("DO[1]", True)
        await robot.write("R[5]", 12.5)
        print(await robot.read("PR[1]"))
        print(await robot.status())

asyncio.run(main())
```

```bash
fanuc-opcua read DO[1] R[5] PR[1]
fanuc-opcua write DO[1]=on R[5]=12.5 PR[1].x=500
```

## Requirements

- A controller with the OPC UA server function (manual B-83284EN-2, chapter 55 *HMI Device
  Communication*): 7DF1 series P19 or later. Status nodes (`info()`, `status()`) need
  7DF1/P28+ or 7DF3/P06+. On a real robot with "North America setting" (R650) the
  *HMI device (R553)* option is required.
- ROBOGUIDE 7DF1 (V9.10) P24+ or 7DF3 (V9.30) P04+.
- Python 3.9+.

## Installation

From GitHub:

```bash
pip install git+https://github.com/kumar-nikhil/fanuc-opcua-lib.git
```

From a local checkout (with test dependencies):

```bash
pip install -e ".[dev]"
```

## Connecting

The server URL is `opc.tcp://<ip>:4880/FANUC/NanoUaServer`. There is no user name or password.

| Target | Host |
|---|---|
| Real controller | the robot's IP (CD38A or CD38B port; CD38C does not work) |
| ROBOGUIDE | **`127.0.0.2`**, not `127.0.0.1` |

ROBOGUIDE shows the port as "OPC UA Server" at the bottom of the window that opens when you
double-click the robot controller. Pass it as `FanucClient(host, port=...)` or `--port` if it is not 4880.

## Addresses

Addresses use the same names as the teach pendant.

| Address | Python type | Read | Write | Notes |
|---|---|---|---|---|
| `DO[n]` `RO[n]` `F[n]` | `bool` | ✓ | ✓ | |
| `DI[n]` `RI[n]` `UI[n]` `UO[n]` `SI[n]` `SO[n]` `WI[n]` `WSI[n]` | `bool` | ✓ | | inputs cannot be written over OPC UA |
| `WO[n]` `WSO[n]` | `bool` | ✓ | ✓ | |
| `GI[n]` `AI[n]` | `int` | ✓ | | |
| `GO[n]` `AO[n]` | `int` | ✓ | ✓ | |
| `R[n]` | `float` | ✓ | ✓ | write an `int` to store an integer, a `float` to store a real |
| `SR[n]` | `str` | ✓ | ✓ | up to 79 characters |
| `PR[n]`, `PR[Gg:n]` | `Position` | ✓ | ✓ | `Position`, or a dict of members |
| `PR[n].x` … `.r`, `.e1`–`.e3`, `.j1`–`.j9` | `float` | ✓ | ✓ | one member |
| `POS`, `POS[uf]`, `POS[Gg:uf]` | `Position` | ✓ | | current position; `uf` 0 = world, -1 = active user frame |
| `$VAR.$NAME` | per `dtype` | ✓ | ✓ | `dtype="int" \| "real" \| "bool" \| "str" \| "pos"` |

Read or write several consecutive items with `count` or a list:

```python
await robot.read("DO[1]", count=8)          # [False, True, ...]
await robot.write("DO[1]", [1, 0, 1])       # DO[1..3]
await robot.read("R[1]", count=10)          # [0.0, 12.5, ...]
```

Indexes that do not exist on the controller (for example `SR[30]` when only 25 string
registers are configured) read as 0/empty, and writes to them are ignored without an error.
That is how the controller behaves (manual 55.2.3).

## Python API

`FanucClient` is asynchronous. `FanucClientSync` has the same methods and blocks instead.

```python
from fanuc_opcua import FanucClient, FanucClientSync, Position

async with FanucClient(host, port=4880, timeout=5.0) as robot:
    await robot.read(address, count=None, dtype=None)
    await robot.write(address, value, dtype=None)
    await robot.read_many(["DO[1]", "R[1]", "PR[1].z"])   # {"DO[1]": False, ...}

    await robot.info()            # RobotInfo(model, serial_number, version, controller_model, software_revision)
    await robot.status()          # RobotStatus(mode, servo_on, speed_override, state, alarms, joint_positions, torque, ...)
    await robot.alarms()          # ["SRVO-001 Operator panel E-stop", ...]
    await robot.position(uframe=0, group=1)  # current position
    await robot.program_status(task=1)       # ProgramStatus(program, line, state, parent_program)

    async for changed in robot.watch(["DO[1]", "R[1]"], interval=0.5):
        print(changed)            # {"DO[1]": True}

with FanucClientSync(host) as robot:
    robot.write("DO[1]", True)
    for changed in robot.watch(["DO[1]"]):
        ...
```

`RobotStatus` has the properties `e_stop`, `running`, `paused`, `held`, `fault`, `tp_enabled` and `busy`.

### Position registers

```python
pr = await robot.read("PR[1]")
pr.x, pr.y, pr.z, pr.w, pr.p, pr.r     # cartesian part
pr.config                              # Config(flip, left, up, front, turn4..6), str() -> "N R U T, 0, 0, 0"
pr.joints                              # (j1, j2, ...) if it can be converted
pr.valid_cartesian, pr.valid_joint     # False when the register is uninitialized

await robot.write("PR[1]", Position.cartesian(500, 0, 400, 180, 0, 0))
await robot.write("PR[1]", Position.joint(0, 10, -20, 0, -70, 0))
await robot.write("PR[1]", {"z": 450})          # change some members, keep the rest
await robot.write("PR[1].x", 510.5)             # one member
```

> **Safety:** writing position registers and system variables changes what the robot
> program does. A position register locked with `LOCK PREG` ignores writes. Read back
> after writing, and test on ROBOGUIDE first.

## Command line

The `fanuc-opcua` command (also `python -m fanuc_opcua`) connects to `$FANUC_HOST`, or to
ROBOGUIDE at `127.0.0.2` when that is not set.

```bash
fanuc-opcua info
fanuc-opcua status
fanuc-opcua read DO[1] R[5] PR[1] PR[1].x SR[1]
fanuc-opcua read DO[1] -n 8                      # 8 consecutive items
fanuc-opcua read '$MCR.$GENOVERRIDE'
fanuc-opcua write DO[1]=on R[5]=3 R[6]=2.5 SR[1]="hello" PR[1].x=500
fanuc-opcua write '$SOME.$REAL_VAR=1.5' -t real
fanuc-opcua watch DO[1] UI[1] R[5] -i 0.2       # print changes until Ctrl+C
fanuc-opcua --host 192.168.1.10 --json read POS
```

Options such as `-n` and `--json` apply to every address on the line. Put them after the addresses.
Quote addresses that start with `$` in a POSIX shell.

## How it works

The controller exposes four Modbus-style arrays and a command node in namespace 1:

| Node | Id | Type | Contents |
|---|---|---|---|
| DiscreteInput | `ns=1;i=301` | Boolean[] | DI, RI, UI, UO, SI, SO, WI, WO, WSI, WSO (read only) |
| Coils | `ns=1;i=302` | Boolean[] | DO, RO, F |
| InputRegisters | `ns=1;i=303` | UInt16[] | GI, GO, AI, AO (read only) |
| HoldingRegisters | `ns=1;i=304` | Int16[] | robot data assigned by `$SNPX_ASG` or `SETASG` |
| Command | `ns=1;i=305` | String | `CLRASG` / `SETASG` commands |

I/O is read and written directly in the arrays, using an OPC UA *IndexRange* so only the
requested elements are sent. Registers, position registers, string registers, current
position, program status and system variables are not directly addressable. The library maps
them into the holding registers for the current connection with the dynamic assignment
commands (manual 55.4), for example `CLRASG` + `SETASG 1 50 PR[1] 0`, and then reads or writes
those words. Dynamic assignments replace the controller's `$SNPX_ASG` mapping for that connection
only. Other clients and the teach pendant settings are not affected.

Status information comes from the `RobotInformation` nodes (`ns=2;s=Model`, `ns=2;s=ModeState`, …)
and the OPC UA for Robotics `MotionDeviceSystem` nodes.

The raw arrays are available through `robot.transport` (`read_array`, `write_array`,
`read_holding`, `write_holding`, `write_command`).

### Controller limits

- Up to 10 OPC UA clients at a time.
- The server accepts one node per read or write request. The library sends one request per address.
- Typical response time is 3–18 ms but can be 100 ms or more under load. Use the
  *High Speed Position Output* function for real-time position streaming.

## Testing

```bash
pytest                                     # unit tests, no robot needed
FANUC_TEST_HOST=127.0.0.2 pytest -m roboguide   # live tests against ROBOGUIDE
```

The live tests write to DO[100], F[100], R[100]–R[102], SR[20] and PR[100], and restore the
original values afterwards. Do not run them against a production robot.

## Changes in 0.2

0.2 replaces the 0.1 API (`robot.robot_info.get_model()`, `robot.io.get_digital_input(1)`,
`robot.registers.read_holding_register(...)`) with `read()` / `write()` on addresses:

| 0.1 | 0.2 |
|---|---|
| `robot.robot_info.get_model()` | `(await robot.info()).model` |
| `robot.robot_info.get_active_alarms()` | `await robot.alarms()` |
| `robot.io.get_digital_input(1)` | `await robot.read("DI[1]")` |
| `robot.io.get_uop_input(1)` | `await robot.read("UI[1]")` |
| `robot.registers.get_group_input(1)` | `await robot.read("GI[1]")` |
| `robot.registers.read_holding_register(1, "int16")` | `await robot.read("R[1]")` |
