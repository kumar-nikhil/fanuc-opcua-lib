import asyncio
import json
from fanuc_opcua import FanucClient

async def dump_data():
    print("Connecting to live robot at 192.168.1.100...")
    data = {}
    
    async with FanucClient("192.168.1.100") as robot:
        print("Connected! Fetching Robot Info (ns=2)...")
        data["RobotInfo"] = {
            "Model": await robot.robot_info.get_model(),
            "SerialNumber": await robot.robot_info.get_serial_number(),
            "Version": await robot.robot_info.get_version(),
            "ActiveAlarms": await robot.robot_info.get_active_alarms(),
            "ServoState": await robot.robot_info.get_servo_state(),
            "OperationState": await robot.robot_info.get_operation_state(),
            "ModeState": await robot.robot_info.get_mode_state(),
            "ProgramSpeed": await robot.robot_info.get_program_speed(),
            "Uptime": await robot.robot_info.get_uptime(),
            "Position": await robot.robot_info.get_position(),
            "Torque": await robot.robot_info.get_torque()
        }
        
        print("Fetching Raw Arrays (ns=1)...")
        # Fetching raw arrays from the controller to avoid multiple offset calls
        discrete_inputs = await robot.io._read_discrete_input_array()
        coils = await robot.io._read_coils_array()
        input_registers = await robot.registers._read_input_registers_array()
        holding_registers = await robot.registers._read_holding_registers_array()

        print("Slicing useful data samples...")
        data["ModbusArrays"] = {
            "DiscreteInputs (DI/RI/UI/SI/etc)": {
                "Length": len(discrete_inputs),
                "Sample_DI_1_to_20": discrete_inputs[0:20],
                "Sample_UI_1_to_20": discrete_inputs[20000:20020]
            },
            "Coils (DO/RO/F/etc)": {
                "Length": len(coils),
                "Sample_DO_1_to_20": coils[0:20],
                "Sample_Flag_1_to_20": coils[20000:20020]
            },
            "InputRegisters (GI/AI)": {
                "Length": len(input_registers),
                "Sample_GI_1_to_20": input_registers[0:20],
                "Sample_AI_1_to_20": input_registers[2000:2020]
            },
            "HoldingRegisters (R/PR)": {
                "Length": len(holding_registers),
                "Sample_Holding_1_to_100": holding_registers[0:100]
            }
        }
        
    # Write to File
    with open("robot_data.json", "w") as f:
        json.dump(data, f, indent=4)
        
    print("Successfully wrote all polled data to robot_data.json!")

if __name__ == "__main__":
    asyncio.run(dump_data())
