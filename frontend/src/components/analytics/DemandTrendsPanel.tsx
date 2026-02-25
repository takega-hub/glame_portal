"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw, TrendingUp, TrendingDown, Minus, BarChart3 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";

interface TrendAnalysis {
  product_id_1c?: string | null;
  product_name?: string | null;
  product_article?: string | null;
  category?: string | null;
  trend_direction?: string | null;
  trend_value?: number | null;
  percent_change?: number | null;
  first_half_avg?: number | null;
  second_half_avg?: number | null;
  overall_avg?: number | null;
}

interface TrendResponse {
  status?: string;
  message?: string;
  period_days?: number;
  trend_direction?: string;
  trend_value?: number;
  percent_change?: number;
  first_half_avg?: number;
  second_half_avg?: number;
  overall_avg?: number;
  products?: TrendAnalysis[];
}

export function DemandTrendsPanel() {
  const [trendData, setTrendData] = useState<TrendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState<number>(90);
  const [category, setCategory] = useState<string>("all");
  const [productId, setProductId] = useState<string>("");
  const [categories, setCategories] = useState<string[]>([]);

  useEffect(() => {
    fetchTrends();
    fetchCategories();
  }, [days, category, productId]);

  const fetchCategories = async () => {
    try {
      const response = await fetch('/api/analytics/inventory/categories');
      if (response.ok) {
        const data = await response.json();
        setCategories(data.categories || []);
      }
    } catch (error) {
      console.error('Ошибка загрузки категорий:', error);
    }
  };

  const fetchTrends = async () => {
    try {
      setLoading(true);
      let url = `/api/analytics/inventory/demand-trends?days=${days}`;
      if (category && category !== 'all') {
        url += `&category=${encodeURIComponent(category)}`;
      }
      if (productId) {
        url += `&product_id_1c=${encodeURIComponent(productId)}`;
      }

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка загрузки трендов');
      }

      const data = await response.json();
      setTrendData(data);
    } catch (error) {
      console.error('Ошибка загрузки трендов:', error);
    } finally {
      setLoading(false);
    }
  };

  const getTrendIcon = (direction?: string | null) => {
    if (!direction) return <Minus className="h-4 w-4 text-gray-400" />;
    if (direction === 'растущий') return <TrendingUp className="h-4 w-4 text-green-600" />;
    if (direction === 'падающий') return <TrendingDown className="h-4 w-4 text-red-600" />;
    return <Minus className="h-4 w-4 text-gray-400" />;
  };

  const getTrendColor = (direction?: string | null) => {
    if (!direction) return 'bg-gray-100 text-gray-800';
    if (direction === 'растущий') return 'bg-green-100 text-green-800';
    if (direction === 'падающий') return 'bg-red-100 text-red-800';
    return 'bg-blue-100 text-blue-800';
  };

  const formatNumber = (value?: number | null) => {
    if (value === null || value === undefined) return '—';
    return value.toFixed(2);
  };

  const formatPercent = (value?: number | null) => {
    if (value === null || value === undefined) return '—';
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(1)}%`;
  };

  const getPercentColor = (value?: number | null) => {
    if (!value) return 'text-gray-600';
    if (value > 10) return 'text-green-600 font-semibold';
    if (value > 0) return 'text-green-500';
    if (value < -10) return 'text-red-600 font-semibold';
    return 'text-red-500';
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Анализ трендов спроса</CardTitle>
              <CardDescription>
                Определение направления тренда (растущий/падающий/стабильный) и процент изменения спроса
              </CardDescription>
            </div>
            <Button onClick={fetchTrends} disabled={loading} variant="outline" size="sm">
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Обновить
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* Фильтры */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div>
              <Label htmlFor="days">Период анализа (дни)</Label>
              <Input
                id="days"
                type="number"
                min="14"
                max="365"
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="category">Категория</Label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger id="category" className="mt-1">
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
              <Label htmlFor="product-id">ID товара (1С)</Label>
              <Input
                id="product-id"
                type="text"
                value={productId}
                onChange={(e) => setProductId(e.target.value)}
                placeholder="Опционально"
                className="mt-1"
              />
            </div>
          </div>

          {/* Общая статистика тренда */}
          {trendData && trendData.status === 'success' && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              <Card>
                <CardContent className="pt-4">
                  <div className="text-sm text-gray-500">Направление тренда</div>
                  <div className="flex items-center gap-2 mt-2">
                    {getTrendIcon(trendData.trend_direction)}
                    <Badge className={getTrendColor(trendData.trend_direction)}>
                      {trendData.trend_direction || '—'}
                    </Badge>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <div className="text-sm text-gray-500">Изменение</div>
                  <div className={`text-2xl font-bold ${getPercentColor(trendData.percent_change)}`}>
                    {formatPercent(trendData.percent_change)}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <div className="text-sm text-gray-500">Среднее (первая половина)</div>
                  <div className="text-2xl font-bold">
                    {formatNumber(trendData.first_half_avg)}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <div className="text-sm text-gray-500">Среднее (вторая половина)</div>
                  <div className="text-2xl font-bold">
                    {formatNumber(trendData.second_half_avg)}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Детальная информация */}
          {trendData && trendData.status === 'success' && (
            <Card className="mb-6">
              <CardHeader>
                <CardTitle className="text-lg">Детальный анализ</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <div className="text-sm text-gray-500 mb-1">Период анализа</div>
                    <div className="text-lg font-semibold">{trendData.period_days} дней</div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-500 mb-1">Значение тренда</div>
                    <div className="text-lg font-semibold">{formatNumber(trendData.trend_value)}</div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-500 mb-1">Общее среднее</div>
                    <div className="text-lg font-semibold">{formatNumber(trendData.overall_avg)}</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Сообщение об ошибке или недостатке данных */}
          {loading ? (
            <p className="text-center py-8 text-gray-500">Загрузка анализа трендов...</p>
          ) : !trendData ? (
            <p className="text-center py-8 text-gray-500">Нет данных для анализа</p>
          ) : trendData.status === 'insufficient_data' ? (
            <div className="text-center py-8">
              <BarChart3 className="h-12 w-12 text-gray-400 mx-auto mb-2" />
              <p className="text-gray-500">{trendData.message}</p>
            </div>
          ) : trendData.status === 'success' ? (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-green-600" />
                <p className="text-green-800 font-medium">Анализ трендов успешно выполнен</p>
              </div>
              <p className="text-green-700 text-sm mt-2">
                Данные за период {trendData.period_days} дней показывают {trendData.trend_direction} тренд
                {trendData.percent_change !== null && trendData.percent_change !== undefined && (
                  <span className="font-semibold"> ({formatPercent(trendData.percent_change)})</span>
                )}
              </p>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
