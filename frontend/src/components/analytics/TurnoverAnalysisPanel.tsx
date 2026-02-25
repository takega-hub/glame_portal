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

type Period = "today" | "yesterday" | "week" | "month" | "quarter" | "year" | "custom";

interface TurnoverProduct {
  product_id_1c?: string;
  product_name?: string;
  product_article?: string;
  category?: string;
  brand?: string;
  product_type?: string;
  store_id?: string;
  channel?: string;
  total_sold: number;
  total_revenue: number;
  orders_count: number;
  current_stock: number;
  avg_daily_sales: number;
  turnover_rate?: number;
  turnover_days?: number;
  turnover_class?: string;
  period_days: number;
}

export function TurnoverAnalysisPanel() {
  const [products, setProducts] = useState<TurnoverProduct[]>([]);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState<Period>("month");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const [brand, setBrand] = useState<string>("");
  const [productType, setProductType] = useState<string>("");
  const [channel, setChannel] = useState<string>("");
  const [storeId, setStoreId] = useState<string>("");
  const [viewMode, setViewMode] = useState<"products" | "category" | "brand">("products");

  const fetchTurnover = async () => {
    try {
      setLoading(true);
      let url = '';
      
      if (viewMode === "products") {
        url = '/api/analytics/products/turnover?';
      } else if (viewMode === "category") {
        url = '/api/analytics/products/turnover/by-category?';
      } else {
        url = '/api/analytics/products/turnover/by-brand?';
      }
      
      if (period === "custom" && startDate && endDate) {
        url += `start_date=${startDate}&end_date=${endDate}&`;
      } else if (period !== "custom") {
        url += `period=${period}&`;
      } else {
        url += 'days=30&';
      }
      
      if (viewMode === "products") {
        if (category) url += `&category=${encodeURIComponent(category)}`;
        if (brand) url += `&brand=${encodeURIComponent(brand)}`;
        if (productType) url += `&product_type=${encodeURIComponent(productType)}`;
      }
      if (channel) url += `&channel=${encodeURIComponent(channel)}`;
      if (storeId) url += `&store_id=${encodeURIComponent(storeId)}`;
      
      const response = await fetch(url);
      const data = await response.json();
      
      if (viewMode === "products" && data.products) {
        setProducts(data.products);
      } else if (viewMode === "category" && data.categories) {
        setProducts(data.categories.map((cat: any) => ({
          ...cat,
          product_name: cat.category,
          total_sold: cat.total_quantity,
          orders_count: cat.total_orders,
          current_stock: cat.total_stock,
          avg_daily_sales: cat.avg_daily_sales,
          turnover_rate: cat.avg_turnover_rate,
          turnover_days: cat.avg_turnover_days,
          period_days: data.period?.days || 30
        })));
      } else if (viewMode === "brand" && data.brands) {
        setProducts(data.brands.map((br: any) => ({
          ...br,
          product_name: br.brand,
          total_sold: br.total_quantity,
          orders_count: br.total_orders,
          current_stock: br.total_stock,
          avg_daily_sales: br.avg_daily_sales,
          turnover_rate: br.avg_turnover_rate,
          turnover_days: br.avg_turnover_days,
          period_days: data.period?.days || 30
        })));
      }
    } catch (err) {
      console.error('Ошибка загрузки оборачиваемости:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTurnover();
  }, [period, startDate, endDate, category, brand, productType, channel, storeId, viewMode]);

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

  const getTurnoverClassLabel = (cls?: string): string => {
    const labels: Record<string, string> = {
      fast: "Быстрая",
      medium: "Средняя",
      slow: "Медленная",
      very_slow: "Очень медленная"
    };
    return labels[cls || ''] || '—';
  };

  const getTurnoverClassColor = (cls?: string): string => {
    const colors: Record<string, string> = {
      fast: "text-green-600",
      medium: "text-blue-600",
      slow: "text-yellow-600",
      very_slow: "text-red-600"
    };
    return colors[cls || ''] || 'text-gray-600';
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency: 'RUB',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Оборачиваемость товаров</span>
          <div className="flex items-center gap-2">
            <Select value={viewMode} onValueChange={(v) => setViewMode(v as any)}>
              <SelectTrigger className="w-[150px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="products">По товарам</SelectItem>
                <SelectItem value="category">По категориям</SelectItem>
                <SelectItem value="brand">По брендам</SelectItem>
              </SelectContent>
            </Select>
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
            <Button onClick={fetchTurnover} disabled={loading} size="sm" variant="outline">
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Обновить
            </Button>
          </div>
        </CardTitle>
        <CardDescription>
          Анализ оборачиваемости за {getPeriodLabel(period).toLowerCase()}
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
        {viewMode === "products" && (
          <div className="flex flex-wrap gap-2 mt-4">
            <input
              type="text"
              placeholder="Категория"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="px-3 py-1 border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
            <input
              type="text"
              placeholder="Бренд"
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              className="px-3 py-1 border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
            <input
              type="text"
              placeholder="Тип"
              value={productType}
              onChange={(e) => setProductType(e.target.value)}
              className="px-3 py-1 border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
          </div>
        )}
      </CardHeader>
      <CardContent>
        {loading && !products.length ? (
          <div>Загрузка...</div>
        ) : products.length === 0 ? (
          <div className="text-center py-8 text-gray-500">Нет данных</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left p-2 font-semibold text-gray-700">
                    {viewMode === "products" ? "Товар" : viewMode === "category" ? "Категория" : "Бренд"}
                  </th>
                  {viewMode === "products" && (
                    <>
                      <th className="text-left p-2 font-semibold text-gray-700">Артикул</th>
                      <th className="text-left p-2 font-semibold text-gray-700">Категория</th>
                      <th className="text-left p-2 font-semibold text-gray-700">Бренд</th>
                    </>
                  )}
                  <th className="text-right p-2 font-semibold text-gray-700">Продано</th>
                  <th className="text-right p-2 font-semibold text-gray-700">Остаток</th>
                  <th className="text-right p-2 font-semibold text-gray-700">Продаж/день</th>
                  <th className="text-right p-2 font-semibold text-gray-700">Коэф. оборач.</th>
                  <th className="text-right p-2 font-semibold text-gray-700">Оборач. (дни)</th>
                  <th className="text-right p-2 font-semibold text-gray-700">Класс</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product, index) => (
                  <tr key={`${product.product_id_1c || 'unknown'}-${product.store_id || ''}-${product.channel || ''}-${index}`} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="p-2 font-medium text-gray-900">{product.product_name || '—'}</td>
                    {viewMode === "products" && (
                      <>
                        <td className="p-2 text-gray-600">{product.product_article || '—'}</td>
                        <td className="p-2 text-gray-600">{product.category || '—'}</td>
                        <td className="p-2 text-gray-600">{product.brand || '—'}</td>
                      </>
                    )}
                    <td className="p-2 text-right text-gray-700">
                      {product.total_sold != null ? product.total_sold.toLocaleString('ru-RU', { maximumFractionDigits: 1 }) : '—'}
                    </td>
                    <td className="p-2 text-right text-gray-700">
                      {product.current_stock != null ? product.current_stock.toLocaleString('ru-RU', { maximumFractionDigits: 1 }) : '—'}
                    </td>
                    <td className="p-2 text-right text-gray-700">
                      {product.avg_daily_sales != null && typeof product.avg_daily_sales === 'number' ? product.avg_daily_sales.toFixed(2) : '—'}
                    </td>
                    <td className="p-2 text-right text-gray-700">
                      {product.turnover_rate != null && typeof product.turnover_rate === 'number' ? product.turnover_rate.toFixed(2) : '—'}
                    </td>
                    <td className="p-2 text-right text-gray-700">
                      {product.turnover_days != null && typeof product.turnover_days === 'number' ? `${product.turnover_days.toFixed(1)} дн.` : '—'}
                    </td>
                    <td className={`p-2 text-right font-medium ${getTurnoverClassColor(product.turnover_class)}`}>
                      {getTurnoverClassLabel(product.turnover_class)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
