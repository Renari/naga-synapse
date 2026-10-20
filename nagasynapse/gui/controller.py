"""Application state + device access on a background thread."""

from __future__ import annotations

import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from PySide6.QtCore import QObject, QSocketNotifier, QTimer, Signal

from ..actions import Action
from ..device import DeviceInfo, FlashUsage, NagaDevice, ProfileData
from ..layout import PLATE_BY_VALUE, default_action
from ..macros import Macro
from ..transport import (DeviceDisconnected, DeviceNotFound, RazerError,
                         find_event_interface)


class _Bridge(QObject):
    done = Signal(object, object, object, bool)  # callback, result, error, quiet
    progress = Signal(str, float)


class Controller(QObject):
    connectionChanged = Signal(bool, str)
    infoChanged = Signal()
    profilesChanged = Signal()
    profileLoaded = Signal(int)
    bindingChanged = Signal(int, int, int)      # slot, button, layer
    performanceChanged = Signal(int)
    macrosChanged = Signal()
    flashChanged = Signal()
    busyChanged = Signal(bool)
    progress = Signal(str, float)
    status = Signal(str)
    error = Signal(str)
    currentSlotChanged = Signal(int)
    plateChanged = Signal(object)   # "side2" / "side6" / "side12", or None

    def __init__(self, device_path: str | None = None):
        super().__init__()
        self.device_path = device_path
        self.dev: NagaDevice | None = None
        self.info: DeviceInfo | None = None
        self.enabled: list[int] = []
        self.active: int = 1
        self.names: dict[int, str] = {}
        self.profiles: dict[int, ProfileData] = {}
        self.macros: dict[int, Macro] = {}
        self.flash: FlashUsage | None = None
        self.power: tuple[int, int] | None = None   # idle seconds, low battery %
        self.current_slot: int = 1
        self.plate: str | None = None        # attached side plate, if the mouse reports it
        self.plate_supported = False
        self._event_fd = -1
        self._event_notifier: QSocketNotifier | None = None
        self._pending = 0
        self._connecting = False

        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="naga")
        self._bridge = _Bridge()
        self._bridge.done.connect(self._dispatch)
        self._bridge.progress.connect(self.progress)

        self._reconnect = QTimer(self)
        self._reconnect.setInterval(2000)
        self._reconnect.timeout.connect(self.connect_device)
        self._battery = QTimer(self)
        self._battery.setInterval(3000)
        self._battery.timeout.connect(self._poll)
        self._ticks = 0

    # ----------------------------------------------------------- plumbing
    @property
    def connected(self) -> bool:
        return self.dev is not None

    @property
    def busy(self) -> bool:
        return self._pending > 0

    def report_progress(self, msg: str, frac: float) -> None:
        """Thread-safe progress callback for long device operations."""
        self._bridge.progress.emit(msg, frac)

    def run(self, fn: Callable[[NagaDevice], Any],
            on_done: Callable[[Any], None] | None = None,
            on_error: Callable[[Exception], None] | None = None,
            needs_device: bool = True, quiet: bool = False) -> None:
        """Run fn(device) on the worker thread; callbacks run on the GUI thread.

        quiet jobs (background polling) don't mark the app as busy."""
        if needs_device and self.dev is None:
            if not quiet:
                self.error.emit("The mouse is not connected.")
            return
        if not quiet:
            self._pending += 1
            if self._pending == 1:
                self.busyChanged.emit(True)
        dev = self.dev

        def job():
            try:
                result = fn(dev)
            except Exception as exc:  # noqa: BLE001 - forwarded to the UI
                if not isinstance(exc, RazerError):
                    traceback.print_exc()
                self._bridge.done.emit(None, None, (on_error, exc), quiet)
            else:
                self._bridge.done.emit(on_done, result, None, quiet)

        self._pool.submit(job)

    def _dispatch(self, callback, result, err, quiet) -> None:
        if not quiet:
            self._pending -= 1
            if self._pending == 0:
                self.busyChanged.emit(False)
        if err is not None:
            on_error, exc = err
            if isinstance(exc, DeviceDisconnected):
                self._lost_device(str(exc))
                return
            if on_error:
                on_error(exc)
            else:
                self.error.emit(str(exc))
            return
        if callback:
            callback(result)

    def shutdown(self) -> None:
        self._stop_events()
        self._reconnect.stop()
        self._battery.stop()
        self._pool.shutdown(wait=True, cancel_futures=True)
        if self.dev:
            self.dev.close()
            self.dev = None

    # --------------------------------------------------------- connection
    def connect_device(self) -> None:
        if self.dev is not None or self._connecting:
            return
        self._connecting = True
        path = self.device_path

        def work(_):
            dev = NagaDevice.open(path)
            try:
                info = dev.device_info()
                enabled = dev.profiles()
                active = dev.active_profile()
                names = {slot: dev.profile_name(slot) or "" for slot in enabled}
                macros = {m.id: m for m in dev.read_macros()}
                flash = dev.flash_usage()
                try:
                    power = (dev.idle_time(), dev.low_battery_threshold())
                except RazerError:
                    power = None
                try:
                    plate = (True, dev.side_plate())
                except RazerError:
                    plate = (False, None)
            except Exception:
                dev.close()
                raise
            return dev, info, enabled, active, names, macros, flash, power, plate

        def done(result):
            self._connecting = False
            (self.dev, self.info, self.enabled, self.active, self.names,
             self.macros, self.flash, self.power, plate) = result
            self.plate_supported, self.plate = plate
            self._reconnect.stop()
            self._battery.start()
            self.profiles.clear()
            if self.active in self.enabled:
                self.current_slot = self.active
            else:
                self.current_slot = self.enabled[0] if self.enabled else 1
            self.connectionChanged.emit(True, "")
            self.infoChanged.emit()
            self.profilesChanged.emit()
            self.macrosChanged.emit()
            self.flashChanged.emit()
            self.plateChanged.emit(self.plate)
            self._watch_events()
            self.currentSlotChanged.emit(self.current_slot)
            self.load_profile(self.current_slot)

        def failed(exc):
            self._connecting = False
            msg = str(exc)
            if isinstance(exc, PermissionError) or "Permission" in msg:
                msg = ("Permission denied opening the mouse. Install the udev rule "
                       "from the README and replug the mouse.")
            elif not isinstance(exc, DeviceNotFound):
                msg = f"Could not talk to the mouse: {msg}"
            self.connectionChanged.emit(False, msg)
            if not self._reconnect.isActive():
                self._reconnect.start()

        self.run(work, done, failed, needs_device=False, quiet=True)

    def _lost_device(self, msg: str) -> None:
        if self.dev is None:
            return
        dev, self.dev = self.dev, None

        def close():
            try:
                dev.close()
            except OSError:
                pass

        # Close on the worker thread so it cannot race an in-flight command.
        self._pool.submit(close)
        self._stop_events()
        self.profiles.clear()
        self._battery.stop()
        self.connectionChanged.emit(False, msg or "The mouse was disconnected.")
        self._reconnect.start()

    # ------------------------------------------------- mouse notifications
    def _watch_events(self) -> None:
        """Listen for the mouse's own notifications, so a side-plate swap
        shows at once instead of on the next poll."""
        self._stop_events()
        path = find_event_interface(self.dev.hid) if self.dev else None
        if not path:
            return
        try:
            self._event_fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        except OSError:
            return
        self._event_notifier = QSocketNotifier(self._event_fd, QSocketNotifier.Type.Read, self)
        self._event_notifier.activated.connect(self._read_events)

    def _stop_events(self) -> None:
        if self._event_notifier is not None:
            self._event_notifier.setEnabled(False)
            self._event_notifier.deleteLater()
            self._event_notifier = None
        if self._event_fd >= 0:
            os.close(self._event_fd)
            self._event_fd = -1

    def _read_events(self, *_args) -> None:
        while self._event_fd >= 0:
            try:
                data = os.read(self._event_fd, 64)
            except BlockingIOError:
                return
            except OSError:  # unplugged; the command channel notices too
                self._stop_events()
                return
            if len(data) >= 3 and data[0] == 0x05 and data[1] == 0x0E:
                plate = PLATE_BY_VALUE.get(data[2])
                self.plate_supported = True
                if plate != self.plate:
                    self.plate = plate
                    self.plateChanged.emit(plate)

    def _poll(self) -> None:
        """Track changes made on the mouse itself (profile button, side plate,
        battery)."""
        if not self.dev or self.busy:
            return
        self._ticks += 1
        with_battery = self._ticks % 20 == 0
        with_plate = self.plate_supported

        def work(dev):
            return (dev.active_profile(), dev.battery() if with_battery else None,
                    dev.side_plate() if with_plate else self.plate)

        def done(result):
            active, battery, plate = result
            if active != self.active:
                self.active = active
                self.profilesChanged.emit()
            if plate != self.plate:
                self.plate = plate
                self.plateChanged.emit(plate)
            if battery and self.info:
                self.info.battery, self.info.charging = battery
                self.infoChanged.emit()

        self.run(work, done, lambda e: None, quiet=True)

    # ----------------------------------------------------------- profiles
    def profile_title(self, slot: int) -> str:
        return self.names.get(slot) or f"Profile {slot}"

    def set_current_slot(self, slot: int) -> None:
        if slot == self.current_slot and slot in self.profiles:
            return
        self.current_slot = slot
        self.currentSlotChanged.emit(slot)
        if slot not in self.profiles:
            self.load_profile(slot)
        else:
            self.profileLoaded.emit(slot)

    def load_profile(self, slot: int) -> None:
        def work(dev):
            return dev.read_profile(slot, progress=self.report_progress)

        def done(data: ProfileData):
            data.name = self.names.get(slot, data.name)
            self.profiles[slot] = data
            self.profileLoaded.emit(slot)

        self.run(work, done)

    def refresh_profiles(self, then: Callable[[], None] | None = None) -> None:
        def work(dev):
            enabled = dev.profiles()
            return enabled, dev.active_profile(), \
                {s: dev.profile_name(s) or "" for s in enabled}, dev.flash_usage()

        def done(result):
            self.enabled, self.active, self.names, self.flash = result
            for slot in list(self.profiles):
                if slot not in self.enabled:
                    del self.profiles[slot]
            self.profilesChanged.emit()
            self.flashChanged.emit()
            if self.current_slot not in self.enabled and self.enabled:
                self.set_current_slot(self.active if self.active in self.enabled
                                      else self.enabled[0])
            if then:
                then()

        self.run(work, done)

    def activate_profile(self, slot: int) -> None:
        def work(dev):
            dev.set_active_profile(slot)
            return dev.active_profile()

        def done(active):
            self.active = active
            self.profilesChanged.emit()
            self.status.emit(f"{self.profile_title(slot)} is now active on the mouse")

        self.run(work, done)

    def create_profile(self, slot: int, name: str, copy_from: int | None = None) -> None:
        def work(dev):
            dev.create_profile(slot)
            if copy_from:
                src = dev.read_profile(copy_from, progress=self.report_progress)
                src.name = name
                dev.write_profile(slot, src, progress=self.report_progress)
            else:
                dev.init_profile(slot, progress=self.report_progress)
                if name:
                    dev.set_profile_name(slot, name)

        def done(_):
            self.profiles.pop(slot, None)
            self.status.emit(f"Created {name or f'Profile {slot}'}")
            self.refresh_profiles(lambda: self.set_current_slot(slot))

        self.run(work, done)

    def delete_profile(self, slot: int) -> None:
        def work(dev):
            dev.delete_profile(slot)

        def done(_):
            self.profiles.pop(slot, None)
            self.status.emit(f"Deleted profile {slot}")
            self.refresh_profiles()

        self.run(work, done)

    def rename_profile(self, slot: int, name: str) -> None:
        def work(dev):
            dev.set_profile_name(slot, name)
            return dev.flash_usage()

        def done(flash):
            self.names[slot] = name
            if slot in self.profiles:
                self.profiles[slot].name = name
            self.flash = flash
            self.profilesChanged.emit()
            self.flashChanged.emit()
            self.status.emit(f"Renamed profile {slot} to {name}")

        self.run(work, done)

    def reset_profile(self, slot: int) -> None:
        def work(dev):
            dev.reset_profile_bindings(slot, progress=self.report_progress)

        def done(_):
            self.status.emit(f"Restored default buttons on {self.profile_title(slot)}")
            self.load_profile(slot)

        self.run(work, done)

    def write_profile_data(self, slot: int, data: ProfileData,
                           macro_map: dict[int, int] | None = None,
                           then: Callable[[], None] | None = None) -> None:
        def work(dev):
            dev.write_profile(slot, data, progress=self.report_progress,
                              macro_map=macro_map)

        def done(_):
            self.profiles.pop(slot, None)
            if data.name:
                self.names[slot] = data.name
            self.refresh_profiles(lambda: (self.load_profile(slot), then and then()))

        self.run(work, done)

    # ----------------------------------------------------------- bindings
    def set_binding(self, slot: int, button: int, layer: int, action: Action) -> None:
        def work(dev):
            dev.set_binding(slot, button, layer, action)
            return dev.get_binding(slot, button, layer)

        def done(stored: Action):
            if slot in self.profiles:
                self.profiles[slot].bindings[(button, layer)] = stored
            self.bindingChanged.emit(slot, button, layer)
            self.status.emit("Saved to onboard memory")

        self.run(work, done)

    # -------------------------------------------------------- performance
    def set_dpi_stages(self, slot: int, stages: list[tuple[int, int]], active: int) -> None:
        def work(dev):
            dev.set_dpi_stages(slot, stages, active)
            return dev.get_dpi_stages(slot)

        def done(result):
            if slot in self.profiles:
                self.profiles[slot].dpi_stages, self.profiles[slot].dpi_active = result
            self.performanceChanged.emit(slot)
            self.status.emit("Sensitivity stages saved")

        self.run(work, done)

    def set_lift_off(self, slot: int, value: int) -> None:
        def work(dev):
            dev.set_lift_off(slot, value)
            return dev.lift_off(slot)

        def done(stored):
            if slot in self.profiles:
                self.profiles[slot].lift_off = stored
            self.performanceChanged.emit(slot)
            self.status.emit("Lift-off distance saved")

        self.run(work, done)

    def set_polling(self, slot: int, interval: int) -> None:
        def work(dev):
            dev.set_polling_interval(slot, interval)
            return dev.get_polling_interval(slot)

        def done(value):
            if slot in self.profiles:
                self.profiles[slot].polling_interval = value
            self.performanceChanged.emit(slot)
            self.status.emit("Polling rate saved")

        self.run(work, done)

    def set_power(self, idle_seconds: int, low_battery: int) -> None:
        def work(dev):
            dev.set_idle_time(idle_seconds)
            dev.set_low_battery_threshold(low_battery)
            return dev.idle_time(), dev.low_battery_threshold()

        def done(power):
            self.power = power
            self.status.emit("Power settings saved")

        self.run(work, done)

    # ------------------------------------------------------------- macros
    def macro_names(self) -> dict[int, str]:
        return {mid: m.name for mid, m in self.macros.items()}

    def macro_usage(self, macro_id: int) -> list[tuple[int, int, int]]:
        """(slot, button, layer) of loaded profiles that use a macro."""
        uses = []
        for slot, data in self.profiles.items():
            for (button, layer), action in data.bindings.items():
                if action.macro_id == macro_id:
                    uses.append((slot, button, layer))
        return uses

    def save_macro(self, macro: Macro, then: Callable[[int], None] | None = None) -> None:
        def work(dev):
            mid = dev.write_macro(macro, progress=self.report_progress)
            return mid, dev.read_macro(mid), dev.flash_usage()

        def done(result):
            mid, stored, flash = result
            self.macros[mid] = stored
            self.flash = flash
            self.macrosChanged.emit()
            self.flashChanged.emit()
            self.status.emit(f"Macro “{stored.name}” saved to the mouse")
            if then:
                then(mid)

        self.run(work, done)

    def delete_macro(self, macro_id: int) -> None:
        """Delete a macro and reset every button (in any profile) bound to it."""
        cached = {slot: dict(data.bindings) for slot, data in self.profiles.items()}

        def work(dev):
            changed = []
            for slot in dev.profiles():
                if slot in cached:
                    bindings = cached[slot]
                else:
                    bindings = dev.read_profile(slot, progress=self.report_progress).bindings
                for (button, layer), action in bindings.items():
                    if action.macro_id == macro_id:
                        dev.set_binding(slot, button, layer, default_action(button))
                        changed.append((slot, button, layer))
            dev.delete_macro(macro_id)
            return changed, dev.flash_usage()

        def done(result):
            changed, flash = result
            self.macros.pop(macro_id, None)
            self.flash = flash
            for slot, button, layer in changed:
                if slot in self.profiles:
                    self.profiles[slot].bindings[(button, layer)] = default_action(button)
                self.bindingChanged.emit(slot, button, layer)
            self.macrosChanged.emit()
            self.flashChanged.emit()
            self.status.emit("Macro deleted")

        self.run(work, done)

    def compact_flash(self) -> None:
        def work(dev):
            path = dev.compact_flash(progress=self.report_progress)
            return path, dev.flash_usage()

        def done(result):
            path, self.flash = result
            self.flashChanged.emit()
            self.status.emit(f"Onboard memory compacted (backup: {path})")

        self.run(work, done)

    # ------------------------------------------------------ import/export
    def export_profile(self, slot: int, path: str) -> None:
        import json
        from pathlib import Path

        def work(dev):
            data = dev.read_profile(slot, progress=self.report_progress)
            data.name = self.names.get(slot, data.name)
            obj = data.to_json()
            ids = dev.macro_ids()
            used = sorted({a.macro_id for a in data.bindings.values()
                           if a.macro_id is not None and a.macro_id in ids})
            obj["macros"] = [dev.read_macro(mid).to_json() for mid in used]
            Path(path).write_text(json.dumps(obj, indent=2))
            return len(used)

        def done(n):
            self.status.emit(f"Exported {self.profile_title(slot)} "
                             f"({n} macro{'s' if n != 1 else ''}) to {path}")

        self.run(work, done)

    def import_profile(self, slot: int, path: str) -> None:
        import json
        from pathlib import Path

        try:
            obj = json.loads(Path(path).read_text())
            data = ProfileData.from_json(obj, slot)
            macros = [Macro.from_json(m) for m in obj.get("macros", [])]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.error.emit(f"Could not read {path}: {exc}")
            return

        def work(dev):
            macro_map = {}
            for m in macros:
                old = m.id
                m.id = None
                macro_map[old] = dev.write_macro(m, progress=self.report_progress)
            dev.write_profile(slot, data, progress=self.report_progress,
                              macro_map=macro_map)
            return {m.id: dev.read_macro(m.id) for m in macros}, dev.flash_usage()

        def done(result):
            new_macros, self.flash = result
            self.macros.update(new_macros)
            self.profiles.pop(slot, None)
            if data.name:
                self.names[slot] = data.name
            self.macrosChanged.emit()
            self.flashChanged.emit()
            self.status.emit(f"Imported {Path(path).name} into profile {slot}")
            self.refresh_profiles(lambda: self.set_current_slot(slot))

        self.run(work, done)

    def backup_all(self, path: str) -> None:
        import json
        from pathlib import Path

        def work(dev):
            obj = {
                "format": "nagasynapse-backup", "version": 1,
                "active": dev.active_profile(),
                "profiles": {},
                "macros": [m.to_json() for m in dev.read_macros()],
            }
            for slot in dev.profiles():
                data = dev.read_profile(slot, progress=self.report_progress)
                data.name = dev.profile_name(slot) or ""
                obj["profiles"][str(slot)] = data.to_json()
            Path(path).write_text(json.dumps(obj, indent=2))
            return len(obj["profiles"]), len(obj["macros"])

        def done(result):
            self.status.emit(f"Backed up {result[0]} profiles and {result[1]} macros to {path}")

        self.run(work, done)
