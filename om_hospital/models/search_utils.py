"""Helpers shared by models that expose a computed boolean through a search method."""

TRUE_DOMAIN = [(1, "=", 1)]
FALSE_DOMAIN = [(0, "=", 1)]


def boolean_search_domain(operator, value, positive_domain, negative_domain):
    """Return the domain for a search on a computed boolean flag.

    Odoo may hand a search method ``('flag', '=', True)`` as well as the normalised
    ``('flag', 'in', [True])`` or ``('flag', 'not in', [False])``, so every spelling is
    reduced to "which values of the flag are wanted" before choosing the domain.
    """
    if operator not in ("=", "!=", "in", "not in"):
        raise NotImplementedError(
            f"Unsupported operator {operator!r} for a boolean search.",
        )
    values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
    asked = {bool(item) for item in values}
    wanted = asked if operator in ("=", "in") else {True, False} - asked
    if wanted == {True, False}:
        return TRUE_DOMAIN
    if not wanted:
        return FALSE_DOMAIN
    return positive_domain if True in wanted else negative_domain
