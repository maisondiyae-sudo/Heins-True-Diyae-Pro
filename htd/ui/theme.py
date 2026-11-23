"""
"White spaceship" light theme: silver background, white cards, cyan/blue accents.

Qt style sheets have no box-shadow, so cards get a QGraphicsDropShadowEffect
(see widgets.add_shadow). Colours use 0-255 alpha, which every Qt 6 accepts.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

INK = "#0b1220"
INK_2 = "#46516a"
INK_3 = "#8a94a6"
CYAN = "#00b4d8"
CYAN_HI = "#00d4ff"
BLUE = "#0a84ff"
OK = "#00866f"
WARN = "#9a6200"
ERR = "#b42332"


def light_palette() -> QPalette:
    """Explicit light palette, so the app stays light even when Windows/macOS is in dark mode."""
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "#f3f5f8",
        QPalette.ColorRole.WindowText: INK,
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#f7f9fb",
        QPalette.ColorRole.Text: INK,
        QPalette.ColorRole.Button: "#ffffff",
        QPalette.ColorRole.ButtonText: INK,
        QPalette.ColorRole.Highlight: CYAN,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: "#ffffff",
        QPalette.ColorRole.ToolTipText: INK,
        QPalette.ColorRole.PlaceholderText: INK_3,
        QPalette.ColorRole.Link: BLUE,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(INK_3))
    return palette


STYLESHEET = f"""
QAbstractItemView {{ outline: 0; }}
QWidget {{ color: {INK}; font-size: 13px; }}
QMainWindow, QWidget#Root {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f8f9fb, stop:1 #e6eaf0);
}}
QToolTip {{ background: #ffffff; color: {INK}; border: 1px solid rgba(11,18,32,30); padding: 6px; }}

/* ---- header ---------------------------------------------------------- */
QLabel#AppTitle {{ font-size: 24px; font-weight: 700; }}
QLabel#AppTitle[accent="true"] {{ color: {BLUE}; }}
QLabel#Tagline {{ color: {INK_2}; font-size: 13px; }}
QLabel#Kicker {{
    color: {INK_2}; font-size: 10px; font-weight: 700;
    background: rgba(255,255,255,210); border: 1px solid rgba(11,18,32,20);
    border-radius: 11px; padding: 3px 10px;
}}

/* ---- tabs: segmented pills --------------------------------------------- */
QTabWidget::pane {{ border: 0; background: transparent; top: -1px; }}
QTabWidget::tab-bar {{ left: 4px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {INK_2}; font-weight: 600; font-size: 13px;
    padding: 8px 20px; margin: 0 6px 10px 0; border-radius: 16px; border: 1px solid transparent;
}}
QTabBar::tab:hover {{ color: {INK}; }}
QTabBar::tab:selected {{ background: #ffffff; color: {BLUE}; border: 1px solid rgba(0,180,216,90); }}

/* ---- cards & panels -------------------------------------------------- */
QFrame#Card, QFrame#Panel {{
    background: #ffffff; border: 1px solid rgba(11,18,32,20); border-radius: 18px;
}}
QFrame#Card[state="error"] {{ border: 2px solid rgba(214,60,74,150); }}
QFrame#Card[state="running"] {{ border: 1px solid rgba(0,180,216,120); }}
QLabel#SectionTitle {{ color: {INK_3}; font-size: 10px; font-weight: 700; }}
QLabel#CardTitle {{ font-size: 15px; font-weight: 700; }}
QLabel#Meta, QLabel#Hint {{ color: {INK_3}; font-size: 12px; }}
QLabel#Body {{ color: {INK_2}; }}
QLabel#Badge {{
    color: {BLUE}; font-weight: 700; font-size: 13px; border-radius: 12px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f3fbff, stop:1 #e4f6ff);
    border: 1px solid rgba(0,180,216,70);
}}
QFrame#Readout {{ background: #f7f9fb; border: 1px solid rgba(11,18,32,20); border-radius: 14px; }}
QFrame#Readout[accent="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f2fcff, stop:1 #e6f7ff);
    border: 1px solid rgba(0,180,216,95);
}}
QLabel#ReadoutLabel {{ color: {INK_3}; font-size: 10px; font-weight: 700; }}
QLabel#ReadoutValue {{ font-size: 20px; font-weight: 600; }}
QLabel#Note {{
    color: #6f4a00; background: rgba(255,176,32,22); border: 1px solid rgba(194,124,0,55);
    border-radius: 10px; padding: 6px 10px;
}}
QLabel#Note[kind="error"] {{ color: #8f1d29; background: rgba(214,60,74,16); border: 1px solid rgba(214,60,74,60); }}

