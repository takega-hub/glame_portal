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

interface Product {
  product_id_1c?: string | null;
  product_id?: string | null;
  product_name?: string | null;
  product_article?: string | null;
  category?: string | null;
  brand?: string | null;
  product_type?: string | null;
  total_revenue?: number | null;
  total_quantity?: number | null;
  total_orders?: number | null;
  avg_price?: number | null;
  avg_margin_percent?: number | null;
}

export function TopProductsPanel() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState<Period>("month");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [sortBy, setSortBy] = useState<string>("revenue");
  const [limit, setLimit] = useState<number>(20);
  const [category, setCategory] = useState<string>("");
  const [brand, setBrand] = useState<string>("");
  const [productType, setProductType] = useState<string>("");
  const [channel, setChannel] = useState<string>("");
  const [storeId, setStoreId] = useState<string>("");

  const fetchTopProducts = async () => {
    try {
      setLoading(true);
      let url = '/api/analytics/products/top-sellers?';
      
      if (period === "custom" && startDate && endDate) {
        url += `start_date=${startDate}&end_date=${endDate}&`;
      } else if (period !== "custom") {
        url += `period=${period}&`;
      } else {
        url += 'days=30&';
      }
      
      url += `limit=${limit}&sort_by=${sortBy}`;
      
      if (category) url += `&category=${encodeURIComponent(category)}`;
      if (brand) url += `&brand=${encodeURIComponent(brand)}`;
      if (productType) url += `&product_type=${encodeURIComponent(productType)}`;
      if (channel) url += `&channel=${encodeURIComponent(channel)}`;
      if (storeId) url += `&store_id=${encodeURIComponent(storeId)}`;
      
      const response = await fetch(url);
      const data = await response.json();
      
      if (data.products) {
        setProducts(data.products);
      }
    } catch (err) {
      console.error('Ошибка загрузки топ товаров:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTopProducts();
  }, [period, startDate, endDate, sortBy, limit, category, brand, productType, channel, storeId]);

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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Топ продаваемых товаров</span>
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
            <Button onClick={fetchTopProducts} disabled={loading} size="sm" variant="outline">
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Обновить
            </Button>
          </div>
        </CardTitle>
        <CardDescription>
          Топ товаров за {getPeriodLabel(period).toLowerCase()}
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
        <div className="flex flex-wrap gap-2 mt-4">
          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger className="w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="revenue">По выручке</SelectItem>
              <SelectItem value="quantity">По количеству</SelectItem>
              <SelectItem value="orders">По заказам</SelectItem>
            </SelectContent>
          </Select>
          <Select value={limit.toString()} onValueChange={(v) => setLimit(Number(v))}>
            <SelectTrigger className="w-[120px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="10">Топ 10</SelectItem>
              <SelectItem value="20">Топ 20</SelectItem>
              <SelectItem value="50">Топ 50</SelectItem>
              <SelectItem value="100">Топ 100</SelectItem>
            </SelectContent>
          </Select>
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
                  <th className="text-left p-2 font-semibold text-gray-700">#</th>
                  <th className="text-left p-2 font-semibold text-gray-700">Товар</th>
                  <th className="text-left p-2 font-semibold text-gray-700">Артикул</th>
                  <th className="text-left p-2 font-semibold text-gray-700">Категория</th>
                  <th className="text-left p-2 font-semibold text-gray-700">Бренд</th>
                  <th className="text-right p-2 font-semibold text-gray-700">Выручка</th>
                  <th className="text-right p-2 font-semibold text-gray-700">Количество</th>
                  <th className="text-right p-2 font-semibold text-gray-700">Средняя цена</th>
                  {products.some(p => p.avg_margin_percent != null) && (
                    <th className="text-right p-2 font-semibold text-gray-700">Маржа %</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {products.map((product, index) => (
                  <tr key={`${product.product_id_1c || 'unknown'}-${product.product_article || ''}-${index}`} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="p-2 text-gray-600">{index + 1}</td>
                    <td className="p-2 font-medium text-gray-900">{product.product_name || '—'}</td>
                    <td className="p-2 text-gray-600">{product.product_article || '—'}</td>
                    <td className="p-2 text-gray-600">{product.category || '—'}</td>
                    <td className="p-2 text-gray-600">{product.brand || '—'}</td>
                    <td className="p-2 text-right font-semibold text-gray-900">
                      {product.total_revenue != null ? formatCurrency(product.total_revenue) : '—'}
                    </td>
                    <td className="p-2 text-right text-gray-700">
                      {product.total_quantity != null ? product.total_quantity.toLocaleString('ru-RU', { maximumFractionDigits: 1 }) : '—'}
                    </td>
                    <td className="p-2 text-right text-gray-700">
                      {product.avg_price != null ? formatCurrency(product.avg_price) : '—'}
                    </td>
                    {products.some(p => p.avg_margin_percent != null) && (
                      <td className="p-2 text-right text-gray-700">
                        {product.avg_margin_percent != null && typeof product.avg_margin_percent === 'number' 
                          ? `${product.avg_margin_percent.toFixed(1)}%` 
                          : '—'}
                      </td>
                    )}
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
