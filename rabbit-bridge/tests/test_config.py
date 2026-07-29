import pytest

from app.config import Settings


def test_generic_consumer_environment_names_are_loaded(monkeypatch) -> None:
    monkeypatch.setenv("BRIDGE_PORT", "8181")
    monkeypatch.setenv(
        "RABBITMQ_ADOBE_TO_SAP_ROUTING_KEY", "customer-account.adobe.updated"
    )
    monkeypatch.setenv(
        "RABBITMQ_CONSUMER_QUEUE", "custom.customer-account.adobe-to-fwt"
    )
    monkeypatch.setenv(
        "RABBITMQ_CONSUMER_ROUTING_PATTERN", "customer-account.adobe.updated"
    )
    monkeypatch.setenv("RABBITMQ_CONSUMER_EXPECTED_ORIGIN", "ADOBE")
    monkeypatch.setenv("RABBITMQ_CONSUMER_REQUIRE_ADOBE_CUSTOMER_ID", "false")
    monkeypatch.setenv("ORBITAL_CONSUMER_PATH", "/api/q/custom/to-fwt")
    monkeypatch.setenv("ORBITAL_CONSUMER_PAYLOAD_FORMAT", "JSON")

    settings = Settings.from_env()

    assert settings.bridge_port == 8181
    assert settings.adobe_to_sap_routing_key == "customer-account.adobe.updated"
    assert settings.consumer_queue == "custom.customer-account.adobe-to-fwt"
    assert settings.consumer_routing_pattern == "customer-account.adobe.updated"
    assert settings.consumer_expected_origin == "adobe"
    assert settings.consumer_require_adobe_customer_id is False
    assert settings.orbital_consumer_path == "/api/q/custom/to-fwt"
    assert settings.orbital_consumer_url == "http://orbital:9022/api/q/custom/to-fwt"
    assert settings.orbital_consumer_payload_format == "json"


def test_legacy_sap_to_adobe_environment_names_remain_fallbacks(monkeypatch) -> None:
    monkeypatch.setenv(
        "RABBITMQ_SAP_TO_ADOBE_QUEUE", "custom.customer-account.sap-to-adobe"
    )
    monkeypatch.setenv(
        "RABBITMQ_SAP_TO_ADOBE_ROUTING_PATTERN", "customer-account.sap.updated"
    )
    monkeypatch.setenv("ORBITAL_SAP_TO_ADOBE_PATH", "/api/q/custom/from-sap")

    settings = Settings.from_env()

    assert settings.sap_to_adobe_queue == "custom.customer-account.sap-to-adobe"
    assert settings.sap_to_adobe_routing_pattern == "customer-account.sap.updated"
    assert settings.orbital_sap_to_adobe_path == "/api/q/custom/from-sap"
    assert settings.orbital_sap_url == "http://orbital:9022/api/q/custom/from-sap"


def test_generic_environment_names_take_precedence_over_legacy_names(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RABBITMQ_CONSUMER_QUEUE", "generic-queue")
    monkeypatch.setenv("RABBITMQ_SAP_TO_ADOBE_QUEUE", "legacy-queue")
    monkeypatch.setenv("ORBITAL_CONSUMER_PATH", "/generic")
    monkeypatch.setenv("ORBITAL_SAP_TO_ADOBE_PATH", "/legacy")

    settings = Settings.from_env()

    assert settings.consumer_queue == "generic-queue"
    assert settings.orbital_consumer_path == "/generic"


def test_consumer_payload_format_defaults_to_xml() -> None:
    assert Settings().orbital_consumer_payload_format == "xml"


def test_consumer_payload_format_rejects_unsupported_value(monkeypatch) -> None:
    monkeypatch.setenv("ORBITAL_CONSUMER_PAYLOAD_FORMAT", "yaml")

    with pytest.raises(ValueError, match="must be one of: json, xml"):
        Settings.from_env()
