'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuth } from '@/components/auth/AuthProvider';
import KpiDashboardPanel from '@/components/app-admin/KpiDashboardPanel';
import ContentAdminPanel from '@/components/app-admin/ContentAdminPanel';
import AppFeaturesPanel from '@/components/app-admin/AppFeaturesPanel';

function canViewKpi(role: string | null | undefined) {
  return role === 'admin' || role === 'ai_marketer';
}

function canManageContent(role: string | null | undefined) {
  return role === 'admin' || role === 'content_manager' || role === 'ai_marketer';
}

export default function AppAdminPage() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-sm text-gray-600 dark:text-gray-300">Загрузка...</div>
      </div>
    );
  }

  const role = user?.role ?? null;
  const allowed = role === 'admin' || role === 'content_manager' || role === 'ai_marketer';
  if (!allowed) {
    return (
      <div className="p-6">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <div className="font-medium text-red-800">Недостаточно прав</div>
          <div className="mt-1 text-sm text-red-700">Требуется роль admin/content_manager/ai_marketer.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-admin-scope p-6 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50">Администрирование приложения</h1>
          <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">KPI и управление контентом мобильного приложения</div>
        </div>
        <div className="text-sm text-gray-600 dark:text-gray-300">
          {user?.email ? user.email : 'Без email'} • {role || 'no-role'}
        </div>
      </div>

      <Tabs defaultValue={canViewKpi(role) ? 'kpi' : 'content'}>
        <TabsList>
          <TabsTrigger value="kpi" disabled={!canViewKpi(role)}>
            Дашборд KPI
          </TabsTrigger>
          <TabsTrigger value="content" disabled={!canManageContent(role)}>
            Контент приложения
          </TabsTrigger>
          <TabsTrigger value="features" disabled={!canManageContent(role)}>
            Функции
          </TabsTrigger>
        </TabsList>

        <TabsContent value="kpi">
          {canViewKpi(role) ? <KpiDashboardPanel /> : null}
        </TabsContent>
        <TabsContent value="content">
          {canManageContent(role) ? <ContentAdminPanel role={role} /> : null}
        </TabsContent>
        <TabsContent value="features">
          {canManageContent(role) ? <AppFeaturesPanel /> : null}
        </TabsContent>
      </Tabs>
    </div>
  );
}
