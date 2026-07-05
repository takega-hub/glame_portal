"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { StoreSelect } from "@/components/inventory-control/StoreSelect";
import { PeriodSelect, type InventoryPeriodPreset } from "@/components/inventory-control/PeriodSelect";

type AssortmentRow = {
  category: string;
  sold_qty?: number | null;
  stock_qty?: number | null;
  category_share_sales?: number | null;
  category_share_stock?: number | null;
  target_share?: number | null;
  deviation?: number | null;
  recommendation?: string | null;
  warnings?: string[] | null;
};

type DiagnosticRow = {
  store_id?: string | null;
  store_name?: string | null;
  seller_id?: string | null;
  seller_external_id?: string | null;
  seller_name?: string | null;
  brand?: string | null;
  category?: string | null;
  nomenclature?: string | null;
  revenue?: number | null;
  sold_qty?: number | null;
  stock_qty?: number | null;
  checks_count?: number | null;
  diagnosis?: string | null;
  diagnostic_cause?: string | null;
  warning?: string | null;
  personal_output_blocked?: boolean;
};

type SalesDiagnostics = {
  stores?: DiagnosticRow[];
  sellers?: DiagnosticRow[];
  brands?: DiagnosticRow[];
  categories?: DiagnosticRow[];
  positions?: DiagnosticRow[];
  diagnostics?: {
    stock_without_sales?: DiagnosticRow[];
    low_or_no_stock_with_sales?: DiagnosticRow[];
    seller_personal_conclusions?: {
      blocked?: boolean;
      warning?: string | null;
    };
    reason_classes?: string[];
  };
  data_quality?: {
    unattributed_seller_share?: number | null;
    unmatched_revenue_share?: number | null;
    warnings?: string[] | null;
  };
  warnings?: string[] | null;
};

type PlanSource = {
  source_url?: string | null;
  source_file?: string | null;
  store_name?: string | null;
  store_id?: string | null;
  period?: string | null;
  import_status?: string | null;
  import_source?: string | null;
  source_system?: string | null;
  storage?: string | null;
  warnings?: string[];
};

type FilterOption = {
  value: string;
  label: string;
  seller_id?: string | null;
  seller_name?: string | null;
};

type AssortmentFilterOptions = {
  sellers: FilterOption[];
  brands: string[];
  categories: string[];
};

