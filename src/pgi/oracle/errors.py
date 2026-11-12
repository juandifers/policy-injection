"""Exceptions shared by the oracle backends."""


class OracleError(Exception):
    """Any validation or authorization error. Never interpreted as a deny."""
