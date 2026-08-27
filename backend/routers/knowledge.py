from fastapi import APIRouter, Body, Depends, Request
from bson import ObjectId
from datetime import datetime, timezone

from middleware.auth import require_manager
from middleware.rate_limit import limiter
from utils.db_config import get_db

router = APIRouter(dependencies=[Depends(require_manager)])


@router.get("")
def get_articles():
    db = get_db()
    if db is None:
        return {"articles": []}
    articles = list(db.knowledge_base.find({}).sort("updated_at", -1))
    for a in articles:
        a["id"] = str(a.pop("_id"))
    return {"articles": articles}


@router.get("/{article_id}")
def get_article(article_id: str):
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}
    try:
        doc = db.knowledge_base.find_one({"_id": ObjectId(article_id)})
    except Exception:
        return {"ok": False, "error": "invalid_id"}
    if not doc:
        return {"ok": False, "error": "not_found"}
    doc["id"] = str(doc.pop("_id"))
    return {"ok": True, "article": doc}


@router.post("")
@limiter.limit("30/minute")
def create_article(request: Request, data: dict = Body(...)):
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    category = (data.get("category") or "general").strip()
    if not title or not content:
        return {"ok": False, "error": "title and content required"}
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "title": title,
        "content": content,
        "category": category,
        "source": "manual",
        "question_patterns": [],
        "usage_count": 0,
        "tags": [],
        "created_at": now,
        "updated_at": now,
    }
    result = db.knowledge_base.insert_one(doc)
    return {"ok": True, "id": str(result.inserted_id)}


@router.put("/{article_id}")
@limiter.limit("30/minute")
def update_article(request: Request, article_id: str, data: dict = Body(...)):
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}
    try:
        oid = ObjectId(article_id)
    except Exception:
        return {"ok": False, "error": "invalid_id"}
    update = {}
    for k in ["title", "content", "category"]:
        if k in data:
            update[k] = data[k]
    if not update:
        return {"ok": False, "error": "nothing to update"}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    db.knowledge_base.update_one({"_id": oid}, {"$set": update})
    return {"ok": True}


@router.delete("/{article_id}")
@limiter.limit("30/minute")
def delete_article(request: Request, article_id: str):
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}
    try:
        oid = ObjectId(article_id)
    except Exception:
        return {"ok": False, "error": "invalid_id"}
    result = db.knowledge_base.delete_one({"_id": oid})
    return {"ok": result.deleted_count > 0}


@router.get("/search/{query}")
def search_articles(query: str):
    db = get_db()
    if db is None:
        return {"articles": []}
    regex = {"$regex": query, "$options": "i"}
    articles = list(db.knowledge_base.find(
        {"$or": [{"title": regex}, {"content": regex}, {"category": regex}]}
    ).sort("updated_at", -1).limit(20))
    for a in articles:
        a["id"] = str(a.pop("_id"))
    return {"articles": articles}
