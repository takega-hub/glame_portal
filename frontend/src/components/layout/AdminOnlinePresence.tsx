'use client';

import { useEffect, useMemo, useState } from 'react';
import { Activity, ChevronDown, Users } from 'lucide-react';
import { usePathname } from 'next/navigation';
import { adminAccess, type OnlineStaffUser } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

function displayName(user: OnlineStaffUser) {
  return user.full_name || user.email || 'Сотрудник';
}

function pathLabel(path?: string | null) {
  if (!path || path === '/') return 'Главная';
  return path;
}

function seenLabel(secondsAgo: number) {
  if (secondsAgo <= 10) return 'сейчас';
  if (secondsAgo < 60) return `${secondsAgo} сек. назад`;
  return `${Math.floor(secondsAgo / 60)} мин. назад`;
}

export default function AdminOnlinePresence() {
  const pathname = usePathname();
  const { user, isAuthenticated } = useAuth();
  const [open, setOpen] = useState(false);
  const [users, setUsers] = useState<OnlineStaffUser[]>([]);
  const [loading, setLoading] = useState(false);
  const isAdmin = user?.role === 'admin' && !user?.is_role_preview;

  const onlineCount = users.length;
  const currentUserOnline = useMemo(
    () => users.some((item) => item.id === user?.id),
    [users, user?.id]
  );

  useEffect(() => {
    if (!isAuthenticated || !user || pathname === '/login') return;
    let disposed = false;

    const beat = async () => {
      if (disposed) return;
      try {
        await adminAccess.heartbeatPresence(pathname);
      } catch {
        // Presence is best-effort and must never interrupt user workflows.
      }
    };

    beat();
    const interval = window.setInterval(beat, 30000);
    window.addEventListener('focus', beat);
    document.addEventListener('visibilitychange', beat);
    return () => {
      disposed = true;
      window.clearInterval(interval);
      window.removeEventListener('focus', beat);
      document.removeEventListener('visibilitychange', beat);
    };
  }, [isAuthenticated, pathname, user]);

  useEffect(() => {
    if (!isAdmin) {
      setUsers([]);
      setOpen(false);
      return;
    }
    let disposed = false;

    const loadOnline = async () => {
      try {
        setLoading(true);
        const response = await adminAccess.getOnlinePresence({ window_seconds: 120 });
        if (!disposed) setUsers(response.users || []);
      } catch {
        if (!disposed) setUsers([]);
      } finally {
        if (!disposed) setLoading(false);
      }
    };

    loadOnline();
    const interval = window.setInterval(loadOnline, 15000);
    return () => {
      disposed = true;
      window.clearInterval(interval);
    };
  }, [isAdmin]);

  if (!isAdmin) return null;

  return (
    <div className="fixed right-4 top-4 z-[70] hidden md:block">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm hover:bg-emerald-50"
        title="Кто сейчас работает на платформе"
      >
        <span className={`h-2.5 w-2.5 rounded-full ${currentUserOnline || onlineCount > 0 ? 'bg-emerald-500' : 'bg-gray-300'}`} />
        <Users className="h-4 w-4 text-emerald-700" aria-hidden="true" />
        <span>Онлайн {loading && !onlineCount ? '...' : onlineCount}</span>
        <ChevronDown className={`h-4 w-4 text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>

      {open && (
        <div className="mt-2 w-80 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-xl">
          <div className="border-b border-gray-100 px-4 py-3">
            <div className="text-sm font-semibold text-gray-950">Сейчас на платформе</div>
            <div className="text-xs text-gray-500">Активность за последние 2 минуты</div>
          </div>
          <div className="max-h-96 overflow-y-auto p-2">
            {users.length ? users.map((item) => (
              <div key={item.id} className="rounded-md px-3 py-2 hover:bg-gray-50">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-gray-900">{displayName(item)}</div>
                    <div className="truncate text-xs text-gray-500">{item.role_label || item.role || 'роль не указана'}</div>
                  </div>
                  <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                    {seenLabel(item.seconds_ago)}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-1 text-xs text-gray-500">
                  <Activity className="h-3 w-3 shrink-0" aria-hidden="true" />
                  <span className="truncate">{pathLabel(item.current_path)}</span>
                </div>
              </div>
            )) : (
              <div className="px-3 py-6 text-center text-sm text-gray-500">
                Пока никого не видно онлайн.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
