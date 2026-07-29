import json
from dataclasses import replace
from xml.etree import ElementTree

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.publisher import UnroutablePublishError


MESSAGE_ID = "11111111-1111-4111-8111-111111111111"
CORRELATION_ID = "22222222-2222-4222-8222-222222222222"
XML = b"<ZBUPA_CBO><IDOC><ZBP_CBO><KUNNR>00042</KUNNR></ZBP_CBO></IDOC></ZBUPA_CBO>"


class FakePublisher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []
        self.closed = False

    def publish(self, body, metadata, routing_key) -> None:
        if self.error:
            raise self.error
        self.calls.append((body, metadata, routing_key))

    def close(self) -> None:
        self.closed = True


def headers() -> dict[str, str]:
    return {
        "Content-Type": "application/xml",
        "X-Message-Id": MESSAGE_ID,
        "X-Correlation-Id": CORRELATION_ID,
        "X-System-Origin": "adobe",
        "X-Account-Action": "UPDATE",
        "X-Adobe-Customer-Id": "42",
    }


def test_publish_forwards_raw_xml_after_metadata_validation() -> None:
    settings = replace(Settings(), consumer_enabled=False)
    publisher = FakePublisher()
    app = create_app(settings, publisher=publisher)

    with TestClient(app) as client:
        response = client.post("/publish", content=XML, headers=headers())

    assert response.status_code == 202
    assert response.json()["status"] == "published"
    assert len(publisher.calls) == 1
    body, metadata, routing_key = publisher.calls[0]
    assert body == XML
    assert metadata.message_id == MESSAGE_ID
    assert metadata.origin == "adobe"
    assert routing_key == "customer-account.adobe.updated"
    assert publisher.closed is True


def test_publish_serializes_orbital_json_to_sap_xml() -> None:
    settings = replace(Settings(), consumer_enabled=False)
    publisher = FakePublisher()
    app = create_app(settings, publisher=publisher)
    request_headers = headers() | {"Content-Type": "application/json"}
    payload = {
        "IDOC": {
            "BEGIN": "1",
            "ZBP_CBO": {"SEGMENT": "1", "KUNNR": "00010001"},
        }
    }

    with TestClient(app) as client:
        response = client.post(
            "/publish",
            content=json.dumps(payload),
            headers=request_headers,
        )

    assert response.status_code == 202
    published_body = publisher.calls[0][0]
    root = ElementTree.fromstring(published_body)
    assert root.tag == "ZBUPA_CBO"
    assert root.find("IDOC").attrib == {"BEGIN": "1"}
    assert root.findtext("IDOC/ZBP_CBO/KUNNR") == "00010001"


def test_publish_rejects_invalid_orbital_json() -> None:
    settings = replace(Settings(), consumer_enabled=False)
    publisher = FakePublisher()
    app = create_app(settings, publisher=publisher)
    request_headers = headers() | {"Content-Type": "application/json"}

    with TestClient(app) as client:
        response = client.post(
            "/publish",
            content=b'{"not_idoc": {}}',
            headers=request_headers,
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_SAP_PAYLOAD"
    assert publisher.calls == []


def test_publish_does_not_call_rabbit_for_invalid_route_metadata() -> None:
    settings = replace(Settings(), consumer_enabled=False)
    publisher = FakePublisher()
    app = create_app(settings, publisher=publisher)
    invalid_headers = headers() | {"X-System-Origin": "sap"}

    with TestClient(app) as client:
        response = client.post("/publish", content=XML, headers=invalid_headers)

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ROUTE_METADATA"
    assert publisher.calls == []


def test_publish_reports_mandatory_unroutable_failure() -> None:
    settings = replace(Settings(), consumer_enabled=False)
    publisher = FakePublisher(UnroutablePublishError("no binding"))
    app = create_app(settings, publisher=publisher)

    with TestClient(app) as client:
        response = client.post("/publish", content=XML, headers=headers())

    assert response.status_code == 503
    assert response.json() == {"code": "UNROUTABLE", "message": "no binding"}


def test_health_is_available_when_consumer_is_disabled() -> None:
    settings = replace(Settings(), consumer_enabled=False)
    app = create_app(settings, publisher=FakePublisher())

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "consumer": {"enabled": False}}
