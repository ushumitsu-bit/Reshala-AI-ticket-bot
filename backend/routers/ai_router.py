"""
AI Router — чат с AI и управление провайдерами
Стоковый промпт использует переменные из настроек (service_name и т.д.)
"""
import os
import re

from fastapi import APIRouter, Body, Depends
from services.ai.manager import AIProviderManager
from services.ai.context import (
    build_knowledge_context,
    build_system_prompt,
    get_stock_prompt as _ctx_stock_prompt,
)
from middleware.auth import require_manager
from utils.db_config import get_db, get_settings

router = APIRouter(dependencies=[Depends(require_manager)])


def _get_settings():
    """Получить все настройки из БД (через кэширующий слой)."""
    return get_settings()


def get_stock_prompt(settings: dict = None) -> str:
    """Стоковый промпт с подстановкой переменных (см. services/ai/context.py)."""
    return _ctx_stock_prompt(settings if settings is not None else _get_settings())


def get_system_prompt() -> str:
    """Финальный системный промпт: override|сток + приоритетные правила + переменные."""
    return build_system_prompt(_get_settings())


@router.post("/test-connection")
def test_connection(data: dict = Body(...)):
    provider_name = data.get("provider", "").strip()
    key = data.get("key", "").strip() or None
    if not provider_name:
        return {"ok": False, "error": "provider required"}
    db = get_db()
    ai_manager = AIProviderManager(db)
    result = ai_manager.test_connection(provider_name, key)
    if result.get("ok") and result.get("models"):
        db.ai_providers.update_one(
            {"name": provider_name},
            {"$set": {"models": result["models"]}}
        )
        if not db.ai_providers.find_one({"name": provider_name}, {"_id": 0}).get("selected_model"):
            db.ai_providers.update_one(
                {"name": provider_name},
                {"$set": {"selected_model": result["models"][0]}}
            )
    return result


@router.get("/models/{provider_name}")
def get_models(provider_name: str):
    db = get_db()
    ai_manager = AIProviderManager(db)
    provider = ai_manager.get_provider(provider_name)
    if not provider:
        return {"ok": False, "error": "provider not found", "models": []}
    return {"ok": True, "models": provider.get("models", []), "selected": provider.get("selected_model", "")}


@router.post("/set-model")
def set_model(data: dict = Body(...)):
    provider_name = data.get("provider", "")
    model = data.get("model", "")
    if not provider_name or not model:
        return {"ok": False, "error": "provider and model required"}
    db = get_db()
    ai_manager = AIProviderManager(db)
    ai_manager.set_model(provider_name, model)
    return {"ok": True}


@router.post("/set-active-provider")
def set_active_provider(data: dict = Body(...)):
    name = data.get("provider", "")
    if not name:
        return {"ok": False, "error": "provider required"}
    db = get_db()
    ai_manager = AIProviderManager(db)
    ai_manager.set_active_provider(name)
    return {"ok": True}


@router.post("/chat")
def chat_test(data: dict = Body(...)):
    """Chat endpoint for AI testing and support"""
    message = data.get("message", "").strip()
    provider = data.get("provider", None)
    user_context = data.get("user_context", "")
    
    if not message:
        return {"ok": False, "error": "message required"}

    db = get_db()
    ai_manager = AIProviderManager(db)

    # Единый промпт + контекст БЗ (та же логика, что в живом боте)
    kb_context = build_knowledge_context(db, message, limit=5)
    system_prompt = build_system_prompt(_get_settings(), user_context=user_context, kb_context=kb_context)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message}
    ]
    
    reply = ai_manager.chat(messages, provider)
    
    if reply:
        escalation_keywords = ["менеджер", "эскалац", "не могу помочь", "обратитесь к", "вызвать поддержку"]
        needs_escalation = any(kw in reply.lower() for kw in escalation_keywords)
        
        return {
            "ok": True, 
            "reply": reply,
            "needs_escalation": needs_escalation
        }
    
    return {"ok": False, "error": "No response from AI provider. Check keys and provider settings."}


@router.get("/stock-prompt")
def get_stock_prompt_endpoint():
    """Get the stock system prompt with current settings"""
    settings = _get_settings()
    return {
        "prompt": get_stock_prompt(settings),
        "variables": {
            "service_name": settings.get("service_name") or "VPN Поддержка",
            "main_bot": settings.get("main_bot_username") or "[не указан]"
        }
    }


def _get_knowledge_context(query: str) -> str:
    """Поиск релевантных статей БЗ (см. services/ai/context.py)."""
    return build_knowledge_context(get_db(), query, limit=5)
