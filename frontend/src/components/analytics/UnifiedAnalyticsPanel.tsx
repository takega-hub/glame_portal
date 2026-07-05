"use client";

import React, { useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchJson } from '@/lib/utils';
import { ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";

type Period = "day" | "yesterday" | "week" | "month" | "quarter" | "year" | "custom";
type Dimension = "store" | "channel";
type AppAnalyticsOverview = {
  total_events?: number;
  active_sessions?: number;
  active_users?: number;
  events_by_type?: Record<string, number>;
};
type AppAnalyticsFunnelStep = { key?: string; label: string; value: number; percent?: number };
type AppAnalyticsScreen = { screen: string; count: number };
type AppAnalyticsProduct = { id: string; name: string; count: number; event_counts?: Record<string, number> };
type AppAnalyticsAggregate = {
  overview: AppAnalyticsOverview;
  funnel: AppAnalyticsFunnelStep[];
  screens: AppAnalyticsScreen[];
  products: AppAnalyticsProduct[];
};

const SOURCE_COLORS = [
  "#ef4444", "#3b82f6", "#65a30d", "#8b5cf6", "#f59e0b", "#14b8a6",
  "#dc2626", "#2563eb", "#16a34a", "#7c3aed", "#d97706", "#0ea5e9",
];

const EXCLUDED_UNIFIED_CHART_STORE_IDS = new Set<string>([
  '5fe87060-39f8-458c-9b3e-5a6e4a54f2ec',
  'e011e44d-7945-4dc0-8080-b4eb555d01a1',
  'e1a2eace-fdc8-11ef-8c0c-fa163e4cc04e',
]);

const normalizeStoreName = (name: string) =>
  String(name || '')
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/[^a-zа-я0-9]+/g, ' ')
    .trim();

const storeAliasNames = (name: string) => {
  const normalized = normalizeStoreName(name);
  const aliases = new Set<string>([normalized]);
  if (normalized.includes('центрум') || normalized.includes('centrum')) aliases.add('centrum');
  if (normalized.includes('ялта') || normalized.includes('yalta')) aliases.add('yalta');
  if (normalized.includes('меганом') || normalized.includes('meganom')) aliases.add('meganom');
  return aliases;
};

const formatCurrency = (value: number) => `₽${Math.round(value || 0).toLocaleString('ru-RU')}`;
const formatNumber = (value: number) => Math.round(value || 0).toLocaleString('ru-RU');

