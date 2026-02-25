'use client';

import { useMemo } from 'react';
import type { Product } from '@/types';

interface ProductVariantsTableProps {
  variants: Product[];
  activeVariantId?: string | null;
  onSelect?: (variant: Product) => void;
}

const isEmptySpecValue = (value: unknown) => {
  if (value === null || value === undefined) return true;
  if (typeof value === 'boolean') return value === false;
  if (typeof value === 'number') return value === 0 || Number.isNaN(value);
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return (
      trimmed === '' ||
      trimmed === '0' ||
      trimmed === '0.0' ||
      trimmed === 'false' ||
      trimmed === '00000000-0000-0000-0000-000000000000'
    );
  }
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'object') return Object.keys(value as Record<string, unknown>).length === 0;
  return false;
};

const formatPrice = (value: number) =>
  new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    minimumFractionDigits: 0,
  }).format(value / 100);

export default function ProductVariantsTable({
  variants,
  activeVariantId,
  onSelect,
}: ProductVariantsTableProps) {
  const propertyKeys = useMemo(() => {
    const counts = new Map<string, number>();
    variants.forEach((variant) => {
      const specs = variant.specifications;
      if (!specs || typeof specs !== 'object') return;
      Object.entries(specs).forEach(([key, value]) => {
        if (
          key === 'parent_external_id' ||
          key === 'Parent_Key' ||
          key === 'parent_key' ||
          typeof value === 'object' ||
          isEmptySpecValue(value)
        ) {
          return;
        }
        counts.set(key, (counts.get(key) || 0) + 1);
      });
    });
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([key]) => key)
      .slice(0, 6);
  }, [variants]);

  if (!variants.length) return null;

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-gray-900">Варианты товара</p>
        <p className="text-xs text-gray-500">{variants.length} вариантов</p>
      </div>
      <div className="mt-3 overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full text-sm text-gray-800">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-3 py-2 text-left">Фото</th>
              <th className="px-3 py-2 text-left">Артикул</th>
              <th className="px-3 py-2 text-left">Цена</th>
              {propertyKeys.map((key) => (
                <th key={key} className="px-3 py-2 text-left">
                  {key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {variants.map((variant) => {
              const isActive = variant.id === activeVariantId;
              return (
                <tr
                  key={variant.id}
                  className={`border-t border-gray-200 ${isActive ? 'bg-gold-50/60' : 'bg-white'} ${
                    onSelect ? 'cursor-pointer hover:bg-gray-50' : ''
                  }`}
                  onClick={() => onSelect?.(variant)}
                >
                  <td className="px-3 py-2">
                    {variant.images?.[0] ? (
                      <img
                        src={variant.images[0]}
                        alt={variant.name}
                        className="h-10 w-10 rounded border border-gray-200 object-cover"
                      />
                    ) : (
                      <div className="h-10 w-10 rounded border border-gray-200 bg-gray-100" />
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-medium text-gray-900">
                      {variant.article || variant.external_code || '—'}
                    </div>
                    {variant.article && variant.external_code && variant.article !== variant.external_code && (
                      <div className="text-xs text-gray-500">Код 1С: {variant.external_code}</div>
                    )}
                  </td>
                  <td className="px-3 py-2 font-medium text-gray-900">
                    {formatPrice(variant.price)}
                  </td>
                  {propertyKeys.map((key) => (
                    <td key={key} className="px-3 py-2 text-gray-700">
                      {variant.specifications && !isEmptySpecValue(variant.specifications[key])
                        ? String(variant.specifications[key])
                        : '—'}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
