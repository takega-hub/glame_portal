'use client';

import { ReactNode, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { findSectionForPath } from '@/config/navigation';

export default function AccessGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, isAuthenticated } = useAuth();

  const isLogin = pathname === '/login';
  const section = findSectionForPath(pathname);
  const allowed = !section || Boolean(user?.allowed_sections?.includes(section.sectionId));

  useEffect(() => {
    if (loading || isLogin) return;
    if (!isAuthenticated) {
      router.replace('/login');
    }
  }, [loading, isLogin, isAuthenticated, router]);

  if (isLogin) return <>{children}</>;
  if (loading) return null;
  if (!isAuthenticated) return null;

  if (!allowed) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="max-w-md rounded-md border border-red-200 bg-white p-6 shadow-sm">
          <div className="text-lg font-semibold text-gray-900">Доступ закрыт</div>
          <div className="mt-2 text-sm text-gray-600">
            Этот раздел не включен для вашей роли. Обратитесь к администратору, чтобы изменить доступ.
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
