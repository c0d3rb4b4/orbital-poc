from app.config import Settings


def test_compose_environment_names_are_loaded(monkeypatch) -> None:
    monkeypatch.setenv("BRIDGE_PORT", "8181")
    monkeypatch.setenv(
        "RABBITMQ_ADOBE_TO_SAP_ROUTING_KEY", "customer-account.adobe.updated"
    )
    monkeypatch.setenv(
        "RABBITMQ_SAP_TO_ADOBE_QUEUE", "custom.customer-account.sap-to-adobe"
    )
    monkeypatch.setenv(
        "RABBITMQ_SAP_TO_ADOBE_ROUTING_PATTERN", "customer-account.sap.updated"
    )
    monkeypatch.setenv(
        "ORBITAL_SAP_TO_ADOBE_PATH", "/api/q/custom/from-sap"
    )

    settings = Settings.from_env()

    assert settings.bridge_port == 8181
    assert settings.adobe_to_sap_routing_key == "customer-account.adobe.updated"
    assert settings.sap_to_adobe_queue == "custom.customer-account.sap-to-adobe"
    assert settings.sap_to_adobe_routing_pattern == "customer-account.sap.updated"
    assert settings.orbital_sap_to_adobe_path == "/api/q/custom/from-sap"
    assert settings.orbital_sap_url == "http://orbital:9022/api/q/custom/from-sap"

