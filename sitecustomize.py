import sys, os
_real_psutil = None

class _PsutilShim:
    def cpu_percent(self, interval=None):
        try:
            global _real_psutil
            if _real_psutil is None:
                import importlib
                _real_psutil = importlib.import_module("psutil")
            return _real_psutil.cpu_percent(interval=interval)
        except:
            return 0.0

    def virtual_memory(self):
        try:
            global _real_psutil
            if _real_psutil is None:
                import importlib
                _real_psutil = importlib.import_module("psutil")
            return _real_psutil.virtual_memory()
        except:
            class M:
                percent=0.0; total=2*1024**3; available=1*1024**3; used=1*1024**3
            return M()

    def disk_usage(self, path="/"):
        try:
            import shutil
            t,u,f = shutil.disk_usage(path)
            class D:
                total=t; used=u; free=f; percent=round(u/t*100,1) if t else 0.0
            return D()
        except:
            class D:
                percent=0.0; free=1*1024**3; total=2*1024**3; used=1*1024**3
            return D()

    def cpu_count(self, logical=True):
        return os.cpu_count() or 4

    def boot_time(self):
        return 0.0

sys.modules["psutil"] = _PsutilShim()
