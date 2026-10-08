import os
import psutil


class ResourceMonitor:
    def __init__(self, settings, db):
        self.settings, self.db = settings, db
        self.process = psutil.Process(os.getpid())
        self.process.cpu_percent()

    def sample(self):
        rss = self.process.memory_info().rss / 1048576
        size = self.db.size() / 1048576
        ratio = size / self.settings.db_limit_mb
        return {
            "rss_mb": round(rss, 1),
            "cpu_pct": self.process.cpu_percent(),
            "db_mb": round(size, 2),
            "resource_pressure": rss >= self.settings.rss_limit_mb * 0.85,
            "storage_pressure": ratio >= 0.7,
            "storage_level": next((p for p in [100, 95, 85, 70] if ratio * 100 >= p), 0),
            "storage_full": ratio >= 1,
        }
