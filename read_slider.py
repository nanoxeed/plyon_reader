"""Read plyon serial data; add --visualize to show the slider contact position."""

import argparse
import math
import sys
import time
from dataclasses import dataclass

import serial

PORT = "/dev/ttyACM0"  # Windowsなら "COM3" など
BAUDRATE = 115200  # 既存の受信設定。必要なら --baudrate で変更
STALE_SECONDS = 1.0


@dataclass(frozen=True)
class SliderSample:
    position: float
    force: float


def parse_sample(line, position_column=7, force_column=8):
    """Read numeric CSV; column numbers are 1-based, including custom layouts."""
    try:
        values = [float(value) for value in line.split(",")]
    except ValueError:
        return None
    if len(values) < max(position_column, force_column):
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    return SliderSample(values[position_column - 1], values[force_column - 1])


class LineBuffer:
    """Keep partial serial lines between GUI ticks; bound unterminated input."""

    def __init__(self, limit=4096):
        self.limit = limit
        self.pending = b""
        self.discarding = False

    def feed(self, data):
        parts = data.split(b"\n")
        lines = []
        for part in parts[:-1]:
            line = self.pending + part
            if not self.discarding and len(line) <= self.limit:
                lines.append(line.decode("utf-8", errors="replace").strip())
            self.pending = b""
            self.discarding = False
        if not self.discarding:
            self.pending += parts[-1]
            if len(self.pending) > self.limit:
                self.pending = b""
                self.discarding = True
        return lines


def position_fraction(sample, args):
    value = (sample.position - args.position_min) / (
        args.position_max - args.position_min
    )
    value = min(1.0, max(0.0, value))
    return 1.0 - value if args.reverse else value


