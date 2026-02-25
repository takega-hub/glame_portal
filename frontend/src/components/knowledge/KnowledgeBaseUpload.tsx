'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  api,
  KnowledgeUploadResponse,
  KnowledgeStats,
  KnowledgeSearchResult,
  KnowledgeDocument,
  SyncProductsToKnowledgeResponse,
  KnowledgeBatchUploadResponse,
} from '@/lib/api';

export default function KnowledgeBaseUpload() {
  const collections = [
    { value: 'brand_philosophy', label: 'Философия бренда' },
    { value: 'product_knowledge', label: 'Описания продуктов' },
    { value: 'collections_info', label: 'Информация о коллекциях' },
    { value: 'buyer_psychology', label: 'Психология покупателей' },
    { value: 'sales_playbook', label: 'Продажные скрипты' },
    { value: 'looks_descriptions', label: 'Описания образов' },
    { value: 'content_pieces', label: 'Готовые контент-блоки' },
    { value: 'persona_knowledge', label: 'Знания о персонах' },
  ];

  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<KnowledgeUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResult | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [replacingId, setReplacingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [selectedCollection, setSelectedCollection] = useState<string>('brand_philosophy');
  const [historyCollectionFilter, setHistoryCollectionFilter] = useState<string>('all');
  const [syncProductsLoading, setSyncProductsLoading] = useState(false);
  const [syncProductsResult, setSyncProductsResult] = useState<SyncProductsToKnowledgeResponse | null>(null);
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchResult, setBatchResult] = useState<KnowledgeBatchUploadResponse | null>(null);
  const [changingCollectionId, setChangingCollectionId] = useState<string | null>(null);
  const [duplicateFilenames, setDuplicateFilenames] = useState<string[] | null>(null);
  const [pendingUpload, setPendingUpload] = useState<
    { type: 'single'; file: File } | { type: 'batch'; files: File[] } | null
  >(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const multiFileInputRef = useRef<HTMLInputElement>(null);
  const replaceFileInputRefs = useRef<{ [key: string]: HTMLInputElement | null }>({});

  const loadStats = useCallback(async () => {
    try {
      const statsData = await api.getKnowledgeStats(selectedCollection);
      setStats(statsData);
    } catch (err: any) {
      console.error('Error loading stats:', err);
    }
  }, [selectedCollection]);

  const loadDocuments = useCallback(async () => {
    setDocumentsLoading(true);
    try {
      const collectionFilter = historyCollectionFilter === 'all' ? undefined : historyCollectionFilter;
      const docs = await api.getKnowledgeDocuments(0, 100, undefined, collectionFilter);
      setDocuments(docs);
    } catch (err: any) {
      console.error('Error loading documents:', err);
    } finally {
      setDocumentsLoading(false);
    }
  }, [historyCollectionFilter]);

  // Загрузка статистики и истории при монтировании компонента
  useEffect(() => {
    loadStats();
    loadDocuments();
  }, [loadStats, loadDocuments]);

  // При изменении фильтра истории — перезагружаем список
  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const ACCEPT_PDF_JSON = '.pdf,.json,application/pdf,application/json';

  const filterPdfJson = (fileList: FileList | null): File[] => {
    if (!fileList) return [];
    return Array.from(fileList).filter((f) => {
      const n = f.name.toLowerCase();
      return n.endsWith('.pdf') || n.endsWith('.json');
    });
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      const isJson = selectedFile.type === 'application/json' || selectedFile.name.endsWith('.json');
      const isPdf = selectedFile.type === 'application/pdf' || selectedFile.name.endsWith('.pdf');
      
      if (isJson || isPdf) {
        setFile(selectedFile);
        setError(null);
      } else {
        setError('Пожалуйста, выберите JSON или PDF файл');
        setFile(null);
      }
    }
  };

  const handleBatchFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const accepted = filterPdfJson(e.target.files);
    setBatchFiles(accepted);
    setFile(null);
    setBatchResult(null);
    setError(accepted.length === 0 && e.target.files?.length ? 'Выберите только PDF или JSON файлы' : null);
    if (folderInputRef.current) folderInputRef.current.value = '';
  };

  const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const accepted = filterPdfJson(e.target.files);
    setBatchFiles(accepted);
    setFile(null);
    setBatchResult(null);
    setError(accepted.length === 0 && e.target.files?.length ? 'В папке нет PDF или JSON файлов' : null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (multiFileInputRef.current) multiFileInputRef.current.value = '';
  };

  const handleBatchUpload = async () => {
    if (batchFiles.length === 0) {
      setError('Добавьте файлы: выберите папку или несколько файлов');
      return;
    }
    setError(null);
    setBatchResult(null);
    try {
      const filenames = batchFiles.map((f) => f.name);
      const { duplicates } = await api.checkKnowledgeDuplicates(selectedCollection, filenames);
      if (duplicates.length > 0) {
        setDuplicateFilenames(duplicates);
        setPendingUpload({ type: 'batch', files: batchFiles });
        return;
      }
      setBatchLoading(true);
      const result = await api.uploadKnowledgeBatch(batchFiles, selectedCollection, false);
      setBatchResult(result);
      await Promise.all([loadStats(), loadDocuments()]);
      setBatchFiles([]);
      if (folderInputRef.current) folderInputRef.current.value = '';
      if (multiFileInputRef.current) multiFileInputRef.current.value = '';
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Ошибка при пакетной загрузке';
      setError(msg);
      console.error('Batch upload error:', err);
    } finally {
      setBatchLoading(false);
    }
  };

  const performUpload = async (replaceDuplicates: boolean) => {
    if (!pendingUpload) return;
    setLoading(pendingUpload.type === 'single');
    setBatchLoading(pendingUpload.type === 'batch');
    setError(null);
    setUploadResult(null);
    setBatchResult(null);
    const col = selectedCollection;
    try {
      if (pendingUpload.type === 'single') {
        const result = await api.uploadKnowledgeFromFile(
          pendingUpload.file,
          col,
          replaceDuplicates
        );
        setUploadResult(result);
        setFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
      } else {
        const result = await api.uploadKnowledgeBatch(
          pendingUpload.files,
          col,
          replaceDuplicates
        );
        setBatchResult(result);
        setBatchFiles([]);
        if (folderInputRef.current) folderInputRef.current.value = '';
        if (multiFileInputRef.current) multiFileInputRef.current.value = '';
      }
      await Promise.all([loadStats(), loadDocuments()]);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Ошибка при загрузке';
      setError(msg);
      console.error('Upload error:', err);
    } finally {
      setLoading(false);
      setBatchLoading(false);
      setPendingUpload(null);
      setDuplicateFilenames(null);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError('Пожалуйста, выберите файл для загрузки');
      return;
    }
    setError(null);
    setUploadResult(null);
    try {
      const { duplicates } = await api.checkKnowledgeDuplicates(selectedCollection, [
        file.name,
      ]);
      if (duplicates.length > 0) {
        setDuplicateFilenames(duplicates);
        setPendingUpload({ type: 'single', file });
        return;
      }
      setLoading(true);
      const result = await api.uploadKnowledgeFromFile(file, selectedCollection, false);
      setUploadResult(result);
      await Promise.all([loadStats(), loadDocuments()]);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Произошла ошибка при загрузке файла';
      setError(errorMessage);
      console.error('Error uploading file:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setError('Введите запрос для поиска');
      return;
    }

    setSearchLoading(true);
    setError(null);

    try {
      const results = await api.searchKnowledge(searchQuery, 5, 0.5, selectedCollection);
      setSearchResults(results);
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Произошла ошибка при поиске';
      setError(errorMessage);
      console.error('Error searching:', err);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleDelete = async (documentId: string) => {
    if (!confirm('Вы уверены, что хотите удалить этот документ? Все связанные знания будут удалены из базы.')) {
      return;
    }

    setDeletingId(documentId);
    setError(null);

    try {
      await api.deleteKnowledgeDocument(documentId);
      await Promise.all([loadStats(), loadDocuments()]);
      alert('Документ успешно удален');
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Произошла ошибка при удалении документа';
      setError(errorMessage);
      console.error('Error deleting document:', err);
    } finally {
      setDeletingId(null);
    }
  };

  const handleClearCollection = async () => {
    if (!confirm(`Очистить всю коллекцию "${selectedCollection}"? Это удалит знания из Qdrant и историю загрузок по этой коллекции.`)) {
      return;
    }
    setError(null);
    try {
      await api.clearKnowledgeCollection(selectedCollection);
      await Promise.all([loadStats(), loadDocuments()]);
      alert('Коллекция очищена');
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Произошла ошибка при очистке коллекции';
      setError(errorMessage);
      console.error('Error clearing collection:', err);
    }
  };

  const handleSyncProducts = async () => {
    setSyncProductsLoading(true);
    setError(null);
    setSyncProductsResult(null);
    try {
      const res = await api.syncProductsToKnowledge({
        collection_name: 'product_knowledge',
        only_active: true,
        limit: 1000,
      });
      setSyncProductsResult(res);
      // обновим статистику по выбранной коллекции (если она совпадает)
      await Promise.all([loadStats(), loadDocuments()]);
    } catch (err: any) {
      const msg =
        err.response?.data?.detail ||
        err.message ||
        'Произошла ошибка при синхронизации товаров в базу знаний';
      setError(msg);
      console.error('Error syncing products to knowledge:', err);
    } finally {
      setSyncProductsLoading(false);
    }
  };

  const handleChangeCollection = async (documentId: string, newCollectionName: string) => {
    setChangingCollectionId(documentId);
    setError(null);
    try {
      await api.changeKnowledgeDocumentCollection(documentId, newCollectionName);
      await Promise.all([loadStats(), loadDocuments()]);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Ошибка при смене коллекции';
      setError(msg);
      console.error('Change collection error:', err);
    } finally {
      setChangingCollectionId(null);
    }
  };

  const handleReplace = async (documentId: string, file: File, docCollectionName?: string) => {
    setReplacingId(documentId);
    setError(null);
    setUploadResult(null);

    try {
      const result = await api.replaceKnowledgeDocument(documentId, file, docCollectionName || selectedCollection);
      setUploadResult(result);
      await Promise.all([loadStats(), loadDocuments()]);
      alert('Документ успешно заменен');
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Произошла ошибка при замене документа';
      setError(errorMessage);
      console.error('Error replacing document:', err);
    } finally {
      setReplacingId(null);
      // Очищаем input
      if (replaceFileInputRefs.current[documentId]) {
        replaceFileInputRefs.current[documentId]!.value = '';
      }
    }
  };

  const downloadExample = () => {
    const example = [
      {
        text: "GLAME — это бренд украшений премиум-класса, который создает уникальные изделия для современных женщин, ценящих элегантность и индивидуальность.",
        category: "brand_philosophy",
        source: "brand_guide"
      },
      {
        text: "Мы используем только качественные материалы: золото 585 пробы, серебро 925 пробы, натуральные камни и жемчуг.",
        category: "materials",
        source: "product_specs"
      }
    ];

    const blob = new Blob([JSON.stringify(example, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'brand_knowledge_example.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-800 mb-2">База знаний о бренде</h1>
      <p className="text-gray-600 mb-6">
        Загрузите базу знаний о бренде GLAME в формате PDF или JSON. Система автоматически извлечет знания из PDF с помощью AI и создаст векторные представления для семантического поиска.
      </p>

      {/* Статистика */}
      {stats && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <h2 className="text-lg font-semibold text-blue-900 mb-2">Статистика базы знаний</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-blue-700">Всего документов</p>
              <p className="text-2xl font-bold text-blue-900">{stats.total_documents}</p>
            </div>
            <div>
              <p className="text-sm text-blue-700">Размерность вектора</p>
              <p className="text-2xl font-bold text-blue-900">{stats.vector_size}</p>
            </div>
            <div>
              <p className="text-sm text-blue-700">Метрика</p>
              <p className="text-lg font-semibold text-blue-900">{stats.distance}</p>
            </div>
            <div>
              <p className="text-sm text-blue-700">Коллекция</p>
              <p className="text-sm font-semibold text-blue-900">{stats.collection_name}</p>
            </div>
          </div>
          <div className="mt-4">
            <div className="flex flex-wrap gap-3">
              <button
                onClick={handleClearCollection}
                className="px-4 py-2 text-sm bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition"
              >
                Очистить коллекцию
              </button>

              {selectedCollection === 'product_knowledge' && (
                <button
                  onClick={handleSyncProducts}
                  disabled={syncProductsLoading}
                  className="px-4 py-2 text-sm bg-emerald-100 text-emerald-800 rounded-lg hover:bg-emerald-200 transition disabled:opacity-50"
                >
                  {syncProductsLoading ? 'Синхронизация товаров…' : 'Синхронизировать товары из каталога'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {syncProductsResult && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 mb-6">
          <h2 className="text-lg font-semibold text-emerald-900 mb-2">Синхронизация товаров в Qdrant</h2>
          <p className="text-sm text-emerald-800">
            Коллекция: <span className="font-semibold">{syncProductsResult.collection_name}</span>
          </p>
          <p className="text-sm text-emerald-800">
            Всего: {syncProductsResult.total_products} • Успешно: {syncProductsResult.synced} • Ошибок:{' '}
            {syncProductsResult.failed}
          </p>
          {syncProductsResult.errors?.length > 0 && (
            <div className="mt-2">
              <p className="text-sm font-medium text-emerald-900 mb-1">Примеры ошибок</p>
              <ul className="text-xs text-emerald-900 list-disc pl-5">
                {syncProductsResult.errors.slice(0, 10).map((e, idx) => (
                  <li key={idx}>{e}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Загрузка файла */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Загрузка базы знаний</h2>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Раздел / коллекция
          </label>
          <select
            value={selectedCollection}
            onChange={(e) => setSelectedCollection(e.target.value)}
            className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
          >
            {collections.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
          <p className="mt-2 text-xs text-gray-500">
            Загрузка, поиск и история будут привязаны к выбранной коллекции.
          </p>
          <p className="mt-1 text-sm text-gray-700">
            Выбрано: <span className="font-semibold text-gold-600">
              {collections.find(c => c.value === selectedCollection)?.label || selectedCollection}
            </span>
          </p>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Один файл
          </label>
          <div className="flex items-center gap-4">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT_PDF_JSON}
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-gold-50 file:text-gold-700 hover:file:bg-gold-100"
            />
            {file && (
              <span className="text-sm text-gray-600">
                Выбран: {file.name} ({(file.size / 1024).toFixed(2)} KB)
                {file.name.endsWith('.pdf') && (
                  <span className="ml-2 px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded">
                    PDF - будет обработан AI
                  </span>
                )}
              </span>
            )}
          </div>
        </div>

        <div className="mb-4 p-4 bg-gray-50 border border-gray-200 rounded-lg">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Пакетная загрузка из папки или несколько файлов
          </label>
          <p className="text-xs text-gray-500 mb-3">
            Выберите папку на компьютере — в базу попадут все PDF и JSON из неё. Либо выберите несколько файлов сразу.
          </p>
          <div className="flex flex-wrap gap-3 mb-3">
            <input
              ref={folderInputRef}
              type="file"
              accept={ACCEPT_PDF_JSON}
              multiple
              // @ts-expect-error webkitdirectory is non-standard but supported in Chrome/Edge
              webkitdirectory=""
              directory=""
              className="hidden"
              onChange={handleFolderSelect}
            />
            <input
              ref={multiFileInputRef}
              type="file"
              accept={ACCEPT_PDF_JSON}
              multiple
              className="hidden"
              onChange={handleBatchFiles}
            />
            <button
              type="button"
              onClick={() => folderInputRef.current?.click()}
              className="px-4 py-2 text-sm bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 transition font-medium"
            >
              Выбрать папку
            </button>
            <button
              type="button"
              onClick={() => multiFileInputRef.current?.click()}
              className="px-4 py-2 text-sm bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 transition font-medium"
            >
              Выбрать файлы
            </button>
          </div>
          {batchFiles.length > 0 && (
            <>
              <p className="text-sm text-gray-700 mb-2">
                К загрузке: <strong>{batchFiles.length}</strong> файл(ов)
              </p>
              <ul className="text-xs text-gray-600 list-disc list-inside max-h-32 overflow-y-auto mb-3">
                {batchFiles.slice(0, 50).map((f, i) => (
                  <li key={i}>{f.name} ({(f.size / 1024).toFixed(1)} KB)</li>
                ))}
                {batchFiles.length > 50 && (
                  <li>… и ещё {batchFiles.length - 50} файлов</li>
                )}
              </ul>
              <button
                type="button"
                onClick={handleBatchUpload}
                disabled={batchLoading}
                className="px-4 py-2 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 transition font-semibold"
              >
                {batchLoading ? (
                  <span className="flex items-center gap-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                    Загрузка…
                  </span>
                ) : (
                  'Загрузить всё'
                )}
              </button>
            </>
          )}
          {batchResult && (
            <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg">
              <p className="text-green-800 font-medium">
                Готово: загружено {batchResult.succeeded} из {batchResult.total_files}, ошибок: {batchResult.failed}
              </p>
              {batchResult.results.some((r) => !r.success) && (
                <ul className="mt-2 text-sm text-red-700 list-disc list-inside">
                  {batchResult.results.filter((r) => !r.success).map((r, i) => (
                    <li key={i}>{r.filename}: {r.message}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <p className="mb-4 text-xs text-gray-500">
          Поддерживаются PDF (извлечение знаний через AI) и JSON (структурированные данные).
        </p>

        <div className="flex gap-4">
          <button
            onClick={handleUpload}
            disabled={loading || !file}
            className="px-6 py-3 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed transition font-semibold"
          >
            {loading ? (
              <span className="flex items-center">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
                Загрузка...
              </span>
            ) : (
              'Загрузить файл'
            )}
          </button>

          <button
            onClick={downloadExample}
            className="px-6 py-3 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition font-semibold"
          >
            Скачать пример
          </button>
        </div>

        {/* Результат загрузки */}
        {uploadResult && (
          <div className="mt-4 bg-green-50 border border-green-200 rounded-lg p-4">
            <p className="text-green-800 font-medium">✓ {uploadResult.message}</p>
            <p className="text-green-600 text-sm mt-1">
              Загружено документов: {uploadResult.uploaded_count}
            </p>
          </div>
        )}
      </div>

      {/* Поиск */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Поиск в базе знаний</h2>

        <div className="flex gap-4 mb-4">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Введите запрос для поиска..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gold-500"
          />
          <button
            onClick={handleSearch}
            disabled={searchLoading || !searchQuery.trim()}
            className="px-6 py-2 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed transition font-semibold"
          >
            {searchLoading ? (
              <span className="flex items-center">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Поиск...
              </span>
            ) : (
              'Найти'
            )}
          </button>
        </div>

        {/* Результаты поиска */}
        {searchResults && (
          <div className="mt-4">
            <p className="text-sm text-gray-600 mb-3">
              Найдено результатов: {searchResults.count}
            </p>
            <div className="space-y-3">
              {searchResults.results.map((result, idx) => (
                <div
                  key={result.id}
                  className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex gap-2">
                      {result.payload.category && (
                        <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded">
                          {result.payload.category}
                        </span>
                      )}
                      {result.payload.source && (
                        <span className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded">
                          {result.payload.source}
                        </span>
                      )}
                    </div>
                    <span className="text-sm text-gray-500">
                      Релевантность: {(result.score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <p className="text-gray-800">{result.payload.text}</p>
                </div>
              ))}
              {searchResults.results.length === 0 && (
                <p className="text-gray-500 text-center py-4">Результаты не найдены</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* История загрузок */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">История загрузок</h2>
          <button
            onClick={loadDocuments}
            disabled={documentsLoading}
            className="px-4 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition"
          >
            {documentsLoading ? 'Обновление...' : 'Обновить'}
          </button>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Фильтр истории по коллекции
          </label>
          <select
            value={historyCollectionFilter}
            onChange={(e) => setHistoryCollectionFilter(e.target.value)}
            className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
          >
            <option value="all">Все коллекции</option>
            {collections.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        {documentsLoading ? (
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gold-500 mx-auto"></div>
            <p className="text-gray-500 mt-2">Загрузка истории...</p>
          </div>
        ) : documents.length === 0 ? (
          <p className="text-gray-500 text-center py-8">История загрузок пуста</p>
        ) : (
          <div className="space-y-4">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition"
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="font-semibold text-gray-800">{doc.filename}</h3>
                      <span className={`px-2 py-1 text-xs rounded ${
                        doc.status === 'completed' ? 'bg-green-100 text-green-700' :
                        doc.status === 'processing' ? 'bg-yellow-100 text-yellow-700' :
                        'bg-red-100 text-red-700'
                      }`}>
                        {doc.status === 'completed' ? 'Загружено' :
                         doc.status === 'processing' ? 'Обработка' :
                         'Ошибка'}
                      </span>
                      <span className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded">
                        {doc.file_type.toUpperCase()}
                      </span>
                    </div>
                    <div className="text-sm text-gray-600 space-y-1">
                      <p className="flex items-center gap-2 flex-wrap">
                        <strong>Коллекция:</strong>
                        <select
                          value={doc.collection_name}
                          onChange={(e) => {
                            const next = e.target.value;
                            if (next !== doc.collection_name) handleChangeCollection(doc.id, next);
                          }}
                          disabled={changingCollectionId === doc.id}
                          className="rounded border border-gray-300 bg-white px-2 py-1 text-gray-900 text-sm focus:outline-none focus:ring-1 focus:ring-gold-500 disabled:opacity-50"
                        >
                          {collections.map((c) => (
                            <option key={c.value} value={c.value}>
                              {c.label}
                            </option>
                          ))}
                        </select>
                        {changingCollectionId === doc.id && (
                          <span className="text-xs text-gray-500">перенос…</span>
                        )}
                      </p>
                      <p>
                        <strong>Загружено:</strong> {doc.uploaded_items} из {doc.total_items} элементов
                        {doc.failed_items > 0 && (
                          <span className="text-red-600 ml-2">({doc.failed_items} ошибок)</span>
                        )}
                      </p>
                      {doc.file_size && (
                        <p><strong>Размер:</strong> {(doc.file_size / 1024).toFixed(2)} KB</p>
                      )}
                      <p><strong>Дата:</strong> {new Date(doc.created_at).toLocaleString('ru-RU')}</p>
                      {doc.error_message && (
                        <p className="text-red-600"><strong>Ошибка:</strong> {doc.error_message}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2 ml-4">
                    <label className="cursor-pointer">
                      <input
                        ref={(el) => replaceFileInputRefs.current[doc.id] = el}
                        type="file"
                        accept=".pdf,.json,application/pdf,application/json"
                        className="hidden"
                        onChange={(e) => {
                          if (e.target.files && e.target.files[0]) {
                            handleReplace(doc.id, e.target.files[0], doc.collection_name);
                          }
                        }}
                      />
                      <button
                        onClick={() => replaceFileInputRefs.current[doc.id]?.click()}
                        disabled={replacingId === doc.id}
                        className="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 transition disabled:opacity-50"
                      >
                        {replacingId === doc.id ? 'Замена...' : 'Заменить'}
                      </button>
                    </label>
                    <button
                      onClick={() => handleDelete(doc.id)}
                      disabled={deletingId === doc.id}
                      className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition disabled:opacity-50"
                    >
                      {deletingId === doc.id ? 'Удаление...' : 'Удалить'}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Ошибка */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800 font-medium">Ошибка</p>
          <p className="text-red-600 text-sm mt-1">{error}</p>
        </div>
      )}

      {/* Диалог дубликатов: пропуск или замена */}
      {duplicateFilenames && duplicateFilenames.length > 0 && pendingUpload && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl shadow-lg max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2">
              Файлы уже есть в базе
            </h3>
            <p className="text-sm text-gray-600 mb-4">
              В выбранной коллекции уже загружены файлы с такими именами. Пропустить их или заменить старые версии новыми?
            </p>
            <ul className="text-sm text-gray-700 list-disc list-inside mb-6 max-h-40 overflow-y-auto">
              {duplicateFilenames.map((name, i) => (
                <li key={i}>{name}</li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => performUpload(false)}
                disabled={loading || batchLoading}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition font-medium disabled:opacity-50"
              >
                Пропустить дубликаты
              </button>
              <button
                type="button"
                onClick={() => performUpload(true)}
                disabled={loading || batchLoading}
                className="px-4 py-2 bg-gold-500 text-white rounded-lg hover:bg-gold-600 transition font-medium disabled:opacity-50"
              >
                Заменить
              </button>
              <button
                type="button"
                onClick={() => {
                  setDuplicateFilenames(null);
                  setPendingUpload(null);
                }}
                disabled={loading || batchLoading}
                className="px-4 py-2 text-gray-600 hover:text-gray-800 transition font-medium disabled:opacity-50"
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Информация о формате */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-3">Форматы файлов</h3>
        
        <div className="mb-4">
          <h4 className="text-sm font-semibold text-gray-800 mb-2">📄 PDF файлы</h4>
          <p className="text-sm text-gray-700 mb-2">
            Загрузите PDF документ с информацией о бренде (брендбук, руководство, документация и т.д.). 
            Система автоматически:
          </p>
          <ul className="text-sm text-gray-700 list-disc list-inside mb-2">
            <li>Извлечет текст из PDF</li>
            <li>Использует AI для структурирования знаний</li>
            <li>Автоматически определит категории знаний</li>
            <li>Создаст векторные представления для поиска</li>
          </ul>
        </div>

        <div className="mb-4">
          <h4 className="text-sm font-semibold text-gray-800 mb-2">📋 JSON файлы</h4>
          <p className="text-sm text-gray-700 mb-2">
            Файл должен содержать массив объектов или объект с полем <code className="bg-gray-200 px-1 rounded">items</code>.
          </p>
          <div className="bg-gray-800 text-gray-100 p-4 rounded-lg overflow-x-auto">
            <pre className="text-xs">
{`[
  {
    "text": "Текст знания о бренде",
    "category": "brand_philosophy",
    "source": "brand_guide",
    "metadata": {}
  }
]`}
            </pre>
          </div>
          <p className="text-xs text-gray-600 mt-2">
            <strong>Поля:</strong> text (обязательно), category (опционально), source (опционально), metadata (опционально)
          </p>
        </div>
      </div>
    </div>
  );
}
