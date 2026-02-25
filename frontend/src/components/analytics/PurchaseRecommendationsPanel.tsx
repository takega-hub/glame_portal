"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw, AlertTriangle, ShoppingCart, TrendingDown, Download } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface PurchaseRecommendation {
  product_name?: string | null;
  product_article?: string | null;
  product_id_1c?: string | null;
  category?: string | null;
  brand?: string | null;
  current_stock?: number | null;
  recommended_stock?: number | null;
  reorder_quantity?: number | null;
  reorder_point?: number | null;
  days_of_stock?: number | null;
  avg_daily_sales?: number | null;
  turnover_rate?: number | null;
  turnover_days?: number | null;
  urgency_level?: string | null;
  recommended_date?: string | null;
}

export function PurchaseRecommendationsPanel() {
  const [recommendations, setRecommendations] = useState<PurchaseRecommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [limit, setLimit] = useState<number>(100);
  const [urgencyLevel, setUrgencyLevel] = useState<string>("all");
  const [category, setCategory] = useState<string>("");
  const [onlyReorder, setOnlyReorder] = useState<boolean>(false);

  const fetchRecommendations = async () => {
    try {
      setLoading(true);
      let url = '/api/analytics/inventory/purchase-recommendations?';
      url += `limit=${limit}`;
      if (urgencyLevel && urgencyLevel !== 'all') url += `&urgency_level=${encodeURIComponent(urgencyLevel)}`;
      if (category) url += `&category=${encodeURIComponent(category)}`;
      if (onlyReorder) url += `&only_reorder=true`;

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка загрузки данных');
      }

      const data = await response.json();
      setRecommendations(data.recommendations || []);
    } catch (error) {
      console.error('Ошибка загрузки рекомендаций:', error);
    } finally {
      setLoading(false);
    }
  };

  const recalculateRecommendations = async () => {
    try {
      setRecalculating(true);
      const response = await fetch('/api/analytics/inventory/purchase-recommendations/recalculate?analysis_period_days=90&lead_time_days=14&min_avg_daily_sales=0.01', {
        method: 'POST'
      });
      
      if (!response.ok) {
        throw new Error('Ошибка пересчёта рекомендаций');
      }

      const data = await response.json();
      console.log('Рекомендации пересчитаны:', data.message);
      
      // Обновляем список после пересчёта
      await fetchRecommendations();
    } catch (error) {
      console.error('Ошибка пересчёта рекомендаций:', error);
    } finally {
      setRecalculating(false);
    }
  };

  const exportToExcel = async () => {
    try {
      let url = '/api/analytics/inventory/purchase-recommendations/export?';
      if (urgencyLevel && urgencyLevel !== 'all') url += `urgency_level=${encodeURIComponent(urgencyLevel)}&`;
      if (category) url += `category=${encodeURIComponent(category)}&`;
      if (onlyReorder) url += `only_reorder=true&`;

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка экспорта данных');
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `Рекомендации_по_закупкам_${new Date().toISOString().split('T')[0]}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Ошибка экспорта:', error);
      alert('Ошибка при экспорте данных');
    }
  };

  useEffect(() => {
    fetchRecommendations();
  }, [limit, urgencyLevel, category, onlyReorder]);

  const getUrgencyColor = (urgency?: string | null) => {
    switch (urgency) {
      case 'critical':
        return 'bg-red-100 text-red-800 border-red-300';
      case 'high':
        return 'bg-orange-100 text-orange-800 border-orange-300';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'low':
        return 'bg-blue-100 text-blue-800 border-blue-300';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  const getUrgencyLabel = (urgency?: string | null) => {
    switch (urgency) {
      case 'critical':
        return 'Критично';
      case 'high':
        return 'Высокий';
      case 'medium':
        return 'Средний';
      case 'low':
        return 'Низкий';
      default:
        return 'Неизвестно';
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Рекомендации по закупкам</CardTitle>
              <CardDescription>
                Товары, требующие заказа на основе оборачиваемости и остатков
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={exportToExcel}
                variant="outline"
                size="sm"
              >
                <Download className="h-4 w-4 mr-2" />
                Экспорт в Excel
              </Button>
              <Button
                onClick={recalculateRecommendations}
                disabled={recalculating}
                variant="outline"
                size="sm"
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${recalculating ? 'animate-spin' : ''}`} />
                Пересчитать
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Фильтры */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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
                  Уровень срочности
                </label>
                <Select value={urgencyLevel} onValueChange={setUrgencyLevel}>
                  <SelectTrigger>
                    <SelectValue placeholder="Все уровни" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Все уровни</SelectItem>
                    <SelectItem value="critical">Критично</SelectItem>
                    <SelectItem value="high">Высокий</SelectItem>
                    <SelectItem value="medium">Средний</SelectItem>
                    <SelectItem value="low">Низкий</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
                  Категория
                </label>
                <input
                  type="text"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="Все категории"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                />
              </div>
              <div className="flex items-end">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={onlyReorder}
                    onChange={(e) => setOnlyReorder(e.target.checked)}
                    className="rounded border-gray-300"
                  />
                  <span className="text-sm text-gray-700">Только требующие заказа</span>
                </label>
              </div>
            </div>

            {/* Таблица рекомендаций */}
            {loading ? (
              <div className="text-center py-8 text-gray-500">Загрузка...</div>
            ) : recommendations.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                Нет рекомендаций с указанными критериями
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="bg-gray-50 border-b">
                      <th className="text-left p-2 font-semibold text-gray-700">Товар</th>
                      <th className="text-left p-2 font-semibold text-gray-700">Артикул</th>
                      <th className="text-left p-2 font-semibold text-gray-700">Категория</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Текущий остаток</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Рекомендуемый остаток</th>
                      <th className="text-right p-2 font-semibold text-gray-700">К заказу</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Дней остатка</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Оборачиваемость (дни)</th>
                      <th className="text-center p-2 font-semibold text-gray-700">Срочность</th>
                      <th className="text-center p-2 font-semibold text-gray-700">Дата заказа</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recommendations.map((rec, index) => (
                      <tr key={`${rec.product_article || 'unknown'}-${rec.product_id_1c || ''}-${index}`} className="border-b hover:bg-gray-50">
                        <td className="p-2">
                          <div className="font-medium text-gray-900">
                            {rec.product_name || 'Без названия'}
                          </div>
                          {rec.brand && (
                            <div className="text-sm text-gray-500">{rec.brand}</div>
                          )}
                        </td>
                        <td className="p-2 text-gray-700">{rec.product_article || '-'}</td>
                        <td className="p-2 text-gray-700">{rec.category || '-'}</td>
                        <td className="p-2 text-right text-gray-700">
                          {rec.current_stock?.toLocaleString('ru-RU') || '0'}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {rec.recommended_stock?.toLocaleString('ru-RU') || '-'}
                        </td>
                        <td className="p-2 text-right">
                          {rec.reorder_quantity && rec.reorder_quantity > 0 ? (
                            <span className="font-semibold text-blue-600">
                              {rec.reorder_quantity.toLocaleString('ru-RU')}
                            </span>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {rec.days_of_stock ? rec.days_of_stock.toFixed(1) : '-'}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {rec.turnover_days ? rec.turnover_days.toFixed(1) : '-'}
                        </td>
                        <td className="p-2 text-center">
                          <span className={`px-2 py-1 rounded text-xs font-medium border ${getUrgencyColor(rec.urgency_level)}`}>
                            {getUrgencyLabel(rec.urgency_level)}
                          </span>
                        </td>
                        <td className="p-2 text-center text-sm text-gray-600">
                          {rec.recommended_date ? new Date(rec.recommended_date).toLocaleDateString('ru-RU') : '-'}
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

      {/* Срочные алерты и неликвид */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ReorderAlertsSection />
        <DeadStockSection />
      </div>
    </div>
  );
}

function ReorderAlertsSection() {
  const [alerts, setAlerts] = useState<PurchaseRecommendation[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/analytics/inventory/reorder-alerts?limit=20');
        if (!response.ok) {
          throw new Error('Ошибка загрузки данных');
        }
        const data = await response.json();
        setAlerts(data.alerts || []);
      } catch (error) {
        console.error('Ошибка загрузки алертов:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchAlerts();
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-500" />
          Срочные заказы
        </CardTitle>
        <CardDescription>
          Товары, требующие немедленного заказа
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="text-center py-4 text-gray-500">Загрузка...</div>
        ) : alerts.length === 0 ? (
          <div className="text-center py-4 text-gray-500">Нет срочных заказов</div>
        ) : (
          <div className="space-y-2">
            {alerts.map((alert, index) => (
              <div key={`${alert.product_article || 'unknown'}-${alert.product_id_1c || ''}-${index}`} className="flex items-center justify-between p-2 bg-red-50 rounded border border-red-200">
                <div>
                  <div className="font-medium text-gray-900">{alert.product_name || 'Без названия'}</div>
                  <div className="text-sm text-gray-600">
                    Остаток: {alert.current_stock?.toLocaleString('ru-RU') || '0'} | 
                    К заказу: {alert.reorder_quantity?.toLocaleString('ru-RU') || '0'}
                  </div>
                </div>
                <ShoppingCart className="h-5 w-5 text-red-500" />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DeadStockSection() {
  const [deadStock, setDeadStock] = useState<PurchaseRecommendation[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchDeadStock = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/analytics/inventory/dead-stock?limit=20&min_days=180');
        if (!response.ok) {
          throw new Error('Ошибка загрузки данных');
        }
        const data = await response.json();
        setDeadStock(data.dead_stock || []);
      } catch (error) {
        console.error('Ошибка загрузки неликвида:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchDeadStock();
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingDown className="h-5 w-5 text-orange-500" />
          Неликвидные товары
        </CardTitle>
        <CardDescription>
          Товары с очень низкой оборачиваемостью
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="text-center py-4 text-gray-500">Загрузка...</div>
        ) : deadStock.length === 0 ? (
          <div className="text-center py-4 text-gray-500">Нет неликвидных товаров</div>
        ) : (
          <div className="space-y-2">
            {deadStock.map((item, index) => (
              <div key={`${item.product_article || 'unknown'}-${item.product_id_1c || ''}-${index}`} className="flex items-center justify-between p-2 bg-orange-50 rounded border border-orange-200">
                <div>
                  <div className="font-medium text-gray-900">{item.product_name || 'Без названия'}</div>
                  <div className="text-sm text-gray-600">
                    Остаток: {item.current_stock?.toLocaleString('ru-RU') || '0'} | 
                    Оборачиваемость: {item.turnover_days?.toFixed(0) || '-'} дней
                  </div>
                </div>
                <TrendingDown className="h-5 w-5 text-orange-500" />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
