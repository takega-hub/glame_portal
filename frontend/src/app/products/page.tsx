'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '@/lib/api';
import { Product } from '@/types';
import ProductCard from '@/components/products/ProductCard';
import OneCSyncUpload from '@/components/products/OneCSyncUpload';
import * as XLSX from 'xlsx';

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(24);
  const [refreshKey, setRefreshKey] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [exporting, setExporting] = useState(false);
  const [catalogSections, setCatalogSections] = useState<Array<{ id: string; name: string }>>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [characteristics, setCharacteristics] = useState<Record<string, string[]>>({});
  const [selectedFilters, setSelectedFilters] = useState<Record<string, string>>({});
  const [showFilters, setShowFilters] = useState(false);
  const [inStockOnly, setInStockOnly] = useState(false);

  const pageCount = useMemo(() => Math.max(1, Math.ceil(total / pageSize)), [total, pageSize]);

  const loadProducts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const skip = (page - 1) * pageSize;
      const params: { 
        skip: number; 
        limit: number; 
        search?: string; 
        category?: string;
        brand?: string;
        material?: string;
        vstavka?: string;
        pokrytie?: string;
        razmer?: string;
        tip_zamka?: string;
        color?: string;
        in_stock?: boolean;
      } = {
        skip,
        limit: pageSize,
      };
      if (searchQuery.trim()) {
        params.search = searchQuery.trim();
      }
      if (selectedCategory) {
        params.category = selectedCategory;
      }
      // Добавляем фильтры по характеристикам
      if (selectedFilters.brand) {
        params.brand = selectedFilters.brand;
      }
      if (selectedFilters.material) {
        params.material = selectedFilters.material;
      }
      if (selectedFilters.vstavka) {
        params.vstavka = selectedFilters.vstavka;
      }
      if (selectedFilters.pokrytie) {
        params.pokrytie = selectedFilters.pokrytie;
      }
      if (selectedFilters.razmer) {
        params.razmer = selectedFilters.razmer;
      }
      if (selectedFilters.tip_zamka) {
        params.tip_zamka = selectedFilters.tip_zamka;
      }
      if (selectedFilters.color) {
        params.color = selectedFilters.color;
      }
      if (inStockOnly) {
        params.in_stock = true;
      }
      const data = await api.getProductsPaged(params);
      setProducts(Array.isArray(data?.items) ? data.items : []);
      setTotal(typeof data?.total === 'number' ? data.total : 0);
    } catch (e: any) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      setError(detail || (status ? `Ошибка загрузки (HTTP ${status})` : 'Не удалось загрузить товары'));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, searchQuery, selectedCategory, selectedFilters, inStockOnly]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      if (!mounted) return;
      await loadProducts();
    })();
    return () => {
      mounted = false;
    };
  }, [loadProducts, refreshKey]);

  useEffect(() => {
    // если total уменьшился/изменился и страница вышла за предел — поправим
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const sections = await api.getCatalogSections();
        if (!mounted) return;
        setCatalogSections(
          Array.isArray(sections)
            ? sections.map((section) => ({ id: section.id, name: section.name }))
            : []
        );
      } catch (e) {
        // Молча игнорируем, фильтр необязателен
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const chars = await api.getCharacteristicsValues();
        if (!mounted) return;
        console.log('Загружены характеристики:', chars);
        setCharacteristics(chars || {});
      } catch (e) {
        console.error('Ошибка загрузки характеристик:', e);
        // Молча игнорируем, фильтры необязательны
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const visiblePages = useMemo(() => {
    // показываем окно страниц вокруг текущей (до 7 кнопок)
    const maxButtons = 7;
    const half = Math.floor(maxButtons / 2);
    let start = Math.max(1, page - half);
    let end = Math.min(pageCount, start + maxButtons - 1);
    start = Math.max(1, end - maxButtons + 1);
    const pages: number[] = [];
    for (let p = start; p <= end; p++) pages.push(p);
    return pages;
  }, [page, pageCount]);

  // Общая функция для загрузки товаров с описаниями
  const loadProductsWithDescriptions = async (): Promise<Array<{
    external_code: string;
    name: string;
    description: string;
  }>> => {
    const allProductsWithDescriptions: Array<{
      external_code: string;
      name: string;
      description: string;
    }> = [];
    
    let skip = 0;
    const limit = 100;
    let hasMore = true;
    
    while (hasMore) {
      const data = await api.getProductsPaged({ skip, limit });
      const products = data.items || [];
      
      // Фильтруем товары с описаниями
      const productsWithDesc = products
        .filter((p: any) => p.description && p.description.trim().length > 0)
        .map((p: any) => ({
          external_code: p.external_code || '',
          name: p.name || '',
          description: p.description || '',
        }));
      
      allProductsWithDescriptions.push(...productsWithDesc);
      
      // Проверяем, есть ли еще товары
      hasMore = products.length === limit && skip + limit < data.total;
      skip += limit;
    }
    
    return allProductsWithDescriptions;
  };

  const exportProductsToCSV = async () => {
    try {
      setExporting(true);
      setError(null);
      
      const allProductsWithDescriptions = await loadProductsWithDescriptions();
      
      if (allProductsWithDescriptions.length === 0) {
        alert('Нет товаров с описаниями для экспорта');
        return;
      }
      
      // Создаем CSV
      const csvHeaders = ['Артикул', 'Название', 'Описание'];
      const csvRows = allProductsWithDescriptions.map(product => {
        // Экранируем кавычки и переносы строк в CSV
        const escapeCSV = (text: string) => {
          if (!text) return '';
          // Заменяем кавычки на двойные кавычки
          const escaped = text.replace(/"/g, '""');
          // Если есть запятые, переносы строк или кавычки, оборачиваем в кавычки
          if (escaped.includes(',') || escaped.includes('\n') || escaped.includes('"')) {
            return `"${escaped}"`;
          }
          return escaped;
        };
        
        return [
          escapeCSV(product.external_code),
          escapeCSV(product.name),
          escapeCSV(product.description),
        ].join(',');
      });
      
      const csvContent = [csvHeaders.join(','), ...csvRows].join('\n');
      
      // Создаем BOM для правильного отображения кириллицы в Excel
      const BOM = '\uFEFF';
      const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
      
      // Создаем ссылку для скачивания
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      link.setAttribute('href', url);
      link.setAttribute('download', `products_descriptions_${new Date().toISOString().split('T')[0]}.csv`);
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      // Освобождаем память
      URL.revokeObjectURL(url);
    } catch (e: any) {
      const errorMessage = e.response?.data?.detail || e.message || 'Ошибка при экспорте в CSV';
      setError(errorMessage);
      alert(`Ошибка при экспорте: ${errorMessage}`);
    } finally {
      setExporting(false);
    }
  };


  const exportProductsToXLSX = async () => {
    try {
      setExporting(true);
      setError(null);
      
      const allProductsWithDescriptions = await loadProductsWithDescriptions();
      
      if (allProductsWithDescriptions.length === 0) {
        alert('Нет товаров с описаниями для экспорта');
        return;
      }
      
      // Подготавливаем данные для Excel
      const worksheetData = [
        ['Артикул', 'Название', 'Описание'], // Заголовки
        ...allProductsWithDescriptions.map(product => [
          product.external_code,
          product.name,
          product.description,
        ]),
      ];
      
      // Создаем рабочую книгу
      const worksheet = XLSX.utils.aoa_to_sheet(worksheetData);
      
      // Настраиваем ширину колонок
      worksheet['!cols'] = [
        { wch: 15 }, // Артикул
        { wch: 50 }, // Название
        { wch: 80 }, // Описание
      ];
      
      // Создаем рабочую книгу
      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheet, 'Товары');
      
      // Генерируем файл
      const excelBuffer = XLSX.write(workbook, { 
        bookType: 'xlsx', 
        type: 'array',
        cellStyles: true,
      });
      
      // Создаем blob и скачиваем
      const blob = new Blob([excelBuffer], { 
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
      });
      
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      link.setAttribute('href', url);
      link.setAttribute('download', `products_descriptions_${new Date().toISOString().split('T')[0]}.xlsx`);
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      // Освобождаем память
      URL.revokeObjectURL(url);
    } catch (e: any) {
      const errorMessage = e.response?.data?.detail || e.message || 'Ошибка при экспорте в XLSX';
      setError(errorMessage);
      alert(`Ошибка при экспорте: ${errorMessage}`);
    } finally {
      setExporting(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Каталог товаров</h1>
          <p className="mt-2 text-gray-600">
            Просмотр и управление каталогом украшений GLAME
          </p>
        </div>

        {/* Компонент синхронизации с 1С */}
        <OneCSyncUpload
          onSyncComplete={() => {
            setPage(1);
            setRefreshKey((k) => k + 1);
          }}
        />

        {/* Поиск по товарам */}
        <div className="mb-6 bg-white rounded-lg shadow p-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              type="text"
              placeholder="Поиск по названию или артикулу..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(1); // Сбрасываем на первую страницу при поиске
              }}
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-transparent text-gray-900"
            />
            <select
              value={selectedCategory}
              onChange={(e) => {
                setSelectedCategory(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900"
            >
              <option value="">Все разделы</option>
              {catalogSections.map((section) => (
                <option key={section.id} value={section.name}>
                  {section.name}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 text-sm">
              <input
                type="checkbox"
                checked={inStockOnly}
                onChange={(e) => {
                  setInStockOnly(e.target.checked);
                  setPage(1);
                }}
                className="h-4 w-4"
              />
              В наличии
            </label>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 bg-white text-gray-700"
            >
              {showFilters ? 'Скрыть фильтры' : 'Фильтры'}
            </button>
            {(searchQuery || Object.keys(selectedFilters).length > 0 || inStockOnly) && (
              <button
                onClick={() => {
                  setSearchQuery('');
                  setSelectedFilters({});
                  setInStockOnly(false);
                  setPage(1);
                }}
                className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 bg-white text-gray-700"
              >
                Очистить
              </button>
            )}
          </div>
          
          {/* Фильтры по характеристикам */}
          {showFilters && (
            <div className="mt-4 pt-4 border-t border-gray-200">
              {Object.keys(characteristics).length === 0 ? (
                <div className="text-sm text-gray-500 py-2">
                  Загрузка фильтров...
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
                  {/* Бренд */}
                  {characteristics['Бренд'] && characteristics['Бренд'].length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Бренд</label>
                    <select
                      value={selectedFilters.brand || ''}
                      onChange={(e) => {
                        const newFilters = { ...selectedFilters };
                        if (e.target.value) {
                          newFilters.brand = e.target.value;
                        } else {
                          delete newFilters.brand;
                        }
                        setSelectedFilters(newFilters);
                        setPage(1);
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 text-sm"
                    >
                      <option value="">Все</option>
                      {characteristics['Бренд'].map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                
                {/* Материал */}
                {characteristics['Материал'] && characteristics['Материал'].length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Материал</label>
                    <select
                      value={selectedFilters.material || ''}
                      onChange={(e) => {
                        const newFilters = { ...selectedFilters };
                        if (e.target.value) {
                          newFilters.material = e.target.value;
                        } else {
                          delete newFilters.material;
                        }
                        setSelectedFilters(newFilters);
                        setPage(1);
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 text-sm"
                    >
                      <option value="">Все</option>
                      {characteristics['Материал'].map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                
                {/* Вставка */}
                {characteristics['Вставка'] && characteristics['Вставка'].length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Вставка</label>
                    <select
                      value={selectedFilters.vstavka || ''}
                      onChange={(e) => {
                        const newFilters = { ...selectedFilters };
                        if (e.target.value) {
                          newFilters.vstavka = e.target.value;
                        } else {
                          delete newFilters.vstavka;
                        }
                        setSelectedFilters(newFilters);
                        setPage(1);
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 text-sm"
                    >
                      <option value="">Все</option>
                      {characteristics['Вставка'].map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                
                {/* Покрытие */}
                {characteristics['Покрытие'] && characteristics['Покрытие'].length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Покрытие</label>
                    <select
                      value={selectedFilters.pokrytie || ''}
                      onChange={(e) => {
                        const newFilters = { ...selectedFilters };
                        if (e.target.value) {
                          newFilters.pokrytie = e.target.value;
                        } else {
                          delete newFilters.pokrytie;
                        }
                        setSelectedFilters(newFilters);
                        setPage(1);
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 text-sm"
                    >
                      <option value="">Все</option>
                      {characteristics['Покрытие'].map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                
                {/* Размер */}
                {characteristics['Размер'] && characteristics['Размер'].length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Размер</label>
                    <select
                      value={selectedFilters.razmer || ''}
                      onChange={(e) => {
                        const newFilters = { ...selectedFilters };
                        if (e.target.value) {
                          newFilters.razmer = e.target.value;
                        } else {
                          delete newFilters.razmer;
                        }
                        setSelectedFilters(newFilters);
                        setPage(1);
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 text-sm"
                    >
                      <option value="">Все</option>
                      {characteristics['Размер'].map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                
                {/* Тип замка */}
                {characteristics['Тип замка'] && characteristics['Тип замка'].length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Тип замка</label>
                    <select
                      value={selectedFilters.tip_zamka || ''}
                      onChange={(e) => {
                        const newFilters = { ...selectedFilters };
                        if (e.target.value) {
                          newFilters.tip_zamka = e.target.value;
                        } else {
                          delete newFilters.tip_zamka;
                        }
                        setSelectedFilters(newFilters);
                        setPage(1);
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 text-sm"
                    >
                      <option value="">Все</option>
                      {characteristics['Тип замка'].map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                
                {/* Цвет */}
                {characteristics['Цвет'] && characteristics['Цвет'].length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Цвет</label>
                    <select
                      value={selectedFilters.color || ''}
                      onChange={(e) => {
                        const newFilters = { ...selectedFilters };
                        if (e.target.value) {
                          newFilters.color = e.target.value;
                        } else {
                          delete newFilters.color;
                        }
                        setSelectedFilters(newFilters);
                        setPage(1);
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 text-sm"
                    >
                      <option value="">Все</option>
                      {characteristics['Цвет'].map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                </div>
              )}
            </div>
          )}
          
          {(searchQuery || Object.keys(selectedFilters).length > 0) && (
            <p className="mt-2 text-sm text-gray-600">
              Найдено товаров: {total}
            </p>
          )}
        </div>

        {/* Список товаров */}
        {loading ? (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold-500 mx-auto"></div>
            <p className="text-gray-500 mt-4">Загрузка товаров...</p>
          </div>
        ) : error ? (
          <div className="bg-white rounded-lg shadow p-8">
            <p className="text-red-900 font-medium">Ошибка</p>
            <p className="text-red-900 text-sm mt-1 font-medium">{error}</p>
          </div>
        ) : total === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <p className="text-gray-500 text-lg">
              Каталог товаров пуст
            </p>
            <p className="text-gray-400 text-sm mt-2">
              Загрузите файл каталога из 1С используя форму выше
            </p>
          </div>
        ) : (
          <>
            <div className="mb-4 flex justify-between items-center">
              <h2 className="text-xl font-semibold text-gray-900">
                Товары ({total})
              </h2>
              <div className="flex gap-2">
                <button
                  onClick={exportProductsToCSV}
                  disabled={exporting || loading}
                  className="px-4 py-2 text-sm border border-blue-300 text-blue-700 rounded-lg hover:bg-blue-50 bg-white disabled:opacity-50"
                >
                  {exporting ? 'Экспорт...' : 'Выгрузить в CSV'}
                </button>
                <button
                  onClick={exportProductsToXLSX}
                  disabled={exporting || loading}
                  className="px-4 py-2 text-sm border border-green-300 text-green-700 rounded-lg hover:bg-green-50 bg-white disabled:opacity-50"
                >
                  {exporting ? 'Экспорт...' : 'Выгрузить в XLSX'}
                </button>
                <button
                  onClick={() => setRefreshKey((k) => k + 1)}
                  className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 bg-white text-gray-700"
                >
                  Обновить список
                </button>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {products.map((product) => (
                <ProductCard key={product.id} product={product} />
              ))}
            </div>

            {/* Пейджер */}
            <div className="mt-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="text-sm text-gray-700">
                Страница <span className="font-medium">{page}</span> из{' '}
                <span className="font-medium">{pageCount}</span>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-700">На странице:</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPage(1);
                    setPageSize(Number(e.target.value));
                  }}
                  className="px-2 py-1 border border-gray-300 rounded bg-white text-gray-700 text-sm"
                >
                  <option value={12}>12</option>
                  <option value={24}>24</option>
                  <option value={48}>48</option>
                  <option value={100}>100</option>
                </select>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ←
                </button>

                <div className="flex items-center gap-1">
                  {visiblePages[0] > 1 && (
                    <>
                      <button
                        onClick={() => setPage(1)}
                        className="px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white text-gray-700 hover:bg-gray-50"
                      >
                        1
                      </button>
                      {visiblePages[0] > 2 && <span className="px-1 text-gray-500">…</span>}
                    </>
                  )}

                  {visiblePages.map((p) => (
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className={`px-3 py-2 text-sm border rounded-lg ${
                        p === page
                          ? 'border-gold-600 bg-gold-50 text-gold-700'
                          : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {p}
                    </button>
                  ))}

                  {visiblePages[visiblePages.length - 1] < pageCount && (
                    <>
                      {visiblePages[visiblePages.length - 1] < pageCount - 1 && (
                        <span className="px-1 text-gray-500">…</span>
                      )}
                      <button
                        onClick={() => setPage(pageCount)}
                        className="px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white text-gray-700 hover:bg-gray-50"
                      >
                        {pageCount}
                      </button>
                    </>
                  )}
                </div>

                <button
                  onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                  disabled={page >= pageCount}
                  className="px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  →
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
