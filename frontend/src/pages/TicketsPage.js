import React, { useState, useEffect, useCallback } from 'react';
import { Flame, User, BarChart3, Calendar, Link2, Smartphone, RotateCcw, RefreshCw, Trash2, Lock, Unlock, AlertTriangle, Clock, ChevronDown, ChevronUp, Send, X, Image } from 'lucide-react';
import ConfirmModal from '../components/ConfirmModal';

const API = process.env.REACT_APP_BACKEND_URL;

function formatBytes(b) {
  let n = Number(b) || 0;
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return n.toFixed(2) + ' ' + u[i];
}

function formatDate(str) {
  if (!str) return 'Не указано';
  try {
    const d = new Date(str.replace('Z', '+00:00'));
    if (isNaN(d.getTime())) return str;
    return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return str; }
}

const DataRow = ({ label, value, code }) => (
  <div className="data-row">
    <span className="data-label">{label}</span>
    <span className="data-value">{code ? <code>{value || '—'}</code> : (value || '—')}</span>
  </div>
);

// Статусы тикетов
const TICKET_STATUSES = {
  open: { emoji: '💬', label: 'Открыт', color: 'info' },
  escalated: { emoji: '🔥', label: 'Эскалация', color: 'warning' },
  suspicious: { emoji: '🚨', label: 'Подозрительный', color: 'danger' },
  closed: { emoji: '✅', label: 'Закрыт', color: 'success' },
};

