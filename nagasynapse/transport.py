"""Low level transport: Razer 90-byte feature reports over Linux hidraw.

Report layout (shared by every modern Razer device):

    0      status            (0 new, 1 busy, 2 ok, 3 fail, 4 timeout, 5 unsupported)
    1      transaction id    (0x1f for the Naga V2 Pro and Naga Pro)
    2..3   remaining packets (big endian)
    4      protocol type     (always 0)
    5      data size
    6      command class
    7      command id        (bit 7 set = read)
    8..87  arguments         (80 bytes)
    88     crc               (xor of bytes 2..87)
    89     reserved
"""

from __future__ import annotations

import errno
import fcntl
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

REPORT_LEN = 90
ARGS_LEN = 80

STATUS_NEW = 0x00
STATUS_BUSY = 0x01
STATUS_OK = 0x02
STATUS_FAIL = 0x03
STATUS_TIMEOUT = 0x04
STATUS_UNSUPPORTED = 0x05

STATUS_NAMES = {
    STATUS_NEW: "new",
    STATUS_BUSY: "busy",
    STATUS_OK: "ok",
    STATUS_FAIL: "fail",
    STATUS_TIMEOUT: "timeout",
    STATUS_UNSUPPORTED: "unsupported",
}

RAZER_VID = 0x1532

# product id -> (name, transaction id)
SUPPORTED_DEVICES = {
    0x00A7: ("Razer Naga V2 Pro (Wired)", 0x1F),
    0x00A8: ("Razer Naga V2 Pro (Wireless)", 0x1F),
    0x008F: ("Razer Naga Pro (Wired)", 0x1F),
    0x0090: ("Razer Naga Pro (Wireless)", 0x1F),
}


