"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw, Calendar } from "lucide-react";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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

export function SalesPanel() {
  const [aggregated, setAggregated] = useState<any>(null);
  const [byStore, setByStore] = useState<any>(null);
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
      
      const response = await fetch(url);
      const data = await response.json();
      if (data.status === 'success') {
        setAggregated(data.aggregated);
        setByStore(data.by_store || {});
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
      
      const response = await fetch(url, { method: 'POST' });
      const data = await response.json();
      
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
      const response = await fetch('/api/analytics/store-visits/sync', {
        method: 'POST',
      });
      const data = await response.json();
      if (data.status === 'success') {
        // Обновляем данные после синхронизации
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
      const response = await fetch('/api/analytics/stores');
      const data = await response.json();
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
      
      const response = await fetch(url);
      const data = await response.json();
      if (data.status === 'success') {
        setSalesDetails(data.sales || []);
      }
    } catch (err) {
      console.error('Ошибка загрузки детальных продаж:', err);
    } finally {
      setLoadingDetails(false);
    }
  };

  useEffect(() => { 
    fetchStores();
    fetchMetrics(); 
    fetchSalesDetails();
  }, [period, startDate, endDate, selectedStoreId]);

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