class SliderView:
    def __init__(self, root, tk, args, ser=None):
        self.root, self.args, self.ser = root, args, ser
        self.buffer = LineBuffer()
        self.sample = None
        self.last_sample_at = None
        self.started_at = time.monotonic()
        self.invalid_lines = 0
        self.error = None
        root.title("plyon slider — contact position")
        root.geometry("820x360")
        root.minsize(640, 360)
        self.canvas = tk.Canvas(root, background="#f4f7fb", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        root.bind("<Escape>", lambda event: root.destroy())
        self.draw(self.started_at)
        root.after(0, self.tick)

    def tick(self):
        now = time.monotonic()
        if self.args.demo:
            elapsed = now - self.started_at
            position = self.args.position_min + (math.sin(elapsed) + 1) / 2 * (
                self.args.position_max - self.args.position_min
            )
            force = self.args.force_max * (0.45 + 0.3 * math.sin(elapsed * 1.7))
            if elapsed % 8 > 6:
                force = 0  # Include releases in the demonstration.
            values = ["0"] * max(self.args.position_column, self.args.force_column)
            values[self.args.position_column - 1] = f"{position:.1f}"
            values[self.args.force_column - 1] = f"{force:.1f}"
            lines = [",".join(values)]
        else:
            try:
                # timeout=0 and a per-tick bound keep the window responsive.
                data = self.ser.read(min(self.ser.in_waiting, 65536))
            except (serial.SerialException, OSError) as exc:
                self.error = str(exc)
                print(f"Serial error: {exc}", file=sys.stderr)
                self.draw(now)
                return
            lines = self.buffer.feed(data)
        for line in lines:
            if not self.args.quiet:
                print(line)
            sample = parse_sample(
                line, self.args.position_column, self.args.force_column
            )
            if sample is None:
                if line:
                    self.invalid_lines += 1
                continue
            self.sample = sample
            self.last_sample_at = now
        self.draw(now)
        self.root.after(33, self.tick)

    def draw(self, now):
        canvas = self.canvas
        canvas.delete("all")
        width = max(640, canvas.winfo_width())
        left, right = 60, width - 60
        fresh = (
            self.last_sample_at is not None
            and now - self.last_sample_at < STALE_SECONDS
            and self.error is None
        )
        touching = fresh and self.sample.force > self.args.force_threshold
        color = "#008573" if touching else "#64748b"
        if self.error:
            status = "DISCONNECTED — see terminal"
        elif self.last_sample_at is None:
            status = "WAITING FOR VALID DATA"
        elif not fresh:
            status = "NO DATA — contact unknown"
        else:
            status = "CONTACT" if touching else "NO CONTACT"
        canvas.create_text(
            left,
            30,
            text="plyon / SLIDER",
            anchor="w",
            font=("sans-serif", 18, "bold"),
            fill="#17243b",
        )
        canvas.create_text(
            right,
            30,
            text="DEMO" if self.args.demo else self.args.port,
            anchor="e",
            font=("sans-serif", 11),
            fill="#64748b",
        )
        canvas.create_text(
            left,
            70,
            text=status,
            anchor="w",
            font=("sans-serif", 12, "bold"),
            fill=color,
        )
        canvas.create_line(
            left, 145, right, 145, width=36, capstyle="round", fill="#dce4ed"
        )
        for fraction in (0, 0.25, 0.5, 0.75, 1):
            x = left + fraction * (right - left)
            canvas.create_line(x, 170, x, 177, fill="#94a3b8")
            canvas.create_text(x, 194, text=f"{fraction:.0%}", fill="#64748b")
        if touching:
            x = left + position_fraction(self.sample, self.args) * (right - left)
            intensity = min(1.0, max(0.0, self.sample.force / self.args.force_max))
            radius = 12 + intensity * 12
            canvas.create_oval(
                x - radius,
                145 - radius,
                x + radius,
                145 + radius,
                fill=color,
                outline="white",
                width=3,
                tags="contact",
            )
        if fresh:
            position = (
                f"{position_fraction(self.sample, self.args):.1%}" if touching else "—"
            )
            values = (
                f"Position: {position}   |   raw: {self.sample.position:g}"
                f"     Force (raw): {self.sample.force:g}"
            )
        else:
            values = "Position: —     Force (raw): —"
        canvas.create_text(
            left,
            230,
            text=values,
            anchor="w",
            font=("sans-serif", 12),
            fill="#17243b",
            width=right - left,
            justify="left",
        )
        canvas.create_rectangle(left, 255, right, 269, fill="#dce4ed", outline="")
        if fresh:
            force_fraction = min(1.0, max(0.0, self.sample.force / self.args.force_max))
            canvas.create_rectangle(
                left,
                255,
                left + force_fraction * (right - left),
                269,
                fill=color,
                outline="",
            )
        info = (
            f"CSV columns: position={self.args.position_column}, force={self.args.force_column}"
            f"   |   contact: force > {self.args.force_threshold:g}"
            f"   |   skipped: {self.invalid_lines}"
        )
        canvas.create_text(
            left,
            300,
            text=info,
            anchor="w",
            fill="#64748b",
            width=right - left,
            justify="left",
        )
        canvas.create_text(
            left, 326, text="Esc / close window to stop", anchor="w", fill="#64748b"
        )


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=PORT)
    parser.add_argument("--baudrate", type=int, default=BAUDRATE)
    parser.add_argument(
        "--visualize", action="store_true", help="show slider contact in a window"
    )
    parser.add_argument(
        "--demo", action="store_true", help="visualize simulated data without hardware"
    )
    parser.add_argument("--quiet", action="store_true", help="suppress raw data output")
    parser.add_argument(
        "--position-column", type=int, default=7, help="1-based CSV position column"
    )
    parser.add_argument(
        "--force-column", type=int, default=8, help="1-based CSV force column"
    )
    parser.add_argument("--position-min", type=float, default=0)
    parser.add_argument("--position-max", type=float, default=4095)
    parser.add_argument(
        "--force-max", type=float, default=4095, help="force bar full scale (raw units)"
    )
    parser.add_argument(
        "--force-threshold",
        type=float,
        default=20,
        help="contact requires force > threshold (raw units)",
    )
    parser.add_argument(
        "--reverse", action="store_true", help="reverse the displayed slider direction"
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.baudrate <= 0 or min(args.position_column, args.force_column) < 1:
        parser.error("baudrate and column numbers must be positive")
    if args.position_column == args.force_column:
        parser.error("position and force must use different columns")
    if not all(
        math.isfinite(v)
        for v in (
            args.position_min,
            args.position_max,
            args.force_max,
            args.force_threshold,
        )
    ):
        parser.error("ranges and threshold must be finite")
    if args.position_max <= args.position_min or not math.isfinite(
        args.position_max - args.position_min
    ):
        parser.error("position-max must exceed position-min with a finite span")
    if args.force_max <= 0 or args.force_threshold < 0:
        parser.error("force-max must be positive and force-threshold nonnegative")

    ser = None
    root = None
    try:
        if args.visualize or args.demo:
            try:
                import tkinter as tk
            except ImportError:
                print(
                    "Visualization requires Python with Tk support (tkinter).",
                    file=sys.stderr,
                )
                return 1
            try:
                root = tk.Tk()
            except tk.TclError as exc:
                print(f"Cannot open visualization window: {exc}", file=sys.stderr)
                return 1
        if not args.demo:
            ser = serial.Serial(
                args.port, args.baudrate, timeout=0 if root is not None else 1
            )
            print(f"Connected to {args.port}")
        if root is not None:
            view = SliderView(root, tk, args, ser)
            root.mainloop()
            return 1 if view.error else 0
        while True:
            raw = ser.readline()
            if raw and not args.quiet:
                print(raw.decode("utf-8", errors="replace").strip())
    except KeyboardInterrupt:
        print("\nStopped")
        return 0
    except (serial.SerialException, OSError) as exc:
        print(f"Serial error: {exc}", file=sys.stderr)
        return 1
    finally:
        if ser is not None:
            ser.close()
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass  # The window may already have been closed by the user.


if __name__ == "__main__":
    raise SystemExit(main())
