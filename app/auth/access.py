"""Who may see which ticket (POPIA least privilege). Pure rules, used by the API and tests.

- The principal sees every ticket.
- Learner-welfare / safety tickets: only the deputy principal and the principal.
- Everyone else: tickets routed to their role, or assigned to them personally.
"""

from __future__ import annotations

from sqlalchemy import and_, or_, true

from app.models import Staff, Ticket
from app.taxonomy import PRINCIPAL_ROLE, SENIOR_ROLES, WELFARE_CATEGORY


def is_welfare(ticket: Ticket) -> bool:
    return ticket.category == WELFARE_CATEGORY or bool(ticket.safety_flag)


def can_see_ticket(staff: Staff, ticket: Ticket) -> bool:
    if staff.role == PRINCIPAL_ROLE:
        return True
    if is_welfare(ticket):
        return staff.role in SENIOR_ROLES       # the deputy principal sees every welfare ticket
    return ticket.routed_role == staff.role or ticket.assigned_to == staff.id


def visible_tickets_filter(staff: Staff):
    """The same rule as can_see_ticket, as a SQL condition for list queries (None = no filter)."""
    if staff.role == PRINCIPAL_ROLE:
        return None
    welfare = or_(Ticket.category == WELFARE_CATEGORY, Ticket.safety_flag == true())
    mine = or_(Ticket.routed_role == staff.role, Ticket.assigned_to == staff.id)
    if staff.role in SENIOR_ROLES:
        return or_(welfare, mine)
    return and_(mine, ~welfare)
