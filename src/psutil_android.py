"""Заглушка psutil для Android/Termux."""
import os

def cpu_percent(interval=None):
    try:
        try:
    import psutil
except Exception:
    from src import psutil_android as psutil
        return psutil.cpu_percent(interval=interval)
    except Exception:
        return 0.0

def virtual_memory():
    try:
        try:
    import psutil
except Exception:
    from src import psutil_android as psutil
        return psutil.virtual_memory()
    except Exception:
        class _Mem:
            percent = 0.0
            total = 2 * 1024**3
            available = 1 * 1024**3
            used = 1 * 1024**3
        return _Mem()

def disk_usage(path="/"):
    try:
        try:
    import psutil
except Exception:
    from src import psutil_android as psutil
        return psutil.disk_usage(path)
    except Exception:
        class _Disk:
            percent = 0.0
            free = 1 * 1024**3
            total = 2 * 1024**3
            used = 1 * 1024**3
        return _Disk()

def cpu_count(logical=True):
    try:
        try:
    import psutil
except Exception:
    from src import psutil_android as psutil
        return psutil.cpu_count(logical=logical)
    except Exception:
        return os.cpu_count() or 4

def boot_time():
    return 0.0
