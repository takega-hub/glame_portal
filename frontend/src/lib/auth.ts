import { apiClient } from './api';

const TOKEN_KEY = 'glame_access_token';
const REFRESH_TOKEN_KEY = 'glame_refresh_token';
const USER_KEY = 'glame_user';

export interface User {
  id: string;
  email: string | null;
  phone: string | null;
  persona: string | null;
  is_customer: boolean;
  loyalty_points: number | null;
  role: string | null;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export const auth = {
  /**
   * Логин пользователя
   */
  async login(email: string, password: string): Promise<AuthTokens> {
    const formData = new FormData();
    formData.append('username', email);
    formData.append('password', password);
    
    const response = await apiClient.post<AuthTokens>('/api/auth/login', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    
    const tokens = response.data;
    this.setTokens(tokens);
    return tokens;
  },

  /**
   * Регистрация пользователя
   */
  async register(email: string, password: string): Promise<User> {
    const response = await apiClient.post<User>('/api/auth/register', {
      email,
      password,
    });
    
    return response.data;
  },

  /**
   * Выход из системы
   */
  logout(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },

  /**
   * Получение текущего токена
   */
  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },

  /**
   * Получение refresh token
   */
  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  },

  /**
   * Сохранение токенов
   */
  setTokens(tokens: AuthTokens): void {
    localStorage.setItem(TOKEN_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  },

  /**
   * Обновление access token
   */
  async refreshToken(): Promise<AuthTokens | null> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      return null;
    }

    try {
      const response = await apiClient.post<AuthTokens>('/api/auth/refresh', null, {
        params: { refresh_token: refreshToken },
      });
      
      const tokens = response.data;
      this.setTokens(tokens);
      return tokens;
    } catch (error) {
      console.error('Error refreshing token:', error);
      this.logout();
      return null;
    }
  },

  /**
   * Получение текущего пользователя
   */
  async getCurrentUser(): Promise<User | null> {
    try {
      // Всегда получаем свежие данные с сервера, чтобы получить актуальную роль
      const response = await apiClient.get<User>('/api/auth/me');
      const user = response.data;
      
      // Сохраняем в кэш только если получили данные
      if (user) {
        localStorage.setItem(USER_KEY, JSON.stringify(user));
      }
      
      return user;
    } catch (error) {
      console.error('Error getting current user:', error);
      // При ошибке очищаем кэш
      localStorage.removeItem(USER_KEY);
      return null;
    }
  },

  /**
   * Вход по номеру дисконтной карты
   */
  async loginByCard(cardNumber: string, code: string): Promise<AuthTokens> {
    const response = await apiClient.post<AuthTokens>('/api/auth/login-by-card', {
      card_number: cardNumber,
      code: code,
    });
    
    const tokens = response.data;
    this.setTokens(tokens);
    return tokens;
  },

  /**
   * Проверка существования дисконтной карты
   */
  async verifyCard(cardNumber: string): Promise<{ exists: boolean; card_number?: string; full_name?: string }> {
    const response = await apiClient.post('/api/auth/verify-card', {
      card_number: cardNumber,
    });
    return response.data;
  },

  /**
   * Запрос кода подтверждения
   */
  async requestCode(cardNumber: string): Promise<{ success: boolean; message: string }> {
    const response = await apiClient.post('/api/auth/request-code', {
      card_number: cardNumber,
    });
    return response.data;
  },

  /**
   * Проверка, авторизован ли пользователь
   */
  isAuthenticated(): boolean {
    return !!this.getToken();
  },
};
