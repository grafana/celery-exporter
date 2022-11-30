import json
import os
import signal
import sys
import time
from types import FrameType
from typing import Optional, Union

import click
from loguru import logger

from .core import CeleryExporter
from .utils import generate_broker_use_ssl, get_transport_scheme

LOG_FORMAT = "[%(asctime)s] %(name)s:%(levelname)s: %(message)s"


def shutdown(signum: Union[int, signal.Signals], frame: Optional[FrameType]):
    """
    Shutdown is called if the process receives a TERM/INT signal.
    """
    logger.info("Shutting down")
    sys.exit(0)


@click.command(context_settings={"auto_envvar_prefix": "CELERY_EXPORTER"})
@click.option(
    "--broker-url",
    "-b",
    type=str,
    show_default=True,
    show_envvar=True,
    default="redis://redis:6379/0",
    help="URL to the Celery broker.",
)
@click.option(
    "--listen-address",
    "-l",
    type=str,
    show_default=True,
    show_envvar=True,
    default="0.0.0.0:9540",
    help="Address the HTTPD should listen on.",
)
@click.option(
    "--max-tasks",
    "-m",
    type=int,
    show_default=True,
    show_envvar=True,
    default="10000",
    help="Tasks cache size.",
)
@click.option(
    "--namespace",
    "-n",
    type=str,
    show_default=True,
    show_envvar=True,
    default="celery",
    help="Namespace for metrics.",
)
@click.option(
    "--transport-options",
    type=str,
    allow_from_autoenv=False,
    help="JSON object with additional options passed to the underlying transport.",
)
@click.option(
    "--enable-events",
    is_flag=True,
    allow_from_autoenv=False,
    help="Periodically enable Celery events.",
)
@click.option(
    "--queues",
    "-q",
    multiple=True,
    allow_from_autoenv=False,
    help="Celery queues to monitor for length",
)
@click.option(
    "--use-ssl",
    is_flag=True,
    help="Enable SSL usage on broker connection if redis or amqp.",
)
@click.option(
    "--ssl-verify",
    type=click.Choice(["CERT_NONE", "CERT_OPTIONAL", "CERT_REQUIRED"], case_sensitive=True),
    default="CERT_REQUIRED",
    help="SSL verify mode.",
)
@click.option(
    "--ssl-ca-certs",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True),
    help="SSL path to the CA certificate.",
)
@click.option(
    "--ssl-certfile",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True),
    help="SSL path to the Client Certificate.",
)
@click.option(
    "--ssl-keyfile",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True),
    help="SSL path to the Client Key.",
)
@click.option("--tz", type=str, allow_from_autoenv=False, help="Timezone used by the celery app.")
@click.option("--verbose", is_flag=True, allow_from_autoenv=False, help="Enable verbose logging.")
def main(
    broker_url,
    listen_address,
    max_tasks,
    namespace,
    transport_options,
    enable_events,
    queues,
    use_ssl,
    ssl_verify,
    ssl_ca_certs,
    ssl_certfile,
    ssl_keyfile,
    tz,
    verbose,
):  # pragma: no cover

    if not verbose:
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    if tz:
        os.environ["TZ"] = tz
        time.tzset()

    if transport_options:
        try:
            transport_options = json.loads(transport_options)
        except ValueError:
            logger.error(f"Error parsing broker transport options from JSON '{transport_options}'")
            sys.exit(1)

    broker_use_ssl = generate_broker_use_ssl(
        use_ssl,
        get_transport_scheme(broker_url),
        ssl_verify,
        ssl_ca_certs,
        ssl_certfile,
        ssl_keyfile,
    )

    celery_exporter = CeleryExporter(
        broker_url,
        listen_address,
        max_tasks,
        namespace,
        transport_options,
        enable_events,
        queues,
        broker_use_ssl,
    )

    celery_exporter.start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        signal.pause()


if __name__ == "__main__":  # pragma: no cover
    main()  # pylint: disable=E1120
