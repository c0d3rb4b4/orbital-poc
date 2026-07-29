from app.config import Settings
from app.metadata import TransportMetadata
from app.publisher import RabbitPublisher


class FakeChannel:
    def __init__(self) -> None:
        self.is_open = True
        self.confirmed = False
        self.publish_kwargs = None

    def confirm_delivery(self) -> None:
        self.confirmed = True

    def basic_publish(self, **kwargs):
        self.publish_kwargs = kwargs
        return True

    def close(self) -> None:
        self.is_open = False


class FakeConnection:
    def __init__(self) -> None:
        self.is_open = True
        self.fake_channel = FakeChannel()

    def channel(self):
        return self.fake_channel

    def close(self) -> None:
        self.is_open = False


def test_publisher_enables_confirms_and_mandatory_routing() -> None:
    connection = FakeConnection()
    publisher = RabbitPublisher(Settings(), connection_factory=lambda _: connection)
    metadata = TransportMetadata(
        message_id="11111111-1111-4111-8111-111111111111",
        correlation_id="22222222-2222-4222-8222-222222222222",
        origin="adobe",
        action="UPDATE",
        schema="sap.zbupa-cbo.v1",
        event_type="customer-account.updated.v1",
        adobe_customer_id="42",
    )

    publisher.publish(
        b"<ZBUPA_CBO />",
        metadata,
        "customer-account.adobe.updated",
    )

    channel = connection.fake_channel
    assert channel.confirmed is True
    assert channel.publish_kwargs["exchange"] == "poc.customer-account.events"
    assert channel.publish_kwargs["routing_key"] == "customer-account.adobe.updated"
    assert channel.publish_kwargs["mandatory"] is True
    properties = channel.publish_kwargs["properties"]
    assert properties.delivery_mode == 2
    assert properties.content_type == "application/xml"
    assert properties.message_id == metadata.message_id
    assert properties.headers["x-origin"] == "adobe"

