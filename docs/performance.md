# Measured performance — 2026-10-08

Environment: Linux-6.18.40.1-microsoft-standard-WSL2-x86_64-with-glibc2.43; Python 3.13.16; 8 logical CPUs. Host laptop model/total RAM were not queried. No GPU or remote provider calls. Reproduce with `python scripts/profile.py --events 5000`.

| Measurement | Result |
|---|---:|
| Initialized idle backend RSS | 88.6 MB |
| Monitoring plus bounded overload RSS | 108.1 MB |
| Active candidates / deep limit | 250 / 25 |
| Trade observations plus discovery | 5000 + 250 |
| Wall time | 38.8 seconds |
| Process CPU time | 38.81 seconds |
| Ingestion throughput | 128.9 events/s |
| Median processing latency | 6.701 ms |
| p95 processing latency | 13.759 ms |
| SQLite + WAL | 16.22 MB |
| Overload submitted / queue retained / dropped | 2500 / 1000 / 1500 |

Includes scoring, economics, indexed SQLite event journal and restart-safe dedup writes for 25 deep-market tokens and 250 active candidates. The main test feeds observations synchronously and normally has queue depth 1; a separate producer burst demonstrates strict queue bounds and dropping. CPU time represents a saturated ingestion benchmark, not ordinary monitoring CPU percentage. Long-running retained databases, browser RSS, paid stream latency and network performance were not measured here. No numbers are extrapolated to promise profitability or hardware-independent performance.

Default RSS guard 700 MB, warning/action at 85%; stops expansion, trims windows, reduces subscriptions and degrades affected signals. The test remains far below the 500 MB target. A soft guard is not an operating-system memory limit. History and evaluation iterate in 500-record batches; no full database load.

Repeated idle risk recomputation is limited to once per second; incoming events still trigger immediate analysis. Economic estimates are cached by cash, liquidity, observed edge and sizing-relevant volatility. These are bounded per-token caches.
