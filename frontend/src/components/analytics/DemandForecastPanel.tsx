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

interface DemandForecast {
  product_id_1c?: string | null;
  product_id?: string | null;
  product_name?: string | null;
  product_article?: string | null;
  category?: string | null;
  brand?: string | null;
  forecast_days?: number | null;
  forecasted_demand?: number | null;
  forecasted_daily_avg?: number | null;
  confidence_interval?: {
    lower?: number;
    upper?: number;
  };
  forecast_accuracy?: number | null;
  trend?: number | null;
  seasonality?: string | null;
  historical_avg_daily?: number | null;
  weighted_avg_daily?: number | null;
  moving_avg_7_days?: number | null;
  moving_avg_30_days?: number | null;
  volatility?: number | null;
}

export function DemandForecastPanel() {
  const [forecasts, setForecasts] = useState<DemandForecast[]>([]);
  const [loading, setLoading] = useState(false);
  const [forecastDays, setForecastDays] = useState<number>(30);
  const [historyDays, setHistoryDays] = useState<number>(90);
  const [category, setCategory] = useState<string>("all");
  const [productId, setProductId] = useState<string>("");
  const [categories, setCategories] = useState<string[]>([]);

  useEffect(() => {
    fetchForecasts();
    fetchCategories();
  }, [forecastDays, historyDays, category, productId]);

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

  const fetchForecasts = async () => {
    try {
      setLoading(true);
      let url = `/api/analytics/inventory/demand-forecast?forecast_days=${forecastDays}&history_days=${historyDays}`;
      if (category && category !== 'all') {
        url += `&category=${encodeURIComponent(category)}`;
      }
      if (productId) {
        url += `&product_id_1c=${encodeURIComponent(productId)}`;
      }

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка загрузки прогнозов');
      }

      const data = await response.json();
      setForecasts(data.forecasts || []);
    } catch (error) {
      console.error('Ошибка загрузки прогнозов:', error);
    } finally {
      setLoading(false);
    }
  };

  const getTrendIcon = (trend?: number | null) => {
    if (!trend) return <Minus className="h-4 w-4 text-gray-400" />;
    if (trend > 0) return <TrendingUp className="h-4 w-4 text-green-600" />;
    if (trend < 0) return <TrendingDown className="h-4 w-4 text-red-600" />;
    return <Minus className="h-4 w-4 text-gray-400" />;
  };

  const getTrendLabel = (trend?: number | null) => {
    if (!trend) return 'Стабильный';
    if (trend > 0.1) return 'Сильный рост';
    if (trend > 0) return 'Рост';
    if (trend < -0.1) return 'Сильное падение';
    return 'Падение';
  };

  const getAccuracyColor = (accuracy?: number | null) => {
    if (!accuracy) return 'bg-gray-100 text-gray-800';
    if (accuracy >= 80) return 'bg-green-100 text-green-800';
    if (accuracy >= 60) return 'bg-yellow-100 text-yellow-800';
    return 'bg-red-100 text-red-800';
  };

  const formatNumber = (value?: number | null) => {
    if (value === null || value === undefined) return '—';
    return value.toFixed(2);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Прогнозирование спроса</CardTitle>
              <CardDescription>
                Прогноз спроса на товары на основе исторических данных о продажах
              </CardDescription>
            </div>
            <Button onClick={fetchForecasts} disabled={loading} variant="outline" size="sm">
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Обновить
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* Фильтры */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div>
              <Label htmlFor="forecast-days">Дней прогноза</Label>
              <Input
                id="forecast-days"
                type="number"
                min="1"
                max="365"
                value={forecastDays}
                onChange={(e) => setForecastDays(Number(e.target.value))}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="history-days">Дней истории</Label>
              <Input
                id="history-days"
                type="number"
                min="7"
                max="365"
                value={historyDays}
                onChange={(e) => setHistoryDays(Number(e.target.value))}
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

          {/* Статистика */}
          {forecasts.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              <Card>
                <CardContent className="pt-4">
                  <div className="text-sm text-gray-500">Всего прогнозов</div>
                  <div className="text-2xl font-bold">{forecasts.length}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <div className="text-sm text-gray-500">Средний прогноз</div>
                  <div className="text-2xl font-bold">
                    {formatNumber(
                      forecasts.reduce((sum, f) => sum + (f.forecasted_demand || 0), 0) / forecasts.length
                    )}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <div className="text-sm text-gray-500">Средняя точность</div>
                  <div className="text-2xl font-bold">
                    {formatNumber(
                      forecasts.reduce((sum, f) => sum + (f.forecast_accuracy || 0), 0) / forecasts.length
                    )}%
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <div className="text-sm text-gray-500">Растущих трендов</div>
                  <div className="text-2xl font-bold">
                    {forecasts.filter((f) => (f.trend || 0) > 0).length}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Таблица прогнозов */}
          {loading ? (
            <p className="text-center py-8 text-gray-500">Загрузка прогнозов...</p>
          ) : forecasts.length === 0 ? (
            <p className="text-center py-8 text-gray-500">Нет данных для прогнозирования</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Товар</TableHead>
                    <TableHead>Артикул</TableHead>
                    <TableHead>Категория</TableHead>
                    <TableHead className="text-right">Прогноз спроса</TableHead>
                    <TableHead className="text-right">Средний/день</TableHead>
                    <TableHead className="text-right">Доверительный интервал</TableHead>
                    <TableHead className="text-right">Точность</TableHead>
                    <TableHead>Тренд</TableHead>
                    <TableHead>Сезонность</TableHead>
                    <TableHead className="text-right">Историческое среднее</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {forecasts.map((forecast, index) => (
                    <TableRow key={`${forecast.product_id_1c || 'unknown'}-${forecast.product_article || ''}-${index}`}>
                      <TableCell className="font-medium">
                        {forecast.product_name || '—'}
                      </TableCell>
                      <TableCell>{forecast.product_article || '—'}</TableCell>
                      <TableCell>{forecast.category || '—'}</TableCell>
                      <TableCell className="text-right font-semibold">
                        {formatNumber(forecast.forecasted_demand)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatNumber(forecast.forecasted_daily_avg)}
                      </TableCell>
                      <TableCell className="text-right text-sm">
                        {forecast.confidence_interval ? (
                          <span>
                            {formatNumber(forecast.confidence_interval.lower)} - {formatNumber(forecast.confidence_interval.upper)}
                          </span>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Badge className={getAccuracyColor(forecast.forecast_accuracy)}>
                          {formatNumber(forecast.forecast_accuracy)}%
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {getTrendIcon(forecast.trend)}
                          <span className="text-sm">{getTrendLabel(forecast.trend)}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {forecast.seasonality || '—'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {formatNumber(forecast.historical_avg_daily)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
