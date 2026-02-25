'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { auth, User } from '@/lib/auth';

const SKIP_APP_AUTH = typeof process !== 'undefined' && process.env.NEXT_PUBLIC_SKIP_APP_AUTH === 'true';

/** Пользователь «портал» при входе только через Basic Auth (без повторного логина в приложении) */
const PORTAL_FAKE_USER: User = {
  id: 'portal-admin',
  email: 'admin@portal',
  phone: null,
  persona: null,
  is_customer: false,
  loyalty_points: null,
  role: 'admin',
};

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  loginByCard: (cardNumber: string, code: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (SKIP_APP_AUTH) {
      setUser(PORTAL_FAKE_USER);
      setLoading(false);
      return;
    }
    // Проверяем, есть ли сохраненный токен
    if (auth.isAuthenticated()) {
      loadUser();
    } else {
      setLoading(false);
    }
  }, []);

  const loadUser = async () => {
    try {
      // Очищаем кэш перед загрузкой, чтобы получить свежие данные
      localStorage.removeItem('glame_user');
      const currentUser = await auth.getCurrentUser();
      setUser(currentUser);
      console.log('User loaded:', currentUser); // Для отладки
    } catch (error) {
      console.error('Error loading user:', error);
      auth.logout();
    } finally {
      setLoading(false);
    }
  };

  const login = async (email: string, password: string) => {
    await auth.login(email, password);
    await loadUser();
  };

  const register = async (email: string, password: string) => {
    await auth.register(email, password);
    // После регистрации автоматически логинимся
    await login(email, password);
  };

  const loginByCard = async (cardNumber: string, code: string) => {
    await auth.loginByCard(cardNumber, code);
    await loadUser();
  };

  const logout = () => {
    auth.logout();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        register,
        loginByCard,
        logout,
        isAuthenticated: !!user,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
