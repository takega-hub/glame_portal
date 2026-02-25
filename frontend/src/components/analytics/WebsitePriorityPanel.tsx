"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw, TrendingUp, Star, AlertCircle } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface WebsitePriorityProduct {
  product_id_1c?: string | null;
  product_id?: string | null;
  product_name?: string | null;
  product_article?: string | null;
  category?: string | null;
  brand?: string | null;
  priority_score?: number | null;
  priority_class?: string | null;
  turnover_score?: number | null;
  revenue_score?: number | null;
  margin_score?: number | null;
  stock_score?: number | null;
  trend_score?: number | null;
  image_score?: number | null;
  has_images?: boolean | null;
  is_recommended?: boolean | null;
  recommendation_reason?: string | null;
}

export function WebsitePriorityPanel() {
  const [products, setProducts] = useState<WebsitePriorityProduct[]>([]);
  const [loading, setLoading] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [limit, setLimit] = useState<number>(500);
  const [minPriority, setMinPriority] = useState<number>(30);
  const [category, setCategory] = useState<string>("");
  const [onlyRecommended, setOnlyRecommended] = useState<boolean>(false);

  const fetchPriorities = async () => {
    try {
      setLoading(true);
      let url = '/api/analytics/inventory/website-priority?';
      url += `limit=${limit}`;
      url += `&min_priority=${minPriority}`;
      if (category) url += `&category=${encodeURIComponent(category)}`;
      if (onlyRecommended) url += `&only_recommended=true`;

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка загрузки данных');
      }

      const data = await response.json();
      setProducts(data.products || []);
    } catch (error) {
      console.error('Ошибка загрузки приоритетов:', error);
    } finally {
      setLoading(false);
    }
  };

  const recalculatePriorities = async () => {
    try {
      setRecalculating(true);
      const response = await fetch('/api/analytics/inventory/website-priority/recalculate?analysis_period_days=90', {
        method: 'POST'
      });
      
      if (!response.ok) {
        throw new Error('Ошибка пересчёта приоритетов');
      }

      const data = await response.json();
      console.log('Приоритеты пересчитаны:', data.message);
      
      // Обновляем список после пересчёта
      await fetchPriorities();
    } catch (error) {
      console.error('Ошибка пересчёта приоритетов:', error);
    } finally {
      setRecalculating(false);
    }
  };

  useEffect(() => {
    fetchPriorities();
  }, [limit, minPriority, category, onlyRecommended]);

  const getPriorityClassColor = (priorityClass?: string | null) => {
    switch (priorityClass) {
      case 'high':
        return 'bg-green-100 text-green-800 border-green-300';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'low':
        return 'bg-gray-100 text-gray-800 border-gray-300';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  const getPriorityClassLabel = (priorityClass?: string | null) => {
    switch (priorityClass) {
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
              <CardTitle>Приоритизация товаров для сайта</CardTitle>
              <CardDescription>
                Товары, рекомендованные для приоритетной выкладки на сайте
              </CardDescription>
            </div>
            <Button
              onClick={recalculatePriorities}
              disabled={recalculating}
              variant="outline"
              size="sm"
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${recalculating ? 'animate-spin' : ''}`} />
              Пересчитать
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Фильтры */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
                  Количество товаров
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
                  Минимальный приоритет
                </label>
                <Select value={minPriority.toString()} onValueChange={(v) => setMinPriority(parseInt(v))}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">0</SelectItem>
                    <SelectItem value="30">30</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="70">70</SelectItem>
                    <SelectItem value="80">80</SelectItem>
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
                    checked={onlyRecommended}
                    onChange={(e) => setOnlyRecommended(e.target.checked)}
                    className="rounded border-gray-300"
                  />
                  <span className="text-sm text-gray-700">Только рекомендованные</span>
                </label>
              </div>
            </div>

            {/* Таблица товаров */}
            {loading ? (
              <div className="text-center py-8 text-gray-500">Загрузка...</div>
            ) : products.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                Нет товаров с указанными критериями
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="bg-gray-50 border-b">
                      <th className="text-left p-2 font-semibold text-gray-700">Товар</th>
                      <th className="text-left p-2 font-semibold text-gray-700">Артикул</th>
                      <th className="text-left p-2 font-semibold text-gray-700">Категория</th>
                      <th className="text-center p-2 font-semibold text-gray-700">Фото</th>
                      <th className="text-center p-2 font-semibold text-gray-700">Остатки</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Приоритет</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Класс</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Оборачиваемость</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Маржа</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Тренд</th>
                      <th className="text-center p-2 font-semibold text-gray-700">Рекомендация</th>
                    </tr>
                  </thead>
                  <tbody>
                    {products.map((product, index) => (
                      <tr key={`${product.product_id_1c || 'unknown'}-${product.product_article || ''}-${index}`} className="border-b hover:bg-gray-50">
                        <td className="p-2">
                          <div className="font-medium text-gray-900">
                            {product.product_name || 'Без названия'}
                          </div>
                          {product.brand && (
                            <div className="text-sm text-gray-500">{product.brand}</div>
                          )}
                        </td>
                        <td className="p-2 text-gray-700">{product.product_article || '-'}</td>
                        <td className="p-2 text-gray-700">{product.category || '-'}</td>
                        <td className="p-2 text-center">
                          {product.has_images ? (
                            <span className="px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-800 border border-green-300">
                              ✓ Есть
                            </span>
                          ) : (
                            <span className="px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-800 border border-red-300">
                              ✗ Нет
                            </span>
                          )}
                        </td>
                        <td className="p-2 text-center">
                          {product.stock_score && product.stock_score > 0 ? (
                            <span className="px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-800 border border-green-300">
                              ✓ Есть
                            </span>
                          ) : (
                            <span className="px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-800 border border-red-300">
                              ✗ Нет
                            </span>
                          )}
                        </td>
                        <td className="p-2 text-right">
                          <span className="font-semibold text-gray-900">
                            {product.priority_score?.toFixed(1) || '0.0'}
                          </span>
                        </td>
                        <td className="p-2 text-right">
                          <span className={`px-2 py-1 rounded text-xs font-medium border ${getPriorityClassColor(product.priority_class)}`}>
                            {getPriorityClassLabel(product.priority_class)}
                          </span>
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {product.turnover_score ? (product.turnover_score * 100).toFixed(1) + '%' : '-'}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {product.margin_score ? (product.margin_score * 100).toFixed(1) + '%' : '-'}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {product.trend_score ? (product.trend_score * 100).toFixed(1) + '%' : '-'}
                        </td>
                        <td className="p-2 text-center">
                          {product.is_recommended ? (
                            <div className="flex items-center justify-center">
                              <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" />
                              {product.recommendation_reason && (
                                <span className="ml-1 text-xs text-gray-600" title={product.recommendation_reason}>
                                  {product.recommendation_reason.substring(0, 20)}...
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Скрытые жемчужины */}
            <HiddenGemsSection />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function HiddenGemsSection() {
  const [gems, setGems] = useState<WebsitePriorityProduct[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchGems = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/analytics/inventory/hidden-gems?limit=20');
        if (!response.ok) {
          throw new Error('Ошибка загрузки данных');
        }
        const data = await response.json();
        setGems(data.products || []);
      } catch (error) {
        console.error('Ошибка загрузки скрытых жемчужин:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchGems();
  }, []);

  if (loading || gems.length === 0) {
    return null;
  }

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-blue-500" />
          Скрытые жемчужины
        </CardTitle>
        <CardDescription>
          Товары с высоким потенциалом роста, но низким текущим приоритетом
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-gray-50 border-b">
                <th className="text-left p-2 font-semibold text-gray-700">Товар</th>
                <th className="text-left p-2 font-semibold text-gray-700">Артикул</th>
                <th className="text-right p-2 font-semibold text-gray-700">Приоритет</th>
                <th className="text-right p-2 font-semibold text-gray-700">Маржа</th>
                <th className="text-right p-2 font-semibold text-gray-700">Тренд</th>
              </tr>
            </thead>
            <tbody>
              {gems.map((gem, index) => (
                <tr key={`${gem.product_id_1c || 'unknown'}-${gem.product_article || ''}-${index}`} className="border-b hover:bg-gray-50">
                  <td className="p-2">
                    <div className="font-medium text-gray-900">
                      {gem.product_name || 'Без названия'}
                    </div>
                    {gem.brand && (
                      <div className="text-sm text-gray-500">{gem.brand}</div>
                    )}
                  </td>
                  <td className="p-2 text-gray-700">{gem.product_article || '-'}</td>
                  <td className="p-2 text-right">
                    <span className="font-semibold text-gray-900">
                      {gem.priority_score?.toFixed(1) || '0.0'}
                    </span>
                  </td>
                  <td className="p-2 text-right text-gray-700">
                    {gem.margin_score ? (gem.margin_score * 100).toFixed(1) + '%' : '-'}
                  </td>
                  <td className="p-2 text-right text-gray-700">
                    {gem.trend_score ? (gem.trend_score * 100).toFixed(1) + '%' : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
