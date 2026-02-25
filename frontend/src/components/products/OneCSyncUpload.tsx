'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { api, OneCSyncResponse, OneCSyncStatus } from '@/lib/api';

interface OneCSyncUploadProps {
  onSyncComplete?: () => void;
}

export default function OneCSyncUpload({ onSyncComplete }: OneCSyncUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncResult, setSyncResult] = useState<OneCSyncResponse | null>(null);
  const [syncStatus, setSyncStatus] = useState<OneCSyncStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updateExisting, setUpdateExisting] = useState(true);
  const [deactivateMissing, setDeactivateMissing] = useState(false);
  const [syncMethod, setSyncMethod] = useState<'file' | 'yml' | 'xml'>('xml');
  const [syncStocks, setSyncStocks] = useState(false);
  const [syncStores, setSyncStores] = useState(true);
  const [testLimit, setTestLimit] = useState<number | null>(null); // Ограничение для тестовой загрузки
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null); // Выбранный раздел каталога
  const [catalogSections, setCatalogSections] = useState<Array<{
    id: string;
    external_id: string;
    external_code: string | null;
    name: string;
    parent_external_id: string | null;
    description: string | null;
    is_active: boolean;
    sync_status: string | null;
  }>>([]);
  
  // Настройки YML
  const [ymlUrl, setYmlUrl] = useState('https://glamejewelry.ru/tstore/yml/b743eb13397ad6a83d95caf72d40b7b2.yml');
  
  // Настройки XML
  const [xmlUrl, setXmlUrl] = useState('https://s22b2e4d6.fastvps-server.com/1c_exchange/uploaded/import.xml');
  
  // Прогресс синхронизации
  const [syncTaskId, setSyncTaskId] = useState<string | null>(null);
  const [syncProgress, setSyncProgress] = useState<{
    status: string;
    progress: number;
    current: number;
    total: number;
    stage: string;
    stage_description: string;
    error?: string;
    result?: any;
  } | null>(null);
  const progressPollingRef = useRef<NodeJS.Timeout | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSyncStatus = useCallback(async () => {
    try {
      const status = await api.getSyncStatus();
      setSyncStatus(status);
    } catch (err: any) {
      console.error('Error loading sync status:', err);
    }
  }, []);

  // Загружаем статус при монтировании
  useEffect(() => {
    loadSyncStatus();
  }, [loadSyncStatus]);

  // Загружаем разделы каталога при монтировании
  useEffect(() => {
    const loadCatalogSections = async () => {
      try {
        const sections = await api.getCatalogSections();
        setCatalogSections(sections);
      } catch (err: any) {
        console.error('Error loading catalog sections:', err);
      }
    };
    loadCatalogSections();
  }, []);

  // Очистка polling при размонтировании
  useEffect(() => {
    return () => {
      if (progressPollingRef.current) {
        clearInterval(progressPollingRef.current);
        progressPollingRef.current = null;
      }
    };
  }, []);

  // Polling статуса синхронизации
  useEffect(() => {
    if (syncTaskId && !progressPollingRef.current) {
      const poll = async () => {
        try {
          const status = await api.getSyncProgress(syncTaskId);
          setSyncProgress(status);
          
          // Если синхронизация завершена, останавливаем polling
          if (status.status === 'completed' || status.status === 'failed' || status.status === 'cancelled') {
            if (progressPollingRef.current) {
              clearInterval(progressPollingRef.current);
              progressPollingRef.current = null;
            }
            
            // Если успешно завершена, обновляем результат
            if (status.status === 'completed' && status.result) {
              const products = status.result.products || {};
              const stocks = status.result.stocks || {};
              const stores = status.result.stores || {};
              
              const totalCreated = (products.created || 0) + (stocks.created || 0) + (stores.created || 0);
              const totalUpdated = (products.updated || 0) + (stocks.updated || 0) + (stores.updated || 0);
              const totalSkipped = (products.skipped || 0) + (stocks.skipped || 0) + (stores.skipped || 0);
              const totalErrors = (products.error_count || 0) + (stocks.error_count || 0) + (stores.error_count || 0);
              const totalDeactivated = (products.deactivated || 0) + (stores.deactivated || 0);
              
              setSyncResult({
                success: true,
                message: 'Синхронизация завершена',
                stats: {
                  created: totalCreated,
                  updated: totalUpdated,
                  skipped: totalSkipped,
                  errors: totalErrors,
                  deactivated: totalDeactivated,
                },
                details: {
                  products,
                  stocks: syncStocks ? stocks : null,
                  stores: syncStores ? stores : null,
                },
              });
              
              await loadSyncStatus();
              if (onSyncComplete) {
                onSyncComplete();
              }
            } else if (status.status === 'failed') {
              setError(status.error || 'Ошибка синхронизации');
            }
            
            setSyncTaskId(null);
            setLoading(false);
          }
        } catch (err: any) {
          // Если задача не найдена (404), возможно сервер был перезапущен
          if (err.response?.status === 404) {
            console.warn('Задача синхронизации не найдена. Возможно, сервер был перезапущен.');
            // Останавливаем polling и сбрасываем состояние
            if (progressPollingRef.current) {
              clearInterval(progressPollingRef.current);
              progressPollingRef.current = null;
            }
            setSyncTaskId(null);
            setLoading(false);
            setError('Задача синхронизации не найдена. Возможно, сервер был перезапущен. Запустите синхронизацию заново.');
            return;
          }
          console.error('Error polling sync status:', err);
        }
      };
      
      // Первый опрос сразу
      poll();
      
      // Затем каждые 2 секунды
      const interval = setInterval(poll, 2000);
      progressPollingRef.current = interval;
    }
  }, [syncTaskId, syncStocks, syncStores, onSyncComplete]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      const isJson = selectedFile.type === 'application/json' || selectedFile.name.endsWith('.json');
      const isXml = selectedFile.type === 'application/xml' || 
                    selectedFile.type === 'text/xml' || 
                    selectedFile.name.endsWith('.xml');
      
      if (isJson || isXml) {
        setFile(selectedFile);
        setError(null);
        setSyncResult(null);
      } else {
        setError('Пожалуйста, выберите JSON или XML файл (CommerceML)');
        setFile(null);
      }
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      const isJson = droppedFile.name.endsWith('.json');
      const isXml = droppedFile.name.endsWith('.xml');
      
      if (isJson || isXml) {
        setFile(droppedFile);
        setError(null);
        setSyncResult(null);
      } else {
        setError('Пожалуйста, перетащите JSON или XML файл (CommerceML)');
      }
    }
  };

  const handleUpload = async () => {
    if (syncMethod === 'file') {
      if (!file) {
        setError('Пожалуйста, выберите файл для синхронизации');
        return;
      }

      setLoading(true);
      setError(null);
      setSyncResult(null);

      try {
        const result = await api.syncFromFile(file, updateExisting, deactivateMissing);
        setSyncResult(result);
        await loadSyncStatus();
        if (onSyncComplete) {
          onSyncComplete();
        }
        setFile(null);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      } catch (err: any) {
        // Обрабатываем разные форматы ошибок
        let errorMessage = 'Ошибка при синхронизации';
        
        if (err?.response?.data?.detail) {
          const detail = err.response.data.detail;
          if (Array.isArray(detail)) {
            errorMessage = detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ');
          } else if (typeof detail === 'object' && detail.msg) {
            errorMessage = detail.msg;
          } else if (typeof detail === 'string') {
            errorMessage = detail;
          } else {
            errorMessage = JSON.stringify(detail);
          }
        } else if (err?.message) {
          errorMessage = err.message;
        }
        
        setError(errorMessage);
        console.error('Sync error:', err);
      } finally {
        setLoading(false);
      }
    } else if (syncMethod === 'yml') {
      if (!ymlUrl) {
        setError('Пожалуйста, укажите URL YML файла');
        return;
      }

      setLoading(true);
      setError(null);
      setSyncResult(null);

      try {
        const result = await api.syncFromYml(
          ymlUrl,
          updateExisting,
          deactivateMissing
        );
        setSyncResult(result);
        await loadSyncStatus();
        if (onSyncComplete) {
          onSyncComplete();
        }
      } catch (err: any) {
        // Обрабатываем разные форматы ошибок
        let errorMessage = 'Ошибка при синхронизации с YML';
        
        if (err?.response?.data?.detail) {
          const detail = err.response.data.detail;
          if (Array.isArray(detail)) {
            errorMessage = detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ');
          } else if (typeof detail === 'object' && detail.msg) {
            errorMessage = detail.msg;
          } else if (typeof detail === 'string') {
            errorMessage = detail;
          } else {
            errorMessage = JSON.stringify(detail);
          }
        } else if (err?.message) {
          errorMessage = err.message;
        }
        
        setError(errorMessage);
        console.error('YML sync error:', err);
      } finally {
        setLoading(false);
      }
    } else if (syncMethod === 'xml') {
      if (!xmlUrl) {
        setError('Пожалуйста, укажите URL XML файла');
        return;
      }

      setLoading(true);
      setError(null);
      setSyncResult(null);

      try {
        const result = await api.syncProductsFromXML(xmlUrl, {
          updateExisting: updateExisting,
          asyncMode: true,
        });
        
        // Если синхронизация запущена в фоне
        if (result.status === 'started' && result.task_id) {
          setSyncTaskId(result.task_id);
          setSyncProgress({
            status: 'running',
            progress: 0,
            current: 0,
            total: 0,
            stage: 'initializing',
            stage_description: 'Инициализация...',
          });
          // Polling будет запущен в useEffect
        } else {
          // Синхронный режим
          const products = result.products || {};
          
          setSyncResult({
            success: true,
            message: result.message || 'Синхронизация из XML завершена',
            stats: {
              created: products.created || 0,
              updated: products.updated || 0,
              skipped: products.skipped || 0,
              errors: products.error_count || 0,
              deactivated: 0,
            },
            details: {
              products,
              stocks: null,
              stores: null,
            },
          });
          await loadSyncStatus();
          if (onSyncComplete) {
            onSyncComplete();
          }
          setLoading(false);
        }
      } catch (err: any) {
        // Обрабатываем разные форматы ошибок
        let errorMessage = 'Ошибка при синхронизации из XML';
        
        if (err?.response?.data?.detail) {
          const detail = err.response.data.detail;
          if (Array.isArray(detail)) {
            errorMessage = detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ');
          } else if (typeof detail === 'object' && detail.msg) {
            errorMessage = detail.msg;
          } else if (typeof detail === 'string') {
            errorMessage = detail;
          } else {
            errorMessage = JSON.stringify(detail);
          }
        } else if (err?.message) {
          errorMessage = err.message;
        }
        
        setError(errorMessage);
        console.error('XML sync error:', err);
      } finally {
        setLoading(false);
      }
    }
  };

  // УДАЛЕНО: handleSyncLoaded - использовал OData API
  // Теперь работаем только с XML (CommerceML)

  const handleReset = () => {
    setFile(null);
    setError(null);
    setSyncResult(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-gray-900 mb-2">Синхронизация с 1С</h2>
        <p className="text-sm text-gray-600">
          Синхронизация каталога товаров из 1С через XML (CommerceML). Также доступна загрузка через файл или YML.
        </p>
      </div>

      {/* Выбор способа синхронизации */}
      <div className="mb-4 flex gap-4 border-b border-gray-200">
        <button
          onClick={() => setSyncMethod('xml')}
          className={`px-4 py-2 font-medium text-sm transition-colors ${
            syncMethod === 'xml'
              ? 'border-b-2 border-gold-600 text-gold-600'
              : 'text-gray-600 hover:text-gray-900'
          }`}
        >
          XML (CommerceML) — основной
        </button>
        <button
          onClick={() => setSyncMethod('file')}
          className={`px-4 py-2 font-medium text-sm transition-colors ${
            syncMethod === 'file'
              ? 'border-b-2 border-gold-600 text-gold-600'
              : 'text-gray-600 hover:text-gray-900'
          }`}
        >
          Загрузка файла
        </button>
        <button
          onClick={() => setSyncMethod('yml')}
          className={`px-4 py-2 font-medium text-sm transition-colors ${
            syncMethod === 'yml'
              ? 'border-b-2 border-gold-600 text-gold-600'
              : 'text-gray-600 hover:text-gray-900'
          }`}
        >
          YML (Yandex Market)
        </button>
      </div>

      {/* Статус синхронизации */}
      {syncStatus && (
        <div className="mb-4 p-4 bg-gray-50 rounded-lg">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <div className="text-gray-500">Всего товаров</div>
              <div className="text-lg font-semibold text-gray-900">{syncStatus.total_products}</div>
            </div>
            <div>
              <div className="text-gray-500">Активных</div>
              <div className="text-lg font-semibold text-green-600">{syncStatus.active_products}</div>
            </div>
            <div>
              <div className="text-gray-500">Синхронизировано</div>
              <div className="text-lg font-semibold text-blue-600">{syncStatus.synced_products}</div>
            </div>
            <div>
              <div className="text-gray-500">Покрытие</div>
              <div className="text-lg font-semibold text-purple-600">{syncStatus.sync_coverage}%</div>
            </div>
          </div>
          {syncStatus.last_sync && (
            <div className="mt-2 text-xs text-gray-600">
              Последняя синхронизация: {new Date(syncStatus.last_sync).toLocaleString('ru-RU')}
            </div>
          )}
        </div>
      )}


      {/* Форма синхронизации через YML */}
      {syncMethod === 'yml' && (
        <div className="mb-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              URL YML файла
            </label>
            <input
              type="text"
              value={ymlUrl}
              onChange={(e) => setYmlUrl(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-gold-500 focus:border-gold-500 text-gray-900 bg-white"
              placeholder="https://glamejewelry.ru/tstore/yml/b743eb13397ad6a83d95caf72d40b7b2.yml"
            />
            <p className="mt-1 text-xs text-gray-600">
              YML (Yandex Market Language) - формат экспорта товаров для Яндекс.Маркет и других маркетплейсов.
              <br />
              Укажите полный URL к YML XML файлу.
            </p>
          </div>
        </div>
      )}

      {/* Форма синхронизации через XML (CommerceML) */}
      {syncMethod === 'xml' && (
        <div className="mb-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              URL файла import.xml (CommerceML)
            </label>
            <input
              type="text"
              value={xmlUrl}
              onChange={(e) => setXmlUrl(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-gold-500 focus:border-gold-500 text-gray-900 bg-white"
              placeholder="https://s22b2e4d6.fastvps-server.com/1c_exchange/uploaded/import.xml"
            />
            <p className="mt-1 text-xs text-gray-600">
              <strong>Важно:</strong> Укажите URL к файлу <code className="bg-gray-100 px-1 rounded">import.xml</code> - это основной файл с каталогом товаров.
              <br />
              Файл <code className="bg-gray-100 px-1 rounded">offers.xml</code> (цены и остатки) будет загружен автоматически из той же папки, если доступен.
              <br />
              CommerceML - стандартный формат обмена данными между 1С и интернет-магазинами.
            </p>
          </div>
        </div>
      )}

      {/* Область загрузки файла */}
      {syncMethod === 'file' && (
      <div
        className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
          file
            ? 'border-green-300 bg-green-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,.xml,application/json,application/xml,text/xml"
          onChange={handleFileChange}
          className="hidden"
        />
        
        {file ? (
          <div>
            <div className="text-green-600 mb-2">
              <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-sm font-medium text-gray-900">{file.name}</p>
            <p className="text-xs text-gray-500 mt-1">
              {(file.size / 1024).toFixed(2)} KB
            </p>
            <button
              onClick={handleReset}
              className="mt-2 text-sm text-gray-500 hover:text-gray-700"
            >
              Выбрать другой файл
            </button>
          </div>
        ) : (
          <div>
            <div className="text-gray-400 mb-2">
              <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <p className="text-sm text-gray-600 mb-2">
              Перетащите файл сюда или{' '}
              <button
                onClick={() => fileInputRef.current?.click()}
                className="text-gold-600 hover:text-gold-700 font-medium"
              >
                выберите файл
              </button>
            </p>
            <p className="text-xs text-gray-600">
              Поддерживаются форматы: JSON, CommerceML XML
            </p>
          </div>
        )}
      </div>
      )}

      {/* Настройки синхронизации через API */}
      {syncMethod === 'api' && (
        <div className="mb-4 space-y-2">
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={updateExisting}
              onChange={(e) => setUpdateExisting(e.target.checked)}
              disabled={loading}
              className="rounded border-gray-300 text-gold-600 focus:ring-gold-500"
            />
            <span className="ml-2 text-sm text-gray-700">Обновлять существующие товары</span>
          </label>
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={syncStores}
              onChange={(e) => setSyncStores(e.target.checked)}
              disabled={loading}
              className="rounded border-gray-300 text-gold-600 focus:ring-gold-500"
            />
            <span className="ml-2 text-sm text-gray-700">
              Синхронизировать склады (магазины) из Catalog_Склады
            </span>
          </label>
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={syncStocks}
              onChange={(e) => setSyncStocks(e.target.checked)}
              disabled={loading}
              className="rounded border-gray-300 text-gold-600 focus:ring-gold-500"
            />
            <span className="ml-2 text-sm text-gray-700">
              Синхронизировать остатки по складам
            </span>
          </label>
          <div className="mt-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Раздел каталога (опционально)
            </label>
            <select
              value={selectedSectionId || ''}
              onChange={(e) => setSelectedSectionId(e.target.value || null)}
              disabled={loading}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-gold-500 focus:border-gold-500 text-sm"
            >
              <option value="">Все разделы</option>
              {catalogSections.map((section) => (
                <option key={section.id} value={section.external_id}>
                  {section.name}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-500">
              Выберите раздел для синхронизации только товаров из этого раздела
            </p>
          </div>
          <div className="pt-2 border-t border-gray-200">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Тестовая загрузка (ограничение количества товаров)
            </label>
            <input
              type="number"
              min="1"
              max="1000"
              value={testLimit || ''}
              onChange={(e) => setTestLimit(e.target.value ? parseInt(e.target.value) : null)}
              disabled={loading}
              placeholder="Оставьте пустым для загрузки всех товаров"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-gold-500 focus:border-gold-500 text-gray-900 bg-white"
            />
            <p className="mt-1 text-xs text-gray-600">
              Укажите количество товаров для тестовой загрузки (например, 10). Оставьте пустым для загрузки всех товаров.
            </p>
          </div>
        </div>
      )}

      {/* Настройки синхронизации через файл/YML */}
      {(syncMethod === 'file' || syncMethod === 'yml') && (
        <div className="mt-4 space-y-2">
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={updateExisting}
              onChange={(e) => setUpdateExisting(e.target.checked)}
              className="rounded border-gray-300 text-gold-600 focus:ring-gold-500"
            />
            <span className="ml-2 text-sm text-gray-700">Обновлять существующие товары</span>
          </label>
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={deactivateMissing}
              onChange={(e) => setDeactivateMissing(e.target.checked)}
              className="rounded border-gray-300 text-gold-600 focus:ring-gold-500"
            />
            <span className="ml-2 text-sm text-gray-700">
              Деактивировать товары, отсутствующие в файле
            </span>
          </label>
        </div>
      )}

      {/* Прогресс-бар синхронизации */}
      {syncProgress && syncMethod === 'xml' && (
        <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-blue-900">
                  {syncProgress.stage_description}
                </span>
                <span className="text-sm text-blue-700">
                  {syncProgress.current > 0 && syncProgress.total > 0
                    ? `${syncProgress.current} / ${syncProgress.total}`
                    : ''}
                </span>
              </div>
              <div className="w-full bg-blue-200 rounded-full h-2.5">
                <div
                  className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
                  style={{ width: `${syncProgress.progress}%` }}
                ></div>
              </div>
              <div className="mt-1 text-xs text-blue-600">
                {syncProgress.progress.toFixed(1)}% завершено
              </div>
            </div>
          </div>
          {syncProgress.status === 'failed' && syncProgress.error && (
            <div className="mt-2 text-sm text-red-600">
              Ошибка: {syncProgress.error}
            </div>
          )}
        </div>
      )}

      {/* Кнопка удаления всех товаров */}
      <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-red-900 mb-1">Опасная зона</h3>
            <p className="text-xs text-red-700">
              Удалить все товары из базы данных. Используйте для полной перезагрузки каталога.
            </p>
          </div>
          <button
            onClick={async () => {
              if (confirm('Вы уверены, что хотите удалить ВСЕ товары? Это действие нельзя отменить.')) {
                try {
                  setLoading(true);
                  setError(null);
                  const result = await api.deleteAllProducts(true);
                  alert(result.message || `Удалено ${result.deleted_count || 0} товаров`);
                  await loadSyncStatus();
                  if (onSyncComplete) {
                    onSyncComplete();
                  }
                } catch (err: any) {
                  // Обрабатываем разные форматы ошибок
                  let errorMessage = 'Ошибка при удалении товаров';
                  
                  if (err?.response?.data?.detail) {
                    const detail = err.response.data.detail;
                    // Если detail - это массив ошибок валидации Pydantic
                    if (Array.isArray(detail)) {
                      errorMessage = detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ');
                    }
                    // Если detail - это объект ошибки валидации
                    else if (typeof detail === 'object' && detail.msg) {
                      errorMessage = detail.msg;
                    }
                    // Если detail - это строка
                    else if (typeof detail === 'string') {
                      errorMessage = detail;
                    }
                    // Иначе преобразуем в строку
                    else {
                      errorMessage = JSON.stringify(detail);
                    }
                  } else if (err?.message) {
                    errorMessage = err.message;
                  }
                  
                  setError(errorMessage);
                } finally {
                  setLoading(false);
                }
              }
            }}
            disabled={loading}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm"
          >
            Удалить все товары
          </button>
        </div>
      </div>

      {/* Кнопка загрузки */}
      <div className="mt-4 flex gap-2">
        <button
          onClick={handleUpload}
          disabled={
            (syncMethod === 'file' && !file) ||
            (syncMethod === 'yml' && !ymlUrl) ||
            (syncMethod === 'xml' && !xmlUrl) ||
            loading ||
            (syncProgress && syncProgress.status === 'running')
          }
          className={`flex-1 px-4 py-2 rounded-lg font-medium transition-colors ${
            ((syncMethod === 'file' && !file) ||
             (syncMethod === 'yml' && !ymlUrl) ||
             (syncMethod === 'xml' && !xmlUrl) ||
             loading ||
             (syncProgress && syncProgress.status === 'running'))
              ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
              : 'bg-gold-600 text-white hover:bg-gold-700'
          }`}
        >
          {(loading || (syncProgress && syncProgress.status === 'running')) ? (
            <span className="flex items-center justify-center">
              <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Синхронизация...
            </span>
          ) : (
            syncMethod === 'yml' ? 'Синхронизировать с YML' :
            syncMethod === 'xml' ? 'Синхронизировать из XML' : 
            'Загрузить и синхронизировать'
          )}
        </button>
        {/* УДАЛЕНО: Кнопка "Синхронизировать загруженные" - была для OData API */}
        <button
          onClick={loadSyncStatus}
          className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
        >
          Обновить статус
        </button>
      </div>

      {/* Результаты синхронизации */}
      {syncResult && (
        <div className={`mt-4 p-4 rounded-lg ${
          syncResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
        }`}>
          <div className="flex items-start">
            <div className={`flex-shrink-0 ${syncResult.success ? 'text-green-600' : 'text-red-600'}`}>
              {syncResult.success ? (
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
              ) : (
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              )}
            </div>
            <div className="ml-3 flex-1">
              <p className={`text-sm font-medium ${
                syncResult.success ? 'text-green-800' : 'text-red-800'
              }`}>
                {syncResult.message}
              </p>
              {syncResult.stats && (
                <div className="mt-2 grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
                  <div>
                    <span className="text-gray-600">Создано:</span>
                    <span className="ml-1 font-semibold text-green-600">{syncResult.stats.created || 0}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Обновлено:</span>
                    <span className="ml-1 font-semibold text-blue-600">{syncResult.stats.updated || 0}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Пропущено:</span>
                    <span className="ml-1 font-semibold text-gray-600">{syncResult.stats.skipped || 0}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Ошибок:</span>
                    <span className="ml-1 font-semibold text-red-600">{syncResult.stats.errors || 0}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Деактивировано:</span>
                    <span className="ml-1 font-semibold text-orange-600">{syncResult.stats.deactivated || 0}</span>
                  </div>
                </div>
              )}
              {syncResult.details && (
                <div className="mt-3 pt-3 border-t border-gray-200 text-xs text-gray-600">
                  {syncResult.details.products && (
                    <div className="mb-1">
                      Товары: создано {syncResult.details.products.created || 0}, обновлено {syncResult.details.products.updated || 0}, ошибок {syncResult.details.products.error_count || 0}
                    </div>
                  )}
                  {syncResult.details.stocks && (
                    <div className="mb-1">
                      Остатки: создано {syncResult.details.stocks.created || 0}, обновлено {syncResult.details.stocks.updated || 0}, пропущено {syncResult.details.stocks.skipped || 0}
                    </div>
                  )}
                  {syncResult.details.stores && (
                    <div>
                      Склады: создано {syncResult.details.stores.created || 0}, обновлено {syncResult.details.stores.updated || 0}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Ошибка */}
      {error && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-start">
            <div className="flex-shrink-0 text-red-600">
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm font-medium text-red-800">Ошибка</p>
              <p className="text-sm text-red-700 mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
