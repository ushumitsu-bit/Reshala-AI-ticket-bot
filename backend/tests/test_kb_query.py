from unittest.mock import MagicMock, patch

import routers.ai_router as ai_router


class _Cursor:
    def limit(self, n):
        return []


class FakeCollection:
    def __init__(self):
        self.queries = []

    def find(self, query, *args, **kwargs):
        self.queries.append(query)
        return _Cursor()


def test_kb_query_escapes_malicious_regex():
    col = FakeCollection()
    db = MagicMock()
    db.knowledge_base = col

    with patch("routers.ai_router.get_db", return_value=db):
        ai_router._get_knowledge_context("(a+)+$ vpn")

    regex = col.queries[0]["$or"][0]["title"]["$regex"]
    assert "(a+)+$" not in regex
    assert regex == r"\(a\+\)\+\$|vpn"


def test_kb_query_empty_on_no_db():
    with patch("routers.ai_router.get_db", return_value=None):
        assert ai_router._get_knowledge_context("vpn") == ""
