from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID


ROUTING_KEY_PATTERN = re.compile(
    r"^customer-account\.(?P<origin>adobe|sap|fwt)\.(?P<action>updated|created)$"
)
ROUTING_ACTIONS = {"updated": "UPDATE", "created": "CREATE"}


class MetadataValidationError(ValueError):
    code = "INVALID_ROUTE_METADATA"


def _string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    text = str(value).strip()
    return text or None


def _normalized(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).strip().lower(): value for key, value in mapping.items()}


def _required(mapping: Mapping[str, Any], key: str) -> str:
    value = _string(mapping.get(key))
    if value is None:
        raise MetadataValidationError(f"Missing required metadata: {key}")
    return value


def _uuid(value: str, field: str) -> str:
    try:
        UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise MetadataValidationError(f"{field} must be a UUID") from exc
    return value


def _optional_bool(value: Any, field: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = _string(value)
    if normalized is None:
        return None
    normalized = normalized.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise MetadataValidationError(f"{field} must be a boolean value")


def parse_routing_key(routing_key: str) -> tuple[str, str]:
    match = ROUTING_KEY_PATTERN.fullmatch(routing_key)
    if match is None:
        raise MetadataValidationError(f"Unsupported routing key: {routing_key}")
    return match.group("origin"), ROUTING_ACTIONS[match.group("action")]


def routing_key_matches(pattern: str, routing_key: str) -> bool:
    """Match a RabbitMQ topic binding pattern against a routing key."""
    pattern_parts = pattern.split(".")
    key_parts = routing_key.split(".")

    def match(pattern_index: int, key_index: int) -> bool:
        while pattern_index < len(pattern_parts):
            token = pattern_parts[pattern_index]
            if token == "#":
                if pattern_index == len(pattern_parts) - 1:
                    return True
                return any(
                    match(pattern_index + 1, candidate)
                    for candidate in range(key_index, len(key_parts) + 1)
                )
            if key_index >= len(key_parts):
                return False
            if token != "*" and token != key_parts[key_index]:
                return False
            pattern_index += 1
            key_index += 1
        return key_index == len(key_parts)

    return match(0, 0)


@dataclass(frozen=True)
class TransportMetadata:
    message_id: str
    correlation_id: str
    origin: str
    action: str
    schema: str
    event_type: str
    causation_id: str | None = None
    adobe_customer_id: str | None = None
    integration_write: bool | None = None

    def validate_for_route(
        self,
        routing_key: str,
        *,
        expected_origin: str | None = None,
        allowed_actions: set[str] | None = None,
        expected_schema: str | None = None,
        expected_event_type: str | None = None,
        require_adobe_customer_id: bool = False,
    ) -> None:
        route_origin, route_action = parse_routing_key(routing_key)
        if self.origin != route_origin:
            raise MetadataValidationError(
                f"x-origin {self.origin!r} does not match routing key origin {route_origin!r}"
            )
        if self.action != route_action:
            raise MetadataValidationError(
                f"x-action {self.action!r} does not match routing key action {route_action!r}"
            )
        if expected_origin is not None and self.origin != expected_origin:
            raise MetadataValidationError(
                f"Route origin must be {expected_origin!r}, got {self.origin!r}"
            )
        if allowed_actions is not None and self.action not in allowed_actions:
            raise MetadataValidationError(
                f"Action {self.action!r} is outside the enabled POC actions"
            )
        if expected_schema is not None and self.schema != expected_schema:
            raise MetadataValidationError(
                f"x-schema must be {expected_schema!r}, got {self.schema!r}"
            )
        if expected_event_type is not None and self.event_type != expected_event_type:
            raise MetadataValidationError(
                f"type must be {expected_event_type!r}, got {self.event_type!r}"
            )
        if require_adobe_customer_id and self.adobe_customer_id is None:
            raise MetadataValidationError("Missing required metadata: x-adobe-customer-id")

    def amqp_headers(self) -> dict[str, Any]:
        headers: dict[str, Any] = {
            "x-origin": self.origin,
            "x-action": self.action,
            "x-schema": self.schema,
        }
        if self.causation_id is not None:
            headers["x-causation-id"] = self.causation_id
        if self.adobe_customer_id is not None:
            headers["x-adobe-customer-id"] = self.adobe_customer_id
        if self.integration_write is not None:
            headers["x-integration-write"] = self.integration_write
        return headers

    def orbital_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/xml",
            "X-Message-Id": self.message_id,
            "X-Correlation-Id": self.correlation_id,
            "X-System-Origin": self.origin,
            "X-Account-Action": self.action,
            "X-Schema": self.schema,
            "X-Event-Type": self.event_type,
        }
        if self.causation_id is not None:
            headers["X-Causation-Id"] = self.causation_id
        if self.adobe_customer_id is not None:
            headers["X-Adobe-Customer-Id"] = self.adobe_customer_id
        if self.integration_write is not None:
            headers["X-Integration-Write"] = str(self.integration_write).lower()
        return headers


