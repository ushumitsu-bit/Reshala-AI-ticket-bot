/**
 * Мост к Telegram WebApp SDK.
 * Синхронизирует тему приложения с темой клиента Telegram,
 * разворачивает вьюпорт и отдаёт initData / данные пользователя.
 */

function applyColorScheme(scheme) {
  const isDark = scheme === 'dark';
  document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
}

export function initTelegram() {
  const tg = typeof window !== 'undefined' && window.Telegram && window.Telegram.WebApp
    ? window.Telegram.WebApp
    : null;

  // Вне Telegram (локальная разработка / браузер) — тема по системной
  if (!tg || !tg.initData) {
    const mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
    applyColorScheme(mq && mq.matches ? 'dark' : 'light');
    if (mq && mq.addEventListener) {
      mq.addEventListener('change', (e) => applyColorScheme(e.matches ? 'dark' : 'light'));
    }
    return { tg: null, user: null, initData: '', isTelegram: false };
  }

  try { tg.ready(); } catch (e) { /* noop */ }
  try { tg.expand(); } catch (e) { /* noop */ }
  try { tg.disableVerticalSwipes && tg.disableVerticalSwipes(); } catch (e) { /* noop */ }

  const syncTheme = () => {
    applyColorScheme(tg.colorScheme);
    try {
      tg.setHeaderColor && tg.setHeaderColor('secondary_bg_color');
      tg.setBackgroundColor && tg.setBackgroundColor('bg_color');
    } catch (e) { /* setHeaderColor кидает на старых клиентах — игнор */ }
  };

  syncTheme();
  try { tg.onEvent && tg.onEvent('themeChanged', syncTheme); } catch (e) { /* noop */ }

  return {
    tg,
    user: (tg.initDataUnsafe && tg.initDataUnsafe.user) || null,
    initData: tg.initData || '',
    isTelegram: true,
  };
}