/* ---- pills ------------------------------------------------------------ */
QLabel#Pill {{ font-size: 10px; font-weight: 700; border-radius: 10px; padding: 3px 10px; }}
QLabel#Pill[kind="idle"] {{ color: #3b5a85; background: rgba(10,132,255,18); border: 1px solid rgba(10,132,255,46); }}
QLabel#Pill[kind="run"]  {{ color: #00739a; background: rgba(0,212,255,26); border: 1px solid rgba(0,180,216,80); }}
QLabel#Pill[kind="ok"]   {{ color: {OK}; background: rgba(0,200,170,26); border: 1px solid rgba(0,163,140,64); }}
QLabel#Pill[kind="warn"] {{ color: {WARN}; background: rgba(255,176,32,33); border: 1px solid rgba(194,124,0,64); }}
QLabel#Pill[kind="error"] {{ color: {ERR}; background: rgba(214,60,74,23); border: 1px solid rgba(214,60,74,64); }}

/* ---- buttons ------------------------------------------------------------ */
QPushButton, QToolButton#Ghost {{
    background: #ffffff; color: {INK}; font-weight: 600; border: 1px solid rgba(11,18,32,36);
    border-radius: 15px; padding: 6px 14px; min-height: 18px;
}}
QPushButton:hover, QToolButton#Ghost:hover {{ border-color: {CYAN}; }}
QPushButton:pressed {{ background: #eef8fc; }}
QPushButton:checked {{ background: #e3f6fd; border-color: {CYAN}; color: {BLUE}; }}
QPushButton:disabled {{ color: {INK_3}; border-color: rgba(11,18,32,20); background: #f6f7f9; }}
QPushButton#Primary {{
    color: #ffffff; border: 0; border-radius: 20px; padding: 10px 22px; font-size: 14px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00f2fe, stop:1 #0a84ff);
}}
QPushButton#Primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #22f5ff, stop:1 #2b95ff); }}
QPushButton#Primary:disabled {{ color: #ffffff; background: #c5cfdb; }}
QPushButton#Danger {{ color: {ERR}; }}
QPushButton#IconButton {{ border: 0; background: transparent; color: {INK_3}; font-size: 15px; padding: 2px 6px; }}
QPushButton#IconButton:hover {{ color: {ERR}; }}
QPushButton#MiniButton {{ border-radius: 10px; padding: 4px 4px; font-size: 11px; }}
QPushButton#HelpButton {{ border-radius: 13px; padding: 0; font-size: 14px; font-weight: 700; min-height: 0; color: {BLUE}; }}
QPushButton#HelpButton:hover {{ color: #ffffff; background: {BLUE}; border-color: {BLUE}; }}
QComboBox#ModeCombo {{ padding: 3px 8px; font-size: 12px; min-height: 0; }}
QLabel#ShortcutKey {{ font-weight: 700; color: {BLUE}; background: #eef3fb; border: 1px solid rgba(10,132,255,46); border-radius: 6px; padding: 2px 8px; }}

/* ---- header companion + language switch ------------------------------------ */
QLabel#BubbleChip {{ color: {CYAN}; font-size: 10px; font-weight: 700; }}
QLabel#BubbleText {{ color: {INK}; font-size: 12px; }}
QPushButton#BubbleButton {{
    border: 0; background: transparent; color: {INK_3}; font-size: 15px; font-weight: 700;
    padding: 0; border-radius: 11px; min-height: 0;
}}
QPushButton#BubbleButton:hover {{ color: {BLUE}; background: rgba(0,180,216,30); }}
QPushButton#BubbleReopen {{ border-radius: 15px; padding: 0; font-size: 14px; min-height: 0; }}
QComboBox#LangCombo {{ padding: 3px 8px; font-size: 12px; min-height: 0; }}
QLabel#LangIcon {{ font-size: 14px; }}
QPushButton#TransportButton {{ border-radius: 13px; padding: 0; font-size: 11px; min-height: 0; }}
QLabel#TimeLabel {{ color: {INK_2}; font-size: 12px; }}
QPushButton#LoopButton {{ border-radius: 9px; padding: 0; font-size: 11px; font-weight: 700; min-height: 0; color: {INK_2}; }}
QPushButton#LoopButton[set="true"] {{ color: {BLUE}; border-color: {CYAN}; }}
QPushButton#LoopButton:checked {{ color: #ffffff; border-color: {BLUE}; background: {BLUE}; }}
QPushButton#ToggleChip {{ border-radius: 12px; padding: 4px 10px; font-size: 12px; }}
QPushButton#VersionChip {{ border-radius: 10px; padding: 2px 9px; font-size: 11px; min-height: 0; color: {INK_2}; }}
QPushButton#VersionChip:checked {{ color: {BLUE}; border-color: {CYAN}; background: #e3f6fd; }}
QPushButton#ExportButton {{
    color: {BLUE}; background: #ffffff; border: 2px solid {BLUE}; border-radius: 20px; padding: 8px 20px; font-size: 14px;
}}
QPushButton#ExportButton:hover {{ background: #eef8ff; }}
QPushButton#ExportButton:disabled {{ color: {INK_3}; border-color: rgba(11,18,32,36); background: #f6f7f9; }}
QPushButton#CardExport {{ border-radius: 14px; padding: 5px 14px; color: {BLUE}; border: 1px solid {BLUE}; }}
QPushButton#CardExport:disabled {{ color: {OK}; border-color: rgba(0,163,140,64); background: rgba(0,200,170,14); }}
QLabel#ExportStatus {{ color: {INK_2}; font-size: 12px; }}
QLineEdit#TimeEdit {{ padding: 3px 6px; font-size: 12px; }}
QLabel#ExportStatus[kind="ok"] {{ color: {OK}; }}
QLabel#ExportStatus[kind="warn"] {{ color: {WARN}; }}
QLabel#ExportStatus[kind="error"] {{ color: {ERR}; }}
QFrame#Readout[level="caution"] {{ background: #fff8ea; border: 1px solid rgba(194,124,0,90); }}
QFrame#Readout[level="risk"] {{ background: #fff1f2; border: 1px solid rgba(214,60,74,110); }}
QPushButton#LangButton {{
    border-radius: 0; padding: 3px 10px; font-size: 11px; font-weight: 700; min-height: 0; color: {INK_2};
}}
QPushButton#LangButton[segment="left"] {{ border-top-left-radius: 11px; border-bottom-left-radius: 11px; }}
QPushButton#LangButton[segment="right"] {{ border-top-right-radius: 11px; border-bottom-right-radius: 11px; border-left: 0; }}
QPushButton#LangButton:checked {{
    color: #ffffff; border-color: {BLUE};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00c8ff, stop:1 #0a84ff);
}}

