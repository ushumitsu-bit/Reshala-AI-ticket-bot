from unittest.mock import MagicMock

import pytest

from services.ticket_service import TicketService


def make_ticket(status="open", topic_id=5, client_id=123456789):
    return {
        "_id": "507f1f77bcf86cd799439011",
        "topic_id": topic_id,
        "client_id": client_id,
        "client_username": "user1",
        "status": status,
        "history": [],
    }


class FakeCollection:
    def __init__(self, doc=None):
        self.doc = doc
        self.archived = []
        self.deleted = []
        self.updated = []

    def find_one(self, query):
        return self.doc

    def update_one(self, query, update):
        self.updated.append((query, update))
        return MagicMock(modified_count=1)

    def insert_one(self, doc):
        self.archived.append(doc)
        return MagicMock(inserted_id="x")

    def delete_one(self, query):
        self.deleted.append(query)
        return MagicMock(deleted_count=1)


class FakeDb:
    def __init__(self, ticket):
        self.tickets = FakeCollection(doc=ticket)
        self.ticket_archive = FakeCollection()


class FakeTelegram:
    def __init__(self):
        self.calls = []

    async def edit_forum_topic(self, *args, **kwargs):
        self.calls.append("edit")

    async def close_forum_topic(self, *args, **kwargs):
        self.calls.append("close")

    async def send_message(self, *args, **kwargs):
        self.calls.append("send")


async def test_close_manager_archives_and_deletes():
    db = FakeDb(make_ticket(status="escalated"))
    svc = TicketService(db, FakeTelegram(), support_group_id=-100123)
    res = await svc.close_ticket("507f1f77bcf86cd799439011", actor="manager", actor_id=1)

    assert res["ok"] is True
    assert len(db.ticket_archive.archived) == 1
    archive_doc = db.ticket_archive.archived[0]
    assert archive_doc["distilled"] is False
    assert archive_doc["closed_by"]["actor"] == "manager"
    assert archive_doc["closed_by"]["actor_id"] == 1
    assert archive_doc["closed_at"] is not None
    assert len(db.tickets.deleted) == 1


async def test_close_client_archives_and_deletes():
    db = FakeDb(make_ticket(status="escalated"))
    svc = TicketService(db, FakeTelegram(), support_group_id=-100123)
    res = await svc.close_ticket("507f1f77bcf86cd799439011", actor="client", actor_id=2)

    assert res["ok"] is True
    assert len(db.ticket_archive.archived) == 1
    assert db.ticket_archive.archived[0]["closed_by"]["actor"] == "client"
    assert len(db.tickets.deleted) == 1


async def test_close_client_suspicious_keeps_ticket():
    db = FakeDb(make_ticket(status="suspicious"))
    svc = TicketService(db, FakeTelegram(), support_group_id=-100123)
    res = await svc.close_ticket("507f1f77bcf86cd799439011", actor="client", actor_id=2)

    assert res["ok"] is True
    assert len(db.ticket_archive.archived) == 0
    assert len(db.tickets.deleted) == 0
    assert len(db.tickets.updated) == 1


def test_ticket_query_resolution():
    svc = TicketService(FakeDb(make_ticket()), None, None)
    from bson import ObjectId

    assert svc._ticket_query("507f1f77bcf86cd799439011") == {"_id": ObjectId("507f1f77bcf86cd799439011")}
    assert svc._ticket_query("123456789") == {
        "$or": [
            {"topic_id": 123456789},
            {"client_id": 123456789, "is_removed": {"$ne": True}, "status": {"$ne": "closed"}},
        ]
    }
    assert svc._ticket_query("5") == {
        "$or": [
            {"topic_id": 5},
            {"client_id": 5, "is_removed": {"$ne": True}, "status": {"$ne": "closed"}},
        ]
    }