export function UnifiedAnalyticsPanel() {
  const [unified, setUnified] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [onecAggregated, setOnecAggregated] = useState<any>(null);

  // Периоды и фильтры
  const [period, setPeriod] = useState<Period>("week");
  const [dimension, setDimension] = useState<Dimension>("store");
  const [start, setStart] = useState<string>("");
  const [end, setEnd] = useState<string>("");
  const [availableStores, setAvailableStores] = useState<Array<{ id: string; external_id?: string; name: string }>>([]);
  const [availableChannels, setAvailableChannels] = useState<string[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[] | null>(null); // null = все

  // Дневные данные: посещаемость офлайн по магазинам и сайт
  const [dailyVisits, setDailyVisits] = useState<Array<{
    date: string;
    visitors: number;
    stores: Array<{ name: string; visitors: number; sales?: number; revenue?: number }>;
  }>>([]);
  const [dailyWebsite, setDailyWebsite] = useState<Array<{ date: string; visits: number }>>([]);

  // Дневные продажи по источникам
  const [legend, setLegend] = useState<Array<{ id: string; name: string }>>([]);
  const [dailySources, setDailySources] = useState<Array<{ date: string; sources: Record<string, number> }>>([]);
  const [loadingDaily, setLoadingDaily] = useState(false);
  const [appAggregate, setAppAggregate] = useState<AppAnalyticsAggregate | null>(null);
  const [loadingAppEvents, setLoadingAppEvents] = useState(false);
  const [syncingSales, setSyncingSales] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const buildPeriodParams = () => {
    if (period === "custom" && start && end) {
      const s = new Date(start).toISOString();
      const e = new Date(end).toISOString();
      return `start_date=${encodeURIComponent(s)}&end_date=${encodeURIComponent(e)}`;
    }
    const p = period === "day" ? "today" : period === "yesterday" ? "yesterday" : period;
    return `period=${p}`;
  };

  const fetchUnified = async () => {
    try {
      setLoading(true);
      const { data: result } = await fetchJson<{ status?: string }>('/api/analytics/unified?' + buildPeriodParams());
      if (result.status === 'success') setUnified(result);
    } catch (err) {
      console.error('Error fetching unified analytics:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchOnecMetrics = async () => {
    try {
      const base = '/api/analytics/1c-sales/metrics?';
      const url = base + buildPeriodParams() + '&auto_sync=true';
      const { data } = await fetchJson<{ status?: string; aggregated?: any }>(url);
      if (data.status === 'success') {
        setOnecAggregated(data.aggregated || null);
      } else {
        setOnecAggregated(null);
      }
    } catch (e) {
      console.error('Error fetching 1C metrics:', e);
      setOnecAggregated(null);
    }
  };

  const fetchSourcesMeta = async () => {
    try {
      const { data } = await fetchJson<{ status?: string; stores: any[]; channels: string[] }>('/api/analytics/sources');
      const seenNames = new Set<string>();
      const stores = (data.stores || []).filter((s) => {
        const name = String(s?.name || "").trim();
        const sourceId = String(s?.external_id || s?.id || "").trim();

        if (!name) return false;
        if (sourceId && EXCLUDED_UNIFIED_CHART_STORE_IDS.has(sourceId)) return false;

        const uuidRegex = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
        const longHexRegex = /^[0-9a-fA-F]{16,}$/;
        const codeOnlyRegex = /^[A-Z0-9_]{8,}$/;
        if (uuidRegex.test(name) || longHexRegex.test(name) || codeOnlyRegex.test(name)) return false;

        const normalizedName = name.toLowerCase();
        if (seenNames.has(normalizedName)) return false;
        seenNames.add(normalizedName);

        return true;
      });
      setAvailableStores(stores);
      setAvailableChannels(data.channels || []);
    } catch (e) {
      console.error('Ошибка загрузки источников', e);
    }
  };

  const fetchDailyAux = async () => {
    try {
      setLoadingDaily(true);
      const q = buildPeriodParams();
      const [storesRes, siteRes] = await Promise.all([
        fetchJson<{
          status?: string;
          daily_data?: Array<{
            date: string;
            visitors: number;
            stores?: Array<{ name: string; visitors: number; sales?: number; revenue?: number }>;
          }>;
        }>(`/api/analytics/store-visits/daily?${q}`),
        fetchJson<{ status?: string; daily_data?: Array<{ date: string; visits: number }> }>(`/api/analytics/website-visits/daily?${q}`),
      ]);
      setDailyVisits(
        storesRes.data.daily_data?.map(d => ({
          date: d.date.split('T')[0],
          visitors: d.visitors ?? 0,
          stores: (d.stores || []).map(store => ({
            name: String(store.name || '').trim(),
            visitors: store.visitors ?? 0,
            sales: store.sales ?? 0,
            revenue: store.revenue ?? 0,
          })).filter(store => store.name),
        })) || []
      );
      setDailyWebsite(
        siteRes.data.daily_data?.map(d => ({ date: d.date.split('T')[0], visits: d.visits ?? 0 })) || []
      );
    } catch (e) {
      console.error('Error loading visits/site daily', e);
      setDailyVisits([]);
      setDailyWebsite([]);
    } finally {
      setLoadingDaily(false);
    }
  };

  const fetchDailySources = async () => {
    try {
      setLoadingDaily(true);
      const q = buildPeriodParams();
      const dim = dimension;
      const allIds = dim === "store"
        ? availableStores.map(s => s.external_id || s.id)
        : availableChannels;
      const sourcesList = (selectedSources ?? allIds).join(',');
      const url = `/api/analytics/1c-sales/daily-sources?${q}&dimension=${dim}&sources=${encodeURIComponent(sourcesList)}&auto_sync=true`;
      const { data } = await fetchJson<{
        status: string;
        legend: Array<{ id: string; name: string }>;
        daily: Array<{ date: string; sources: Record<string, number> }>;
      }>(url);
      if (data.status === 'success') {
        setLegend(data.legend || []);
        setDailySources(data.daily || []);
      } else {
        setLegend([]);
        setDailySources([]);
      }
    } catch (e) {
      console.error('Ошибка загрузки daily-sources', e);
      setLegend([]);
      setDailySources([]);
    } finally {
      setLoadingDaily(false);
    }
  };

  const syncSales = async () => {
    try {
      setSyncingSales(true);
      setSyncMessage(null);
      const { data } = await fetchJson<{
        status?: string;
        records_inserted?: number;
        records_updated?: number;
        inserted?: number;
        updated?: number;
        total_records?: number;
        message?: string;
      }>(`/api/analytics/1c-sales/sync?${buildPeriodParams()}&incremental=true`, {
        method: 'POST',
      });
      if (data.status === 'success') {
        const changed = Number(data.records_inserted ?? data.inserted ?? 0) + Number(data.records_updated ?? data.updated ?? 0);
        setSyncMessage(`Продажи обновлены. Новых/обновленных записей: ${changed}.`);
      } else {
        setSyncMessage(data.message || 'Синхронизация завершилась без статуса success.');
      }
      await Promise.all([
        fetchUnified(),
        fetchDailyAux(),
        fetchOnecMetrics(),
        fetchDailySources(),
        fetchSourcesMeta(),
      ]);
    } catch (e) {
      console.error('Ошибка синхронизации продаж из 1С', e);
      setSyncMessage('Не удалось синхронизировать продажи из 1С. Подробности в логах сервера.');
    } finally {
      setSyncingSales(false);
    }
  };

  const fetchAppAnalytics = async () => {
    try {
      setLoadingAppEvents(true);
      const params = new URLSearchParams({ channel: 'mobile_app' });
      if (unified?.period?.start) params.set('start_date', unified.period.start);
      if (unified?.period?.end) params.set('end_date', unified.period.end);
      const q = params.toString();
      const [overviewRes, funnelRes, screensRes, productsRes] = await Promise.all([
        fetchJson<AppAnalyticsOverview & { status?: string }>(`/api/analytics/app/overview?${q}`),
        fetchJson<{ status?: string; steps?: AppAnalyticsFunnelStep[] }>(`/api/analytics/app/funnel?${q}`),
        fetchJson<{ status?: string; screens?: AppAnalyticsScreen[] }>(`/api/analytics/app/screens?${q}&limit=6`),
        fetchJson<{ status?: string; products?: AppAnalyticsProduct[] }>(`/api/analytics/app/products?${q}&limit=5`),
      ]);
      setAppAggregate({
        overview: overviewRes.data || {},
        funnel: funnelRes.data.steps || [],
        screens: screensRes.data.screens || [],
        products: productsRes.data.products || [],
      });
    } catch (e) {
      console.error('Ошибка загрузки агрегированной аналитики приложения', e);
      setAppAggregate(null);
    } finally {
      setLoadingAppEvents(false);
    }
  };

  useEffect(() => {
    fetchSourcesMeta();
  }, []);

  useEffect(() => {
    fetchUnified();
    fetchDailyAux();
    fetchOnecMetrics();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, start, end]);

  useEffect(() => {
    // Не сбрасываем выбранные источники при смене периода
    fetchDailySources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, start, end, dimension, selectedSources, availableStores.length, availableChannels.length]);

  useEffect(() => {
    if (!unified?.period) return;
    fetchAppAnalytics();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unified?.period?.start, unified?.period?.end]);

  const activeStoreIds = useMemo(() => {
    if (dimension !== 'store') return null as Set<string> | null;
    const totals: Record<string, number> = {};
    for (const d of dailySources) {
      for (const [id, val] of Object.entries(d.sources || {})) {
        totals[id] = (totals[id] || 0) + (val || 0);
      }
    }
    const set = new Set<string>();
    for (const [id, sum] of Object.entries(totals)) {
      if ((sum || 0) > 0) set.add(id);
    }
    return set;
  }, [dailySources, dimension]);

  const allSourceIds = useMemo(() => {
    if (dimension === "store") {
      const raw = availableStores.map(s => s.external_id || s.id);
      const filteredByActive = activeStoreIds
        ? raw.filter(id => activeStoreIds.has(id))
        : raw;
      return filteredByActive;
    }
    return availableChannels.slice();
  }, [dimension, availableStores, availableChannels, activeStoreIds]);

  const chartSourceIds = useMemo(() => {
    const ids = selectedSources ?? allSourceIds;
    if (dimension !== 'store') return ids;
    return ids.filter((id) => !EXCLUDED_UNIFIED_CHART_STORE_IDS.has(id));
  }, [selectedSources, allSourceIds, dimension]);

  useEffect(() => {
    if (!selectedSources) return;
    const allowed = new Set(allSourceIds);
    const next = selectedSources.filter(id => allowed.has(id));
    if (next.length !== selectedSources.length) {
      setSelectedSources(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allSourceIds]);

  const selectedVisitorStoreNames = useMemo(() => {
    if (dimension !== 'store') return null as Set<string> | null;
    const selected = new Set(chartSourceIds);
    const result = new Set<string>();
    availableStores.forEach((store) => {
      const id = store.external_id || store.id;
      if (!selected.has(id)) return;
      storeAliasNames(store.name).forEach(alias => result.add(alias));
    });
    return result;
  }, [dimension, chartSourceIds, availableStores]);

  const visitorStoreSeries = useMemo(() => {
    if (dimension !== 'store') return [] as Array<{ key: string; name: string }>;
    const series = new Map<string, { key: string; name: string; visitors: number }>();
    dailyVisits.forEach((day) => {
      (day.stores || []).forEach((store) => {
        const normalized = normalizeStoreName(store.name);
        if (!normalized) return;
        if (selectedVisitorStoreNames && selectedVisitorStoreNames.size > 0 && !selectedVisitorStoreNames.has(normalized)) {
          const aliases = storeAliasNames(store.name);
          const matchesSelectedAlias = Array.from(aliases).some(alias => selectedVisitorStoreNames.has(alias));
          if (!matchesSelectedAlias) return;
        }
        const key = `store_visitors__${normalized.replace(/\s+/g, '_')}`;
        const prev = series.get(key) || { key, name: store.name, visitors: 0 };
        prev.visitors += store.visitors || 0;
        series.set(key, prev);
      });
    });
    return Array.from(series.values())
      .filter(seriesItem => seriesItem.visitors > 0)
      .map(({ key, name }) => ({ key, name }));
  }, [dailyVisits, dimension, selectedVisitorStoreNames]);

  const pivotedChartRows = useMemo(() => {
    // Список всех дат
    const dateSet = new Set<string>();
    dailySources.forEach(d => dateSet.add(d.date));
    dailyVisits.forEach(d => dateSet.add(d.date));
    dailyWebsite.forEach(d => dateSet.add(d.date));
    const dates = Array.from(dateSet).sort();

    // Построение строк
    return dates.map((date) => {
      const src = dailySources.find(d => d.date === date);
      const visits = dailyVisits.find(d => d.date === date);
      const site = dailyWebsite.find(d => d.date === date)?.visits ?? 0;
      const row: Record<string, number | string> = { date, store_visitors: visits?.visitors ?? 0, website_visits: site };
      const selected = new Set(chartSourceIds);
      (src?.sources ? Object.entries(src.sources) : []).forEach(([id, rev]) => {
        if (selected.has(id)) row[id] = rev;
      });

      (visits?.stores || []).forEach((store) => {
        const normalized = normalizeStoreName(store.name);
        if (!normalized) return;
        const key = `store_visitors__${normalized.replace(/\s+/g, '_')}`;
        if (!visitorStoreSeries.some(series => series.key === key)) return;
        row[key] = (Number(row[key] || 0) + (store.visitors || 0));
      });

      return row;
    });
  }, [dailySources, dailyVisits, dailyWebsite, chartSourceIds, visitorStoreSeries]);

  const filteredRevenueTotal = useMemo(() => {
    // Пересчет карточки "Продажи" по выбранным источникам
    const selected = new Set(chartSourceIds);
    let sum = 0;
    for (const d of dailySources) {
      for (const [id, val] of Object.entries(d.sources)) {
        if (selected.has(id)) sum += val || 0;
      }
    }
    return sum;
  }, [dailySources, chartSourceIds]);

  const offlineConversionPct = useMemo(() => {
    const visitors = Number(unified?.stores?.total_visitors ?? 0);
    const ordersFrom1C = Number(onecAggregated?.total_orders ?? 0);
    const salesCount = ordersFrom1C > 0 ? ordersFrom1C : Number(unified?.stores?.total_sales ?? 0);
    if (!visitors || visitors <= 0) return 0;
    const conversion = (salesCount / visitors) * 100;
    return Math.min(conversion, 100);
  }, [unified, onecAggregated]);

  const revenuePerIncoming = useMemo(() => {
    const visitors = Number(unified?.stores?.total_visitors ?? 0);
    if (!visitors || visitors <= 0) return 0;
    return filteredRevenueTotal / visitors;
  }, [filteredRevenueTotal, unified]);

  const storePerformance = useMemo(() => {
    const selected = new Set(chartSourceIds);
    const rows = new Map<string, {
      id: string;
      name: string;
      color: string;
      revenue: number;
      visitors: number;
      sales: number;
    }>();

    chartSourceIds.forEach((id, idx) => {
      const meta = legend.find(l => l.id === id);
      rows.set(id, {
        id,
        name: meta?.name || availableStores.find(s => (s.external_id || s.id) === id)?.name || id,
        color: SOURCE_COLORS[idx % SOURCE_COLORS.length],
        revenue: 0,
        visitors: 0,
        sales: 0,
      });
    });

    dailySources.forEach(day => {
      Object.entries(day.sources || {}).forEach(([id, value]) => {
        if (!selected.has(id)) return;
        const row = rows.get(id);
        if (row) row.revenue += value || 0;
      });
    });

    dailyVisits.forEach(day => {
      (day.stores || []).forEach(store => {
        const storeAliases = storeAliasNames(store.name);
        const matched = Array.from(rows.values()).find(row => {
          const meta = availableStores.find(s => (s.external_id || s.id) === row.id);
          const aliases = storeAliasNames(meta?.name || row.name);
          return Array.from(storeAliases).some(alias => aliases.has(alias));
        });
        if (matched) {
          matched.visitors += store.visitors || 0;
          matched.sales += Number(store.sales || 0);
        }
      });
    });

    return Array.from(rows.values())
      .filter(row => row.revenue > 0 || row.visitors > 0)
      .map(row => ({
        ...row,
        conversion: row.visitors > 0 && row.sales > 0 ? (row.sales / row.visitors) * 100 : null,
        revenuePerVisitor: row.visitors > 0 ? row.revenue / row.visitors : 0,
        revenueShare: filteredRevenueTotal > 0 ? (row.revenue / filteredRevenueTotal) * 100 : 0,
      }))
      .sort((a, b) => b.revenue - a.revenue);
  }, [chartSourceIds, legend, availableStores, dailySources, dailyVisits, filteredRevenueTotal]);

  const maxStoreRevenue = useMemo(
    () => Math.max(1, ...storePerformance.map(store => store.revenue)),
    [storePerformance]
  );

  const appAnalytics = useMemo(() => {
    const typeCounts = appAggregate?.overview.events_by_type || {};
    const funnel = appAggregate?.funnel?.length
      ? appAggregate.funnel
      : [
          { label: 'Открыли / смотрели экраны', value: 0, percent: 0 },
          { label: 'Интерес к товарам', value: 0, percent: 0 },
          { label: 'Просмотры образов', value: 0, percent: 0 },
          { label: 'Корзина / checkout', value: 0, percent: 0 },
          { label: 'Покупки', value: 0, percent: 0 },
        ];

    return {
      totalEvents: appAggregate?.overview.total_events || 0,
      sessions: appAggregate?.overview.active_sessions || 0,
      users: appAggregate?.overview.active_users || 0,
      typeCounts,
      topScreens: appAggregate?.screens || [],
      topProducts: appAggregate?.products || [],
      topLooksCount: typeCounts.look_view || 0,
      funnel,
    };
  }, [appAggregate]);

  const businessInsights = useMemo(() => {
    const insights: Array<{ title: string; text: string; tone: 'warning' | 'positive' | 'info' }> = [];
    storePerformance.forEach(store => {
      if (store.visitors >= 50 && store.revenuePerVisitor < 700) {
        insights.push({
          tone: 'warning',
          title: `${store.name}: высокий трафик, низкая выручка на входящего`,
          text: `${formatNumber(store.visitors)} посетителей и ${formatCurrency(store.revenuePerVisitor)} на посетителя — стоит проверить ассортимент, выкладку и работу продавцов.`,
        });
      }
      if (store.visitors > 0 && store.revenuePerVisitor >= 1500) {
        insights.push({
          tone: 'positive',
          title: `${store.name}: сильная монетизация трафика`,
          text: `${formatCurrency(store.revenuePerVisitor)} на посетителя — точку можно усиливать дополнительным трафиком.`,
        });
      }
    });
    if (appAnalytics.totalEvents > 0 && (appAnalytics.typeCounts.product_click || 0) / Math.max(1, appAnalytics.totalEvents) < 0.08) {
      insights.push({
        tone: 'warning',
        title: 'Приложение: мало переходов в товарные карточки',
        text: `${appAnalytics.typeCounts.product_click || 0} кликов по товарам на ${appAnalytics.totalEvents} событий — проверьте карточки в ленте, фильтры и призывы к действию.`,
      });
    }
    if (appAnalytics.topScreens[0]) {
      insights.push({
        tone: 'info',
        title: 'Самый популярный экран приложения',
        text: `${appAnalytics.topScreens[0].screen}: ${appAnalytics.topScreens[0].count} просмотров за выбранный период.`,
      });
    }
    return insights.slice(0, 5);
  }, [storePerformance, appAnalytics]);

  if (loading || !unified) return <div>Загрузка объединенной аналитики...</div>;

  const renderSourceChips = () => {
    const ids = allSourceIds;
    const selected = new Set(selectedSources ?? ids);
    const toggle = (id: string) => {
      const cur = new Set(selectedSources ?? ids);
      if (cur.has(id)) cur.delete(id); else cur.add(id);
      setSelectedSources(Array.from(cur));
    };
    return (
      <div className="flex flex-wrap gap-2">
        {ids.map((id, idx) => {
          const name = legend.find(l => l.id === id)?.name || id;
          const active = selected.has(id);
          const color = SOURCE_COLORS[idx % SOURCE_COLORS.length];
          return (
            <button
              key={id}
              onClick={() => toggle(id)}
              className={`px-2 py-1 rounded text-xs border flex items-center gap-2 ${active ? 'bg-white' : 'bg-gray-100'} `}
              title={id}
              style={{ borderColor: color, color: active ? color : '#4b5563' }}
            >
              <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
              {name}
            </button>
          );
        })}
      </div>
    );
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Объединенная аналитика</CardTitle>
            <CardDescription>Сводка по всем источникам данных</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={syncSales} disabled={syncingSales}>
              {syncingSales ? 'Синхронизация...' : 'Синхронизировать'}
            </Button>
            <Select value={period} onValueChange={(v) => setPeriod(v as Period)}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="Период" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="day">День</SelectItem>
                <SelectItem value="yesterday">Вчера</SelectItem>
                <SelectItem value="week">Неделя</SelectItem>
                <SelectItem value="month">Месяц</SelectItem>
                <SelectItem value="quarter">Квартал</SelectItem>
                <SelectItem value="year">Год</SelectItem>
                <SelectItem value="custom">Диапазон</SelectItem>
              </SelectContent>
            </Select>
            {period === "custom" && (
              <>
                <input
                  type="datetime-local"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                  max={end || undefined}
                  className="px-2 py-1 border rounded text-sm"
                />
                <span className="text-gray-500">—</span>
                <input
                  type="datetime-local"
                  value={end}
                  onChange={(e) => setEnd(e.target.value)}
                  min={start || undefined}
                  max={new Date().toISOString().slice(0,16)}
                  className="px-2 py-1 border rounded text-sm"
                />
                <Button size="sm" variant="outline" onClick={() => fetchUnified()}>
                  Применить
                </Button>
              </>
            )}
          </div>
        </div>
        {syncMessage && (
          <div className="mt-3 text-xs text-gray-600">{syncMessage}</div>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Select value={dimension} onValueChange={(v) => setDimension(v as Dimension)}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Разрез" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="store">По магазинам</SelectItem>
              <SelectItem value="channel">По каналам</SelectItem>
            </SelectContent>
          </Select>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setSelectedSources(allSourceIds)}
          >
            Выбрать все
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setSelectedSources([])}
          >
            Снять все
          </Button>
          <div className="text-xs text-gray-600">
            Источники:
          </div>
          {renderSourceChips()}
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <div className="bg-gradient-to-br from-orange-50 to-orange-100 p-6 rounded-lg">
            <h3 className="text-sm font-semibold text-orange-900 mb-2">Сайт</h3>
            <p className="text-2xl font-bold text-orange-900">
              {unified.website?.visits?.toLocaleString() || 0}
            </p>
            <p className="text-xs text-orange-700 mt-1">
              {unified.website?.visitors?.toLocaleString() || 0} посетителей
            </p>
            {unified.website?.bounce_rate !== undefined && (
              <p className="text-xs text-orange-700">
                Отказы: {unified.website.bounce_rate}%
              </p>
            )}
          </div>
          
          <div className="bg-gradient-to-br from-blue-50 to-blue-100 p-6 rounded-lg">
            <h3 className="text-sm font-semibold text-blue-900 mb-2">Социальные сети</h3>
            <p className="text-2xl font-bold text-blue-900">{unified.social_media.total_metrics}</p>
            <p className="text-xs text-blue-700 mt-1">
              Платформы: {unified.social_media.platforms.length > 0 ? unified.social_media.platforms.join(', ') : 'нет данных'}
            </p>
          </div>
          
          <div className="bg-gradient-to-br from-purple-50 to-purple-100 p-6 rounded-lg">
            <h3 className="text-sm font-semibold text-purple-900 mb-2">Офлайн магазины</h3>
            <p className="text-2xl font-bold text-purple-900">
              {unified.stores.total_visitors.toLocaleString()}
            </p>
            <p className="text-xs text-purple-700 mt-1">посетителей</p>
          </div>

          <div className="bg-gradient-to-br from-green-50 to-green-100 p-6 rounded-lg">
            <h3 className="text-sm font-semibold text-green-900 mb-2">Продажи</h3>
            <p className="text-2xl font-bold text-green-900">
              ₽{filteredRevenueTotal.toLocaleString('ru-RU')}
            </p>
            <p className="text-xs text-green-700 mt-1">по выбранным источникам</p>
          </div>

          <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 p-6 rounded-lg">
            <h3 className="text-sm font-semibold text-emerald-900 mb-2">Выручка на входящего</h3>
            <p className="text-2xl font-bold text-emerald-900">
              ₽{Math.round(revenuePerIncoming).toLocaleString('ru-RU')}
            </p>
            <p className="text-xs text-emerald-700 mt-1">на посетителя офлайна</p>
          </div>

          <div className="bg-gradient-to-br from-indigo-50 to-indigo-100 p-6 rounded-lg">
            <h3 className="text-sm font-semibold text-indigo-900 mb-2">Конверсия офлайн</h3>
            <p className="text-2xl font-bold text-indigo-900">
              {offlineConversionPct.toFixed(2)}%
            </p>
            <p className="text-xs text-indigo-700 mt-1">продажи / посетители</p>
          </div>
        </div>
        
        <div className="mt-6">
          <h3 className="text-base font-semibold text-gray-900 mb-2">Выручка и посещаемость (обзор)</h3>
          {loadingDaily ? (
            <div className="h-[300px] flex items-center justify-center text-gray-500">Загрузка...</div>
          ) : pivotedChartRows.length === 0 ? (
            <div className="h-[300px] flex items-center justify-center text-gray-500 border border-dashed border-gray-300 rounded-lg">
              Нет данных для графика
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={pivotedChartRows} margin={{ top: 8, right: 40, left: 8, bottom: 24 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tickFormatter={(v) => new Date(v).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })} angle={-45} textAnchor="end" height={56} />
                <YAxis yAxisId="left" orientation="left" tickFormatter={(v) => `₽${v >= 1000 ? (v / 1000) + 'k' : v}`} />
                <YAxis yAxisId="right" orientation="right" />
                <Tooltip
                  labelFormatter={(label) => new Date(label).toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}
                />
                <Legend />
                {/* Stacked bars for each selected source */}
                {chartSourceIds.map((id, idx) => (
                  <Bar
                    key={id}
                    yAxisId="left"
                    dataKey={id}
                    name={legend.find(l => l.id === id)?.name || id}
                    stackId="revenue"
                    fill={SOURCE_COLORS[idx % SOURCE_COLORS.length]}
                    radius={idx === 0 ? [4,4,0,0] : [0,0,0,0]}
                  />
                ))}
                {dimension === 'store' && visitorStoreSeries.length > 0 ? (
                  visitorStoreSeries.map((series, idx) => (
                    <Line
                      key={series.key}
                      yAxisId="right"
                      dataKey={series.key}
                      name={`Посетители: ${series.name}`}
                      stroke={SOURCE_COLORS[(idx + chartSourceIds.length) % SOURCE_COLORS.length]}
                      strokeWidth={2}
                      dot={{ r: 2 }}
                    />
                  ))
                ) : (
                  <Line yAxisId="right" dataKey="store_visitors" name="Магазины" stroke="#4f46e5" strokeWidth={2} dot={{ r: 2 }} />
                )}
                <Line yAxisId="right" dataKey="website_visits" name="Сайт" stroke="#10b981" strokeWidth={2} dot={{ r: 2 }} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="mt-6 grid grid-cols-1 xl:grid-cols-2 gap-6">
          <div className="p-5 rounded-xl border bg-white">
            <div className="flex items-start justify-between gap-3 mb-4">
              <div>
                <h3 className="text-base font-semibold text-gray-900">Выручка по магазинам</h3>
                <p className="text-sm text-gray-500">Доля выбранных магазинов в 1С-выручке за период</p>
              </div>
              <div className="text-right">
                <div className="text-xs text-gray-500">Всего</div>
                <div className="text-lg font-bold text-gray-900">{formatCurrency(filteredRevenueTotal)}</div>
              </div>
            </div>
            {storePerformance.length === 0 ? (
              <div className="h-32 flex items-center justify-center text-sm text-gray-500 border border-dashed rounded-lg">
                Нет данных по магазинам за выбранный период
              </div>
            ) : (
              <div className="space-y-4">
                {storePerformance.map(store => (
                  <div key={store.id}>
                    <div className="flex justify-between gap-3 text-sm mb-1">
                      <span className="font-medium text-gray-800 truncate">{store.name}</span>
                      <span className="text-gray-900 font-semibold">{formatCurrency(store.revenue)}</span>
                    </div>
                    <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${Math.max(3, (store.revenue / maxStoreRevenue) * 100)}%`, backgroundColor: store.color }}
                      />
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      {store.revenueShare.toFixed(1)}% выручки · {formatNumber(store.visitors)} посетителей · {formatCurrency(store.revenuePerVisitor)} / посетителя
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="p-5 rounded-xl border bg-white">
            <h3 className="text-base font-semibold text-gray-900">Эффективность магазинов</h3>
            <p className="text-sm text-gray-500 mb-4">Сравнение качества трафика: посетители, выручка и монетизация</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {storePerformance.map(store => (
                <div key={store.id} className="rounded-lg border p-4 bg-gray-50">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="w-3 h-3 rounded-full" style={{ backgroundColor: store.color }} />
                    <div className="font-semibold text-gray-900 truncate">{store.name}</div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <div className="text-gray-500">Выручка</div>
                      <div className="font-bold text-gray-900">{formatCurrency(store.revenue)}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Посетители</div>
                      <div className="font-bold text-gray-900">{formatNumber(store.visitors)}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">₽ / входящего</div>
                      <div className="font-bold text-gray-900">{formatCurrency(store.revenuePerVisitor)}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Конверсия</div>
                      <div className="font-bold text-gray-900">{store.conversion === null ? 'нет чеков' : `${store.conversion.toFixed(1)}%`}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-6 p-5 rounded-xl border bg-gradient-to-br from-slate-50 to-violet-50">
          <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
            <div>
              <h3 className="text-base font-semibold text-gray-900">Клиентское приложение</h3>
              <p className="text-sm text-gray-600">MVP-аналитика поведения: события, сессии, экраны и продуктовая воронка</p>
            </div>
            {loadingAppEvents && <span className="text-xs text-gray-500">Загрузка событий...</span>}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            <div className="bg-white/80 rounded-lg p-4 border">
              <div className="text-xs text-gray-500">События</div>
              <div className="text-2xl font-bold text-gray-900">{formatNumber(appAnalytics.totalEvents)}</div>
            </div>
            <div className="bg-white/80 rounded-lg p-4 border">
              <div className="text-xs text-gray-500">Сессии</div>
              <div className="text-2xl font-bold text-gray-900">{formatNumber(appAnalytics.sessions)}</div>
            </div>
            <div className="bg-white/80 rounded-lg p-4 border">
              <div className="text-xs text-gray-500">Клики по товарам</div>
              <div className="text-2xl font-bold text-gray-900">{formatNumber(appAnalytics.typeCounts.product_click || 0)}</div>
            </div>
            <div className="bg-white/80 rounded-lg p-4 border">
              <div className="text-xs text-gray-500">Просмотры образов</div>
              <div className="text-2xl font-bold text-gray-900">{formatNumber(appAnalytics.typeCounts.look_view || 0)}</div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <div className="bg-white/80 rounded-lg p-4 border">
              <h4 className="font-semibold text-gray-900 mb-3">Воронка приложения</h4>
              <div className="space-y-3">
                {appAnalytics.funnel.map(step => (
                  <div key={step.label}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-gray-700">{step.label}</span>
                      <span className="font-semibold">{formatNumber(step.value)} · {step.percent || 0}%</span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-violet-500 rounded-full" style={{ width: `${Math.min(100, step.percent || 0)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-white/80 rounded-lg p-4 border">
              <h4 className="font-semibold text-gray-900 mb-3">Топ экранов</h4>
              <div className="space-y-2">
                {appAnalytics.topScreens.length === 0 ? (
                  <div className="text-sm text-gray-500">Нет событий приложения за период</div>
                ) : appAnalytics.topScreens.map(screen => (
                  <div key={screen.screen} className="flex justify-between gap-3 text-sm">
                    <span className="truncate text-gray-700" title={screen.screen}>{screen.screen}</span>
                    <span className="font-semibold text-gray-900">{formatNumber(screen.count)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-white/80 rounded-lg p-4 border">
              <h4 className="font-semibold text-gray-900 mb-3">Интерес к товарам</h4>
              <div className="space-y-2">
                {appAnalytics.topProducts.length === 0 ? (
                  <div className="text-sm text-gray-500">Пока мало товарных событий</div>
                ) : appAnalytics.topProducts.map(product => (
                  <div key={product.id} className="text-sm">
                    <div className="flex justify-between gap-3">
                      <span className="truncate text-gray-700" title={product.name}>{product.name}</span>
                      <span className="font-semibold text-gray-900">{formatNumber(product.count)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6 p-5 rounded-xl border bg-white">
          <h3 className="text-base font-semibold text-gray-900 mb-1">Инсайты</h3>
          <p className="text-sm text-gray-500 mb-4">Автоматические подсказки по трафику, выручке и поведению в приложении</p>
          {businessInsights.length === 0 ? (
            <div className="text-sm text-gray-500">Пока недостаточно данных для уверенных инсайтов.</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {businessInsights.map((insight) => (
                <div
                  key={insight.title}
                  className={`rounded-lg p-4 border ${insight.tone === 'warning' ? 'bg-amber-50 border-amber-200' : insight.tone === 'positive' ? 'bg-emerald-50 border-emerald-200' : 'bg-blue-50 border-blue-200'}`}
                >
                  <div className="font-semibold text-gray-900 mb-1">{insight.title}</div>
                  <div className="text-sm text-gray-700">{insight.text}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 p-4 bg-gray-100 rounded-lg">
          <p className="text-sm text-gray-700">
            Период: {new Date(unified.period.start).toLocaleDateString()} - {new Date(unified.period.end).toLocaleDateString()}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
