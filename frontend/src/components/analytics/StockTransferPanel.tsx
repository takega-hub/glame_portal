"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw, Download, TruckIcon, AlertTriangle, TrendingUp } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface TransferRecommendation {
  product_article?: string | null;
  product_name?: string | null;
  category?: string | null;
  brand?: string | null;
  from_store?: string | null;
  to_store_name?: string | null;
  to_store_id?: string | null;
  current_stock?: number | null;
  warehouse_stock?: number | null;
  recommended_transfer?: number | null;
  days_until_stockout?: number | null;
  avg_daily_sales?: number | null;
  priority?: string | null;
  is_hot_product?: boolean | null;
  reason?: string | null;
}

export function StockTransferPanel() {
  const [recommendations, setRecommendations] = useState<TransferRecommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [limit, setLimit] = useState<number>(100);
  const [priority, setPriority] = useState<string>("all");
  const [storeId, setStoreId] = useState<string>("");
  const [category, setCategory] = useState<string>("");

  const fetchRecommendations = async () => {
    try {
      setLoading(true);
      let url = '/api/analytics/inventory/transfer-recommendations?';
      url += `limit=${limit}`;
      if (priority && priority !== 'all') url += `&priority=${encodeURIComponent(priority)}`;
      if (storeId) url += `&store_id=${encodeURIComponent(storeId)}`;
      if (category) url += `&category=${encodeURIComponent(category)}`;

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

  const exportToExcel = async () => {
    try {
      let url = '/api/analytics/inventory/transfer-recommendations/export?';
      if (priority && priority !== 'all') url += `priority=${encodeURIComponent(priority)}&`;
      if (storeId) url += `store_id=${encodeURIComponent(storeId)}&`;

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка экспорта данных');
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `Перемещения_товаров_${new Date().toISOString().split('T')[0]}.xlsx`;
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
  }, [limit, priority, storeId, category]);

  const getPriorityColor = (priority?: string | null) => {
    switch (priority) {
      case 'critical':
        return 'bg-red-100 text-red-800 border-red-300';
      case 'high':
        return 'bg-orange-100 text-orange-800 border-orange-300';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  const getPriorityLabel = (priority?: string | null) => {
    switch (priority) {
      case 'critical':
        return 'Критично';
      case 'high':
        return 'Высокий';
      case 'medium':
        return 'Средний';
      default:
        return 'Низкий';
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <TruckIcon className="h-5 w-5" />
                Перемещение товаров
              </CardTitle>
              <CardDescription>
                AI-рекомендации по перемещению товаров со склада в магазины
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
                onClick={fetchRecommendations}
                disabled={loading}
                variant="outline"
                size="sm"
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                Обновить
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
                <Select value={limit.toString()} onValueChange={(value) => setLimit(parseInt(value))}>
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
                  Приоритет
                </label>
                <Select value={priority} onValueChange={setPriority}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Все уровни</SelectItem>
                    <SelectItem value="critical">Критично</SelectItem>
                    <SelectItem value="high">Высокий</SelectItem>
                    <SelectItem value="medium">Средний</SelectItem>
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
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            {/* Таблица рекомендаций */}
            {loading ? (
              <div className="text-center py-8">
                <RefreshCw className="h-8 w-8 animate-spin mx-auto text-blue-500" />
                <p className="mt-2 text-gray-500">Загрузка рекомендаций...</p>
              </div>
            ) : recommendations.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                Нет рекомендаций с указанными критериями
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="p-2 text-left text-xs font-medium text-gray-500 uppercase">Товар</th>
                      <th className="p-2 text-left text-xs font-medium text-gray-500 uppercase">Артикул</th>
                      <th className="p-2 text-left text-xs font-medium text-gray-500 uppercase">Куда</th>
                      <th className="p-2 text-right text-xs font-medium text-gray-500 uppercase">Остаток</th>
                      <th className="p-2 text-right text-xs font-medium text-gray-500 uppercase">На складе</th>
                      <th className="p-2 text-right text-xs font-medium text-gray-500 uppercase">Переместить</th>
                      <th className="p-2 text-right text-xs font-medium text-gray-500 uppercase">Дней до дефицита</th>
                      <th className="p-2 text-center text-xs font-medium text-gray-500 uppercase">Приоритет</th>
                      <th className="p-2 text-left text-xs font-medium text-gray-500 uppercase">Причина</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recommendations.map((rec, index) => (
                      <tr key={index} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="p-2">
                          <div className="flex items-center gap-2">
                            <div>
                              <div className="font-medium text-gray-900">{rec.product_name || '-'}</div>
                              {rec.brand && (
                                <div className="text-sm text-gray-500">{rec.brand}</div>
                              )}
                              {rec.is_hot_product && (
                                <div className="flex items-center gap-1 text-xs text-orange-600 mt-1">
                                  <TrendingUp className="h-3 w-3" />
                                  <span>Популярный товар</span>
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="p-2 text-gray-700">{rec.product_article || '-'}</td>
                        <td className="p-2 text-gray-700">{rec.to_store_name || '-'}</td>
                        <td className="p-2 text-right text-gray-700">
                          {rec.current_stock != null ? rec.current_stock.toLocaleString('ru-RU') : '-'}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {rec.warehouse_stock != null ? rec.warehouse_stock.toLocaleString('ru-RU') : '-'}
                        </td>
                        <td className="p-2 text-right">
                          {rec.recommended_transfer && rec.recommended_transfer > 0 ? (
                            <span className="font-semibold text-blue-600">
                              {rec.recommended_transfer.toLocaleString('ru-RU')}
                            </span>
                          ) : (
                            '-'
                          )}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {rec.days_until_stockout ? rec.days_until_stockout.toFixed(1) : '-'}
                        </td>
                        <td className="p-2 text-center">
                          <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${getPriorityColor(rec.priority)}`}>
                            {rec.priority === 'critical' && <AlertTriangle className="h-3 w-3 mr-1" />}
                            {getPriorityLabel(rec.priority)}
                          </span>
                        </td>
                        <td className="p-2 text-sm text-gray-600">{rec.reason || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
