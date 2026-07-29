from __future__ import annotations

import os
from dataclasses import dataclass


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    value = float(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "orbital"
    rabbitmq_password: str = "orbital-poc"
    rabbitmq_vhost: str = "poc"
    rabbitmq_heartbeat: int = 30
    rabbitmq_blocked_connection_timeout: float = 30.0

    exchange: str = "poc.customer-account.events"
    adobe_to_sap_routing_key: str = "customer-account.adobe.updated"
    sap_to_adobe_queue: str = "poc.customer-account.sap-to-adobe"
    sap_to_adobe_routing_pattern: str = "customer-account.sap.*"
    consumer_prefetch: int = 1
    consumer_enabled: bool = True
    consumer_reconnect_delay: float = 5.0

    expected_schema: str = "sap.zbupa-cbo.v1"
    event_type: str = "customer-account.updated.v1"

    orbital_base_url: str = "http://orbital:9022"
    orbital_sap_to_adobe_path: str = "/api/q/customer-account/from-sap"
    orbital_timeout: float = 30.0

    http_host: str = "0.0.0.0"
    bridge_port: int = 8080

    @property
    def orbital_sap_url(self) -> str:
        return (
            f"{self.orbital_base_url.rstrip('/')}"
            f"/{self.orbital_sap_to_adobe_path.lstrip('/')}"
        )

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            rabbitmq_host=os.getenv("RABBITMQ_HOST", cls.rabbitmq_host),
            rabbitmq_port=_int_env("RABBITMQ_PORT", cls.rabbitmq_port),
            rabbitmq_user=os.getenv("RABBITMQ_USER", cls.rabbitmq_user),
            rabbitmq_password=os.getenv("RABBITMQ_PASSWORD", cls.rabbitmq_password),
            rabbitmq_vhost=os.getenv("RABBITMQ_VHOST", cls.rabbitmq_vhost),
            rabbitmq_heartbeat=_int_env("RABBITMQ_HEARTBEAT", cls.rabbitmq_heartbeat),
            rabbitmq_blocked_connection_timeout=_float_env(
                "RABBITMQ_BLOCKED_CONNECTION_TIMEOUT",
                cls.rabbitmq_blocked_connection_timeout,
            ),
            exchange=os.getenv("RABBITMQ_EXCHANGE", cls.exchange),
            adobe_to_sap_routing_key=os.getenv(
                "RABBITMQ_ADOBE_TO_SAP_ROUTING_KEY",
                cls.adobe_to_sap_routing_key,
            ),
            sap_to_adobe_queue=os.getenv(
                "RABBITMQ_SAP_TO_ADOBE_QUEUE", cls.sap_to_adobe_queue
            ),
            sap_to_adobe_routing_pattern=os.getenv(
                "RABBITMQ_SAP_TO_ADOBE_ROUTING_PATTERN",
                cls.sap_to_adobe_routing_pattern,
            ),
            consumer_prefetch=_int_env(
                "RABBITMQ_CONSUMER_PREFETCH", cls.consumer_prefetch
            ),
            consumer_enabled=_bool_env("RABBITMQ_CONSUMER_ENABLED", cls.consumer_enabled),
            consumer_reconnect_delay=_float_env(
                "RABBITMQ_CONSUMER_RECONNECT_DELAY",
                cls.consumer_reconnect_delay,
            ),
            expected_schema=os.getenv("CUSTOMER_ACCOUNT_SCHEMA", cls.expected_schema),
            event_type=os.getenv("CUSTOMER_ACCOUNT_EVENT_TYPE", cls.event_type),
            orbital_base_url=os.getenv("ORBITAL_BASE_URL", cls.orbital_base_url),
            orbital_sap_to_adobe_path=os.getenv(
                "ORBITAL_SAP_TO_ADOBE_PATH", cls.orbital_sap_to_adobe_path
            ),
            orbital_timeout=_float_env("ORBITAL_TIMEOUT", cls.orbital_timeout),
            http_host=os.getenv("HTTP_HOST", cls.http_host),
            bridge_port=_int_env("BRIDGE_PORT", cls.bridge_port),
        )
