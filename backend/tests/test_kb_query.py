"""Тесты поиска по базе знаний и сборки системного промпта (services/ai/context.py)."""
from services.ai import context


class FakeKB:
    """Мини-заглушка коллекции knowledge_base с regex-матчем в памяти."""

    def __init__(self, docs):
        self.docs = docs
        self.queries = []

    def find(self, query, *a, **kw):
        import re
        self.queries.append(query)
        matched = self.docs
        if "$or" in query:
            rx = query["$or"][0]["title"]["$regex"]
            pat = re.compile(rx, re.IGNORECASE)
            matched = [
                d for d in self.docs
                if pat.search(d.get("title", "")) or pat.search(d.get("content", ""))
                or pat.search(d.get("category", "")) or pat.search(str(d.get("keywords", "")))
            ]
        elif "category" in query:
            pat = re.compile(query["category"]["$regex"], re.IGNORECASE)
            matched = [d for d in self.docs if pat.search(d.get("category", ""))]
        return _Cur(matched)


class _Cur:
    def __init__(self, docs):
        self._docs = docs

    def limit(self, n):
        return list(self._docs)[:n]


class FakeDB:
    def __init__(self, kb):
        self.knowledge_base = kb


IOS_ROUTING = {
    "title": "Настройка выборочной маршрутизации в Happ (iOS)",
    "category": "#Маршрутизация IOS",
    "content": "В iOS нельзя выбирать приложения, только домены. routing.happ.su ...",
}
PRICING = {"title": "Тарифы", "category": "pricing", "content": "30 дней — 150 рублей"}
AI_CHEAT = {"title": "Инструкция для AI-бота поддержки", "category": "Инструкция для AI", "content": "..."}


def test_finds_ios_routing_by_synonyms():
    db = FakeDB(FakeKB([IOS_ROUTING, PRICING, AI_CHEAT]))
    ctx = context.build_knowledge_context(db, "как на айфоне сделать чтобы госуслуги не шли через vpn")
    assert "маршрутизации в Happ (iOS)" in ctx
    assert "routing.happ.su" in ctx


def test_keywords_field_is_scored():
    # статья, где термин запроса есть только в keywords, должна победить
    kw_art = {"title": "Про разделение трафика", "category": "general",
              "keywords": "айфон сбербанк госуслуги банк не работает автоконфиг msk",
              "content": "Подключитесь к серверу Авто RU."}
    noise = {"title": "Тарифы", "category": "pricing", "content": "150 рублей"}
    db = FakeDB(FakeKB([noise, kw_art]))
    ctx = context.build_knowledge_context(db, "на айфоне не работает сбербанк")
    assert "Про разделение трафика" in ctx


def test_fallback_to_core_articles_when_no_match():
    db = FakeDB(FakeKB([IOS_ROUTING, PRICING, AI_CHEAT]))
    ctx = context.build_knowledge_context(db, "абракадабра квакозябра")
    assert "Инструкция для AI-бота" in ctx


def test_stopwords_do_not_drive_search():
    kb = FakeKB([IOS_ROUTING, PRICING, AI_CHEAT])
    context.build_knowledge_context(FakeDB(kb), "здравствуйте подскажите пожалуйста")
    # только стоп-слова -> нет осмысленных токенов -> фолбэк на core, без $or-запроса
    assert all("$or" not in q for q in kb.queries)


def test_malicious_regex_is_neutralised():
    kb = FakeKB([PRICING])
    context.build_knowledge_context(FakeDB(kb), "(a+)+$ vpn")
    ors = [q for q in kb.queries if "$or" in q]
    assert ors and "(a+)+$" not in ors[0]["$or"][0]["title"]["$regex"]


def test_empty_on_no_db():
    assert context.build_knowledge_context(None, "vpn") == ""


def test_build_system_prompt_substitutes_and_appends():
    settings = {
        "service_name": "S-Access Support",
        "main_bot_username": "Isothermbot",
        "system_prompt_override": "Бот сервиса {service_name}. Продажи: @{main_bot}.",
    }
    p = context.build_system_prompt(settings, user_context="## USER", kb_context="## KB TEXT")
    assert "S-Access Support" in p and "@Isothermbot" in p
    assert "{service_name}" not in p and "{main_bot}" not in p
    assert "ПРИОРИТЕТНЫЕ ПРАВИЛА" in p
    assert "## USER" in p
    assert "БАЗА ЗНАНИЙ" in p and "## KB TEXT" in p


def test_build_system_prompt_falls_back_to_stock():
    p = context.build_system_prompt({"service_name": "X", "main_bot_username": "Y"})
    assert "AI-ассистент" in p
    assert "ПРИОРИТЕТНЫЕ ПРАВИЛА" in p


def test_escalation_detection_multilingual():
    from utils.support_common import should_escalate
    assert should_escalate("Сейчас передам Ваш вопрос менеджеру.")
    assert should_escalate("Подключаю менеджера, подождите минутку.")
    assert should_escalate("Это вопрос для менеджера, он скоро ответит.")
    assert should_escalate("I'll pass your question to a manager.")
    assert should_escalate("")  # пустой ответ -> эскалация
    assert not should_escalate("Попробуйте сменить сервер, обычно помогает.")
    assert not should_escalate("Your subscription is active until next month.")


def test_filter_strips_markdown():
    from bot.handlers.support_client import filter_ai_thinking
    out = filter_ai_thinking("Open **@Isothermbot** and tap *Connect*.\n- step one\n## Header\n`code`")
    assert "**" not in out and "*Connect*" not in out
    assert "@Isothermbot" in out and "Connect" in out
    assert "Header" in out and "#" not in out
    assert "• step one" in out
