from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Body, Depends

from middleware.auth import require_manager
from utils.db_config import get_db

router = APIRouter(dependencies=[Depends(require_manager)])


def _serialize(doc):
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    for field in ("created_at", "reviewed_at"):
        if isinstance(doc.get(field), datetime):
            doc[field] = doc[field].isoformat()
    return doc


@router.get("")
def list_suggestions(status: str = "pending"):
    db = get_db()
    if db is None:
        return {"suggestions": []}
    query = {"status": status} if status else {}
    items = list(db.kb_suggestions.find(query).sort("created_at", -1).limit(100))
    return {"suggestions": [_serialize(s) for s in items]}


@router.get("/{suggestion_id}")
def get_suggestion(suggestion_id: str):
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}
    try:
        oid = ObjectId(suggestion_id)
    except Exception:
        return {"ok": False, "error": "invalid_id"}
    doc = db.kb_suggestions.find_one({"_id": oid})
    if not doc:
        return {"ok": False, "error": "not_found"}
    return {"ok": True, "suggestion": _serialize(doc)}


@router.post("/{suggestion_id}/approve")
def approve_suggestion(suggestion_id: str, data: dict = Body(...)):
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}
    try:
        oid = ObjectId(suggestion_id)
    except Exception:
        return {"ok": False, "error": "invalid_id"}
    sug = db.kb_suggestions.find_one({"_id": oid})
    if not sug:
        return {"ok": False, "error": "not_found"}

    proposed = sug.get("proposed", {}) or {}
    final = dict(proposed)
    editable = ("title", "category", "tags", "question_patterns", "content")
    for key in editable:
        if key in data:
            final[key] = data[key]
    edited = any(final.get(k) != proposed.get(k) for k in editable)

    title = (final.get("title") or "").strip()
    content = (final.get("content") or "").strip()
    if not title or not content:
        return {"ok": False, "error": "title and content required"}

    now = datetime.now(timezone.utc)
    action = sug.get("action", "add")
    target_id = sug.get("target_article_id")

    updated = False
    if action == "update" and target_id:
        try:
            db.knowledge_base.update_one(
                {"_id": ObjectId(target_id)},
                {"$set": {
                    "title": title,
                    "content": content,
                    "category": final.get("category", "general"),
                    "tags": final.get("tags", []),
                    "question_patterns": final.get("question_patterns", []),
                    "source": "auto",
                    "origin_ticket_id": sug.get("source_ticket_id"),
                    "updated_at": now.isoformat(),
                }}
            )
            updated = True
        except Exception:
            updated = False

    if not updated:
        db.knowledge_base.insert_one({
            "title": title,
            "content": content,
            "category": final.get("category", "general"),
            "tags": final.get("tags", []),
            "question_patterns": final.get("question_patterns", []),
            "source": "auto",
            "origin_ticket_id": sug.get("source_ticket_id"),
            "usage_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        })

    new_status = "edited" if edited else "approved"
    db.kb_suggestions.update_one(
        {"_id": oid},
        {"$set": {"status": new_status, "reviewed_at": now}}
    )
    return {"ok": True, "status": new_status}


@router.post("/{suggestion_id}/reject")
def reject_suggestion(suggestion_id: str, data: dict = Body(...)):
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}
    try:
        oid = ObjectId(suggestion_id)
    except Exception:
        return {"ok": False, "error": "invalid_id"}
    db.kb_suggestions.update_one(
        {"_id": oid},
        {"$set": {"status": "rejected", "reason": data.get("reason", ""), "reviewed_at": datetime.now(timezone.utc)}}
    )
    return {"ok": True, "status": "rejected"}
