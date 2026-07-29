from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import pika

from app.config import Settings
from app.metadata import TransportMetadata


LOGGER = logging.getLogger(__name__)


class PublishError(RuntimeError):
    pass


class UnroutablePublishError(PublishError):
    pass


class RabbitPublisher:
    """Thread-safe publisher using confirms and mandatory routing."""

    def __init__(
        self,
        settings: Settings,
        connection_factory: Callable[[pika.ConnectionParameters], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._connection_factory = connection_factory or pika.BlockingConnection
        self._connection: Any = None
        self._channel: Any = None
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return bool(
            self._connection
            and getattr(self._connection, "is_open", False)
            and self._channel
            and getattr(self._channel, "is_open", False)
        )

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

    def _connect(self) -> None:
        if self.connected:
            return
        self._close_unlocked()
        self._connection = self._connection_factory(self._parameters())
        self._channel = self._connection.channel()
        self._channel.confirm_delivery()

    def publish(
        self,
        body: bytes,
        metadata: TransportMetadata,
        routing_key: str,
    ) -> None:
        properties = pika.BasicProperties(
            content_type="application/xml",
            delivery_mode=2,
            message_id=metadata.message_id,
            correlation_id=metadata.correlation_id,
            type=metadata.event_type,
            headers=metadata.amqp_headers(),
        )
        with self._lock:
            try:
                self._connect()
                confirmed = self._channel.basic_publish(
                    exchange=self._settings.exchange,
                    routing_key=routing_key,
                    body=body,
                    properties=properties,
                    mandatory=True,
                )
                if confirmed is False:
                    raise PublishError("RabbitMQ negatively acknowledged the message")
            except pika.exceptions.UnroutableError as exc:
                raise UnroutablePublishError(
                    f"No queue is bound for routing key {routing_key!r}"
                ) from exc
            except pika.exceptions.NackError as exc:
                raise PublishError("RabbitMQ negatively acknowledged the message") from exc
            except pika.exceptions.AMQPError as exc:
                self._close_unlocked()
                raise PublishError(f"RabbitMQ publish failed: {exc}") from exc

    def close(self) -> None:
        with self._lock:
            self._close_unlocked()

    def _close_unlocked(self) -> None:
        channel = self._channel
        connection = self._connection
        self._channel = None
        self._connection = None
        try:
            if channel and getattr(channel, "is_open", False):
                channel.close()
        except Exception:
            LOGGER.debug("Failed to close publisher channel", exc_info=True)
        try:
            if connection and getattr(connection, "is_open", False):
                connection.close()
        except Exception:
            LOGGER.debug("Failed to close publisher connection", exc_info=True)

