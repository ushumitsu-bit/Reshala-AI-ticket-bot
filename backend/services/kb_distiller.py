"""
KB Distiller — фоновый воркер самообучения (Фаза 4 MVP).

Берёт закрытые эскалированные тикеты из ticket_archive, скраббит PII,
ищет похожие статьи, просит LLM-«методиста» сформировать черновик статьи
и кладёт его в kb_suggestions (status=pending). Без автопубликации.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone

from services.ai.manager import AIProviderManager
from utils.db_config import get_db
from utils.support_common import esc

logger = logging.getLogger(__name__)

KB_DISTILL_BATCH = int(os.environ.get("KB_DISTILL_BATCH", "5"))

METHODIST_SYSTEM = (
    "Ты — методист базы знаний службы поддержки VPN-сервиса. "
    "На основе очищенного транскрипта диалога сформируй черновик статьи. "
    "Отвечай СТРОГО одним JSON-объектом без markdown-обёртки."
)

# --- PII scrubbing ---
_SUB_LINK_RE = re.compile(r'(?:vless|vmess|trojan|ss)://[^\s]+', re.IGNORECASE)
_SUB_PATH_RE = re.compile(r'https?://[^\s]*/sub/[^\s]*', re.IGNORECASE)
_UUID_RE = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.IGNORECASE)
_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
_PHONE_RE = re.compile(r'(?<!\d)(?:\+?\d[\d\s\-()]{6,}\d)(?!\d)')


def scrub_pii(text: str) -> str:
    """Удалить/замаскировать персональные данные из текста."""
    if not text:
        return ""
    text = _SUB_LINK_RE.sub("[subscription_link]", text)
    text = _SUB_PATH_RE.sub("[subscription_link]", text)
    text = _UUID_RE.sub("[uuid]", text)
    text = _EMAIL_RE.sub("[email]", text)
    text = _PHONE_RE.sub("[phone]", text)
    return text


def _extract_keywords(text: str, limit: int = 6):
    seen = []
    for w in re.findall(r'\w+', text.lower()):
        if len(w) > 3 and w not in seen:
            seen.append(w)
        if len(seen) >= limit:
            break
    return seen


def _find_similar_articles(db, text: str):
    keywords = [re.escape(w) for w in _extract_keywords(text)]
    if not keywords:
        return []
    regex = {"$regex": "|".join(keywords), "$options": "i"}
    try:
        articles = list(db.knowledge_base.find(
            {"$or": [{"title": regex}, {"content": regex}, {"category": regex}]}
        ).limit(3))
    except Exception as e:
        logger.warning(f"similar articles search failed: {e}")
        return []
    return [
        {"article_id": str(a.get("_id")), "title": a.get("title", ""), "category": a.get("category", "general")}
        for a in articles
    ]


def _is_worth_learning(doc):
    """Фильтр «стоит ли учиться». Возвращает (bool, reason)."""
    if doc.get("status") not in ("escalated", "answered"):
        return False, "not_escalated"
    history = doc.get("history", []) or []
    manager_replies = [h for h in history if h.get("role") == "manager" and (h.get("content") or "").strip()]
    if not manager_replies:
        return False, "no_manager_reply"
    substantive = [h for h in history if (h.get("content") or "").strip() and h.get("role") in ("client", "ai", "manager")]
    if len(substantive) < 4:
        return False, "too_few_messages"
    return True, "ok"


def _build_transcript(doc):
    lines = []
    for h in doc.get("history", []) or []:
        role = h.get("role", "client")
        content = (h.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _scrub_transcript(history):
    """Скраббить PII в каждой реплике транскрипта (для хранения в kb_suggestions)."""
    out = []
    for h in history or []:
        e = dict(h)
        if "content" in e:
            e["content"] = scrub_pii(e["content"])
        out.append(e)
    return out


def parse_methodist_json(raw):
    """Парсинг JSON от LLM (с возможной markdown-обёрткой)."""
    if not raw:
        return None
    text = raw.strip()
    fence = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _build_prompt(transcript, similar):
    similar_text = "\n".join(f"- [{a['article_id']}] {a['title']} ({a['category']})" for a in similar) or "нет"
    return f"""Проанализируй диалог поддержки и составь черновик статьи базы знаний.

ПРАВИЛА:
- Не включай персональные данные конкретного пользователя.
- Если ответ менеджера выглядит неверным/небезопасным — should_add=false.
- Если тема уже покрыта похожей статьёй — action="update" и target_article_id, либо should_add=false.
- Пиши инструкцию кратко и по делу.

