"""JSON API of the browser GUI, against the in-memory fake controller."""
import pytest

pytest.importorskip("aiohttp")
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from fanuc_opcua import FanucClient, codec  # noqa: E402
from fanuc_opcua.nodes import ModbusNodes, RobotInfoNodes  # noqa: E402
from fanuc_opcua.transport import AssignmentWindow  # noqa: E402
from fanuc_opcua.web.server import RobotSession, create_app  # noqa: E402
from test_client import FakeTransport  # noqa: E402

NODE_VALUES = {
    RobotInfoNodes.MODEL: "CRX-10iA/L",
    RobotInfoNodes.SERIAL_NUMBER: "F00000    ",
    RobotInfoNodes.VERSION: "7DF5/89",
    RobotInfoNodes.MODE_STATE: "Auto",
    RobotInfoNodes.SERVO_STATE: 1,
    RobotInfoNodes.PROGRAM_SPEED: 100,
    RobotInfoNodes.OPERATION_STATE: 40,
    RobotInfoNodes.ALARM: ["MOTN-018 Position not reachable (G:1)", None],
    RobotInfoNodes.POSITION: [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
    RobotInfoNodes.TORQUE: [0.0] * 6,
    RobotInfoNodes.UPTIME: 120,
}


class FakeController(FakeTransport):
    async def read_value(self, node_id, index_range=None):
        if node_id in NODE_VALUES:
            return NODE_VALUES[node_id]
        from fanuc_opcua.errors import CommunicationError
        raise CommunicationError(f"Read of {node_id} failed", "BadNodeIdUnknown")


def make_session(read_only=False):
    fake = FakeController()
    robot = FanucClient("127.0.0.2")
    robot._client = object()
    robot._transport = fake
    robot._window = AssignmentWindow(fake)
    session = RobotSession("127.0.0.2", 4880, read_only)
    session.robot = robot
    session.connected_at = 0
    return session, fake


@pytest.fixture
async def gui():
    session, fake = make_session()
    client = TestClient(TestServer(create_app(session=session, auto_connect=False)))
    await client.start_server()
    yield client, fake
    session.robot = None  # nothing real to disconnect
    await client.close()


async def test_index_page(gui):
    client, _ = gui
    res = await client.get("/")
    assert res.status == 200
    assert "FANUC OPC UA Console" in await res.text()


async def test_catalog(gui):
    client, _ = gui
    items = {i["kind"]: i for i in (await (await client.get("/api/catalog")).json())["items"]}
    assert items["DO"]["writable"] and not items["DI"]["writable"]
    assert items["PR"]["type"] == "position" and not items["POS"]["writable"]
    assert items["SI"]["first"] == 0


async def test_live_dashboard(gui):
    client, _ = gui
    data = await (await client.get("/api/live")).json()
    assert data["connected"] is True
    assert data["status"]["state_flags"] == ["PAUSED", "FAULT"]
    assert data["status"]["alarms"] == ["MOTN-018 Position not reachable (G:1)"]
    assert data["program"]["state"] == "ABORTED"
    assert data["stats"]["requests"] == 3


async def test_read_and_write_digital_output(gui):
    client, fake = gui
    res = await (await client.post("/api/write", json={"address": "DO[3]", "value": "on"})).json()
    assert res["ok"] and res["readback"] is True
    assert fake.arrays[ModbusNodes.COILS][2] is True
    res = await (await client.post("/api/write", json={"address": "DO[3]", "value": False})).json()
    assert res["readback"] is False
    res = await (await client.post("/api/read", json={"address": "DO[1]", "count": 4})).json()
    assert res["value"] == [False, False, False, False]


async def test_register_int_and_real(gui):
    client, fake = gui
    await client.post("/api/write", json={"address": "R[1]", "value": "7"})
    assert fake.commands[-2] == "CLRASG\nSETASG 1 2 R[1] 1"  # integer write, then the read-back
    res = await (await client.post("/api/write", json={"address": "R[1]", "value": "2.5"})).json()
    assert res["readback"] == 2.5


async def test_position_register_dict(gui):
    client, fake = gui
    res = await (await client.post("/api/write", json={"address": "PR[1]", "value": {"x": 500, "z": 400}})).json()
    assert res["ok"]
    assert codec.words_to_floats(fake.holding[0:6]) == [500, 0, 400]


async def test_read_many_reports_errors_per_address(gui):
    client, _ = gui
    res = await (await client.post("/api/read_many", json={"addresses": ["DO[1]", "XX[1]"]})).json()
    assert res["values"] == {"DO[1]": False}
    assert "XX[1]" in res["errors"]


async def test_bad_requests(gui):
    client, _ = gui
    res = await client.post("/api/write", json={"address": "DI[1]", "value": "on"})
    assert res.status == 400 and "cannot be written" in (await res.json())["error"]
    res = await client.post("/api/read", json={"address": "nonsense"})
    assert res.status == 400


async def test_read_only_server():
    session, _ = make_session(read_only=True)
    client = TestClient(TestServer(create_app(session=session, auto_connect=False)))
    await client.start_server()
    try:
        res = await client.post("/api/write", json={"address": "DO[1]", "value": "on"})
        assert res.status == 403
    finally:
        session.robot = None
        await client.close()


async def test_not_connected():
    session = RobotSession("127.0.0.2", 4880, False)
    client = TestClient(TestServer(create_app(session=session, auto_connect=False)))
    await client.start_server()
    try:
        assert (await client.post("/api/read", json={"address": "DO[1]"})).status == 409
        data = await (await client.get("/api/live")).json()
        assert data["connected"] is False and data["status"] is None
    finally:
        await client.close()


class OldController(FakeController):
    """Software older than 7DF1/P28: no RobotInformation or Robotics nodes."""

    async def read_value(self, node_id, index_range=None):
        from fanuc_opcua.errors import CommunicationError
        raise CommunicationError(f"Read of {node_id} failed", "BadNodeIdUnknown")


async def test_catalog_has_system_variable_presets(gui):
    client, _ = gui
    data = await (await client.get("/api/catalog")).json()
    names = {v["name"]: v for v in data["sysvars"]}
    assert names["$MCR.$GENOVERRIDE"]["dtype"] == "int" and names["$MCR.$GENOVERRIDE"]["write"]
    assert all(v["dtype"] in data["dtypes"] for v in data["sysvars"])


async def test_older_controller_without_status_nodes():
    session, fake = make_session()
    old = OldController()
    old.arrays, old.commands = fake.arrays, fake.commands
    session.robot._transport = old
    session.robot._window = AssignmentWindow(old)
    old.holding[0:40] = codec.str_to_words("CRX", 40)  # every sysvar read sees this window

    info = await session._read_info()
    assert info["model"] == "CRX" and "note" in info

    client = TestClient(TestServer(create_app(session=session, auto_connect=False)))
    await client.start_server()
    try:
        first = await (await client.get("/api/live")).json()
        assert first["ok"] and first["status"] is None and "status" in first["unavailable"]
        assert first["program"] is not None and first["position"] is not None
        requests = first["stats"]["requests"]
        second = await (await client.get("/api/live")).json()
        assert second["stats"]["requests"] - requests == 2  # status is not asked for again
    finally:
        session.robot = None
        await client.close()


async def test_latency_history_is_labelled_by_operation(gui):
    client, _ = gui
    await client.post("/api/read", json={"address": "DO[1]"})
    data = await (await client.get("/api/live")).json()
    ops = [entry[1] for entry in data["stats"]["history"]]
    assert ops == ["manual", "status", "program", "position"]
    ms, op, ok, ago = data["stats"]["history"][0]
    assert ms >= 0 and ok is True and ago >= 0


def test_find_free_port_skips_busy_port():
    import socket

    from fanuc_opcua.web.server import find_free_port

    first = find_free_port("127.0.0.1", 18080)
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", first))
        busy.listen()
        assert find_free_port("127.0.0.1", first) == first + 1


def _closed_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]  # nothing listens here once the socket is closed


