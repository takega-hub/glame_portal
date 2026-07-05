'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api, type SellerKpiDashboardResponse, type SellerKpiDashboardStore, type SellerKpiRow } from '@/lib/api';

const currentMonth = new Date().toISOString().slice(0, 7);

const METRIC_LABELS: Record<string, string> = {
  revenue: 'Выручка',
  items_count: 'Изделия',
  checks_count: 'Чеки',
  avg_check: 'Средний чек',
  avg_item_price: 'Стоимость изделия',
  items_per_check: 'Длина чека',
  shifts_count: 'Смены',
  avg_sales_per_shift: 'Продажи/смена',
  traffic: 'Трафик',
  conversion: 'Конверсия',
};

const HEATMAP_METRICS = ['revenue', 'checks_count', 'items_count', 'avg_check', 'avg_item_price', 'items_per_check', 'shifts_count', 'avg_sales_per_shift'];

function formatMoney(value?: number | null) {
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value || 0);
}

function formatNumber(value?: number | null, digits = 0) {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(value);
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined) return '—';
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)}%`;
}

function statusColor(percent?: number | null) {
  if (percent === null || percent === undefined) return 'bg-gray-100 text-gray-600 border-gray-200';
  if (percent >= 100) return 'bg-emerald-50 text-emerald-800 border-emerald-200';
  if (percent >= 85) return 'bg-amber-50 text-amber-800 border-amber-200';
  return 'bg-red-50 text-red-700 border-red-200';
}

function heatmapColor(percent?: number | null) {
  if (percent === null || percent === undefined) return 'bg-gray-50 text-gray-400';
  if (percent >= 110) return 'bg-emerald-700 text-white';
  if (percent >= 100) return 'bg-emerald-500 text-white';
  if (percent >= 85) return 'bg-amber-300 text-amber-950';
  if (percent >= 70) return 'bg-orange-300 text-orange-950';
  return 'bg-red-500 text-white';
}

function riskLabel(risk: SellerKpiDashboardStore['risk_level']) {
  if (risk === 'critical') return 'Критичный риск';
  if (risk === 'warning') return 'Есть риск';
  return 'Темп нормальный';
}

function planSourceLabel(source?: string | null) {
  if (source === 'target_metric_plan') return 'Админ-план KPI';
  if (source === 'seller_monthly_plans_sum') return 'Сумма планов продавцов';
  if (source === 'excel_formula_hours_share') return 'Excel/formula по часам';
  return source || 'Источник не указан';
}

function planStatusLabel(status?: string | null) {
  if (status === 'matched_confirmed') return 'сопоставлен';
  if (status === 'missing_or_unconfirmed') return 'нет/не подтверждён';
  return status || 'неизвестно';
}

function sellerDisplayName(row: SellerKpiRow) {
  return row.seller_name || 'Не сопоставлено';
}

function sellerPersonalHref(row: SellerKpiRow, month: string) {
  const params = new URLSearchParams();
  params.set('month', month);
  if (row.store_name) params.set('store_name', row.store_name);
  if (row.seller_external_id) params.set('seller_external_id', row.seller_external_id);
  if (row.seller_name) params.set('seller_name', row.seller_name);
  return `/profile/sellers/personal?${params.toString()}`;
}

function sellerAttentionText(row: SellerKpiRow) {
  const percent = row.completion_percent;
  if (percent === null || percent === undefined) return 'Нет процента выполнения — проверить план/сопоставление';
  if (percent < 50) return 'Критичная просадка: проверить смены, трафик, средний чек и допродажи';
  if (percent < 85) return 'Зона внимания: усилить сценарии продаж и контроль личного плана';
  if (percent < 100) return 'Близко к плану: добрать выручку до 100%';
  return 'План выполнен / темп нормальный';
}

function sellerRowTone(row: SellerKpiRow) {
  const percent = row.completion_percent;
  if (percent === null || percent === undefined) return 'bg-gray-50/70 hover:bg-gray-100';
  if (percent < 50) return 'bg-red-50/70 hover:bg-red-100';
  if (percent < 85) return 'bg-amber-50/80 hover:bg-amber-100';
  return 'bg-white hover:bg-emerald-50';
}

export default function SellerKpiMainDashboard() {
  const [month, setMonth] = useState(currentMonth);
  const [data, setData] = useState<SellerKpiDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.getSellerKpiDashboard({ month });
      setData(response);
    } catch (e: any) {
      if (e.response?.status === 404) {
        const fallback = await api.getSellerKpi({ month });
        const stores = (fallback.stores || []).map((store) => ({
          store_id: store.store_id,
          store_name: store.store_name,
          revenue: store.revenue,
          revenue_plan: store.revenue_plan,
          revenue_plan_source: store.revenue_plan ? 'seller_monthly_plans_sum' : null,
          revenue_plan_period: fallback.month?.slice(0, 7),
          revenue_plan_store: store.store_name,
          revenue_plan_matching_status: store.revenue_plan ? 'matched_confirmed' as const : 'missing_or_unconfirmed' as const,
          completion_percent: store.completion_percent,
          forecast_revenue: null,
          forecast_percent: null,
          checks: store.checks,
          items_sold: (fallback.sellers || []).filter((seller) => seller.store_name === store.store_name).reduce((sum, seller) => sum + Number(seller.items_sold || 0), 0),
          shifts_count: 0,
          avg_check: store.checks ? store.revenue / store.checks : null,
          avg_item_price: null,
          items_per_check: null,
          avg_sales_per_shift: null,
          sellers_count: (fallback.sellers || []).filter((seller) => seller.store_name === store.store_name).length,
          risk_level: (store.completion_percent || 0) < 75 ? 'critical' as const : (store.completion_percent || 0) < 100 ? 'warning' as const : 'ok' as const,
        }));
        setData({
          success: true,
          month: fallback.month,
          elapsed_days: 0,
          days_in_month: 0,
          totals: {
            revenue: fallback.totals.revenue,
            revenue_plan: fallback.totals.revenue_plan,
            completion_percent: fallback.totals.completion_percent,
            forecast_revenue: null,
            forecast_percent: null,
            checks: fallback.totals.checks,
            items_sold: (fallback.sellers || []).reduce((sum, seller) => sum + Number(seller.items_sold || 0), 0),
            shifts_count: 0,
            avg_check: fallback.totals.checks ? fallback.totals.revenue / fallback.totals.checks : null,
            avg_item_price: null,
            items_per_check: null,
            avg_sales_per_shift: null,
          },
          stores,
          sellers: fallback.sellers || [],
          metric_totals: {},
          metric_matrix: stores.map((store) => ({
            store_name: store.store_name,
            metrics: {
              revenue: { fact: store.revenue, plan: store.revenue_plan, percent: store.completion_percent },
              checks_count: { fact: store.checks, plan: null, percent: null },
              items_count: { fact: store.items_sold, plan: null, percent: null },
            },
          })),
          insights: [{ type: 'fallback', severity: 'warning', title: 'Dashboard endpoint ещё не развернут', text: 'Показана базовая сводка из текущего KPI API. После rebuild backend появятся прогнозы, heatmap по всем метрикам и качество данных.' }],
          data_quality: { unmatched_sellers: (fallback.sellers || []).filter((seller) => !seller.seller_name).length, duplicate_store_rows: 0, seller_field_status: fallback.seller_field_status },
        });
      } else {
        setError(e.response?.data?.detail || e.message || 'Не удалось загрузить главный KPI дашборд');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  const sellerRows = useMemo(() => [...(data?.sellers || [])]
    .sort((a, b) => Number(b.revenue || 0) - Number(a.revenue || 0))
    .map((seller, index) => ({
      ...seller,
      revenueRank: index + 1,
      revenueGap: Math.max(Number(seller.revenue_plan || 0) - Number(seller.revenue || 0), 0),
      avgCheckFact: Number(seller.checks || 0) > 0 ? Number(seller.revenue || 0) / Number(seller.checks || 0) : null,
      itemsPerCheckFact: Number(seller.checks || 0) > 0 ? Number(seller.items_sold || 0) / Number(seller.checks || 0) : null,
    })), [data?.sellers]);
  const attentionCount = useMemo(() => sellerRows.filter((seller) => seller.completion_percent === null || seller.completion_percent === undefined || seller.completion_percent < 85).length, [sellerRows]);
  const chartData = useMemo(() => (data?.stores || []).map((store) => ({
    name: store.store_name.replace('Ялта, ', 'Ялта '),
    Выручка: store.revenue,
    План: store.revenue_plan,
    Прогноз: store.forecast_revenue || 0,
    Выполнение: store.completion_percent || 0,
  })), [data?.stores]);

  if (loading && !data) {
    return <div className="p-8 text-gray-600">Загружаю главный KPI дашборд…</div>;
  }

  return (
    <section className="space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-700">GLAME KPI Control Center</p>
          <h1 className="mt-2 text-3xl font-semibold text-gray-950">Главный дашборд магазинов и продавцов</h1>
          <p className="mt-2 max-w-3xl text-sm text-gray-600">
            Сводка по всем магазинам: план-факт, прогноз месяца, сравнительный анализ, риски, продавцы и качество данных.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <input
            type="month"
            value={month}
            onChange={(event) => setMonth(event.target.value)}
            className="rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium shadow-sm"
          />
          <button
            type="button"
            onClick={loadDashboard}
            className="rounded-2xl bg-gray-950 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-gray-800"
          >
            Обновить
          </button>
          <Link href="/profile/sellers" className="rounded-2xl border border-gray-200 bg-white px-5 py-3 text-sm font-semibold text-gray-800 shadow-sm hover:bg-gray-50">
            Магазины / планы
          </Link>
        </div>
      </div>

      {error && <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <p className="text-sm text-gray-500">Выручка / план</p>
              <p className="mt-2 text-3xl font-semibold text-gray-950">{formatMoney(data.totals.revenue)}</p>
              <p className="mt-1 text-sm text-gray-500">План: {formatMoney(data.totals.revenue_plan)}</p>
              <span className={`mt-4 inline-flex rounded-full border px-3 py-1 text-sm font-semibold ${statusColor(data.totals.completion_percent)}`}>
                {formatPercent(data.totals.completion_percent)} выполнения
              </span>
            </div>
            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <p className="text-sm text-gray-500">Прогноз месяца</p>
              <p className="mt-2 text-3xl font-semibold text-gray-950">{formatMoney(data.totals.forecast_revenue)}</p>
              <p className="mt-1 text-sm text-gray-500">{formatPercent(data.totals.forecast_percent)} от плана при текущем темпе</p>
              <div className="mt-4 h-2 rounded-full bg-gray-100">
                <div className="h-2 rounded-full bg-emerald-500" style={{ width: `${Math.min(data.totals.forecast_percent || 0, 120)}%` }} />
              </div>
            </div>
            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <p className="text-sm text-gray-500">Чеки / изделия</p>
              <p className="mt-2 text-3xl font-semibold text-gray-950">{formatNumber(data.totals.checks)}</p>
              <p className="mt-1 text-sm text-gray-500">Изделий: {formatNumber(data.totals.items_sold)} · Длина чека: {formatNumber(data.totals.items_per_check, 2)}</p>
              <p className="mt-4 text-sm font-medium text-gray-800">Средний чек: {formatMoney(data.totals.avg_check)}</p>
            </div>
            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <p className="text-sm text-gray-500">Смены и эффективность</p>
              <p className="mt-2 text-3xl font-semibold text-gray-950">{formatNumber(data.totals.shifts_count)}</p>
              <p className="mt-1 text-sm text-gray-500">Продажи/смена: {formatMoney(data.totals.avg_sales_per_shift)}</p>
              <p className="mt-4 text-sm font-medium text-gray-800">Период: {data.elapsed_days}/{data.days_in_month} дней</p>
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.35fr_0.9fr]">
            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-xl font-semibold text-gray-950">Сравнение магазинов</h2>
                  <p className="text-sm text-gray-500">Выручка, план и прогноз по каждому магазину.</p>
                </div>
              </div>
              <div className="mt-4 h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData} margin={{ top: 20, right: 20, left: 0, bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis yAxisId="money" tickFormatter={(value) => `${Math.round(Number(value) / 1000)}к`} tick={{ fontSize: 12 }} />
                    <YAxis yAxisId="percent" orientation="right" tickFormatter={(value) => `${value}%`} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(value: any, name) => name === 'Выполнение' ? formatPercent(Number(value)) : formatMoney(Number(value))} />
                    <Bar yAxisId="money" dataKey="План" fill="#d1d5db" radius={[8, 8, 0, 0]} />
                    <Bar yAxisId="money" dataKey="Выручка" fill="#10b981" radius={[8, 8, 0, 0]} />
                    <Line yAxisId="percent" type="monotone" dataKey="Выполнение" stroke="#111827" strokeWidth={3} dot={{ r: 4 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold text-gray-950">Прогнозные риски</h2>
              <div className="mt-4 space-y-3">
                {data.insights.slice(0, 5).map((insight, index) => (
                  <div key={`${insight.type}-${index}`} className={`rounded-2xl border p-4 ${insight.severity === 'critical' ? 'border-red-200 bg-red-50' : insight.severity === 'warning' ? 'border-amber-200 bg-amber-50' : 'border-emerald-100 bg-emerald-50'}`}>
                    <p className="font-semibold text-gray-950">{insight.title}</p>
                    <p className="mt-1 text-sm text-gray-700">{insight.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            {data.stores.map((store) => (
              <div key={store.store_name} className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-950">{store.store_name}</h3>
                    <p className="text-sm text-gray-500">{store.sellers_count} продавцов · {store.shifts_count} смен</p>
                  </div>
                  <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusColor(store.forecast_percent)}`}>{riskLabel(store.risk_level)}</span>
                </div>
                <p className="mt-5 text-2xl font-semibold text-gray-950">{formatMoney(store.revenue)}</p>
                <p className="text-sm text-gray-500">План: {formatMoney(store.revenue_plan)} · {formatPercent(store.completion_percent)}</p>
                <div className={`mt-3 rounded-2xl border px-3 py-2 text-xs ${store.revenue_plan_matching_status === 'matched_confirmed' ? 'border-emerald-100 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-900'}`}>
                  <div className="font-semibold">Источник плана: {planSourceLabel(store.revenue_plan_source)}</div>
                  <div>Период: {store.revenue_plan_period || data.month.slice(0, 7)} · Магазин: {store.revenue_plan_store || store.store_name} · Статус: {planStatusLabel(store.revenue_plan_matching_status)}</div>
                </div>
                <div className="mt-4 h-2 rounded-full bg-gray-100">
                  <div className="h-2 rounded-full bg-emerald-500" style={{ width: `${Math.min(store.completion_percent || 0, 120)}%` }} />
                </div>
                <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-2xl bg-gray-50 p-3"><p className="text-gray-500">Прогноз</p><p className="font-semibold">{formatPercent(store.forecast_percent)}</p></div>
                  <div className="rounded-2xl bg-gray-50 p-3"><p className="text-gray-500">Средний чек</p><p className="font-semibold">{formatMoney(store.avg_check)}</p></div>
                  <div className="rounded-2xl bg-gray-50 p-3"><p className="text-gray-500">Изделий/чек</p><p className="font-semibold">{formatNumber(store.items_per_check, 2)}</p></div>
                  <div className="rounded-2xl bg-gray-50 p-3"><p className="text-gray-500">Продажи/смена</p><p className="font-semibold">{formatMoney(store.avg_sales_per_shift)}</p></div>
                </div>
                <Link href={`/profile/sellers?tab=kpi&store_name=${encodeURIComponent(store.store_name)}`} className="mt-5 inline-flex w-full justify-center rounded-2xl bg-gray-950 px-4 py-3 text-sm font-semibold text-white hover:bg-gray-800">
                  Открыть магазин и план
                </Link>
              </div>
            ))}
          </div>

          <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="text-xl font-semibold text-gray-950">Продавцы: рейтинг и зона внимания</h2>
                <p className="mt-1 text-sm text-gray-500">
                  Одна таблица вместо двух: рейтинг по выручке, личный план, выполнение, базовые KPI и причина внимания.
                </p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs font-semibold">
                <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-gray-700">Всего: {sellerRows.length}</span>
                <span className={`rounded-full border px-3 py-1 ${attentionCount ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'}`}>
                  Внимание: {attentionCount}
                </span>
              </div>
            </div>

            <div className="mt-5 overflow-x-auto">
              <table className="min-w-[1100px] w-full border-separate border-spacing-y-2 text-sm">
                <thead>
                  <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-3 py-2">#</th>
                    <th className="px-3 py-2">Продавец / магазин</th>
                    <th className="px-3 py-2 text-right">Факт</th>
                    <th className="px-3 py-2 text-right">План / остаток</th>
                    <th className="px-3 py-2 text-center">Выполнение</th>
                    <th className="px-3 py-2 text-right">Чеки</th>
                    <th className="px-3 py-2 text-right">Изделия</th>
                    <th className="px-3 py-2 text-right">Средний чек</th>
                    <th className="px-3 py-2">Управленческий фокус</th>
                    <th className="px-3 py-2 text-right">Действие</th>
                  </tr>
                </thead>
                <tbody>
                  {sellerRows.map((seller) => (
                    <tr key={`${seller.seller_external_id || seller.seller_name}-${seller.store_name}-${seller.revenueRank}`} className={`rounded-2xl transition ${sellerRowTone(seller)}`}>
                      <td className="rounded-l-2xl px-3 py-4 align-top font-semibold text-gray-500">{seller.revenueRank}</td>
                      <td className="px-3 py-4 align-top">
                        <Link href={sellerPersonalHref(seller, month)} className="font-semibold text-gray-950 hover:text-emerald-700">
                          {sellerDisplayName(seller)}
                        </Link>
                        <div className="mt-1 text-xs text-gray-500">{seller.store_name || 'Магазин не указан'}</div>
                        {seller.plan_source && <div className="mt-1 text-[11px] text-gray-400">План: {planSourceLabel(seller.plan_source)}</div>}
                      </td>
                      <td className="px-3 py-4 text-right align-top font-semibold text-gray-950">{formatMoney(seller.revenue)}</td>
                      <td className="px-3 py-4 text-right align-top">
                        <div className="font-medium text-gray-900">{formatMoney(seller.revenue_plan)}</div>
                        <div className="mt-1 text-xs text-gray-500">осталось {formatMoney(seller.revenueGap)}</div>
                      </td>
                      <td className="px-3 py-4 text-center align-top">
                        <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${statusColor(seller.completion_percent)}`}>
                          {formatPercent(seller.completion_percent)}
                        </span>
                        <div className="mt-2 h-1.5 rounded-full bg-gray-200">
                          <div
                            className={`h-1.5 rounded-full ${(seller.completion_percent || 0) >= 100 ? 'bg-emerald-500' : (seller.completion_percent || 0) >= 85 ? 'bg-amber-500' : 'bg-red-500'}`}
                            style={{ width: `${Math.min(Math.max(seller.completion_percent || 0, 0), 120)}%` }}
                          />
                        </div>
                      </td>
                      <td className="px-3 py-4 text-right align-top">{formatNumber(seller.checks)}</td>
                      <td className="px-3 py-4 text-right align-top">
                        <div>{formatNumber(seller.items_sold)}</div>
                        <div className="mt-1 text-xs text-gray-500">{formatNumber(seller.itemsPerCheckFact, 2)} / чек</div>
                      </td>
                      <td className="px-3 py-4 text-right align-top">{formatMoney(seller.avgCheckFact)}</td>
                      <td className="max-w-[260px] px-3 py-4 align-top text-xs leading-5 text-gray-700">{sellerAttentionText(seller)}</td>
                      <td className="rounded-r-2xl px-3 py-4 text-right align-top">
                        <Link href={sellerPersonalHref(seller, month)} className="font-semibold text-emerald-700 hover:text-emerald-800">
                          Открыть KPI →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
            <h2 className="text-xl font-semibold text-gray-950">KPI heatmap: магазины × показатели</h2>
            <p className="mt-1 text-sm text-gray-500">Цвет показывает выполнение плана: красный — просадка, зелёный — план выполнен.</p>
            <div className="mt-5 overflow-x-auto">
              <table className="min-w-full border-separate border-spacing-2 text-sm">
                <thead>
                  <tr>
                    <th className="text-left font-semibold text-gray-600">Магазин</th>
                    {HEATMAP_METRICS.map((metric) => <th key={metric} className="text-center font-semibold text-gray-600">{METRIC_LABELS[metric]}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data.metric_matrix.map((row) => (
                    <tr key={row.store_name}>
                      <td className="whitespace-nowrap rounded-xl bg-gray-50 px-3 py-3 font-semibold text-gray-950">{row.store_name}</td>
                      {HEATMAP_METRICS.map((metric) => {
                        const cell = row.metrics[metric];
                        return (
                          <td key={metric} className={`min-w-[110px] rounded-xl px-3 py-3 text-center font-semibold ${heatmapColor(cell?.percent)}`}>
                            <div>{formatPercent(cell?.percent)}</div>
                            <div className="text-xs opacity-80">{cell?.fact === null || cell?.fact === undefined ? '—' : metric.includes('avg') || metric === 'revenue' || metric === 'avg_sales_per_shift' ? formatMoney(cell.fact) : formatNumber(cell.fact, 2)}</div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-3xl border border-gray-100 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h2 className="text-xl font-semibold text-gray-950">Качество данных</h2>
                <p className="text-sm text-gray-500">Контроль, можно ли доверять управленческим выводам.</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className={`rounded-2xl border px-4 py-3 ${data.data_quality.unmatched_sellers ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>
                  <p className="text-xs uppercase tracking-wide">Без имени</p>
                  <p className="text-2xl font-semibold">{data.data_quality.unmatched_sellers}</p>
                </div>
                <div className={`rounded-2xl border px-4 py-3 ${data.data_quality.duplicate_store_rows ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>
                  <p className="text-xs uppercase tracking-wide">Дубли магазинов</p>
                  <p className="text-2xl font-semibold">{data.data_quality.duplicate_store_rows}</p>
                </div>
                <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 text-gray-700">
                  <p className="text-xs uppercase tracking-wide">Статус 1С seller field</p>
                  <p className="text-sm font-semibold">{data.data_quality.seller_field_status || '—'}</p>
                </div>
              </div>
              {data.data_quality.plan_warnings && data.data_quality.plan_warnings.length > 0 && (
                <div className="mt-4 space-y-2">
                  {data.data_quality.plan_warnings.map((warning) => (
                    <div key={`${warning.code}-${warning.store_name}-${warning.period}`} className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                      <span className="font-semibold">Data-warning по плану:</span> {warning.message}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
