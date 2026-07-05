"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { StoreSelect } from "@/components/inventory-control/StoreSelect";
import { PeriodSelect, type InventoryPeriodPreset } from "@/components/inventory-control/PeriodSelect";

type SalesStockRow = {
  nomenclature: string;
  color: string;
  category?: string | null;
  sold_qty?: number | null;
  stock_qty?: number | null;
  sales_month?: number | null;
  stock_cover?: number | null;
  status?: string | null;
};

function formatNumber(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("ru-RU", { maximumFractionDigits: digits });
}

function formatStatus(value: string | null | undefined) {
  if (!value) return "—";
  const map: Record<string, string> = {
    no_sales: "Нет продаж",
    critical_stock: "Критический остаток",
    reorder: "Нужен заказ",
    normal: "Норма",
    overstock: "Излишек",
    slow_moving: "Медленнооборачиваемый",
    unknown: "Неизвестно",
  };
  return map[value] || value;
}

export function InventorySalesStockPanel() {
  const [rows, setRows] = useState<SalesStockRow[]>([]);
  const [loading, setLoading] = useState(false);

  const [periodPreset, setPeriodPreset] = useState<InventoryPeriodPreset>("days");
  const [analysisPeriodDays, setAnalysisPeriodDays] = useState(90);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [storeId, setStoreId] = useState("");
  const [category, setCategory] = useState("");
  const [color, setColor] = useState("");
  const [brand, setBrand] = useState("");
  const [collection, setCollection] = useState("");

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
    if (category) p.set("category", category);
    if (color) p.set("color", color);
    if (brand) p.set("brand", brand);
    if (collection) p.set("collection", collection);
    return p.toString();
  }, [analysisPeriodDays, brand, category, collection, color, endDate, periodPreset, startDate, storeId]);

  const fetchReport = async (forceRefresh: boolean) => {
    try {
      setLoading(true);
      const res = await fetch(`/api/inventory/report?${query}${forceRefresh ? "&force_refresh=true" : ""}`);
      if (!res.ok) throw new Error("Ошибка загрузки отчёта");
      const json = await res.json();
      setRows((json?.rows || []) as SalesStockRow[]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport(false);
  }, [query]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle>Продажи и остатки</CardTitle>
              <CardDescription>Продажи, остатки, покрытие и статусы</CardDescription>
            </div>
            <Button onClick={() => fetchReport(true)} disabled={loading} variant="outline" size="sm">
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
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <FilterInput label="Категория" value={category} onChange={setCategory} />
            <FilterInput label="Цвет" value={color} onChange={setColor} />
            <FilterInput label="Бренд" value={brand} onChange={setBrand} />
            <FilterInput label="Коллекция" value={collection} onChange={setCollection} />
          </div>

          {loading ? (
            <div className="text-center py-8 text-gray-500">Загрузка...</div>
          ) : rows.length === 0 ? (
            <div className="text-center py-8 text-gray-500">Нет данных</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-gray-50 border-b">
                    <th className="text-left p-2 font-semibold text-gray-700">Номенклатура</th>
                    <th className="text-left p-2 font-semibold text-gray-700">Цвет</th>
                    <th className="text-left p-2 font-semibold text-gray-700">Категория</th>
                    <th className="text-right p-2 font-semibold text-gray-700">Продано</th>
                    <th className="text-right p-2 font-semibold text-gray-700">Остаток</th>
                    <th className="text-right p-2 font-semibold text-gray-700">Продажи/мес</th>
                    <th className="text-right p-2 font-semibold text-gray-700">Покрытие</th>
                    <th className="text-left p-2 font-semibold text-gray-700">Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, idx) => (
                    <tr key={`${r.nomenclature}-${r.color}-${idx}`} className="border-b hover:bg-gray-50">
                      <td className="p-2 text-gray-900">{r.nomenclature}</td>
                      <td className="p-2 text-gray-700">{r.color}</td>
                      <td className="p-2 text-gray-700">{r.category || "—"}</td>
                      <td className="p-2 text-right text-gray-700">{formatNumber(r.sold_qty)}</td>
                      <td className="p-2 text-right text-gray-700">{formatNumber(r.stock_qty)}</td>
                      <td className="p-2 text-right text-gray-700">{formatNumber(r.sales_month, 2)}</td>
                      <td className="p-2 text-right text-gray-700">{formatNumber(r.stock_cover, 2)}</td>
                      <td className="p-2 text-gray-700">{formatStatus(r.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function FilterInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="text-sm font-medium text-gray-700 mb-1 block">{label}</label>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
      />
    </div>
  );
}
