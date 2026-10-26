from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from automation_worker.connection import ConnectionJob, ConnectionProcessor, StoredConnection


CLIENT_ID = UUID("477751f2-1142-4283-a3c0-387f8aa45fbd")
EVENT_ID = UUID("477751f2-1142-4283-a3c0-387f8aa45fbe")
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


class FakeQbo:
    def __init__(self, connected=False, current_time=NOW, outcome="updated"):
        self.connected = connected
        self.current_time = current_time
        self.outcome = outcome
        self.updates = 0

    def update(self, job):
        self.updates += 1
        if self.outcome == "updated":
            self.connected = job.is_connected
            self.current_time = job.checked_at
        return self.outcome

    def current(self, _job):
        return StoredConnection(self.connected, self.current_time, "ACME Sandbox")


class FakeLedger:
    def __init__(self, last=None, fail=False):
        self.last = last
        self.fail = fail
        self.sent = []
        self.queries = []

    def last_sent_at(self, **kwargs):
        self.queries.append(kwargs)
        if self.fail:
            raise RuntimeError("ledger unavailable")
        if kwargs["scope"] is not None:
            return self.last if self.sent else None
        return self.last

    def send(self, request):
        self.sent.append(request)
        self.last = NOW + timedelta(seconds=1)


class FakeCheckpoints:
    def __init__(self):
        self.fields = {}
        self.episodes = {}

    def get(self, event_id, field):
        return self.fields.get((event_id, field))

    def set(self, event_id, field, value):
        self.fields[(event_id, field)] = value

    def get_episode(self, client_id, environment):
        return self.episodes.get((client_id, environment))

    def set_episode(self, client_id, environment, episode):
        self.episodes[(client_id, environment)] = episode

    def clear_episode(self, client_id, environment):
        self.episodes.pop((client_id, environment), None)


def make_job(*, connected=False, previous=False, checked_at=NOW):
    return ConnectionJob(
        client_id=CLIENT_ID,
        provider="qbo",
        environment="sandbox",
        is_connected=connected,
        checked_at=checked_at,
        correlation_id=EVENT_ID,
        notification={"candidate": True, "observed_previous_connected": previous},
    )


def make_processor(qbo=None, ledger=None, checkpoints=None):
    qbo = qbo or FakeQbo()
    ledger = ledger or FakeLedger()
    checkpoints = checkpoints or FakeCheckpoints()
    processor = ConnectionProcessor(
        qbo=qbo,
        notifications=ledger,
        checkpoints=checkpoints,
        recipient="D0B3LSR4C1Y",
        now=lambda: NOW,
    )
    return processor, qbo, ledger, checkpoints


def test_disconnected_sends_router_contract_once():
    processor, qbo, ledger, checkpoints = make_processor()
    assert processor.process(EVENT_ID, make_job(previous=True)) == "notified"
    assert processor.process(EVENT_ID, make_job(previous=True)) == "duplicate"
    assert qbo.updates == 1
    assert len(ledger.sent) == 1
    request = ledger.sent[0]
    assert request["contract_type"] == "notification_router.request"
    assert request["contract_version"] == "1.0"
    assert request["entity"]["client_id"] == str(CLIENT_ID)
    assert request["context"]["recipient"] == "D0B3LSR4C1Y"
    assert request["context"]["communication"]["destination_type"] == "channel"
    assert request["context"]["communication"]["recipient"] == "D0B3LSR4C1Y"
    assert checkpoints.get_episode(CLIENT_ID, "sandbox") == str(EVENT_ID)


def test_previous_delivery_within_48_hours_suppresses():
    ledger = FakeLedger(last=NOW - timedelta(hours=47))
    processor, _, _, _ = make_processor(ledger=ledger)
    assert processor.process(EVENT_ID, make_job()) == "suppressed"
    assert ledger.sent == []


def test_new_observed_episode_not_suppressed_by_prior_delivery():
    ledger = FakeLedger(last=NOW - timedelta(minutes=10))
    processor, _, _, _ = make_processor(ledger=ledger)
    assert processor.process(EVENT_ID, make_job(previous=True)) == "notified"
    assert len(ledger.sent) == 1


def test_connected_clears_episode_and_never_notifies():
    checkpoints = FakeCheckpoints()
    checkpoints.set_episode(CLIENT_ID, "sandbox", "prior")
    processor, _, ledger, _ = make_processor(checkpoints=checkpoints)
    assert processor.process(EVENT_ID, make_job(connected=True)) == "connected"
    assert checkpoints.get_episode(CLIENT_ID, "sandbox") is None
    assert ledger.sent == []


def test_ledger_failure_remains_retryable_after_status_persisted():
    ledger = FakeLedger(fail=True)
    processor, qbo, _, checkpoints = make_processor(ledger=ledger)
    with pytest.raises(RuntimeError, match="ledger unavailable"):
        processor.process(EVENT_ID, make_job())
    assert checkpoints.get(EVENT_ID, "persisted") == "updated"
    ledger.fail = False
    assert processor.process(EVENT_ID, make_job()) == "notified"
    assert qbo.updates == 1


def test_stale_job_cannot_notify_after_newer_connected_state():
    qbo = FakeQbo(connected=True, current_time=NOW + timedelta(minutes=1), outcome="stale")
    processor, _, ledger, _ = make_processor(qbo=qbo)
    assert processor.process(EVENT_ID, make_job()) == "superseded"
    assert ledger.sent == []


def test_qbo_conflict_does_not_notify():
    qbo = FakeQbo(outcome="conflict")
    processor, _, ledger, _ = make_processor(qbo=qbo)
    with pytest.raises(ValueError, match="conflicting"):
        processor.process(EVENT_ID, make_job())
    assert ledger.sent == []


def test_notification_destination_must_be_a_slack_dm_conversation():
    with pytest.raises(ValueError, match="DM conversation ID"):
        ConnectionProcessor(
            qbo=FakeQbo(),
            notifications=FakeLedger(),
            checkpoints=FakeCheckpoints(),
            recipient="@jorge.vera",
        )
