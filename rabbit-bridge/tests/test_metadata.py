from types import SimpleNamespace

import pytest

from app.metadata import (
    MetadataValidationError,
    metadata_from_amqp,
    metadata_from_http,
)


MESSAGE_ID = "11111111-1111-4111-8111-111111111111"
CORRELATION_ID = "22222222-2222-4222-8222-222222222222"
CAUSATION_ID = "33333333-3333-4333-8333-333333333333"


def test_http_metadata_matches_publish_route() -> None:
    metadata = metadata_from_http(
        {
            "X-Message-Id": MESSAGE_ID,
            "X-Correlation-Id": CORRELATION_ID,
            "X-System-Origin": "adobe",
            "X-Account-Action": "UPDATE",
            "X-Adobe-Customer-Id": "42",
        },
        routing_key="customer-account.adobe.updated",
        default_schema="sap.zbupa-cbo.v1",
        default_event_type="customer-account.updated.v1",
    )

    assert metadata.message_id == MESSAGE_ID
    assert metadata.origin == "adobe"
    assert metadata.action == "UPDATE"
    assert metadata.adobe_customer_id == "42"
    assert metadata.amqp_headers()["x-schema"] == "sap.zbupa-cbo.v1"


def test_http_metadata_rejects_origin_route_mismatch() -> None:
    with pytest.raises(MetadataValidationError, match="Route origin must be 'adobe'"):
        metadata_from_http(
            {
                "X-Message-Id": MESSAGE_ID,
                "X-Correlation-Id": CORRELATION_ID,
                "X-System-Origin": "sap",
                "X-Account-Action": "UPDATE",
            },
            routing_key="customer-account.sap.updated",
            default_schema="sap.zbupa-cbo.v1",
            default_event_type="customer-account.updated.v1",
        )


def test_amqp_metadata_is_validated_and_mapped_to_orbital_headers() -> None:
    properties = SimpleNamespace(
        content_type="application/xml",
        delivery_mode=2,
        message_id=MESSAGE_ID,
        correlation_id=CORRELATION_ID,
        type="customer-account.updated.v1",
        headers={
            "x-origin": "sap",
            "x-action": "UPDATE",
            "x-schema": "sap.zbupa-cbo.v1",
            "x-causation-id": CAUSATION_ID,
            "x-adobe-customer-id": "42",
            "x-integration-write": False,
        },
    )

    metadata = metadata_from_amqp(
        "customer-account.sap.updated",
        properties,
        expected_schema="sap.zbupa-cbo.v1",
        expected_routing_pattern="customer-account.sap.*",
        expected_event_type="customer-account.updated.v1",
    )

    headers = metadata.orbital_headers()
    assert headers["X-Message-Id"] == MESSAGE_ID
    assert headers["X-Correlation-Id"] == CORRELATION_ID
    assert headers["X-Causation-Id"] == CAUSATION_ID
    assert headers["X-System-Origin"] == "sap"
    assert headers["X-Account-Action"] == "UPDATE"
    assert headers["X-Adobe-Customer-Id"] == "42"
    assert headers["X-Integration-Write"] == "false"


@pytest.mark.parametrize(
    ("routing_key", "origin", "action"),
    [
        ("customer-account.adobe.updated", "sap", "UPDATE"),
        ("customer-account.sap.created", "sap", "UPDATE"),
        ("customer-account.sap.updated.extra", "sap", "UPDATE"),
    ],
)
def test_amqp_metadata_rejects_inconsistent_routing(
    routing_key: str,
    origin: str,
    action: str,
) -> None:
    properties = SimpleNamespace(
        content_type="application/xml",
        delivery_mode=2,
        message_id=MESSAGE_ID,
        correlation_id=CORRELATION_ID,
        type="customer-account.updated.v1",
        headers={
            "x-origin": origin,
            "x-action": action,
            "x-schema": "sap.zbupa-cbo.v1",
            "x-adobe-customer-id": "42",
        },
    )

    with pytest.raises(MetadataValidationError):
        metadata_from_amqp(
            routing_key,
            properties,
            expected_schema="sap.zbupa-cbo.v1",
            expected_routing_pattern="customer-account.sap.*",
            expected_event_type="customer-account.updated.v1",
        )


def test_amqp_metadata_requires_reverse_route_identity() -> None:
    properties = SimpleNamespace(
        content_type="application/xml",
        delivery_mode=2,
        message_id=MESSAGE_ID,
        correlation_id=CORRELATION_ID,
        type="customer-account.updated.v1",
        headers={
            "x-origin": "sap",
            "x-action": "UPDATE",
            "x-schema": "sap.zbupa-cbo.v1",
        },
    )

    with pytest.raises(MetadataValidationError, match="x-adobe-customer-id"):
        metadata_from_amqp(
            "customer-account.sap.updated",
            properties,
            expected_schema="sap.zbupa-cbo.v1",
            expected_routing_pattern="customer-account.sap.*",
            expected_event_type="customer-account.updated.v1",
        )


@pytest.mark.parametrize("origin", ["adobe", "sap"])
def test_amqp_metadata_supports_fwt_routes_without_reverse_identity(origin: str) -> None:
    properties = SimpleNamespace(
        content_type="application/xml",
        delivery_mode=2,
        message_id=MESSAGE_ID,
        correlation_id=CORRELATION_ID,
        type="customer-account.updated.v1",
        headers={
            "x-origin": origin,
            "x-action": "UPDATE",
            "x-schema": "sap.zbupa-cbo.v1",
        },
    )

    metadata = metadata_from_amqp(
        f"customer-account.{origin}.updated",
        properties,
        expected_schema="sap.zbupa-cbo.v1",
        expected_routing_pattern=f"customer-account.{origin}.*",
        expected_event_type="customer-account.updated.v1",
        expected_origin=origin,
        require_adobe_customer_id=False,
    )

    assert metadata.origin == origin
    assert metadata.adobe_customer_id is None


def test_amqp_metadata_rejects_origin_outside_configured_worker_route() -> None:
    properties = SimpleNamespace(
        content_type="application/xml",
        delivery_mode=2,
        message_id=MESSAGE_ID,
        correlation_id=CORRELATION_ID,
        type="customer-account.updated.v1",
        headers={
            "x-origin": "sap",
            "x-action": "UPDATE",
            "x-schema": "sap.zbupa-cbo.v1",
        },
    )

    with pytest.raises(MetadataValidationError, match="Route origin must be 'adobe'"):
        metadata_from_amqp(
            "customer-account.sap.updated",
            properties,
            expected_schema="sap.zbupa-cbo.v1",
            expected_routing_pattern="customer-account.sap.*",
            expected_event_type="customer-account.updated.v1",
            expected_origin="adobe",
            require_adobe_customer_id=False,
        )
