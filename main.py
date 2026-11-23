"""
Heins True Diyae Pro - desktop entry point (Windows / macOS).

    python main.py                      (or: python main.py MyProject.htd)

The heavy audio libraries (scipy, librosa, pedalboard, matplotlib) are imported
after the splash screen is shown, so the window appears immediately.
"""

from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    multiprocessing.freeze_support()           # needed by PyInstaller builds on Windows

    if sys.platform == "win32":
        try:                                    # own taskbar icon instead of python.exe's
            import ctypes

            from htd import config as _config

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_config.APP_ID)
        except Exception:  # noqa: BLE001
            pass

    from PySide6.QtCore import QEvent, QLocale, QObject, QSettings, Qt, QTimer
    from PySide6.QtWidgets import QApplication, QSplashScreen

    from htd import config
    from htd import logging_setup
    from htd.ui import theme
    from htd.ui.translate import init_language, tr
    from htd.ui.widgets import logo_pixmap

    logging_setup.install()                     # rotating log + unhandled-exception capture (no console)

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.ORG_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setStyle("Fusion")                      # same look on Windows and macOS
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):        # Qt >= 6.8: stay light in OS dark mode
        hints.setColorScheme(Qt.ColorScheme.Light)
    app.setPalette(theme.light_palette())
    app.setStyleSheet(theme.STYLESHEET)
    settings = QSettings(config.ORG_NAME, config.APP_NAME)
    from htd.ui import fonts

    fonts.apply_language(init_language(settings, QLocale.system().name()))   # saved choice, else the system's

    splash = QSplashScreen(logo_pixmap(220))
    splash.show()
    splash.showMessage(tr("Loading the audio engine…"),
                       Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
    app.processEvents()

    from htd.engine import ffmpeg_tools
    from htd.ui.main_window import AppContext, MainWindow

    ffmpeg = ffmpeg_tools.install_resolver()
    window = MainWindow(AppContext(ffmpeg, settings))
    window.show()
    splash.finish(window)

    class _ProjectOpener(QObject):
        """macOS: a .htd double-clicked in the Finder arrives as a FileOpen event."""

        def eventFilter(self, _obj, event) -> bool:  # noqa: N802
            if event.type() == QEvent.Type.FileOpen and str(event.file()).lower().endswith(".htd"):
                window.open_project(str(event.file()))
                return True
            return False

    opener = _ProjectOpener(app)
    app.installEventFilter(opener)
    projects = [arg for arg in sys.argv[1:] if arg.lower().endswith(".htd")]     # "Open with" / command line
    if projects:
        QTimer.singleShot(0, lambda: window.open_project(projects[0]))
    try:
        return app.exec()
    finally:
        config.cleanup_session()


if __name__ == "__main__":
    sys.exit(main())
