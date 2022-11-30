import os
from typing import List

import prometheus_client
from loguru import logger

INF = float("inf")
DEFAULT_BUCKETS = {
    "runtime": [0.25, 1, 3, 10, 30, 60, 120, 600, 1800, INF],
    "latency": [0.001, 0.01, 0.1, 0.5, 1, 5, 10, 30, 60, INF],
}


def get_buckets(key: str) -> List[float]:
    env_var = f"CELERY_EXPORTER_{key.upper()}_BUCKETS"
    val = os.environ.get(env_var)
    if val is not None:
        try:
            buckets = [float(x.strip().lower()) for x in val.split(",")]
        except Exception as e:
            logger.error("Error parsing custom buckets; falling back to defaults")
            logger.exception(e)
            buckets = DEFAULT_BUCKETS[key]
        return buckets
    else:
        return DEFAULT_BUCKETS[key]


TASKS_RUNTIME = prometheus_client.Histogram(
    "celery_tasks_runtime_seconds",
    "Task runtime.",
    ["namespace", "name", "queue"],
    buckets=get_buckets("runtime"),
)


LATENCY = prometheus_client.Histogram(
    "celery_tasks_latency_seconds",
    "Time between a task is received and started.",
    ["namespace", "name", "queue"],
    buckets=get_buckets("latency"),
)


TASKS = prometheus_client.Counter(
    "celery_tasks_total",
    "Number of task events.",
    ["namespace", "name", "state", "queue"],
)

WORKERS = prometheus_client.Gauge(
    "celery_workers",
    "Number of alive workers.",
    ["namespace"],
)
