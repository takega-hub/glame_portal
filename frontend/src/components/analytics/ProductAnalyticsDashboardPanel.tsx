"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  PackageCheck,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Star,
  TrendingUp,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Period = "today" | "yesterday" | "week" | "month" | "quarter" | "year";

type TopProduct = {
  product_id_1c?: string | null;
  product_id?: string | null;
  product_name?: string | null;
  product_article?: string | null;
  category?: string | null;
  brand?: string | null;
  total_revenue?: number | null;
  total_quantity?: number | null;
  total_orders?: number | null;
  avg_price?: number | null;
};

type ProductCategory = {
  category?: string | null;
  products_count?: number | null;
  total_orders?: number | null;
  total_quantity?: number | null;
  total_revenue?: number | null;
};

type TurnoverCategory = {
  category?: string | null;
  products_count?: number | null;
  total_sold?: number | null;
  total_stock?: number | null;
  avg_daily_sales?: number | null;
  avg_turnover_rate?: number | null;
  avg_turnover_days?: number | null;
};

type HealthScore = {
  status?: string;
  health_score?: number;
  metrics?: {
    total_products?: number;
    avg_stockout_risk?: number;
    avg_overstock_risk?: number;
    avg_service_level?: number;
    critical_stockout_count?: number;
    critical_overstock_count?: number;
    stock_total?: number;
    source?: string;
  };
};

type WebsitePriorityProduct = {
  product_id_1c?: string | null;
  product_name?: string | null;
  product_article?: string | null;
  category?: string | null;
  brand?: string | null;
  priority_score?: number | null;
  priority_class?: string | null;
  is_recommended?: boolean | null;
  has_images?: boolean | null;
  recommendation_reason?: string | null;
};

type InventoryItem = {
  product_id_1c?: string | null;
  product_name?: string | null;
  product_article?: string | null;
  category?: string | null;
  brand?: string | null;
  current_stock?: number | null;
  stockout_risk?: number | null;
  overstock_risk?: number | null;
  service_level?: number | null;
  abc_class?: string | null;
  xyz_class?: string | null;
};

type AssortmentSalesDiagnostics = {
  stores?: Array<{ store_id?: string | null; store_name?: string | null; revenue?: number | null; sold_qty?: number | null; checks_count?: number | null }>;
  sellers?: Array<{ seller_id?: string | null; seller_name?: string | null; store_name?: string | null; revenue?: number | null; sold_qty?: number | null; personal_output_blocked?: boolean; warning?: string | null }>;
  brands?: Array<{ brand?: string | null; revenue?: number | null; sold_qty?: number | null }>;
  categories?: Array<{ category?: string | null; revenue?: number | null; sold_qty?: number | null }>;
  positions?: Array<{ product_id?: string | null; article?: string | null; product_name?: string | null; brand?: string | null; category?: string | null; revenue?: number | null; sold_qty?: number | null; stock_qty?: number | null; diagnosis?: string | null }>;
  data_quality?: {
    total_revenue?: number | null;
    unattributed_seller_revenue?: number | null;
    unattributed_seller_share?: number | null;
    warnings?: string[];
  };
};

type AssortmentData = {
  rows?: Array<{ category?: string | null; sold_qty?: number | null; stock_qty?: number | null; target_share?: number | null; warnings?: string[] | null }>;
  sales_diagnostics?: AssortmentSalesDiagnostics;
  plan_source?: {
    period?: string | null;
    store_id?: string | null;
    source_url?: string | null;
    store_name?: string | null;
    import_status?: string | null;
    warnings?: string[];
    sources?: Array<{ store_name?: string | null; seller_name?: string | null; source_file?: string | null; source_url?: string | null; import_status?: string | null }>;
  };
};

type DashboardData = {
  topByRevenue: TopProduct[];
  topByQuantity: TopProduct[];
  categories: ProductCategory[];
  turnoverCategories: TurnoverCategory[];
  health: HealthScore | null;
  priorityProducts: WebsitePriorityProduct[];
  inventory: InventoryItem[];
  assortment: AssortmentData | null;
};


const CATEGORY_COLORS = ["#a16207", "#be123c", "#0f766e", "#6d28d9", "#2563eb", "#c2410c", "#4d7c0f", "#7c2d12"];

const PERIOD_LABELS: Record<Period, string> = {
  today: "Сегодня",
  yesterday: "Вчера",
  week: "Неделя",
  month: "Месяц",
  quarter: "Квартал",
  year: "Год",
};

const compactNumber = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1, notation: "compact" });
const plainNumber = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });
const currency = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0,
});

