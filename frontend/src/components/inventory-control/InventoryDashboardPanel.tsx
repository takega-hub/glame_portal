"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { StoreSelect } from "@/components/inventory-control/StoreSelect";
import { PeriodSelect, type InventoryPeriodPreset } from "@/components/inventory-control/PeriodSelect";

type DashboardMetrics = {
  sales: Record<string, number | null | undefined>;
  stock: Record<string, number | null | undefined>;
  purchases: Record<string, number | null | undefined>;
  clearance: Record<string, number | null | undefined>;
  updated_at?: string | null;
};

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("ru-RU");
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return "—";
  return dt.toLocaleString("ru-RU");
}

export function InventoryDashboardPanel() {
  const [data, setData] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [periodPreset, setPeriodPreset] = useState<InventoryPeriodPreset>("days");
  const [periodDays, setPeriodDays] = useState(90);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [storeId, setStoreId] = useState("");

  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (periodPreset === "days") {
      p.set("analysis_period_days", String(periodDays));
    } else if (periodPreset === "custom") {
      p.set("period", "custom");
      if (startDate) p.set("start_date", startDate);
      if (endDate) p.set("end_date", endDate);
    } else {
      p.set("period", periodPreset);
    }
    if (storeId) p.set("store_id", storeId);
    return p.toString();
  }, [endDate, periodDays, periodPreset, startDate, storeId]);

  const fetchDashboard = async (forceRefresh: boolean) => {
    try {
      setLoading(true);
      const res = await fetch(`/api/inventory/dashboard?${query}${forceRefresh ? "&force_refresh=true" : ""}`);
      if (!res.ok) throw new Error("Ошибка загрузки сводки");
      const json = await res.json();
      setData(json);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard(false);
  }, [query]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-sm text-gray-600">Обновлено: {formatDateTime(data?.updated_at)}</div>
        </div>
          <div className="flex flex-col md:flex-row md:items-end gap-2">
            <div className="w-full md:w-72">
              <StoreSelect label="Магазин" value={storeId} onChange={setStoreId} />
            </div>
            <PeriodSelect
              value={periodPreset}
              onChange={setPeriodPreset}
              days={periodDays}
              onDaysChange={setPeriodDays}
              startDate={startDate}
              endDate={endDate}
              onStartDateChange={setStartDate}
              onEndDateChange={setEndDate}
            />
            <Button onClick={() => fetchDashboard(true)} disabled={loading} variant="outline" size="sm">
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
              Обновить
            </Button>
          </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Продажи</CardTitle>
            <CardDescription>Ключевые метрики продаж</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <MetricRow label="Выручка" value={formatNumber(data?.sales?.revenue)} />
            <MetricRow label="Кол-во изделий" value={formatNumber(data?.sales?.items_count)} />
            <MetricRow label="Средний чек" value={formatNumber(data?.sales?.avg_check)} />
            <MetricRow label="Кол-во чеков" value={formatNumber(data?.sales?.checks_count)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Остатки</CardTitle>
            <CardDescription>Состояние склада</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <MetricRow label="Количество SKU" value={formatNumber(data?.stock?.sku_count)} />
            <MetricRow label="Общий остаток" value={formatNumber(data?.stock?.total_stock)} />
            <MetricRow label="Среднее покрытие" value={formatNumber(data?.stock?.avg_stock_cover)} />
            <MetricRow label="Критические остатки" value={formatNumber(data?.stock?.critical_count)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Закупки</CardTitle>
            <CardDescription>Рекомендации по заказу</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <MetricRow label="Позиций к заказу" value={formatNumber(data?.purchases?.items_to_order)} />
            <MetricRow label="Сумма заказа" value={formatNumber(data?.purchases?.total_order_amount)} />
            <MetricRow label="Критических позиций" value={formatNumber(data?.purchases?.critical_items)} />
            <MetricRow label="Рекомендуемый заказ" value={formatNumber(data?.purchases?.total_order_qty)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Чистка склада</CardTitle>
            <CardDescription>Медленнооборачиваемые товары и неликвид</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <MetricRow label="Медленнооборачиваемые" value={formatNumber(data?.clearance?.slow_moving_count)} />
            <MetricRow label="Неликвид" value={formatNumber(data?.clearance?.dead_stock_count)} />
            <MetricRow label="Промо" value={formatNumber(data?.clearance?.promo_count)} />
            <MetricRow label="Списание" value={formatNumber(data?.clearance?.write_off_count)} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="text-sm text-gray-600">{label}</div>
      <div className="text-sm font-semibold text-gray-900">{value}</div>
    </div>
  );
}
