'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient } from '@/lib/api';
import Link from 'next/link';

interface Segment {
  id: string;
  name: string;
  description: string | null;
  rules?: any;
  customer_count: number;
  color: string | null;
  is_auto_generated: boolean;
}

type FieldMeta = { name: string; type: 'string' | 'number' | 'date'; label: string };
type AvailableFields = { user: FieldMeta[]; purchase_history: FieldMeta[] };
type FilterRow = {
  connector?: 'AND' | 'OR';
  source: 'user' | 'purchase_history';
  field: string;
  type: 'string' | 'number' | 'date';
  operator: string;
  value: any;
};

export default function CustomerSegmentsPage() {
  const { loading } = useAuth();
  const router = useRouter();
  const [segments, setSegments] = useState<Segment[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newSegmentName, setNewSegmentName] = useState('');
  const [newSegmentDescription, setNewSegmentDescription] = useState('');
  const [creatingSegment, setCreatingSegment] = useState(false);
  const [availableFields, setAvailableFields] = useState<AvailableFields | null>(null);
  const [groupLogic, setGroupLogic] = useState<'AND' | 'OR'>('AND');
  const [filters, setFilters] = useState<FilterRow[]>([]);
  const [calcLoading, setCalcLoading] = useState(false);
  const [calcCount, setCalcCount] = useState<number | null>(null);
  const calcTimerRef = useRef<any>(null);
  const [editSegmentId, setEditSegmentId] = useState<string | null>(null);
  const [advancedRulesMode, setAdvancedRulesMode] = useState(false);
  const [advancedRulesJson, setAdvancedRulesJson] = useState('');
  const [advancedRulesError, setAdvancedRulesError] = useState<string | null>(null);
  const [stores, setStores] = useState<Array<{ id: string; name: string; city?: string | null; external_id?: string | null }>>([]);
  const [storesLoading, setStoresLoading] = useState(false);
  const [storesError, setStoresError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading) {
      loadSegments();
    }
  }, [loading, router]);

  useEffect(() => {
    const fetchFields = async () => {
      try {
        const res = await apiClient.get<AvailableFields>('/api/customer-segmentation/available-fields');
        setAvailableFields(res.data);
      } catch (e) {
        console.error('Error loading available fields:', e);
      }
    };
    fetchFields();
    
    // Загружаем список магазинов для выпадающего меню
    const fetchStores = async () => {
      setStoresLoading(true);
      setStoresError(null);
      try {
        const r = await apiClient.get('/api/stores', { params: { active: true } });
        const list = (Array.isArray(r.data) ? r.data : []).filter((store: any) => {
          const name = String(store?.name || '').trim().toLowerCase();
          return name === 'трк центрум' || name === 'ялта, набережная 18';
        });
        setStores(list);
        if (!list.length) {
          console.warn('[Segments] /api/stores вернул пустой список');
          setStoresError('Пустой список магазинов');
        }
      } catch (e: any) {
        const msg = e?.response?.data?.detail || e?.message || String(e);
        console.error('[Segments] Error loading stores list:', e);
        setStores([]);
        setStoresError(msg);
      } finally {
        setStoresLoading(false);
      }
    };
    fetchStores();
  }, []);

  const loadSegments = async () => {
    try {
      const response = await apiClient.get<Segment[]>('/api/admin/customers/segments/list');
      setSegments(response.data);
    } catch (error) {
      console.error('Error loading segments:', error);
    } finally {
      setLoadingData(false);
    }
  };

  const operatorsByType = useMemo(() => {
    return {
      string: [
        { value: 'equals', label: 'Равно' },
        { value: 'contains', label: 'Содержит' },
        { value: 'in', label: 'В списке' },
        { value: 'not_in', label: 'Не в списке' },
      ],
      number: [
        { value: 'equals', label: 'Равно' },
        { value: '>=', label: '≥' },
        { value: '<=', label: '≤' },
        { value: '>', label: '>' },
        { value: '<', label: '<' },
        { value: 'in', label: 'В списке' },
        { value: 'not_in', label: 'Не в списке' },
      ],
      date: [
        { value: '>=', label: 'После даты' },
        { value: '<=', label: 'До даты' },
        { value: 'within_last_days', label: 'За последние N дней' },
      ],
    } as Record<'string' | 'number' | 'date', { value: string; label: string }[]>;
  }, []);

  const operatorLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    Object.values(operatorsByType).flat().forEach((item) => {
      labels[item.value] = item.label;
    });
    return labels;
  }, [operatorsByType]);

  const fieldLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    ([...(availableFields?.user || []), ...(availableFields?.purchase_history || [])]).forEach((field) => {
      labels[field.name] = field.label;
    });
    return labels;
  }, [availableFields]);

  const segmentLabelById = useMemo(() => {
    const labels: Record<string, string> = {};
    segments.forEach((segment) => {
      labels[segment.id] = `${segment.name} (${segment.customer_count.toLocaleString()})`;
    });
    return labels;
  }, [segments]);

  const isStoreField = (field: string | null | undefined) => {
    if (!field) return false;
    const f = String(field).toLowerCase();
    return f.includes('store');
  };

  const isExcludeSegmentField = (field: string | null | undefined) => field === 'exclude_segment';

  const addFilter = (source: 'user' | 'purchase_history') => {
    const srcFields = availableFields?.[source] || [];
    const first = srcFields[0];
    if (!first) return;
    const op = operatorsByType[first.type][0]?.value || 'equals';
    setFilters((prev) => [
      ...prev,
      { connector: prev.length > 0 ? groupLogic : undefined, source, field: first.name, type: first.type, operator: op, value: '' },
    ]);
  };

  const removeFilter = (idx: number) => {
    setFilters((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      if (next.length > 0) next[0] = { ...next[0], connector: undefined };
      return next;
    });
  };

  const updateFilterSource = (idx: number, source: 'user' | 'purchase_history') => {
    const srcFields = availableFields?.[source] || [];
    const first = srcFields[0];
    if (!first) return;
    const op = operatorsByType[first.type][0]?.value || 'equals';
    setFilters((prev) => {
      const next = [...prev];
      next[idx] = { connector: next[idx]?.connector, source, field: first.name, type: first.type, operator: op, value: '' };
      return next;
    });
  };

  const updateFilterField = (idx: number, fieldName: string) => {
    setFilters((prev) => {
      const row = prev[idx];
      const srcFields = availableFields?.[row.source] || [];
      const meta = srcFields.find((f) => f.name === fieldName);
      if (!meta) return prev;
      const op = operatorsByType[meta.type][0]?.value || 'equals';
      const next = [...prev];
      next[idx] = { ...row, field: fieldName, type: meta.type, operator: op, value: '' };
      return next;
    });
  };

  const updateFilterConnector = (idx: number, connector: 'AND' | 'OR') => {
    setFilters((prev) => {
      const next = [...prev];
      if (idx > 0 && next[idx]) {
        next[idx] = { ...next[idx], connector };
      }
      return next;
    });
  };

  const updateFilterOperator = (idx: number, operator: string) => {
    setFilters((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], operator };
      return next;
    });
  };

  const updateFilterValue = (idx: number, value: any) => {
    setFilters((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], value };
      return next;
    });
  };

  const parsedRules = useMemo(() => {
    if (advancedRulesMode) {
      try {
        const parsed = JSON.parse(advancedRulesJson || '{"logic":"AND","filters":[]}');
        if (!parsed || typeof parsed !== 'object') {
          return { logic: 'AND', filters: [] };
        }
        return parsed;
      } catch (e: any) {
        return { logic: 'AND', filters: [] };
      }
    }
    const valid = filters
      .filter((f) => {
        if (!f.field || !f.operator) return false;
        if (f.value === '' || f.value === null || f.value === undefined) return false;
        if (f.operator === 'in' || f.operator === 'not_in') {
          return String(f.value)
            .split(',')
            .map((v) => v.trim())
            .filter(Boolean).length > 0;
        }
        if (f.type === 'number' || f.operator === 'within_last_days') {
          return Number.isFinite(Number(f.value));
        }
        return true;
      })
      .map((f, idx) => ({
        ...(idx > 0 ? { connector: f.connector || groupLogic } : {}),
        field: f.field,
        operator: f.operator,
        value:
          f.operator === 'in' || f.operator === 'not_in'
            ? String(f.value)
                .split(',')
                .map((v) => v.trim())
                .filter(Boolean)
            : f.type === 'number' || f.operator === 'within_last_days'
              ? Number(f.value)
              : f.value,
      }));
    return { logic: groupLogic, filters: valid };
  }, [filters, groupLogic, advancedRulesMode, advancedRulesJson]);

  useEffect(() => {
    if (!advancedRulesMode) {
      setAdvancedRulesError(null);
      return;
    }
    try {
      const parsed = JSON.parse(advancedRulesJson || '{"logic":"AND","filters":[]}');
      setAdvancedRulesError(parsed && typeof parsed === 'object' ? null : 'JSON должен быть объектом правил');
    } catch (e: any) {
      setAdvancedRulesError(e?.message || 'Некорректный JSON');
    }
  }, [advancedRulesMode, advancedRulesJson]);

  const hasNestedRules = (rules: any): boolean => {
    const filtersList = Array.isArray(rules?.filters) ? rules.filters : [];
    return filtersList.some((filter: any) => filter && typeof filter === 'object' && 'logic' in filter);
  };

  const collectLeafFilters = (rules: any): any[] => {
    const out: any[] = [];
    const walk = (node: any) => {
      const list = Array.isArray(node?.filters) ? node.filters : [];
      list.forEach((filter: any) => {
        if (!filter || typeof filter !== 'object') return;
        if ('logic' in filter) walk(filter);
        else out.push(filter);
      });
    };
    walk(rules);
    return out;
  };

  const formatRuleValue = (value: any, field?: string) => {
    const formatOne = (item: any) => {
      const key = String(item ?? '');
      if (field === 'exclude_segment') return segmentLabelById[key] || key;
      return key;
    };

    if (Array.isArray(value)) {
      const items = value.map(formatOne);
      if (items.length > 6) return `${items.slice(0, 6).join(', ')} +${items.length - 6}`;
      return items.join(', ');
    }
    if (value === true) return 'Да';
    if (value === false) return 'Нет';
    if (typeof value === 'string' && field === 'exclude_segment' && value.includes(',')) {
      const items = value.split(',').map((item) => formatOne(item.trim())).filter(Boolean);
      if (items.length > 6) return `${items.slice(0, 6).join(', ')} +${items.length - 6}`;
      return items.join(', ');
    }
    return formatOne(value) || '—';
  };

  const humanizeRules = (rules: any): string[] => {
    const lines: string[] = [];
    const walk = (node: any, level = 0) => {
      const logic = String(node?.logic || 'AND').toUpperCase();
      const filtersList = Array.isArray(node?.filters) ? node.filters : [];
      filtersList.forEach((filter: any) => {
        if (!filter || typeof filter !== 'object') return;
        if ('logic' in filter) {
          const connector = String(filter.connector || logic).toUpperCase() === 'OR' ? 'ИЛИ' : 'И';
          lines.push(`${'  '.repeat(level)}${connector} группа (${String(filter.logic || 'AND').toUpperCase()}):`);
          walk(filter, level + 1);
        } else {
          const field = fieldLabels[filter.field] || filter.field || 'Поле';
          const op = operatorLabels[filter.operator] || filter.operator || 'условие';
          const prefix = level > 0 || filter.connector
            ? `${String(filter.connector || logic).toUpperCase() === 'OR' ? 'ИЛИ' : 'И'} `
            : '';
          lines.push(`${'  '.repeat(level)}${prefix}${field} · ${op} · ${formatRuleValue(filter.value, filter.field)}`);
        }
      });
    };
    if (!rules || !Array.isArray(rules.filters) || !rules.filters.length) return ['Фильтры не заданы'];
    lines.push(`Логика верхнего уровня: ${String(rules.logic || 'AND').toUpperCase()}`);
    walk(rules);
    return lines.slice(0, 8);
  };

  const openCreateModal = () => {
    setNewSegmentName('');
    setNewSegmentDescription('');
    setCreatingSegment(false);
    setEditSegmentId(null);
    setGroupLogic('AND');
    setFilters([]);
    setAdvancedRulesMode(false);
    setAdvancedRulesJson('');
    setAdvancedRulesError(null);
    setCalcCount(null);
    setCalcLoading(false);
    setIsCreateModalOpen(true);
  };

  const openEditModal = async (segmentId: string) => {
    setCreatingSegment(false);
    setEditSegmentId(segmentId);
    setCalcCount(null);
    setCalcLoading(false);
    setIsCreateModalOpen(true);
    try {
      let fields = availableFields;
      if (!fields) {
        const fieldsRes = await apiClient.get<AvailableFields>('/api/customer-segmentation/available-fields');
        fields = fieldsRes.data;
        setAvailableFields(fields);
      }
      const res = await apiClient.get<any>(`/api/customer-segmentation/segments/${segmentId}`);
      const seg = res.data;
      setNewSegmentName(seg?.name ?? '');
      setNewSegmentDescription(seg?.description ?? '');
      const rules = seg?.rules;
      const logic = (rules?.logic || 'AND').toUpperCase() === 'OR' ? 'OR' : 'AND';
      setGroupLogic(logic);
      const nested = hasNestedRules(rules);
      setAdvancedRulesMode(nested);
      setAdvancedRulesJson(JSON.stringify(rules || { logic: 'AND', filters: [] }, null, 2));
      setAdvancedRulesError(null);
      const flat = nested ? collectLeafFilters(rules) : (Array.isArray(rules?.filters) ? rules.filters : []);
      const makeRow = (fieldName: string): FilterRow | null => {
        const inUser = fields?.user?.find((x) => x.name === fieldName);
        if (inUser) {
          return { source: 'user', field: inUser.name, type: inUser.type, operator: 'equals', value: '' };
        }
        const inPh = fields?.purchase_history?.find((x) => x.name === fieldName);
        if (inPh) {
          return { source: 'purchase_history', field: inPh.name, type: inPh.type, operator: 'equals', value: '' };
        }
        return null;
      };
      const rows: FilterRow[] = flat
        .map((f: any) => {
          const base = makeRow(String(f.field || ''));
          if (!base) return null;
          const op = String(f.operator || 'equals');
          const supported = operatorsByType[base.type].some((o) => o.value === op);
          const operator = supported ? op : operatorsByType[base.type][0]?.value || 'equals';
          const connector = String(f.connector || logic).toUpperCase() === 'OR' ? 'OR' : 'AND';
          let value: any = f.value;
          if (operator === 'in' || operator === 'not_in') {
            value = Array.isArray(value) ? value.join(', ') : String(value ?? '');
          } else if (base.type === 'number' || operator === 'within_last_days') {
            value = value ?? '';
          } else {
            value = value ?? '';
          }
          return { ...base, connector, operator, value };
        })
        .filter(Boolean) as FilterRow[];
      if (rows.length > 0) rows[0] = { ...rows[0], connector: undefined };
      setFilters(rows);
    } catch (e) {
      console.error('Error loading segment for edit:', e);
      alert('Не удалось загрузить сегмент для редактирования');
      setIsCreateModalOpen(false);
    }
  };

  useEffect(() => {
    if (!isCreateModalOpen) return;
    if (!availableFields) return;
    if (calcTimerRef.current) clearTimeout(calcTimerRef.current);
    setCalcLoading(true);
    const t = setTimeout(async () => {
      try {
        const res = await apiClient.post<{ count: number }>(
          '/api/customer-segmentation/segments/calculate-count',
          parsedRules
        );
        setCalcCount(res.data.count);
      } catch (e) {
        setCalcCount(null);
      } finally {
        setCalcLoading(false);
      }
    }, 350);
    calcTimerRef.current = t;
  }, [isCreateModalOpen, parsedRules, availableFields]);

  const handleCreateSegment = async () => {
    if (!newSegmentName.trim()) {
      alert('Введите название сегмента');
      return;
    }
    if (advancedRulesMode && advancedRulesError) {
      alert('Исправьте JSON правил сегмента');
      return;
    }

    setCreatingSegment(true);
    try {
      if (editSegmentId) {
        await apiClient.put(`/api/customer-segmentation/segments/${editSegmentId}`, {
          name: newSegmentName.trim(),
          description: newSegmentDescription.trim() || null,
          rules: parsedRules,
        });
      } else {
        await apiClient.post('/api/customer-segmentation/segments', {
          name: newSegmentName.trim(),
          description: newSegmentDescription.trim() || null,
          rules: parsedRules,
        });
      }
      setIsCreateModalOpen(false);
      await loadSegments();
    } catch (error: any) {
      console.error('Error creating segment:', error);
      const detail = error?.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : 'Ошибка при создании сегмента');
    } finally {
      setCreatingSegment(false);
    }
  };

  const exportSegment = async (segmentId: string, format: 'csv' | 'excel') => {
    try {
      const res = await apiClient.post(`/api/customer-segmentation/segments/${segmentId}/export`, null, {
        responseType: 'blob',
        params: { format },
      });
      const contentDisposition = (res.headers?.['content-disposition'] || res.headers?.['Content-Disposition']) as
        | string
        | undefined;
      let filename = format === 'csv' ? 'segment.csv' : 'segment.xlsx';
      if (contentDisposition) {
        const m = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i) || contentDisposition.match(/filename="?([^"]+)"?/i);
        if (m?.[1]) filename = decodeURIComponent(m[1]);
      }
      const blob = new Blob([res.data], {
        type: format === 'csv' ? 'text/csv' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      alert('Не удалось экспортировать сегмент');
    }
  };

  const handleAutoGenerate = async () => {
    if (!confirm('Запустить автоматическую сегментацию? Это может занять некоторое время.')) {
      return;
    }

    setGenerating(true);
    try {
      await apiClient.post('/api/ai-marketer/segments/auto-generate');
      alert('Сегментация запущена. Обновите страницу через несколько секунд.');
      setTimeout(() => loadSegments(), 3000);
    } catch (error) {
      console.error('Error generating segments:', error);
      alert('Ошибка при запуске сегментации');
    } finally {
      setGenerating(false);
    }
  };

  const handleDeleteSegment = async (id: string, name: string) => {
    if (!confirm(`Вы уверены, что хотите удалить сегмент "${name}"? Это действие нельзя отменить.`)) {
      return;
    }

    try {
      await apiClient.delete(`/api/customer-segmentation/segments/${id}`);
      await loadSegments();
    } catch (error) {
      console.error('Error deleting segment:', error);
      alert('Не удалось удалить сегмент. Возможно, он используется в активных кампаниях.');
    }
  };

  if (loading || loadingData) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Загрузка...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <Link href="/admin/customers" className="text-pink-600 hover:text-pink-700 mb-4 inline-block">
              ← Назад к покупателям
            </Link>
            <h1 className="text-3xl font-bold text-gray-900">Сегменты покупателей</h1>
          </div>
          <div className="flex gap-4">
            <button
              onClick={handleAutoGenerate}
              disabled={generating}
              className="px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 disabled:opacity-50"
            >
              {generating ? 'Генерация...' : 'Автосегментация AI'}
            </button>
            <button
              onClick={openCreateModal}
              className="px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700"
            >
              Создать сегмент
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {segments.map((segment) => (
            <div
              key={segment.id}
              className="bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow duration-200 border border-gray-100 overflow-hidden flex flex-col h-full"
            >
              <div 
                className="h-1 w-full" 
                style={{ backgroundColor: segment.color || '#e5e7eb' }} 
              />
              
              <div className="p-5 flex-1 flex flex-col">
                <div className="flex items-start justify-between mb-3">
                  <h3 className="text-lg font-bold text-gray-900 line-clamp-1 pr-2" title={segment.name}>
                    {segment.name}
                  </h3>
                  {segment.is_auto_generated && (
                    <span className="flex-shrink-0 px-2 py-0.5 text-xs font-medium bg-purple-100 text-purple-700 rounded-full">
                      AI
                    </span>
                  )}
                </div>
                
                <p className="text-sm text-gray-600 mb-4 line-clamp-3 flex-1">
                  {segment.description || 'Нет описания'}
                </p>

                <div className="mb-4 rounded-lg border border-gray-100 bg-gray-50 p-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">Фильтры выборки</span>
                    {hasNestedRules(segment.rules) ? (
                      <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] text-indigo-700">Сложная логика</span>
                    ) : null}
                  </div>
                  <div className="space-y-1">
                    {humanizeRules(segment.rules).map((line, index) => (
                      <div key={index} className="line-clamp-1 text-xs text-gray-600" title={line}>
                        {line}
                      </div>
                    ))}
                  </div>
                </div>
                
                <div className="mt-auto pt-4 border-t border-gray-100">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Покупателей</span>
                    <span className="text-2xl font-bold text-gray-900">{segment.customer_count.toLocaleString()}</span>
                  </div>
                  
                  <div className="space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      <Link
                        href={`/admin/customers?segment_id=${segment.id}`}
                        className="col-span-2 flex items-center justify-center px-4 py-2 bg-pink-50 text-pink-700 text-sm font-medium rounded-lg hover:bg-pink-100 transition-colors"
                      >
                        Просмотреть список
                      </Link>
                      
                      <button
                        onClick={() => openEditModal(segment.id)}
                        className="col-span-2 flex items-center justify-center px-3 py-2 bg-gray-50 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-100 transition-colors border border-gray-200"
                      >
                        Редактировать фильтры
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={() => exportSegment(segment.id, 'csv')}
                        className="flex items-center justify-center px-3 py-2 bg-white text-gray-600 text-xs font-medium rounded-lg hover:bg-gray-50 transition-colors border border-gray-200"
                        title="Экспорт в CSV"
                      >
                        CSV
                      </button>
                      <button
                        onClick={() => exportSegment(segment.id, 'excel')}
                        className="flex items-center justify-center px-3 py-2 bg-white text-gray-600 text-xs font-medium rounded-lg hover:bg-gray-50 transition-colors border border-gray-200"
                        title="Экспорт в Excel"
                      >
                        Excel
                      </button>
                    </div>

                    <button
                      onClick={() => handleDeleteSegment(segment.id, segment.name)}
                      className="w-full flex items-center justify-center px-3 py-1.5 text-red-600 text-xs font-medium hover:bg-red-50 rounded-lg transition-colors mt-2"
                    >
                      Удалить сегмент
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {segments.length === 0 && (
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <p className="text-gray-500 mb-4">Сегментов пока нет</p>
            <button
              onClick={handleAutoGenerate}
              disabled={generating}
              className="px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 disabled:opacity-50"
            >
              {generating ? 'Генерация...' : 'Создать сегменты автоматически'}
            </button>
          </div>
        )}
        {isCreateModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40 p-4">
            <div className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg bg-white shadow-lg">
              <div className="border-b border-gray-100 px-6 py-4">
                <h2 className="text-xl font-semibold">{editSegmentId ? 'Редактировать сегмент' : 'Создать сегмент'}</h2>
              </div>
              <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Название сегмента
                  </label>
                  <input
                    type="text"
                    value={newSegmentName}
                    onChange={(e) => setNewSegmentName(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
                    placeholder="Например, VIP клиенты"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Описание
                  </label>
                  <textarea
                    value={newSegmentDescription}
                    onChange={(e) => setNewSegmentDescription(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
                    rows={3}
                    placeholder="Краткое описание сегмента"
                  />
                </div>

                <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-gray-900">Правила фильтрации</div>
                      <div className="text-xs text-gray-500">
                        AI-сегменты используют те же правила, что и ручная сегментация. Сложные вложенные AND/OR редактируются в расширенном режиме.
                      </div>
                    </div>
                    <label className="flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="checkbox"
                        checked={advancedRulesMode}
                        onChange={(e) => {
                          const checked = e.target.checked;
                          if (checked) {
                            setAdvancedRulesJson(JSON.stringify(parsedRules, null, 2));
                          }
                          setAdvancedRulesMode(checked);
                        }}
                        className="rounded border-gray-300 text-pink-600 focus:ring-pink-500"
                      />
                      Расширенный режим
                    </label>
                  </div>
                  <div className="mt-3 space-y-1">
                    {humanizeRules(parsedRules).map((line, index) => (
                      <div key={index} className="text-xs text-gray-600">{line}</div>
                    ))}
                  </div>
                </div>

                {advancedRulesMode ? (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">JSON правил сегмента</label>
                    <textarea
                      value={advancedRulesJson}
                      onChange={(e) => setAdvancedRulesJson(e.target.value)}
                      rows={12}
                      className="w-full font-mono text-xs px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
                    />
                    {advancedRulesError ? (
                      <div className="mt-1 text-xs text-red-600">{advancedRulesError}</div>
                    ) : (
                      <div className="mt-1 text-xs text-gray-500">Можно редактировать вложенные группы AND/OR без потери логики AI-сегмента.</div>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-sm text-gray-600">Логика по умолчанию</span>
                        <select
                          value={groupLogic}
                          onChange={(e) => setGroupLogic(e.target.value as 'AND' | 'OR')}
                          className="px-2 py-1 border rounded"
                        >
                          <option value="AND">AND</option>
                          <option value="OR">OR</option>
                        </select>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => addFilter('user')}
                          disabled={!availableFields}
                          className="px-3 py-1 bg-gray-100 text-gray-800 rounded hover:bg-gray-200 disabled:opacity-50"
                        >
                          + Поле покупателя
                        </button>
                        <button
                          onClick={() => addFilter('purchase_history')}
                          disabled={!availableFields}
                          className="px-3 py-1 bg-gray-100 text-gray-800 rounded hover:bg-gray-200 disabled:opacity-50"
                        >
                          + История покупок
                        </button>
                      </div>
                    </div>

                    <div className="space-y-3">
                  {filters.length === 0 && (
                    <div className="text-sm text-gray-500">Добавьте хотя бы одно условие или создайте сегмент без фильтров.</div>
                  )}
                  {filters.map((row, idx) => {
                    const srcFields = availableFields?.[row.source] || [];
                    let ops = operatorsByType[row.type];
                    
                    const isStore = isStoreField(row.field);
                    const isExcludeSegment = isExcludeSegmentField(row.field);
                    const isListOp = ['in', 'not_in'].includes(row.operator);
                    const segmentOptions = segments.filter((segment) => segment.id !== editSegmentId);

                    if (isStore) {
                      ops = ops.filter(o => o.value !== 'contains');
                    }
                    if (isExcludeSegment) {
                      ops = ops.filter((o) => o.value === 'equals' || o.value === 'in');
                    }

                    return (
                      <div key={idx} className="grid grid-cols-12 gap-3 items-center">
                        <div className="col-span-2">
                          {idx === 0 ? (
                            <div className="px-3 py-2 text-sm text-gray-400">Если</div>
                          ) : (
                            <select
                              value={row.connector || groupLogic}
                              onChange={(e) => updateFilterConnector(idx, e.target.value as 'AND' | 'OR')}
                              className="w-full px-3 py-2 border rounded"
                              title="Как связать это условие с предыдущими"
                            >
                              <option value="AND">AND</option>
                              <option value="OR">OR</option>
                            </select>
                          )}
                        </div>
                        <div className="col-span-2">
                          <select
                            value={row.source}
                            onChange={(e) => updateFilterSource(idx, e.target.value as 'user' | 'purchase_history')}
                            className="w-full px-3 py-2 border rounded"
                          >
                            <option value="user">Покупатель</option>
                            <option value="purchase_history">Покупки</option>
                          </select>
                        </div>
                        <div className="col-span-3">
                          <select
                            value={row.field}
                            onChange={(e) => updateFilterField(idx, e.target.value)}
                            className="w-full px-3 py-2 border rounded"
                          >
                            {srcFields.map((f) => (
                              <option key={f.name} value={f.name}>
                                {f.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="col-span-2">
                          <select
                            value={row.operator}
                            onChange={(e) => updateFilterOperator(idx, e.target.value)}
                            className="w-full px-3 py-2 border rounded"
                          >
                            {ops.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="col-span-3">
                          {isExcludeSegment && !isListOp ? (
                            <select
                              className="w-full px-3 py-2 border rounded"
                              value={row.value ?? ''}
                              onChange={(e) => updateFilterValue(idx, e.target.value)}
                            >
                              <option value="">— Выберите сегмент —</option>
                              {segmentOptions.map((segment) => (
                                <option key={segment.id} value={segment.id}>
                                  {segment.name} ({segment.customer_count.toLocaleString()})
                                </option>
                              ))}
                            </select>
                          ) : isExcludeSegment && isListOp ? (
                            <div className="relative group">
                              <div className="w-full px-3 py-2 border rounded cursor-pointer bg-white min-h-[42px] flex flex-wrap gap-1 items-center relative">
                                {(() => {
                                  const currentValues = String(row.value || '').split(',').map(v => v.trim()).filter(Boolean);
                                  if (currentValues.length === 0) {
                                    return <span className="text-gray-400 text-xs">Выберите сегменты...</span>;
                                  }
                                  const visible = currentValues.slice(0, 1);
                                  const remainder = currentValues.length - visible.length;
                                  return (
                                    <>
                                      {visible.map((val) => (
                                        <span key={val} className="bg-pink-100 text-pink-800 text-xs px-2 py-1 rounded-full whitespace-nowrap overflow-hidden max-w-[140px] text-ellipsis">
                                          {segmentLabelById[val] || val}
                                        </span>
                                      ))}
                                      {remainder > 0 && (
                                        <span className="bg-gray-100 text-gray-600 text-xs px-2 py-1 rounded-full whitespace-nowrap">
                                          +{remainder}
                                        </span>
                                      )}
                                    </>
                                  );
                                })()}
                                <div className="absolute right-1 top-1/2 transform -translate-y-1/2 pointer-events-none">
                                  <svg className="h-3 w-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                  </svg>
                                </div>
                              </div>
                              <div className="hidden group-hover:block absolute z-10 w-full min-w-[260px] bg-white border border-gray-200 rounded shadow-lg mt-1 max-h-60 overflow-y-auto p-2 right-0">
                                {segmentOptions.length === 0 && <div className="text-gray-400 text-sm p-2">Нет других сегментов</div>}
                                {segmentOptions.map((segment) => {
                                  const currentValues = String(row.value || '').split(',').map(v => v.trim()).filter(Boolean);
                                  const checked = currentValues.includes(segment.id);
                                  return (
                                    <label key={segment.id} className="flex items-center space-x-2 mb-1 cursor-pointer hover:bg-gray-50 p-2 rounded">
                                      <input
                                        type="checkbox"
                                        checked={checked}
                                        onChange={(e) => {
                                          let newValues = [...currentValues];
                                          if (e.target.checked) {
                                            newValues.push(segment.id);
                                          } else {
                                            newValues = newValues.filter(v => v !== segment.id);
                                          }
                                          updateFilterValue(idx, newValues.join(','));
                                        }}
                                        className="rounded border-gray-300 text-pink-600 focus:ring-pink-500 h-4 w-4"
                                      />
                                      <span className="text-sm text-gray-700">
                                        {segment.name} ({segment.customer_count.toLocaleString()})
                                      </span>
                                    </label>
                                  );
                                })}
                              </div>
                            </div>
                          ) : isStore && !isListOp ? (
                            <>
                              <select
                                className="w-full px-3 py-2 border rounded"
                                value={row.value ?? ''}
                                onChange={(e) => updateFilterValue(idx, e.target.value)}
                                onFocus={async () => {
                                  if (!storesLoading && stores.length === 0) {
                                    try {
                                      setStoresLoading(true);
                                      const r = await apiClient.get('/api/stores', { params: { active: true } });
                                      const list = (Array.isArray(r.data) ? r.data : []).filter((store: any) => {
                                        const name = String(store?.name || '').trim().toLowerCase();
                                        return name === 'трк центрум' || name === 'ялта, набережная 18';
                                      });
                                      setStores(list);
                                      if (!list.length) setStoresError('Пустой список магазинов');
                                    } catch (e: any) {
                                      const msg = e?.response?.data?.detail || e?.message || String(e);
                                      setStoresError(msg);
                                      console.error('[Segments] onFocus load stores error:', e);
                                    } finally {
                                      setStoresLoading(false);
                                    }
                                  }
                                }}
                              >
                                <option value="">{storesLoading ? 'Загрузка...' : '— Выберите —'}</option>
                                {stores.map((s) => (
                                  <option
                                    key={s.id}
                                    value={(row.field === 'preferred_store' || row.field === 'preferred_store_name' || row.field === 'last_store_name' || row.field === 'secondary_store') ? s.name : (s.external_id || s.id)}
                                  >
                                    {s.name}{s.city ? ` — ${s.city}` : ''}
                                  </option>
                                ))}
                              </select>
                              {storesError && <div className="text-xs text-red-600">{storesError}</div>}
                            </>
                          ) : isStore && isListOp ? (
                            <div className="relative group">
                              <div className="w-full px-3 py-2 border rounded cursor-pointer bg-white min-h-[42px] flex flex-wrap gap-1 items-center relative">
                                {(() => {
                                  const currentValues = String(row.value || '').split(',').map(v => v.trim()).filter(Boolean);
                                  if (currentValues.length === 0) {
                                    return <span className="text-gray-400 text-xs">Выберите...</span>;
                                  }
                                  const displayLimit = 1;
                                  const visible = currentValues.slice(0, displayLimit);
                                  const remainder = currentValues.length - displayLimit;
                                  return (
                                    <>
                                      {visible.map(val => {
                                        const store = stores.find(s => s.name === val || s.external_id === val || s.id === val);
                                        const label = store ? store.name : val;
                                        return (
                                          <span key={val} className="bg-pink-100 text-pink-800 text-xs px-2 py-1 rounded-full whitespace-nowrap overflow-hidden max-w-[100px] text-ellipsis">
                                            {label}
                                          </span>
                                        );
                                      })}
                                      {remainder > 0 && (
                                        <span className="bg-gray-100 text-gray-600 text-xs px-2 py-1 rounded-full whitespace-nowrap">
                                          +{remainder}
                                        </span>
                                      )}
                                    </>
                                  );
                                })()}
                                <div className="absolute right-1 top-1/2 transform -translate-y-1/2 pointer-events-none">
                                  <svg className="h-3 w-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                  </svg>
                                </div>
                              </div>
                              <div className="hidden group-hover:block absolute z-10 w-full min-w-[200px] bg-white border border-gray-200 rounded shadow-lg mt-1 max-h-60 overflow-y-auto p-2 right-0">
                                {stores.length === 0 && <div className="text-gray-400 text-sm p-2">Нет магазинов</div>}
                                {stores.map((s) => {
                                  const val = (row.field === 'preferred_store' || row.field === 'preferred_store_name' || row.field === 'last_store_name' || row.field === 'secondary_store') ? s.name : (s.external_id || s.id);
                                  const currentValues = String(row.value || '').split(',').map(v => v.trim()).filter(Boolean);
                                  const checked = currentValues.includes(val);
                                  return (
                                    <label key={s.id} className="flex items-center space-x-2 mb-1 cursor-pointer hover:bg-gray-50 p-2 rounded">
                                      <input
                                        type="checkbox"
                                        checked={checked}
                                        onChange={(e) => {
                                          let newValues = [...currentValues];
                                          if (e.target.checked) {
                                            newValues.push(val);
                                          } else {
                                            newValues = newValues.filter(v => v !== val);
                                          }
                                          updateFilterValue(idx, newValues.join(','));
                                        }}
                                        className="rounded border-gray-300 text-pink-600 focus:ring-pink-500 h-4 w-4"
                                      />
                                      <span className="text-sm text-gray-700">{s.name}{s.city ? ` — ${s.city}` : ''}</span>
                                    </label>
                                  );
                                })}
                              </div>
                            </div>
                          ) : isListOp ? (
                            <input
                              type="text"
                              value={row.value}
                              onChange={(e) => updateFilterValue(idx, e.target.value)}
                              className="w-full px-3 py-2 border rounded"
                              placeholder={isStore ? "Магазины через запятую" : "через запятую"}
                            />
                          ) : row.type === 'number' || row.operator === 'within_last_days' ? (
                            <input
                              type="number"
                              value={row.value}
                              onChange={(e) => updateFilterValue(idx, e.target.value)}
                              className="w-full px-3 py-2 border rounded"
                            />
                          ) : row.type === 'date' ? (
                            <input
                              type="date"
                              value={row.value}
                              onChange={(e) => updateFilterValue(idx, e.target.value)}
                              className="w-full px-3 py-2 border rounded"
                            />
                          ) : (
                            <input
                              type="text"
                              value={row.value}
                              onChange={(e) => updateFilterValue(idx, e.target.value)}
                              className="w-full px-3 py-2 border rounded"
                            />
                          )}
                        </div>
                        <div className="col-span-1">
                          <button
                            onClick={() => removeFilter(idx)}
                            className="px-2 py-2 bg-red-50 text-red-700 rounded hover:bg-red-100"
                            title="Удалить"
                          >
                            ×
                          </button>
                        </div>
                      </div>
                    );
                  })}
                    </div>
                  </>
                )}

                <div className="flex items-center gap-3">
                  <div className="text-sm text-gray-600">
                    {calcLoading ? 'Подсчет...' : calcCount !== null ? `Покупателей: ${calcCount}` : 'Покупателей: —'}
                  </div>
                  {calcLoading && <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-pink-600"></div>}
                </div>
              </div>
              <div className="flex justify-end gap-3 border-t border-gray-100 px-6 py-4">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200"
                  disabled={creatingSegment}
                >
                  Отмена
                </button>
                <button
                  type="button"
                  onClick={handleCreateSegment}
                  disabled={creatingSegment || !newSegmentName.trim() || Boolean(advancedRulesMode && advancedRulesError)}
                  className="px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 disabled:opacity-50"
                >
                  {creatingSegment ? 'Сохранение...' : editSegmentId ? 'Сохранить' : 'Создать'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
