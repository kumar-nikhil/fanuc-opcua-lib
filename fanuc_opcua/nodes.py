"""
Node ids of the FANUC NanoUaServer.

Reference: FANUC Optional Function manual B-83284EN-2, chapter 55
"HMI DEVICE COMMUNICATION" (55.2.2 Modbus nodes, 55.5 OPC UA data model).
"""

DEFAULT_PORT = 4880
ENDPOINT_PATH = "/FANUC/NanoUaServer"

# ROBOGUIDE binds its virtual controller to 127.0.0.2, not 127.0.0.1.
ROBOGUIDE_HOST = "127.0.0.2"

ROBOTICS_NS_URI = "http://opcfoundation.org/UA/Robotics/"
ROBOTICS_NS_DEFAULT = 3


class ModbusNodes:
    """Namespace 1 Modbus tables. Arrays are indexed by (Modbus address - 1)."""
    DISCRETE_INPUT = "ns=1;i=301"     # Boolean[], read only: DI, RI, UI, UO, SI, SO, WI, WO, WSI, WSO
    COILS = "ns=1;i=302"              # Boolean[], read/write: DO, RO, F
    INPUT_REGISTERS = "ns=1;i=303"    # UInt16[], read only: GI, GO, AI, AO
    HOLDING_REGISTERS = "ns=1;i=304"  # Int16[], read/write: data assigned by $SNPX_ASG / SETASG
    COMMAND = "ns=1;i=305"            # String, CLRASG / SETASG commands (55.4)


class RobotInfoNodes:
    """Namespace 2 RobotInformation nodes (55.5.1, 7DF1/P28+ and 7DF3/P06+)."""
    MODEL = "ns=2;s=Model"
    SERIAL_NUMBER = "ns=2;s=SerialNumber"
    VERSION = "ns=2;s=Version"
    SERVO_STATE = "ns=2;s=ServoState"
    OPERATION_STATE = "ns=2;s=OperationState"
    MODE_STATE = "ns=2;s=ModeState"
    PROGRAM_SPEED = "ns=2;s=ProgramSpeed"
    UPTIME = "ns=2;s=Uptime"
    TORQUE = "ns=2;s=Torque"
    POSITION = "ns=2;s=Position"
    ALARM = "ns=2;s=Alarm"


class RoboticsNodes:
    """Numeric identifiers inside the OPC UA Robotics namespace (55.5.2)."""
    SPEED_OVERRIDE = 30003
    CONTROLLER_MODEL = 40003
    SOFTWARE_REVISION = 40012
    USER_LEVEL = 40007
    OPERATIONAL_MODE = 50003
    EMERGENCY_STOP = 50004
    PROTECTIVE_STOP = 50005