def metadata_from_http(
    headers: Mapping[str, Any],
    *,
    routing_key: str,
    default_schema: str,
    default_event_type: str,
) -> TransportMetadata:
    values = _normalized(headers)
    metadata = TransportMetadata(
        message_id=_uuid(_required(values, "x-message-id"), "X-Message-Id"),
        correlation_id=_uuid(
            _required(values, "x-correlation-id"), "X-Correlation-Id"
        ),
        causation_id=(
            _uuid(value, "X-Causation-Id")
            if (value := _string(values.get("x-causation-id"))) is not None
            else None
        ),
        origin=_required(values, "x-system-origin").lower(),
        action=_required(values, "x-account-action").upper(),
        schema=_string(values.get("x-schema")) or default_schema,
        event_type=_string(values.get("x-event-type")) or default_event_type,
        adobe_customer_id=_string(values.get("x-adobe-customer-id")),
        integration_write=_optional_bool(
            values.get("x-integration-write"), "X-Integration-Write"
        ),
    )
    metadata.validate_for_route(
        routing_key,
        expected_origin="adobe",
        allowed_actions={"UPDATE"},
        expected_schema=default_schema,
        expected_event_type=default_event_type,
    )
    return metadata


def metadata_from_amqp(
    routing_key: str,
    properties: Any,
    *,
    expected_schema: str,
    expected_routing_pattern: str | None = None,
    expected_event_type: str | None = None,
    expected_origin: str = "sap",
    require_adobe_customer_id: bool = True,
) -> TransportMetadata:
    if expected_routing_pattern is not None and not routing_key_matches(
        expected_routing_pattern, routing_key
    ):
        raise MetadataValidationError(
            f"Routing key {routing_key!r} does not match configured pattern "
            f"{expected_routing_pattern!r}"
        )
    headers = _normalized(getattr(properties, "headers", None) or {})
    content_type = _string(getattr(properties, "content_type", None))
    if content_type != "application/xml":
        raise MetadataValidationError(
            f"content_type must be 'application/xml', got {content_type!r}"
        )
    delivery_mode = getattr(properties, "delivery_mode", None)
    if delivery_mode != 2:
        raise MetadataValidationError(
            f"delivery_mode must be 2, got {delivery_mode!r}"
        )

    message_id = _string(getattr(properties, "message_id", None))
    correlation_id = _string(getattr(properties, "correlation_id", None))
    event_type = _string(getattr(properties, "type", None))
    if message_id is None:
        raise MetadataValidationError("Missing required metadata: message_id")
    if correlation_id is None:
        raise MetadataValidationError("Missing required metadata: correlation_id")
    if event_type is None:
        raise MetadataValidationError("Missing required metadata: type")

    metadata = TransportMetadata(
        message_id=_uuid(message_id, "message_id"),
        correlation_id=_uuid(correlation_id, "correlation_id"),
        causation_id=(
            _uuid(value, "x-causation-id")
            if (value := _string(headers.get("x-causation-id"))) is not None
            else None
        ),
        origin=_required(headers, "x-origin").lower(),
        action=_required(headers, "x-action").upper(),
        schema=_required(headers, "x-schema"),
        event_type=event_type,
        adobe_customer_id=_string(headers.get("x-adobe-customer-id")),
        integration_write=_optional_bool(
            headers.get("x-integration-write"), "x-integration-write"
        ),
    )
    metadata.validate_for_route(
        routing_key,
        expected_origin=expected_origin,
        allowed_actions={"UPDATE"},
        expected_schema=expected_schema,
        expected_event_type=expected_event_type,
        require_adobe_customer_id=require_adobe_customer_id,
    )
    return metadata
