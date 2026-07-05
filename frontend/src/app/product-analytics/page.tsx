'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ProductAnalyticsDashboardPanel } from '@/components/analytics/ProductAnalyticsDashboardPanel';
import { TopProductsPanel } from '@/components/analytics/TopProductsPanel';
import { TurnoverAnalysisPanel } from '@/components/analytics/TurnoverAnalysisPanel';
import { WebsitePriorityPanel } from '@/components/analytics/WebsitePriorityPanel';
import { StockManagementPanel } from '@/components/analytics/StockManagementPanel';
import { StockTransferPanel } from '@/components/analytics/StockTransferPanel';
import { DemandForecastPanel } from '@/components/analytics/DemandForecastPanel';
import { SeasonalForecastPanel } from '@/components/analytics/SeasonalForecastPanel';
import { DemandTrendsPanel } from '@/components/analytics/DemandTrendsPanel';
import { PurchaseRecommendationsPanel } from '@/components/analytics/PurchaseRecommendationsPanel';
import { InventoryDashboardPanel } from '@/components/inventory-control/InventoryDashboardPanel';
import { InventorySalesStockPanel } from '@/components/inventory-control/InventorySalesStockPanel';
import { InventoryStockClearancePanel } from '@/components/inventory-control/InventoryStockClearancePanel';
import { InventoryMarketingLinkPanel } from '@/components/inventory-control/InventoryMarketingLinkPanel';
import { InventoryTasksPanel } from '@/components/inventory-control/InventoryTasksPanel';

export default function ProductAnalyticsPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50">Аналитика товара</h1>
        <p className="mt-1 text-sm text-gray-600">
          Единый раздел для товарной аналитики, контроля запасов, закупок, перемещений, спроса и ИИ-задач по ассортименту.
        </p>
      </div>
      <Tabs defaultValue="dashboard">
        <TabsList className="flex h-auto flex-wrap justify-start">
          <TabsTrigger value="dashboard">Дашборд</TabsTrigger>
          <TabsTrigger value="top-products">Топ товары</TabsTrigger>
          <TabsTrigger value="turnover">Оборачиваемость</TabsTrigger>
          <TabsTrigger value="stock-control">Запасы</TabsTrigger>
          <TabsTrigger value="procurement">Закупки и перемещения</TabsTrigger>
          <TabsTrigger value="assortment">Ассортимент и маркетинг</TabsTrigger>
          <TabsTrigger value="demand">Спрос</TabsTrigger>
          <TabsTrigger value="ai-tasks">ИИ-задачи</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard">
          <ProductAnalyticsDashboardPanel />
        </TabsContent>
        <TabsContent value="top-products">
          <TopProductsPanel />
        </TabsContent>
        <TabsContent value="turnover">
          <TurnoverAnalysisPanel />
        </TabsContent>
        <TabsContent value="stock-control">
          <div className="space-y-6">
            <InventoryDashboardPanel />
            <InventorySalesStockPanel />
            <StockManagementPanel />
          </div>
        </TabsContent>
        <TabsContent value="procurement">
          <div className="space-y-6">
            <PurchaseRecommendationsPanel />
            <StockTransferPanel />
          </div>
        </TabsContent>
        <TabsContent value="assortment">
          <div className="space-y-6">
            <WebsitePriorityPanel />
            <InventoryStockClearancePanel />
            <InventoryMarketingLinkPanel />
          </div>
        </TabsContent>
        <TabsContent value="demand">
          <div className="space-y-6">
            <DemandForecastPanel />
            <SeasonalForecastPanel />
            <DemandTrendsPanel />
          </div>
        </TabsContent>
        <TabsContent value="ai-tasks">
          <InventoryTasksPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
