import React, { useState, useEffect, useCallback } from 'react';
import './App.css';
import Navigation from './components/Navigation';
import { initTelegram } from './telegram';
import SearchPage from './pages/SearchPage';
import SettingsPage from './pages/SettingsPage';
import ProvidersPage from './pages/ProvidersPage';
import KnowledgePage from './pages/KnowledgePage';
import KnowledgeSuggestionsPage from './pages/KnowledgeSuggestionsPage';
import AIChatTestPage from './pages/AIChatTestPage';
import TicketsPage from './pages/TicketsPage';
import { ShieldX } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

function AccessDenied() {
  return (
    <div className="app" data-testid="app-container">
      <div className="access-denied" data-testid="access-denied">
        <div className="access-denied-icon">
          <ShieldX size={48} />
        </div>
        <h2>Доступ запрещён</h2>
        <p>Mini App доступен только для менеджеров.</p>
        <p className="text-muted">Если вы менеджер — обратитесь к администратору для добавления вашего ID.</p>
      </div>
    </div>
  );
}

function App() {
  const [page, setPage] = useState('search');
  const [settings, setSettings] = useState(null);
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [accessDenied, setAccessDenied] = useState(false);
  const [initData, setInitData] = useState('');
  const [pendingCount, setPendingCount] = useState(0);

  // Сохранение состояния поиска между вкладками
  const [searchState, setSearchState] = useState({
    query: '',
    result: null,
    section: 'profile'
  });

  const fetchSettings = useCallback(async (dataStr) => {
    try {
      const headers = {};
      if (dataStr) headers['X-Telegram-Init-Data'] = dataStr;

      const r = await fetch(`${API}/api/settings`, { headers });
      const data = await r.json();
      setSettings(data);
      return data;
    } catch (e) {
      console.error('Settings fetch error:', e);
      return null;
    }
  }, []);

  const fetchProviders = useCallback(async (dataStr) => {
    try {
      const headers = {};
      if (dataStr) headers['X-Telegram-Init-Data'] = dataStr;

      const r = await fetch(`${API}/api/settings/providers`, { headers });
      const data = await r.json();
      setProviders(data.providers || []);
    } catch (e) {
      console.error('Providers fetch error:', e);
    }
  }, []);

  const fetchPendingCount = useCallback(async (dataStr) => {
    try {
      const headers = {};
      if (dataStr) headers['X-Telegram-Init-Data'] = dataStr;
      const r = await fetch(`${API}/api/kb-suggestions?status=pending`, { headers });
      const data = await r.json();
      setPendingCount((data.suggestions || []).length);
    } catch (e) {
      console.error('Suggestions fetch error:', e);
    }
  }, []);

  const checkAccess = useCallback((settingsData, userId) => {
    if (!settingsData || !userId) return false;
    const allowedIds = settingsData.allowed_manager_ids || [];
    return allowedIds.some((id) => String(id) === String(userId));
  }, []);

  useEffect(() => {
    const init = async () => {
      const { user: tgUser, initData: rawData } = initTelegram();

      setInitData(rawData);

      const settingsData = await fetchSettings(rawData);
      await fetchProviders(rawData);
      await fetchPendingCount(rawData);

      if (tgUser?.id) {
        const hasAccess = checkAccess(settingsData, tgUser.id);
        setAccessDenied(!hasAccess);
      } else {
        // Dev mode fallback or denial
        const isDev = !rawData;
        setAccessDenied(!isDev);
      }

      setLoading(false);
    };

    init();
  }, [fetchSettings, fetchProviders, fetchPendingCount, checkAccess]);

  if (loading) {
    return (
      <div className="app-loading" data-testid="app-loading">
        <div className="loading-spinner" />
        <span>Загрузка...</span>
      </div>
    );
  }

  if (accessDenied) {
    return <AccessDenied />;
  }

  return (
    <div className="app" data-testid="app-container">
      <Navigation page={page} setPage={setPage} pendingCount={pendingCount} />
      <main className="app-main">
        {/* Поиск — сохраняет состояние */}
        <div style={{ display: page === 'search' ? 'block' : 'none' }}>
          <SearchPage
            settings={settings}
            searchState={searchState}
            setSearchState={setSearchState}
            initData={initData}
          />
        </div>

        {/* Тикеты */}
        <div style={{ display: page === 'tickets' ? 'block' : 'none' }}>
          <TicketsPage settings={settings} initData={initData} />
        </div>

        {/* AI Чат */}
        {page === 'chat-test' && <AIChatTestPage settings={settings} initData={initData} />}

        {/* AI Провайдеры */}
        {page === 'providers' && (
          <ProvidersPage
            providers={providers}
            settings={settings}
            initData={initData}
            onRefresh={() => { fetchProviders(initData); fetchSettings(initData); }}
          />
        )}

        {/* База знаний */}
        {page === 'knowledge' && <KnowledgePage initData={initData} />}

        {/* Черновики (самообучение) */}
        {page === 'suggestions' && (
          <KnowledgeSuggestionsPage initData={initData} onReview={() => fetchPendingCount(initData)} />
        )}

        {/* Настройки */}
        {page === 'settings' && (
          <SettingsPage
            settings={settings}
            initData={initData}
            onUpdate={() => fetchSettings(initData)}
          />
        )}
      </main>
    </div>
  );
}

export default App;
