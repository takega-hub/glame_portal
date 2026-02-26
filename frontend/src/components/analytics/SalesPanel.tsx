"use client";

import React, { useEffect, useState, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw, Calendar } from "lucide-react";
import { Label } from "@/components/ui/label";
import { fetchJson } from '@/lib/utils';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ComposedChart, BarChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

type Period = "today" | "yesterday" | "week" | "month" | "quarter" | "year" | "custom";

interface SalesDetail {
  id: string;
  sale_date: string;
  product_name: string;
  product_article: string;
  product_category?: string;
  product_brand?: string;
  quantity: number;
  revenue: number;
  store_id?: string;
  store_name?: string;
  channel?: string;
}

type VisitorsByStore = Record<string, { visitor_count: number; store_name: string }>;

export function SalesPanel() {
  const [aggregated, setAggregated] = useState<any>(null);
  const [byStore, setByStore] = useState<any>(null);
  const [visitorsByStore, setVisitorsByStore] = useState<VisitorsByStore>({});
  const [stores, setStores] = useState<any[]>([]);
  const [salesDetails, setSalesDetails] = useState<SalesDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncingVisits, setSyncingVisits] = useState(false);
  const [syncResult, setSyncResult] = useState<any>(null);
  const [period, setPeriod] = useState<Period>("today");
  const [selectedStoreId, setSelectedStoreId] = useState<string>("all");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [chartSalesDaily, setChartSalesDaily] = useState<{ daily_data: Array<{ date: string; revenue: number; orders: number; items_sold: number }> } | null>(null);
  const [chartVisitsDaily, setChartVisitsDaily] = useState<{
    daily_data: Array<{
      date: string;
      visitors: number;
      stores?: Array<{ name: string; visitors: number }>;
    }>;
  } | null>(null);
  const [loadingCharts, setLoadingCharts] = useState(false);

  const fetchMetrics = async () => {
    try {
      setLoading(true);
      let url = '/api/analytics/1c-sales/metrics?auto_sync=true&';
      
      if (period === "custom") {
        if (startDate && endDate) {
          // Форматируем даты в ISO формат
          const startISO = new Date(startDate + 'T00:00:00').toISOString();
          const endISO = new Date(endDate + 'T23:59:59').toISOString();
          url += `start_date=${encodeURIComponent(startISO)}&end_date=${encodeURIComponent(endISO)}&`;
        } else {
          // Если даты не выбраны, используем последние 30 дней
          url += 'days=30&';
        }
      } else {
        url += `period=${period}&`;
      }
      
      // Добавляем фильтр по магазину
      if (selectedStoreId && selectedStoreId !== "all") {
        url += `store_id=${encodeURIComponent(selectedStoreId)}&`;
      }
      
      const { data } = await fetchJson<{ status?: string; aggregated?: any; by_store?: any; visitors_by_store?: VisitorsByStore }>(url);
      if (data.status === 'success') {
        setAggregated(data.aggregated);
        setByStore(data.by_store || {});
        setVisitorsByStore(data.visitors_by_store || {});
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const syncData = async () => {
    try {
      setSyncing(true);
      setSyncResult(null);
      let url = '/api/analytics/1c-sales/sync?incremental=true&';
      
      if (period === "custom") {
        if (startDate && endDate) {
          // Форматируем даты в ISO формат
          const startISO = new Date(startDate + 'T00:00:00').toISOString();
          const endISO = new Date(endDate + 'T23:59:59').toISOString();
          url += `start_date=${encodeURIComponent(startISO)}&end_date=${encodeURIComponent(endISO)}`;
        } else {
          // Если даты не выбраны, используем последние 30 дней
          url += 'days=30';
        }
      } else {
        url += `period=${period}`;
      }
      
      const { data } = await fetchJson<{ status?: string; message?: string; detail?: string; inserted?: number; updated?: number; skipped?: number; total_records?: number }>(url, { method: 'POST' });

      if (data.status === 'success') {
        // Сохраняем результат синхронизации для отображения
        setSyncResult({
          success: true,
          message: data.message || "Синхронизация завершена",
          stats: {
            created: data.inserted || 0,
            updated: data.updated || 0,
            skipped: data.skipped || 0,
            total: data.total_records || 0
          }
        });
        // Обновляем данные после синхронизации
        await fetchMetrics();
        // Скрываем уведомление через 5 секунд
        setTimeout(() => setSyncResult(null), 5000);
      } else {
        setSyncResult({
          success: false,
          message: data.detail || "Ошибка синхронизации",
          stats: null
        });
      }
    } catch (err) {
      console.error(err);
      setSyncResult({
        success: false,
        message: "Ошибка при синхронизации",
        stats: null
      });
    } finally {
      setSyncing(false);
    }
  };

  const syncStoreVisits = async () => {
    setSyncingVisits(true);
    try {
      const { data } = await fetchJson<{ status?: string }>('/api/analytics/store-visits/sync', {
        method: 'POST',
      });
      if (data.status === 'success') {
        await fetchMetrics();
      } else {
        console.error('Ошибка синхронизации посещаемости:', data);
      }
    } catch (err) {
      console.error('Ошибка синхронизации посещаемости:', err);
    } finally {
      setSyncingVisits(false);
    }
  };

  const fetchStores = async () => {
    try {
      const { data } = await fetchJson<{ status?: string; stores?: any[] }>('/api/analytics/stores');
      if (data.status === 'success') {
        setStores(data.stores || []);
      }
    } catch (err) {
      console.error('Ошибка загрузки магазинов:', err);
    }
  };

  const fetchSalesDetails = async () => {
    try {
      setLoadingDetails(true);
      let url = '/api/analytics/1c-sales/details?';
      
      if (period === "custom") {
        if (startDate && endDate) {
          // Форматируем даты в ISO формат
          const startISO = new Date(startDate + 'T00:00:00').toISOString();
          const endISO = new Date(endDate + 'T23:59:59').toISOString();
          url += `start_date=${encodeURIComponent(startISO)}&end_date=${encodeURIComponent(endISO)}&`;
        } else {
          // Если даты не выбраны, используем последние 30 дней
          url += 'days=30&';
        }
      } else {
        url += `period=${period}&`;
      }
      
      if (selectedStoreId && selectedStoreId !== "all") {
        url += `store_id=${encodeURIComponent(selectedStoreId)}&`;
      }
      
      url += 'limit=100';
      
      const { data } = await fetchJson<{ status?: string; sales?: SalesDetail[] }>(url);
      if (data.status === 'success') {
        setSalesDetails(data.sales || []);
      }
    } catch (err) {
      console.error('Ошибка загрузки детальных продаж:', err);
    } finally {
      setLoadingDetails(false);
    }
  };

  // Для «Сегодня» и «Вчера» — недельный график (7 дней), для остальных периодов — по выбранному
  const getChartDays = useCallback((): number => {
    if (period === 'today' || period === 'yesterday') return 7;
    if (period === 'week') return 7;
    if (period === 'month') return 30;
    if (period === 'quarter') return 92;
    if (period === 'year') return 365;
    if (period === 'custom' && startDate && endDate) {
      const start = new Date(startDate);
      const end = new Date(endDate);
      return Math.max(1, Math.ceil((end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000)) + 1);
    }
    return 7;
  }, [period, startDate, endDate]);

  const fetchChartData = useCallback(async () => {
    setLoadingCharts(true);
    const chartDays = getChartDays();
    try {
      let salesUrl = '/api/analytics/1c-sales/daily?auto_sync=true&';
      if (period === 'today' || period === 'yesterday') {
        salesUrl += `days=${chartDays}`;
      } else if (period === 'custom' && startDate && endDate) {
        const startISO = new Date(startDate + 'T00:00:00').toISOString();
        const endISO = new Date(endDate + 'T23:59:59').toISOString();
        salesUrl += `start_date=${encodeURIComponent(startISO)}&end_date=${encodeURIComponent(endISO)}`;
      } else {
        salesUrl += `period=${period}`;
      }
      const storeForChart = selectedStoreId && selectedStoreId !== 'all'
        ? stores.find(s => (s.external_id || s.name) === selectedStoreId)
        : null;
      const storeIdForSales = storeForChart?.id;
      const storeIdForVisits = storeForChart?.id ?? (selectedStoreId !== 'all' ? selectedStoreId : undefined);
      if (storeIdForSales) {
        salesUrl += `&store_id=${encodeURIComponent(storeIdForSales)}`;
      }
      let visitsUrl = `/api/analytics/store-visits/daily?days=${chartDays}`;
      if (storeIdForVisits) visitsUrl += `&store_id=${encodeURIComponent(storeIdForVisits)}`;

      const [salesRes, visitsRes] = await Promise.all([
        fetchJson<{ status?: string; daily_data?: Array<{ date: string; revenue: number; orders: number; items_sold: number }> }>(salesUrl),
        fetchJson<{ status?: string; daily_data?: Array<{ date: string; visitors: number; stores?: Array<{ name: string; visitors: number }> }> }>(visitsUrl),
      ]);
      if (salesRes.data.status === 'success' && salesRes.data.daily_data) {
        setChartSalesDaily({ daily_data: salesRes.data.daily_data });
      } else {
        setChartSalesDaily(null);
      }
      if (visitsRes.data.status === 'success' && visitsRes.data.daily_data) {
        setChartVisitsDaily({ daily_data: visitsRes.data.daily_data });
      } else {
        setChartVisitsDaily(null);
      }
    } catch (err) {
      console.error('Ошибка загрузки данных для графиков:', err);
      setChartSalesDaily(null);
      setChartVisitsDaily(null);
    } finally {
      setLoadingCharts(false);
    }
  }, [period, startDate, endDate, selectedStoreId, stores, getChartDays]);

  useEffect(() => { 
    fetchStores();
    fetchMetrics(); 
    fetchSalesDetails();
  }, [period, startDate, endDate, selectedStoreId]);

  useEffect(() => {
    fetchChartData();
  }, [fetchChartData]);

  const getPeriodLabel = (p: Period): string => {
    const labels: Record<Period, string> = {
      today: "Сегодня",
      yesterday: "Вчера",
      week: "Неделя",
      month: "Месяц",
      quarter: "Квартал",
      year: "Год",
      custom: "Диапазон дат"
    };
    return labels[p] || "Месяц";
  };

  // Метрики для отображения (используем aggregated, который уже учитывает фильтр по магазину)
  const totalRevenue = aggregated?.total_revenue || 0;
  const totalOrders = aggregated?.total_orders || 0;  // Количество чеков (distinct external_id)
  const totalItems = aggregated?.total_items || 0;  // Количество товаров (без упаковки)
  const totalVisitors = aggregated?.total_visitors || 0;  // Посещаемость магазина
  // Средний чек = Выручка / Количество чеков
  const avgOrderValue = totalOrders > 0 ? totalRevenue / totalOrders : 0;
  // Выручка на входящего = Выручка / Посещаемость
  const revenuePerVisitor = totalVisitors > 0 ? totalRevenue / totalVisitors : 0;

  // Список магазинов из данных 1С (для выпадающего списка)
  const availableStores = byStore ? Object.keys(byStore).filter(id => id !== "unknown") : [];
  
  // Функция для получения названия магазина
  const getStoreName = (storeId: string): string => {
    if (storeId === "all") return "Все магазины";
    // Сначала проверяем в данных byStore (там может быть store_name)
    if (byStore?.[storeId]?.store_name) {
      return byStore[storeId].store_name;
    }
    // Затем проверяем в списке магазинов из API
    const store = stores.find(s => s.external_id === storeId);
    return store?.name || storeId;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <span>Продажи (1С)</span>
            {/* Селектор магазина */}
            <Select value={selectedStoreId} onValueChange={setSelectedStoreId}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Выберите магазин" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все магазины</SelectItem>
                {stores.map(store => (
                  <SelectItem key={store.external_id || store.name} value={store.external_id || store.name}>
                    {store.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <Select value={period} onValueChange={(value) => setPeriod(value as Period)}>
              <SelectTrigger className="w-[140px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="today">Сегодня</SelectItem>
                <SelectItem value="yesterday">Вчера</SelectItem>
                <SelectItem value="week">Неделя</SelectItem>
                <SelectItem value="month">Месяц</SelectItem>
                <SelectItem value="quarter">Квартал</SelectItem>
                <SelectItem value="year">Год</SelectItem>
                <SelectItem value="custom">Диапазон дат</SelectItem>
              </SelectContent>
            </Select>
            {period === "custom" && (
              <>
                <input
                  id="start-date"
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  placeholder="Начальная дата"
                  className="px-3 py-2 border border-gray-300 rounded-md bg-white text-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-pink-500 w-[140px]"
                />
                <span className="text-gray-500">—</span>
                <input
                  id="end-date"
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  min={startDate}
                  placeholder="Конечная дата"
                  className="px-3 py-2 border border-gray-300 rounded-md bg-white text-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-pink-500 w-[140px]"
                />
                {startDate && endDate && (
                  <Button
                    onClick={() => {
                      setStartDate("");
                      setEndDate("");
                    }}
                    variant="outline"
                    size="sm"
                    className="h-[38px]"
                  >
                    Сбросить
                  </Button>
                )}
              </>
            )}
            <Button onClick={syncData} disabled={syncing || loading} size="sm" variant="outline">
              <RefreshCw className={`h-4 w-4 mr-2 ${syncing ? 'animate-spin' : ''}`} />
              Синхронизировать
            </Button>
          </div>
        </CardTitle>
        <CardDescription>
          Статистика продаж за {getPeriodLabel(period).toLowerCase()}
          {period === "custom" && startDate && endDate && ` (${startDate} - ${endDate})`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {/* Уведомление о результате синхронизации */}
        {syncResult && (
          <div className={`mb-4 p-4 border rounded-lg ${
            syncResult.success 
              ? 'bg-green-50 border-green-200' 
              : 'bg-red-50 border-red-200'
          }`}>
            <div className="flex items-start">
              <div className={`flex-shrink-0 ${
                syncResult.success ? 'text-green-400' : 'text-red-400'
              }`}>
                {syncResult.success ? (
                  <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                ) : (
                  <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                )}
              </div>
              <div className="ml-3 flex-1">
                <p className={`text-sm font-medium ${
                  syncResult.success ? 'text-green-800' : 'text-red-800'
                }`}>
                  {syncResult.message}
                </p>
                {syncResult.stats && (
                  <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                    <div>
                      <span className="text-gray-600">Создано:</span>
                      <span className="ml-1 font-semibold text-green-600">{syncResult.stats.created}</span>
                    </div>
                    <div>
                      <span className="text-gray-600">Обновлено:</span>
                      <span className="ml-1 font-semibold text-blue-600">{syncResult.stats.updated}</span>
                    </div>
                    <div>
                      <span className="text-gray-600">Пропущено:</span>
                      <span className="ml-1 font-semibold text-gray-600">{syncResult.stats.skipped}</span>
                    </div>
                    <div>
                      <span className="text-gray-600">Всего:</span>
                      <span className="ml-1 font-semibold text-gray-700">{syncResult.stats.total}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
        {loading && !aggregated ? (
          <div>Загрузка...</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
            <div className="bg-gray-100 p-4 rounded-lg">
              <p className="text-sm text-gray-600">Выручка</p>
              <p className="text-2xl font-bold text-gray-900">₽{totalRevenue.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
            </div>
            <div className="bg-gray-100 p-4 rounded-lg">
              <p className="text-sm text-gray-600">Количество чеков</p>
              <p className="text-2xl font-bold text-gray-900">{totalOrders.toLocaleString('ru-RU')}</p>
            </div>
            <div className="bg-gray-100 p-4 rounded-lg">
              <p className="text-sm text-gray-600">Товары</p>
              <p className="text-2xl font-bold text-gray-900">{totalItems.toLocaleString('ru-RU')}</p>
            </div>
            <div className="bg-gray-100 p-4 rounded-lg relative">
              <div className="flex items-center justify-between mb-1">
                <p className="text-sm text-gray-600">Посещаемость</p>
                <button
                  onClick={syncStoreVisits}
                  disabled={syncingVisits}
                  className="p-1 hover:bg-gray-200 rounded transition-colors disabled:opacity-50"
                  title="Обновить данные посещаемости"
                >
                  <RefreshCw className={`h-4 w-4 text-gray-600 ${syncingVisits ? 'animate-spin' : ''}`} />
                </button>
              </div>
              <p className="text-2xl font-bold text-gray-900">{totalVisitors.toLocaleString('ru-RU')}</p>
              {Object.keys(visitorsByStore).length > 0 && (() => {
                const byName: Record<string, number> = {};
                for (const v of Object.values(visitorsByStore)) {
                  const name = v?.store_name;
                  if (name && byName[name] === undefined) byName[name] = v.visitor_count;
                }
                const list = Object.entries(byName);
                return list.length > 0 ? (
                  <div className="mt-2 pt-2 border-t border-gray-200">
                    <p className="text-xs text-gray-500 mb-1">По магазинам:</p>
                    <ul className="text-xs text-gray-700 space-y-0.5">
                      {list.map(([name, count]) => (
                        <li key={name}>
                          {name}: <span className="font-medium">{count.toLocaleString('ru-RU')}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null;
              })()}
            </div>
            <div className="bg-gray-100 p-4 rounded-lg">
              <p className="text-sm text-gray-600">Средний чек</p>
              <p className="text-2xl font-bold text-gray-900">₽{avgOrderValue.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</p>
            </div>
            <div className="bg-gray-100 p-4 rounded-lg">
              <p className="text-sm text-gray-600">Выручка на входящего</p>
              <p className="text-2xl font-bold text-gray-900">₽{revenuePerVisitor.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</p>
            </div>
          </div>
        )}

        {/* Объединённый график: выручка и посещаемость по дате */}
        <div className="mt-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Выручка и посещаемость по дням</h3>
          {loadingCharts ? (
            <div className="h-[340px] flex items-center justify-center text-gray-500">Загрузка...</div>
          ) : (() => {
            const salesMap = new Map<string, number>();
            (chartSalesDaily?.daily_data || []).forEach((d) => {
              const key = d.date.split('T')[0];
              salesMap.set(key, d.revenue ?? 0);
            });
            const visitsDaily = chartVisitsDaily?.daily_data || [];
            const visitsMap = new Map<string, number>();
            const visitsByStoreMap = new Map<string, Map<string, number>>();
            const storeNamesSet = new Set<string>();
            visitsDaily.forEach((d) => {
              const key = d.date.split('T')[0];
              visitsMap.set(key, d.visitors ?? 0);
              (d.stores || []).forEach((s) => {
                storeNamesSet.add(s.name);
                if (!visitsByStoreMap.has(s.name)) visitsByStoreMap.set(s.name, new Map());
                visitsByStoreMap.get(s.name)!.set(key, s.visitors ?? 0);
              });
            });
            const allDates = new Set([
              ...Array.from(salesMap.keys()),
              ...Array.from(visitsMap.keys()),
            ]);
            const storeNames = Array.from(storeNamesSet);
            const hasPerStore = storeNames.length > 0;
            const combinedData = Array.from(allDates)
              .sort()
              .map((date) => {
                const row: Record<string, string | number> = {
                  date,
                  revenue: salesMap.get(date) ?? 0,
                  visitors: visitsMap.get(date) ?? 0,
                };
                storeNames.forEach((name) => {
                  row[name] = visitsByStoreMap.get(name)?.get(date) ?? 0;
                });
                return row;
              });
            let maxVisitors = 0;
            combinedData.forEach((row) => {
              const v = Number(row.visitors ?? 0);
              if (v > maxVisitors) maxVisitors = v;
              storeNames.forEach((name) => {
                const vv = Number(row[name] ?? 0);
                if (vv > maxVisitors) maxVisitors = vv;
              });
            });
            const rightDomain = maxVisitors > 0 ? [0, Math.ceil(maxVisitors * 1.1)] as const : undefined;
            if (combinedData.length === 0) {
              return (
                <div className="h-[340px] flex items-center justify-center text-gray-500 border border-dashed border-gray-300 rounded-lg">
                  Нет данных за период
                </div>
              );
            }
            const visitLineColors = ['#4f46e5', '#059669', '#dc2626', '#d97706', '#7c3aed', '#0d9488'];
            return (
              <ResponsiveContainer width="100%" height={340}>
                <ComposedChart data={combinedData} margin={{ top: 8, right: 48, left: 8, bottom: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(v) => new Date(v).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}
                    angle={-45}
                    textAnchor="end"
                    height={56}
                  />
                  <YAxis yAxisId="left" orientation="left" tickFormatter={(v) => `₽${v >= 1000 ? (v / 1000) + 'k' : v}`} />
                  <YAxis yAxisId="right" orientation="right" domain={rightDomain} />
                  <Tooltip
                    labelFormatter={(label) => new Date(label).toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}
                    formatter={(value, name) => {
                      const numericValue = Number(value ?? 0);
                      const seriesName = String(name ?? '');
                      if (seriesName === 'revenue' || seriesName === 'Выручка') {
                        return [`₽${numericValue.toLocaleString('ru-RU', { minimumFractionDigits: 2 })}`, 'Выручка'];
                      }
                      return [numericValue.toLocaleString('ru-RU'), seriesName];
                    }}
                  />
                  <Legend />
                  <Bar yAxisId="left" dataKey="revenue" fill="#b8860b" name="Выручка" radius={[4, 4, 0, 0]} />
                  {hasPerStore
                    ? storeNames.map((name, i) => (
                        <Line
                          key={name}
                          yAxisId="right"
                          type="monotone"
                          dataKey={name}
                          stroke={visitLineColors[i % visitLineColors.length]}
                          strokeWidth={2}
                          name={name}
                          dot={{ r: 3 }}
                          activeDot={{ r: 5 }}
                        />
                      ))
                    : (
                      <Line yAxisId="right" type="monotone" dataKey="visitors" stroke="#4f46e5" strokeWidth={2} name="Посещаемость" dot={{ r: 3 }} activeDot={{ r: 5 }} />
                    )}
                </ComposedChart>
              </ResponsiveContainer>
            );
          })()}
        </div>
        
        {/* Таблица детальных продаж */}
        <div className="mt-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Детальные продажи</h3>
          {loadingDetails ? (
            <div className="text-center py-8 text-gray-500">Загрузка...</div>
          ) : salesDetails.length === 0 ? (
            <div className="text-center py-8 text-gray-500">Нет данных о продажах</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="text-left p-3 font-semibold text-gray-700">Дата/Время</th>
                    <th className="text-left p-3 font-semibold text-gray-700">Товар</th>
                    <th className="text-left p-3 font-semibold text-gray-700">Артикул</th>
                    <th className="text-left p-3 font-semibold text-gray-700">Категория</th>
                    <th className="text-right p-3 font-semibold text-gray-700">Количество</th>
                    <th className="text-right p-3 font-semibold text-gray-700">Сумма</th>
                    <th className="text-left p-3 font-semibold text-gray-700">Магазин</th>
                    <th className="text-left p-3 font-semibold text-gray-700">Канал</th>
                  </tr>
                </thead>
                <tbody>
                  {salesDetails.map((sale) => (
                    <tr key={sale.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="p-3 text-gray-700">
                        {sale.sale_date ? new Date(sale.sale_date).toLocaleString('ru-RU', {
                          year: 'numeric',
                          month: '2-digit',
                          day: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit'
                        }) : '—'}
                      </td>
                      <td className="p-3 font-medium text-gray-900">{sale.product_name || '—'}</td>
                      <td className="p-3 text-gray-600">{sale.product_article || '—'}</td>
                      <td className="p-3 text-gray-600">{sale.product_category || '—'}</td>
                      <td className="p-3 text-right text-gray-700">
                        {sale.quantity != null ? sale.quantity.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) : '—'}
                      </td>
                      <td className="p-3 text-right font-semibold text-gray-900">
                        ₽{sale.revenue != null ? sale.revenue.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00'}
                      </td>
                      <td className="p-3 text-gray-600">{sale.store_name || sale.store_id || '—'}</td>
                      <td className="p-3 text-gray-600">{sale.channel || 'offline'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
