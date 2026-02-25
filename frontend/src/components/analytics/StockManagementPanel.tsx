"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw, Package, AlertCircle, TrendingUp, Activity, Download } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface InventoryAnalysis {
  product_id_1c?: string | null;
  product_id?: string | null;
  product_name?: string | null;
  product_article?: string | null;
  category?: string | null;
  brand?: string | null;
  store_id?: string | null;
  store_name?: string | null;
  current_stock?: number | null;
  avg_stock_30d?: number | null;
  avg_stock_90d?: number | null;
  sales_velocity?: number | null;
  avg_daily_sales?: number | null;
  turnover_days?: number | null;
  turnover_rate?: number | null;
  stockout_risk?: number | null;
  overstock_risk?: number | null;
  abc_class?: string | null;
  xyz_class?: string | null;
  service_level?: number | null;
}

interface HealthScore {
  health_score?: number;
  status?: string;
  metrics?: {
    total_products?: number;
    avg_stockout_risk?: number;
    avg_overstock_risk?: number;
    avg_service_level?: number;
    critical_stockout_count?: number;
    critical_overstock_count?: number;
  };
}

export function StockManagementPanel() {
  const [analysis, setAnalysis] = useState<InventoryAnalysis[]>([]);
  const [healthScore, setHealthScore] = useState<HealthScore | null>(null);
  const [loading, setLoading] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [syncingStocks, setSyncingStocks] = useState(false);
  const [syncProgress, setSyncProgress] = useState<string>('');
  const [limit, setLimit] = useState<number>(100);
  const [storeId, setStoreId] = useState<string>("all");
  const [category, setCategory] = useState<string>("all");
  const [abcClass, setAbcClass] = useState<string>("all");
  const [xyzClass, setXyzClass] = useState<string>("all");
  const [stores, setStores] = useState<any[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [showDialog, setShowDialog] = useState(false);
  const [dialogTitle, setDialogTitle] = useState('');
  const [filteredProducts, setFilteredProducts] = useState<InventoryAnalysis[]>([]);
  const [loadingFiltered, setLoadingFiltered] = useState(false);

  const fetchAnalysis = async () => {
    try {
      setLoading(true);
      let url = '/api/analytics/inventory/analysis?';
      url += `limit=${limit}`;
      if (storeId && storeId !== 'all') url += `&store_id=${encodeURIComponent(storeId)}`;
      if (category && category !== 'all') url += `&category=${encodeURIComponent(category)}`;
      if (abcClass && abcClass !== 'all') url += `&abc_class=${encodeURIComponent(abcClass)}`;
      if (xyzClass && xyzClass !== 'all') url += `&xyz_class=${encodeURIComponent(xyzClass)}`;

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка загрузки данных');
      }

      const data = await response.json();
      setAnalysis(data.analysis || []);
    } catch (error) {
      console.error('Ошибка загрузки аналитики:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchHealthScore = async () => {
    try {
      let url = '/api/analytics/inventory/health-score';
      if (storeId && storeId !== 'all') url += `?store_id=${encodeURIComponent(storeId)}`;

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка загрузки данных');
      }

      const data = await response.json();
      setHealthScore(data);
    } catch (error) {
      console.error('Ошибка загрузки здоровья остатков:', error);
    }
  };

  const fetchFilteredProducts = async (filterType: 'stockout' | 'overstock' | 'all') => {
    try {
      setLoadingFiltered(true);
      let url = '/api/analytics/inventory/analysis?limit=1000';
      if (storeId && storeId !== 'all') url += `&store_id=${encodeURIComponent(storeId)}`;
      
      if (filterType === 'stockout') {
        url += '&critical_stockout=true';
        setDialogTitle('Товары с критическим дефицитом');
      } else if (filterType === 'overstock') {
        url += '&critical_overstock=true';
        setDialogTitle('Товары с критическими излишками');
      } else {
        setDialogTitle('Все товары');
      }

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка загрузки данных');
      }

      const data = await response.json();
      setFilteredProducts(data.analysis || []);
      setShowDialog(true);
    } catch (error) {
      console.error('Ошибка загрузки отфильтрованных товаров:', error);
    } finally {
      setLoadingFiltered(false);
    }
  };

  const recalculateAnalysis = async () => {
    try {
      setRecalculating(true);
      const response = await fetch('/api/analytics/inventory/analysis/recalculate?analysis_period_days=90', {
        method: 'POST'
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Неизвестная ошибка' }));
        throw new Error(errorData.detail || 'Ошибка пересчёта аналитики');
      }

      const data = await response.json();
      console.log('Аналитика пересчитана:', data.message);
      
      // Обновляем данные после пересчёта
      await fetchAnalysis();
      await fetchHealthScore();
    } catch (error) {
      console.error('Ошибка пересчёта аналитики:', error);
      alert(`Ошибка пересчёта аналитики: ${error instanceof Error ? error.message : 'Неизвестная ошибка'}`);
    } finally {
      setRecalculating(false);
    }
  };

  const exportToExcel = async () => {
    try {
      let url = '/api/analytics/inventory/analysis/export?';
      if (storeId && storeId !== 'all') url += `store_id=${encodeURIComponent(storeId)}&`;
      if (category && category !== 'all') url += `category=${encodeURIComponent(category)}&`;
      if (abcClass && abcClass !== 'all') url += `abc_class=${encodeURIComponent(abcClass)}&`;
      if (xyzClass && xyzClass !== 'all') url += `xyz_class=${encodeURIComponent(xyzClass)}&`;

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка экспорта данных');
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `Аналитика_остатков_${new Date().toISOString().split('T')[0]}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
      console.error('Ошибка экспорта:', error);
      alert(`Ошибка экспорта: ${error instanceof Error ? error.message : 'Неизвестная ошибка'}`);
    }
  };

  const syncStocks = async () => {
    try {
      setSyncingStocks(true);
      setSyncProgress('Начало синхронизации остатков...');
      console.log('Начало синхронизации остатков...');
      
      // Увеличиваем таймаут для долгих операций (10 минут)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 600000); // 10 минут
      
      try {
        setSyncProgress('Загрузка offers.xml...');
        const response = await fetch('/api/analytics/inventory/stocks/sync', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          signal: controller.signal,
        });
        
        clearTimeout(timeoutId);
      
        setSyncProgress('Обработка ответа сервера...');
        console.log('Ответ получен:', response.status, response.statusText);
        
        let responseData;
        try {
          const text = await response.text();
          console.log('Текст ответа (первые 500 символов):', text.substring(0, 500));
          
          // Проверяем, не является ли ответ HTML (ошибка сервера)
          if (text.trim().startsWith('<') || text.includes('<!DOCTYPE') || text.includes('<html')) {
            console.error('Сервер вернул HTML вместо JSON:', text.substring(0, 1000));
            throw new Error(`Сервер вернул HTML ошибку вместо JSON. Проверьте логи сервера.`);
          }
          
          responseData = text ? JSON.parse(text) : {};
        } catch (parseError) {
          console.error('Ошибка парсинга ответа:', parseError);
          if (parseError instanceof Error && parseError.message.includes('HTML')) {
            throw parseError;
          }
          throw new Error(`Ошибка парсинга ответа сервера: ${parseError instanceof Error ? parseError.message : 'Неизвестная ошибка'}`);
        }
        
        if (!response.ok) {
          const errorMessage = responseData.detail || responseData.message || `HTTP ${response.status}: ${response.statusText}`;
          console.error('Ошибка от сервера:', errorMessage);
          throw new Error(errorMessage);
        }

        setSyncProgress('Синхронизация завершена');
        console.log('Остатки синхронизированы:', responseData);
        
        let message = `Остатки успешно обновлены.\nСоздано: ${responseData.created || 0}, Обновлено: ${responseData.updated || 0}`;
        if (responseData.stores_synced) {
          message += `\nСклады: создано ${responseData.stores_synced.created || 0}, обновлено ${responseData.stores_synced.updated || 0}`;
        }
        if (responseData.analytics_recalculated) {
          message += `\nАналитика пересчитана: обработано ${responseData.analytics_count || 0} товаров`;
        } else if (responseData.analytics_error) {
          message += `\n⚠️ Ошибка пересчёта аналитики: ${responseData.analytics_error}`;
        }
        alert(message);
        
        // Обновляем данные после синхронизации
        setSyncProgress('Обновление данных...');
        await fetchAnalysis();
        await fetchHealthScore();
        setSyncProgress('');
      } catch (fetchError) {
        clearTimeout(timeoutId);
        if (fetchError instanceof Error && fetchError.name === 'AbortError') {
          throw new Error('Операция превысила максимальное время ожидания (10 минут). Попробуйте позже или проверьте логи сервера.');
        }
        throw fetchError;
      }
    } catch (error) {
      console.error('Ошибка синхронизации остатков:', error);
      const errorMessage = error instanceof Error 
        ? error.message 
        : typeof error === 'string' 
          ? error 
          : 'Неизвестная ошибка';
      alert(`Ошибка синхронизации остатков: ${errorMessage}`);
      setSyncProgress('');
    } finally {
      setSyncingStocks(false);
    }
  };

  const fetchStores = async () => {
    try {
      const response = await fetch('/api/analytics/stores?include_warehouse=true');
      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success') {
          setStores(data.stores || []);
        }
      }
    } catch (error) {
      console.error('Ошибка загрузки магазинов:', error);
    }
  };

  const fetchCategories = async () => {
    try {
      const response = await fetch('/api/analytics/inventory/categories');
      if (response.ok) {
        const data = await response.json();
        if (data.status === 'success') {
          setCategories(data.categories || []);
        }
      }
    } catch (error) {
      console.error('Ошибка загрузки категорий:', error);
    }
  };

  useEffect(() => {
    fetchStores();
    fetchCategories();
  }, []);

  useEffect(() => {
    fetchAnalysis();
    fetchHealthScore();
  }, [limit, storeId, category, abcClass, xyzClass]);

  const getHealthStatusColor = (status?: string) => {
    switch (status) {
      case 'excellent':
        return 'bg-green-100 text-green-800 border-green-300';
      case 'good':
        return 'bg-blue-100 text-blue-800 border-blue-300';
      case 'fair':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'poor':
        return 'bg-red-100 text-red-800 border-red-300';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  const getHealthStatusLabel = (status?: string) => {
    switch (status) {
      case 'excellent':
        return 'Отлично';
      case 'good':
        return 'Хорошо';
      case 'fair':
        return 'Удовлетворительно';
      case 'poor':
        return 'Плохо';
      default:
        return 'Неизвестно';
    }
  };

  const getRiskColor = (risk?: number | null) => {
    if (!risk) return 'text-gray-500';
    if (risk >= 0.7) return 'text-red-600 font-semibold';
    if (risk >= 0.4) return 'text-orange-600';
    return 'text-green-600';
  };

  return (
    <div className="space-y-4">
      {/* Health Score Card */}
      {healthScore && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-blue-500" />
              Здоровье остатков
            </CardTitle>
            <CardDescription>
              Общая оценка состояния запасов
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-gray-50 p-4 rounded-lg">
                <div className="text-sm text-gray-600 mb-1">Общий балл</div>
                <div className="text-3xl font-bold text-gray-900">
                  {healthScore.health_score?.toFixed(1) || '0.0'}
                </div>
                <div className={`mt-2 px-2 py-1 rounded text-xs font-medium border inline-block ${getHealthStatusColor(healthScore.status)}`}>
                  {getHealthStatusLabel(healthScore.status)}
                </div>
              </div>
              {healthScore.metrics && (
                <>
                  <div 
                    className="bg-gray-50 p-4 rounded-lg cursor-pointer hover:bg-gray-100 transition-colors"
                    onClick={() => fetchFilteredProducts('all')}
                    title="Нажмите, чтобы увидеть все товары"
                  >
                    <div className="text-sm text-gray-600 mb-1">Всего товаров</div>
                    <div className="text-2xl font-bold text-gray-900">
                      {healthScore.metrics.total_products?.toLocaleString('ru-RU') || '0'}
                    </div>
                  </div>
                  <div 
                    className="bg-gray-50 p-4 rounded-lg cursor-pointer hover:bg-gray-100 transition-colors"
                    onClick={() => fetchFilteredProducts('stockout')}
                    title="Нажмите, чтобы увидеть товары с критическим дефицитом"
                  >
                    <div className="text-sm text-gray-600 mb-1">Критический дефицит</div>
                    <div className="text-2xl font-bold text-red-600">
                      {healthScore.metrics.critical_stockout_count || 0}
                    </div>
                  </div>
                  <div 
                    className="bg-gray-50 p-4 rounded-lg cursor-pointer hover:bg-gray-100 transition-colors"
                    onClick={() => fetchFilteredProducts('overstock')}
                    title="Нажмите, чтобы увидеть товары с критическими излишками"
                  >
                    <div className="text-sm text-gray-600 mb-1">Критические излишки</div>
                    <div className="text-2xl font-bold text-orange-600">
                      {healthScore.metrics.critical_overstock_count || 0}
                    </div>
                  </div>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Управление запасами</CardTitle>
              <CardDescription>
                Комплексная аналитика остатков товаров
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={syncStocks}
                disabled={syncingStocks}
                variant="outline"
                size="sm"
              >
                <Package className={`h-4 w-4 mr-2 ${syncingStocks ? 'animate-spin' : ''}`} />
                Обновить остатки
              </Button>
              <Button
                onClick={recalculateAnalysis}
                disabled={recalculating}
                variant="outline"
                size="sm"
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${recalculating ? 'animate-spin' : ''}`} />
                Пересчитать
              </Button>
              <Button
                onClick={exportToExcel}
                disabled={loading || analysis.length === 0}
                variant="outline"
                size="sm"
              >
                <Download className="h-4 w-4 mr-2" />
                Экспорт в Excel
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Фильтры */}
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
                  Количество
                </label>
                <Select value={limit.toString()} onValueChange={(v) => setLimit(parseInt(v))}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                    <SelectItem value="200">200</SelectItem>
                    <SelectItem value="500">500</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
                  Магазин
                </label>
                <Select value={storeId} onValueChange={setStoreId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Все магазины" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Все магазины</SelectItem>
                    {stores.map((store) => (
                      <SelectItem key={store.external_id || store.id} value={store.external_id || store.id}>
                        {store.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
                  Категория
                </label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger>
                    <SelectValue placeholder="Все категории" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Все категории</SelectItem>
                    {categories.map((cat) => (
                      <SelectItem key={cat} value={cat}>
                        {cat}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
                  ABC класс
                </label>
                <Select value={abcClass} onValueChange={setAbcClass}>
                  <SelectTrigger>
                    <SelectValue placeholder="Все" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Все</SelectItem>
                    <SelectItem value="A">A</SelectItem>
                    <SelectItem value="B">B</SelectItem>
                    <SelectItem value="C">C</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
                  XYZ класс
                </label>
                <Select value={xyzClass} onValueChange={setXyzClass}>
                  <SelectTrigger>
                    <SelectValue placeholder="Все" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Все</SelectItem>
                    <SelectItem value="X">X</SelectItem>
                    <SelectItem value="Y">Y</SelectItem>
                    <SelectItem value="Z">Z</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Таблица аналитики */}
            {loading ? (
              <div className="text-center py-8 text-gray-500">Загрузка...</div>
            ) : analysis.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                Нет данных с указанными критериями
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="bg-gray-50 border-b">
                      <th className="text-left p-2 font-semibold text-gray-700">Товар</th>
                      <th className="text-left p-2 font-semibold text-gray-700">Артикул</th>
                      <th className="text-left p-2 font-semibold text-gray-700">Магазин</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Остаток</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Продажи/день</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Оборачиваемость (дни)</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Риск дефицита</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Риск излишков</th>
                      <th className="text-center p-2 font-semibold text-gray-700">ABC/XYZ</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Уровень сервиса</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.map((item, index) => (
                      <tr key={`${item.product_id_1c}-${item.store_id}-${index}`} className="border-b hover:bg-gray-50">
                        <td className="p-2">
                          <div className="font-medium text-gray-900">
                            {item.product_name || 'Без названия'}
                          </div>
                          {item.brand && (
                            <div className="text-sm text-gray-500">{item.brand}</div>
                          )}
                        </td>
                        <td className="p-2 text-gray-700">{item.product_article || '-'}</td>
                        <td className="p-2 text-gray-700">{item.store_name || item.store_id || '-'}</td>
                        <td className="p-2 text-right text-gray-700">
                          {item.current_stock?.toLocaleString('ru-RU') || '0'}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {item.avg_daily_sales ? item.avg_daily_sales.toFixed(2) : '-'}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {item.turnover_days ? item.turnover_days.toFixed(1) : '-'}
                        </td>
                        <td className={`p-2 text-right ${getRiskColor(item.stockout_risk)}`}>
                          {item.stockout_risk ? (item.stockout_risk * 100).toFixed(1) + '%' : '-'}
                        </td>
                        <td className={`p-2 text-right ${getRiskColor(item.overstock_risk)}`}>
                          {item.overstock_risk ? (item.overstock_risk * 100).toFixed(1) + '%' : '-'}
                        </td>
                        <td className="p-2 text-center">
                          <span className="px-2 py-1 rounded text-xs font-medium bg-blue-100 text-blue-800 border border-blue-300">
                            {item.abc_class || '-'}/{item.xyz_class || '-'}
                          </span>
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {item.service_level ? (item.service_level * 100).toFixed(1) + '%' : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Прогноз дефицита и ABC/XYZ матрица */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StockoutForecastSection storeId={storeId} />
        <ABCXYZMatrixSection storeId={storeId} />
      </div>

      {/* Модальный диалог для отображения отфильтрованных товаров */}
      {showDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] flex flex-col">
            <div className="p-6 border-b flex items-center justify-between">
              <h2 className="text-xl font-bold text-gray-900">{dialogTitle}</h2>
              <button
                onClick={() => setShowDialog(false)}
                className="text-gray-500 hover:text-gray-700 text-2xl font-bold"
              >
                ×
              </button>
            </div>
            <div className="p-6 overflow-y-auto flex-1">
              {loadingFiltered ? (
                <div className="text-center py-8">
                  <RefreshCw className="h-8 w-8 animate-spin mx-auto text-gray-400" />
                  <p className="mt-2 text-gray-600">Загрузка товаров...</p>
                </div>
              ) : filteredProducts.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-gray-600">Нет товаров с указанными критериями</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-gray-50">
                        <th className="text-left p-2 font-semibold text-gray-700">Товар</th>
                        <th className="text-left p-2 font-semibold text-gray-700">Артикул</th>
                        <th className="text-left p-2 font-semibold text-gray-700">Магазин</th>
                        <th className="text-right p-2 font-semibold text-gray-700">Остаток</th>
                        <th className="text-right p-2 font-semibold text-gray-700">Продаж/день</th>
                        <th className="text-right p-2 font-semibold text-gray-700">Риск дефицита</th>
                        <th className="text-right p-2 font-semibold text-gray-700">Риск излишков</th>
                        <th className="text-center p-2 font-semibold text-gray-700">ABC/XYZ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredProducts.map((item, index) => (
                        <tr key={`${item.product_id_1c}-${item.store_id}-${index}`} className="border-b hover:bg-gray-50">
                          <td className="p-2">
                            <div className="font-medium text-gray-900">
                              {item.product_name || 'Без названия'}
                            </div>
                            {item.brand && (
                              <div className="text-sm text-gray-500">{item.brand}</div>
                            )}
                          </td>
                          <td className="p-2 text-gray-700">{item.product_article || '-'}</td>
                          <td className="p-2 text-gray-700">{item.store_name || item.store_id || '-'}</td>
                          <td className="p-2 text-right text-gray-700">
                            {item.current_stock?.toLocaleString('ru-RU') || '0'}
                          </td>
                          <td className="p-2 text-right text-gray-700">
                            {item.avg_daily_sales ? item.avg_daily_sales.toFixed(2) : '-'}
                          </td>
                          <td className={`p-2 text-right ${getRiskColor(item.stockout_risk)}`}>
                            {item.stockout_risk ? (item.stockout_risk * 100).toFixed(1) + '%' : '-'}
                          </td>
                          <td className={`p-2 text-right ${getRiskColor(item.overstock_risk)}`}>
                            {item.overstock_risk ? (item.overstock_risk * 100).toFixed(1) + '%' : '-'}
                          </td>
                          <td className="p-2 text-center">
                            <span className="px-2 py-1 rounded text-xs font-medium bg-blue-100 text-blue-800 border border-blue-300">
                              {item.abc_class || '-'}/{item.xyz_class || '-'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="mt-4 text-sm text-gray-600">
                    Всего товаров: {filteredProducts.length}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StockoutForecastSection({ storeId }: { storeId: string }) {
  const [forecast, setForecast] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchForecast = async () => {
      try {
        setLoading(true);
        let url = '/api/analytics/inventory/stockout-forecast?days=30';
        if (storeId && storeId !== 'all') url += `&store_id=${encodeURIComponent(storeId)}`;

        const response = await fetch(url);
        if (!response.ok) {
          throw new Error('Ошибка загрузки данных');
        }
        const data = await response.json();
        setForecast(data.forecast || []);
      } catch (error) {
        console.error('Ошибка загрузки прогноза:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchForecast();
  }, [storeId]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertCircle className="h-5 w-5 text-red-500" />
          Прогноз дефицита (30 дней)
        </CardTitle>
        <CardDescription>
          Товары, которые могут закончиться в ближайшие 30 дней
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="text-center py-4 text-gray-500">Загрузка...</div>
        ) : forecast.length === 0 ? (
          <div className="text-center py-4 text-gray-500">Нет прогнозируемого дефицита</div>
        ) : (
          <div className="space-y-2">
            {forecast.slice(0, 10).map((item, index) => (
              <div key={index} className="flex items-center justify-between p-2 bg-red-50 rounded border border-red-200">
                <div>
                  <div className="font-medium text-gray-900">{item.product_name || 'Без названия'}</div>
                  <div className="text-sm text-gray-600">
                    Остаток: {item.current_stock?.toLocaleString('ru-RU') || '0'} | 
                    Дней до дефицита: {item.days_until_stockout?.toFixed(0) || '-'}
                  </div>
                </div>
                <Package className="h-5 w-5 text-red-500" />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ABCXYZMatrixSection({ storeId }: { storeId: string }) {
  const [matrix, setMatrix] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [dialogTitle, setDialogTitle] = useState('');
  const [filteredProducts, setFilteredProducts] = useState<InventoryAnalysis[]>([]);
  const [loadingFiltered, setLoadingFiltered] = useState(false);

  const getRiskColor = (risk?: number | null) => {
    if (risk == null) return 'text-gray-600';
    if (risk >= 0.7) return 'text-red-600';
    if (risk >= 0.4) return 'text-orange-600';
    return 'text-green-600';
  };

  useEffect(() => {
    const fetchMatrix = async () => {
      try {
        setLoading(true);
        let url = '/api/analytics/inventory/abc-xyz-matrix';
        if (storeId && storeId !== 'all') url += `?store_id=${encodeURIComponent(storeId)}`;

        const response = await fetch(url);
        if (!response.ok) {
          throw new Error('Ошибка загрузки данных');
        }
        const data = await response.json();
        setMatrix(data.matrix || {});
      } catch (error) {
        console.error('Ошибка загрузки матрицы:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchMatrix();
  }, [storeId]);

  const fetchProductsByClass = async (abcClass: string, xyzClass: string) => {
    try {
      setLoadingFiltered(true);
      let url = '/api/analytics/inventory/analysis?limit=1000';
      if (storeId && storeId !== 'all') url += `&store_id=${encodeURIComponent(storeId)}`;
      url += `&abc_class=${abcClass}`;
      url += `&xyz_class=${xyzClass}`;

      setDialogTitle(`Товары класса ${abcClass}${xyzClass}`);

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка загрузки данных');
      }

      const data = await response.json();
      setFilteredProducts(data.analysis || []);
      setShowDialog(true);
    } catch (error) {
      console.error('Ошибка загрузки товаров:', error);
    } finally {
      setLoadingFiltered(false);
    }
  };

  if (loading || Object.keys(matrix).length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-blue-500" />
            ABC/XYZ Матрица
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4 text-gray-500">
            {loading ? 'Загрузка...' : 'Нет данных'}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-blue-500" />
          ABC/XYZ Матрица
        </CardTitle>
        <CardDescription>
          Классификация товаров по выручке (ABC) и стабильности спроса (XYZ)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-2">
          {['AX', 'AY', 'AZ', 'BX', 'BY', 'BZ', 'CX', 'CY', 'CZ'].map((key) => {
            const item = matrix[key];
            if (!item) return null;
            const abcClass = key[0];
            const xyzClass = key[1];
            const count = item.count || 0;
            
            return (
              <div
                key={key}
                className="p-3 bg-gray-50 rounded border cursor-pointer hover:bg-gray-100 hover:border-blue-300 transition-colors"
                onClick={() => count > 0 && fetchProductsByClass(abcClass, xyzClass)}
                title={count > 0 ? `Нажмите, чтобы увидеть ${count} товаров класса ${key}` : 'Нет товаров'}
              >
                <div className="font-semibold text-gray-900">{key}</div>
                <div className="text-sm text-gray-600 mt-1">
                  Товаров: {count}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Оборачиваемость: {item.avg_turnover?.toFixed(2) || '0.00'}
                </div>
              </div>
            );
          })}
        </div>

        {/* Модальный диалог для отображения товаров по классу */}
        {showDialog && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] flex flex-col">
              <div className="p-6 border-b flex items-center justify-between">
                <h2 className="text-xl font-bold text-gray-900">{dialogTitle}</h2>
                <button
                  onClick={() => setShowDialog(false)}
                  className="text-gray-500 hover:text-gray-700 text-2xl font-bold"
                >
                  ×
                </button>
              </div>
              <div className="p-6 overflow-y-auto flex-1">
                {loadingFiltered ? (
                  <div className="text-center py-8">
                    <RefreshCw className="h-8 w-8 animate-spin mx-auto text-gray-400" />
                    <p className="mt-2 text-gray-600">Загрузка товаров...</p>
                  </div>
                ) : filteredProducts.length === 0 ? (
                  <div className="text-center py-8">
                    <p className="text-gray-600">Нет товаров с указанными критериями</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b bg-gray-50">
                          <th className="text-left p-2 font-semibold text-gray-700">Товар</th>
                          <th className="text-left p-2 font-semibold text-gray-700">Артикул</th>
                          <th className="text-left p-2 font-semibold text-gray-700">Магазин</th>
                          <th className="text-right p-2 font-semibold text-gray-700">Остаток</th>
                          <th className="text-right p-2 font-semibold text-gray-700">Продаж/день</th>
                          <th className="text-right p-2 font-semibold text-gray-700">Оборачиваемость (дни)</th>
                          <th className="text-right p-2 font-semibold text-gray-700">Риск дефицита</th>
                          <th className="text-right p-2 font-semibold text-gray-700">Риск излишков</th>
                          <th className="text-center p-2 font-semibold text-gray-700">ABC/XYZ</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredProducts.map((item, index) => (
                          <tr key={`${item.product_id_1c}-${item.store_id}-${index}`} className="border-b hover:bg-gray-50">
                            <td className="p-2">
                              <div className="font-medium text-gray-900">
                                {item.product_name || 'Без названия'}
                              </div>
                              {item.brand && (
                                <div className="text-sm text-gray-500">{item.brand}</div>
                              )}
                            </td>
                            <td className="p-2 text-gray-700">{item.product_article || '-'}</td>
                            <td className="p-2 text-gray-700">{item.store_name || item.store_id || '-'}</td>
                            <td className="p-2 text-right text-gray-700">
                              {item.current_stock?.toLocaleString('ru-RU') || '0'}
                            </td>
                            <td className="p-2 text-right text-gray-700">
                              {item.avg_daily_sales ? item.avg_daily_sales.toFixed(2) : '-'}
                            </td>
                            <td className="p-2 text-right text-gray-700">
                              {item.turnover_days ? item.turnover_days.toFixed(1) : '-'}
                            </td>
                            <td className={`p-2 text-right ${getRiskColor(item.stockout_risk)}`}>
                              {item.stockout_risk ? (item.stockout_risk * 100).toFixed(1) + '%' : '-'}
                            </td>
                            <td className={`p-2 text-right ${getRiskColor(item.overstock_risk)}`}>
                              {item.overstock_risk ? (item.overstock_risk * 100).toFixed(1) + '%' : '-'}
                            </td>
                            <td className="p-2 text-center">
                              <span className="px-2 py-1 rounded text-xs font-medium bg-blue-100 text-blue-800 border border-blue-300">
                                {item.abc_class || '-'}/{item.xyz_class || '-'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="mt-4 text-sm text-gray-600">
                      Всего товаров: {filteredProducts.length}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
