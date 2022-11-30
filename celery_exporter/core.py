from typing import Any, Dict, Optional, Union

import celery
import prometheus_client
from loguru import logger
from prometheus_client import REGISTRY

from .monitor import (
    EnableEventsThread,
    QueueLengthCollector,
    TaskThread,
    WorkerCollectorThread,
    setup_metrics,
)

__all__ = ("CeleryExporter",)


class CeleryExporter:
    def __init__(
        self,
        broker_url: str,
        listen_address: str,
        max_tasks: int = 10000,
        namespace: str = "celery",
        transport_options: Optional[Dict] = None,
        enable_events: bool = False,
        queues: Optional[Any] = None,
        broker_use_ssl: Optional[Union[bool, Dict]] = None,
    ):
        self._listen_address = listen_address
        self._max_tasks = max_tasks
        self._namespace = namespace
        self._enable_events = enable_events
        self._queues = queues

        self._app = celery.Celery(broker=broker_url, broker_use_ssl=broker_use_ssl)
        # need to set accept_content since 5.1.0: https://github.com/celery/celery/pull/6757
        # celery <5.1.0: self._app.control.ping returns json content
        # celery 5.1.0+: self._app.control.ping returns pickle content
        self._app.conf.update(accept_content=["pickle", "json"])
        self._app.conf.broker_transport_options = transport_options or {}

    def start(self):

        setup_metrics(self._app, self._namespace)

        self._start_httpd()

        t = TaskThread(
            app=self._app,
            namespace=self._namespace,
            max_tasks_in_memory=self._max_tasks,
        )
        t.daemon = True
        logger.debug("Starting TaskThread")
        t.start()

        if self._queues:
            logger.debug("Registering QueueLengthCollector")
            REGISTRY.register(QueueLengthCollector(app=self._app, queue_list=self._queues))

        w = WorkerCollectorThread(
            app=self._app,
            namespace=self._namespace,
        )
        w.daemon = True
        logger.debug("Starting WorkerCollectorThread")
        w.start()

        if self._enable_events:
            e = EnableEventsThread(app=self._app)
            e.daemon = True
            logger.debug("Starting EventsThread")
            e.start()

    def _start_httpd(self):  # pragma: no cover
        """
        Starts the exposing HTTPD using the addr provided in a separate
        thread.
        """
        host, port = self._listen_address.split(":")
        logger.info(f"Starting HTTPD on {host}:{port}")
        prometheus_client.start_http_server(int(port), host)
