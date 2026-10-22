"""
Round-trip tests against a live controller or ROBOGUIDE.

    FANUC_TEST_HOST=127.0.0.2 pytest -m roboguide

These tests overwrite DO[100], F[100], R[100]-R[102], SR[20] and PR[100] and put
the original values back afterwards. Do not run them against a production robot.
"""
import os

import pytest

from fanuc_opcua import FanucClient, FanucClientSync, Position, ReadOnlyError

HOST = os.environ.get("FANUC_TEST_HOST")
PORT = int(os.environ.get("FANUC_TEST_PORT", "4880"))

pytestmark = [
    pytest.mark.roboguide,
    pytest.mark.skipif(not HOST, reason="set FANUC_TEST_HOST to run live tests"),
]


@pytest.fixture
async def robot():
    async with FanucClient(HOST, PORT) as client:
        yield client


async def test_info_and_status(robot):
    info = await robot.info()
    assert info.model and info.version
    status = await robot.status()
    assert status.mode in ("Auto", "T1", "T2")
    assert 0 <= status.speed_override <= 100
    assert isinstance(status.alarms, list)
    assert len(status.joint_positions) >= 1


async def test_digital_output_and_flag(robot):
    for address in ("DO[100]", "F[100]"):
        original = await robot.read(address)
        try:
            await robot.write(address, True)
            assert await robot.read(address) is True
            await robot.write(address, False)
            assert await robot.read(address) is False
        finally:
            await robot.write(address, original)


async def test_register_real_and_int(robot):
    original = await robot.read("R[100]", count=3)
    try:
        await robot.write("R[100]", 12.75)
        assert await robot.read("R[100]") == 12.75
        await robot.write("R[100]", [1, -2, 300000])
        assert await robot.read("R[100]", count=3) == [1, -2, 300000]
    finally:
        await robot.write("R[100]", original)


async def test_string_register(robot):
    original = await robot.read("SR[20]")
    try:
        await robot.write("SR[20]", "fanuc-opcua test")
        assert await robot.read("SR[20]") == "fanuc-opcua test"
    finally:
        await robot.write("SR[20]", original)


async def test_position_register(robot):
    original = await robot.read("PR[100]")
    try:
        current = await robot.position()
        assert current.valid_cartesian
        target = Position.cartesian(current.x, current.y, current.z - 10, current.w, current.p, current.r,
                                    config=current.config)
        await robot.write("PR[100]", target)
        pr = await robot.read("PR[100]")
        assert pr.valid_cartesian
        assert pr.z == pytest.approx(current.z - 10, abs=1e-3)

        await robot.write("PR[100].x", current.x + 5)
        assert await robot.read("PR[100].x") == pytest.approx(current.x + 5, abs=1e-3)

        await robot.write("PR[100]", {"y": current.y + 1})
        pr = await robot.read("PR[100]")
        assert pr.y == pytest.approx(current.y + 1, abs=1e-3)
        assert pr.x == pytest.approx(current.x + 5, abs=1e-3)

        await robot.write("PR[100]", Position.joint(*current.joints))
        pr = await robot.read("PR[100]")
        assert pr.joints[:6] == pytest.approx(current.joints[:6], abs=1e-3)
    finally:
        if original.valid_cartesian or original.valid_joint:
            await robot.write("PR[100]", original)


async def test_read_only_and_bulk(robot):
    with pytest.raises(ReadOnlyError):
        await robot.write("DI[1]", True)
    assert len(await robot.read("DO[1]", count=1000)) == 1000
    assert len(await robot.read("UI[1]", count=8)) == 8


async def test_program_status_and_sysvar(robot):
    status = await robot.program_status()
    assert status.state.name in ("ABORTED", "PAUSED", "RUNNING")
    override = await robot.read("$MCR.$GENOVERRIDE")
    assert 0 <= override <= 100


def test_sync_client():
    with FanucClientSync(HOST, PORT) as robot:
        assert robot.info().model
        original = robot.read("DO[100]")
        robot.write("DO[100]", not original)
        assert robot.read("DO[100]") is (not original)
        robot.write("DO[100]", original)
