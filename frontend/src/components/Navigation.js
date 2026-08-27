import React from 'react';
import { Search, Cpu, Settings, BookOpen, MessageSquare, Flame, Lightbulb } from 'lucide-react';

const tabs = [
  { id: 'search', label: 'Поиск', icon: Search },
  { id: 'tickets', label: 'Тикеты', icon: Flame },
  { id: 'chat-test', label: 'AI Чат', icon: MessageSquare },
  { id: 'providers', label: 'AI', icon: Cpu },
  { id: 'knowledge', label: 'База', icon: BookOpen },
  { id: 'suggestions', label: 'Черновики', icon: Lightbulb },
  { id: 'settings', label: 'Настройки', icon: Settings },
];

export default function Navigation({ page, setPage, pendingCount = 0 }) {
  return (
    <nav className="nav" data-testid="navigation">
      {tabs.map(t => {
        const showBadge = t.id === 'suggestions' && pendingCount > 0;
        return (
          <button
            key={t.id}
            className={`nav-btn ${page === t.id ? 'active' : ''}`}
            onClick={() => setPage(t.id)}
            data-testid={`nav-${t.id}`}
          >
            <t.icon />
            <span>{t.label}</span>
            {showBadge && <span className="badge badge-danger">{pendingCount}</span>}
          </button>
        );
      })}
    </nav>
  );
}

