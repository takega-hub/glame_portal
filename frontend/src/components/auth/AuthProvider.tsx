'use client';

import { createContext, useCallback, useContext, useState, useEffect, ReactNode } from 'react';
import { adminAccess, RoleAccess } from '@/lib/api';
import { auth, User } from '@/lib/auth';

const ROLE_PREVIEW_KEY = 'glame_admin_role_preview';
const ACCOUNT_PREVIEW_KEY = 'glame_admin_account_preview';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
  rolePreview: RoleAccess | null;
  accountPreview: PreviewAccount | null;
  setRolePreview: (role: RoleAccess | null, account?: PreviewAccount | null) => void;
}

export interface PreviewAccount {
  id: string;
  email: string | null;
  full_name?: string | null;
  role: string | null;
  role_label?: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const applyRolePreview = (currentUser: User, preview: RoleAccess | null, account: PreviewAccount | null = null): User => {
  const actualRole = currentUser.actual_role || currentUser.role;
  if (!preview || actualRole !== 'admin') {
    return {
      ...currentUser,
      actual_role: actualRole,
      is_role_preview: false,
    };
  }

  return {
    ...currentUser,
    ...(account
      ? {
          id: account.id,
          email: account.email,
          full_name: account.full_name,
        }
      : {}),
    actual_role: actualRole,
    role: preview.role_key,
    role_label: account?.role_label || preview.role_label,
    allowed_sections: preview.section_ids,
    is_role_preview: true,
  };
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [actualUser, setActualUser] = useState<User | null>(null);
  const [rolePreview, setRolePreviewState] = useState<RoleAccess | null>(null);
  const [accountPreview, setAccountPreviewState] = useState<PreviewAccount | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    try {
      // Очищаем кэш перед загрузкой, чтобы получить свежие данные
      localStorage.removeItem('glame_user');
      const currentUser = await auth.getCurrentUser();

      if (currentUser?.is_customer) {
        auth.logout();
        localStorage.removeItem(ROLE_PREVIEW_KEY);
        localStorage.removeItem(ACCOUNT_PREVIEW_KEY);
        setUser(null);
        setActualUser(null);
        setRolePreviewState(null);
        setAccountPreviewState(null);
        throw new Error('Портал доступен только для сотрудников/администраторов');
      }

      if (!currentUser) {
        localStorage.removeItem(ROLE_PREVIEW_KEY);
        localStorage.removeItem(ACCOUNT_PREVIEW_KEY);
        setRolePreviewState(null);
        setAccountPreviewState(null);
        setUser(null);
        setActualUser(null);
        return;
      }

      setActualUser(currentUser);

      const actualRole = currentUser.role;
      if (actualRole !== 'admin') {
        localStorage.removeItem(ROLE_PREVIEW_KEY);
        localStorage.removeItem(ACCOUNT_PREVIEW_KEY);
        setRolePreviewState(null);
        setAccountPreviewState(null);
        setUser(applyRolePreview(currentUser, null));
        return;
      }

      const storedPreviewRole = localStorage.getItem(ROLE_PREVIEW_KEY);
      if (storedPreviewRole) {
        try {
          const roles = await adminAccess.getRoles();
          const preview = roles.find((role) => role.role_key === storedPreviewRole) || null;
          const storedAccountRaw = localStorage.getItem(ACCOUNT_PREVIEW_KEY);
          let account: PreviewAccount | null = null;
          if (storedAccountRaw) {
            try {
              account = JSON.parse(storedAccountRaw) as PreviewAccount;
            } catch {
              localStorage.removeItem(ACCOUNT_PREVIEW_KEY);
            }
          }
          setRolePreviewState(preview);
          setAccountPreviewState(account);
          setUser(applyRolePreview(currentUser, preview, account));
          console.log('User loaded:', preview ? applyRolePreview(currentUser, preview, account) : currentUser); // Для отладки
          return;
        } catch (previewError) {
          console.warn('Role preview was reset:', previewError);
          localStorage.removeItem(ROLE_PREVIEW_KEY);
          localStorage.removeItem(ACCOUNT_PREVIEW_KEY);
          setRolePreviewState(null);
          setAccountPreviewState(null);
        }
      }

      setUser(applyRolePreview(currentUser, null));
      console.log('User loaded:', currentUser); // Для отладки
    } catch (error) {
      console.error('Error loading user:', error);
      localStorage.removeItem(ROLE_PREVIEW_KEY);
      localStorage.removeItem(ACCOUNT_PREVIEW_KEY);
      setRolePreviewState(null);
      setAccountPreviewState(null);
      auth.logout();
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth.isAuthenticated()) {
      loadUser();
    } else {
      setLoading(false);
    }
  }, [loadUser]);

  const login = async (email: string, password: string) => {
    await auth.login(email, password);
    await loadUser();
  };

  const setRolePreview = (role: RoleAccess | null, account: PreviewAccount | null = null) => {
    if (!user || (user.actual_role || user.role) !== 'admin') return;

    if (role) {
      localStorage.setItem(ROLE_PREVIEW_KEY, role.role_key);
      if (account) localStorage.setItem(ACCOUNT_PREVIEW_KEY, JSON.stringify(account));
      else localStorage.removeItem(ACCOUNT_PREVIEW_KEY);
      setRolePreviewState(role);
      setAccountPreviewState(account);
      setUser((current) => {
        const baseUser = actualUser || current;
        return baseUser ? applyRolePreview(baseUser, role, account) : current;
      });
    } else {
      localStorage.removeItem(ROLE_PREVIEW_KEY);
      localStorage.removeItem(ACCOUNT_PREVIEW_KEY);
      setRolePreviewState(null);
      setAccountPreviewState(null);
      setUser((current) => {
        const baseUser = actualUser || current;
        return baseUser ? applyRolePreview(baseUser, null) : current;
      });
    }
  };

  const logout = () => {
    localStorage.removeItem(ROLE_PREVIEW_KEY);
    localStorage.removeItem(ACCOUNT_PREVIEW_KEY);
    auth.logout();
    setRolePreviewState(null);
    setAccountPreviewState(null);
    setUser(null);
    setActualUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        logout,
        isAuthenticated: !!user,
        rolePreview,
        accountPreview,
        setRolePreview,
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
