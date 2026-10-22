"""Save a snapshot of robot state, I/O and registers to robot_data.json."""
import asyncio
import json
import sys

from fanuc_opcua import ROBOGUIDE_HOST, FanucClient
from fanuc_opcua.cli import to_jsonable


async def dump_data(host: str) -> None:
    async with FanucClient(host) as robot:
        print(f"Connected to {robot.endpoint}")
        data = {
            "info": await robot.info(),
            "status": await robot.status(),
            "program": await robot.program_status(),
            "position": await robot.position(),
            "DI[1-20]": await robot.read("DI[1]", count=20),
            "DO[1-20]": await robot.read("DO[1]", count=20),
            "UI[1-20]": await robot.read("UI[1]", count=20),
            "UO[1-20]": await robot.read("UO[1]", count=20),
            "F[1-20]": await robot.read("F[1]", count=20),
            "GI[1-10]": await robot.read("GI[1]", count=10),
            "R[1-50]": await robot.read("R[1]", count=50),
            "PR[1-10]": await robot.read("PR[1]", count=10),
            "SR[1-10]": await robot.read("SR[1]", count=10),
        }

    with open("robot_data.json", "w") as f:
        json.dump(to_jsonable(data), f, indent=2)
    print("Wrote robot_data.json")


if __name__ == "__main__":
    asyncio.run(dump_data(sys.argv[1] if len(sys.argv) > 1 else ROBOGUIDE_HOST))
