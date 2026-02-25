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

export const analytics = {
  /**
   * Трекинг события
   */
  async trackEvent(params: TrackEventParams): Promise<void> {
    try {
      await apiClient.post('/api/analytics/track', params);
    } catch (error) {
      console.error('Error tracking event:', error);
      // Не бросаем ошибку, чтобы не ломать UX
    }
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
  let sessionId = sessionStorage.getItem('analytics_session_id');
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    sessionStorage.setItem('analytics_session_id', sessionId);
  }
  return sessionId;
}

// Получаем user_id из localStorage (если есть аутентификация)
export function getUserId(): string | undefined {
  // TODO: Интегрировать с системой аутентификации
  return localStorage.getItem('user_id') || undefined;
}
