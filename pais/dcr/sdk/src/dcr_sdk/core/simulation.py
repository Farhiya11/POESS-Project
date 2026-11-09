from __future__ import annotations

import json
import warnings
from typing import cast

import requests

from dcr_sdk.core.account import Account
from dcr_sdk.models import Event, State
from dcr_sdk.utils.color import Color
from dcr_sdk.utils.constants import (
    INITIALIZE_SIMULATION_URL,
    SIMULATION_EVENT_URL,
    SIMULATION_EVENTS_URL,
    SIMULATION_URL,
)
from dcr_sdk.utils.dcr_parser import DCR_Parser
from dcr_sdk.utils.event_view import EventView


class Simulation:
    graph_id: int
    account: Account
    sim_id: int
    url: str
    parser: DCR_Parser
    state: State

    def __init__(
        self,
        graph_id: int,
        account: Account,
        sim_id: int | None = None,
        title: str = "Python Simulation",
    ):
        self.graph_id = graph_id
        self.account = account
        self.parser = DCR_Parser()

        if sim_id is None:
            response = self._init_simulation(title)
            sim_id = int(response.headers["X-Dcr-Simulation-Id"])
        else:
            self._verify_sim_id(sim_id)

        self.sim_id = sim_id
        self.url = SIMULATION_URL.format(graph_id, sim_id)

        self.state = self._refresh_event_state()

    # ===== Simulation Managment Routes =======================

    def _init_simulation(self, title: str) -> requests.Response:
        url = INITIALIZE_SIMULATION_URL.format(self.graph_id)
        payload = json.dumps({"Title": title})
        response = self.account.session.post(url, data=payload)
        response.raise_for_status()
        return response

    # Note: There is no formal GET request to check this
    # Solution: Get events and raise_for_status in case it doens't find it
    def _verify_sim_id(self, sim_id: int) -> None:
        url = SIMULATION_EVENTS_URL.format(self.graph_id, sim_id)
        response = self.account.session.get(url, params={"filter": "all"})
        response.raise_for_status()

    def kill_simulation(self) -> None:
        response = self.account.session.delete(self.url)
        response.raise_for_status()

    # DCR calls this "accepting": no included pending events are left
    # The body can come back as true, "true" or "True", so we normalize it
    def is_concluded(self) -> bool:
        response = self.account.session.get(
            self.url, params={"filter": "isAccepting"}
        )
        response.raise_for_status()
        return response.text.strip().strip('"').lower() == "true"

    # ===== Event Managment Routes =======================

    def _refresh_event_state(self, event_filter: str = "all") -> State:
        url = SIMULATION_EVENTS_URL.format(self.graph_id, self.sim_id)
        response = self.account.session.get(
            url, params={"filter": event_filter}
        )
        response.raise_for_status()
        # DCR wraps the events XML in a JSON string
        return self.parser.parse_state(cast(str, response.json()))

    # This is a simple quality of life function
    def execute_event(self, event_id: str, role: str | None = None) -> None:
        event = self.state.events.get(event_id)
        if event is None:
            raise ValueError(f"Event {event_id!r} does not exist")
        if not event.enabled:
            raise ValueError(f"Event {event_id!r} is not enabled")

        url = SIMULATION_EVENT_URL.format(self.graph_id, self.sim_id, event_id)
        payload = json.dumps({"Role": role} if role else {})
        response = self.account.session.post(url, data=payload)
        response.raise_for_status()
        new_state = self._refresh_event_state()
        if new_state == self.state:
            warnings.warn("State of simulation did not change on event trigger")
        else:
            self.state = self._refresh_event_state()

    # ===== Visualization =======================

    def print_events(self, zen: bool = False) -> None:
        print(Color.header("EVENT TREE"))
        for event in self._children(""):
            self._print_event(event, zen)

    def _children(self, parent_id: str) -> list[Event]:
        events = self.state.events.values()
        return [e for e in events if e.parent == parent_id]

    # If it has children, the program will default to subgraph
    def _is_container(self, event: Event) -> bool:
        return bool(event.type) or bool(self._children(event.id))

    # Zen mode is to only focus what is to be executed
    def _print_event(self, event: Event, zen: bool, depth: int = 0) -> None:
        pad = "    " * depth
        view = EventView(event, self._is_container(event))
        print(pad + (f"{view.label}" if zen else view.details(pad)))
        for child in self._children(event.id):
            self._print_event(child, zen, depth + 1)
