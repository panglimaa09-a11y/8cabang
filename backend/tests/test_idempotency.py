"""Idempotency tests — duplicate POST with one key = one transaction.

Exercises app.common's store/lookup directly against SQLite, plus the
header-vs-body key resolution rule (header wins).
"""
from datetime import datetime, timezone

from app.common import (
    get_idempotency_key, lookup_idempotency, store_idempotency,
)

from .conftest import uid


class _Req:
    def __init__(self, headers=None):
        self.headers = headers or {}


def test_header_key_wins_over_body():
    req = _Req({"Idempotency-Key": "hdr-1"})
    assert get_idempotency_key(req, {"idempotency_key": "body-1"}) == "hdr-1"


def test_body_key_used_when_no_header():
    req = _Req({})
    assert get_idempotency_key(req, {"idempotency_key": "body-1"}) == "body-1"
    assert get_idempotency_key(req, None) is None


def test_duplicate_key_returns_stored_response(db, seed):
    """First call stores; second lookup returns the SAME response, no re-post."""
    user = seed["users"]["karyawan"]
    response = {"id": str(uid()), "txn_no": "PJ-20240101-0001",
                "status": "posted", "total": "150000.00"}
    store_idempotency(db, key="idem-abc", profile_id=user.id,
                      endpoint="POST /api/sales",
                      response=response, status_code=201)
    db.commit()

    rec = lookup_idempotency(db, "idem-abc", "POST /api/sales")
    assert rec is not None
    assert rec.response == response
    assert rec.status_code == 201
    assert rec.profile_id == user.id


def test_unknown_key_returns_none(db):
    assert lookup_idempotency(db, "nope", "POST /api/sales") is None


def test_expired_record_is_purged(db, seed):
    user = seed["users"]["karyawan"]
    store_idempotency(db, key="idem-old", profile_id=user.id,
                      endpoint="POST /api/sales",
                      response={"ok": True}, status_code=200)
    rec = lookup_idempotency(db, "idem-old", "POST /api/sales")
    assert rec is not None
    # Force expiry, then lookup must purge and return None.
    rec.expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    db.commit()
    assert lookup_idempotency(db, "idem-old", "POST /api/sales") is None