export default function TicketsPage({ settings, initData }) {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [expandedTicket, setExpandedTicket] = useState(null);
  const [confirm, setConfirm] = useState({ open: false, action: null, data: null });
  const [actionMsg, setActionMsg] = useState('');
  const [filter, setFilter] = useState('all'); // all, escalated, suspicious

  const headers = { 'Content-Type': 'application/json' };
  if (initData) headers['X-Telegram-Init-Data'] = initData;

  const fetchTickets = useCallback(async () => {
    try {
      const reqHeaders = {};
      if (initData) reqHeaders['X-Telegram-Init-Data'] = initData;

      const r = await fetch(`${API}/api/tickets/active`, { headers: reqHeaders });
      const data = await r.json();
      setTickets(data.tickets || []);
    } catch (e) {
      console.error('Tickets fetch error:', e);
    } finally {
      setLoading(false);
    }
  }, [initData]);

  useEffect(() => {
    fetchTickets();
    const interval = setInterval(fetchTickets, 30000);
    return () => clearInterval(interval);
  }, [fetchTickets]);

  const sendReply = async (ticketId) => {
    if (!replyText.trim()) return;
    setSending(true);
    try {
      const r = await fetch(`${API}/api/tickets/${ticketId}/reply`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ message: replyText.trim(), manager_name: 'Менеджер' })
      });
      const data = await r.json();

      if (data.ok) {
        setReplyText('');
        setActionMsg('Ответ отправлен клиенту в Telegram');
        fetchTickets();
      } else {
        setActionMsg(data.error || 'Ошибка отправки');
      }
    } catch (e) {
      console.error('Reply error:', e);
      setActionMsg('Ошибка сети');
    } finally {
      setSending(false);
    }
  };

  const closeTicket = async (ticketId) => {
    try {
      await fetch(`${API}/api/tickets/${ticketId}/close`, { method: 'POST', headers });
      fetchTickets();
      setSelectedTicket(null);
      setActionMsg('Тикет закрыт');
    } catch (e) {
      console.error('Close ticket error:', e);
    }
  };

  const removeTicket = async (ticketId) => {
    try {
      await fetch(`${API}/api/tickets/${ticketId}/remove`, { method: 'POST', headers });
      fetchTickets();
      setSelectedTicket(null);
      setActionMsg('Тикет удалён');
    } catch (e) {
      console.error('Remove ticket error:', e);
    }
  };

  const showConfirm = (action, data, title, message, danger = false) => {
    setConfirm({ open: true, action, data, title, message, danger });
  };

  const handleConfirm = async () => {
    const { action, data } = confirm;
    setConfirm({ open: false });
    setActionMsg('');

    if (action === 'close-ticket') {
      await closeTicket(data.ticketId);
    } else if (action === 'remove-ticket') {
      await removeTicket(data.ticketId);
    } else {
      try {
        const r = await fetch(`${API}/api/actions/${action}`, {
          method: 'POST',
          headers,
          body: JSON.stringify(data)
        });
        const result = await r.json();
        setActionMsg(result.message || (result.ok ? 'Готово' : 'Ошибка'));
        if (result.ok) fetchTickets();
      } catch {
        setActionMsg('Ошибка сети');
      }
    }
  };

  // Фильтрация тикетов
  const filteredTickets = tickets.filter(t => {
    if (filter === 'all') return true;
    if (filter === 'escalated') return t.status === 'escalated';
    if (filter === 'suspicious') return t.status === 'suspicious';
    return true;
  });

  // Подсчёт по статусам
  const counts = {
    all: tickets.length,
    escalated: tickets.filter(t => t.status === 'escalated').length,
    suspicious: tickets.filter(t => t.status === 'suspicious').length,
  };

  const user = selectedTicket?.user_data?.user;
  const uuid = user?.id ?? '';
  const isDisabled = (user?.status || '').toUpperCase() === 'DISABLED';

  if (loading) {
    return (
      <div className="empty-state" data-testid="tickets-loading">
        <div className="loading-spinner" />
        <div style={{ marginTop: 12 }}>Загрузка тикетов...</div>
      </div>
    );
  }

  return (
    <div data-testid="tickets-page">
      {/* Фильтры */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-header">
          <span className="card-title">Активные тикеты</span>
        </div>
        <div className="filter-tabs">
          <button
            className={`filter-tab ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            Все <span className="filter-count">{counts.all}</span>
          </button>
          <button
            className={`filter-tab ${filter === 'escalated' ? 'active' : ''}`}
            onClick={() => setFilter('escalated')}
          >
            🔥 Эскалация <span className="filter-count">{counts.escalated}</span>
          </button>
          <button
            className={`filter-tab suspicious ${filter === 'suspicious' ? 'active' : ''}`}
            onClick={() => setFilter('suspicious')}
          >
            🚨 Подозрительные <span className="filter-count">{counts.suspicious}</span>
          </button>
        </div>
      </div>

      {actionMsg && <div className="alert alert-info" data-testid="action-message">{actionMsg}</div>}

      {filteredTickets.length === 0 ? (
        <div className="empty-state" data-testid="no-tickets">
          <div className="empty-icon"><Flame size={24} /></div>
          <div className="empty-title">Нет активных тикетов</div>
          <div className="empty-text">
            {filter === 'suspicious' ? 'Нет подозрительных пользователей' :
              filter === 'escalated' ? 'Нет эскалированных тикетов' :
                'Все вопросы решены AI-ассистентом'}
          </div>
        </div>
      ) : (
        <div className="tickets-list">
          {filteredTickets.map(ticket => {
            const status = TICKET_STATUSES[ticket.status] || TICKET_STATUSES.open;
            const isSuspicious = ticket.status === 'suspicious';

            return (
              <div
                key={ticket.id}
                className={`ticket-card ${selectedTicket?.id === ticket.id ? 'selected' : ''} ${isSuspicious ? 'suspicious' : ''}`}
                data-testid={`ticket-${ticket.id}`}
              >
                <div className="ticket-header" onClick={() => setSelectedTicket(selectedTicket?.id === ticket.id ? null : ticket)}>
                  <div className="ticket-user">
                    <div className={`user-avatar ${isSuspicious ? 'suspicious' : ''}`} style={{ width: 36, height: 36, fontSize: '0.85rem' }}>
                      {isSuspicious ? '🚨' : (ticket.client_name || 'U')[0].toUpperCase()}
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                        {ticket.client_name || `ID ${ticket.client_id}`}
                        {isSuspicious && (
                          <span className="badge badge-danger" style={{ fontSize: '0.65rem' }}>
                            НЕТ В СИСТЕМЕ
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                        @{ticket.client_username || '—'} • ID: {ticket.client_id}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className={`badge badge-${status.color}`}>
                      {status.emoji} {status.label}
                    </span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      <Clock size={12} style={{ marginRight: 3 }} />
                      {formatDate(ticket.escalated_at || ticket.created_at)}
                    </span>
                  </div>
                </div>

                {selectedTicket?.id === ticket.id && (
                  <div className="ticket-details animate-fade">
                    {/* Причина */}
                    <div className={`ticket-reason ${isSuspicious ? 'suspicious' : ''}`}>
                      {isSuspicious ? (
                        <>
                          <AlertTriangle size={16} style={{ marginRight: 6 }} />
                          <strong>ВНИМАНИЕ:</strong> Пользователь не найден в панели Remnawave. Возможно мошенник или использует чужую подписку.
                        </>
                      ) : (
                        <><strong>Причина эскалации:</strong> {ticket.reason || 'Пользователь запросил менеджера'}</>
                      )}
                    </div>

                    {/* Прикреплённые файлы (скриншоты, ссылки) */}
                    {ticket.attachments && ticket.attachments.length > 0 && (
                      <div className="ticket-attachments">
                        <div style={{ fontWeight: 600, fontSize: '0.82rem', marginBottom: 8, color: 'var(--text-secondary)' }}>
                          <Image size={14} style={{ marginRight: 4 }} /> Прикреплённые файлы:
                        </div>
                        {ticket.attachments.map((att, i) => (
                          <div key={i} className="attachment-item">
                            {att.type === 'photo' ? (
                              <a href={att.url} target="_blank" rel="noopener noreferrer">📷 Скриншот {i + 1}</a>
                            ) : att.type === 'subscription_link' ? (
                              <div><strong>Ссылка подписки:</strong> <code>{att.value}</code></div>
                            ) : (
                              <div>{att.value}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* История переписки */}
                    {(ticket.last_messages?.length > 0 || ticket.history?.length > 0) && (
                      <div className="ticket-messages">
                        <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: 10, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                          💬 Переписка ({(ticket.history || ticket.last_messages || []).length} сообщений)
                        </div>
                        <div className="messages-container">
                          {(ticket.history || ticket.last_messages || []).slice(-15).map((msg, i) => (
                            <div key={i} className={`chat-message ${msg.role}`}>
                              <div className="chat-message-header">
                                <span className="chat-message-role">
                                  {msg.role === 'user' ? '👤 Клиент' :
                                    msg.role === 'manager' ? `👨‍💼 ${msg.name || 'Менеджер'}` :
                                      '🤖 AI'}
                                </span>
                                {msg.timestamp && (
                                  <span className="chat-message-time">
                                    {formatDate(msg.timestamp)}
                                  </span>
                                )}
                              </div>
                              <div className="chat-message-text">{msg.content}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Данные пользователя (если найден) */}
                    {ticket.user_data?.user && !isSuspicious && (
                      <div className="ticket-user-data">
                        <div
                          className="ticket-accordion-header"
                          onClick={() => setExpandedTicket(expandedTicket === ticket.id ? null : ticket.id)}
                        >
                          <span>Данные пользователя</span>
                          {expandedTicket === ticket.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </div>
                        {expandedTicket === ticket.id && (
                          <div className="ticket-accordion-content animate-fade">
                            <DataRow label="UUID" value={user.vlessUuid || user.uuid} code />
                            <DataRow label="Username" value={user.username ? `@${user.username}` : '—'} />
                            <DataRow label="Статус" value={user.status} />
                            <DataRow label="Истекает" value={formatDate(user.expireAt)} />
                            {user.userTraffic && (
                              <DataRow label="Трафик" value={`${formatBytes(user.userTraffic.usedTrafficBytes || 0)} / ${user.trafficLimitBytes > 0 ? formatBytes(user.trafficLimitBytes) : '∞'}`} />
                            )}

                            <div className="actions-bar" style={{ marginTop: 12 }}>
                              <button className="btn btn-secondary btn-sm" onClick={() => showConfirm('reset-traffic', { userUuid: uuid }, 'Сброс трафика', 'Сбросить использованный трафик пользователя?')}>
                                <RotateCcw size={13} /> Сброс
                              </button>
                              <button className="btn btn-secondary btn-sm" onClick={() => showConfirm('revoke-subscription', { userUuid: uuid }, 'Перевыпуск подписки', 'Перевыпустить подписку пользователя?')}>
                                <RefreshCw size={13} /> Перевыпуск
                              </button>
                              <button className="btn btn-danger btn-sm" onClick={() => showConfirm('hwid-delete-all', { userUuid: uuid }, 'Удаление HWID', 'Удалить ВСЕ привязанные устройства?', true)}>
                                <Trash2 size={13} /> HWID
                              </button>
                              {isDisabled ? (
                                <button className="btn btn-secondary btn-sm" onClick={() => showConfirm('enable-user', { userUuid: uuid }, 'Разблокировка', 'Разблокировать пользователя?')}>
                                  <Unlock size={13} /> Разблокировать
                                </button>
                              ) : (
                                <button className="btn btn-danger btn-sm" onClick={() => showConfirm('disable-user', { userUuid: uuid }, 'Блокировка', 'Заблокировать пользователя?', true)}>
                                  <Lock size={13} /> Заблокировать
                                </button>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Reply Section */}
                    <div className="ticket-reply">
                      <input
                        className="input"
                        placeholder="Написать ответ клиенту..."
                        value={replyText}
                        onChange={e => setReplyText(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && sendReply(ticket.id)}
                        data-testid="ticket-reply-input"
                      />
                      <button
                        className="btn btn-primary"
                        onClick={() => sendReply(ticket.id)}
                        disabled={sending || !replyText.trim()}
                        data-testid="ticket-reply-send"
                      >
                        <Send size={14} />
                      </button>
                    </div>

                    {/* Действия с тикетом */}
                    <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                      {ticket.status !== 'closed' && (
                        <button
                          className="btn btn-secondary"
                          onClick={() => showConfirm('close-ticket', { ticketId: ticket.id }, 'Закрытие тикета', 'Закрыть этот тикет? Пользователь получит уведомление.')}
                          data-testid="close-ticket-btn"
                        >
                          ✅ Закрыть тикет
                        </button>
                      )}
                      {(isSuspicious || ticket.status === 'closed') && (
                        <button
                          className="btn btn-danger"
                          onClick={() => showConfirm('remove-ticket', { ticketId: ticket.id }, 'Удаление тикета', 'Полностью удалить этот тикет из списка?', true)}
                          data-testid="remove-ticket-btn"
                        >
                          <X size={14} /> Убрать тикет
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <ConfirmModal
        isOpen={confirm.open}
        title={confirm.title}
        message={confirm.message}
        danger={confirm.danger}
        onConfirm={handleConfirm}
        onCancel={() => setConfirm({ open: false })}
      />
    </div>
  );
}
