from __future__ import annotations

import json
from typing import Any
from xml.etree import ElementTree


class SapXmlSerializationError(ValueError):
    pass


_ATTRIBUTE_NAMES = {
    "IDOC": {"BEGIN"},
    "EDI_DC40": {"SEGMENT"},
    "ZBP_CBO": {"SEGMENT"},
    "ZBP_CBO2": {"SEGMENT"},
}


def sap_json_to_xml(body: bytes) -> bytes:
    """Serialize Orbital's projected SAP object without changing its values."""
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SapXmlSerializationError("Request body must be valid JSON") from exc

    if not isinstance(payload, dict) or set(payload) != {"IDOC"}:
        raise SapXmlSerializationError(
            "SAP publish payload must contain exactly one IDOC object"
        )
    if not isinstance(payload["IDOC"], dict):
        raise SapXmlSerializationError("IDOC must be an object")

    root = ElementTree.Element("ZBUPA_CBO")
    _append_element(root, "IDOC", payload["IDOC"])
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _append_element(parent: ElementTree.Element, name: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            _append_element(parent, name, item)
        return

    element = ElementTree.SubElement(parent, name)
    if isinstance(value, dict):
        attribute_names = _ATTRIBUTE_NAMES.get(name, set())
        for key, child_value in value.items():
            if child_value is None:
                continue
            if key in attribute_names:
                if isinstance(child_value, (dict, list)):
                    raise SapXmlSerializationError(
                        f"XML attribute {name}.{key} must be a scalar value"
                    )
                element.set(key, _scalar_text(child_value))
            else:
                _append_element(element, key, child_value)
        return

    element.text = _scalar_text(value)


def _scalar_text(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (str, int, float)):
        return str(value)
    raise SapXmlSerializationError(
        f"Unsupported SAP XML value type: {type(value).__name__}"
    )
