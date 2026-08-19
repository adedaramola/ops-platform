from __future__ import annotations

from opsdesk.tickets.repository import TicketRepository


def test_append_only_activity_has_no_repository_mutation_api() -> None:
    prohibited = {
        "update_activity",
        "delete_activity",
        "save_activity",
        "update_internal_note",
        "delete_internal_note",
    }
    assert prohibited.isdisjoint(dir(TicketRepository))