function productLabel(name?: string | null, fallback?: string | null) {
  const source = name || fallback || "Без названия";
  return source.length > 34 ? `${source.slice(0, 34)}…` : source;
}

function categoryLabel(name?: string | null) {
  const source = name || "Без категории";
  return source.length > 24 ? `${source.slice(0, 24)}…` : source;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function healthStatusLabel(status?: string) {
  switch (status) {
    case "excellent":
      return "Отлично";
    case "good":
      return "Хорошо";
    case "fair":
      return "Средне";
    case "poor":
      return "Плохо";
    default:
      return "Нет оценки";
  }
}

function healthStatusClass(status?: string) {
  switch (status) {
    case "excellent":
      return "bg-green-100 text-green-800 border-green-200";
    case "good":
      return "bg-blue-100 text-blue-800 border-blue-200";
    case "fair":
      return "bg-yellow-100 text-yellow-800 border-yellow-200";
    case "poor":
      return "bg-red-100 text-red-800 border-red-200";
    default:
      return "bg-gray-100 text-gray-700 border-gray-200";
  }
}

function KpiCard({
  title,
  value,
  subtitle,
  icon: Icon,
  tone = "default",
}: {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ElementType;
  tone?: "default" | "good" | "warning" | "danger";
}) {
  const toneClass = {
    default: "bg-gray-100 text-gray-700",
    good: "bg-emerald-100 text-emerald-700",
    warning: "bg-amber-100 text-amber-700",
    danger: "bg-rose-100 text-rose-700",
  }[tone];

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm text-gray-500">{title}</p>
            <p className="mt-2 text-2xl font-semibold text-gray-950">{value}</p>
            <p className="mt-1 text-xs text-gray-500">{subtitle}</p>
          </div>
          <div className={`rounded-full p-2 ${toneClass}`}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="flex h-[260px] items-center justify-center text-sm text-gray-500">{label}</div>;
}

export function ProductAnalyticsDashboardPanel() {
  const [period, setPeriod] = useState<Period>("month");
  const [data, setData] = useState<DashboardData>({
    topByRevenue: [],
    topByQuantity: [],
    categories: [],
    turnoverCategories: [],
    health: null,
    priorityProducts: [],
    inventory: [],
    assortment: null,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const assortmentPeriod = ["week", "month", "quarter", "year"].includes(period) ? period : "month";
      const [topRevenue, topQuantity, categories, turnoverCategories, health, priorities, inventory, assortment] = await Promise.all([
        fetchJson<{ products?: TopProduct[] }>(`/api/analytics/products/top-sellers?period=${period}&limit=10&sort_by=revenue`),
        fetchJson<{ products?: TopProduct[] }>(`/api/analytics/products/top-sellers?period=${period}&limit=10&sort_by=quantity`),
        fetchJson<{ categories?: ProductCategory[] }>(`/api/analytics/products/by-category?period=${period}`),
        fetchJson<{ categories?: TurnoverCategory[] }>(`/api/analytics/products/turnover/by-category?period=${period}`),
        fetchJson<HealthScore>("/api/analytics/inventory/health-score"),
        fetchJson<{ products?: WebsitePriorityProduct[] }>("/api/analytics/inventory/website-priority?limit=25&min_priority=0&only_recommended=true"),
        fetchJson<{ analysis?: InventoryItem[] }>("/api/analytics/inventory/analysis?limit=250"),
        fetchJson<AssortmentData>(`/api/inventory/assortment?period=${assortmentPeriod}&force_refresh=true`),
      ]);

      setData({
        topByRevenue: topRevenue.products || [],
        topByQuantity: topQuantity.products || [],
        categories: categories.categories || [],
        turnoverCategories: turnoverCategories.categories || [],
        health,
        priorityProducts: priorities.products || [],
        inventory: inventory.analysis || [],
        assortment,
      });
    } catch (err) {
      console.error("Ошибка загрузки товарного дашборда:", err);
      setError(err instanceof Error ? err.message : "Неизвестная ошибка");
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const topRevenueChart = useMemo(
    () => data.topByRevenue.map((product) => ({
      name: productLabel(product.product_name, product.product_article),
      revenue: product.total_revenue || 0,
      quantity: product.total_quantity || 0,
      fullName: product.product_name || "Без названия",
    })).reverse(),
    [data.topByRevenue],
  );

  const topQuantityChart = useMemo(
    () => data.topByQuantity.map((product) => ({
      name: productLabel(product.product_name, product.product_article),
      quantity: product.total_quantity || 0,
      orders: product.total_orders || 0,
      revenue: product.total_revenue || 0,
    })).reverse(),
    [data.topByQuantity],
  );

  const categoriesChart = useMemo(
    () => data.categories.slice(0, 8).map((category) => ({
      name: categoryLabel(category.category),
      category: category.category || "Без категории",
      revenue: category.total_revenue || 0,
      quantity: category.total_quantity || 0,
      products: category.products_count || 0,
    })),
    [data.categories],
  );

  const turnoverChart = useMemo(
    () => data.turnoverCategories.slice(0, 10).map((category) => ({
      name: categoryLabel(category.category),
      turnover: category.avg_turnover_rate || 0,
      stock: category.total_stock || 0,
      sold: category.total_sold || 0,
    })),
    [data.turnoverCategories],
  );

  const inventoryRiskChart = useMemo(() => {
    const criticalStockout = data.inventory.filter((item) => (item.stockout_risk || 0) >= 0.8).length;
    const criticalOverstock = data.inventory.filter((item) => (item.overstock_risk || 0) >= 0.8).length;
    const healthy = data.inventory.filter((item) => (item.stockout_risk || 0) < 0.8 && (item.overstock_risk || 0) < 0.8).length;
    return [
      { name: "Дефицит", value: criticalStockout, color: "#dc2626" },
      { name: "Излишки", value: criticalOverstock, color: "#d97706" },
      { name: "Без крит. риска", value: healthy, color: "#059669" },
    ].filter((item) => item.value > 0);
  }, [data.inventory]);

  const totalRevenue = data.categories.reduce((sum, category) => sum + (category.total_revenue || 0), 0);
  const totalQuantity = data.categories.reduce((sum, category) => sum + (category.total_quantity || 0), 0);
  const totalCategoryProducts = data.categories.reduce((sum, category) => sum + (category.products_count || 0), 0);
  const topCategory = data.categories[0]?.category || "—";
  const priorityCount = data.priorityProducts.length;
  const health = data.health;
  const salesDiagnostics = data.assortment?.sales_diagnostics;
  const planSource = data.assortment?.plan_source;
  const unattributedShare = salesDiagnostics?.data_quality?.unattributed_seller_share || 0;
  const topStore = salesDiagnostics?.stores?.[0];
  const topSeller = salesDiagnostics?.sellers?.find((seller) => !seller.personal_output_blocked) || salesDiagnostics?.sellers?.[0];
  const topBrand = salesDiagnostics?.brands?.[0];
  const topAssortmentCategory = salesDiagnostics?.categories?.[0];
  const stuckPositions = (salesDiagnostics?.positions || []).filter((position) => position.diagnosis && position.diagnosis !== "selling").slice(0, 5);

  const tooltipCurrency = (value: number | string) => currency.format(Number(value || 0));
  const tooltipNumber = (value: number | string) => plainNumber.format(Number(value || 0));

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-amber-700" />
                Товарный дашборд
              </CardTitle>
              <CardDescription>
                Сводка по товарам: популярность, категории, оборачиваемость, складские риски и приоритет сайта — без дублирования общего графика продаж.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Select value={period} onValueChange={(value) => setPeriod(value as Period)}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(PERIOD_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button onClick={loadDashboard} disabled={loading} size="sm" variant="outline">
                <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                Обновить
              </Button>
            </div>
          </div>
          {error && (
            <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              Не удалось загрузить часть товарной аналитики: {error}
            </div>
          )}
        </CardHeader>
      </Card>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        <KpiCard
          title="Товаров в продажах"
          value={plainNumber.format(totalCategoryProducts)}
          subtitle={`За период: ${PERIOD_LABELS[period].toLowerCase()}`}
          icon={PackageCheck}
        />
        <KpiCard
          title="Продано единиц"
          value={plainNumber.format(totalQuantity)}
          subtitle={`Товарный объём, не общий sales-график`}
          icon={TrendingUp}
          tone="good"
        />
        <KpiCard
          title="Топ категория"
          value={topCategory}
          subtitle={totalRevenue ? `Выручка категорий: ${currency.format(totalRevenue)}` : "Нет данных"}
          icon={Sparkles}
        />
        <KpiCard
          title="Health score"
          value={health?.health_score != null ? plainNumber.format(health.health_score) : "—"}
          subtitle={healthStatusLabel(health?.status)}
          icon={Activity}
          tone={health?.status === "poor" ? "danger" : health?.status === "fair" ? "warning" : "good"}
        />
        <KpiCard
          title="Крит. дефицит"
          value={plainNumber.format(health?.metrics?.critical_stockout_count || 0)}
          subtitle={`Излишки: ${plainNumber.format(health?.metrics?.critical_overstock_count || 0)}`}
          icon={ShieldAlert}
          tone="danger"
        />
      </div>


      <Card>
        <CardHeader>
          <CardTitle>AI Assortment: диагностика продаж по магазинам и продавцам</CardTitle>
          <CardDescription>Блок из существующего AssortmentMatrixAgent: сеть → магазин → продавец → бренд → категория → позиция, с контролем seller attribution и источника плана.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <KpiCard title="Топ магазин" value={topStore?.store_name || "—"} subtitle={topStore?.revenue ? currency.format(topStore.revenue) : "Нет продаж"} icon={BarChart3} />
            <KpiCard title="Топ продавец" value={topSeller?.seller_name || "—"} subtitle={topSeller?.personal_output_blocked ? "Выводы заблокированы: нет seller_id" : topSeller?.revenue ? currency.format(topSeller.revenue) : "Нет атрибуции"} icon={Star} tone={topSeller?.personal_output_blocked ? "warning" : "good"} />
            <KpiCard title="Топ бренд" value={topBrand?.brand || "—"} subtitle={topBrand?.revenue ? currency.format(topBrand.revenue) : "Нет данных"} icon={Sparkles} />
            <KpiCard title="Несопоставлено" value={`${plainNumber.format(unattributedShare * 100)}%`} subtitle="Доля продаж без продавца" icon={AlertTriangle} tone={unattributedShare > 0.1 ? "danger" : unattributedShare > 0 ? "warning" : "good"} />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div className="rounded-lg border p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="font-medium text-gray-900">Категория / бренд / позиция</div>
                <Badge variant="outline">{topAssortmentCategory?.category || "без категории"}</Badge>
              </div>
              {stuckPositions.length ? (
                <div className="space-y-2">
                  {stuckPositions.map((position, index) => (
                    <div key={`${position.product_id || position.article || index}`} className="rounded-md bg-amber-50 p-2 text-sm">
                      <div className="font-medium text-gray-900">{position.product_name || position.article || "Позиция"}</div>
                      <div className="text-xs text-amber-800">{position.brand || "—"} · {position.category || "—"} · причина: {position.diagnosis}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-gray-500">Нет критичных товарных позиций в текущей выборке.</div>
              )}
            </div>

            <div className="rounded-lg border p-3">
              <div className="mb-2 font-medium text-gray-900">Источник плана и data quality</div>
              <div className="space-y-2 text-sm text-gray-700">
                <div>План: {planSource?.store_name || "—"} · {planSource?.period || "—"} · {planSource?.import_status || "нет статуса"}</div>
                {planSource?.source_url && <div className="break-all text-xs text-gray-500">source_url: {planSource.source_url}</div>}
                {(planSource?.warnings || []).map((warning) => (
                  <Badge key={warning} variant="outline" className="mr-2 border-amber-200 bg-amber-50 text-amber-800">{warning}</Badge>
                ))}
                {(salesDiagnostics?.data_quality?.warnings || []).map((warning) => (
                  <Badge key={warning} variant="outline" className="mr-2 border-red-200 bg-red-50 text-red-700">{warning}</Badge>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Популярные товары по выручке</CardTitle>
            <CardDescription>Топ-10 товаров за выбранный период</CardDescription>
          </CardHeader>
          <CardContent>
            {topRevenueChart.length ? (
              <div className="h-[360px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topRevenueChart} layout="vertical" margin={{ left: 16, right: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tickFormatter={(value) => compactNumber.format(Number(value))} />
                    <YAxis dataKey="name" type="category" width={170} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(value) => tooltipCurrency(value as number)} />
                    <Bar dataKey="revenue" name="Выручка" fill="#a16207" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState label={loading ? "Загрузка..." : "Нет данных по товарам"} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Популярные товары по количеству</CardTitle>
            <CardDescription>Что чаще всего покупают в штуках</CardDescription>
          </CardHeader>
          <CardContent>
            {topQuantityChart.length ? (
              <div className="h-[360px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topQuantityChart} layout="vertical" margin={{ left: 16, right: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tickFormatter={(value) => plainNumber.format(Number(value))} />
                    <YAxis dataKey="name" type="category" width={170} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(value, name) => name === "Выручка" ? tooltipCurrency(value as number) : tooltipNumber(value as number)} />
                    <Legend />
                    <Bar dataKey="quantity" name="Количество" fill="#0f766e" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState label={loading ? "Загрузка..." : "Нет данных по количеству"} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Категории: структура спроса</CardTitle>
            <CardDescription>Доля категорий по товарной выручке</CardDescription>
          </CardHeader>
          <CardContent>
            {categoriesChart.length ? (
              <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
                <div className="h-[320px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={categoriesChart} dataKey="revenue" nameKey="name" innerRadius={72} outerRadius={118} paddingAngle={2}>
                        {categoriesChart.map((entry, index) => (
                          <Cell key={entry.name} fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value) => tooltipCurrency(value as number)} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-2 self-center">
                  {categoriesChart.map((category, index) => (
                    <div key={category.category} className="flex items-center justify-between gap-3 text-sm">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: CATEGORY_COLORS[index % CATEGORY_COLORS.length] }} />
                        <span className="truncate text-gray-700">{category.category}</span>
                      </div>
                      <span className="shrink-0 font-medium text-gray-900">{currency.format(category.revenue)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyState label={loading ? "Загрузка..." : "Нет данных по категориям"} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Оборачиваемость по категориям</CardTitle>
            <CardDescription>Где товар быстрее превращается в продажи, а где зависает остаток</CardDescription>
          </CardHeader>
          <CardContent>
            {turnoverChart.length ? (
              <div className="h-[320px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={turnoverChart} margin={{ left: 8, right: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-25} textAnchor="end" height={70} />
                    <YAxis yAxisId="left" tickFormatter={(value) => plainNumber.format(Number(value))} />
                    <YAxis yAxisId="right" orientation="right" tickFormatter={(value) => compactNumber.format(Number(value))} />
                    <Tooltip formatter={(value) => tooltipNumber(value as number)} />
                    <Legend />
                    <Bar yAxisId="left" dataKey="turnover" name="Коэф. оборач." fill="#2563eb" radius={[4, 4, 0, 0]} />
                    <Bar yAxisId="right" dataKey="stock" name="Остаток" fill="#d97706" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState label={loading ? "Загрузка..." : "Нет данных по оборачиваемости"} />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Приоритетные товары для сайта</CardTitle>
            <CardDescription>Товары, которые стоит выводить в каталог/витрину первыми</CardDescription>
          </CardHeader>
          <CardContent>
            {data.priorityProducts.length ? (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="p-2 text-left font-semibold text-gray-700">Товар</th>
                      <th className="p-2 text-left font-semibold text-gray-700">Категория</th>
                      <th className="p-2 text-right font-semibold text-gray-700">Приоритет</th>
                      <th className="p-2 text-center font-semibold text-gray-700">Фото</th>
                      <th className="p-2 text-center font-semibold text-gray-700">Рекоменд.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.priorityProducts.slice(0, 10).map((product, index) => (
                      <tr key={`${product.product_id_1c || product.product_article || "product"}-${index}`} className="border-b hover:bg-gray-50">
                        <td className="p-2">
                          <div className="font-medium text-gray-900">{product.product_name || "Без названия"}</div>
                          <div className="text-xs text-gray-500">{product.product_article || "—"}{product.brand ? ` · ${product.brand}` : ""}</div>
                        </td>
                        <td className="p-2 text-gray-700">{product.category || "—"}</td>
                        <td className="p-2 text-right font-semibold text-gray-900">{plainNumber.format(product.priority_score || 0)}</td>
                        <td className="p-2 text-center">
                          <Badge variant="outline" className={product.has_images ? "border-green-200 bg-green-50 text-green-700" : "border-red-200 bg-red-50 text-red-700"}>
                            {product.has_images ? "есть" : "нет"}
                          </Badge>
                        </td>
                        <td className="p-2 text-center">
                          {product.is_recommended ? <Star className="mx-auto h-4 w-4 fill-yellow-500 text-yellow-500" /> : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState label={loading ? "Загрузка..." : "Нет рекомендованных товаров"} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Риски ассортимента</CardTitle>
            <CardDescription>По текущей выборке складской аналитики</CardDescription>
          </CardHeader>
          <CardContent>
            {inventoryRiskChart.length ? (
              <>
                <div className="mb-3 flex items-center gap-2">
                  <Badge variant="outline" className={healthStatusClass(health?.status)}>
                    {healthStatusLabel(health?.status)}
                  </Badge>
                  {health?.metrics?.source && (
                    <span className="text-xs text-gray-500">source: {health.metrics.source}</span>
                  )}
                </div>
                <div className="h-[260px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={inventoryRiskChart} dataKey="value" nameKey="name" outerRadius={100} label>
                        {inventoryRiskChart.map((entry) => (
                          <Cell key={entry.name} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value) => tooltipNumber(value as number)} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4" />
                    <span>Если дефицит высокий — первые действия: пополнение, перемещения между складами и скрытие товаров без доступности с сайта.</span>
                  </div>
                </div>
              </>
            ) : (
              <EmptyState label={loading ? "Загрузка..." : "Нет данных по складским рискам"} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
