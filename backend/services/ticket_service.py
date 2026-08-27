import logging
from datetime import datetime, timezone
from typing import List, Optional
from bson import ObjectId
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from services.telegram_service import TelegramService
from utils.support_common import get_topic_name, build_support_header, TOPIC_CLOSED, esc, normalize_role

logger = logging.getLogger(__name__)

class TicketService:
    def __init__(self, db: Database, telegram_service: Optional[TelegramService] = None, support_group_id: Optional[int] = None):
        self.db = db
        self.telegram_service = telegram_service
        self.support_group_id = support_group_id

    async def create_ticket(self, client_id: int, client_name: str, client_username: str, 
                          user_data: dict, reason: str = None, last_messages: list = None,
                          is_suspicious: bool = False) -> dict:
        """Creates a new ticket and optionally a Telegram forum topic."""
        
        # Check if active ticket exists?
        # For now, following existing logic: just create.
        
        status = "suspicious" if is_suspicious else "open"
        
        ticket = {
            "client_id": client_id,
            "client_name": client_name,
            "client_username": client_username,
            "status": status,
            "reason": reason,
            "messages": [],
            "last_messages": last_messages or [],
            "user_data": user_data,
            "attachments": [],
            "created_at": datetime.now(timezone.utc),
            "escalated_at": None,
            "is_removed": False,
        }

        topic_id = None
        if self.telegram_service and self.support_group_id:
             try:
                # 1. Create topic
                topic_name = get_topic_name(client_username, status)
                topic_id = await self.telegram_service.create_forum_topic(
                    chat_id=self.support_group_id,
                    name=topic_name
                )
                ticket["topic_id"] = topic_id

                # 2. Send header
                user_info = user_data.get("user", {}) if user_data else {}
                balance_data = user_data.get("bedolaga_user") if user_data else {}
                header_text = build_support_header(user_info, balance_data, is_suspicious)
                
                await self.telegram_service.send_message(
                    chat_id=self.support_group_id,
                    message_thread_id=topic_id,
                    text=header_text
                )
                
                # 3. Pin message? (TelegramService logic needs expansion or direct bot usage if needed, but for now simple send)
                # Note: helper 'send_message' returns None currently in my impl, need to update if I want to pin.
             except Exception as e:
                logger.error(f"Error creating telegram topic: {e}")

        try:
            result = self.db.tickets.insert_one(ticket)
        except DuplicateKeyError:
            # Защита: старый «закрытый» тикет с is_removed=False блокирует
            # частичный уникальный индекс client_id. Помечаем его убранным и пробуем снова.
            self.db.tickets.update_one(
                {"client_id": client_id, "status": "closed"},
                {"$set": {"is_removed": True, "removed_at": datetime.now(timezone.utc)}},
            )
            try:
                result = self.db.tickets.insert_one(ticket)
            except DuplicateKeyError:
                existing = self.db.tickets.find_one({"client_id": client_id, "is_removed": {"$ne": True}})
                if existing:
                    return {
                        "ticket_id": str(existing["_id"]),
                        "status": existing.get("status"),
                        "topic_id": existing.get("topic_id"),
                        "duplicate": True,
                    }
                raise
        return {
            "ticket_id": str(result.inserted_id),
            "status": status,
            "topic_id": topic_id
        }

    async def get_active_tickets(self, manager_id: int = None) -> List[dict]:
        """Get all active tickets (escalated + suspicious)"""
        tickets = list(self.db.tickets.find(
            {
                "status": {"$in": ["escalated", "suspicious"]},
                "is_removed": {"$ne": True}
            }
        ).sort([("status", 1), ("created_at", -1)]).limit(100))
        
        order = {"suspicious": 0, "escalated": 1}
        tickets.sort(key=lambda t: order.get(t.get("status"), 3))
        return tickets

    async def get_escalated_tickets(self, limit: int = 50) -> List[dict]:
        """Get escalated tickets"""
        return list(self.db.tickets.find(
            {"status": "escalated", "is_removed": {"$ne": True}}
        ).sort("escalated_at", -1).limit(limit))

    async def get_suspicious_tickets(self, limit: int = 50) -> List[dict]:
        """Get suspicious tickets"""
        return list(self.db.tickets.find(
            {"status": "suspicious", "is_removed": {"$ne": True}}
        ).sort("created_at", -1).limit(limit))

    async def get_ticket(self, ticket_id: str) -> Optional[dict]:
        """Get ticket by ID"""
        if not ObjectId.is_valid(ticket_id):
            return None
        return self.db.tickets.find_one({"_id": ObjectId(ticket_id)})

    async def remove_ticket(self, ticket_id: str) -> bool:
        """Remove ticket"""
        if not ObjectId.is_valid(ticket_id):
            return False
        result = self.db.tickets.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": {"is_removed": True, "removed_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

    async def escalate_ticket(self, ticket_id: str, reason: str = None, user_data: dict = None, last_messages: list = None):
        """Escalate ticket to manager"""
        update_data = {
            "status": "escalated",
            "escalated_at": datetime.now(timezone.utc)
        }
        if reason: update_data["reason"] = reason
        if user_data: update_data["user_data"] = user_data
        if last_messages: update_data["last_messages"] = last_messages

        result = self.db.tickets.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def mark_suspicious(self, ticket_id: str, reason: str = None):
        """Mark ticket as suspicious"""
        update_data = {
            "status": "suspicious",
            "escalated_at": datetime.now(timezone.utc)
        }
        if reason: update_data["reason"] = reason
        
        result = self.db.tickets.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def add_attachment(self, ticket_id: str, att_type: str, value: str, url: str = None):
        """Add attachment to ticket"""
        attachment = {
            "type": att_type,
            "value": value,
            "url": url,
            "added_at": datetime.now(timezone.utc).isoformat()
        }
        result = self.db.tickets.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$push": {"attachments": attachment}}
        )
        return result.modified_count > 0

    async def reply_to_ticket(self, ticket_id: str, message: str, manager_name: str) -> dict:
        """Reply to ticket from manager"""
        ticket = self.db.tickets.find_one({"_id": ObjectId(ticket_id)})
        if not ticket:
            return {"ok": False, "error": "ticket_not_found"}

        client_id = ticket.get("client_id")
        topic_id = ticket.get("topic_id")
        
        if not client_id:
             return {"ok": False, "error": "No client_id in ticket"}

        telegram_sent = False
        telegram_error = None

        if self.telegram_service:
            # 1. Send to client
            text_client = f"💬 <b>Поддержка</b> ({esc(manager_name)}):\n\n{esc(message)}"
            try:
                await self.telegram_service.send_message(chat_id=client_id, text=text_client)
                telegram_sent = True
            except Exception as e:
                telegram_error = str(e)

            # 2. Send to support group
            if self.support_group_id and topic_id:
                text_group = f"👨‍💼 <b>{esc(manager_name)}:</b>\n\n{esc(message)}"
                await self.telegram_service.send_message(
                    chat_id=self.support_group_id,
                    text=text_group,
                    message_thread_id=topic_id
                )

        # Update DB
        last_messages = ticket.get("last_messages", [])
        last_messages.append({
            "role": "manager",
            "name": manager_name,
            "content": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sent_to_telegram": telegram_sent,
        })
        if len(last_messages) > 20: last_messages = last_messages[-20:]

        self.db.tickets.update_one(
            {"_id": ObjectId(ticket_id)},
            {
                "$set": {
                    "last_messages": last_messages,
                    "last_reply_at": datetime.now(timezone.utc),
                    "ai_disabled": True  # <--- ОТКЛЮЧАЕМ ИИ ПРИ ОТВЕТЕ МЕНЕДЖЕРА (API)
                }
            }
        )
        self.append_history(ticket["_id"], "manager", message, {"name": manager_name, "sent_to_telegram": telegram_sent})

        if telegram_sent:
            return {"ok": True, "message": "Reply sent"}
        else:
            return {"ok": False, "error": telegram_error or "Telegram service unavailable", "saved": True}

    def _ticket_query(self, ticket_ref):
        """Резолвит ticket_ref (_id | client_id > 1e6 | topic_id) в Mongo-запрос."""
        if isinstance(ticket_ref, ObjectId):
            return {"_id": ticket_ref}
        if isinstance(ticket_ref, str) and ObjectId.is_valid(ticket_ref):
            return {"_id": ObjectId(ticket_ref)}
        s = str(ticket_ref)
        if s.isdigit():
            tid = int(s)
            return {"$or": [
                {"topic_id": tid},
                {"client_id": tid, "is_removed": {"$ne": True}, "status": {"$ne": "closed"}},
            ]}
        return None

    def append_history(self, ticket_ref, role: str, content: str, meta: dict = None):
        """Единый хелпер записи реплики в history с нормализованной ролью."""
        query = self._ticket_query(ticket_ref)
        if query is None:
            return False
        entry = {
            "role": normalize_role(role),
            "content": content or "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if meta:
            entry.update(meta)
        result = self.db.tickets.update_one(query, {"$push": {"history": entry}})
        return result.modified_count > 0

    def _archive_ticket(self, ticket: dict, actor: str, actor_id: int) -> bool:
        """Перенос тикета в ticket_archive. Возвращает True при успехе."""
        archive_doc = dict(ticket)
        archive_doc.pop("_id", None)
        archive_doc["closed_at"] = datetime.now(timezone.utc)
        archive_doc["closed_by"] = {"actor": actor, "actor_id": actor_id}
        archive_doc["distilled"] = False
        try:
            self.db.ticket_archive.insert_one(archive_doc)
            return True
        except Exception as e:
            logger.error(f"ticket_archive insert failed: {e}")
            return False

    async def close_ticket(self, ticket_ref, actor: str = "manager", actor_id: int = None):
        """Единый путь закрытия тикета. actor: 'manager' | 'client'."""
        if actor not in ("manager", "client"):
            return {"ok": False, "error": "Invalid actor"}

        query = self._ticket_query(ticket_ref)
        if query is None:
            return {"ok": False, "error": "Invalid ticket_id"}

        ticket = self.db.tickets.find_one(query)
        if not ticket:
            return {"ok": False, "error": "Ticket not found"}

        thread_id = ticket.get("topic_id")
        client_id = ticket.get("client_id")
        client_username = ticket.get("client_username") or ticket.get("client_name") or ""
        current_status = ticket.get("status")

        if current_status == "closed":
             return {"ok": True, "message": "Already closed"}

        is_suspicious = current_status == "suspicious"
        is_manager = actor == "manager"
        final_status = "closed" if is_manager else ("suspicious" if is_suspicious else "closed")

        if self.telegram_service and self.support_group_id and thread_id:
            try:
                if is_manager or not is_suspicious:
                    new_name = get_topic_name(client_username, final_status)
                    logger.info(f"[CLOSE_TICKET] Renaming topic {thread_id} to: {new_name} (status={final_status})")
                    await self.telegram_service.edit_forum_topic(self.support_group_id, thread_id, new_name)

                    await self.telegram_service.close_forum_topic(self.support_group_id, thread_id)
                    logger.info(f"[CLOSE_TICKET] Closed topic {thread_id}")

                    closer = "менеджером" if is_manager else "клиентом"
                    await self.telegram_service.send_message(
                        self.support_group_id,
                        f"✅ <b>Тикет закрыт {closer}.</b>",
                        thread_id
                    )

                    if is_manager and client_id:
                        await self.telegram_service.send_message(client_id, "✅ Тикет поддержки закрыт менеджером.\n\nЕсли нужна помощь — напишите снова.")
                else:
                    await self.telegram_service.send_message(
                        self.support_group_id,
                        "✅ Клиент закрыл чат. Тикет остаётся для проверки!",
                        thread_id
                    )
            except Exception as e:
                logger.error(f"Telegram error in close_ticket: {e}")

        if actor == "client" and is_suspicious:
            logger.info(f"[CLOSE_TICKET] Keeping suspicious ticket {ticket['_id']} in DB")
            self.db.tickets.update_one(
                {"_id": ticket["_id"]},
                {"$set": {"status": "suspicious", "closed_at": datetime.now(timezone.utc)}}
            )
        else:
            logger.info(f"[CLOSE_TICKET] Archiving ticket {ticket['_id']} and removing from active")
            if self._archive_ticket(ticket, actor, actor_id):
                self.db.tickets.delete_one({"_id": ticket["_id"]})
            else:
                return {"ok": False, "error": "archive failed", "client_id": client_id, "topic_id": thread_id}

        return {"ok": True, "message": "Ticket closed", "client_id": client_id, "topic_id": thread_id}