@pytest.mark.parametrize("host", ["192.168.1.10", "robot-cell3.local", "127.0.0.2"])
def test_validate_host_accepts(host):
    from fanuc_opcua.web.connection_test import validate_host
    assert validate_host(f" {host} ") == host


@pytest.mark.parametrize("host", ["", "1.2.3.4; del x", "a & calc", "-n 5 host", "x" * 300, "http://1.2.3.4"])
def test_validate_host_rejects(host):
    from fanuc_opcua.web.connection_test import validate_host
    with pytest.raises(ValueError):
        validate_host(host)


async def test_connection_test_reports_refused_port(gui):
    client, _ = gui
    res = await (await client.post("/api/test_connection", json={"host": "127.0.0.1", "port": _closed_port()})).json()
    assert res["ok"] is True and res["passed"] is False
    names = [st["name"] for st in res["steps"]]
    assert names == ["Ping", "OPC UA port", "OPC UA session"]
    port_step, session_step = res["steps"][1], res["steps"][2]
    assert port_step["ok"] is False and "refused" in port_step["detail"] and port_step["hint"]
    assert session_step["ok"] is None


async def test_connection_test_rejects_bad_host(gui):
    client, _ = gui
    res = await client.post("/api/test_connection", json={"host": "1.2.3.4 & calc", "port": 4880})
    assert res.status == 400


async def test_failed_switch_keeps_current_robot(gui):
    client, _ = gui
    res = await client.post("/api/connect", json={"host": "127.0.0.1", "port": _closed_port()})
    assert res.status == 503
    data = await (await client.get("/api/session")).json()
    assert data["connected"] is True and data["host"] == "127.0.0.2"
