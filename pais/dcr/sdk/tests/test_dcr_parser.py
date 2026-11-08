from dcr_sdk import Event, Graph, Sim
from dcr_sdk.utils.dcr_parser import DCR_Parser

from .constants import ACCOUNT_GRAPH_BODY, GRAPH_SIMS_BODY, SIM_EVENTS_BODY


def test_parse_graphs():
    assert DCR_Parser.parse_graphs(ACCOUNT_GRAPH_BODY) == [
        Graph(
            id=2016035,
            title="DCR_Test",
            description="DCR Process",
            created="2026-11-04T18:18:29.430",
            modified="2026-11-04T18:21:06.733",
        ),
        Graph(
            id=2016043,
            title="Payout",
            description="DCR Process",
            created="2026-11-05T08:55:00.140",
            modified="2026-11-05T08:56:49.057",
        ),
    ]


def test_parse_graphs_empty():
    assert DCR_Parser.parse_graphs("<graphs></graphs>") == []


def test_parse_sims():
    assert DCR_Parser.parse_sims(GRAPH_SIMS_BODY) == [
        Sim(
            id=2108181,
            title="DCR",
            init="2026-11-06T20:45:44",
            percentage=0.0,
            is_scenario=False,
            created="2026-11-06T20:45:44.127Z",
            created_by=176191,
            modified="2026-11-06T21:45:44.120Z",
            modified_by=176191,
            business_type="none",
        ),
        Sim(
            id=2108182,
            title="DCR",
            init="2026-11-06T20:47:26",
            percentage=0.0,
            is_scenario=False,
            created="2026-11-06T20:47:26.247Z",
            created_by=176191,
            modified="2026-11-06T21:47:26.243Z",
            modified_by=176191,
            business_type="none",
        ),
    ]


def test_parse_sims_empty():
    assert DCR_Parser.parse_sims("<log></log>") == []


def test_parse_state():
    state = DCR_Parser.parse_state(SIM_EVENTS_BODY)

    assert state.next_delay is None
    assert state.next_deadline is None
    assert state.is_accepting is False
    assert state.current_time == "2026-11-05T07:53:58.8474492+00:00"
    assert state.current_phase == 0
    assert list(state.events) == ["Approve", "FilloutExpenseReport", "Payout"]
    assert state.events["Payout"] == Event(
        id="Payout",
        included=True,
        enabled=False,
        pending=False,
        effectively_pending=False,
        effectively_included=True,
        executed=False,
        full_path="Payout",
        roles="Finance",
        groups="",
        description="<p>We pay out using our ERP system SAP.</p>",
        label="Pay out",
        event_type="",
        phases="50,100",
        deadline="",
        sequence=1,
        parent="",
        type="",
        refer_id="",
        event_type_data="",
    )
