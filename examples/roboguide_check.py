"""
Step-by-step check of every library feature against ROBOGUIDE or a test robot.

Prints each value it reads, writes and reads back, then a PASS/FAIL summary.
Writes only to scratch addresses (DO[100..107], F[100], R[100..102], SR[20], PR[100])
and puts the original values back at the end.

    python examples/roboguide_check.py                  # ROBOGUIDE at 127.0.0.2
    python examples/roboguide_check.py --host 10.0.0.5  # another controller
    python examples/roboguide_check.py --read-only      # no writes at all
"""
import argparse
import os
import sys
import time
import traceback

from fanuc_opcua import (
    ROBOGUIDE_HOST, FanucClientSync, FanucError, Position, ReadOnlyError,
)

DO_START, DO_COUNT = 100, 8
FLAG = "F[100]"
REG = "R[100]"
STRING_REG = "SR[20]"
POS_REG = "PR[100]"


class Report:
    def __init__(self):
        self.results = []  # (section, name, ok, detail)
        self.section = ""

    def header(self, title: str) -> None:
        self.section = title
        print(f"\n=== {title} " + "=" * max(0, 66 - len(title)))

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((self.section, name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ->  {detail}" if detail else ""))
        return ok

    def info(self, name: str, value) -> None:
        text = str(value).replace("\n", "\n" + " " * 26)
        print(f"  {name:<22}{text}")

    def run(self, name: str, func) -> None:
        """Run one step; an exception counts as a failure instead of stopping the script."""
        try:
            func()
        except Exception as e:  # noqa: BLE001 - report every failure and keep going
            self.check(name, False, f"{type(e).__name__}: {e}")
            if os.environ.get("FANUC_CHECK_TRACE"):
                traceback.print_exc()

    def summary(self) -> int:
        failed = [r for r in self.results if not r[2]]
        print("\n" + "=" * 72)
        print(f"  {len(self.results) - len(failed)} passed, {len(failed)} failed")
        for section, name, _, detail in failed:
            print(f"  FAIL  {section} / {name}: {detail}")
        print("=" * 72)
        return 1 if failed else 0


def approx(a: float, b: float, tol: float = 1e-3) -> bool:
    return abs(a - b) <= tol


def timed(func):
    start = time.perf_counter()
    value = func()
    return value, (time.perf_counter() - start) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=os.environ.get("FANUC_HOST", ROBOGUIDE_HOST))
    parser.add_argument("--port", type=int, default=4880)
    parser.add_argument("--read-only", action="store_true", help="skip every write test")
    args = parser.parse_args()

    rep = Report()
    print(f"Connecting to {args.host}:{args.port} ...")
    try:
        robot = FanucClientSync(args.host, args.port)
        robot.connect()
    except FanucError as e:
        print(f"Connection failed: {e}")
        return 2

    originals = {}
    try:
        # ------------------------------------------------------------ 1
        rep.header("1. Connection and controller info")
        rep.check("connected", robot.connected, robot.endpoint)

        def info():
            i = robot.info()
            rep.info("model", i.model)
            rep.info("serial number", i.serial_number)
            rep.info("software", i.software_revision or i.version)
            rep.info("controller", i.controller_model)
            rep.check("info() returned model and version", bool(i.model and i.version))
        rep.run("info()", info)

        # ------------------------------------------------------------ 2
        rep.header("2. Robot status")

        def status():
            s = robot.status()
            rep.info("mode", s.mode)
            rep.info("servo", "ON" if s.servo_on else "OFF")
            rep.info("speed override", f"{s.speed_override}%")
            rep.info("state flags", ", ".join(s.state_flags) or "-")
            rep.info("e-stop", s.e_stop)
            rep.info("protective stop", s.protective_stop)
            rep.info("alarms", "; ".join(s.alarms) or "none")
            rep.info("joints (deg)", s.joint_positions)
            rep.info("torque (A)", s.torque)
            rep.info("uptime", f"{s.uptime_minutes} min")
            rep.check("mode is Auto/T1/T2", s.mode in ("Auto", "T1", "T2"), s.mode)
            rep.check("speed override 0..100", 0 <= s.speed_override <= 100, f"{s.speed_override}%")
        rep.run("status()", status)

        def program():
            p = robot.program_status()
            rep.info("program", f"{p.program or '-'} line {p.line} ({p.state.name})")
            rep.check("program_status() read", True)
        rep.run("program_status()", program)

        # ------------------------------------------------------------ 3
        rep.header("3. Current position")

        def position():
            pos = robot.position()
            rep.info("POS (world)", pos)
            rep.check("position is valid", pos.valid_cartesian, f"config {pos.config}")
            x = robot.read("POS.x")
            rep.check("POS.x matches POS", approx(x, pos.x, 0.5), f"{x}")
        rep.run("position()", position)

        # ------------------------------------------------------------ 4
        rep.header("4. Read inputs and outputs")
        for addr in ("DI[1]", "DO[1]", "RI[1]", "RO[1]", "UI[1]", "UO[1]", "SI[0]", "SO[0]", "F[1]"):
            def read_io(addr=addr):
                values, ms = timed(lambda: robot.read(addr, count=8))
                bits = "".join("1" if v else "0" for v in values)
                rep.check(f"read {addr} x8", len(values) == 8, f"{bits}  ({ms:.1f} ms)")
            rep.run(f"read {addr}", read_io)
        for addr in ("GI[1]", "GO[1]", "AI[1]", "AO[1]"):
            rep.run(f"read {addr}", lambda addr=addr: rep.check(f"read {addr}", True, str(robot.read(addr))))

        def read_only():
            try:
                robot.write("DI[1]", True)
                rep.check("writing DI[1] is refused", False, "write was accepted")
            except ReadOnlyError as e:
                rep.check("writing DI[1] is refused", True, str(e))
        rep.run("read-only check", read_only)

        if not args.read_only:
            # -------------------------------------------------------- 5
            rep.header(f"5. Write digital outputs (DO[{DO_START}..{DO_START + DO_COUNT - 1}], {FLAG})")
            originals["do"] = robot.read(f"DO[{DO_START}]", count=DO_COUNT)
            originals["flag"] = robot.read(FLAG)
            rep.info("original DO", originals["do"])

            def do_single():
                for value in (True, False):
                    robot.write(f"DO[{DO_START}]", value)
                    back = robot.read(f"DO[{DO_START}]")
                    rep.check(f"DO[{DO_START}] = {'ON' if value else 'OFF'}", back is value, f"read back {back}")
            rep.run("DO single", do_single)

            def do_block():
                pattern = [True, False, True, True, False, False, True, False]
                robot.write(f"DO[{DO_START}]", pattern)
                back = robot.read(f"DO[{DO_START}]", count=DO_COUNT)
                rep.check(f"DO[{DO_START}..] block of {DO_COUNT}", back == pattern,
                          "".join("1" if v else "0" for v in back))
            rep.run("DO block", do_block)

            def flag():
                robot.write(FLAG, True)
                back = robot.read(FLAG)
                rep.check(f"{FLAG} = ON", back is True, f"read back {back}")
            rep.run("flag", flag)

            # -------------------------------------------------------- 6
            rep.header(f"6. Numeric registers ({REG} and next two)")
            originals["reg"] = robot.read(REG, count=3)
            rep.info("original", originals["reg"])

            def reg_real():
                robot.write(REG, 12.75)
                back = robot.read(REG)
                rep.check(f"{REG} = 12.75 (real)", back == 12.75, f"read back {back}")
            rep.run("R real", reg_real)

            def reg_int():
                robot.write(REG, [1, -2, 300000])
                back = robot.read(REG, count=3)
                rep.check(f"{REG}..+2 = [1, -2, 300000] (int)", back == [1, -2, 300000], f"read back {back}")
            rep.run("R int", reg_int)

            # -------------------------------------------------------- 7
            rep.header(f"7. String register ({STRING_REG})")
            originals["sr"] = robot.read(STRING_REG)
            rep.info("original", repr(originals["sr"]))

            def string_reg():
                text = "fanuc-opcua check"
                robot.write(STRING_REG, text)
                back = robot.read(STRING_REG)
                rep.check(f"{STRING_REG} = {text!r}", back == text, f"read back {back!r}")
            rep.run("SR", string_reg)

            # -------------------------------------------------------- 8
            rep.header(f"8. Position register ({POS_REG})")
            originals["pr"] = robot.read(POS_REG)
            rep.info("original", originals["pr"])

            def pr_cartesian():
                here = robot.position()
                target = Position.cartesian(here.x, here.y, here.z + 50, here.w, here.p, here.r, config=here.config)
                robot.write(POS_REG, target)
                back = robot.read(POS_REG)
                rep.info("written", target)
                rep.info("read back", back)
                rep.check("cartesian write (current + 50 mm Z)",
                          all(approx(a, b) for a, b in zip(back.xyzwpr, target.xyzwpr)))
            rep.run("PR cartesian", pr_cartesian)

            def pr_member():
                robot.write(f"{POS_REG}.x", 555.5)
                back = robot.read(f"{POS_REG}.x")
                rep.check(f"{POS_REG}.x = 555.5", approx(back, 555.5), f"read back {back}")
            rep.run("PR member", pr_member)

            def pr_partial():
                before = robot.read(POS_REG)
                robot.write(POS_REG, {"y": before.y + 10})
                after = robot.read(POS_REG)
                rep.check("partial write y += 10 keeps x",
                          approx(after.y, before.y + 10) and approx(after.x, before.x),
                          f"x {after.x}, y {before.y} -> {after.y}")
            rep.run("PR partial", pr_partial)

            def pr_joint():
                joints = (0.0, 10.0, -20.0, 0.0, -70.0, 0.0)
                robot.write(POS_REG, Position.joint(*joints))
                back = robot.read(POS_REG)
                rep.check(f"joint write {joints}",
                          all(approx(a, b) for a, b in zip(back.joints, joints)), f"read back {back.joints}")
            rep.run("PR joint", pr_joint)

        # ------------------------------------------------------------ 9
        rep.header("9. System variable")

        def sysvar():
            value = robot.read("$MCR.$GENOVERRIDE")
            rep.check("read $MCR.$GENOVERRIDE", 0 <= value <= 100, f"{value}%")
        rep.run("sysvar", sysvar)

        # ------------------------------------------------------------ 10
        rep.header("10. Speed")
        for addr, count in (("DO[1]", 10000), ("R[1]", 200), ("PR[1]", 20)):
            def bulk(addr=addr, count=count):
                values, ms = timed(lambda: robot.read(addr, count=count))
                rep.check(f"read {count} x {addr.split('[')[0]}", len(values) == count, f"{ms:.1f} ms")
            rep.run(f"bulk {addr}", bulk)

        def single():
            _, ms = timed(lambda: [robot.read("DO[1]") for _ in range(20)])
            rep.check("20 single reads", True, f"{ms / 20:.1f} ms each")
        rep.run("single reads", single)

    finally:
        if originals:
            rep.header("Restoring original values")
            restore = [
                ("do", f"DO[{DO_START}]"), ("flag", FLAG), ("reg", REG), ("sr", STRING_REG), ("pr", POS_REG),
            ]
            for key, addr in restore:
                if key not in originals:
                    continue
                value = originals[key]
                if isinstance(value, Position) and not (value.valid_cartesian or value.valid_joint):
                    print(f"  {addr}: was uninitialized; left with test value")
                    continue
                try:
                    robot.write(addr, value)
                    print(f"  {addr}: restored")
                except FanucError as e:
                    print(f"  {addr}: could not restore ({e})")
        robot.close()

    return rep.summary()


if __name__ == "__main__":
    sys.exit(main())
