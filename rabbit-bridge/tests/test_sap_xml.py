import json
from xml.etree import ElementTree

import pytest

from app.sap_xml import SapXmlSerializationError, sap_json_to_xml, sap_xml_to_json


def test_serializes_projected_sap_json_as_idoc_xml() -> None:
    xml = sap_json_to_xml(
        b'''{
          "IDOC": {
            "BEGIN": "1",
            "EDI_DC40": {"SEGMENT": "1", "TABNAM": "EDI_DC40"},
            "ZBP_CBO": {
              "SEGMENT": "1",
              "KUNNR": "00010001",
              "ANRED": null,
              "NAME1": "Ada & Grace"
            },
            "ZBP_CBO2": {"SEGMENT": "1", "KATR10": "PEM"}
          }
        }'''
    )

    root = ElementTree.fromstring(xml)
    assert root.tag == "ZBUPA_CBO"
    assert root.find("IDOC").attrib == {"BEGIN": "1"}
    assert root.find("IDOC/EDI_DC40").attrib == {"SEGMENT": "1"}
    assert root.findtext("IDOC/ZBP_CBO/KUNNR") == "00010001"
    assert root.find("IDOC/ZBP_CBO/ANRED") is None
    assert root.findtext("IDOC/ZBP_CBO/NAME1") == "Ada & Grace"


def test_adapts_idoc_xml_to_json_without_changing_values() -> None:
    payload = json.loads(
        sap_xml_to_json(
            b"""<ZBUPA_CBO>
              <IDOC BEGIN="1">
                <ZBP_CBO SEGMENT="1">
                  <KUNNR>00010001</KUNNR>
                  <NAME1>Ada &amp; Grace</NAME1>
                  <CODE> 01 </CODE>
                  <TAG>first</TAG>
                  <TAG>second</TAG>
                </ZBP_CBO>
              </IDOC>
            </ZBUPA_CBO>"""
        )
    )

    assert payload == {
        "IDOC": {
            "BEGIN": "1",
            "ZBP_CBO": {
                "SEGMENT": "1",
                "KUNNR": "00010001",
                "NAME1": "Ada & Grace",
                "CODE": " 01 ",
                "TAG": ["first", "second"],
            },
        }
    }


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"[]",
        b'{}',
        b'{"IDOC": null}',
        b'{"IDOC": {}, "unexpected": {}}',
    ],
)
def test_rejects_invalid_publish_envelopes(body: bytes) -> None:
    with pytest.raises(SapXmlSerializationError):
        sap_json_to_xml(body)


@pytest.mark.parametrize(
    "body",
    [
        b"not-xml",
        b"<IDOC />",
        b"<ZBUPA_CBO />",
        b"<ZBUPA_CBO><IDOC /><IDOC /></ZBUPA_CBO>",
        b"<ZBUPA_CBO><IDOC /><unexpected /></ZBUPA_CBO>",
        b'<ZBUPA_CBO version="1"><IDOC /></ZBUPA_CBO>',
    ],
)
def test_rejects_invalid_xml_adaptation_envelopes(body: bytes) -> None:
    with pytest.raises(SapXmlSerializationError):
        sap_xml_to_json(body)
