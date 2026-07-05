'use client';

import { useEffect, useMemo, useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import type { Product } from '@/types';

type TargetCategoryItem = {
  id: string;
  category: string;
  target_share: number;
  is_active: boolean;
};

export default function InventoryControlAdminPage() {
  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50">Администрирование запасов</h1>
      <Tabs defaultValue="matrix">
        <TabsList>
          <TabsTrigger value="matrix">Целевая матрица</TabsTrigger>
          <TabsTrigger value="flags">Защита бренда</TabsTrigger>
        </TabsList>

        <TabsContent value="matrix">
          <TargetMatrixPanel />
        </TabsContent>
        <TabsContent value="flags">
          <BrandProtectionPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function TargetMatrixPanel() {
  const [items, setItems] = useState<TargetCategoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const totalShare = useMemo(() => {
    return items.filter((i) => i.is_active).reduce((acc, i) => acc + (Number(i.target_share) || 0), 0);
  }, [items]);

  const load = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/inventory/target-matrix/categories');
      if (!res.ok) throw new Error('Ошибка загрузки матрицы');
      const json = await res.json();
      setItems((json?.items || []) as TargetCategoryItem[]);
    } finally {
      setLoading(false);
    }
  };

  const save = async () => {
    try {
      setSaving(true);
      const payload = items.map((i) => ({
        category: i.category,
        target_share: Number(i.target_share) || 0,
        is_active: Boolean(i.is_active),
      }));
      const res = await fetch('/api/inventory/target-matrix/categories', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Ошибка сохранения матрицы');
      await load();
    } finally {
      setSaving(false);
    }
  };

  const addRow = () => {
    setItems((prev) => [
      ...prev,
      { id: `new-${prev.length + 1}`, category: '', target_share: 0, is_active: true },
    ]);
  };

  const removeRow = async (id: string) => {
    if (id.startsWith('new-')) {
      setItems((prev) => prev.filter((x) => x.id !== id));
      return;
    }
    const res = await fetch(`/api/inventory/target-matrix/categories/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Ошибка удаления категории');
    await load();
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle>Целевая матрица по категориям</CardTitle>
            <CardDescription>Доля задаётся в диапазоне от 0 до 1</CardDescription>
            <div className="text-sm text-gray-600 mt-1">Сумма активных долей: {(totalShare * 100).toFixed(1)}%</div>
          </div>
          <div className="flex gap-2">
            <Button onClick={addRow} variant="outline" size="sm">Добавить</Button>
            <Button onClick={save} disabled={saving || loading} size="sm">Сохранить</Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="text-center py-8 text-gray-500">Загрузка...</div>
        ) : items.length === 0 ? (
          <div className="text-center py-8 text-gray-500">Матрица пустая</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b">
                  <th className="text-left p-2 font-semibold text-gray-700">Категория</th>
                  <th className="text-right p-2 font-semibold text-gray-700">Целевая доля</th>
                  <th className="text-center p-2 font-semibold text-gray-700">Активна</th>
                  <th className="text-right p-2 font-semibold text-gray-700">Действия</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.id} className="border-b hover:bg-gray-50">
                    <td className="p-2">
                      <input
                        value={it.category}
                        onChange={(e) => setItems((prev) => prev.map((x) => (x.id === it.id ? { ...x, category: e.target.value } : x)))}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                      />
                    </td>
                    <td className="p-2">
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        value={it.target_share}
                        onChange={(e) => setItems((prev) => prev.map((x) => (x.id === it.id ? { ...x, target_share: Number(e.target.value) } : x)))}
                        className="w-40 ml-auto block px-3 py-2 border border-gray-300 rounded-md text-sm text-right"
                      />
                    </td>
                    <td className="p-2 text-center">
                      <input
                        type="checkbox"
                        checked={it.is_active}
                        onChange={(e) => setItems((prev) => prev.map((x) => (x.id === it.id ? { ...x, is_active: e.target.checked } : x)))}
                        className="rounded border-gray-300"
                      />
                    </td>
                    <td className="p-2 text-right">
                      <Button onClick={() => removeRow(it.id)} variant="outline" size="sm">Удалить</Button>
                    </td>
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

function BrandProtectionPanel() {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      const data = await api.getProductsPaged({ search: query.trim() || undefined, limit: 25, skip: 0 });
      setItems((data?.items || []) as Product[]);
    } finally {
      setLoading(false);
    }
  };

  const updateFlags = async (productId: string, patch: Partial<Pick<Product, 'is_core_assortment' | 'supports_brand_concept'>>) => {
    const res = await fetch(`/api/products/${productId}/inventory-flags`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error('Ошибка обновления флагов');
    const updated = (await res.json()) as Product;
    setItems((prev) => prev.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)));
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle>Защита концепции бренда</CardTitle>
            <CardDescription>Флаги используются агентами для ограничения скидок/вывода</CardDescription>
          </div>
          <Button onClick={load} variant="outline" size="sm" disabled={loading}>Обновить</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск по названию / артикулу"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm"
          />
          <Button onClick={load} disabled={loading}>Найти</Button>
        </div>

        {loading ? (
          <div className="text-center py-8 text-gray-500">Загрузка...</div>
        ) : items.length === 0 ? (
          <div className="text-center py-8 text-gray-500">Нет товаров</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b">
                  <th className="text-left p-2 font-semibold text-gray-700">Товар</th>
                  <th className="text-left p-2 font-semibold text-gray-700">Категория</th>
                  <th className="text-center p-2 font-semibold text-gray-700">Ядро</th>
                  <th className="text-center p-2 font-semibold text-gray-700">Концепция бренда</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.id} className="border-b hover:bg-gray-50">
                    <td className="p-2 text-gray-900">{p.name}</td>
                    <td className="p-2 text-gray-700">{p.category || '—'}</td>
                    <td className="p-2 text-center">
                      <input
                        type="checkbox"
                        checked={Boolean(p.is_core_assortment)}
                        onChange={(e) => updateFlags(p.id, { is_core_assortment: e.target.checked })}
                        className="rounded border-gray-300"
                      />
                    </td>
                    <td className="p-2 text-center">
                      <input
                        type="checkbox"
                        checked={Boolean(p.supports_brand_concept)}
                        onChange={(e) => updateFlags(p.id, { supports_brand_concept: e.target.checked })}
                        className="rounded border-gray-300"
                      />
                    </td>
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
