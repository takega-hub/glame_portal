'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import MetricsCard from './MetricsCard';
import Charts from './Charts';
import ContentPerformance from './ContentPerformance';
import { YandexMetrikaPanel } from './YandexMetrikaPanel';
import { InstagramPanel } from './InstagramPanel';
import { VKPanel } from './VKPanel';
import { TelegramPanel } from './TelegramPanel';
import { SalesPanel } from './SalesPanel';
import { UnifiedAnalyticsPanel } from './UnifiedAnalyticsPanel';
import { TopProductsPanel } from './TopProductsPanel';
import { TurnoverAnalysisPanel } from './TurnoverAnalysisPanel';
import { ChannelAnalyticsPanel } from './ChannelAnalyticsPanel';
import { WebsitePriorityPanel } from './WebsitePriorityPanel';
import { PurchaseRecommendationsPanel } from './PurchaseRecommendationsPanel';
import { StockManagementPanel } from './StockManagementPanel';
import { StockTransferPanel } from './StockTransferPanel';
import { DemandForecastPanel } from './DemandForecastPanel';
import { SeasonalForecastPanel } from './SeasonalForecastPanel';
import { DemandTrendsPanel } from './DemandTrendsPanel';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    loadDashboard();
  }, [days]);

  const loadDashboard = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getDashboardMetrics(days);
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
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50">Аналитика</h1>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-700 dark:text-gray-300">Период:</label>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="px-3 py-1.5 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-pink-500"
          >
            <option value={7}>7 дней</option>
            <option value={30}>30 дней</option>
            <option value={90}>90 дней</option>
            <option value={365}>Год</option>
          </select>
        </div>
      </div>

      {/* Основные метрики */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricsCard
          title="Всего событий"
          value={total_events || 0}
          subtitle={`За ${days} дней`}
        />
        <MetricsCard
          title="Средний чек"
          value={aov?.aov ? `${aov.aov.toFixed(2)} ₽` : '0 ₽'}
          subtitle={`${aov?.order_count || 0} заказов`}
        />
        <MetricsCard
          title="Конверсия чат → покупка"
          value={conversion?.conversion_rates?.chat_to_purchase 
            ? `${conversion.conversion_rates.chat_to_purchase.toFixed(2)}%` 
            : '0%'}
          subtitle={`${conversion?.events?.purchase || 0} покупок`}
        />
        <MetricsCard
          title="Средняя длительность сессии"
          value={engagement?.avg_session_duration_seconds 
            ? `${Math.round(engagement.avg_session_duration_seconds / 60)} мин` 
            : '0 мин'}
          subtitle={`${engagement?.total_sessions || 0} сессий`}
        />
      </div>

      {/* Графики */}
      <Charts eventsData={eventsChartData} />

      {/* Анализ контента */}
      <ContentPerformance days={days} />

      {/* Внешние источники аналитики */}
      <div className="mt-8">
        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-50 mb-4">Внешние источники данных</h2>
        
        <Tabs defaultValue="overview" className="w-full">
          <TabsList className="flex flex-wrap w-full mb-4 h-auto">
            <TabsTrigger value="overview" className="flex-shrink-0">Обзор</TabsTrigger>
            <TabsTrigger value="yandex" className="flex-shrink-0">Яндекс.Метрика</TabsTrigger>
            <TabsTrigger value="instagram" className="flex-shrink-0">Instagram</TabsTrigger>
            <TabsTrigger value="vk" className="flex-shrink-0">ВКонтакте</TabsTrigger>
            <TabsTrigger value="telegram" className="flex-shrink-0">Telegram</TabsTrigger>
            <TabsTrigger value="sales" className="flex-shrink-0">Продажи</TabsTrigger>
            <TabsTrigger value="top-products" className="flex-shrink-0">Топ товары</TabsTrigger>
            <TabsTrigger value="turnover" className="flex-shrink-0">Оборачиваемость</TabsTrigger>
            <TabsTrigger value="channels" className="flex-shrink-0">Каналы</TabsTrigger>
            <TabsTrigger value="website-priority" className="flex-shrink-0">Приоритет сайта</TabsTrigger>
            <TabsTrigger value="purchase-recommendations" className="flex-shrink-0">Закупки</TabsTrigger>
            <TabsTrigger value="stock-management" className="flex-shrink-0">Запасы</TabsTrigger>
            <TabsTrigger value="stock-transfer" className="flex-shrink-0">Перемещения</TabsTrigger>
            <TabsTrigger value="demand-forecast" className="flex-shrink-0">Прогноз спроса</TabsTrigger>
            <TabsTrigger value="seasonal-forecast" className="flex-shrink-0">Сезонность</TabsTrigger>
            <TabsTrigger value="demand-trends" className="flex-shrink-0">Тренды</TabsTrigger>
          </TabsList>
          
          <TabsContent value="overview">
            <UnifiedAnalyticsPanel />
          </TabsContent>
          
          <TabsContent value="yandex">
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
          
          <TabsContent value="sales">
            <SalesPanel />
          </TabsContent>
          
          <TabsContent value="top-products">
            <TopProductsPanel />
          </TabsContent>
          
          <TabsContent value="turnover">
            <TurnoverAnalysisPanel />
          </TabsContent>
          
          <TabsContent value="channels">
            <ChannelAnalyticsPanel />
          </TabsContent>
          <TabsContent value="website-priority">
            <WebsitePriorityPanel />
          </TabsContent>
          <TabsContent value="purchase-recommendations">
            <PurchaseRecommendationsPanel />
          </TabsContent>
          <TabsContent value="stock-management">
            <StockManagementPanel />
          </TabsContent>
          
          <TabsContent value="stock-transfer">
            <StockTransferPanel />
          </TabsContent>
          
          <TabsContent value="demand-forecast">
            <DemandForecastPanel />
          </TabsContent>
          
          <TabsContent value="seasonal-forecast">
            <SeasonalForecastPanel />
          </TabsContent>
          
          <TabsContent value="demand-trends">
            <DemandTrendsPanel />
          </TabsContent>
        </Tabs>
      </div>

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
