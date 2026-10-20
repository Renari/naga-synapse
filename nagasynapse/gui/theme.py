"""Dark, Synapse-inspired look."""

from importlib import resources

from PySide6.QtGui import QColor, QPalette

ASSETS = str(resources.files("nagasynapse") / "assets")

ACCENT = "#44d62c"
ACCENT_DIM = "#2f9a1e"
HYPERSHIFT = "#f5a623"
BG = "#0d0d0d"
PANEL = "#161616"
PANEL_2 = "#1e1e1e"
BORDER = "#2a2a2a"
TEXT = "#e6e6e6"
TEXT_DIM = "#8a8a8a"
DANGER = "#ff4d4d"

STYLE = f"""
* {{
    color: {TEXT};
    font-size: 10pt;
}}
QMainWindow, QWidget#Root {{
    background: {BG};
}}
QWidget#Header {{
    background: #050505;
    border-bottom: 1px solid {BORDER};
}}
QLabel#Brand {{
    color: {ACCENT};
    font-size: 15pt;
    font-weight: 800;
    letter-spacing: 3px;
}}
QLabel#DeviceName {{
    font-size: 12pt;
    font-weight: 700;
    letter-spacing: 2px;
}}
QLabel#Dim, QLabel[dim="true"] {{
    color: {TEXT_DIM};
}}
QLabel#SectionTitle {{
    color: {TEXT_DIM};
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 2px;
}}
QLabel#PanelTitle {{
    font-size: 13pt;
    font-weight: 700;
}}
QLabel#Accent {{
    color: {ACCENT};
}}
QLabel#Warning {{
    color: {HYPERSHIFT};
}}
QPushButton#Tab {{
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
    padding: 10px 18px 8px 18px;
    color: {TEXT_DIM};
    font-weight: 700;
    letter-spacing: 2px;
}}
QPushButton#Tab:hover {{
    color: {TEXT};
}}
QPushButton#Tab:checked {{
    color: {TEXT};
    border-bottom: 3px solid {ACCENT};
}}
QFrame#Panel, QWidget#Panel {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#Card {{
    background: {PANEL_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#Card[active="true"] {{
    border: 1px solid {ACCENT};
}}
QPushButton {{
    background: {PANEL_2};
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 7px 14px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background: #101010;
}}
QPushButton:disabled {{
    color: #555;
    border-color: #2a2a2a;
}}
QPushButton#Primary {{
    background: {ACCENT};
    color: #000;
    border: none;
    font-weight: 700;
}}
QPushButton#Primary:hover {{
    background: #5ff046;
}}
QPushButton#Primary:disabled {{
    background: #24461e;
    color: #6b6b6b;
}}
QPushButton#Danger:hover {{
    border-color: {DANGER};
    color: {DANGER};
}}
QPushButton#Segment {{
    border-radius: 0px;
    padding: 6px 16px;
    font-weight: 600;
}}
QPushButton#Segment:checked {{
    background: {ACCENT};
    color: #000;
    border-color: {ACCENT};
}}
QPushButton#Segment[hypershift="true"]:checked {{
    background: {HYPERSHIFT};
    border-color: {HYPERSHIFT};
}}
QPushButton#Chip {{
    text-align: left;
    padding: 6px 10px;
    border-radius: 5px;
    background: #121212;
    border: 1px solid #262626;
    font-size: 9pt;
}}
QPushButton#Chip:hover {{
    border-color: #555;
}}
QPushButton#Chip:checked {{
    background: #1f3a19;
    border: 1px solid {ACCENT};
    font-weight: 700;
}}
QPushButton#Record {{
    border-color: #803030;
}}
QPushButton#Record:checked {{
    background: {DANGER};
    color: #000;
    font-weight: 700;
}}
QPushButton#Flat {{
    background: transparent;
    border: none;
    padding: 4px 8px;
    color: {TEXT_DIM};
}}
QPushButton#Flat:hover {{
    color: {TEXT};
}}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{
    background: #0a0a0a;
    border: 1px solid #333;
    border-radius: 5px;
    padding: 5px 8px;
    selection-background-color: {ACCENT};
    selection-color: #000;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}
QLineEdit#KeyCapture {{
    font-weight: 700;
    font-size: 11pt;
    padding: 9px;
}}
QComboBox QAbstractItemView {{
    background: #121212;
    border: 1px solid #333;
    selection-background-color: #26401f;
    selection-color: {TEXT};
    outline: none;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    image: url({ASSETS}/down.svg);
    width: 10px;
    height: 6px;
}}
QSpinBox {{
    padding-right: 20px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border;
    width: 18px;
    border: none;
    background: transparent;
}}
QSpinBox::up-button {{
    subcontrol-position: top right;
}}
QSpinBox::down-button {{
    subcontrol-position: bottom right;
}}
QSpinBox::up-arrow {{
    image: url({ASSETS}/up.svg);
    width: 9px;
    height: 6px;
}}
QSpinBox::down-arrow {{
    image: url({ASSETS}/down.svg);
    width: 9px;
    height: 6px;
}}
QPushButton::menu-indicator {{
    image: none;
    width: 0px;
}}
QListWidget, QTreeWidget, QTableWidget {{
    background: #0f0f0f;
    border: 1px solid {BORDER};
    border-radius: 6px;
    outline: none;
    alternate-background-color: #131313;
}}
QListWidget::item {{
    padding: 8px 10px;
    border-radius: 4px;
}}
QListWidget::item:hover {{
    background: #1b1b1b;
}}
QListWidget::item:selected, QTableWidget::item:selected, QTreeWidget::item:selected {{
    background: #1f3a19;
    color: {TEXT};
}}
QListWidget#CategoryList::item {{
    padding: 9px 12px;
}}
QListWidget#CategoryList::item:selected {{
    background: #1f3a19;
    border-left: 3px solid {ACCENT};
}}
QHeaderView::section {{
    background: #141414;
    color: {TEXT_DIM};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    font-weight: 700;
}}
QTableWidget {{
    gridline-color: transparent;
}}
QTableWidget::item {{
    padding: 4px;
}}
QCheckBox, QRadioButton {{
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
}}
QCheckBox::indicator {{
    border: 1px solid #555;
    border-radius: 3px;
    background: #0a0a0a;
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QRadioButton::indicator {{
    border: 1px solid #555;
    border-radius: 8px;
    background: #0a0a0a;
}}
QRadioButton::indicator:checked {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 {ACCENT}, stop:0.55 {ACCENT}, stop:0.65 #0a0a0a, stop:1 #0a0a0a);
    border-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: #333;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {TEXT};
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}
QProgressBar {{
    background: #0a0a0a;
    border: 1px solid {BORDER};
    border-radius: 4px;
    height: 8px;
    text-align: center;
    font-size: 8pt;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: #333;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
}}
QStatusBar {{
    background: #050505;
    color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
}}
QMenu {{
    background: #141414;
    border: 1px solid #333;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 22px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: #1f3a19;
}}
QMenu::separator {{
    height: 1px;
    background: #2a2a2a;
    margin: 4px 8px;
}}
QToolTip {{
    background: #1a1a1a;
    color: {TEXT};
    border: 1px solid #444;
    padding: 4px;
}}
QMessageBox, QDialog, QInputDialog {{
    background: {PANEL};
}}
"""


def apply(app) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Base, QColor("#0a0a0a"))
    pal.setColor(QPalette.AlternateBase, QColor("#131313"))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor(PANEL_2))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("#000"))
    pal.setColor(QPalette.ToolTipBase, QColor("#1a1a1a"))
    pal.setColor(QPalette.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.PlaceholderText, QColor("#666"))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
