"""Read and write a few scratch values (DO[100], R[100], SR[20], PR[100]) on ROBOGUIDE or a given IP."""
import asyncio
import sys

from fanuc_opcua import ROBOGUIDE_HOST, FanucClient, Position


async def main(host: str) -> None:
    async with FanucClient(host) as robot:
        info = await robot.info()
        print(f"Connected to {info.model}, software {info.version}")

        status = await robot.status()
        print(f"Mode {status.mode}, servo {'ON' if status.servo_on else 'OFF'}, "
              f"override {status.speed_override}%, alarms: {status.alarms or 'none'}")

        print("Current position:\n", await robot.position())

        await robot.write("DO[100]", True)
        print("DO[100] =", await robot.read("DO[100]"))
        print("UI[1..8] =", await robot.read("UI[1]", count=8))

        await robot.write("R[100]", 12.5)
        print("R[100] =", await robot.read("R[100]"))

        await robot.write("SR[20]", "hello from python")
        print("SR[20] =", await robot.read("SR[20]"))

        here = await robot.position()
        await robot.write("PR[100]", Position.cartesian(here.x, here.y, here.z + 50, here.w, here.p, here.r,
                                                      config=here.config))
        await robot.write("PR[100].x", here.x + 10)
        print("PR[100] =\n", await robot.read("PR[100]"))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else ROBOGUIDE_HOST))
