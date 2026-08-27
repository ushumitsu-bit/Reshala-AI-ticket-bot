
import os
import copy
import time
import threading
from pymongo import MongoClient
import logging

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "reshala_support")

# TTL кэша настроек (секунды). Кэш избавляет от лишних запросов к Mongo на каждое
# сообщение и от необходимости хранить секреты в bot_data/pickle (IMPROVEMENT_PLAN 0.2 / 2.5).
SETTINGS_CACHE_TTL = float(os.environ.get("SETTINGS_CACHE_TTL", "60"))

# Global client and db
_client = None
_db = None
_db_lock = threading.Lock()

# In-memory TTL cache for settings
_settings_cache = {"data": None, "timestamp": 0.0}
_settings_lock = threading.Lock()

def get_db():
    """
    Get the MongoDB database instance.
    Initializes connection if not already established.
    """
    global _client, _db
    if _db is None:
        with _db_lock:
            if _db is None:
                try:
                    _client = MongoClient(MONGO_URL)
                    _db = _client[DB_NAME]
                    # Verify connection
                    _client.admin.command('ping')
                    logger.info(f"Connected to MongoDB: {DB_NAME}")
                except Exception as e:
                    logger.error(f"Failed to connect to MongoDB: {e}")
                    _client = None
                    _db = None
                    return None
    return _db

def invalidate_settings_cache():
    """
    Сбросить кэш настроек. Вызывать после изменения коллекции settings
    (PUT /api/settings, тоглы в боте и т.п.).
    """
    with _settings_lock:
        _settings_cache["data"] = None
        _settings_cache["timestamp"] = 0.0


def get_settings():
    """
    Получить настройки из Mongo с фолбэком на ENV.
    Результат кэшируется на SETTINGS_CACHE_TTL секунд; возвращается копия,
    чтобы вызывающий код не мог случайно изменить закэшированный объект.
    """
    now = time.monotonic()
    with _settings_lock:
        cached = _settings_cache["data"]
        if cached is not None and (now - _settings_cache["timestamp"]) < SETTINGS_CACHE_TTL:
            return copy.deepcopy(cached)

    settings = _load_settings()

    with _settings_lock:
        _settings_cache["data"] = settings
        _settings_cache["timestamp"] = time.monotonic()

    return copy.deepcopy(settings)


def _load_settings():
    """
    Загрузить настройки из БД и смержить с ENV (при необходимости записать ENV в БД).
    Вызывается только при промахе кэша.
    """
    db = get_db()
    settings = {}
    if db is not None:
        try:
            settings = db.settings.find_one({}, {"_id": 0}) or {}
        except Exception as e:
            logger.error(f"Error fetching settings: {e}")

    # Environment variable mapping (DB Key -> ENV Key)
    env_mapping = {
        "bot_token": "BOT_TOKEN",
        "remnawave_api_url": "REMNAWAVE_API_URL",
        "remnawave_api_token": "REMNAWAVE_API_TOKEN",
        "support_group_id": "SUPPORT_GROUP_ID",
        "allowed_manager_ids": "ALLOWED_MANAGER_IDS",
        "bedolaga_api_url": "BEDOLAGA_API_URL",
        "bedolaga_api_token": "BEDOLAGA_API_TOKEN",
        "react_app_backend_url": "REACT_APP_BACKEND_URL",
        "miniapp_url": "MINI_APP_URL",
        "mini_app_domain": "MINI_APP_DOMAIN",
        "service_name": "SERVICE_NAME"
    }

    # Track if we need to update DB
    updates = {}

    for db_key, env_key in env_mapping.items():
        # Check if value is missing or empty in DB
        db_value = settings.get(db_key)
        is_empty = (
            db_value is None or 
            db_value == "" or 
            db_value == [] or 
            db_value == 0 or
            (isinstance(db_value, list) and len(db_value) == 0)
        )
        
        if db_key not in settings or is_empty:
            val = os.environ.get(env_key)
            if val:
                # Type conversion
                if db_key == "support_group_id":
                    try: val = int(val)
                    except: pass
                elif db_key == "allowed_manager_ids":
                    try:
                        if isinstance(val, str):
                            val = [int(i.strip()) for i in val.split(",") if i.strip()]
                        elif isinstance(val, (int, float)):
                            val = [int(val)]
                    except Exception as e:
                        logger.error(f"Error parsing allowed_manager_ids: {e}")
                        val = []
                
                # Special case for miniapp_url if only domain is provided
                if db_key == "miniapp_url" and val and not str(val).startswith("http"):
                    val = f"https://{val}"
                
                settings[db_key] = val
                updates[db_key] = val
    
    # Fallback for miniapp_url from mini_app_domain if miniapp_url still missing
    if "miniapp_url" not in settings or not settings.get("miniapp_url"):
        domain = settings.get("mini_app_domain")
        if domain:
            if not str(domain).startswith("http"):
                miniapp_url = f"https://{domain}"
            else:
                miniapp_url = domain
                settings["miniapp_url"] = miniapp_url
                updates["miniapp_url"] = miniapp_url

    # [CRITICAL] Always enforce ALLOWED_MANAGER_IDS from ENV
    # Even if DB has a value, we merge ENV values into it to ensure admin access
    env_managers_str = os.environ.get("ALLOWED_MANAGER_IDS", "")
    if env_managers_str:
        try:
            env_managers = [int(i.strip()) for i in env_managers_str.split(",") if i.strip()]
            current_managers = settings.get("allowed_manager_ids", [])
            
            # Ensure it's a list
            if not isinstance(current_managers, list):
                current_managers = []
                
            # Merge unique
            new_managers = list(set(current_managers + env_managers))
            
            # If changed, update
            if set(new_managers) != set(current_managers):
                settings["allowed_manager_ids"] = new_managers
                updates["allowed_manager_ids"] = new_managers
                logger.info(f"Enforced ALLOWED_MANAGER_IDS from ENV. Managers: {new_managers}")
        except Exception as e:
            logger.error(f"Error enforcing ALLOWED_MANAGER_IDS from ENV: {e}")

    # Save updates to DB if any
    if updates and db is not None:
        try:
            db.settings.update_one({}, {"$set": updates}, upsert=True)
            logger.info(f"Initialized settings from .env: {list(updates.keys())}")
        except Exception as e:
            logger.error(f"Error saving settings to DB: {e}")

    return settings

def get_bot_token():
    """Get bot token from settings."""
    settings = get_settings()
    return settings.get("bot_token", "")

def get_support_group_id():
    """Get support group ID from settings."""
    settings = get_settings()
    return settings.get("support_group_id")
