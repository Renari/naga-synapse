"""GUI entry point: nagasynapse."""

from __future__ import annotations

import argparse
import signal
import sys
from importlib import resources

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import theme
from .controller import Controller
from .main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nagasynapse",
                                     description="Razer Naga V2 Pro configurator")
    parser.add_argument("--device", help="hidraw node (auto-detected by default)")
    args, qt_args = parser.parse_known_args(argv)

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Naga Synapse")
    app.setOrganizationName("nagasynapse")
    app.setDesktopFileName("nagasynapse")
    icon_path = resources.files("nagasynapse") / "assets" / "nagasynapse.svg"
    app.setWindowIcon(QIcon(str(icon_path)))
    theme.apply(app)

    ctl = Controller(args.device)
    window = MainWindow(ctl)
    window.show()
    ctl.connect_device()
    signal.signal(signal.SIGINT, lambda *_: window.close())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
