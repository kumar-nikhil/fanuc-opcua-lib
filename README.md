# Fanuc OPC UA Library (`fanuc-opcua-lib`)

> A Pythonic, asynchronous OPC UA abstraction library for Fanuc robots. Seamlessly monitor system states, perform position tracking, and interact with native Modbus I/O and Register arrays.

## Overview
Fanuc robots that have the OPC UA server option enabled expose various information arrays including Registers, Strings, Current Position, and Operational Status. 

Usually, reading this data entails writing low-level scripts managing NodeIDs and namespaces. `fanuc-opcua` abstracts the Fanuc `NanoUaServer` complexity using `asyncua` and provides a clean asynchronous API for typical data read/write workflows.

## Installation

```bash
pip install fanuc-opcua
```

## Quick Start

The library uses the standard python `asyncio` framework. Connection string targets the Fanuc controller IP.

```python
import asyncio
from fanuc_opcua import FanucClient

async def main():
    # Use context manager for auto connect/disconnect
    async with FanucClient("192.168.1.100") as robot:
        
        # 1. System Information
        model = await robot.robot_info.get_model()
        print(f"Connected to {model} robot!")

        # 2. Operational State
        alarms = await robot.robot_info.get_active_alarms()
        print(f"Active Alarms: {alarms}") # Cleanly filtered list

        # 3. Position and Motion
        position_data = await robot.robot_info.get_position()
        print(f"Position (X, Y, Z, W, P, R): {position_data}")

        # 4. Extended Discrete Modbus I/O (DI/DO mapped natively)
        # Supports DI, DO, RI, RO, UI, UO, SI, SO, Flags
        is_ui_active = await robot.io.get_uop_input(1) 
        print(f"UI[1] active: {is_ui_active}")
        
        # 5. Native Registers (Input/Holding)
        gi_1 = await robot.registers.get_group_input(1)
        print(f"GI[1]: {gi_1}")
        
        # Reading HoldingRegisters natively decodes standard INT16 Fanuc assignments
        r_1 = await robot.registers.read_holding_register(1, "int16")
        print(f"Numeric Register R[1]: {r_1}")
        
        # Supports reading user-mapped REALs seamlessly (combines two 16-bit registers natively)
        # r_real = await robot.registers.read_holding_register(11, "real")

if __name__ == "__main__":
    asyncio.run(main())
```

## Available API Namespaces

### `FanucClient.robot_info`
Access to device-level Namespace 2 nodes:
- `.get_model()`, `.get_version()`, `.get_serial_number()`
- `.get_active_alarms()`, `.get_uptime()`, `.get_servo_state()`
- `.get_operation_state()`, `.get_mode_state()`, `.get_program_speed()`
- `.get_position()`, `.get_torque()`

### `FanucClient.io`
Access to the discrete I/O structures (Namespace 1 Modbus mappings). *(Note: Index parameter natively matches Fanuc screen 1-based indices)*
- **Digital**: `.get_digital_input(idx)`, `.get_digital_output(idx)`
- **Robot**: `.get_robot_input(idx)`, `.get_robot_output(idx)`
- **User Operator**: `.get_uop_input(idx)`, `.get_uop_output(idx)`
- **System Operator**: `.get_sop_input(idx)`, `.get_sop_output(idx)`
- **Flags**: `.get_flag(idx)`

### `FanucClient.registers`
Access to Modbus Numeric registers (Groups, Analogs, Holding).
- **Groups**: `.get_group_input(idx)`, `.get_group_output(idx)`
- **Analogs**: `.get_analog_input(idx)`, `.get_analog_output(idx)`
- **Holding Data**: `.read_holding_register(address, data_type="int16"|"int32"|"real")`
