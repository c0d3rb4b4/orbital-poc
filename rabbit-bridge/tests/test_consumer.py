import json
from dataclasses import replace
from types import SimpleNamespace

import httpx

from app.config import Settings
from app.consumer import OrbitalForwarder, RabbitConsumer
from app.metadata import TransportMetadata


MESSAGE_ID = "11111111-1111-4111-8111-111111111111"
CORRELATION_ID = "22222222-2222-4222-8222-222222222222"
XML = b"<ZBUPA_CBO><IDOC /></ZBUPA_CBO>"


class FakeChannel:
    def __init__(self) -> None:
        self.acked = []
        self.rejected = []

    def basic_ack(self, *, delivery_tag) -> None:
        self.acked.append(delivery_tag)

    def basic_reject(self, *, delivery_tag, requeue) -> None:
        self.rejected.append((delivery_tag, requeue))


class FakeForwarder:
    def __init__(self, result=True) -> None:
        self.result = result
        self.calls = []

    def forward(self, body, metadata) -> bool:
        self.calls.append((body, metadata))
        return self.result

    def close(self) -> None:
        pass


def properties(*, origin="sap", action="UPDATE", adobe_customer_id="42"):
    headers = {
        "x-origin": origin,
        "x-action": action,
        "x-schema": "sap.zbupa-cbo.v1",
    }
    if adobe_customer_id is not None:
        headers["x-adobe-customer-id"] = adobe_customer_id
    return SimpleNamespace(
        content_type="application/xml",
        delivery_mode=2,
        message_id=MESSAGE_ID,
        correlation_id=CORRELATION_ID,
        type="customer-account.updated.v1",
        headers=headers,
    )


def method(routing_key="customer-account.sap.updated"):
    return SimpleNamespace(delivery_tag=7, routing_key=routing_key)


def test_consumer_acknowledges_only_after_successful_forward() -> None:
    channel = FakeChannel()
    forwarder = FakeForwarder(result=True)
    consumer = RabbitConsumer(Settings(), forwarder)

    consumer.handle_delivery(channel, method(), properties(), XML)

    assert channel.acked == [7]
    assert channel.rejected == []
    assert forwarder.calls[0][0] == XML
    assert forwarder.calls[0][1].orbital_headers()["X-Adobe-Customer-Id"] == "42"


def test_consumer_rejects_without_requeue_after_non_2xx() -> None:
    channel = FakeChannel()
    forwarder = FakeForwarder(result=False)
    consumer = RabbitConsumer(Settings(), forwarder)

    consumer.handle_delivery(channel, method(), properties(), XML)

    assert channel.acked == []
    assert channel.rejected == [(7, False)]
    assert len(forwarder.calls) == 1


def test_consumer_rejects_invalid_route_without_forwarding() -> None:
    channel = FakeChannel()
    forwarder = FakeForwarder(result=True)
    consumer = RabbitConsumer(Settings(), forwarder)

    consumer.handle_delivery(
        channel,
        method("customer-account.adobe.updated"),
        properties(origin="sap"),
        XML,
    )

    assert channel.acked == []
    assert channel.rejected == [(7, False)]
    assert forwarder.calls == []


def test_consumer_uses_origin_and_identity_policy_for_adobe_fwt_worker() -> None:
    channel = FakeChannel()
    forwarder = FakeForwarder(result=True)
    settings = replace(
        Settings(),
        consumer_queue="poc.customer-account.adobe-to-fwt",
        consumer_routing_pattern="customer-account.adobe.*",
        consumer_expected_origin="adobe",
        consumer_require_adobe_customer_id=False,
        orbital_consumer_path="/api/q/customer-account/to-fwt",
    )
    consumer = RabbitConsumer(settings, forwarder)

    consumer.handle_delivery(
        channel,
        method("customer-account.adobe.updated"),
        properties(origin="adobe", adobe_customer_id=None),
        XML,
    )

    assert channel.acked == [7]
    assert channel.rejected == []
    metadata = forwarder.calls[0][1]
    assert metadata.origin == "adobe"
    assert "X-Adobe-Customer-Id" not in metadata.orbital_headers()


def test_orbital_forwarder_preserves_raw_xml_and_lineage_headers() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["headers"] = request.headers
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    forwarder = OrbitalForwarder(
        "http://orbital:9022/api/q/customer-account/from-sap",
        timeout=1,
        client=client,
    )
    metadata = TransportMetadata(
        message_id=MESSAGE_ID,
        correlation_id=CORRELATION_ID,
        origin="sap",
        action="UPDATE",
        schema="sap.zbupa-cbo.v1",
        event_type="customer-account.updated.v1",
        adobe_customer_id="42",
    )

    assert forwarder.forward(XML, metadata) is True
    assert captured["body"] == XML
    assert captured["headers"]["content-type"] == "application/xml"
    assert captured["headers"]["x-message-id"] == MESSAGE_ID
    assert captured["headers"]["x-system-origin"] == "sap"
    assert captured["headers"]["x-adobe-customer-id"] == "42"

    client.close()


def test_orbital_forwarder_adapts_xml_to_json_for_fwt_worker() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["headers"] = request.headers
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    forwarder = OrbitalForwarder(
        "http://orbital:9022/api/q/customer-account/to-fwt",
        timeout=1,
        client=client,
        payload_format="json",
    )
    metadata = TransportMetadata(
        message_id=MESSAGE_ID,
        correlation_id=CORRELATION_ID,
        origin="adobe",
        action="UPDATE",
        schema="sap.zbupa-cbo.v1",
        event_type="customer-account.updated.v1",
    )
    xml = b"""<ZBUPA_CBO><IDOC BEGIN="1"><ZBP_CBO SEGMENT="1">
      <KUNNR>00010001</KUNNR>
    </ZBP_CBO></IDOC></ZBUPA_CBO>"""

    assert forwarder.forward(xml, metadata) is True
    assert json.loads(captured["body"]) == {
        "IDOC": {
            "BEGIN": "1",
            "ZBP_CBO": {"SEGMENT": "1", "KUNNR": "00010001"},
        }
    }
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["headers"]["x-system-origin"] == "adobe"

    client.close()
