'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { Product } from '@/types';
import DOMPurify from 'dompurify';
import ProductVariantsTable from '@/components/products/ProductVariantsTable';

export default function ProductDetailsPage() {
  const params = useParams();
  const productId = params.id as string;
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeImageIdx, setActiveImageIdx] = useState(0);
  const [variants, setVariants] = useState<Product[]>([]);
  const [variantsLoading, setVariantsLoading] = useState(false);
  const [variantsError, setVariantsError] = useState<string | null>(null);
  const [activeVariantId, setActiveVariantId] = useState<string | null>(null);
  const [baseProduct, setBaseProduct] = useState<Product | null>(null);

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


  const displayProduct = baseProduct ?? product;
  const selectedVariant = variants.find((variant) => variant.id === activeVariantId) ?? null;
  // Если текущий товар - это вариант (есть base, отличный от текущего), и он не найден в списке вариантов,
  // но activeVariantId установлен на его ID, используем текущий товар
  const isCurrentProductVariant = baseProduct && baseProduct.id !== product?.id;
  const effectiveProduct = selectedVariant ?? (isCurrentProductVariant && activeVariantId === product?.id ? product : displayProduct);

  const priceText = useMemo(() => {
    if (!effectiveProduct) return '';
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency: 'RUB',
      minimumFractionDigits: 0,
    }).format(effectiveProduct.price / 100);
  }, [effectiveProduct]);

  const safeDescriptionHtml = useMemo(() => {
    if (!displayProduct?.description) return '';
    return DOMPurify.sanitize(displayProduct.description, {
      USE_PROFILES: { html: true },
    });
  }, [displayProduct?.description]);

  useEffect(() => {
    if (!productId) {
      setError('ID товара не указан');
      setLoading(false);
      return;
    }

    let mounted = true;
    setLoading(true);
    setError(null);
    setProduct(null);
    setBaseProduct(null);
    setVariants([]);
    setVariantsError(null);
    setActiveVariantId(null);
    setActiveImageIdx(0);

    api
      .getProduct(productId)
      .then((data) => {
        if (!mounted) return;
        setProduct(data);
      })
      .catch((e: any) => {
        if (!mounted) return;
        const status = e?.response?.status;
        const detail = e?.response?.data?.detail;
        setError(detail || (status ? `Ошибка загрузки (HTTP ${status})` : 'Не удалось загрузить товар'));
      })
      .finally(() => {
        if (!mounted) return;
        setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [productId]);

  useEffect(() => {
    if (!product?.id) return;
    let mounted = true;
    setVariantsLoading(true);
    setVariantsError(null);

    api
      .getProductVariants(product.id)
      .then((data) => {
        if (!mounted) return;
        setVariants(data?.variants || []);
        setBaseProduct(data?.base || null);
        
        // Проверяем, является ли текущий товар вариантом
        // Если base существует и отличается от текущего товара, значит текущий товар - это вариант
        const isCurrentProductVariant = data?.base && data.base.id !== product.id;
        
        if (isCurrentProductVariant) {
          // Текущий товар - это вариант, устанавливаем его как активный
          // Проверяем, есть ли он в списке вариантов, если нет - добавляем его логику
          const variantInList = data?.variants?.some((v: Product) => v.id === product.id);
          if (variantInList) {
            setActiveVariantId(product.id);
          } else {
            // Вариант не найден в списке, но это вариант, устанавливаем его ID
            setActiveVariantId(product.id);
          }
        } else if (data?.variants?.length) {
          // Текущий товар - это родитель, устанавливаем первый вариант
          setActiveVariantId((prev) => prev || data.variants[0].id);
        }
      })
      .catch((e: any) => {
        if (!mounted) return;
        const status = e?.response?.status;
        const detail = e?.response?.data?.detail;
        setVariantsError(detail || (status ? `Ошибка вариантов (HTTP ${status})` : 'Не удалось загрузить варианты'));
      })
      .finally(() => {
        if (!mounted) return;
        setVariantsLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [product?.id]);

  useEffect(() => {
    setActiveImageIdx(0);
  }, [activeVariantId]);

  return (
    <main className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-6">
          <Link href="/products" className="text-sm text-gray-700 hover:text-gray-900">
            ← Назад к каталогу
          </Link>
        </div>

        {loading ? (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold-500 mx-auto"></div>
            <p className="text-gray-600 mt-4">Загрузка товара...</p>
          </div>
        ) : error ? (
          <div className="bg-white rounded-lg shadow p-8">
            <p className="text-red-900 font-medium">Ошибка</p>
            <p className="text-red-900 text-sm mt-1 font-medium">{error}</p>
          </div>
        ) : !product ? (
          <div className="bg-white rounded-lg shadow p-8">
            <p className="text-gray-700">Товар не найден</p>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                {(effectiveProduct?.images?.length || displayProduct?.images?.length) ? (
                  <>
                    <img
                      src={
                        (effectiveProduct?.images?.length ? effectiveProduct.images : displayProduct?.images || [])[
                          Math.min(
                            activeImageIdx,
                            (effectiveProduct?.images?.length ? effectiveProduct.images : displayProduct?.images || [])
                              .length - 1
                          )
                        ]
                      }
                      alt={displayProduct?.name || 'Product'}
                      className="w-full h-80 object-cover rounded-lg border border-gray-200"
                    />
                    {(effectiveProduct?.images?.length || displayProduct?.images?.length || 0) > 1 && (
                      <div className="mt-3 flex gap-2 overflow-x-auto">
                        {(effectiveProduct?.images?.length ? effectiveProduct.images : displayProduct?.images || []).map(
                          (img, idx) => (
                          <button
                            key={img + idx}
                            onClick={() => setActiveImageIdx(idx)}
                            className={`shrink-0 rounded border ${
                              idx === activeImageIdx ? 'border-gold-500' : 'border-gray-200'
                            }`}
                            aria-label={`Фото ${idx + 1}`}
                          >
                            <img src={img} alt="" className="h-16 w-16 object-cover rounded" />
                          </button>
                          )
                        )}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="w-full h-80 bg-gray-100 rounded-lg flex items-center justify-center border border-gray-200">
                    <span className="text-gray-500">Нет изображения</span>
                  </div>
                )}
              </div>

              <div className="text-gray-900">
                <h1 className="text-2xl font-bold text-gray-900">{displayProduct?.name}</h1>
                {displayProduct?.brand &&
                  displayProduct.brand !== '00000000-0000-0000-0000-000000000000' && (
                    <p className="mt-1 text-sm text-gray-700">{displayProduct.brand}</p>
                  )}
                {(effectiveProduct?.article || effectiveProduct?.external_code) && (
                  <p className="mt-1 text-sm text-gray-600">
                    Артикул:{' '}
                    <span className="font-medium text-gray-900">
                      {effectiveProduct?.article || effectiveProduct?.external_code}
                    </span>
                    {effectiveProduct?.article &&
                      effectiveProduct?.external_code &&
                      effectiveProduct.article !== effectiveProduct.external_code && (
                        <span className="ml-2 text-xs text-gray-500">
                          (Код 1С: {effectiveProduct.external_code})
                        </span>
                    )}
                  </p>
                )}

                {effectiveProduct?.stock !== undefined && effectiveProduct?.stock !== null && (
                  <p className="mt-2 text-sm">
                    {effectiveProduct.stock > 0 ? (
                      <span className="text-green-600 font-medium">В наличии: {Math.floor(effectiveProduct.stock)} шт.</span>
                    ) : (
                      <span className="text-red-600 font-medium">Нет в наличии</span>
                    )}
                  </p>
                )}

                <p className="mt-4 text-2xl font-bold text-gold-600">{priceText}</p>

                {/* Характеристики из specifications */}
                {effectiveProduct?.specifications && Object.keys(effectiveProduct.specifications).length > 0 ? (
                  <div className="mt-4">
                    <p className="text-sm font-medium text-gray-900 mb-2">Характеристики</p>
                    <div className="space-y-2">
                      {Object.entries(effectiveProduct.specifications)
                        .filter(([key, value]) => 
                          key !== 'parent_external_id' && 
                          key !== 'Parent_Key' &&
                          key !== 'parent_key' &&
                          !isEmptySpecValue(value) &&
                          typeof value !== 'object'
                        )
                        .map(([key, value], idx) => (
                          <div
                            key={key + idx}
                            className="px-3 py-2 bg-gray-50 border border-gray-200 rounded text-sm"
                          >
                            <span className="font-medium text-gray-900">{key}:</span>{' '}
                            <span className="text-gray-700">{String(value)}</span>
                          </div>
                        ))}
                    </div>
                  </div>
                ) : null}

                {/* Теги (если есть) */}
                {displayProduct?.tags?.length ? (
                  <div className="mt-4">
                    <p className="text-sm font-medium text-gray-900 mb-2">Теги</p>
                    <div className="flex flex-wrap gap-2">
                      {displayProduct.tags.map((tag, idx) => (
                        <span
                          key={tag + idx}
                          className="px-2 py-1 bg-gray-50 border border-gray-200 text-gray-800 text-xs rounded"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                {displayProduct?.description ? (
                  <div className="mt-6">
                    <p className="text-sm font-medium text-gray-900 mb-2">Описание</p>
                    <div
                      className="prose prose-sm max-w-none text-gray-800"
                      dangerouslySetInnerHTML={{ __html: safeDescriptionHtml }}
                    />
                  </div>
                ) : null}
              </div>
            </div>

            {variantsLoading ? (
              <div className="mt-8 text-sm text-gray-500">Загрузка вариантов...</div>
            ) : variantsError ? (
              <div className="mt-8 text-sm text-red-600">{variantsError}</div>
            ) : (
              <ProductVariantsTable
                variants={variants}
                activeVariantId={activeVariantId}
                onSelect={(variant) => setActiveVariantId(variant.id)}
              />
            )}
          </div>
        )}
      </div>
    </main>
  );
}

