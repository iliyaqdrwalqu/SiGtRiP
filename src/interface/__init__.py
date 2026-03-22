\
# ARGOS Interface modules
try:
    from src.interface.web_engine import WebDashboard, run_web_sync
except Exception:
    pass
try:
    from src.interface.kivy_gui import ArgosGUI
except ImportError:
    pass
