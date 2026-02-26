"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetchJson } from '@/lib/utils';

type Period = "today" | "yesterday" | "week" | "month" | "quarter" | "year" | "custom";

interface Channel {
  channel: string;
  total_revenue: number;
  total_quantity: number;
  total_orders: number;
  unique_customers: number;
  unique_products: number;
  avg_price?: number;
  avg_order_value?: number;
  revenue_share: number;
  quantity_share: number;
  orders_share: number;
  revenue_without_discount?: number;
  discount_amount?: number;
  discount_percent?: number;
}

export function ChannelAnalyticsPanel() {
  const [comparison, setComparison] = useState<Channel[]>([]);
  const [conversion, setConversion] = useState<any>(null);
  const [trends, setTrends] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState<Period>("month");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [activeTab, setActiveTab] = useState<string>("comparison");

  const fetchComparison = async () => {
    try {
      setLoading(true);
      let url = '/api/analytics/channels/comparison?';
      
      if (period === "custom" && startDate && endDate) {
        url += `start_date=${startDate}&end_date=${endDate}`;
      } else if (period !== "custom") {
        url += `period=${period}`;
      } else {
        url += 'days=30';
      }
      
      const { data } = await fetchJson<{ channels?: Channel[] }>(url);
      if (data.channels) {
        setComparison(data.channels);
      }
    } catch (err) {
      console.error('Ошибка загрузки сравнения каналов:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchConversion = async () => {
    try {
      setLoading(true);
      let url = '/api/analytics/channels/conversion?';
      
      if (period === "custom" && startDate && endDate) {
        url += `start_date=${startDate}&end_date=${endDate}`;
      } else if (period !== "custom") {
        url += `period=${period}`;
      } else {
        url += 'days=30';
      }
      
      const { data } = await fetchJson<{ channels?: unknown }>(url);
      if (data.channels) {
        setConversion(data);
      }
    } catch (err) {
      console.error('Ошибка загрузки конверсии:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTrends = async () => {
    try {
      setLoading(true);
      let url = '/api/analytics/channels/trends?';
      
      if (period === "custom" && startDate && endDate) {
        url += `start_date=${startDate}&end_date=${endDate}&`;
      } else if (period !== "custom") {
        url += `period=${period}&`;
      } else {
        url += 'days=30&';
      }
      
      url += 'period_type=week';
      
      const { data } = await fetchJson<{ trends?: unknown }>(url);
      if (data.trends) {
        setTrends(data);
      }
    } catch (err) {
      console.error('Ошибка загрузки трендов:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "comparison") {
      fetchComparison();
    } else if (activeTab === "conversion") {
      fetchConversion();
    } else if (activeTab === "trends") {
      fetchTrends();
    }
  }, [period, startDate, endDate, activeTab]);

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

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency: 'RUB',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  const formatPercent = (value: number | null | undefined) => {
    if (value == null || typeof value !== 'number') return '—';
    return `${value.toFixed(1)}%`;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Аналитика каналов продаж</span>
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
            <Button onClick={() => {
              if (activeTab === "comparison") fetchComparison();
              else if (activeTab === "conversion") fetchConversion();
              else if (activeTab === "trends") fetchTrends();
            }} disabled={loading} size="sm" variant="outline">
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Обновить
            </Button>
          </div>
        </CardTitle>
        <CardDescription>
          Анализ каналов продаж за {getPeriodLabel(period).toLowerCase()}
          {period === "custom" && startDate && endDate && ` (${startDate} - ${endDate})`}
        </CardDescription>
        {period === "custom" && (
          <div className="flex gap-2 mt-2">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="px-3 py-1 border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="px-3 py-1 border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
          </div>
        )}
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="comparison" value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="comparison">Сравнение</TabsTrigger>
            <TabsTrigger value="conversion">Конверсия</TabsTrigger>
            <TabsTrigger value="trends">Тренды</TabsTrigger>
          </TabsList>
          
          <TabsContent value="comparison" className="mt-4">
            {loading && !comparison.length ? (
              <div>Загрузка...</div>
            ) : comparison.length === 0 ? (
              <div className="text-center py-8 text-gray-500">Нет данных</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left p-2 font-semibold text-gray-700">Канал</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Выручка</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Доля выручки</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Количество</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Заказы</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Средний чек</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Покупатели</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Товары</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.map((channel, index) => (
                      <tr key={channel.channel || index} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="p-2 font-medium text-gray-900">{channel.channel || '—'}</td>
                        <td className="p-2 text-right font-semibold text-gray-900">
                          {formatCurrency(channel.total_revenue)}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {formatPercent(channel.revenue_share)}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {channel.total_quantity != null ? channel.total_quantity.toLocaleString('ru-RU', { maximumFractionDigits: 1 }) : '—'}
                        </td>
                        <td className="p-2 text-right text-gray-700">{channel.total_orders}</td>
                        <td className="p-2 text-right text-gray-700">
                          {channel.avg_order_value ? formatCurrency(channel.avg_order_value) : '—'}
                        </td>
                        <td className="p-2 text-right text-gray-700">{channel.unique_customers}</td>
                        <td className="p-2 text-right text-gray-700">{channel.unique_products}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>
          
          <TabsContent value="conversion" className="mt-4">
            {loading && !conversion ? (
              <div>Загрузка...</div>
            ) : !conversion?.channels || conversion.channels.length === 0 ? (
              <div className="text-center py-8 text-gray-500">Нет данных</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left p-2 font-semibold text-gray-700">Канал</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Заказы</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Покупатели</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Средний чек</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Товаров/заказ</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Повторные</th>
                      <th className="text-right p-2 font-semibold text-gray-700">% повторных</th>
                    </tr>
                  </thead>
                  <tbody>
                    {conversion.channels.map((channel: any, index: number) => (
                      <tr key={channel.channel || index} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="p-2 font-medium text-gray-900">{channel.channel || '—'}</td>
                        <td className="p-2 text-right text-gray-700">{channel.total_orders}</td>
                        <td className="p-2 text-right text-gray-700">{channel.unique_customers}</td>
                        <td className="p-2 text-right text-gray-700">
                          {channel.avg_order_value ? formatCurrency(channel.avg_order_value) : '—'}
                        </td>
                        <td className="p-2 text-right text-gray-700">
                          {channel.avg_items_per_order != null && typeof channel.avg_items_per_order === 'number' ? channel.avg_items_per_order.toFixed(1) : '—'}
                        </td>
                        <td className="p-2 text-right text-gray-700">{channel.repeat_customers || 0}</td>
                        <td className="p-2 text-right text-gray-700">
                          {channel.repeat_purchase_rate ? formatPercent(channel.repeat_purchase_rate) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>
          
          <TabsContent value="trends" className="mt-4">
            {loading && !trends ? (
              <div>Загрузка...</div>
            ) : !trends?.trends || trends.trends.length === 0 ? (
              <div className="text-center py-8 text-gray-500">Нет данных</div>
            ) : (
              <div className="space-y-4">
                <div className="text-sm text-gray-600 mb-4">
                  Каналы: {trends.channels?.join(', ') || '—'}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="border-b border-gray-200">
                        <th className="text-left p-2 font-semibold text-gray-700">Период</th>
                        {trends.channels?.map((channel: string) => (
                          <th key={channel} className="text-right p-2 font-semibold text-gray-700" colSpan={3}>
                            {channel}
                          </th>
                        ))}
                      </tr>
                      <tr className="border-b border-gray-200">
                        <th className="text-left p-2 font-semibold text-gray-700"></th>
                        {trends.channels?.map((channel: string) => (
                          <React.Fragment key={channel}>
                            <th className="text-right p-2 text-xs text-gray-600">Выручка</th>
                            <th className="text-right p-2 text-xs text-gray-600">Заказы</th>
                            <th className="text-right p-2 text-xs text-gray-600">Покупатели</th>
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {trends.trends.map((trend: any, index: number) => (
                        <tr key={index} className="border-b border-gray-100 hover:bg-gray-50">
                          <td className="p-2 font-medium text-gray-900">{trend.period}</td>
                          {trends.channels?.map((channel: string) => {
                            const channelData = trend.channels?.[channel] || {};
                            return (
                              <React.Fragment key={channel}>
                                <td className="p-2 text-right text-gray-700">
                                  {formatCurrency(channelData.total_revenue || 0)}
                                </td>
                                <td className="p-2 text-right text-gray-700">
                                  {channelData.total_orders || 0}
                                </td>
                                <td className="p-2 text-right text-gray-700">
                                  {channelData.unique_customers || 0}
                                </td>
                              </React.Fragment>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
