from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import httpx
import pika

from app.config import Settings
from app.metadata import MetadataValidationError, TransportMetadata, metadata_from_amqp
from app.sap_xml import sap_xml_to_json


LOGGER = logging.getLogger(__name__)


class ConsumerState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._connected = False
        self._last_error: str | None = None

    def update(
        self,
        *,
        running: bool | None = None,
        connected: bool | None = None,
        last_error: str | None = None,
        clear_error: bool = False,
    ) -> None:
        with self._lock:
            if running is not None:
                self._running = running
            if connected is not None:
                self._connected = connected
            if clear_error:
                self._last_error = None
            elif last_error is not None:
                self._last_error = last_error

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "connected": self._connected,
                "last_error": self._last_error,
            }


class OrbitalForwarder:
    def __init__(
        self,
        target_url: str,
        timeout: float,
        client: httpx.Client | None = None,
        *,
        payload_format: str = "xml",
    ) -> None:
        if payload_format not in {"json", "xml"}:
            raise ValueError("payload_format must be 'xml' or 'json'")
        self._target_url = target_url
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        self._payload_format = payload_format

    def forward(self, body: bytes, metadata: TransportMetadata) -> bool:
        headers = metadata.orbital_headers()
        if self._payload_format == "json":
            body = sap_xml_to_json(body)
            headers["Content-Type"] = "application/json"
        response = self._client.post(
            self._target_url,
            content=body,
            headers=headers,
        )
        return 200 <= response.status_code < 300

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class RabbitConsumer:
    """Consumes routed XML and forwards it to Orbital with manual acknowledgements."""

    def __init__(
        self,
        settings: Settings,
        forwarder: OrbitalForwarder,
        connection_factory: Callable[[pika.ConnectionParameters], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._forwarder = forwarder
        self._connection_factory = connection_factory or pika.BlockingConnection
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._connection: Any = None
        self._channel: Any = None
        self.state = ConsumerState()

    def _parameters(self) -> pika.ConnectionParameters:
        credentials = pika.PlainCredentials(
            self._settings.rabbitmq_user,
            self._settings.rabbitmq_password,
        )
        return pika.ConnectionParameters(
            host=self._settings.rabbitmq_host,
            port=self._settings.rabbitmq_port,
            virtual_host=self._settings.rabbitmq_vhost,
            credentials=credentials,
            heartbeat=self._settings.rabbitmq_heartbeat,
            blocked_connection_timeout=self._settings.rabbitmq_blocked_connection_timeout,
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"rabbit-{self._settings.consumer_expected_origin}-consumer",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        connection = self._connection
        channel = self._channel
        if connection and getattr(connection, "is_open", False) and channel:
            try:
                connection.add_callback_threadsafe(channel.stop_consuming)
            except Exception:
                LOGGER.debug("Unable to request consumer stop", exc_info=True)
        if self._thread:
            self._thread.join(timeout=timeout)
        self._forwarder.close()

    def health_snapshot(self) -> dict[str, Any]:
        return self.state.snapshot()

    def _run(self) -> None:
        self.state.update(running=True, connected=False, clear_error=True)
        while not self._stop_event.is_set():
            try:
                self._connection = self._connection_factory(self._parameters())
                self._channel = self._connection.channel()
                self._channel.queue_declare(
                    queue=self._settings.consumer_queue,
                    passive=True,
                )
                self._channel.basic_qos(
                    prefetch_count=self._settings.consumer_prefetch
                )
                self._channel.basic_consume(
                    queue=self._settings.consumer_queue,
                    on_message_callback=self.handle_delivery,
                    auto_ack=False,
                )
                self.state.update(connected=True, clear_error=True)
                LOGGER.info(
                    "Consuming queue %s with prefetch=%s",
                    self._settings.consumer_queue,
                    self._settings.consumer_prefetch,
                )
                self._channel.start_consuming()
            except pika.exceptions.AMQPError as exc:
                if not self._stop_event.is_set():
                    LOGGER.warning("RabbitMQ consumer disconnected: %s", exc)
                    self.state.update(connected=False, last_error=str(exc))
            except Exception as exc:
                if not self._stop_event.is_set():
                    LOGGER.exception("Unexpected consumer failure")
                    self.state.update(connected=False, last_error=str(exc))
            finally:
                self.state.update(connected=False)
                self._close_connection()

            if not self._stop_event.is_set():
                self._stop_event.wait(self._settings.consumer_reconnect_delay)

        self.state.update(running=False, connected=False)

    def _close_connection(self) -> None:
        channel = self._channel
        connection = self._connection
        self._channel = None
        self._connection = None
        try:
            if channel and getattr(channel, "is_open", False):
                channel.close()
        except Exception:
            LOGGER.debug("Failed to close consumer channel", exc_info=True)
        try:
            if connection and getattr(connection, "is_open", False):
                connection.close()
        except Exception:
            LOGGER.debug("Failed to close consumer connection", exc_info=True)

    def handle_delivery(
        self,
        channel: Any,
        method: Any,
        properties: Any,
        body: bytes,
    ) -> None:
        delivery_tag = method.delivery_tag
        try:
            metadata = metadata_from_amqp(
                method.routing_key,
                properties,
                expected_schema=self._settings.expected_schema,
                expected_routing_pattern=self._settings.consumer_routing_pattern,
                expected_event_type=self._settings.event_type,
                expected_origin=self._settings.consumer_expected_origin,
                require_adobe_customer_id=(
                    self._settings.consumer_require_adobe_customer_id
                ),
            )
        except MetadataValidationError as exc:
            LOGGER.warning(
                "Rejecting message with invalid route metadata: %s",
                exc,
            )
            channel.basic_reject(delivery_tag=delivery_tag, requeue=False)
            return

        try:
            succeeded = self._forwarder.forward(body, metadata)
        except httpx.HTTPError as exc:
            LOGGER.warning(
                "Orbital request failed for message %s: %s",
                metadata.message_id,
                exc,
            )
            succeeded = False
        except Exception:
            LOGGER.exception(
                "Unexpected Orbital forwarding failure for message %s",
                metadata.message_id,
            )
            succeeded = False

        if succeeded:
            channel.basic_ack(delivery_tag=delivery_tag)
            return

        LOGGER.warning(
            "Rejecting message %s after non-2xx Orbital response",
            metadata.message_id,
        )
        channel.basic_reject(delivery_tag=delivery_tag, requeue=False)