def _ioc(direction: int, type_: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (type_ << 8) | nr


_IOC_WRITE = 1
_IOC_READ = 2


def HIDIOCSFEATURE(length: int) -> int:
    return _ioc(_IOC_WRITE | _IOC_READ, ord("H"), 0x06, length)


def HIDIOCGFEATURE(length: int) -> int:
    return _ioc(_IOC_WRITE | _IOC_READ, ord("H"), 0x07, length)


class RazerError(Exception):
    """A command was rejected by the device or could not be delivered."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class DeviceNotFound(RazerError):
    pass


class DeviceDisconnected(RazerError):
    pass


def crc(report: bytes | bytearray) -> int:
    value = 0
    for b in report[2:88]:
        value ^= b
    return value


def build_report(transaction_id: int, command_class: int, command_id: int,
                 args: bytes = b"", data_size: int | None = None) -> bytearray:
    if len(args) > ARGS_LEN:
        raise ValueError(f"arguments too long ({len(args)} > {ARGS_LEN})")
    report = bytearray(REPORT_LEN)
    report[1] = transaction_id
    report[5] = len(args) if data_size is None else data_size
    report[6] = command_class
    report[7] = command_id
    report[8:8 + len(args)] = args
    report[88] = crc(report)
    return report


@dataclass
class Response:
    status: int
    transaction_id: int
    data_size: int
    command_class: int
    command_id: int
    args: bytes
    raw: bytes

    @classmethod
    def parse(cls, raw: bytes) -> "Response":
        return cls(
            status=raw[0],
            transaction_id=raw[1],
            data_size=raw[5],
            command_class=raw[6],
            command_id=raw[7],
            args=bytes(raw[8:88]),
            raw=bytes(raw),
        )


@dataclass
class HidrawInfo:
    path: str
    vid: int
    pid: int
    interface: int
    name: str


def _read_uevent(path: Path) -> dict[str, str]:
    values = {}
    try:
        for line in path.read_text().splitlines():
            key, _, value = line.partition("=")
            values[key] = value
    except OSError:
        pass
    return values


def find_control_interfaces() -> list[HidrawInfo]:
    """Find the hidraw node of each supported mouse's control interface.

    The control interface is the one whose report descriptor declares the
    vendor-defined (usage page 0xFF00) 90 byte feature report.
    """
    found = []
    for node in sorted(Path("/sys/class/hidraw").glob("hidraw*")):
        uevent = _read_uevent(node / "device" / "uevent")
        hid_id = uevent.get("HID_ID", "")
        try:
            _bus, vid, pid = (int(x, 16) for x in hid_id.split(":"))
        except ValueError:
            continue
        if vid != RAZER_VID or pid not in SUPPORTED_DEVICES:
            continue
        try:
            descriptor = (node / "device" / "report_descriptor").read_bytes()
        except OSError:
            continue
        # Usage Page (Vendor 0xFF00) ... Report Count (90) ... Feature
        if b"\x06\x00\xff" not in descriptor or b"\x95\x5a\xb1" not in descriptor:
            continue
        phys = uevent.get("HID_PHYS", "")
        interface = int(phys.rsplit("input", 1)[-1]) if "input" in phys else -1
        found.append(HidrawInfo(
            path=f"/dev/{node.name}", vid=vid, pid=pid, interface=interface,
            name=SUPPORTED_DEVICES[pid][0],
        ))
    return found


class HidrawTransport:
    """Sends commands to the device and waits for their responses."""

    def __init__(self, path: str, transaction_id: int = 0x1F):
        self.path = path
        self.transaction_id = transaction_id
        self.fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        # Serialise access between our own processes (GUI + CLI).
        lock_dir = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
        self._lock_fd = os.open(lock_dir / f"nagasynapse-{Path(path).name}.lock",
                                os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        self.trace = False
        self._lock = threading.RLock()

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            os.close(self._lock_fd)
            self.fd = -1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _set_feature(self, report: bytes) -> None:
        buf = bytearray(b"\x00" + report)
        fcntl.ioctl(self.fd, HIDIOCSFEATURE(len(buf)), buf, True)

    def _get_feature(self) -> bytes:
        buf = bytearray(REPORT_LEN + 1)
        fcntl.ioctl(self.fd, HIDIOCGFEATURE(len(buf)), buf, True)
        return bytes(buf[1:])

    def command(self, command_class: int, command_id: int, args: bytes = b"",
                data_size: int | None = None, *, timeout: float = 2.0,
                check: bool = True) -> Response:
        report = build_report(self.transaction_id, command_class, command_id,
                              args, data_size)
        if self.fd < 0:
            raise DeviceDisconnected("device is closed")
        try:
            with self._lock:
                return self._command(report, command_class, command_id, args,
                                     timeout, check)
        except OSError as exc:
            if exc.errno in (errno.ENODEV, errno.ENOENT, errno.ESHUTDOWN, errno.EIO,
                             errno.EPIPE, errno.ETIMEDOUT, errno.EBADF):
                raise DeviceDisconnected(f"lost connection to the mouse ({exc.strerror})") from exc
            raise

    def _command(self, report: bytearray, command_class: int, command_id: int,
                 args: bytes, timeout: float, check: bool) -> Response:
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
        try:
            if self.trace:
                print(f">> {report[:8 + max(len(args), 8)].hex(' ')}")
            for attempt in range(3):
                try:
                    self._set_feature(report)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EPIPE, errno.EIO, errno.ETIMEDOUT) or attempt == 2:
                        raise
                    time.sleep(0.05)
            deadline = time.monotonic() + timeout
            delay = 0.002
            while True:
                time.sleep(delay)
                raw = self._get_feature()
                resp = Response.parse(raw)
                if resp.command_class != command_class or resp.command_id != command_id:
                    # Another program (e.g. openrazer) talked to the device in
                    # between; resend our request.
                    if time.monotonic() > deadline:
                        raise RazerError("response does not match request")
                    self._set_feature(report)
                    continue
                if resp.status in (STATUS_BUSY, STATUS_NEW) and time.monotonic() < deadline:
                    delay = min(delay * 1.5, 0.05)
                    continue
                break
        finally:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        if self.trace:
            print(f"<< [{STATUS_NAMES.get(resp.status, resp.status)}] "
                  f"{resp.raw[:8 + max(resp.data_size, 8)].hex(' ')}")
        if check and resp.status != STATUS_OK:
            name = STATUS_NAMES.get(resp.status, hex(resp.status))
            raise RazerError(
                f"command {command_class:02x}:{command_id:02x} failed: {name}",
                resp.status)
        return resp


def open_device(path: str | None = None) -> tuple[HidrawTransport, HidrawInfo]:
    candidates = find_control_interfaces()
    if path:
        candidates = [c for c in candidates if c.path == path] or [
            HidrawInfo(path, RAZER_VID, 0x00A7, 0, "Razer Naga V2 Pro")]
    if not candidates:
        raise DeviceNotFound("No supported Razer Naga found. Is it plugged in?")
    info = candidates[0]
    tid = SUPPORTED_DEVICES.get(info.pid, ("", 0x1F))[1]
    try:
        return HidrawTransport(info.path, tid), info
    except PermissionError as exc:
        raise DeviceNotFound(
            f"Permission denied opening {info.path}. Install the udev rule "
            f"(see README) and replug the mouse.") from exc