ОЧИЩЕННЫЙ ТРАНСКРИПТ:
{transcript}

ПОХОЖИЕ СТАТЬИ:
{similar_text}

Верни СТРОГО JSON:
{{"should_add": bool, "action": "add"|"update", "target_article_id": null|"id", "title": str, "category": str, "tags": [str], "question_patterns": [str], "content": str, "summary": str, "reasoning": str}}"""


def mark_distilled(db, doc, result, detail=""):
    update = {"distilled": True, "distill_result": result, "distilled_at": datetime.now(timezone.utc)}
    if detail:
        update["distill_detail"] = detail[:1000]
    try:
        db.ticket_archive.update_one({"_id": doc["_id"]}, {"$set": update})
    except Exception as e:
        logger.warning(f"mark distilled failed: {e}")


def _notify_managers(suggestion):
    flag = os.environ.get("KB_SUGGESTION_NOTIFY", "1").lower()
    if flag in ("0", "false", "off", "no"):
        return
    try:
        import requests
        from utils.db_config import get_settings
        settings = get_settings()
        token = settings.get("bot_token", "")
        group = settings.get("support_group_id")
        if not token or not group:
            return
        title = esc(suggestion.get("proposed", {}).get("title", ""))
        text = f"📚 Новый черновик для базы знаний:\n<b>{title}</b>\n\nПроверьте и подтвердите в Mini App."
        miniapp = settings.get("miniapp_url") or ""
        if miniapp:
            text += f"\n{miniapp}"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": group, "text": text, "parse_mode": "HTML"}, timeout=15)
    except Exception as e:
        logger.warning(f"kb suggestion notify failed: {e}")


def distill_one(db, ai_manager, doc):
    worth, reason = _is_worth_learning(doc)
    if not worth:
        mark_distilled(db, doc, "skipped_filter", reason)
        return None

    transcript = _build_transcript(doc)
    scrubbed = scrub_pii(transcript)
    similar = _find_similar_articles(db, scrubbed)
    prompt = _build_prompt(scrubbed, similar)

    try:
        raw = ai_manager.chat([
            {"role": "system", "content": METHODIST_SYSTEM},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        logger.warning(f"distill LLM call failed: {e}")
        mark_distilled(db, doc, "llm_error", str(e)[:300])
        return None

    if not raw:
        mark_distilled(db, doc, "llm_no_response")
        return None

    parsed = parse_methodist_json(raw)
    if not parsed:
        mark_distilled(db, doc, "llm_parse_error")
        return None

    if not parsed.get("should_add", False):
        mark_distilled(db, doc, "skipped_llm", str(parsed.get("reasoning", ""))[:500])
        return None

    action = parsed.get("action", "add")
    if action not in ("add", "update"):
        action = "add"

    proposed = {
        "title": (parsed.get("title") or "").strip(),
        "category": (parsed.get("category") or "general").strip(),
        "tags": parsed.get("tags") or [],
        "question_patterns": parsed.get("question_patterns") or [],
        "content": (parsed.get("content") or "").strip(),
    }
    if not proposed["title"] or not proposed["content"]:
        mark_distilled(db, doc, "llm_empty_draft")
        return None

    suggestion = {
        "transcript": _scrub_transcript(doc.get("history", [])),
        "summary": parsed.get("summary", ""),
        "proposed": proposed,
        "similar": similar,
        "action": action,
        "target_article_id": parsed.get("target_article_id"),
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "reviewed_by": None,
        "reviewed_at": None,
        "source_ticket_id": str(doc.get("_id")),
    }
    db.kb_suggestions.insert_one(suggestion)
    mark_distilled(db, doc, "suggested", action)
    _notify_managers(suggestion)
    return suggestion


def run_distillation_once():
    db = get_db()
    if db is None:
        logger.warning("kb distiller: db unavailable")
        return 0
    docs = list(db.ticket_archive.find({"distilled": False}).limit(KB_DISTILL_BATCH))
    if not docs:
        return 0
    ai_manager = AIProviderManager(db)
    processed = 0
    for doc in docs:
        try:
            distill_one(db, ai_manager, doc)
        except Exception as e:
            logger.exception(f"distill {doc.get('_id')}: {e}")
            mark_distilled(db, doc, "error", str(e)[:300])
        processed += 1
    return processed
