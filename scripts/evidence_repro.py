"""Bounded read-only diagnostics for synthetic replay reproducibility, never runtime policy."""
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import threading
import time
from typing import Any

import psutil


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def read_text(path):
    try:
        with Path(path).open() as file:
            value = file.read(8193)
        return value[:8192].strip() + (" [TRUNCATED]" if len(value) > 8192 else "")
    except OSError:
        return None


def pressure():
    return {name: read_text(f"/proc/pressure/{name}") for name in ("cpu", "io", "memory")}


class ReproTrace:
    """Fixed memory: <=1,801 lag values, 128 long calls, <=181 interval summaries."""

    def __init__(self):
        self.epoch: float | None = None
        self.long_calls: deque[dict] = deque(maxlen=128)
        self.long_count = 0
        self.loop_lag: deque[float] = deque(maxlen=1801)
        self.intervals: dict[str, dict[str, Any]] = {}
        self.cost_seconds = 0.0
        self.record_lock = threading.Lock()
        psutil.cpu_percent()
        self.environment = dict(kernel=platform.release(), python=platform.python_version(),
            sqlite=sqlite3.sqlite_version, python_hash_seed=os.getenv("PYTHONHASHSEED", "random"), logical_cpus=psutil.cpu_count(),
            affinity=psutil.Process().cpu_affinity(), memory_total=psutil.virtual_memory().total,
            cpu_max=read_text('/sys/fs/cgroup/cpu.max'), memory_max=read_text('/sys/fs/cgroup/memory.max'),
            initial_pressure=pressure(), project_device=os.stat('.').st_dev,
            project_free_bytes=psutil.disk_usage('.').free,
            mount=next((dict(device=p.device, mountpoint=p.mountpoint, fstype=p.fstype, opts=p.opts)
                for p in sorted(psutil.disk_partitions(all=True), key=lambda p: -len(p.mountpoint))
                if Path.cwd().is_relative_to(p.mountpoint)), None))

    def start(self, epoch):
        self.epoch = epoch

    def sample_lag(self, due):
        # Observe the harness's EXISTING one-second sleep. Do not introduce timers
        # which could accidentally mask the restricted-runtime selector wakeup issue.
        self.loop_lag.append(max(0, time.perf_counter() - due))

    def record(self, stage, start, duration, role=None):
        # Retention/evaluation run on existing workers: keep diagnostic counters
        # coherent without ever holding this lock across application work or I/O.
        with self.record_lock:
            self._record(stage, start, duration, role)

    def _record(self, stage, start, duration, role):
        if self.epoch is None:
            return
        at = start - self.epoch
        interval = int(max(0, at) // 10)
        if interval >= 181:
            return
        row = self.intervals.setdefault(str(interval), {})
        if stage not in row and len(row) >= 20:
            return
        values = row.setdefault(stage, dict(count=0, seconds=0., maximum=0.))
        values['count'] += 1
        values['seconds'] += duration
        values['maximum'] = max(values['maximum'], duration)
        if role is not None:
            allowed = {"event_identity", "raw_event", "other_record", "restore_checkpoint",
                       "outcome_batch", "pending_state", "retention", "evaluation", "unattributed"}
            role = role if role in allowed else "unattributed"
            item = values.setdefault("roles", {}).setdefault(role,
                dict(count=0, seconds=0., maximum=0., over_10ms=0, over_20ms=0, over_50ms=0))
            item["count"] += 1
            item["seconds"] += duration
            item["maximum"] = max(item["maximum"], duration)
            for name, limit in [("over_10ms", .01), ("over_20ms", .02), ("over_50ms", .05)]:
                item[name] += duration > limit
        if duration >= .05:
            self.long_count += 1
            self.long_calls.append(dict(stage=stage, at=at, seconds=duration, **({"role": role} if role else {})))

    def sample(self):
        start = time.perf_counter()
        memory = psutil.virtual_memory()
        row = dict(host_cpu_percent=psutil.cpu_percent(), available_memory=memory.available,
            swap=psutil.swap_memory().used, pressure=pressure(),
            cgroup_cpu_stat=read_text('/sys/fs/cgroup/cpu.stat'),
            cgroup_io_stat=read_text('/sys/fs/cgroup/io.stat'))
        # Some restricted runtimes omit /proc/self/io; absence is explicit.
        try:
            row['process_io'] = psutil.Process().io_counters()._asdict()
        except (OSError, psutil.Error, AttributeError):
            row['process_io'] = None
        self.cost_seconds += time.perf_counter() - start
        return row

    def result(self):
        values = sorted(self.loop_lag)
        def p(f):
            return values[min(len(values)-1, int((len(values)-1)*f))] if values else None
        return dict(environment=self.environment, final_pressure=pressure(),
            sample_cost_seconds=self.cost_seconds, long_call_count=self.long_count,
            long_call_limit=128, long_calls=list(self.long_calls), intervals=self.intervals,
            loop_lag=dict(count=len(values), p50=p(.5), p95=p(.95), p99=p(.99), maximum=p(1)),
            limitations='Lag timer samples cooperative-loop lateness, not exclusive CPU; timers overlap. No checkpoint or fsync is forced.')
