# fanuc-opcua

Read and write FANUC robot data — I/O, registers, position registers, string registers,
system variables and robot status — over the controller's **built-in OPC UA server**.
Tested against ROBOGUIDE (R-30iB Plus, V9.40P).

There are three ways to use it:

| | For | Start with |
|---|---|---|
| [**Python API**](#python-api) | scripts, cell controllers, data logging | `from fanuc_opcua import FanucClient` |
| [**Command line**](#command-line) | quick checks and shell scripts | `fanuc-opcua read DO[1] R[5]` |
| [**Browser GUI**](#browser-gui) | beginners, commissioning, customer demos | `fanuc-opcua web` |
| [**Windows .exe**](#standalone-windows-exe) | any Windows PC, nothing to install | double-click `FANUC-OPCUA.exe` |

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

**Contents:** [Requirements](#requirements) · [Installation](#installation) · [Connecting](#connecting) ·
[Addresses](#addresses) · [Python API](#python-api) · [Command line](#command-line) ·
[Browser GUI](#browser-gui) · [Standalone .exe](#standalone-windows-exe) · [How it works](#how-it-works) ·
[Testing](#testing) · [Changes](#changes)

## Requirements

- A controller with the OPC UA server function (manual B-83284EN-2, chapter 55 *HMI Device
  Communication*): 7DF1 series P19 or later. Status nodes (`info()`, `status()`) need
  7DF1/P28+ or 7DF3/P06+. On a real robot with "North America setting" (R650) the
  *HMI device (R553)* option is required.
- ROBOGUIDE 7DF1 (V9.10) P24+ or 7DF3 (V9.30) P04+.
- Python 3.9+.

## Installation

| What you need | Command |
|---|---|
| Library and command line | `pip install git+https://github.com/kumar-nikhil/fanuc-opcua-lib.git` |
| Plus the browser GUI | `pip install "fanuc-opcua[web] @ git+https://github.com/kumar-nikhil/fanuc-opcua-lib.git"` |
| A specific release | add the tag after `.git`, e.g. `...fanuc-opcua-lib.git@v0.2.0` |
| Development (local checkout) | `pip install -e ".[dev,web]"` |

On Windows, if `fanuc-opcua` is "not recognized" in a terminal where the virtual environment is not
activated, call it by path, for example `.venv\Scripts\fanuc-opcua.exe web`.

## Connecting

The server URL is `opc.tcp://<ip>:4880/FANUC/NanoUaServer`. There is no user name or password.

| Target | Host |
|---|---|
| Real controller | the robot's IP (CD38A or CD38B port; CD38C does not work) |
| ROBOGUIDE | **`127.0.0.2`**, not `127.0.0.1` |

ROBOGUIDE shows the port as "OPC UA Server" at the bottom of the window that opens when you
double-click the robot controller. Pass it as `FanucClient(host, port=...)` or `--port` if it is not 4880.

For a real robot the PC must be on the robot's subnet (check with `ping <robot-ip>`), TCP/IP must be
set up on the controller, and the PC firewall must allow outgoing TCP port 4880.

## Addresses

Addresses use the same names as the teach pendant. The Python API, command line and GUI all accept them.

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

Indexes that do not exist on the controller (for example `SR[30]` when only 25 string
registers are configured), and misspelled system variable names, read as 0/empty and writes
to them are ignored without an error. That is how the controller behaves (manual 55.2.3).

## Python API

`FanucClient` is asynchronous (`asyncio`). `FanucClientSync` has exactly the same methods and
blocks instead, for scripts that do not use `asyncio`.

The full reference — every method, parameter, data type and error — is in **[docs/API.md](docs/API.md)**.

### Connect

```python
from fanuc_opcua import FanucClient, FanucClientSync, Position, FanucError

async with FanucClient("192.168.1.10", port=4880, timeout=5.0) as robot:
    ...                                   # connected here, disconnected afterwards

robot = FanucClient("127.0.0.2")          # or manage the connection yourself
await robot.connect()
await robot.disconnect()
```

### Read and write

```python
await robot.read("DO[1]")                    # True
await robot.read("UI[1]", count=8)           # [True, True, True, False, ...]
await robot.read("R[5]")                     # 12.5
await robot.read("SR[1]")                    # "hello"
await robot.read("$MCR.$GENOVERRIDE")        # 100   (system variables default to dtype="int")
await robot.read("$GROUP[1].$SPEED", dtype="real")
await robot.read_many(["DO[1]", "R[1]", "PR[1].z"])   # {"DO[1]": False, "R[1]": 0.0, "PR[1].z": 400.0}

await robot.write("DO[1]", True)             # also 1/0 or "on"/"off"
await robot.write("DO[1]", [1, 0, 1])        # DO[1..3]
await robot.write("GO[1]", 42)
await robot.write("R[5]", 3)                 # integer register
await robot.write("R[5]", 2.5)               # real register
await robot.write("R[1]", [1, 2, 3])         # R[1..3]
await robot.write("SR[1]", "hello")
await robot.write("$MCR.$GENOVERRIDE", 50)
```

### Position registers and current position

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

here = await robot.position()                   # current position, world frame
here = await robot.position(uframe=-1)          # in the active user frame
z = await robot.read("POS.z")
```

> **Safety:** writing position registers and system variables changes what the robot
> program does. A position register locked with `LOCK PREG` ignores writes. Read back
> after writing, and test on ROBOGUIDE first.

### Robot state

```python
info = await robot.info()           # RobotInfo(model, serial_number, version, controller_model, software_revision)
status = await robot.status()       # RobotStatus(mode, servo_on, speed_override, state, alarms,
                                    #             joint_positions, torque, uptime_minutes, protective_stop)
status.state_flags                  # ["PAUSED", "FAULT"]
status.e_stop, status.running, status.paused, status.held, status.fault, status.tp_enabled, status.busy
await robot.alarms()                # ["SRVO-001 Operator panel E-stop", ...]
prog = await robot.program_status() # ProgramStatus(program="MAIN", line=12, state=RUNNING, parent_program="MAIN")
```

### Watch for changes

```python
async for changed in robot.watch(["DO[1]", "R[1]", "PR[1].x"], interval=0.5):
    print(changed)                  # first all values, then only what changed: {"DO[1]": True}
```

### Without asyncio

```python
with FanucClientSync("127.0.0.2") as robot:
    robot.write("DO[1]", True)
    print(robot.read("R[1]", count=5))
    print(robot.status().state_flags)
    for changed in robot.watch(["DO[1]"]):
        print(changed)
```

### Errors

All errors derive from `FanucError`: `FanucConnectionError` (server not reachable),
`AddressError` (bad address or count, also a `ValueError`), `ReadOnlyError` (e.g. writing `DI[1]`),
`CommunicationError` (the server rejected a request) and `NotConnectedError`.

More examples: [`examples/quickstart.py`](examples/quickstart.py),
[`examples/sync_quickstart.py`](examples/sync_quickstart.py),
[`examples/dump_robot_data.py`](examples/dump_robot_data.py).

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
fanuc-opcua --json status                        # includes "state_flags": ["PAUSED", "FAULT"]
fanuc-opcua web                                  # start the browser GUI, see below
```

Options such as `-n` and `--json` apply to every address on the line. Put them after the addresses.
Quote addresses that start with `$` in a POSIX shell.

## Browser GUI

A local web page for beginners, commissioning and customer demos. It needs the optional `web`
extra (see [Installation](#installation)) and no internet connection.

### Start and stop

```bash
fanuc-opcua web                           # ROBOGUIDE at 127.0.0.2, opens http://127.0.0.1:8080
fanuc-opcua web --host 192.168.1.10       # a real controller
fanuc-opcua web --read-only               # nothing can be written, whatever is clicked
fanuc-opcua web --http-port 8081          # if port 8080 is taken
fanuc-opcua web --no-browser              # do not open a browser window
```

Press **Ctrl+C** in the terminal to stop it. After updating the library, restart the GUI and refresh
the browser — refreshing alone keeps the old server running.

### The screen

- **Header** — robot IP and port with **Test**, **Connect** / **Disconnect**, a green/red connection
  indicator, and the **Writes locked** switch. See [Switching robots](#switching-robots).
- **Robot** — model, controller, software version, serial number and power-on time.
- **Status** — mode, servo, e-stop, protective stop and colored state flags (RUNNING, PAUSED, FAULT, …).
  Active alarms appear in a red banner at the top of the page.
- **Speed override** — the current value, and a slider with **Set** to change it.
- **Program** — the running program, its line and state.
- **Communication** — last, average and max request time, dashboard refresh time, requests per second,
  read/write/error counts, and a chart of recent requests (below).
- **Current position** — XYZWPR, J1–J6 and configuration, plus motor current per axis.
- **Read & write** tab — choose *What to access* (every address type), an index and a count, then
  **Read**. Writable items get a matching input: ON/OFF, a number, text, or position fields with
  *Fill with current position*. For system variables, pick from a list of 25 checked variables grouped
  by Speed, Frames, Operation, Controller and OPC UA, or choose *Custom name…*.
- **I/O panel** tab — 16 to 64 signals as LEDs, refreshed twice a second. Click an output to toggle it.
- **Watch list** tab — any addresses, refreshed every second, with changes highlighted. *Add demo set*
  fills in a typical set. The list is remembered by the browser.
- **Activity log** tab — every read and write made from the page, with its timing.

### Switching robots

No command-line options are needed to work with another robot:

1. Type the robot's IP (and port, if it is not 4880) in the header. The boxes turn amber while the
   address differs from the connected robot; **Esc** puts the current one back.
2. Press **Enter** or click **Test**. Three checks run without touching the current connection:

   | Check | Passes when | If it fails |
   |---|---|---|
   | Ping | the robot replies | wrong IP, PC not on the robot's subnet, cable on CD38C, or Wi-Fi taking the traffic (some networks block ping; the other checks still run) |
   | OPC UA port | TCP port 4880 accepts a connection | *refused*: OPC UA server not available (software/option) or wrong port; *no answer*: wrong IP, robot off, or a firewall/VLAN |
   | OPC UA session | a session opens and the robot model is read | not a FANUC OPC UA server, or 10 clients already connected |

3. Click **Connect to this robot** (or **Connect** in the header). If the new robot cannot be reached,
   the GUI stays connected to the previous one and shows the test results.

### Reading the communication chart

Each bar is one request, newest on the right; its height is the time it took (scale on the left).
The color says what the request was for, and the legend shows each type's average:

| Color | Request | Typical on ROBOGUIDE |
|---|---|---|
| Blue | Robot status — about 10 OPC UA reads, so the tallest bar | 3–5 ms |
| Orange | Program status | under 1 ms |
| Green | Current position | under 1 ms |
| Yellow | Your own reads and writes from the tabs | depends |

The dashboard refreshes once a second with one blue, one orange and one green request, so a healthy
link draws a regular repeating pattern. Faded bars are failed requests; hover any bar for details.
On a real robot expect higher times — the manual quotes 3–18 ms typical and 100 ms or more under
load. Occasional spikes are normal; steadily rising times or a growing error count point to a network
or load problem. Each open browser tab adds its own requests, so close extra tabs before a demo.

### Safety

- Writes stay locked until you turn on the switch in the header. Position register and system
  variable writes ask for confirmation, and only *Speed override* is writable from the system variable list.
- `--read-only` disables writes in the server itself. Use it for customer demos on real robots.
- On a real robot, DO/RO writes switch the real outputs wired to them, and a running program may
  overwrite what you write.
- The GUI only accepts connections from this computer. `--bind 0.0.0.0` makes it reachable from the
  network, but it has **no login**, so only use that on a trusted network.

### Older controllers

Controllers older than 7DF1/P28 or 7DF3/P06 do not have the status nodes. The GUI still connects:
the Robot card falls back to model and version read from system variables, the Status card shows
*Not available*, and program, position, read & write, I/O panel and watch list work as usual.

## Standalone Windows .exe

`FANUC-OPCUA.exe` is a single file (about 25 MB) that contains Python, this library, the GUI and all
dependencies. Copy it to any 64-bit Windows 10/11 PC — no Python, no installation, no internet needed.

### Use it

1. **Double-click `FANUC-OPCUA.exe`.** A console window opens and the GUI opens in the default browser
   (the first start takes a few seconds while the file unpacks).
2. It connects to ROBOGUIDE at `127.0.0.2`. For a real robot, type its IP in **Robot IP** at the top of
   the page and click **Connect**.
3. Keep the console window open while you work; **close it (or press Ctrl+C) to stop**.

If port 8080 is busy the GUI uses 8081, 8082, … — the console window shows the address. Writes always
start locked.

The same file is also the command-line tool. Open a terminal in its folder:

```bat
FANUC-OPCUA.exe web --host 192.168.1.10 --read-only
FANUC-OPCUA.exe info --host 192.168.1.10
FANUC-OPCUA.exe read DO[1] R[5] PR[1]
FANUC-OPCUA.exe write DO[1]=on R[5]=2.5
FANUC-OPCUA.exe --help
```

The file is not code-signed, so Windows SmartScreen may show *"Windows protected your PC"* the first
time: click **More info → Run anyway**. Some company antivirus tools quarantine unsigned single-file
programs; ask IT to allow it, or build it yourself from source on that network.

### Build it

On a Windows PC with this repository and its development environment:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[web,build]"
.venv\Scripts\python packaging\build_exe.py
```

The result is `dist\FANUC-OPCUA.exe`. Stop any running GUI first, because Windows locks the program while
it runs. [`packaging/launcher.py`](packaging/launcher.py) is the entry point and
[`packaging/build_exe.py`](packaging/build_exe.py) the PyInstaller call.

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

For a readable end-to-end check against ROBOGUIDE, run the master check script. It prints every value
it reads, writes and reads back, then a PASS/FAIL summary:

```bash
python examples/roboguide_check.py                 # ROBOGUIDE at 127.0.0.2
python examples/roboguide_check.py --host 10.0.0.5 # another controller
python examples/roboguide_check.py --read-only     # no writes
```

Automated tests:

```bash
pytest -v                                         # unit tests, no robot needed
FANUC_TEST_HOST=127.0.0.2 pytest -v -m roboguide  # live tests against ROBOGUIDE
```

The live tests write to DO[100], F[100], R[100]–R[102], SR[20] and PR[100], and restore the
original values afterwards. Do not run them against a production robot.

## Changes

### 0.3

- Browser GUI: `fanuc-opcua web` (optional `web` extra). Picks the next free port if 8080 is busy.
- Standalone Windows `FANUC-OPCUA.exe` (double-click for the GUI; also the command line).
- `RobotStatus.state_flags`; `fanuc-opcua --json status` includes the flag names.
- Master check script `examples/roboguide_check.py`.

### 0.2

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
