import { apiClient } from './api';

export interface TrackEventParams {
  session_id: string;
  event_type: string;
  event_data?: Record<string, any>;
  user_id?: string;
  product_id?: string;
  look_id?: string;
  content_item_id?: string;
  channel?: string;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
}

function isUuid(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function uuidV4Fallback(): string {
  if (typeof crypto !== 'undefined' && 'getRandomValues' in crypto) {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  return '00000000-0000-4000-8000-000000000000';
}

function createUuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    try {
      return crypto.randomUUID();
    } catch {
      return uuidV4Fallback();
    }
  }
  return uuidV4Fallback();
}

function normalizeTrackEventParams(params: TrackEventParams): TrackEventParams {
  const session_id = isUuid(params.session_id) ? params.session_id : getSessionId();
  const normalized: TrackEventParams = {
    ...params,
    session_id,
    event_data: params.event_data ?? {},
  };

  if (normalized.user_id && !isUuid(normalized.user_id)) normalized.user_id = undefined;
  if (normalized.product_id && !isUuid(normalized.product_id)) normalized.product_id = undefined;
  if (normalized.look_id && !isUuid(normalized.look_id)) normalized.look_id = undefined;
  if (normalized.content_item_id && !isUuid(normalized.content_item_id)) normalized.content_item_id = undefined;

  return normalized;
}

const TRACK_QUEUE_MAX = 100;
const TRACK_FLUSH_DELAY_MS = 150;
let trackQueue: TrackEventParams[] = [];
let trackFlushTimer: ReturnType<typeof setTimeout> | null = null;
let trackFlushRunning = false;

function enqueueTrackEvent(params: TrackEventParams): void {
  trackQueue.push(normalizeTrackEventParams(params));
  if (trackQueue.length > TRACK_QUEUE_MAX) {
    trackQueue = trackQueue.slice(-TRACK_QUEUE_MAX);
  }

  if (!trackFlushTimer) {
    trackFlushTimer = setTimeout(() => {
      trackFlushTimer = null;
      void flushTrackQueue();
    }, TRACK_FLUSH_DELAY_MS);
  }
}

async function flushTrackQueue(): Promise<void> {
  if (trackFlushRunning || typeof window === 'undefined') return;
  trackFlushRunning = true;
  try {
    while (trackQueue.length > 0) {
      const event = trackQueue.shift();
      if (!event) continue;
      try {
        await apiClient.post('/api/analytics/track', event);
      } catch {
      }
    }
  } finally {
    trackFlushRunning = false;
    if (trackQueue.length > 0 && !trackFlushTimer) {
      trackFlushTimer = setTimeout(() => {
        trackFlushTimer = null;
        void flushTrackQueue();
      }, TRACK_FLUSH_DELAY_MS);
    }
  }
}

export const analytics = {
  /**
   * Трекинг события
   */
  async trackEvent(params: TrackEventParams): Promise<void> {
    if (typeof window === 'undefined') return;
    enqueueTrackEvent(params);
  },

  /**
   * Трекинг клика по товару
   */
  async trackProductClick(
    sessionId: string,
    productId: string,
    userId?: string,
    channel?: string
  ): Promise<void> {
    await this.trackEvent({
      session_id: sessionId,
      event_type: 'product_click',
      product_id: productId,
      user_id: userId,
      channel: channel || 'website',
      event_data: {
        timestamp: new Date().toISOString(),
      },
    });
  },

  /**
   * Трекинг просмотра образа
   */
  async trackLookView(
    sessionId: string,
    lookId: string,
    userId?: string,
    channel?: string
  ): Promise<void> {
    await this.trackEvent({
      session_id: sessionId,
      event_type: 'look_view',
      look_id: lookId,
      user_id: userId,
      channel: channel || 'website',
      event_data: {
        timestamp: new Date().toISOString(),
      },
    });
  },

  /**
   * Трекинг сообщения в чате
   */
  async trackChatMessage(
    sessionId: string,
    message: string,
    userId?: string,
    channel?: string
  ): Promise<void> {
    await this.trackEvent({
      session_id: sessionId,
      event_type: 'chat_message',
      user_id: userId,
      channel: channel || 'chat',
      event_data: {
        message: message.substring(0, 500), // Ограничиваем длину
        timestamp: new Date().toISOString(),
      },
    });
  },

  /**
   * Трекинг визита на страницу
   */
  async trackPageView(
    sessionId: string,
    pageUrl: string,
    userId?: string,
    referrer?: string
  ): Promise<void> {
    await this.trackEvent({
      session_id: sessionId,
      event_type: 'page_view',
      user_id: userId,
      channel: 'website',
      event_data: {
        page_url: pageUrl,
        referrer: referrer || document.referrer,
        timestamp: new Date().toISOString(),
      },
    });
  },
};

// Получаем или создаем session_id
export function getSessionId(): string {
  if (typeof window === 'undefined') return createUuid();
  let sessionId = sessionStorage.getItem('analytics_session_id');
  if (!isUuid(sessionId)) {
    sessionId = createUuid();
    sessionStorage.setItem('analytics_session_id', sessionId);
  }
  return sessionId;
}

// Получаем user_id из localStorage (если есть аутентификация)
export function getUserId(): string | undefined {
  // TODO: Интегрировать с системой аутентификации
  return localStorage.getItem('user_id') || undefined;
}
