from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from app.domain.idempotency import IdempotencyRecord, IdempotencyStatus


def _start() -> IdempotencyRecord:
    return IdempotencyRecord.start(
        key="idem-key-1",
        request_fingerprint="abc123",
        ttl=timedelta(hours=24),
    )


class TestIdempotencyRecordStart:
    def test_initial_state_is_in_progress(self) -> None:
        r = _start()
        assert r.status is IdempotencyStatus.IN_PROGRESS
        assert r.response_status is None
        assert r.response_body is None
        assert r.payment_id is None

    def test_expires_at_uses_ttl(self) -> None:
        r = _start()
        delta = r.expires_at - r.created_at
        assert delta == timedelta(hours=24)


class TestFingerprintMatching:
    def test_match_returns_true_for_same_fingerprint(self) -> None:
        r = _start()
        assert r.matches_fingerprint("abc123") is True

    def test_match_returns_false_for_different_fingerprint(self) -> None:
        r = _start()
        assert r.matches_fingerprint("xyz999") is False


class TestExpiry:
    def test_not_expired_immediately(self) -> None:
        assert _start().is_expired() is False

    def test_expired_after_ttl(self) -> None:
        r = _start()
        future = r.expires_at + timedelta(seconds=1)
        assert r.is_expired(now=future) is True


class TestStuckDetection:
    def test_fresh_in_progress_is_not_stuck(self) -> None:
        r = _start()
        assert r.is_stuck(timeout=timedelta(seconds=30)) is False

    def test_old_in_progress_is_stuck(self) -> None:
        r = _start()
        future = r.locked_at + timedelta(seconds=60)
        assert r.is_stuck(timeout=timedelta(seconds=30), now=future) is True

    def test_completed_is_never_stuck(self) -> None:
        r = _start()
        r.complete(response_status=201, response_body={"ok": True}, payment_id=uuid4())
        future = r.locked_at + timedelta(hours=24)
        assert r.is_stuck(timeout=timedelta(seconds=30), now=future) is False


class TestCompletion:
    def test_complete_sets_cached_response(self) -> None:
        r = _start()
        pid = uuid4()
        r.complete(response_status=201, response_body={"id": str(pid)}, payment_id=pid)
        assert r.status is IdempotencyStatus.COMPLETED
        assert r.response_status == 201
        assert r.response_body == {"id": str(pid)}
        assert r.payment_id == pid
