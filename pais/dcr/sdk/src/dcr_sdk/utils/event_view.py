from __future__ import annotations

from dataclasses import dataclass

from dcr_sdk.models import Event
from dcr_sdk.utils.color import Color


# This class is for simple printing a simulation state
@dataclass(frozen=True)
class EventView:
    event: Event

    @property
    def kind(self) -> str:
        if self.event.is_container:
            return Color.magenta("CONTAINER")
        return Color.cyan("ACTIVITY")

    # Containers are bold magenta.
    # Activities are blue when pending, grey otherwise.
    @property
    def label(self) -> str:
        if self.event.is_container:
            return f"{Color.paint(self.event.label, Color.BOLD, Color.MAGENTA)} (ID:{self.event.id})"
        if self.event.pending:
            return f"{Color.paint(self.event.label, Color.BOLD, Color.BLUE)} (ID:{self.event.id})"
        return Color.grey(f"{self.event.label} (ID:{self.event.id})")

    @property
    def state(self) -> str:
        e = self.event
        flags = {
            "Enabled": e.enabled,
            "Pending": e.pending,
            "Effectively pending": e.effectively_pending,
            "Executed": e.executed,
            "Included": e.included,
        }
        return "  ".join(f"{k}: {Color.flag(v)}" for k, v in flags.items())

    @property
    def meta(self) -> str:
        e = self.event
        return Color.grey(
            f"id={e.id!r} type={e.type!r} fullPath={e.full_path!r}"
        )

    def details(self, pad: str = "") -> str:
        lines = [f"{self.kind} {self.label}", self.state, self.meta]
        return f"\n{pad}  ".join(lines)
