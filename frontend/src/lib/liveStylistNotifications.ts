'use client';

export const LIVE_STYLIST_BROWSER_NOTIFICATIONS_KEY = 'glame-live-stylist-browser-notifications';
export const LIVE_STYLIST_SOUND_NOTIFICATIONS_KEY = 'glame-live-stylist-sound-notifications';
export const LIVE_STYLIST_VIBRATION_NOTIFICATIONS_KEY = 'glame-live-stylist-vibration-notifications';

function safeGet(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') return fallback;
  const value = window.localStorage.getItem(key);
  if (value === null) return fallback;
  return value === '1';
}

function safeSet(key: string, value: boolean) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(key, value ? '1' : '0');
}

export function getLiveStylistBrowserNotificationsEnabled() {
  return safeGet(LIVE_STYLIST_BROWSER_NOTIFICATIONS_KEY, false);
}

export function setLiveStylistBrowserNotificationsEnabled(value: boolean) {
  safeSet(LIVE_STYLIST_BROWSER_NOTIFICATIONS_KEY, value);
}

export function getLiveStylistSoundNotificationsEnabled() {
  return safeGet(LIVE_STYLIST_SOUND_NOTIFICATIONS_KEY, true);
}

export function setLiveStylistSoundNotificationsEnabled(value: boolean) {
  safeSet(LIVE_STYLIST_SOUND_NOTIFICATIONS_KEY, value);
}

export function getLiveStylistVibrationNotificationsEnabled() {
  return safeGet(LIVE_STYLIST_VIBRATION_NOTIFICATIONS_KEY, true);
}

export function setLiveStylistVibrationNotificationsEnabled(value: boolean) {
  safeSet(LIVE_STYLIST_VIBRATION_NOTIFICATIONS_KEY, value);
}

export function isLiveStylistVibrationSupported() {
  return typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function';
}

export function getBrowserNotificationPermission(): NotificationPermission | 'unsupported' {
  if (typeof window === 'undefined' || !('Notification' in window)) return 'unsupported';
  return Notification.permission;
}

export async function requestBrowserNotificationPermission(): Promise<NotificationPermission | 'unsupported'> {
  if (typeof window === 'undefined' || !('Notification' in window)) return 'unsupported';
  return window.Notification.requestPermission();
}

export function sendLiveStylistBrowserNotification(title: string, body: string, tag: string) {
  if (typeof window === 'undefined' || !('Notification' in window)) return;
  if (Notification.permission !== 'granted') return;
  const notification = new Notification(title, {
    body,
    tag,
  });
  notification.onclick = () => {
    window.focus();
    window.location.href = '/admin/live-stylist';
  };
}

export function playLiveStylistNotificationSound() {
  if (typeof window === 'undefined') return;
  const AudioContextCtor = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextCtor) return;
  const context = new AudioContextCtor();
  const gain = context.createGain();
  gain.connect(context.destination);

  const playBeep = (startAt: number, fromHz: number, toHz: number, peakGain: number) => {
    const oscillator = context.createOscillator();
    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(fromHz, startAt);
    oscillator.frequency.exponentialRampToValueAtTime(toHz, startAt + 0.16);
    gain.gain.setValueAtTime(0.0001, startAt);
    gain.gain.exponentialRampToValueAtTime(peakGain, startAt + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, startAt + 0.22);
    oscillator.connect(gain);
    oscillator.start(startAt);
    oscillator.stop(startAt + 0.24);
  };

  const start = context.currentTime;
  playBeep(start, 920, 700, 0.14);
  playBeep(start + 0.32, 1040, 760, 0.16);

  window.setTimeout(() => {
    context.close().catch(() => undefined);
  }, 900);
}

export function vibrateLiveStylistAlert() {
  if (!isLiveStylistVibrationSupported()) return;
  navigator.vibrate([220, 120, 320, 140, 220]);
}

export function buildLiveStylistAlertTitle(totalUnread: number, requested: number, attention: number) {
  if (requested > 0) return `(${requested}) Новый запрос стилисту`;
  if (attention > 0) return `(${attention}) Обращение требует внимания`;
  if (totalUnread > 0) return `(${totalUnread}) Новое сообщение покупателя`;
  return '';
}

export function hasLiveStylistPendingAlerts(totalUnread: number, requested: number, attention: number) {
  return totalUnread > 0 || requested > 0 || attention > 0;
}
