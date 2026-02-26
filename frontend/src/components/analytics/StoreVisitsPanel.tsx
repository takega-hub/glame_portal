"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, TrendingDown, ArrowRight } from 'lucide-react';
import { fetchJson } from '@/lib/utils';

export function StoreVisitsPanel() {
  const [status, setStatus] = useState<any>(null);
  const [dailyData, setDailyData] = useState<any>(null);
  const [salesData, setSalesData] = useState<any>(null);
  const [stores, setStores] = useState<any[]>([]);
  const [selectedStoreId, setSelectedStoreId] = useState<string>('all');
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(30);

  const fetchStores = async () => {
    try {
      const { data } = await fetchJson<{ stores?: any[] }>('/api/analytics/stores');
      setStores(data.stores || []);
    } catch (err) {
      console.error('Error fetching stores:', err);
    }
  };

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const url = selectedStoreId === 'all'
        ? '/api/analytics/ftp/status'
        : `/api/analytics/ftp/status?store_id=${selectedStoreId}`;
      const { data } = await fetchJson(url);
      setStatus(data);
    } catch (err) {
      console.error('Error fetching store visits:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchDailyData = async () => {
    try {
      const url = selectedStoreId === 'all'
        ? `/api/analytics/store-visits/daily?days=${days}`
        : `/api/analytics/store-visits/daily?days=${days}&store_id=${selectedStoreId}`;
      const { data } = await fetchJson(url);
      setDailyData(data);
    } catch (err) {
      console.error('Error fetching daily data:', err);
    }
  };

  const fetchSalesData = async () => {
    try {
      let url = `/api/analytics/1c-sales/daily?days=${days}&auto_sync=true`;
      if (selectedStoreId !== 'all') {
        url += `&store_id=${selectedStoreId}`;
      }
      const { data } = await fetchJson<{ status?: string }>(url);
      if (data.status === 'success') {
        setSalesData(data);
      }
    } catch (err) {
      console.error('Error fetching sales data:', err);
    }
  };

  useEffect(() => { 
    fetchStores();
  }, []);

  useEffect(() => { 
    fetchStatus(); 
    fetchDailyData();
    fetchSalesData();
  }, [days, selectedStoreId]);

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('ru-RU', { month: 'short', day: 'numeric' });
  };

  const selectedStoreName = selectedStoreId === 'all' 
    ? 'Все магазины' 
    : stores.find(s => s.id === selectedStoreId)?.name || 'Все магазины';

  return (
    <div className="space-y-6">
      {/* Селектор магазина */}
      <Card>
        <CardHeader>
          <CardTitle>Выбор магазина</CardTitle>
          <CardDescription>Выберите магазин для просмотра статистики</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <label htmlFor="store-select" className="text-sm font-medium">
              Магазин:
            </label>
            <select
              id="store-select"
              value={selectedStoreId}
              onChange={(e) => setSelectedStoreId(e.target.value)}
              className="px-4 py-2 rounded-md border border-gray-300 bg-white text-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-pink-500"
            >
              <option value="all">Все магазины</option>
              {stores.map((store) => (
                <option key={store.id} value={store.id}>
                  {store.name} {store.city ? `(${store.city})` : ''}
                </option>
              ))}
            </select>
            <span className="text-sm text-gray-600">
              {selectedStoreName}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Посещения магазинов</CardTitle>
          <CardDescription>
            {selectedStoreId === 'all' 
              ? 'Данные со счетчиков через FTP' 
              : `Данные со счетчиков через FTP - ${selectedStoreName}`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? <div>Загрузка...</div> : status ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-gray-100 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Всего магазинов</p>
                  <p className="text-2xl font-bold text-gray-900">{status.total_stores}</p>
                </div>
                <div className="bg-gray-100 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Активных</p>
                  <p className="text-2xl font-bold text-gray-900">{status.active_stores}</p>
                </div>
              </div>
              <div>
                <h3 className="text-lg font-semibold mb-2 text-gray-900">За последние 30 дней</h3>
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-gray-100 p-4 rounded-lg">
                    <p className="text-sm text-gray-600">Посетители</p>
                    <p className="text-xl font-bold text-gray-900">{status.last_30_days?.total_visitors?.toLocaleString() || 0}</p>
                  </div>
                  <div className="bg-gray-100 p-4 rounded-lg">
                    <p className="text-sm text-gray-600">Продажи</p>
                    <p className="text-xl font-bold text-gray-900">{status.last_30_days?.total_sales?.toLocaleString() || 0}</p>
                  </div>
                  <div className="bg-gray-100 p-4 rounded-lg">
                    <p className="text-sm text-gray-600">Выручка</p>
                    <p className="text-xl font-bold text-gray-900">₽{status.last_30_days?.total_revenue?.toLocaleString() || 0}</p>
                  </div>
                </div>
              </div>
            </div>
          ) : <div>Нет данных</div>}
        </CardContent>
      </Card>

      {dailyData && (
        <>
          {/* Сравнение с предыдущим периодом */}
          <Card>
            <CardHeader>
              <CardTitle>Сравнение с предыдущим периодом</CardTitle>
              <CardDescription>
                {dailyData.comparison_period?.start || ''} — {dailyData.comparison_period?.end || ''}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-gray-100 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Текущий период</p>
                  <p className="text-2xl font-bold text-gray-900">{dailyData.summary.current_total.toLocaleString()}</p>
                </div>
                <div className="bg-gray-100 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Предыдущий период</p>
                  <p className="text-2xl font-bold text-gray-900">{dailyData.summary.previous_total.toLocaleString()}</p>
                </div>
                <div className={`bg-gray-100 p-4 rounded-lg ${dailyData.summary.change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  <p className="text-sm text-gray-600">Изменение</p>
                  <div className="flex items-center gap-2">
                    {dailyData.summary.change >= 0 ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
                    <p className="text-2xl font-bold">{dailyData.summary.change_percent}%</p>
                  </div>
                  <p className="text-sm">{dailyData.summary.change >= 0 ? '+' : ''}{dailyData.summary.change.toLocaleString()} посетителей</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* График посещений */}
          <Card>
            <CardHeader>
              <CardTitle>Динамика посещений</CardTitle>
              <CardDescription>
                За последние {days} дней
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-4 mb-4">
                <span className="text-sm text-gray-600">Период:</span>
                <select 
                  value={days} 
                  onChange={(e) => setDays(Number(e.target.value))}
                  className="px-2 py-1 rounded border border-gray-300 bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-pink-500"
                >
                  <option value="7">7 дней</option>
                  <option value="14">14 дней</option>
                  <option value="30">30 дней</option>
                  <option value="60">60 дней</option>
                  <option value="90">90 дней</option>
                </select>
              </div>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={(() => {
                  // Объединяем данные о посещениях и продажах по датам
                  const combinedData: any[] = [];
                  
                  // Создаем мапу продаж по датам
                  const salesMap = new Map<string, any>();
                  if (salesData && salesData.daily_data) {
                    salesData.daily_data.forEach((day: any) => {
                      // Нормализуем дату (может быть с временем или без)
                      const dateKey = day.date.split('T')[0];
                      salesMap.set(dateKey, day);
                    });
                  }
                  
                  // Создаем мапу посещений по датам
                  const visitsMap = new Map<string, any>();
                  if (dailyData && dailyData.daily_data) {
                    dailyData.daily_data.forEach((visitDay: any) => {
                      const dateKey = visitDay.date.split('T')[0];
                      visitsMap.set(dateKey, visitDay);
                    });
                  }
                  
                  // Объединяем все уникальные даты из обоих источников
                  const allDates = new Set<string>();
                  salesMap.forEach((_, dateKey) => allDates.add(dateKey));
                  visitsMap.forEach((_, dateKey) => allDates.add(dateKey));
                  
                  // Сортируем даты
                  const sortedDates = Array.from(allDates).sort();
                  
                  // Создаем объединенные данные для каждой даты
                  sortedDates.forEach((dateKey) => {
                    const visitDay = visitsMap.get(dateKey);
                    const salesDay = salesMap.get(dateKey);
                    
                    combinedData.push({
                      date: dateKey,
                      visitors: visitDay ? (visitDay.visitors || 0) : 0,
                      revenue: salesDay ? (salesDay.revenue || 0) : 0,
                      orders: salesDay ? (salesDay.orders || 0) : 0
                    });
                  });
                  
                  return combinedData;
                })()}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="date" 
                    tickFormatter={formatDate}
                    angle={-45}
                    textAnchor="end"
                    height={80}
                  />
                  <YAxis yAxisId="left" />
                  <YAxis yAxisId="right" orientation="right" />
                  <Tooltip 
                    labelFormatter={(label) => new Date(label).toLocaleDateString('ru-RU', { 
                      year: 'numeric', 
                      month: 'long', 
                      day: 'numeric' 
                    })}
                    formatter={(value: any, name: string | undefined) => {
                      const label = name ?? '';
                      if (label === 'Посетители') {
                        return [value.toLocaleString(), 'Посетители'];
                      } else if (label === 'Выручка') {
                        return [`₽${value.toLocaleString()}`, 'Выручка'];
                      } else if (label === 'Заказы') {
                        return [value.toLocaleString(), 'Заказы'];
                      }
                      return [value, label];
                    }}
                  />
                  <Legend />
                  <Line 
                    yAxisId="left"
                    type="monotone" 
                    dataKey="visitors" 
                    stroke="#8884d8" 
                    strokeWidth={2}
                    name="Посетители"
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                  />
                  <Line 
                    yAxisId="right"
                    type="monotone" 
                    dataKey="revenue" 
                    stroke="#82ca9d" 
                    strokeWidth={2}
                    name="Выручка"
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Разбивка по магазинам */}
          {selectedStoreId === 'all' && dailyData.stores && dailyData.stores.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Детализация по магазинам</CardTitle>
                <CardDescription>Средние показатели за выбранный период</CardDescription>
              </CardHeader>
              <CardContent>
                {dailyData.stores.map((storeName: string) => {
                  const storeData = dailyData.daily_data
                    .flatMap((day: any) => day.stores?.filter((s: any) => s.name === storeName) || []);
                  
                  const totalVisitors = storeData.reduce((sum: number, s: any) => sum + s.visitors, 0);
                  const avgVisitors = storeData.length > 0 
                    ? Math.round(totalVisitors / storeData.length) 
                    : 0;
                  
                  return (
                    <div key={storeName} className="mb-4 p-4 bg-gray-100 rounded-lg">
                      <div className="flex justify-between items-center mb-2">
                        <h4 className="font-semibold text-lg text-gray-900">{storeName}</h4>
                        <span className="text-sm text-gray-600">
                          {totalVisitors.toLocaleString()} посетителей
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <span className="text-gray-600">Среднее в день: </span>
                          <span className="font-semibold text-gray-900">{avgVisitors}</span>
                        </div>
                        <div>
                          <span className="text-gray-600">Дней с данными: </span>
                          <span className="font-semibold text-gray-900">{storeData.length}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          )}

          {/* Детальная статистика для выбранного магазина */}
          {selectedStoreId !== 'all' && dailyData && dailyData.daily_data && dailyData.daily_data.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Детальная статистика: {selectedStoreName}</CardTitle>
                <CardDescription>Показатели за выбранный период</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-4">
                  <div className="p-4 bg-gray-100 rounded-lg">
                    <p className="text-sm text-gray-600">Всего посетителей</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {dailyData.summary.current_total.toLocaleString()}
                    </p>
                  </div>
                  <div className="p-4 bg-gray-100 rounded-lg">
                    <p className="text-sm text-gray-600">Среднее в день</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {Math.round(dailyData.summary.current_total / dailyData.daily_data.length).toLocaleString()}
                    </p>
                  </div>
                  <div className="p-4 bg-gray-100 rounded-lg">
                    <p className="text-sm text-gray-600">Дней с данными</p>
                    <p className="text-2xl font-bold text-gray-900">{dailyData.daily_data.length}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Гистограмма по дням недели */}
          <Card>
            <CardHeader>
              <CardTitle>Посещаемость по дням недели</CardTitle>
              <CardDescription>Средние значения за период</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={(() => {
                  const dayStats: any = {};
                  const dayNames = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
                  
                  dailyData.daily_data.forEach((day: any) => {
                    const date = new Date(day.date);
                    const dayOfWeek = date.getDay();
                    const dayName = dayNames[dayOfWeek];
                    
                    if (!dayStats[dayName]) {
                      dayStats[dayName] = { day: dayName, total: 0, count: 0 };
                    }
                    dayStats[dayName].total += day.visitors;
                    dayStats[dayName].count += 1;
                  });
                  
                  return dayNames.map(name => ({
                    day: name,
                    avg: dayStats[name] ? Math.round(dayStats[name].total / dayStats[name].count) : 0
                  }));
                })()}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="day" />
                  <YAxis />
                  <Tooltip formatter={(value: any) => [value, 'Среднее']} />
                  <Bar dataKey="avg" fill="#82ca9d" name="Средняя посещаемость" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
