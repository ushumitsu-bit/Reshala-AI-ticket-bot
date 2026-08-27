import React, { useState, useEffect, useCallback } from 'react';
import { Lightbulb, Check, X, ArrowLeft, FileText, Tag } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

function apiHeaders(initData, json = true) {
  const h = {};
  if (json) h['Content-Type'] = 'application/json';
  if (initData) h['X-Telegram-Init-Data'] = initData;
  return h;
}

export default function KnowledgeSuggestionsPage({ initData, onReview }) {
  const [suggestions, setSuggestions] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(null);
  const [msg, setMsg] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchSuggestions = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/kb-suggestions?status=pending`, { headers: apiHeaders(initData, false) });
      const data = await r.json();
      setSuggestions(data.suggestions || []);
    } catch (e) {
      console.error('fetch suggestions error:', e);
    } finally {
      setLoading(false);
    }
  }, [initData]);

  useEffect(() => { fetchSuggestions(); }, [fetchSuggestions]);

  const openDetail = async (id) => {
    setMsg('');
    const r = await fetch(`${API}/api/kb-suggestions/${id}`, { headers: apiHeaders(initData, false) });
    const data = await r.json();
    if (data.ok) {
      const p = data.suggestion.proposed || {};
      setSelected(data.suggestion);
      setForm({
        title: p.title || '',
        category: p.category || 'general',
        tags: (p.tags || []).join(', '),
        question_patterns: (p.question_patterns || []).join(', '),
        content: p.content || '',
      });
    }
  };

  const closeDetail = () => { setSelected(null); setForm(null); };
  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }));

  const approve = async () => {
    if (!selected || saving) return;
    setSaving(true);
    setMsg('');
    const body = {
      title: form.title,
      category: form.category,
      tags: form.tags.split(',').map(s => s.trim()).filter(Boolean),
      question_patterns: form.question_patterns.split(',').map(s => s.trim()).filter(Boolean),
      content: form.content,
    };
    const r = await fetch(`${API}/api/kb-suggestions/${selected.id}/approve`, {
      method: 'POST',
      headers: apiHeaders(initData),
      body: JSON.stringify(body),
    });
    const data = await r.json();
    setSaving(false);
    if (data.ok) {
      setMsg('✅ Добавлено в базу знаний');
      setSelected(null);
      setForm(null);
      fetchSuggestions();
      if (onReview) onReview();
    } else {
      setMsg(data.error || 'Ошибка');
    }
  };

  const reject = async () => {
    if (!selected || saving) return;
    setSaving(true);
    const r = await fetch(`${API}/api/kb-suggestions/${selected.id}/reject`, {
      method: 'POST',
      headers: apiHeaders(initData),
      body: JSON.stringify({ reason: 'Отклонено менеджером' }),
    });
    const data = await r.json();
    setSaving(false);
    if (data.ok) {
      setMsg('Черновик отклонён');
      setSelected(null);
      setForm(null);
      fetchSuggestions();
      if (onReview) onReview();
    }
  };

  if (loading) {
    return <div className="empty-state"><div className="loading-spinner" /></div>;
  }

  if (selected && form) {
    return (
      <div className="page" data-testid="suggestion-detail">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <button className="btn btn-icon btn-secondary" onClick={closeDetail}><ArrowLeft size={16} /></button>
          <span className="card-title">Черновик статьи</span>
        </div>

        <div className="card" style={{ marginBottom: 12 }}>
          <div className="card-header"><span className="card-title">Транскрипт диалога</span></div>
          <div>
            {(selected.transcript || []).map((h, i) => (
              <div key={i} style={{ padding: '4px 0' }}>
                <span className="badge badge-muted">{h.role || 'client'}</span> {h.content}
              </div>
            ))}
          </div>
        </div>

        {selected.similar && selected.similar.length > 0 && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="card-header"><span className="card-title">Похожие статьи</span></div>
            {selected.similar.map(s => (
              <div key={s.article_id} className="data-row"><span className="data-label">{s.title}</span></div>
            ))}
          </div>
        )}

        <div className="card">
          <div className="card-header"><span className="card-title">Черновик (редактируемый)</span></div>
          <div className="input-group">
            <label className="input-label">Заголовок</label>
            <input className="input" value={form.title} onChange={e => update('title', e.target.value)} data-testid="sug-title" />
          </div>
          <div className="input-group">
            <label className="input-label">Категория</label>
            <input className="input" value={form.category} onChange={e => update('category', e.target.value)} data-testid="sug-category" />
          </div>
          <div className="input-group">
            <label className="input-label">Теги (через запятую)</label>
            <input className="input" value={form.tags} onChange={e => update('tags', e.target.value)} />
          </div>
          <div className="input-group">
            <label className="input-label">Паттерны вопросов (через запятую)</label>
            <input className="input" value={form.question_patterns} onChange={e => update('question_patterns', e.target.value)} />
          </div>
          <div className="input-group">
            <label className="input-label">Содержание</label>
            <textarea className="input" rows={8} value={form.content} onChange={e => update('content', e.target.value)} style={{ resize: 'vertical', minHeight: 120 }} data-testid="sug-content" />
          </div>

          {msg && <div style={{ marginTop: 8 }}>{msg}</div>}

          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button className="btn btn-primary" onClick={approve} disabled={saving || !form.title.trim() || !form.content.trim()} data-testid="sug-approve">
              <Check size={14} /> Добавить в базу
            </button>
            <button className="btn btn-danger" onClick={reject} disabled={saving} data-testid="sug-reject">
              <X size={14} /> Отклонить
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page" data-testid="suggestions-page">
      <h2 style={{ margin: 0, marginBottom: 12 }}>Черновики для базы знаний</h2>

      {suggestions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon"><Lightbulb size={22} /></div>
          <div className="empty-title">Нет черновиков</div>
          <div className="empty-text">После закрытия эскалированных тикетов AI предложит статьи для базы знаний.</div>
        </div>
      ) : (
        suggestions.map(s => (
          <div key={s.id} className="kb-article" onClick={() => openDetail(s.id)} data-testid={`suggestion-${s.id}`}>
            <div className="kb-article-title"><FileText size={14} /> {s.proposed?.title || 'Без названия'}</div>
            <div className="kb-article-meta">
              <span className="badge badge-muted"><Tag size={9} /> {s.proposed?.category || 'general'}</span>
              {s.created_at && <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>{new Date(s.created_at).toLocaleString('ru-RU')}</span>}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
