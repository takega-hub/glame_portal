"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw, Calendar, TrendingUp } from "lucide-react";
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

interface SeasonalForecast {
  month?: string;
  forecasted_demand?: number;
  historical_avg?: number;
  change_percent?: number;
  seasonality_factor?: number;
}

interface SeasonalForecastResponse {
  status?: string;
  message?: string;
  months_ahead?: number;
  forecasts?: SeasonalForecast[];
  seasonal_pattern?: string;
  total_forecast?: number;
}

export function SeasonalForecastPanel() {
  const [forecastData, setForecastData] = useState<SeasonalForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [monthsAhead, setMonthsAhead] = useState<number>(3);
  const [category, setCategory] = useState<string>("all");
  const [categories, setCategories] = useState<string[]>([]);

  useEffect(() => {
    fetchForecast();
    fetchCategories();
  }, [monthsAhead, category]);

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

  const fetchForecast = async () => {
    try {
      setLoading(true);
      let url = `/api/analytics/inventory/seasonal-forecast?months_ahead=${monthsAhead}`;
      if (category && category !== 'all') {
        url += `&category=${encodeURIComponent(category)}`;
      }

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Ошибка загрузки сезонного прогноза');
      }

      const data = await response.json();
      setForecastData(data);
    } catch (error) {
      console.error('Ошибка загрузки сезонного прогноза:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatNumber = (value?: number | null) => {
    if (value === null || value === undefined) return '—';
    return Math.round(value).toLocaleString('ru-RU');
  };

  const formatPercent = (value?: number | null) => {
    if (value === null || value === undefined) return '—';
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(1)}%`;
  };

  const getChangeColor = (change?: number | null) => {
    if (!change) return 'text-gray-600';
    if (change > 10) return 'text-green-600 font-semibold';
    if (change > 0) return 'text-green-500';
    if (change < -10) return 'text-red-600 font-semibold';
    return 'text-red-500';
  };

  const getMonthName = (monthKey: string) => {
    const [year, month] = monthKey.split('-');
    const date = new Date(parseInt(year), parseInt(month) - 1, 1);
    return date.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Сезонное прогнозирование</CardTitle>
              <CardDescription>
                Прогноз спроса на несколько месяцев вперёд с учётом сезонных паттернов
              </CardDescription>
            </div>
            <Button onClick={fetchForecast} disabled={loading} variant="outline" size="sm">
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Обновить
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* Фильтры */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div>
              <Label htmlFor="months-ahead">Месяцев прогноза</Label>
              <Select value={monthsAhead.toString()} onValueChange={(v) => setMonthsAhead(Number(v))}>
                <SelectTrigger id="months-ahead" className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1 месяц</SelectItem>
                  <SelectItem value="2">2 месяца</SelectItem>
                  <SelectItem value="3">3 месяца</SelectItem>
                  <SelectItem value="6">6 месяцев</SelectItem>
                  <SelectItem value="12">12 месяцев</SelectItem>
                </SelectContent>
              </Select>
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
          </div>

          {/* Статистика */}
          {forecastData && forecastData.status === 'success' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <Card>
                <CardContent className="pt-4">
                  <div className="text-sm text-gray-500">Общий прогноз</div>
                  <div className="text-2xl font-bold">
                    {formatNumber(forecastData.total_forecast)}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <div className="text-sm text-gray-500">Период прогноза</div>
                  <div className="text-2xl font-bold">
                    {forecastData.months_ahead} {forecastData.months_ahead === 1 ? 'месяц' : 'месяцев'}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4">
                  <div className="text-sm text-gray-500">Сезонный паттерн</div>
                  <div className="text-lg font-semibold">
                    <Badge variant="outline" className="mt-1">
                      {forecastData.seasonal_pattern || '—'}
                    </Badge>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Таблица прогнозов */}
          {loading ? (
            <p className="text-center py-8 text-gray-500">Загрузка сезонного прогноза...</p>
          ) : !forecastData ? (
            <p className="text-center py-8 text-gray-500">Нет данных для прогнозирования</p>
          ) : forecastData.status === 'no_data' ? (
            <div className="text-center py-8">
              <p className="text-gray-500 mb-2">{forecastData.message}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Месяц</TableHead>
                    <TableHead className="text-right">Прогноз спроса</TableHead>
                    <TableHead className="text-right">Историческое среднее</TableHead>
                    <TableHead className="text-right">Изменение</TableHead>
                    <TableHead className="text-right">Сезонный фактор</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {forecastData.forecasts?.map((forecast, index) => (
                    <TableRow key={`${forecast.month || 'unknown'}-${index}`}>
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-2">
                          <Calendar className="h-4 w-4 text-gray-400" />
                          {forecast.month ? getMonthName(forecast.month) : '—'}
                        </div>
                      </TableCell>
                      <TableCell className="text-right font-semibold">
                        {formatNumber(forecast.forecasted_demand)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatNumber(forecast.historical_avg)}
                      </TableCell>
                      <TableCell className={`text-right ${getChangeColor(forecast.change_percent)}`}>
                        {forecast.change_percent !== null && forecast.change_percent !== undefined ? (
                          <div className="flex items-center justify-end gap-1">
                            {forecast.change_percent > 0 ? (
                              <TrendingUp className="h-4 w-4" />
                            ) : forecast.change_percent < 0 ? (
                              <TrendingUp className="h-4 w-4 rotate-180" />
                            ) : null}
                            {formatPercent(forecast.change_percent)}
                          </div>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {forecast.seasonality_factor ? (
                          <Badge variant="outline">
                            {forecast.seasonality_factor.toFixed(2)}x
                          </Badge>
                        ) : (
                          '—'
                        )}
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
