"use client";

import { useEffect, useMemo, useState } from "react";

type StoreItem = {
  id: string;
  external_id?: string | null;
  name: string;
  city?: string | null;
};

export function StoreSelect({
  label,
  value,
  onChange,
  includeWarehouse = false,
  includeAll = true,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  includeWarehouse?: boolean;
  includeAll?: boolean;
}) {
  const [stores, setStores] = useState<StoreItem[]>([]);
  const [loading, setLoading] = useState(false);

  const options = useMemo(() => {
    const out = stores
      .map((s) => ({
        value: String(s.external_id || s.id),
        label: `${s.name}${s.city ? ` (${s.city})` : ""}`,
      }))
      .filter((o) => o.value);
    out.sort((a, b) => a.label.localeCompare(b.label, "ru"));
    return out;
  }, [stores]);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const res = await fetch(`/api/analytics/stores${includeWarehouse ? "?include_warehouse=true" : ""}`);
        if (!res.ok) throw new Error("Ошибка загрузки списка магазинов");
        const json = await res.json();
        setStores((json?.stores || []) as StoreItem[]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [includeWarehouse]);

  return (
    <div>
      <label className="text-sm font-medium text-gray-700 mb-1 block">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm bg-white"
      >
        {includeAll && <option value="">{loading ? "Загрузка..." : "Все магазины"}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

