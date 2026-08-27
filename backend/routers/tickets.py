"""
Tickets Router — управление тикетами поддержки

Статусы:
  💬 open — Новый тикет
  🔥 escalated — Эскалация (клиент вызвал менеджера / AI не знает ответа)
  🚨 suspicious — Подозрительный (пользователь не найден в системе)
  ✅ closed — Закрыт
"""
from fastapi import APIRouter, Body, Depends, Request
from typing import List
import logging
import sys
import os

# Добавляем путь к корню для импорта utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.ticket_service import TicketService
from dependencies import get_ticket_service
from middleware.rate_limit import limiter
from middleware.auth import require_manager

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_manager)])

def serialize_ticket(ticket):
    """Convert MongoDB document to JSON-serializable dict"""
    if not ticket:
        return None
    return {
        "id": str(ticket.get("_id", "")),
        "client_id": ticket.get("client_id"),
        "client_name": ticket.get("client_name"),
        "client_username": ticket.get("client_username"),
        "topic_id": ticket.get("topic_id"),
        "status": ticket.get("status", "open"),
        "reason": ticket.get("reason"),
        "escalated_at": ticket.get("escalated_at").isoformat() if ticket.get("escalated_at") else None,
        "created_at": ticket.get("created_at").isoformat() if ticket.get("created_at") else None,
        "closed_at": ticket.get("closed_at").isoformat() if ticket.get("closed_at") else None,
        "last_messages": ticket.get("last_messages", []),
        "history": ticket.get("history", []),
        "user_data": ticket.get("user_data"),
        "attachments": ticket.get("attachments", []),
        "is_removed": ticket.get("is_removed", False),
    }


@router.get("/escalated")
@limiter.limit("30/minute")
async def get_escalated_tickets(
    request: Request,
    ticket_service: TicketService = Depends(get_ticket_service)
):
    """Get escalated (🔥) tickets only"""
    tickets = await ticket_service.get_escalated_tickets()
    return {"tickets": [serialize_ticket(t) for t in tickets]}


@router.get("/active")
@limiter.limit("30/minute")
async def get_active_tickets(
    request: Request,
    ticket_service: TicketService = Depends(get_ticket_service)
):
    """Get all active tickets (escalated + suspicious) — без open (они у AI) и closed!"""
    tickets = await ticket_service.get_active_tickets()
    return {"tickets": [serialize_ticket(t) for t in tickets]}


@router.get("/suspicious")
@limiter.limit("30/minute")
async def get_suspicious_tickets(
    request: Request,
    ticket_service: TicketService = Depends(get_ticket_service)
):
    """Get suspicious (🚨) tickets — users not found in system"""
    tickets = await ticket_service.get_suspicious_tickets()
    return {"tickets": [serialize_ticket(t) for t in tickets]}


@router.get("/{ticket_id}")
@limiter.limit("60/minute")
async def get_ticket(
    request: Request,
    ticket_id: str,
    ticket_service: TicketService = Depends(get_ticket_service)
):
    """Get single ticket by ID"""
    try:
        ticket = await ticket_service.get_ticket(ticket_id)
        if not ticket:
            return {"ok": False, "error": "ticket_not_found"}
        return {"ok": True, "ticket": serialize_ticket(ticket)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/{ticket_id}/reply")
@limiter.limit("20/minute")
async def reply_to_ticket(
    request: Request,
    ticket_id: str,
    data: dict = Body(...),
    ticket_service: TicketService = Depends(get_ticket_service)
):
    """Отправить ответ менеджера клиенту через Telegram"""
    message = data.get("message", "").strip()
    manager_name = data.get("manager_name", "Менеджер")
    
    if not message:
        return {"ok": False, "error": "message_required"}
    
    result = await ticket_service.reply_to_ticket(ticket_id, message, manager_name)
    return result


@router.post("/{ticket_id}/close")
@limiter.limit("20/minute")
async def close_ticket(
    request: Request,
    ticket_id: str,
    ticket_service: TicketService = Depends(get_ticket_service)
):
    """Close ticket (✅) — переименовывает топик и закрывает его"""
    result = await ticket_service.close_ticket(ticket_id, actor="manager")
    return result


@router.post("/{ticket_id}/remove")
@limiter.limit("20/minute")
async def remove_ticket(
    request: Request,
    ticket_id: str,
    ticket_service: TicketService = Depends(get_ticket_service)
):
    """Remove ticket from list (for suspicious/closed tickets)"""
    try:
        success = await ticket_service.remove_ticket(ticket_id)
        if not success:
            return {"ok": False, "error": "ticket_not_found_or_invalid"}
        return {"ok": True, "message": "Тикет удалён из списка"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/create")
@limiter.limit("5/minute")
async def create_ticket(
    request: Request,
    data: dict = Body(...),
    ticket_service: TicketService = Depends(get_ticket_service)
):
    """Create new ticket"""
    client_id = data.get("client_id")
    if not client_id:
        return {"ok": False, "error": "client_id_required"}
    
    result = await ticket_service.create_ticket(
        client_id=client_id,
        client_name=data.get("client_name"),
        client_username=data.get("client_username"),
        user_data=data.get("user_data"),
        reason=data.get("reason"),
        last_messages=data.get("last_messages"),
        is_suspicious=data.get("is_suspicious")
    )
    
    return {"ok": True, **result}


@router.post("/{ticket_id}/escalate")
@limiter.limit("10/minute")
async def escalate_ticket(
    request: Request,
    ticket_id: str, 
    data: dict = Body(...),
    ticket_service: TicketService = Depends(get_ticket_service)
):
    """Escalate ticket to manager (🔥)"""
    try:
        success = await ticket_service.escalate_ticket(
            ticket_id, 
            reason=data.get("reason", "Пользователь запросил менеджера"),
            user_data=data.get("user_data"),
            last_messages=data.get("last_messages")
        )
        if not success:
            return {"ok": False, "error": "ticket_not_found"}
        return {"ok": True, "message": "Тикет эскалирован"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/{ticket_id}/mark-suspicious")
@limiter.limit("10/minute")
async def mark_suspicious(
    request: Request,
    ticket_id: str, 
    data: dict = Body(...),
    ticket_service: TicketService = Depends(get_ticket_service)
):
    """Mark ticket as suspicious (🚨) — user not found in system"""
    try:
        success = await ticket_service.mark_suspicious(
            ticket_id, 
            reason=data.get("reason", "Пользователь не найден в системе")
        )
        if not success:
            return {"ok": False, "error": "ticket_not_found"}
        return {"ok": True, "message": "Тикет помечен как подозрительный"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/{ticket_id}/add-attachment")
@limiter.limit("10/minute")
async def add_attachment(
    request: Request,
    ticket_id: str, 
    data: dict = Body(...),
    ticket_service: TicketService = Depends(get_ticket_service)
):
    """Add attachment (screenshot, subscription link) to ticket"""
    att_type = data.get("type")
    value = data.get("value") or data.get("url")
    
    if not att_type or not value:
        return {"ok": False, "error": "type and value required"}
    
    try:
        success = await ticket_service.add_attachment(ticket_id, att_type, value, data.get("url"))
        if not success:
             return {"ok": False, "error": "ticket_not_found"}
        return {"ok": True, "message": "Вложение добавлено"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
