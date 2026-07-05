'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api, type PersonalTrainingSummaryResponse, type SellerKpiRow, type SellerKpiSnapshot, type SellerShift } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

const currentMonth = new Date().toISOString().slice(0, 7);

function formatMoney(value?: number | null) {
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value || 0);
}

function formatNumber(value?: number | null, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(value);
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)}%`;
}

function normalizeText(value?: string | null) {
  return (value || '').trim().toLowerCase();
}

function sameSeller(left?: string | null, right?: string | null) {
  const a = normalizeText(left);
  const b = normalizeText(right);
  return Boolean(a && b && (a === b || a.includes(b) || b.includes(a)));
}

function sellerLabel(row?: Pick<SellerKpiRow, 'seller_name' | 'seller_external_id'> | null, fallback?: string | null) {
  return row?.seller_name || fallback || row?.seller_external_id || 'Продавец';
}

function completion(fact?: number | null, plan?: number | null) {
  if (!plan) return null;
  return ((fact || 0) / plan) * 100;
}

function statusClass(percent?: number | null) {
  if (percent === null || percent === undefined) return 'border-gray-200 bg-gray-50 text-gray-600';
  if (percent >= 100) return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (percent >= 75) return 'border-amber-200 bg-amber-50 text-amber-800';
  return 'border-red-200 bg-red-50 text-red-700';
}

function barColor(percent?: number | null) {
  if (percent === null || percent === undefined) return '#9ca3af';
  if (percent >= 100) return '#10b981';
  if (percent >= 75) return '#f59e0b';
  return '#ef4444';
}

function monthRange(month: string) {
  const [year, monthIndex] = month.split('-').map(Number);
  if (!year || !monthIndex) return { start: `${currentMonth}-01`, end: `${currentMonth}-31` };
  const start = new Date(year, monthIndex - 1, 1);
  const end = new Date(year, monthIndex, 0);
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
}

function recommendation(metric: string, percent?: number | null) {
  if (percent === null || percent === undefined) return 'Нет плана или факта — проверьте сопоставление продавца, смены и данные 1С.';
  if (percent >= 100) return 'План выполняется. Зафиксируйте удачные действия продавца и масштабируйте скрипты на команду.';
  if (metric === 'Выручка') return 'Главный фокус: увеличить комплектность и доводить примерку до выбора 2–3 изделий.';
  if (metric === 'Средний чек') return 'Разобрать чеки с высоким результатом: какие комплекты, аргументы ценности и premium-позиции сработали.';
  if (metric === 'Изделий/чек') return 'Тренировать естественную допродажу: серьги к колье, кольцо к серьгам, уход или готовый образ.';
  if (metric === 'Чеки') return 'Фокус на конверсии входящего трафика: быстрый контакт, повод покупки, примерка в первые минуты.';
  return 'Показатель ниже плана — сравнить смены с лучшим результатом и повторить рабочий сценарий.';
}

function monthProgress(month: string) {
  const [year, monthIndex] = month.split('-').map(Number);
  if (!year || !monthIndex) return { daysInMonth: 30, elapsedDays: 1, daysLeftIncludingToday: 30, isCurrentMonth: false };
  const daysInMonth = new Date(year, monthIndex, 0).getDate();
  const today = new Date();
  const isCurrentMonth = today.getFullYear() === year && today.getMonth() === monthIndex - 1;
  const isPastMonth = new Date(year, monthIndex, 0) < new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const elapsedDays = isCurrentMonth ? Math.min(Math.max(today.getDate(), 1), daysInMonth) : isPastMonth ? daysInMonth : 1;
  const daysLeftIncludingToday = isCurrentMonth ? Math.max(daysInMonth - today.getDate() + 1, 1) : isPastMonth ? 1 : daysInMonth;
  return { daysInMonth, elapsedDays, daysLeftIncludingToday, isCurrentMonth };
}

function buildDailyPlanRecommendation(dailyPlan: { remainingRevenue: number; requiredDailyRevenue: number; expectedRevenueToDate: number; revenueGapToDate: number; requiredDailyChecks: number | null; requiredDailyItems: number | null }) {
  if (dailyPlan.remainingRevenue <= 0) return 'План месяца уже закрыт. Удерживайте premium-сервис, собирайте комплекты и фиксируйте удачные сценарии для команды.';
  if (dailyPlan.revenueGapToDate > 0) {
    return `Сегодня важно добрать отставание ${formatMoney(dailyPlan.revenueGapToDate)} и выйти на темп ${formatMoney(dailyPlan.requiredDailyRevenue)} в день. Начните с клиентов с готовым поводом покупки, предлагайте 2–3 комплекта и закрывайте образ целиком.`;
  }
  return `Вы идёте в плановом темпе. Чтобы закрыть месяц, держите ориентир ${formatMoney(dailyPlan.requiredDailyRevenue)} в день${dailyPlan.requiredDailyChecks ? ` и около ${formatNumber(dailyPlan.requiredDailyChecks, 1)} чеков` : ''}. Усильте средний чек через комплекты и premium-позиции.`;
}

const weekDays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

function formatShiftTime(shift: SellerShift) {
  return `${shift.starts_at || '—'}–${shift.ends_at || '—'}`;
}

export default function SellerPersonalKpiPage() {
  const { user, accountPreview } = useAuth();
  const searchParams = useSearchParams();
  const [month, setMonth] = useState(searchParams.get('month') || currentMonth);
  const storeName = searchParams.get('store_name') || '';
  const sellerExternalId = searchParams.get('seller_external_id') || '';
  const sellerNameParam = searchParams.get('seller_name') || '';
  const isSelfSellerPage = user?.role === 'seller' && !sellerExternalId && !sellerNameParam;
  const previewNeedsAccount = Boolean(user?.is_role_preview && user?.role === 'seller' && !accountPreview && !sellerNameParam && !sellerExternalId);
  const selfName = accountPreview?.full_name || user?.full_name || user?.email || '';
  const canUseSelfFallback = isSelfSellerPage && !user?.is_role_preview;

  const [seller, setSeller] = useState<SellerKpiRow | null>(null);
  const [storeSellers, setStoreSellers] = useState<SellerKpiRow[]>([]);
  const [shifts, setShifts] = useState<SellerShift[]>([]);
  const [snapshots, setSnapshots] = useState<SellerKpiSnapshot[]>([]);
  const [trainingSummary, setTrainingSummary] = useState<PersonalTrainingSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      if (previewNeedsAccount) {
        setSeller(null);
        setStoreSellers([]);
        setShifts([]);
        setSnapshots([]);
        setTrainingSummary(null);
        setError(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const range = monthRange(month);
        const [kpi, shiftResponse, snapshotResponse] = await Promise.all([
          api.getSellerKpi({ month, ...(storeName ? { store_name: storeName } : {}) }),
          api.getSellerShifts({ start_date: range.start, end_date: range.end, ...(storeName ? { store_name: storeName } : {}) }),
          api.getSellerKpiSnapshots({ month, limit: 90 }),
        ]);
        const rows = kpi.sellers || [];
        const matched = rows.find((row) => sellerExternalId && row.seller_external_id === sellerExternalId)
          || rows.find((row) => sameSeller(row.seller_name, sellerNameParam) && (!storeName || row.store_name === storeName))
          || rows.find((row) => sameSeller(row.seller_name, sellerNameParam))
          || rows.find((row) => sameSeller(row.seller_name, selfName) && (!storeName || row.store_name === storeName))
          || rows.find((row) => sameSeller(row.seller_name, selfName))
          || (canUseSelfFallback && kpi.scope === 'self' ? rows[0] || null : null);
        setSeller(matched);
        setStoreSellers(rows);
        setShifts((shiftResponse.shifts || []).filter((shift) => {
          const byId = sellerExternalId && shift.seller_external_id === sellerExternalId;
          const byName = sameSeller(shift.seller_name, sellerNameParam || matched?.seller_name);
          return Boolean(byId || byName);
        }));
        setSnapshots(snapshotResponse.snapshots || []);
        if (matched) {
          const checks = matched.checks || 0;
          const matchedItems = matched.items_sold || 0;
          setTrainingSummary(await api.getSellerTrainingSummary({
            seller_external_id: matched.seller_external_id || sellerExternalId || null,
            seller_name: matched.seller_name || sellerNameParam || selfName || null,
            store_name: matched.store_name || storeName || null,
            kpi: {
              completion_percent: matched.completion_percent,
              avg_check: checks ? matched.revenue / checks : null,
              items_per_check: checks ? matchedItems / checks : null,
              revenue: matched.revenue,
              revenue_plan: matched.revenue_plan,
              checks: matched.checks,
            },
          }));
        } else {
          setTrainingSummary(null);
        }
      } catch (e: any) {
        setError(e.response?.data?.detail || e.message || 'Не удалось загрузить личный KPI продавца');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [accountPreview?.full_name, canUseSelfFallback, month, previewNeedsAccount, sellerExternalId, sellerNameParam, selfName, storeName]);

  const displayName = sellerLabel(seller, sellerNameParam);
  const shiftCount = shifts.length;
  const items = seller?.items_sold || 0;
  const checks = seller?.checks || 0;
  const avgCheck = checks ? seller!.revenue / checks : null;
  const avgItemPrice = items ? seller!.revenue / items : null;
  const itemsPerCheck = checks ? items / checks : null;
  const salesPerShift = shiftCount ? (seller?.revenue || 0) / shiftCount : null;

  const metrics = useMemo(() => {
    if (!seller) return [];
    return [
      { label: 'Выручка', fact: seller.revenue, plan: seller.revenue_plan, percent: seller.completion_percent, format: 'money' },
      { label: 'Чеки', fact: seller.checks, plan: seller.checks_plan, percent: completion(seller.checks, seller.checks_plan), format: 'number' },
      { label: 'Изделия', fact: seller.items_sold || 0, plan: seller.items_plan, percent: completion(seller.items_sold || 0, seller.items_plan), format: 'number' },
      { label: 'Средний чек', fact: avgCheck, plan: seller.avg_check_plan, percent: completion(avgCheck, seller.avg_check_plan), format: 'money' },
      { label: 'Стоимость изделия', fact: avgItemPrice, plan: seller.avg_item_price_plan, percent: completion(avgItemPrice, seller.avg_item_price_plan), format: 'money' },
      { label: 'Изделий/чек', fact: itemsPerCheck, plan: seller.items_per_check_plan, percent: completion(itemsPerCheck, seller.items_per_check_plan), format: 'decimal' },
      { label: 'Смены', fact: shiftCount, plan: seller.shifts_plan, percent: completion(shiftCount, seller.shifts_plan), format: 'number' },
      { label: 'Продажи/смена', fact: salesPerShift, plan: seller.avg_sales_per_shift_plan, percent: completion(salesPerShift, seller.avg_sales_per_shift_plan), format: 'money' },
    ];
  }, [avgCheck, avgItemPrice, itemsPerCheck, salesPerShift, seller, shiftCount]);

  const dailyPlan = useMemo(() => {
    if (!seller) return null;
    const { daysInMonth, elapsedDays, daysLeftIncludingToday, isCurrentMonth } = monthProgress(month);
    const revenuePlan = Number(seller.revenue_plan || 0);
    const checksPlan = seller.checks_plan === null || seller.checks_plan === undefined ? null : Number(seller.checks_plan || 0);
    const itemsPlan = seller.items_plan === null || seller.items_plan === undefined ? null : Number(seller.items_plan || 0);
    const expectedRevenueToDate = revenuePlan ? (revenuePlan / daysInMonth) * elapsedDays : 0;
    const expectedChecksToDate = checksPlan ? (checksPlan / daysInMonth) * elapsedDays : null;
    const expectedItemsToDate = itemsPlan ? (itemsPlan / daysInMonth) * elapsedDays : null;
    const remainingRevenue = Math.max(revenuePlan - Number(seller.revenue || 0), 0);
    const remainingChecks = checksPlan === null ? null : Math.max(checksPlan - Number(seller.checks || 0), 0);
    const remainingItems = itemsPlan === null ? null : Math.max(itemsPlan - Number(seller.items_sold || 0), 0);
    const requiredDailyRevenue = remainingRevenue / daysLeftIncludingToday;
    const requiredDailyChecks = remainingChecks === null ? null : remainingChecks / daysLeftIncludingToday;
    const requiredDailyItems = remainingItems === null ? null : remainingItems / daysLeftIncludingToday;
    const revenueGapToDate = Math.max(expectedRevenueToDate - Number(seller.revenue || 0), 0);
    const checksGapToDate = expectedChecksToDate === null ? null : Math.max(expectedChecksToDate - Number(seller.checks || 0), 0);
    const itemsGapToDate = expectedItemsToDate === null ? null : Math.max(expectedItemsToDate - Number(seller.items_sold || 0), 0);
    return {
      daysInMonth,
      elapsedDays,
      daysLeftIncludingToday,
      isCurrentMonth,
      expectedRevenueToDate,
      expectedChecksToDate,
      expectedItemsToDate,
      remainingRevenue,
      remainingChecks,
      remainingItems,
      requiredDailyRevenue,
      requiredDailyChecks,
      requiredDailyItems,
      revenueGapToDate,
      checksGapToDate,
      itemsGapToDate,
    };
  }, [month, seller]);

  const trendData = useMemo(() => snapshots
    .map((snapshot) => {
      const row = (snapshot.sellers || []).find((item) => {
        const byId = sellerExternalId && item.seller_external_id === sellerExternalId;
        const byName = sameSeller(item.seller_name, sellerNameParam || seller?.seller_name);
        return Boolean(byId || byName);
      });
      if (!row) return null;
      return {
        date: snapshot.snapshot_date.slice(5),
        Выручка: row.revenue,
        Выполнение: row.completion_percent || 0,
      };
    })
    .filter(Boolean) as Array<{ date: string; Выручка: number; Выполнение: number }>, [seller?.seller_name, sellerExternalId, sellerNameParam, snapshots]);

  const shiftCalendarDays = useMemo(() => {
    const [year, monthIndex] = month.split('-').map(Number);
    if (!year || !monthIndex) return [];

    const daysInMonth = new Date(year, monthIndex, 0).getDate();
    const firstWeekDay = new Date(year, monthIndex - 1, 1).getDay();
    const leadingEmptyDays = (firstWeekDay + 6) % 7;
    const shiftsByDate = shifts.reduce<Record<string, SellerShift[]>>((acc, shift) => {
      const key = shift.shift_date.slice(0, 10);
      acc[key] = [...(acc[key] || []), shift];
      return acc;
    }, {});

    return [
      ...Array.from({ length: leadingEmptyDays }, (_, index) => ({ key: `empty-${index}`, day: null, date: null, shifts: [] as SellerShift[] })),
      ...Array.from({ length: daysInMonth }, (_, index) => {
        const day = index + 1;
        const dateKey = `${year}-${String(monthIndex).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        return { key: dateKey, day, date: dateKey, shifts: shiftsByDate[dateKey] || [] };
      }),
    ];
  }, [month, shifts]);

  const nextShift = useMemo(() => shifts
    .slice()
    .sort((a, b) => a.shift_date.localeCompare(b.shift_date))
    .find((shift) => shift.shift_date >= new Date().toISOString().slice(0, 10)), [shifts]);

  const rankingPosition = useMemo(() => {
    if (!seller) return null;
    const sorted = [...storeSellers].sort((a, b) => Number(b.revenue || 0) - Number(a.revenue || 0));
    const index = sorted.findIndex((row) => (sellerExternalId && row.seller_external_id === sellerExternalId) || (row.seller_name === seller.seller_name && row.store_name === seller.store_name));
    return index >= 0 ? index + 1 : null;
  }, [seller, sellerExternalId, storeSellers]);

  if (loading) return <section className="p-8 text-gray-600">Загружаю личный KPI продавца…</section>;

  return (
    <section className="space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-700">Личный KPI продавца</p>
          <h1 className="mt-2 text-3xl font-semibold text-gray-950">{displayName}</h1>
          <p className="mt-2 text-sm text-gray-600">{seller?.store_name || storeName || 'Магазин не определён'} · месяц {month}</p>
          {seller?.plan_source && <p className="mt-1 text-sm text-gray-500">Источник личного плана: {seller.plan_source}</p>}
        </div>
        <div className="flex flex-wrap gap-3">
          <input type="month" value={month} onChange={(event) => setMonth(event.target.value)} className="rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium shadow-sm" />
          {user?.role !== 'seller' && (
            <>
              <Link href={`/profile/sellers?tab=kpi&store_name=${encodeURIComponent(seller?.store_name || storeName)}`} className="rounded-2xl bg-gray-950 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-gray-800">Магазин / план</Link>
            </>
          )}
        </div>
      </div>

      {error && <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
      {previewNeedsAccount && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Выберите конкретный аккаунт продавца в профиле администратора, чтобы проверить персональный KPI, магазин и смены. Один выбор роли «Продавец» показывает только права доступа, но не даёт платформе понять, чьи личные показатели открыть.
        </div>
      )}
      {!seller && !previewNeedsAccount && <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">Продавец не найден в KPI-строках. Проверьте seller_external_id, имя, магазин и сопоставление 1С/графика.</div>}

      {seller && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <p className="text-sm text-gray-500">Выручка / личный план</p>
              <p className="mt-2 text-3xl font-semibold text-gray-950">{formatMoney(seller.revenue)}</p>
              <p className="mt-1 text-sm text-gray-500">План: {formatMoney(seller.revenue_plan)}</p>
              <span className={`mt-4 inline-flex rounded-full border px-3 py-1 text-sm font-semibold ${statusClass(seller.completion_percent)}`}>{formatPercent(seller.completion_percent)}</span>
            </div>
            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <p className="text-sm text-gray-500">Чеки / изделия</p>
              <p className="mt-2 text-3xl font-semibold text-gray-950">{formatNumber(seller.checks)}</p>
              <p className="mt-1 text-sm text-gray-500">Изделий: {formatNumber(seller.items_sold || 0)} · Изделий/чек: {formatNumber(itemsPerCheck, 2)}</p>
              <p className="mt-4 text-sm font-medium text-gray-800">Средний чек: {formatMoney(avgCheck)}</p>
            </div>
            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <p className="text-sm text-gray-500">Смены и часы плана</p>
              <p className="mt-2 text-3xl font-semibold text-gray-950">{formatNumber(shiftCount)}</p>
              <p className="mt-1 text-sm text-gray-500">План смен: {formatNumber(seller.shifts_plan)} · часов: {formatNumber(seller.hours_plan, 1)}</p>
              <p className="mt-4 text-sm font-medium text-gray-800">Продажи/смена: {formatMoney(salesPerShift)}</p>
            </div>
            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <p className="text-sm text-gray-500">Позиция в магазине</p>
              <p className="mt-2 text-3xl font-semibold text-gray-950">{rankingPosition ? `#${rankingPosition}` : '—'}</p>
              <p className="mt-1 text-sm text-gray-500">Среди {storeSellers.length} KPI-строк магазина</p>
              <p className="mt-4 text-sm font-medium text-gray-800">Конверсия план: {formatPercent(seller.conversion_plan !== null && seller.conversion_plan !== undefined && Math.abs(seller.conversion_plan) <= 1 ? seller.conversion_plan * 100 : seller.conversion_plan)}</p>
            </div>
          </div>

          {trainingSummary && (
            <div className="rounded-3xl border border-blue-100 bg-gradient-to-br from-blue-50 via-white to-amber-50 p-5 shadow-sm">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.18em] text-blue-700">KPI + обучение</p>
                  <h2 className="mt-2 text-2xl font-semibold text-gray-950">Что развивать, чтобы выполнить личный план</h2>
                  <p className="mt-1 text-sm text-gray-600">Обучение связано с KPI как управленческая гипотеза: следующий учебный фокус проверяем через ближайшие смены и динамику продаж.</p>
                </div>
                <div className={`rounded-2xl px-4 py-3 text-sm font-semibold ${trainingSummary.summary.priority === 'high' ? 'bg-red-50 text-red-800' : 'bg-blue-50 text-blue-900'}`}>
                  {trainingSummary.summary.priority === 'high' ? 'Высокий приоритет' : 'Учебный фокус'}
                </div>
              </div>
              <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl bg-white p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Уровень</p>
                  <p className="mt-2 text-2xl font-semibold text-gray-950">{trainingSummary.summary.level || '—'}</p>
                  <p className="mt-1 text-sm text-gray-600">{trainingSummary.summary.completed_steps}/{trainingSummary.summary.total_steps} этапов</p>
                </div>
                <div className="rounded-2xl bg-white p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Прогресс обучения</p>
                  <p className="mt-2 text-2xl font-semibold text-blue-700">{trainingSummary.summary.progress_percent}%</p>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-100"><div className="h-full rounded-full bg-blue-600" style={{ width: `${Math.min(trainingSummary.summary.progress_percent, 100)}%` }} /></div>
                </div>
                <div className="rounded-2xl bg-white p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Аттестация</p>
                  <p className="mt-2 text-2xl font-semibold text-gray-950">{trainingSummary.summary.attestation_ready ? 'Готов' : 'Не готов'}</p>
                  <p className="mt-1 text-sm text-gray-600">допуск по прогрессу и компетенциям</p>
                </div>
                <div className="rounded-2xl bg-white p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Следующий шаг</p>
                  <p className="mt-2 text-lg font-semibold text-gray-950">{trainingSummary.summary.next_program_title || 'Программа не найдена'}</p>
                  <p className="mt-1 text-sm text-gray-600">{trainingSummary.summary.next_action?.label || 'Назначить этап обучения'}</p>
                </div>
              </div>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <div className="rounded-2xl bg-white/85 p-4">
                  <p className="text-sm font-semibold text-blue-900">Учебный фокус</p>
                  <p className="mt-2 text-sm leading-6 text-gray-800">{trainingSummary.summary.recommended_training_focus}</p>
                  {trainingSummary.summary.weakest_competencies.length ? <div className="mt-3 flex flex-wrap gap-2">{trainingSummary.summary.weakest_competencies.slice(0, 4).map((item) => <span key={item.code || item.label} className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-800">{item.label} · {item.percent}%</span>)}</div> : null}
                </div>
                <div className="rounded-2xl bg-white/85 p-4">
                  <p className="text-sm font-semibold text-blue-900">Рекомендация руководителю</p>
                  <p className="mt-2 text-sm leading-6 text-gray-800">{trainingSummary.summary.manager_recommendation}</p>
                  {trainingSummary.summary.kpi_focus.length ? <p className="mt-3 text-xs text-gray-500">KPI-фокус: {trainingSummary.summary.kpi_focus.join(', ')}</p> : null}
                </div>
              </div>
              {!trainingSummary.found && <p className="mt-3 rounded-2xl bg-amber-50 p-3 text-sm text-amber-800">Аккаунт обучения для этого продавца пока не сопоставлен. KPI виден, но обучение нужно связать с пользователем/1C ID.</p>}
            </div>
          )}

          {dailyPlan && (
            <div className="rounded-3xl border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-amber-50 p-5 shadow-sm">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-700">План на сегодня</p>
                  <h2 className="mt-2 text-2xl font-semibold text-gray-950">Что нужно сделать, чтобы выйти на месячный план</h2>
                  <p className="mt-1 text-sm text-gray-600">
                    Расчёт корректируется от факта: план месяца минус уже выполнено, делим на оставшиеся дни.
                  </p>
                </div>
                <div className="rounded-2xl border border-white/70 bg-white/80 px-4 py-3 text-sm text-gray-700 shadow-sm">
                  <p className="font-semibold text-gray-950">{dailyPlan.isCurrentMonth ? 'Сегодня' : 'Ориентир периода'}</p>
                  <p>{dailyPlan.elapsedDays} из {dailyPlan.daysInMonth} дней · осталось {dailyPlan.daysLeftIncludingToday}</p>
                </div>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-white/80 bg-white p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Нужно сегодня</p>
                  <p className="mt-2 text-3xl font-semibold text-emerald-700">{formatMoney(dailyPlan.requiredDailyRevenue)}</p>
                  <p className="mt-1 text-sm text-gray-600">средний дневной темп до конца месяца</p>
                </div>
                <div className="rounded-2xl border border-white/80 bg-white p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Плановый темп к сегодняшнему дню</p>
                  <p className="mt-2 text-2xl font-semibold text-gray-950">{formatMoney(dailyPlan.expectedRevenueToDate)}</p>
                  <p className="mt-1 text-sm text-gray-600">добрать по темпу: {formatMoney(dailyPlan.revenueGapToDate)}</p>
                </div>
                <div className="rounded-2xl border border-white/80 bg-white p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">До месячного плана осталось</p>
                  <p className="mt-2 text-2xl font-semibold text-gray-950">{formatMoney(dailyPlan.remainingRevenue)}</p>
                  <p className="mt-1 text-sm text-gray-600">из плана {formatMoney(seller.revenue_plan)}</p>
                </div>
                <div className="rounded-2xl border border-white/80 bg-white p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">Чеки и изделия на день</p>
                  <p className="mt-2 text-2xl font-semibold text-gray-950">{formatNumber(dailyPlan.requiredDailyChecks, 1)} чеков</p>
                  <p className="mt-1 text-sm text-gray-600">изделий: {formatNumber(dailyPlan.requiredDailyItems, 1)} · добрать изделий по темпу: {formatNumber(dailyPlan.itemsGapToDate, 1)}</p>
                </div>
              </div>

              <div className="mt-4 rounded-2xl border border-emerald-100 bg-white/85 p-4">
                <p className="text-sm font-semibold text-emerald-800">Совет AI-тренера на сегодня</p>
                <p className="mt-2 text-sm leading-6 text-gray-800">{buildDailyPlanRecommendation(dailyPlan)}</p>
              </div>
            </div>
          )}

          <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold text-gray-950">Личный план-факт по KPI</h2>
              <p className="mt-1 text-sm text-gray-500">Каждый показатель сравнивается с личным планом продавца.</p>
              <div className="mt-5 h-96">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={metrics} layout="vertical" margin={{ top: 10, right: 20, bottom: 10, left: 110 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis type="number" tickFormatter={(value) => `${value}%`} />
                    <YAxis type="category" dataKey="label" width={105} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(value: any) => formatPercent(Number(value))} />
                    <Bar dataKey="percent" radius={[0, 8, 8, 0]}>
                      {metrics.map((metric) => <Cell key={metric.label} fill={barColor(metric.percent)} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold text-gray-950">Анализ и рекомендации</h2>
              <div className="mt-4 space-y-3">
                {metrics.slice().sort((a, b) => Number(a.percent || 0) - Number(b.percent || 0)).slice(0, 5).map((metric) => (
                  <div key={metric.label} className={`rounded-2xl border p-4 ${statusClass(metric.percent)}`}>
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-semibold">{metric.label}</p>
                      <span className="rounded-full bg-white/70 px-3 py-1 text-xs font-semibold">{formatPercent(metric.percent)}</span>
                    </div>
                    <p className="mt-1 text-sm">Факт: {metric.format === 'money' ? formatMoney(metric.fact) : formatNumber(metric.fact, metric.format === 'decimal' ? 2 : 0)} · План: {metric.format === 'money' ? formatMoney(metric.plan) : formatNumber(metric.plan, metric.format === 'decimal' ? 2 : 0)}</p>
                    <p className="mt-2 text-sm">{recommendation(metric.label, metric.percent)}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold text-gray-950">Динамика личного выполнения</h2>
              <p className="mt-1 text-sm text-gray-500">История по daily snapshots. Если график пустой — live backend ещё не сохранял персональные snapshots.</p>
              <div className="mt-5 h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData} margin={{ top: 20, right: 20, bottom: 10, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                    <YAxis yAxisId="money" tickFormatter={(value) => `${Math.round(Number(value) / 1000)}к`} tick={{ fontSize: 12 }} />
                    <YAxis yAxisId="percent" orientation="right" tickFormatter={(value) => `${value}%`} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(value: any, name) => name === 'Выполнение' ? formatPercent(Number(value)) : formatMoney(Number(value))} />
                    <Line yAxisId="money" type="monotone" dataKey="Выручка" stroke="#10b981" strokeWidth={3} dot={{ r: 3 }} />
                    <Line yAxisId="percent" type="monotone" dataKey="Выполнение" stroke="#111827" strokeWidth={3} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-gray-950">Смены продавца</h2>
                  <p className="mt-1 text-sm text-gray-500">Календарь событий: рабочие дни отмечены сменами и временем.</p>
                </div>
                <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-right">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">События смен</p>
                  <p className="text-2xl font-semibold text-emerald-900">{shiftCount}</p>
                </div>
              </div>

              {shifts.length ? (
                <div className="mt-5 rounded-3xl border border-gray-100 bg-gray-50/70 p-3">
                  <div className="mb-3 flex items-center justify-between gap-3 px-1">
                    <div>
                      <p className="text-sm font-semibold text-gray-950">{month}</p>
                      <p className="text-xs text-gray-500">{seller?.store_name || storeName || 'Магазин не определён'}</p>
                    </div>
                    <div className="text-right text-xs text-gray-500">
                      <p>Ближайшая смена</p>
                      <p className="font-semibold text-gray-800">{nextShift ? `${nextShift.shift_date.slice(8, 10)} · ${formatShiftTime(nextShift)}` : '—'}</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-7 gap-1.5 text-center text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-400">
                    {weekDays.map((day) => <div key={day} className="py-1">{day}</div>)}
                  </div>
                  <div className="mt-1 grid grid-cols-7 gap-1.5">
                    {shiftCalendarDays.map((day) => {
                      const hasShift = day.shifts.length > 0;
                      return (
                        <div
                          key={day.key}
                          className={`min-h-[86px] rounded-2xl border p-2 text-left transition ${day.day ? hasShift ? 'border-emerald-200 bg-white shadow-sm ring-1 ring-emerald-100' : 'border-gray-100 bg-white/70 text-gray-400' : 'border-transparent bg-transparent'}`}
                        >
                          {day.day && (
                            <>
                              <div className="flex items-center justify-between gap-1">
                                <span className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${hasShift ? 'bg-emerald-600 text-white' : 'bg-gray-100 text-gray-500'}`}>{day.day}</span>
                                {hasShift && <span className="h-2 w-2 rounded-full bg-emerald-500" aria-label="Есть смена" />}
                              </div>
                              <div className="mt-2 space-y-1">
                                {day.shifts.map((shift) => (
                                  <div key={`${shift.id || shift.shift_date}-${shift.starts_at || 'start'}`} className="rounded-xl bg-emerald-50 px-2 py-1 text-[11px] font-medium text-emerald-900">
                                    <p>{formatShiftTime(shift)}</p>
                                    <p className="truncate text-emerald-700">{shift.store_name || storeName}</p>
                                  </div>
                                ))}
                              </div>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">Смены не найдены. Проверьте график и сопоставление имени продавца.</div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