/* ---- inputs ------------------------------------------------------------- */
QComboBox, QLineEdit, QSpinBox {{
    background: #ffffff; border: 1px solid rgba(11,18,32,36); border-radius: 10px;
    padding: 6px 10px; min-height: 18px; selection-background-color: {CYAN};
}}
QComboBox:hover, QLineEdit:focus, QSpinBox:focus {{ border-color: {CYAN}; }}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled {{ color: {INK_3}; background: #f6f7f9; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: 0; }}
QLabel#CoverThumb {{
    background: #f3f5f8; border: 1px dashed rgba(11,18,32,50); border-radius: 10px; color: {INK_3};
}}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox QAbstractItemView {{
    background: #ffffff; border: 1px solid rgba(11,18,32,36); selection-background-color: #e3f6fd;
    selection-color: {INK}; outline: 0; padding: 4px;
}}
QCheckBox, QRadioButton {{ spacing: 7px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
QSlider::groove:horizontal {{ height: 4px; background: rgba(11,18,32,26); border-radius: 2px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f2fe, stop:1 #0a84ff); border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #ffffff; border: 2px solid {CYAN}; width: 14px; height: 14px; margin: -7px 0; border-radius: 9px;
}}
QProgressBar {{ border: 0; background: rgba(11,18,32,16); border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{
    border-radius: 3px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f2fe, stop:0.6 #4facfe, stop:1 #0a84ff);
}}
QProgressBar[state="error"]::chunk {{ background: #d63c4a; }}

/* ---- drop zone ---------------------------------------------------------- */
QFrame#DropZone {{
    background: rgba(255,255,255,190); border: 2px dashed rgba(0,180,216,125); border-radius: 18px;
}}
QFrame#DropZone[active="true"] {{ background: rgba(0,212,255,22); border: 2px dashed {CYAN}; }}
QLabel#DropTitle {{ font-size: 15px; font-weight: 700; }}

/* ---- scroll areas & tables --------------------------------------------- */
QScrollArea, QScrollArea > QWidget#qt_scrollarea_viewport, QWidget#ScrollBody {{ background: transparent; border: 0; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(11,18,32,45); border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QTableWidget {{
    background: #ffffff; border: 1px solid rgba(11,18,32,20); border-radius: 12px;
    gridline-color: rgba(11,18,32,18); alternate-background-color: #f7f9fb;
}}
QHeaderView::section {{
    background: #f3f5f8; color: {INK_2}; border: 0; border-bottom: 1px solid rgba(11,18,32,26);
    padding: 6px; font-weight: 700;
}}
QStatusBar {{ color: {INK_2}; }}
"""
