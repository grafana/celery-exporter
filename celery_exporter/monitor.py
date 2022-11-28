import logging
import threading
import time
from typing import Dict, List, Set

import amqp
import celery
import celery.states
from celery.utils.objects import FallbackContext
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

from .celery_state import CeleryState
from .metrics import LATENCY, TASKS, TASKS_RUNTIME
from .utils import get_config


class TaskThread(threading.Thread):
    """
    MonitorThread is the thread that will collect the data that is later
    exposed from Celery using its eventing system.
    """

    def __init__(
        self, app: celery.Celery, namespace: str, max_tasks_in_memory: int, *args, **kwargs
    ):
        self._app = app
        self._namespace = namespace
        self.log = logging.getLogger("task-thread")
        self._state = CeleryState.new(max_tasks_in_memory=max_tasks_in_memory)
        self._known_states: Set = set()
        self._known_states_names: Set = set()
        self._tasks_started: Dict = dict()
        super(TaskThread, self).__init__(*args, **kwargs)

    def run(self):  # pragma: no cover
        self._monitor()

    def _process_event(self, event: Dict):
        (name, queue, latency) = self._state.latency(event)
        if latency is not None:
            LATENCY.labels(namespace=self._namespace, name=name, queue=queue).observe(latency)
        (name, state, runtime, queue) = self._state.collect(event)

        if name is not None:
            if runtime is not None:
                TASKS_RUNTIME.labels(namespace=self._namespace, name=name, queue=queue).observe(
                    runtime
                )

            TASKS.labels(namespace=self._namespace, name=name, state=state, queue=queue).inc()

    def _monitor(self):  # pragma: no cover
        while True:
            try:
                with self._app.connection() as conn:
                    recv = self._app.events.Receiver(conn, handlers={"*": self._process_event})
                    setup_metrics(self._app, self._namespace)
                    self.log.info("Start capturing events...")
                    recv.capture(limit=None, timeout=None, wakeup=True)
            except Exception:
                self.log.exception("Connection failed")
                setup_metrics(self._app, self._namespace)
                time.sleep(5)


class WorkerCollector(Collector):
    celery_ping_timeout_seconds = 5

    def __init__(self, app: celery.Celery, namespace: str):
        self._app = app
        self._namespace = namespace

    def collect(self):
        try:
            workers = GaugeMetricFamily(
                "celery_workers", "Number of alive workers", labels=["namespace"]
            )
            workers.add_metric(
                [self._namespace],
                len(self._app.control.ping(timeout=self.celery_ping_timeout_seconds)),
            )
            yield workers
        except Exception:  # pragma: no cover
            logging.exception("Error while pinging workers")


class EnableEventsThread(threading.Thread):
    periodicity_seconds = 5

    def __init__(self, app: celery.Celery, *args, **kwargs):  # pragma: no cover
        self._app = app
        self.log = logging.getLogger("enable-events-thread")
        super(EnableEventsThread, self).__init__(*args, **kwargs)

    def run(self):  # pragma: no cover
        while True:
            try:
                self.enable_events()
            except Exception:
                self.log.exception("Error while trying to enable events")
            time.sleep(self.periodicity_seconds)

    def enable_events(self):
        self._app.control.enable_events()


class QueueLengthCollector(Collector):
    def __init__(self, app: celery.Celery, queue_list: List):
        self.celery_app = app
        self.queue_list = queue_list
        self.connection = self.celery_app.connection_or_acquire()

        if isinstance(self.connection, FallbackContext):
            self.connection = self.connection.fallback()

    def collect(self):
        gauge = GaugeMetricFamily(
            "celery_queue_length",
            "Number of tasks in pending the queue (excludes those prefetched by workers).",
            labels=["queue_name"],
        )
        for queue in self.queue_list:
            try:
                length = self.connection.default_channel.queue_declare(
                    queue=queue,
                    passive=True,
                    timeout=5,
                ).message_count

            except (amqp.exceptions.ChannelError,) as e:
                # With a Redis broker, an empty queue "(404) NOT_FOUND" is the same as
                # a missing queue.
                if "NOT_FOUND" not in str(e):
                    logging.warning(f"Unexpected error fetching queue: '{queue}': {e}")
                length = 0

            gauge.add_metric([queue], length)
        yield gauge


def setup_metrics(app: celery.Celery, namespace: str):
    """
    This initializes the available metrics with default values so that
    even before the first event is received, data can be exposed.
    """
    config = get_config(app)

    if not config:  # pragma: no cover
        for metric in TASKS.collect():
            for name, labels, cnt, timestamp, exemplar in metric.samples:
                TASKS.labels(**labels)
    else:
        for task, queue in config.items():
            LATENCY.labels(namespace=namespace, name=task, queue=queue)
            for state in celery.states.ALL_STATES:
                TASKS.labels(namespace=namespace, name=task, state=state, queue=queue)
