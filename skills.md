---
name: fanuc-opcua
description: How to read and write FANUC robot I/O, registers, position registers and status over the controller's built-in OPC UA server with the fanuc_opcua Python library or its CLI.
---

# Using fanuc_opcua

## Connect

- URL: `opc.tcp://<ip>:4880/FANUC/NanoUaServer`, no authentication.
- ROBOGUIDE listens on **127.0.0.2**, not 127.0.0.1 (`fanuc_opcua.ROBOGUIDE_HOST`).

```python
from fanuc_opcua import FanucClient, FanucClientSync, Position

async with FanucClient("127.0.0.2") as robot: ...      # asyncio
with FanucClientSync("127.0.0.2") as robot: ...        # blocking, same methods
```

## Read and write by teach-pendant address

```python
await robot.read("DO[1]")                 # bool
await robot.read("UI[1]", count=8)        # list of 8
await robot.write("DO[1]", True)          # DO, RO, F, GO, AO, WO, WSO are writable
await robot.read("R[5]")                  # float
await robot.write("R[5]", 3)              # int -> integer register, float -> real register
await robot.write("SR[1]", "text")        # <= 79 chars
await robot.read("PR[1]")                 # Position (x..r, config, joints, valid flags)
await robot.write("PR[1]", Position.cartesian(500, 0, 400, 180, 0, 0))
await robot.write("PR[1]", Position.joint(0, 10, -20, 0, -70, 0))
await robot.write("PR[1]", {"z": 450})    # partial update
await robot.write("PR[1].x", 510)         # single member
await robot.read("POS")                   # current position, world frame (read only)
await robot.read("$MCR.$GENOVERRIDE")     # system variable, dtype="int" by default
await robot.read("$X.$Y", dtype="real")   # dtype must match the variable: int/real/bool/str/pos
```

Inputs (DI, RI, UI, UO, SI, SO, WI, WSI, GI, AI) and POS are read only; writing raises `ReadOnlyError`.
Non-existent indexes read as 0 and writes to them are silently ignored by the controller.

## Status

```python
await robot.info()            # model, serial_number, version, controller_model, software_revision
await robot.status()          # mode ("Auto"/"T1"/"T2"), servo_on, speed_override, state flags, alarms, joints, torque
await robot.program_status()  # program, line, state (ABORTED/PAUSED/RUNNING)
async for changed in robot.watch(["DO[1]", "R[1]"], interval=0.5): ...
```

## CLI

```bash
fanuc-opcua [--host IP] [--json] info | status
fanuc-opcua read DO[1] R[5] PR[1] [-n COUNT] [-t int|real|bool|str|pos]
fanuc-opcua write DO[1]=on R[5]=2.5 PR[1].x=500
fanuc-opcua watch DO[1] R[5] [-i SECONDS]
```

## Protocol notes (manual B-83284EN-2 ch. 55)

- Namespace 1: `Modbus` arrays DiscreteInput `i=301`, Coils `i=302`, InputRegisters `i=303`,
  HoldingRegisters `i=304` (Int16), Command `i=305`. Array index = Modbus address - 1.
- Namespace 2: `RobotInformation` nodes by string id (`ns=2;s=Model`, `ModeState`, `Alarm`, ...).
- OPC UA Robotics namespace (usually 3): `MotionDeviceSystem` (safety states, axes, controller).
- The server accepts **one node per Read/Write request**. Use IndexRange for partial array access.
- Registers, PR, SR, POS, PRG and system variables are reached with dynamic assignment:
  write `"CLRASG\nSETASG <addr> <size> <VAR_NAME> <multiply>"` to the Command node, then
  access the holding registers. Assignments last for the connection only. `CLRASG` hides the static
  `$SNPX_ASG` mapping for that connection. Multiply 0 gives REAL words, 1 gives int32.
- 32-bit values use two words, low word first. Strings pack the first character in the low byte.
- A position uses 50 words: x..r, e1..e3 (floats), flip/left/up/front/turn4-6, VALIDC (word 26),
  j1..j9 (words 27-44), VALIDJ, UF, UT. `PR[1]@27.12` extracts only the joint words.
