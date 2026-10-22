"""The same API without asyncio, plus a change monitor (Ctrl+C to stop)."""
import sys

from fanuc_opcua import ROBOGUIDE_HOST, FanucClientSync

host = sys.argv[1] if len(sys.argv) > 1 else ROBOGUIDE_HOST

with FanucClientSync(host) as robot:
    print(robot.info())
    robot.write("DO[101]", True)
    print("DO[101] =", robot.read("DO[101]"))
    print("R[1..5] =", robot.read("R[1]", count=5))

    try:
        for changed in robot.watch(["DO[100]", "DO[101]", "R[100]"], interval=0.5):
            print(changed)
    except KeyboardInterrupt:
        pass
