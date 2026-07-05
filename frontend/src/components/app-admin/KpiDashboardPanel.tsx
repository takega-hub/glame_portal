'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { AppAdminKpiDashboard } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

function formatNumber(value: number) {
  if (!Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('ru-RU').format(value);
}

export default function KpiDashboardPanel() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AppAdminKpiDashboard | null>(null);
  const [days, setDays] = useState('30');

  const daysNum = useMemo(() => {
    const n = Number(days);
    if (!Number.isFinite(n)) return 30;
    return Math.max(1, Math.min(365, Math.floor(n)));
  }, [days]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getAppAdminKpiDashboard({ days: daysNum });
      setData(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки KPI');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const eventsTop = useMemo(() => {
    const entries = Object.entries(data?.events?.by_type || {});
    entries.sort((a, b) => (b[1] || 0) - (a[1] || 0));
    return entries.slice(0, 10);
  }, [data]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <div className="text-xs text-gray-500 dark:text-gray-400">Период (дней)</div>
          <Input value={days} onChange={(e) => setDays(e.target.value)} className="w-28" />
        </div>
        <Button onClick={load} disabled={loading}>
          Обновить
        </Button>
        {data?.period ? (
          <div className="ml-auto text-xs text-gray-500 dark:text-gray-400">
            {new Date(data.period.start).toLocaleString('ru-RU')} — {new Date(data.period.end).toLocaleString('ru-RU')}
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <div className="font-medium text-red-800">Ошибка</div>
          <div className="mt-1 text-sm text-red-700">{error}</div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>Выручка</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data ? `${formatNumber(data.sales.revenue)} ₽` : loading ? '…' : '—'}</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">По данным продаж (1С)</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Покупки</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data ? formatNumber(data.sales.orders) : loading ? '…' : '—'}</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">Количество записей продаж</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>События</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data ? formatNumber(data.events.total) : loading ? '…' : '—'}</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">Аналитика поведения</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Пользователи</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data ? formatNumber(data.users.total) : loading ? '…' : '—'}</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">Покупатели: {data ? formatNumber(data.users.customers) : '—'}</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Топ событий</CardTitle>
        </CardHeader>
        <CardContent>
          {loading && !data ? <div className="text-sm text-gray-600 dark:text-gray-300">Загрузка…</div> : null}
          {!loading && data && eventsTop.length === 0 ? (
            <div className="text-sm text-gray-600 dark:text-gray-300">Нет данных</div>
          ) : null}
          {eventsTop.length > 0 ? (
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {eventsTop.map(([k, v]) => (
                <div key={k} className="flex items-center justify-between rounded-md border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-800 dark:bg-gray-950">
                  <div className="font-medium text-gray-900 dark:text-gray-100">{k}</div>
                  <div className="text-gray-700 dark:text-gray-300">{formatNumber(v)}</div>
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

