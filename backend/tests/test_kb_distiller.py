from services.kb_distiller import scrub_pii, _is_worth_learning, parse_methodist_json


def test_scrub_pii_masks_identifiers():
    text = (
        "user 12345678-1234-1234-1234-123456789012, mail a@b.co, "
        "sub vless://abc, id 1234567890, phone +7 900 123-45-67"
    )
    out = scrub_pii(text)
    assert "12345678-1234-1234-1234-123456789012" not in out
    assert "a@b.co" not in out
    assert "vless://abc" not in out
    assert "1234567890" not in out
    assert "+7 900 123-45-67" not in out


def test_scrub_pii_keeps_plain_words():
    out = scrub_pii("Не работает VPN после обновления")
    assert out == "Не работает VPN после обновления"


def test_is_worth_learning_ok():
    doc = {
        "status": "escalated",
        "history": [
            {"role": "client", "content": "проблема"},
            {"role": "ai", "content": "не знаю"},
            {"role": "manager", "content": "сделайте так"},
            {"role": "client", "content": "спасибо"},
        ],
    }
    ok, reason = _is_worth_learning(doc)
    assert ok is True
    assert reason == "ok"


def test_is_worth_learning_answered_status():
    doc = {
        "status": "answered",
        "history": [
            {"role": "client", "content": "проблема"},
            {"role": "ai", "content": "не знаю"},
            {"role": "manager", "content": "сделайте так"},
            {"role": "client", "content": "спасибо"},
        ],
    }
    ok, reason = _is_worth_learning(doc)
    assert ok is True
    assert reason == "ok"


def test_is_worth_learning_not_escalated():
    ok, reason = _is_worth_learning({"status": "open", "history": []})
    assert ok is False
    assert reason == "not_escalated"


def test_is_worth_learning_no_manager():
    doc = {
        "status": "escalated",
        "history": [
            {"role": "client", "content": "a"},
            {"role": "ai", "content": "b"},
            {"role": "client", "content": "c"},
            {"role": "ai", "content": "d"},
        ],
    }
    ok, reason = _is_worth_learning(doc)
    assert ok is False
    assert reason == "no_manager_reply"


def test_parse_methodist_json_with_fence():
    raw = '```json\n{"should_add": true, "action": "add", "title": "T", "content": "C"}\n```'
    parsed = parse_methodist_json(raw)
    assert parsed["should_add"] is True


def test_parse_methodist_json_plain():
    parsed = parse_methodist_json('{"should_add": false}')
    assert parsed["should_add"] is False
