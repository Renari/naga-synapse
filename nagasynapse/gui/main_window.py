"""Main application window."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QStackedWidget,
                               QStatusBar, QVBoxLayout, QWidget)

from ..actions import PROFILE_COLORS
from ..layout import PROFILE_COLOR_HEX
from . import theme
from .controller import Controller
from .customize import CustomizePage
from .lighting_page import LightingPage
from .macros_page import MacrosPage
from .performance import PerformancePage
from .profiles_page import ProfilesPage
from .widgets import dim, dot_icon


class DisconnectedPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addStretch(2)
        title = QLabel("Connect your Razer Naga V2 Pro")
        title.setObjectName("PanelTitle")
        title.setStyleSheet("font-size: 18pt;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        self.detail = dim("Looking for the mouse…")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.detail)
        row = QHBoxLayout()
        row.addStretch(1)
        retry = QPushButton("Retry now")
        retry.clicked.connect(ctl.connect_device)
        row.addWidget(retry)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(3)


class MainWindow(QMainWindow):
    TABS = ["CUSTOMIZE", "PERFORMANCE", "LIGHTING", "MACROS", "PROFILES"]

    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        self.settings = QSettings("nagasynapse", "nagasynapse")
        self.setWindowTitle("Naga Synapse — Razer Naga V2 Pro")
        self.resize(1480, 860)
        self.setMinimumSize(1180, 720)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ------------------------------------------------------ header
        header = QWidget()
        header.setObjectName("Header")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(22, 12, 22, 0)
        hl.setSpacing(6)
        top = QHBoxLayout()
        brand = QLabel("NAGA SYNAPSE")
        brand.setObjectName("Brand")
        top.addWidget(brand)
        top.addSpacing(22)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.device_name = QLabel("RAZER NAGA V2 PRO")
        self.device_name.setObjectName("DeviceName")
        col.addWidget(self.device_name)
        self.device_status = dim("Not connected", wrap=False)
        col.addWidget(self.device_status)
        top.addLayout(col)
        top.addStretch(1)
        top.addWidget(QLabel("PROFILE"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(260)
        top.addWidget(self.profile_combo)
        self.active_label = QLabel()
        self.active_label.setMinimumWidth(130)
        top.addWidget(self.active_label)
        self.activate_btn = QPushButton("Make active")
        self.activate_btn.setToolTip("Switch the mouse to this profile now")
        top.addWidget(self.activate_btn)
        hl.addLayout(top)
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.tab_group = QButtonGroup(self)
        for i, name in enumerate(self.TABS):
            b = QPushButton(name)
            b.setObjectName("Tab")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tab_group.addButton(b, i)
            tabs.addWidget(b)
        tabs.addStretch(1)
        hl.addLayout(tabs)
        lay.addWidget(header)

        # ------------------------------------------------------ pages
        self.outer = QStackedWidget()
        self.disconnected = DisconnectedPage(ctl)
        self.outer.addWidget(self.disconnected)
        self.pages = QStackedWidget()
        self.customize = CustomizePage(ctl, self.settings)
        self.performance = PerformancePage(ctl)
        self.lighting = LightingPage(ctl, self.settings)
        self.macros = MacrosPage(ctl)
        self.profiles = ProfilesPage(ctl)
        for page in (self.customize, self.performance, self.lighting, self.macros,
                     self.profiles):
            self.pages.addWidget(page)
        self.outer.addWidget(self.pages)
        lay.addWidget(self.outer, 1)

        # ------------------------------------------------------ status bar
        bar = QStatusBar()
        self.setStatusBar(bar)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setFixedHeight(10)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)
        self.progress.hide()
        self.busy_label = dim("", wrap=False)
        bar.addPermanentWidget(self.busy_label)
        bar.addPermanentWidget(self.progress)

        # ------------------------------------------------------ wiring
        self.tab_group.idClicked.connect(self.pages.setCurrentIndex)
        self.tab_group.button(0).setChecked(True)
        self.profile_combo.activated.connect(self._profile_chosen)
        self.activate_btn.clicked.connect(lambda: ctl.activate_profile(ctl.current_slot))
        self.customize.openMacros.connect(self._open_macros)
        self.profiles.editRequested.connect(self._edit_profile)
        ctl.connectionChanged.connect(self._connection)
        ctl.infoChanged.connect(self._info)
        ctl.profilesChanged.connect(self._profiles)
        ctl.currentSlotChanged.connect(lambda _s: self._profiles())
        ctl.busyChanged.connect(self._busy)
        ctl.progress.connect(self._progress)
        ctl.status.connect(lambda msg: self.statusBar().showMessage(msg, 6000))
        ctl.error.connect(self._error)
        self._connection(False, "Looking for the mouse…")

    # -------------------------------------------------------------- slots
    def _connection(self, connected: bool, message: str) -> None:
        self.outer.setCurrentIndex(1 if connected else 0)
        self.profile_combo.setEnabled(connected)
        self.activate_btn.setEnabled(connected)
        if not connected:
            self.disconnected.detail.setText(message or "Looking for the mouse…")
            self.device_status.setText("Not connected")
            self.active_label.setText("")

    def _info(self) -> None:
        info = self.ctl.info
        if not info:
            return
        name = info.name.replace("Razer ", "").upper()
        self.device_name.setText(f"RAZER {name}")
        parts = [f"<span style='color:{theme.ACCENT}'>●</span> Connected",
                 f"Firmware {info.firmware}"]
        if info.battery is not None:
            parts.append(f"Battery {info.battery}%" + (" ⚡" if info.charging else ""))
        self.device_status.setText(" · ".join(parts))

    def _profiles(self) -> None:
        ctl = self.ctl
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for slot in ctl.enabled:
            self.profile_combo.addItem(dot_icon(PROFILE_COLOR_HEX[slot]),
                                       f"{slot} · {ctl.profile_title(slot)}", slot)
        idx = self.profile_combo.findData(ctl.current_slot)
        self.profile_combo.setCurrentIndex(max(0, idx))
        self.profile_combo.blockSignals(False)
        if ctl.current_slot == ctl.active:
            self.active_label.setText(f"<span style='color:{theme.ACCENT}'>●</span> "
                                      "Active on mouse")
            self.activate_btn.hide()
        else:
            color = PROFILE_COLORS.get(ctl.active, "")
            self.active_label.setText(f"Mouse is using {ctl.active} ({color})")
            self.activate_btn.show()
        self.customize.panel.set_profile_names(ctl.names)

    def _profile_chosen(self, index: int) -> None:
        slot = self.profile_combo.itemData(index)
        if slot is not None:
            self.ctl.set_current_slot(slot)

    def _edit_profile(self, slot: int) -> None:
        self.ctl.set_current_slot(slot)
        self.tab_group.button(0).setChecked(True)
        self.pages.setCurrentIndex(0)

    def _open_macros(self, macro_id) -> None:
        index = self.TABS.index("MACROS")
        self.tab_group.button(index).setChecked(True)
        self.pages.setCurrentIndex(index)
        if macro_id is None:
            self.macros.new_macro()
        else:
            self.macros.open_macro(macro_id)

    def _busy(self, busy: bool) -> None:
        self.busy_label.setText("Working…" if busy else "")
        if not busy:
            self.progress.hide()
        for page in (self.customize.panel, self.performance, self.profiles):
            page.setEnabled(not busy)
        self.macros.save_btn.setEnabled(not busy)

    def _progress(self, msg: str, frac: float) -> None:
        if frac >= 1:
            self.progress.hide()
            return
        self.progress.show()
        self.progress.setValue(int(frac * 1000))
        self.busy_label.setText(msg)

    def _error(self, message: str) -> None:
        QMessageBox.warning(self, "Naga Synapse", message)

    def closeEvent(self, ev) -> None:
        if self.macros.has_unsaved_changes() and QMessageBox.question(
                self, "Unsaved macro",
                "The macro you are editing has unsaved changes. Quit anyway?") \
                != QMessageBox.StandardButton.Yes:
            ev.ignore()
            return
        self.ctl.shutdown()
        ev.accept()