function formatNumber(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("ru-RU", { maximumFractionDigits: digits });
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatAssortmentRecommendation(value: string | null | undefined) {
  if (!value) return "—";
  const map: Record<string, string> = {
    reduce_stock_share: "Снизить долю склада",
    increase_stock_share: "Увеличить долю склада",
  };
  return map[value] || value;
}

export function InventoryAssortmentStructurePanel() {
  const [rows, setRows] = useState<AssortmentRow[]>([]);
  const [diagnostics, setDiagnostics] = useState<SalesDiagnostics | null>(null);
  const [planSource, setPlanSource] = useState<PlanSource | null>(null);
  const [loading, setLoading] = useState(false);
  const [periodPreset, setPeriodPreset] = useState<InventoryPeriodPreset>("days");
  const [analysisPeriodDays, setAnalysisPeriodDays] = useState(90);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [storeId, setStoreId] = useState("");
  const [sellerId, setSellerId] = useState("");
  const [sellerName, setSellerName] = useState("");
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("");
  const [filterOptions, setFilterOptions] = useState<AssortmentFilterOptions>({ sellers: [], brands: [], categories: [] });
  const [filtersLoading, setFiltersLoading] = useState(false);

  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (periodPreset === "days") {
      p.set("analysis_period_days", String(analysisPeriodDays));
    } else if (periodPreset === "custom") {
      p.set("period", "custom");
      if (startDate) p.set("start_date", startDate);
      if (endDate) p.set("end_date", endDate);
    } else {
      p.set("period", periodPreset);
    }
    if (storeId) p.set("store_id", storeId);
    if (sellerId) p.set("seller_id", sellerId);
    if (sellerName) p.set("seller_name", sellerName);
    if (brand) p.set("brand", brand);
    if (category) p.set("category", category);
    return p.toString();
  }, [analysisPeriodDays, brand, category, endDate, periodPreset, sellerId, sellerName, startDate, storeId]);

  const filterOptionsQuery = useMemo(() => {
    const p = new URLSearchParams();
    if (periodPreset === "days") {
      p.set("analysis_period_days", String(analysisPeriodDays));
    } else if (periodPreset === "custom") {
      p.set("period", "custom");
      if (startDate) p.set("start_date", startDate);
      if (endDate) p.set("end_date", endDate);
    } else {
      p.set("period", periodPreset);
    }
    if (storeId) p.set("store_id", storeId);
    return p.toString();
  }, [analysisPeriodDays, endDate, periodPreset, startDate, storeId]);

  const fetchAssortment = useCallback(
    async (forceRefresh: boolean) => {
      try {
        setLoading(true);
        const res = await fetch(`/api/inventory/assortment?${query}${forceRefresh ? "&force_refresh=true" : ""}`);
        if (!res.ok) throw new Error("Ошибка загрузки структуры ассортимента");
        const json = await res.json();
        setRows((json?.rows || []) as AssortmentRow[]);
        setDiagnostics((json?.sales_diagnostics || null) as SalesDiagnostics | null);
        setPlanSource((json?.plan_source || null) as PlanSource | null);
      } finally {
        setLoading(false);
      }
    },
    [query],
  );

  useEffect(() => {
    fetchAssortment(false);
  }, [fetchAssortment]);

  useEffect(() => {
    const loadFilterOptions = async () => {
      try {
        setFiltersLoading(true);
        const res = await fetch(`/api/inventory/assortment/filters?${filterOptionsQuery}`);
        if (!res.ok) throw new Error("Ошибка загрузки фильтров ассортимента");
        const json = await res.json();
        setFilterOptions({
          sellers: Array.isArray(json?.sellers) ? json.sellers : [],
          brands: Array.isArray(json?.brands) ? json.brands : [],
          categories: Array.isArray(json?.categories) ? json.categories : [],
        });
      } finally {
        setFiltersLoading(false);
      }
    };
    loadFilterOptions();
  }, [filterOptionsQuery]);

  const handleSellerChange = (value: string) => {
    const selected = filterOptions.sellers.find((option) => option.value === value);
    setSellerId(value);
    setSellerName(selected?.seller_name || "");
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle>Структура ассортимента</CardTitle>
              <CardDescription>Доли продаж/склада по категориям и отклонения от целевой матрицы</CardDescription>
            </div>
            <Button onClick={() => fetchAssortment(true)} disabled={loading} variant="outline" size="sm">
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
              Обновить
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <PeriodSelect
              value={periodPreset}
              onChange={setPeriodPreset}
              days={analysisPeriodDays}
              onDaysChange={setAnalysisPeriodDays}
              startDate={startDate}
              endDate={endDate}
              onStartDateChange={setStartDate}
              onEndDateChange={setEndDate}
            />
            <StoreSelect label="Магазин" value={storeId} onChange={setStoreId} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <AssortmentFilterSelect
              label="Продавец"
              value={sellerId}
              onChange={handleSellerChange}
              placeholder={filtersLoading ? "Загрузка продавцов..." : "Все продавцы"}
              options={filterOptions.sellers}
            />
            <AssortmentFilterSelect
              label="Бренд"
              value={brand}
              onChange={setBrand}
              placeholder={filtersLoading ? "Загрузка брендов..." : "Все бренды"}
              options={filterOptions.brands.map((item) => ({ value: item, label: item }))}
            />
            <AssortmentFilterSelect
              label="Категория"
              value={category}
              onChange={setCategory}
              placeholder={filtersLoading ? "Загрузка категорий..." : "Все категории"}
              options={filterOptions.categories.map((item) => ({ value: item, label: item }))}
            />
          </div>

          {loading ? (
            <div className="text-center py-8 text-gray-500">Загрузка...</div>
          ) : rows.length === 0 ? (
            <div className="text-center py-8 text-gray-500">Нет данных</div>
          ) : (
            <div className="space-y-4">
              {diagnostics?.data_quality?.warnings?.length || diagnostics?.warnings?.length ? (
                <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  Предупреждение качества данных: {[...(diagnostics.data_quality?.warnings || []), ...(diagnostics.warnings || [])].join(", ")}
                  {diagnostics.data_quality?.unattributed_seller_share !== undefined
                    ? ` · не сопоставлено с продавцом: ${formatPercent(diagnostics.data_quality.unattributed_seller_share)}`
                    : ""}
                </div>
              ) : null}

              {diagnostics?.diagnostics?.seller_personal_conclusions?.blocked ? (
                <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  Личные выводы по продавцу заблокированы: {diagnostics.diagnostics.seller_personal_conclusions.warning || "нет seller_id"}. Это предупреждение качества данных, не факт о навыке продавца.
                </div>
              ) : null}

              {planSource ? (
                <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700 space-y-1">
                  <div>
                    План в БД: {planSource.store_name || "—"} · период {planSource.period || "—"} · статус {planSource.import_status || "—"}
                    {planSource.warnings?.length ? ` · ${planSource.warnings.join(", ")}` : ""}
                  </div>
                  <div className="text-xs text-gray-500">
                    Хранилище: {planSource.storage || "seller_monthly_plans"}
                    {planSource.import_source ? ` · источник импорта: ${planSource.import_source}` : ""}
                    {planSource.source_file ? ` · файл: ${planSource.source_file}` : ""}
                    {planSource.source_url ? ` · provenance URL: ${planSource.source_url}` : ""}
                  </div>
                </div>
              ) : null}

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                <DiagnosticMiniTable title="Магазины" rows={diagnostics?.stores || []} labelKey="store_name" />
                <DiagnosticMiniTable title="Продавцы" rows={diagnostics?.sellers || []} labelKey="seller_name" empty="Нет seller_id — личные выводы заблокированы warning-ом" />
                <DiagnosticMiniTable title="Бренды" rows={diagnostics?.brands || []} labelKey="brand" />
                <DiagnosticMiniTable title="Категории" rows={diagnostics?.categories || []} labelKey="category" />
                <DiagnosticMiniTable title="Позиции" rows={diagnostics?.positions || []} labelKey="nomenclature" />
                <DiagnosticMiniTable title="Остаток без продаж" rows={diagnostics?.diagnostics?.stock_without_sales || []} labelKey="nomenclature" valueKey="stock_qty" />
                <DiagnosticMiniTable title="Продажи при низком/нулевом остатке" rows={diagnostics?.diagnostics?.low_or_no_stock_with_sales || []} labelKey="nomenclature" valueKey="sold_qty" />
              </div>

              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="bg-gray-50 border-b">
                      <th className="text-left p-2 font-semibold text-gray-700">Категория</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Продано</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Остаток</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Доля продаж</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Доля склада</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Целевая доля</th>
                      <th className="text-right p-2 font-semibold text-gray-700">Отклонение</th>
                      <th className="text-left p-2 font-semibold text-gray-700">Рекомендация</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, idx) => (
                      <tr key={`${r.category}-${idx}`} className="border-b hover:bg-gray-50">
                        <td className="p-2 text-gray-900">{r.category}</td>
                        <td className="p-2 text-right text-gray-700">{formatNumber(r.sold_qty)}</td>
                        <td className="p-2 text-right text-gray-700">{formatNumber(r.stock_qty)}</td>
                        <td className="p-2 text-right text-gray-700">{formatPercent(r.category_share_sales)}</td>
                        <td className="p-2 text-right text-gray-700">{formatPercent(r.category_share_stock)}</td>
                        <td className="p-2 text-right text-gray-700">{formatPercent(r.target_share)}</td>
                        <td className="p-2 text-right text-gray-700">{formatPercent(r.deviation)}</td>
                        <td className="p-2 text-gray-700">{formatAssortmentRecommendation(r.recommendation)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function AssortmentFilterSelect({
  label,
  value,
  onChange,
  placeholder,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  options: FilterOption[];
}) {
  return (
    <div>
      <label className="text-sm font-medium text-gray-700 mb-1 block">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm bg-white"
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function DiagnosticMiniTable({
  title,
  rows,
  labelKey,
  valueKey = "revenue",
  empty = "Нет данных",
}: {
  title: string;
  rows: DiagnosticRow[];
  labelKey: keyof DiagnosticRow;
  valueKey?: keyof DiagnosticRow;
  empty?: string;
}) {
  const visible = rows.slice(0, 5);
  return (
    <div className="rounded-md border border-gray-200 p-3">
      <div className="font-semibold text-gray-800 mb-2">{title}</div>
      {visible.length === 0 ? (
        <div className="text-xs text-gray-500">{empty}</div>
      ) : (
        <div className="space-y-2">
          {visible.map((row, idx) => (
            <div key={`${title}-${idx}`} className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate text-gray-700">{String(row[labelKey] || "—")}</span>
              <span className="shrink-0 font-medium text-gray-900">{formatNumber(row[valueKey] as number | null | undefined, 1)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
