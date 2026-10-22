"""The comparison card on screen carries the importer link of each catalog car (app/api/common.py);
the model's payload (calculate's result) does not."""
import json

from langchain_core.messages import ToolMessage

from app.api.common import cards_of


def card(alt_label, alt_kind="car", today_label="TUCSON (2024)", today_kind="car"):
    return {"status": "ok", "card": {"today": {"kind": today_kind, "label": today_label},
                                     "alternative": {"kind": alt_kind, "label": alt_label}}}


def shown(result):
    msg = ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id="1", name="calculate")
    return cards_of([msg])[0]["card"]


def test_a_catalog_car_gets_its_importer_link_the_model_payload_does_not():
    result = card("BYD DOLPHIN (2025)")
    c = shown(result)
    assert c["alternative"]["importer_url"].startswith("https://bydauto.co.il")
    assert "importer_url" not in json.dumps(result)


def test_no_link_for_a_car_outside_the_catalog_or_a_waiver():
    c = shown(card("ATTO 2 (2025)", today_label="ויתור על הרכב", today_kind="waiver"))
    assert "importer_url" not in c["alternative"] and "importer_url" not in c["today"]
