from __future__ import annotations

from contextlib import nullcontext


def storage_transaction(state_store: object, event_store: object):
    """Return a transaction context when state and events share one backend."""
    if state_store is event_store:
        transaction = getattr(state_store, "transaction", None)
        if callable(transaction):
            return transaction()
    return nullcontext()
