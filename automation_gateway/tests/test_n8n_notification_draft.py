import json
from pathlib import Path


CONFIG = Path(__file__).resolve().parents[2] / "automation_worker" / "n8n_qbo_disconnect_draft.json"


def test_n8n_draft_matches_worker_contract_and_only_targets_slack_dm():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    rule = config["rule"]
    template = config["template"]
    actions = json.loads(rule["actions_json"])

    assert rule["contract_type"] == "notification_router.request"
    assert rule["event_type"] == "qbo_connection_disconnected"
    assert rule["source_workflow"] == "QBO Connection Monitor"
    assert rule["source_node"] == "Automation Worker"
    assert len(actions) == 1
    assert actions[0]["channel"] == "slack"
    assert actions[0]["destination_type"] == "channel"
    assert actions[0]["recipient"] == "D0B3LSR4C1Y"
    assert actions[0]["dedupe"]["base_path"] == "execution.request_id"
    assert actions[0]["template_scope"] == template["scope"]
    assert actions[0]["template_key"] == template["template_key"]
    assert actions[0]["template_case"] == template["template_case"]
    assert template["channel"] == "slack"
    assert "{{context.checked_at}}" in template["template_text"]
