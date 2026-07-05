'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { UnifiedAnalyticsPanel } from './UnifiedAnalyticsPanel';
import { YandexMetrikaPanel } from './YandexMetrikaPanel';
import { InstagramPanel } from './InstagramPanel';
import { VKPanel } from './VKPanel';
import { TelegramPanel } from './TelegramPanel';
import { ChannelAnalyticsPanel } from './ChannelAnalyticsPanel';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getDashboardMetrics(30);
      setDashboardData(data);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки данных');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6">
        <p className="text-gray-600 dark:text-gray-300">Загрузка данных...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800 font-medium">Ошибка</p>
          <p className="text-red-600 text-sm mt-1">{error}</p>
        </div>
      </div>
    );
  }

  if (!dashboardData) {
    return null;
  }

  const { conversion, aov, engagement, events_by_type, total_events } = dashboardData;

  // Подготовка данных для графиков
  const eventsChartData = Object.entries(events_by_type || {}).map(([name, value]) => ({
    name,
    value: value as number,
  }));

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50 mb-6">Аналитика</h1>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Обзор</TabsTrigger>
          <TabsTrigger value="channels">Каналы</TabsTrigger>
          <TabsTrigger value="yandex-metrika">Яндекс.Метрика</TabsTrigger>
          <TabsTrigger value="instagram">Инстаграм</TabsTrigger>
          <TabsTrigger value="vk">ВКонтакте</TabsTrigger>
          <TabsTrigger value="telegram">Телеграм</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <UnifiedAnalyticsPanel />
        </TabsContent>
        <TabsContent value="channels">
          <ChannelAnalyticsPanel />
        </TabsContent>
        <TabsContent value="yandex-metrika">
          <YandexMetrikaPanel />
        </TabsContent>
        <TabsContent value="instagram">
          <InstagramPanel />
        </TabsContent>
        <TabsContent value="vk">
          <VKPanel />
        </TabsContent>
        <TabsContent value="telegram">
          <TelegramPanel />
        </TabsContent>
      </Tabs>

      {/* Детальная статистика конверсии */}
      {conversion && (
        <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Конверсия по этапам</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-gray-600">Чаты</p>
              <p className="text-2xl font-bold text-gray-900">{conversion.events?.chat_message || 0}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600">Клики по товарам</p>
              <p className="text-2xl font-bold text-gray-900">{conversion.events?.product_click || 0}</p>
              {conversion.conversion_rates?.chat_to_product && (
                <p className="text-xs text-green-600">
                  {conversion.conversion_rates.chat_to_product.toFixed(2)}% от чатов
                </p>
              )}
            </div>
            <div>
              <p className="text-sm text-gray-600">Просмотры образов</p>
              <p className="text-2xl font-bold text-gray-900">{conversion.events?.look_view || 0}</p>
              {conversion.conversion_rates?.chat_to_look && (
                <p className="text-xs text-green-600">
                  {conversion.conversion_rates.chat_to_look.toFixed(2)}% от чатов
                </p>
              )}
            </div>
            <div>
              <p className="text-sm text-gray-600">Покупки</p>
              <p className="text-2xl font-bold text-gray-900">{conversion.events?.purchase || 0}</p>
              {conversion.conversion_rates?.chat_to_purchase && (
                <p className="text-xs text-green-600">
                  {conversion.conversion_rates.chat_to_purchase.toFixed(2)}% от чатов
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
