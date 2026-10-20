"""Command line interface: nagasynapse-cli."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .actions import PROFILE_COLORS, parse_action
from .device import NagaDevice, ProfileData, backup_dir
from .layout import (BUTTONS, GROUP_NAMES, POLLING_RATES, PROFILE_SLOTS,
                     button_label, default_action, find_button, use_model)
from .macros import Macro, parse_steps
from .transport import RazerError

RATE_TO_INTERVAL = {v: k for k, v in POLLING_RATES.items()}


def _slot(dev: NagaDevice, value: int | None) -> int:
    return value if value is not None else dev.active_profile()


def _macro_names(dev: NagaDevice) -> dict[int, str]:
    names = {}
    for mid in dev.macro_ids():
        names[mid] = dev.read_macro(mid).name
    return names


def cmd_info(dev: NagaDevice, args) -> None:
    info = dev.device_info()
    print(f"Device:    {info.name}")
    print(f"Node:      {info.path}")
    print(f"Firmware:  {info.firmware}")
    print(f"Serial:    {info.serial}")
    if info.battery is not None:
        print(f"Battery:   {info.battery}%{' (charging)' if info.charging else ''}")
    usage = dev.flash_usage()
    print(f"Memory:    {usage.used / 1024:.1f} KiB used, {usage.free / 1024:.1f} KiB free, "
          f"{usage.recycled / 1024:.1f} KiB reclaimable")
    print(f"Macros:    {len(dev.macro_ids())}")
    print()
    cmd_profiles(dev, args)


def cmd_profiles(dev: NagaDevice, args) -> None:
    enabled = dev.profiles()
    active = dev.active_profile()
    for slot in PROFILE_SLOTS:
        if slot in enabled:
            name = dev.profile_name(slot) or f"Profile {slot}"
            mark = "*" if slot == active else " "
            print(f" {mark} {slot} [{PROFILE_COLORS[slot]:5}] {name}")
        else:
            print(f"   {slot} [{PROFILE_COLORS[slot]:5}] (empty)")
    print("\n * = active profile")


def cmd_profile(dev: NagaDevice, args) -> None:
    slot = args.slot
    if args.action == "create":
        if slot in dev.profiles():
            sys.exit(f"profile {slot} already exists")
        dev.create_profile(slot)
        if args.copy_from:
            src = dev.read_profile(args.copy_from)
            src.name = args.name or f"{src.name or f'Profile {args.copy_from}'} copy"
            dev.write_profile(slot, src)
        else:
            dev.init_profile(slot)
            if args.name:
                dev.set_profile_name(slot, args.name)
        print(f"created profile {slot}")
    elif args.action == "delete":
        if len(dev.profiles()) <= 1:
            sys.exit("cannot delete the last profile")
        dev.delete_profile(slot)
        print(f"deleted profile {slot}")
    elif args.action == "activate":
        dev.set_active_profile(slot)
        print(f"profile {slot} is now active")
    elif args.action == "rename":
        if not args.name:
            sys.exit("--name is required")
        dev.set_profile_name(slot, args.name)
        print(f"renamed profile {slot} to {args.name!r}")
    elif args.action == "reset":
        dev.reset_profile_bindings(slot)
        print(f"profile {slot} buttons restored to defaults")


def cmd_show(dev: NagaDevice, args) -> None:
    slot = _slot(dev, args.profile)
    names = _macro_names(dev)
    data = dev.read_profile(slot)
    title = data.name or f"Profile {slot}"
    print(f"Profile {slot} ({PROFILE_COLORS.get(slot, 'direct')}): {title}")
    layers = (0, 1) if args.all_layers else ((1,) if args.hypershift else (0,))
    for layer in layers:
        print(f"\n== {'Hypershift' if layer else 'Standard'} layer ==")
        group = None
        for button in BUTTONS:
            if button.group != group:
                group = button.group
                print(f"  -- {GROUP_NAMES[group]} --")
            action = data.binding(button.id, layer)
            marker = "" if action.same_as(default_action(button.id)) else "  *"
            print(f"  {button.name:<22} {action.describe(names)}{marker}")
    print("\n== Performance ==")
    print("  DPI stages: " + ", ".join(
        f"{'[' if i + 1 == data.dpi_active else ''}{x}{'' if x == y else f'x{y}'}"
        f"{']' if i + 1 == data.dpi_active else ''}"
        for i, (x, y) in enumerate(data.dpi_stages)))
    print(f"  Polling rate: {POLLING_RATES.get(data.polling_interval, '?')} Hz")
    print("\n  * = changed from default")


def cmd_bind(dev: NagaDevice, args) -> None:
    slot = _slot(dev, args.profile)
    button = find_button(args.button)
    action = parse_action(args.action)
    if action.macro_id is not None and action.macro_id not in dev.macro_ids():
        sys.exit(f"macro {action.macro_id} does not exist (see `macro list`)")
    layer = 1 if args.hypershift else 0
    dev.set_binding(slot, button, layer, action)
    names = _macro_names(dev) if action.macro_id is not None else {}
    print(f"profile {slot} {'hypershift ' if layer else ''}{button_label(button)} -> "
          f"{action.describe(names)}")


def cmd_unbind(dev: NagaDevice, args) -> None:
    slot = _slot(dev, args.profile)
    button = find_button(args.button)
    layer = 1 if args.hypershift else 0
    dev.set_binding(slot, button, layer, default_action(button))
    print(f"profile {slot} {button_label(button)} restored to "
          f"{default_action(button).describe()}")


def cmd_macro(dev: NagaDevice, args) -> None:
    if args.action == "list":
        ids = dev.macro_ids()
        if not ids:
            print("no macros stored on the mouse")
        for mid in ids:
            m = dev.read_macro(mid)
            print(f"  {mid:>4}  {m.name:<30} {len(m.events):>4} steps  "
                  f"{m.duration_ms() / 1000:.2f}s")
        u = dev.flash_usage()
        print(f"\nonboard memory: {u.free / 1024:.1f} KiB free")
    elif args.action == "show":
        m = dev.read_macro(args.id)
        print(f"Macro {m.id}: {m.name}")
        for i, ev in enumerate(m.events, 1):
            print(f"  {i:>4}. {ev.describe()}")
    elif args.action == "create":
        events = parse_steps(args.steps)
        macro = Macro(name=args.name, events=events)
        _warn_stuck(macro)
        mid = dev.write_macro(macro, progress=_progress)
        print(f"created macro {mid}: {macro.name} ({len(events)} steps)")
    elif args.action == "edit":
        m = dev.read_macro(args.id)
        if args.steps:
            m.events = parse_steps(args.steps)
        if args.name:
            m.name = args.name
        _warn_stuck(m)
        dev.write_macro(m, progress=_progress)
        print(f"updated macro {m.id}")
    elif args.action == "delete":
        dev.delete_macro(args.id)
        print(f"deleted macro {args.id}")
    elif args.action == "export":
        m = dev.read_macro(args.id)
        Path(args.file).write_text(json.dumps(
            {"format": "nagasynapse-macro", "version": 1, **m.to_json()}, indent=2))
        print(f"wrote {args.file}")
    elif args.action == "import":
        obj = json.loads(Path(args.file).read_text())
        m = Macro.from_json(obj)
        m.id = None
        if args.name:
            m.name = args.name
        mid = dev.write_macro(m, progress=_progress)
        print(f"imported macro {mid}: {m.name}")


def _warn_stuck(macro: Macro) -> None:
    stuck = macro.stuck_keys()
    if stuck:
        print(f"warning: these stay pressed when the macro ends: {', '.join(stuck)}",
              file=sys.stderr)


def _progress(msg: str, frac: float) -> None:
    if sys.stderr.isatty():
        print(f"\r\033[K{msg} {frac * 100:3.0f}%", end="\n" if frac >= 1 else "",
              file=sys.stderr, flush=True)


def cmd_dpi(dev: NagaDevice, args) -> None:
    slot = _slot(dev, args.profile)
    stages, active = dev.get_dpi_stages(slot)
    if args.stages:
        stages = []
        for part in args.stages.split(","):
            xy = part.lower().split("x")
            x = int(xy[0])
            stages.append((x, int(xy[1]) if len(xy) > 1 else x))
    if args.active:
        active = args.active
    if args.stages or args.active:
        dev.set_dpi_stages(slot, stages, active)
    print(f"profile {slot} DPI stages: " + ", ".join(
        f"{'*' if i + 1 == active else ''}{x}{'' if x == y else f'x{y}'}"
        for i, (x, y) in enumerate(stages)))


def cmd_poll(dev: NagaDevice, args) -> None:
    slot = _slot(dev, args.profile)
    if args.rate:
        if args.rate not in RATE_TO_INTERVAL:
            sys.exit("rate must be 125, 500 or 1000")
        dev.set_polling_interval(slot, RATE_TO_INTERVAL[args.rate])
    print(f"profile {slot} polling rate: "
          f"{POLLING_RATES.get(dev.get_polling_interval(slot), '?')} Hz")


def _export_profile(dev: NagaDevice, slot: int) -> dict:
    data = dev.read_profile(slot)
    obj = data.to_json()
    macro_ids = sorted({a.macro_id for a in data.bindings.values() if a.macro_id is not None})
    obj["macros"] = [dev.read_macro(mid).to_json() for mid in macro_ids
                     if mid in dev.macro_ids()]
    return obj


def _import_profile(dev: NagaDevice, obj: dict, slot: int) -> None:
    macro_map: dict[int, int] = {}
    for m_obj in obj.get("macros", []):
        m = Macro.from_json(m_obj)
        old_id = m.id
        m.id = None
        macro_map[old_id] = dev.write_macro(m, progress=_progress)
    data = ProfileData.from_json(obj, slot)
    dev.write_profile(slot, data, progress=_progress, macro_map=macro_map)


def cmd_export(dev: NagaDevice, args) -> None:
    slot = _slot(dev, args.profile)
    Path(args.file).write_text(json.dumps(_export_profile(dev, slot), indent=2))
    print(f"exported profile {slot} to {args.file}")


def cmd_import(dev: NagaDevice, args) -> None:
    slot = _slot(dev, args.profile)
    obj = json.loads(Path(args.file).read_text())
    _import_profile(dev, obj, slot)
    print(f"imported {args.file} into profile {slot}")


def _backup_obj(dev: NagaDevice) -> dict:
    profiles = {}
    for slot in dev.profiles():
        data = dev.read_profile(slot, progress=_progress)
        profiles[str(slot)] = data.to_json()
    return {
        "format": "nagasynapse-backup", "version": 1,
        "active": dev.active_profile(),
        "profiles": profiles,
        "macros": [m.to_json() for m in dev.read_macros()],
    }


def cmd_backup(dev: NagaDevice, args) -> None:
    obj = _backup_obj(dev)
    Path(args.file).write_text(json.dumps(obj, indent=2))
    print(f"backed up {len(obj['profiles'])} profiles and {len(obj['macros'])} macros "
          f"to {args.file}")


def cmd_restore(dev: NagaDevice, args) -> None:
    obj = json.loads(Path(args.file).read_text())
    if obj.get("format") != "nagasynapse-backup":
        sys.exit("not a backup file")
    # Parse everything before touching the mouse.
    macros = [Macro.from_json(m) for m in obj["macros"]]
    for m in macros:
        m.encode()
    profiles = {int(k): ProfileData.from_json(v, int(k)) for k, v in obj["profiles"].items()}
    if not profiles or not all(slot in PROFILE_SLOTS for slot in profiles):
        sys.exit("backup has no valid profiles")
    safety = backup_dir() / f"before-restore-{time.strftime('%Y%m%d-%H%M%S')}.json"
    safety.write_text(json.dumps(_backup_obj(dev), indent=2))
    print(f"current state saved to {safety}")
    # Restore macros with their original ids so bindings stay valid.
    for mid in dev.macro_ids():
        dev.delete_macro(mid)
    dev.compact_flash(progress=_progress)
    for m in macros:
        dev.write_macro(m, progress=_progress)
    for slot, data in profiles.items():
        dev.write_profile(slot, data, progress=_progress)
    for slot in dev.profiles():
        if slot not in profiles:
            dev.delete_profile(slot)
    if obj.get("active") in dev.profiles():
        dev.set_active_profile(obj["active"])
    print("restore complete")


def cmd_memory(dev: NagaDevice, args) -> None:
    if args.compact:
        path = dev.compact_flash(progress=_progress)
        print(f"compacted (backup saved to {path})")
    u = dev.flash_usage()
    print(f"total {u.total} B, used {u.used} B, free {u.free} B, reclaimable {u.recycled} B")


def cmd_raw(dev: NagaDevice, args) -> None:
    payload = bytes.fromhex(args.args) if args.args else b""
    resp = dev.t.command(int(args.cls, 16), int(args.cmd, 16), payload,
                         args.size, check=False)
    print(f"status={resp.status} size={resp.data_size} "
          f"{resp.args[:max(resp.data_size, len(payload))].hex(' ')}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nagasynapse-cli",
        description="Configure the onboard memory of the Razer Naga V2 Pro and Naga Pro.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Buttons: left right middle scrollup scrolldown tiltleft tiltright
         scrollmode dpi bottom front rear 6:1..6:6 12:1..12:12 (or 1..12)

Actions: disable | key:ctrl+c | key:f:turbo=50 | mouse:left[:double]
         mouse:wheelup:turbo=20 | macro:ID[:times=N|:hold|:toggle|:sequence]
         dpi:cycle|cycledown|up|down|stage=N|clutch=400 | profile:cycle|next|prev|N
         media:volup|voldown|mute|playpause|next|prev | system:sleep
         hypershift | scrollmode

Macro steps (comma separated): a, ctrl+c, +shift, -shift, 50ms, click:left,
         wheel:-3, text:Hello there, media:mute
""")
    p.add_argument("--device", help="hidraw node (auto-detected by default)")
    p.add_argument("--trace", action="store_true", help="print raw USB traffic")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="device, profile and memory overview")
    sub.add_parser("profiles", help="list onboard profiles")

    sp = sub.add_parser("profile", help="manage onboard profiles")
    sp.add_argument("action", choices=["create", "delete", "activate", "rename", "reset"])
    sp.add_argument("slot", type=int, choices=PROFILE_SLOTS)
    sp.add_argument("--name")
    sp.add_argument("--copy-from", type=int, choices=PROFILE_SLOTS)

    sp = sub.add_parser("show", help="show button assignments")
    sp.add_argument("-p", "--profile", type=int)
    sp.add_argument("--hypershift", action="store_true")
    sp.add_argument("-a", "--all-layers", action="store_true")

    sp = sub.add_parser("bind", help="assign an action to a button")
    sp.add_argument("button")
    sp.add_argument("action")
    sp.add_argument("-p", "--profile", type=int)
    sp.add_argument("--hypershift", action="store_true")

    sp = sub.add_parser("unbind", help="restore a button's default action")
    sp.add_argument("button")
    sp.add_argument("-p", "--profile", type=int)
    sp.add_argument("--hypershift", action="store_true")

    sp = sub.add_parser("macro", help="manage onboard macros")
    msub = sp.add_subparsers(dest="action", required=True)
    msub.add_parser("list")
    m = msub.add_parser("show"); m.add_argument("id", type=int)
    m = msub.add_parser("create"); m.add_argument("name"); m.add_argument("steps")
    m = msub.add_parser("edit"); m.add_argument("id", type=int)
    m.add_argument("--name"); m.add_argument("--steps")
    m = msub.add_parser("delete"); m.add_argument("id", type=int)
    m = msub.add_parser("export"); m.add_argument("id", type=int); m.add_argument("file")
    m = msub.add_parser("import"); m.add_argument("file"); m.add_argument("--name")

    sp = sub.add_parser("dpi", help="show or set DPI stages")
    sp.add_argument("-p", "--profile", type=int)
    sp.add_argument("--stages", help="e.g. 400,800,1600,3200 or 800x600,1600")
    sp.add_argument("--active", type=int, help="active stage (1-based)")

    sp = sub.add_parser("poll", help="show or set polling rate")
    sp.add_argument("rate", nargs="?", type=int)
    sp.add_argument("-p", "--profile", type=int)

    sp = sub.add_parser("export", help="export a profile (with its macros) to JSON")
    sp.add_argument("file"); sp.add_argument("-p", "--profile", type=int)
    sp = sub.add_parser("import", help="import a profile JSON into a slot")
    sp.add_argument("file"); sp.add_argument("-p", "--profile", type=int)
    sp = sub.add_parser("backup", help="save all profiles and macros to a file")
    sp.add_argument("file")
    sp = sub.add_parser("restore", help="restore everything from a backup file")
    sp.add_argument("file")

    sp = sub.add_parser("memory", help="onboard memory usage")
    sp.add_argument("--compact", action="store_true",
                    help="reclaim space left by deleted macros")

    sp = sub.add_parser("raw", help="send a raw command (debugging)")
    sp.add_argument("cls"); sp.add_argument("cmd")
    sp.add_argument("args", nargs="?", default="")
    sp.add_argument("--size", type=int, default=None)
    return p


COMMANDS = {
    "info": cmd_info, "profiles": cmd_profiles, "profile": cmd_profile,
    "show": cmd_show, "bind": cmd_bind, "unbind": cmd_unbind, "macro": cmd_macro,
    "dpi": cmd_dpi, "poll": cmd_poll, "export": cmd_export, "import": cmd_import,
    "backup": cmd_backup, "restore": cmd_restore, "memory": cmd_memory, "raw": cmd_raw,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with NagaDevice.open(args.device) as dev:
            use_model(dev.model.key)
            dev.t.trace = args.trace
            COMMANDS[args.command](dev, args)
    except (RazerError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
