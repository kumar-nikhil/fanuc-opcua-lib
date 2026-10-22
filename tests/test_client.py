"""Client logic against an in-memory stand-in for the controller's Modbus nodes."""
import pytest

from fanuc_opcua import FanucClient, Position, ReadOnlyError
from fanuc_opcua import codec
from fanuc_opcua.errors import AddressError, NotConnectedError
from fanuc_opcua.nodes import ModbusNodes
from fanuc_opcua.transport import AssignmentWindow


class FakeTransport:
    def __init__(self):
        self.arrays = {
            ModbusNodes.DISCRETE_INPUT: [False] * 28000,
            ModbusNodes.COILS: [False] * 30000,
            ModbusNodes.INPUT_REGISTERS: [0] * 4000,
            ModbusNodes.HOLDING_REGISTERS: [0] * 16384,
        }
        self.commands = []

    async def read_array(self, node_id, start, count):
        return self.arrays[node_id][start:start + count]

    async def write_array(self, node_id, start, values, variant_type):
        self.arrays[node_id][start:start + len(values)] = list(values)

    async def read_holding(self, start, count):
        return await self.read_array(ModbusNodes.HOLDING_REGISTERS, start, count)

    async def write_holding(self, start, words):
        await self.write_array(ModbusNodes.HOLDING_REGISTERS, start, words, None)

    async def write_command(self, text):
        self.commands.append(text)

    @property
    def holding(self):
        return self.arrays[ModbusNodes.HOLDING_REGISTERS]


@pytest.fixture
def fake():
    return FakeTransport()


@pytest.fixture
def robot(fake):
    client = FanucClient("127.0.0.2")
    client._client = object()  # mark as connected
    client._transport = fake
    client._window = AssignmentWindow(fake)
    return client


async def test_requires_connection():
    with pytest.raises(NotConnectedError):
        await FanucClient("127.0.0.2").read("DO[1]")


async def test_coils(robot, fake):
    await robot.write("DO[3]", True)
    await robot.write("F[1]", [1, 0, "on"])
    assert fake.arrays[ModbusNodes.COILS][2] is True
    assert fake.arrays[ModbusNodes.COILS][20000:20003] == [True, False, True]
    assert await robot.read("DO[3]") is True
    assert await robot.read("F[1]", count=3) == [True, False, True]


async def test_discrete_inputs_are_read_only(robot, fake):
    fake.arrays[ModbusNodes.DISCRETE_INPUT][20000] = True
    assert await robot.read("UI[1]") is True
    for address in ("DI[1]", "UI[1]", "GI[1]", "POS"):
        with pytest.raises(ReadOnlyError):
            await robot.write(address, 1)


async def test_group_output_is_written_through_holding_register(robot, fake):
    await robot.write("GO[2]", 65535)
    assert fake.commands[-1] == "CLRASG\nSETASG 1 1 GO[2] 1"
    assert fake.holding[0] == -1


async def test_register_real(robot, fake):
    await robot.write("R[5]", 2.5)
    assert fake.commands == ["CLRASG\nSETASG 1 2 R[5] 0"]
    assert fake.holding[0:2] == codec.float_to_words(2.5)
    assert await robot.read("R[5]") == 2.5
    assert len(fake.commands) == 1  # same assignment is not re-sent


async def test_register_ints_use_int32(robot, fake):
    await robot.write("R[1]", [1, 2, -3])
    assert fake.commands[-1] == "CLRASG\nSETASG 1 6 R[1] 1"
    assert fake.holding[0:6] == [1, 0, 2, 0, -3, -1]


async def test_string_register(robot, fake):
    await robot.write("SR[2]", "hello")
    assert fake.commands[-1] == "CLRASG\nSETASG 1 40 SR[2] 1"
    assert await robot.read("SR[2]") == "hello"


async def test_position_register_cartesian(robot, fake):
    await robot.write("PR[G2:7]", Position.cartesian(500, 1, 2, 180, 0, 0))
    assert fake.commands[-1] == "CLRASG\nSETASG 1 50 PR[G2:7] 0"
    fake.holding[25] = 1  # VALIDC, set by the controller
    pos = await robot.read("PR[G2:7]")
    assert pos.xyzwpr == (500, 1, 2, 180, 0, 0)


async def test_position_register_joint(robot, fake):
    await robot.write("PR[1]", Position.joint(1, 2, 3, 4, 5, 6))
    assert codec.words_to_floats(fake.holding[26:38]) == [1, 2, 3, 4, 5, 6]
    assert fake.holding[0:25] == [0] * 25


async def test_position_register_partial_dict(robot, fake):
    fake.holding[0:25] = codec.encode_cartesian(Position.cartesian(1, 2, 3, 4, 5, 6))
    await robot.write("PR[1]", {"x": 100, "Z": 300})
    assert codec.words_to_floats(fake.holding[0:12]) == [100, 2, 300, 4, 5, 6]
    with pytest.raises(AddressError):
        await robot.write("PR[1]", {"x": 1, "j1": 2})


async def test_position_member(robot, fake):
    await robot.write("PR[3].y", 12.5)
    assert fake.commands[-1] == "CLRASG\nSETASG 1 2 PR[3]@3.2 0"
    assert await robot.read("PR[3].y") == 12.5


async def test_sysvar_types(robot, fake):
    await robot.write("$MCR.$GENOVERRIDE", 50)
    assert fake.commands[-1] == "CLRASG\nSETASG 1 2 $MCR.$GENOVERRIDE 1"
    assert await robot.read("$MCR.$GENOVERRIDE") == 50
    await robot.write("$SOME.$REAL", 1.5, dtype="real")
    assert fake.commands[-1] == "CLRASG\nSETASG 1 2 $SOME.$REAL 0"
    assert await robot.read("$SOME.$REAL", dtype="real") == 1.5
    with pytest.raises(AddressError):
        await robot.read("R[1]", dtype="real")


async def test_program_status(robot, fake):
    fake.holding[0:8] = codec.str_to_words("MAIN", 8)
    fake.holding[8:10] = [12, 2]
    fake.holding[10:18] = codec.str_to_words("MAIN", 8)
    status = await robot.program_status()
    assert (status.program, status.line, status.state.name) == ("MAIN", 12, "RUNNING")
    assert fake.commands[-1] == "CLRASG\nSETASG 1 18 PRG[1] 1"


async def test_invalid_values(robot):
    with pytest.raises(ValueError):
        await robot.write("DO[1]", 2)
    with pytest.raises(ValueError):
        await robot.write("GO[1]", 1.5)
    with pytest.raises(ValueError):
        await robot.write("SR[1]", "x" * 80)


async def test_watch_yields_changes(robot, fake):
    seen = []
    async for changed in robot.watch(["DO[1]", "DO[2]"], interval=0):
        seen.append(changed)
        if len(seen) == 1:
            fake.arrays[ModbusNodes.COILS][1] = True
        else:
            break
    assert seen == [{"DO[1]": False, "DO[2]": False}, {"DO[2]": True}]
