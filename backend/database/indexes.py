from pymongo.database import Database
import logging

logger = logging.getLogger(__name__)


async def ensure_indexes(db: Database):
    """
    Ensure required indexes exist on MongoDB collections.
    Каждый индекс создаётся независимо, чтобы падение одного не ломало остальные.
    """
    logger.info("Ensuring indexes...")

    def _safe(collection, *args, **kwargs):
        try:
            collection.create_index(*args, **kwargs)
        except Exception as e:
            logger.error(f"Failed to create index {args} on {collection.name}: {e}")

    # Миграция: гарантируем is_removed=False у существующих активных тикетов,
    # иначе partial unique index не покроет старые документы.
    try:
        db.tickets.update_many({"is_removed": {"$exists": False}}, {"$set": {"is_removed": False}})
    except Exception as e:
        logger.error(f"Migration is_removed failed: {e}")

    # tickets
    _safe(db.tickets, [("status", 1), ("created_at", -1)])
    _safe(db.tickets, "client_id")
    _safe(db.tickets, "topic_id")
    _safe(db.tickets, [("escalated_at", -1)])
    # Уникальный активный тикет на клиента (защита от гонки).
    # $ne не поддерживается в partialFilterExpression — используем $eq.
    _safe(db.tickets, [("client_id", 1)], unique=True, partialFilterExpression={"is_removed": False})

    # ticket_archive
    _safe(db.ticket_archive, "distilled")
    _safe(db.ticket_archive, "closed_at")
    _safe(db.ticket_archive, "client_id")

    # kb_suggestions: status + created_at (TTL 30 дней — ретеншен черновиков)
    _safe(db.kb_suggestions, "status")
    _safe(db.kb_suggestions, "created_at", expireAfterSeconds=30 * 86400)

    logger.info("Indexes ensured.")
