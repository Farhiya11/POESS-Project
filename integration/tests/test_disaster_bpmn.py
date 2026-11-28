import xml.etree.ElementTree as ET
from pathlib import Path


BPMN_PATH = (
    Path(__file__).parents[2]
    / "pais"
    / "bpmn"
    / "microservice"
    / "Disaster_Attention_Protocol_camunda.bpmn"
)
BPMN_NAMESPACE = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
ZEEBE_NAMESPACE = "{http://camunda.org/schema/zeebe/1.0}"


def test_alert_updates_are_correlated_and_each_stage_has_a_worker() -> None:
    root = ET.parse(BPMN_PATH).getroot()
    message = root.find(f"{BPMN_NAMESPACE}message[@name='AlertLevelUpdated']")
    assert message is not None
    subscription = message.find(
        f"{BPMN_NAMESPACE}extensionElements/{ZEEBE_NAMESPACE}subscription"
    )
    assert subscription is not None
    assert subscription.attrib["correlationKey"] == "=caseId"

    task_types = {
        task_definition.attrib.get("type")
        for task_definition in root.findall(f".//{ZEEBE_NAMESPACE}taskDefinition")
    }
    assert {
        "evaluate-forecast",
        "prepare-internal",
        "prepare-information",
        "prepare-staff",
        "send-preparedness-notice",
    }.issubset(task_types)


def test_bpmn_references_resolve_and_alert_clear_terminates_escalation() -> None:
    root = ET.parse(BPMN_PATH).getroot()
    ids = [element.attrib["id"] for element in root.iter() if "id" in element.attrib]
    assert len(ids) == len(set(ids))
    known_ids = set(ids)

    for attribute in ("sourceRef", "targetRef", "messageRef"):
        for element in root.iter():
            reference = element.attrib.get(attribute)
            if reference is not None:
                assert reference in known_ids, f"Unresolved {attribute}: {reference}"

    clear_event = root.find(
        f".//{BPMN_NAMESPACE}endEvent[@id='Event_AlertCleared']"
    )
    assert clear_event is not None
    assert len(clear_event.findall(f"{BPMN_NAMESPACE}incoming")) == 3

    receive_events = [
        event
        for event in root.findall(f".//{BPMN_NAMESPACE}intermediateCatchEvent")
        if event.attrib.get("id", "").startswith("Event_WaitFor")
    ]
    assert len(receive_events) == 3
    assert all(
        event.find(
            f"{BPMN_NAMESPACE}messageEventDefinition[@messageRef='Message_AlertLevelUpdated']"
        )
        is not None
        for event in receive_events
    )
