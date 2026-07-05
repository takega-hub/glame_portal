'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api, type OneCSeller, type SellerKpiResponse, type SellerKpiRow, type SellerKpiSnapshot, type SellerKpiTargetsResponse, type SellerKpiAssortmentGuidanceResponse, type SellerKpiAssortmentGuidanceRow, type SellerShift, type SellerShiftExcelImportResponse } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

const today = new Date();
const currentMonth = today.toISOString().slice(0, 7);
const monthStart = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10);
const monthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0).toISOString().slice(0, 10);

const STORE_OPTIONS = [
  { value: 'ТРК Центрум', label: 'Центрум — ТРК Центрум' },
  { value: 'Ялта, Набережная 18', label: 'Ялта — Набережная Ленина, 18' },
  { value: 'Меганом', label: 'Меганом' },
];

const KNOWN_SELLER_NAMES_BY_EXTERNAL_ID: Record<string, string> = {
  '6ded351c-4a43-11f1-9b6c-fa163e4cc04e': 'Максимычева Евгения',
  '4a1f26ca-a92d-11f0-9b8f-fa163e4cc04e': 'Уразгильдеева Екатерина',
  '1d5f839e-ba5a-11f0-836e-fa163e4cc04e': 'Рогалевич Ирина',
  'eee9caf0-293b-11f1-83c6-fa163e4cc04e': 'Бешлиева Аджере',
  '4d189eb8-4ee8-11f1-9b97-fa163e4cc04e': 'Орешников Анатолий',
};

function resolveSellerDisplayName(seller: Pick<SellerKpiRow, 'seller_name' | 'seller_external_id'>) {
  const rawName = seller.seller_name?.trim();
  const isUnknownName = !rawName || ['без имени', 'не сопоставлено с продавцом'].includes(rawName.toLowerCase());
  if (!isUnknownName) return rawName;
  return seller.seller_external_id ? KNOWN_SELLER_NAMES_BY_EXTERNAL_ID[seller.seller_external_id] : undefined;
}

function sellerPersonalHref(row: Pick<SellerKpiRow, 'seller_external_id' | 'seller_name' | 'store_name'>, month: string) {
  const params = new URLSearchParams();
  params.set('month', month);
  if (row.store_name) params.set('store_name', row.store_name);
  if (row.seller_external_id) params.set('seller_external_id', row.seller_external_id);
  const displayName = resolveSellerDisplayName(row as SellerKpiRow) || row.seller_name;
  if (displayName) params.set('seller_name', displayName);
  return `/profile/sellers/personal?${params.toString()}`;
}

type TabKey = 'kpi' | 'schedule' | 'list';

function sellerKey(seller: OneCSeller, index: number) {
  return seller.external_id || seller.code || seller.email || `${seller.name}-${index}`;
}

function formatMoney(value?: number | null) {
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value || 0);
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined) return '—';
  return `${value}%`;
}

function formatMetricValue(value: number | null | undefined, format: string) {
  if (value === null || value === undefined) return '—';
  if (format === 'money') return formatMoney(value);
  if (format === 'percent') {
    const percentValue = Math.abs(value) <= 1 ? value * 100 : value;
    return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(percentValue)}%`;
  }
  if (format === 'decimal') return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value);
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value);
}

function parsePlanInput(value: string) {
  const normalized = value.replace(/\s/g, '').replace(',', '.');
  return normalized === '' ? null : Number(normalized);
}

function completionColor(value?: number | null) {
  if (value === null || value === undefined) return 'bg-gray-100 text-gray-600';
  if (value >= 100) return 'bg-emerald-100 text-emerald-800';
  if (value >= 75) return 'bg-amber-100 text-amber-800';
  return 'bg-red-100 text-red-700';
}

function progressBarColor(value?: number | null) {
  if (value === null || value === undefined) return 'bg-gray-300';
  if (value >= 100) return 'bg-emerald-500';
  if (value >= 75) return 'bg-amber-500';
  return 'bg-red-500';
}

function normalizeText(value?: string | null) {
  return (value || '').trim().toLowerCase();
}

function samePerson(left?: string | null, right?: string | null) {
  const a = normalizeText(left);
  const b = normalizeText(right);
  return Boolean(a && b && (a === b || a.includes(b) || b.includes(a)));
}

function dateRange(startDate: string, endDate: string) {
  if (!startDate || !endDate) return [];
  const start = new Date(`${startDate}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) return [];
  const dates: string[] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    dates.push(cursor.toISOString().slice(0, 10));
    cursor.setDate(cursor.getDate() + 1);
  }
  return dates;
}

function metricRecommendation(key: string, percent?: number | null) {
  if (percent === null || percent === undefined) return 'План пока не задан: администратор должен зафиксировать цель, чтобы видеть выполнение.';
  if (percent >= 100) return 'Цель выполняется. Сохраняйте темп и используйте удачные скрипты в сменах.';
  if (key === 'revenue') return 'Сделайте упор на допродажи комплектов и работу с клиентами, которые уже выбирают изделие.';
  if (key === 'average_check') return 'Поднимайте средний чек через комплекты, второй товар и premium-аргументацию ценности.';
  if (key === 'average_item_price') return 'Показывайте более сильные позиции коллекции и объясняйте материалы, образ и универсальность.';
  if (key === 'check_length') return 'Добавляйте к основному изделию серьги, кольцо, подвеску или уход как естественное продолжение образа.';
  if (key === 'checks') return 'Фокус на конверсии входящего трафика: быстрый контакт, выявление повода и доведение до примерки.';
  if (key === 'conversion') return 'Усильте первый контакт, вопросы о поводе покупки и предложение 2–3 готовых вариантов.';
  return 'Показатель ниже плана: разберите смены, где результат был выше, и повторите рабочие действия.';
}

function sparklinePath(values: number[], width = 320, height = 96) {
  if (values.length === 0) return '';
  if (values.length === 1) return `M0 ${height - Math.min(Math.max(values[0], 0), 100) / 100 * height}`;
  const max = Math.max(...values, 100);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  return values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
}

function formatDateShort(value?: string | null) {
  if (!value) return '—';
  const [, monthValue, dayValue] = value.slice(0, 10).split('-');
  return `${dayValue}.${monthValue}`;
}

function fileToBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      resolve(result.includes(',') ? result.split(',')[1] : result);
    };
    reader.onerror = () => reject(reader.error || new Error('Не удалось прочитать Excel-файл'));
    reader.readAsDataURL(file);
  });
}

export default function ProfileSellersPage() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const initialTab = searchParams.get('tab') as TabKey | null;
  const initialStoreName = searchParams.get('store_name') || 'ТРК Центрум';
  const [activeTab, setActiveTab] = useState<TabKey>(initialTab && ['kpi', 'schedule', 'list'].includes(initialTab) ? initialTab : 'kpi');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [endpoint, setEndpoint] = useState<string | null>(null);
  const [totalLoaded, setTotalLoaded] = useState<number | null>(null);
  const [filteredOut, setFilteredOut] = useState<number | null>(null);
  const [sellers, setSellers] = useState<OneCSeller[]>([]);
  const [query, setQuery] = useState('');
  const [selectedStoreName, setSelectedStoreName] = useState(initialStoreName);

  const [month, setMonth] = useState(currentMonth);
  const [kpi, setKpi] = useState<SellerKpiResponse | null>(null);
  const [kpiTargets, setKpiTargets] = useState<SellerKpiTargetsResponse | null>(null);
  const [assortmentGuidance, setAssortmentGuidance] = useState<SellerKpiAssortmentGuidanceResponse | null>(null);
  const [assortmentDraftRows, setAssortmentDraftRows] = useState<SellerKpiAssortmentGuidanceRow[]>([]);
  const [savingAssortmentGuidance, setSavingAssortmentGuidance] = useState(false);
  const [kpiSnapshots, setKpiSnapshots] = useState<SellerKpiSnapshot[]>([]);
  const [planInputs, setPlanInputs] = useState<Record<string, string>>({});
  const [savingTargets, setSavingTargets] = useState(false);
  const [targetOrder, setTargetOrder] = useState<string[]>([]);
  const [draggedMetric, setDraggedMetric] = useState<string | null>(null);

  const [scheduleStart, setScheduleStart] = useState(monthStart);
  const [scheduleEnd, setScheduleEnd] = useState(monthEnd);
  const [shifts, setShifts] = useState<SellerShift[]>([]);
  const [savingShift, setSavingShift] = useState(false);
  const [importingSchedule, setImportingSchedule] = useState(false);
  const [scheduleImportFile, setScheduleImportFile] = useState<File | null>(null);
  const [scheduleImportPreview, setScheduleImportPreview] = useState<SellerShiftExcelImportResponse | null>(null);
  const [replaceExistingSchedule, setReplaceExistingSchedule] = useState(false);
  const [selectedScheduleSeller, setSelectedScheduleSeller] = useState('');
  const [draggedShift, setDraggedShift] = useState<SellerShift | null>(null);
  const [shiftForm, setShiftForm] = useState<SellerShift>({
    shift_date: new Date().toISOString().slice(0, 10),
    seller_name: '',
    store_name: '',
    starts_at: '10:00',
    ends_at: '22:00',
    note: '',
  });

  const role = user?.role || '';
  const isSellerView = role === 'seller';
  const canEditSchedule = role === 'admin' || role === 'manager';
  const canEditPlans = role === 'admin';
  const canViewManagerAnalytics = role === 'admin' || role === 'manager';

  const loadSellers = async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const response = await api.getOneCSellers({ limit: 500 });
      setEndpoint(response.endpoint);
      setTotalLoaded(response.total_loaded ?? response.count ?? null);
      setFilteredOut(response.filtered_out ?? null);
      setSellers(response.sellers || []);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось получить продавцов из 1С');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const loadKpi = async () => {
    setError(null);
    try {
      const params = { month, ...(isSellerView ? {} : selectedStoreName ? { store_name: selectedStoreName } : {}) };
      const response = await api.getSellerKpi(params);
      setKpi(response);
      const targets = await api.getSellerKpiTargets(params);
      setKpiTargets(targets);
      const assortment = await api.getSellerKpiAssortmentGuidance({
        ...params,
        seller_personal_plan: isSellerView ? (currentSellerKpi?.revenue_plan || undefined) : undefined,
      });
      setAssortmentGuidance(assortment);
      setAssortmentDraftRows(assortment.rows || []);
      if (!isSellerView) {
        const snapshots = await api.getSellerKpiSnapshots({ month, limit: 60 });
        setKpiSnapshots(snapshots.snapshots || []);
      }
      setPlanInputs(Object.fromEntries((targets.rows || []).map((row) => [row.key, row.plan !== null && row.plan !== undefined ? String(row.plan) : ''])));
      setTargetOrder((current) => current.length ? current : (targets.rows || []).map((row) => row.key));
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось получить KPI продавцов');
    }
  };

  const loadShifts = async () => {
    setError(null);
    try {
      const response = await api.getSellerShifts({
        start_date: scheduleStart,
        end_date: scheduleEnd,
        ...(isSellerView ? {} : selectedStoreName ? { store_name: selectedStoreName } : {}),
      });
      setShifts(response.shifts || []);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось получить график смен');
    }
  };

  const refreshAll = async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    await Promise.all([loadSellers(true), loadKpi(), loadShifts()]);
    setLoading(false);
    setRefreshing(false);
  };

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadKpi();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month, selectedStoreName]);

  useEffect(() => {
    loadShifts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scheduleStart, scheduleEnd, selectedStoreName]);

  const filteredSellers = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sellers;
    return sellers.filter((seller) =>
      [seller.name, seller.email, seller.phone, seller.store, seller.position, seller.code]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(q))
    );
  }, [query, sellers]);

  const orderedTargetRows = useMemo(() => {
    const rows = kpiTargets?.rows || [];
    if (!targetOrder.length) return rows;
    const order = new Map(targetOrder.map((key, index) => [key, index]));
    return [...rows].sort((a, b) => (order.get(a.key) ?? 999) - (order.get(b.key) ?? 999));
  }, [kpiTargets, targetOrder]);



  const mergedSellerRows = useMemo(() => {
    const grouped = new Map<string, SellerKpiRow>();
    (kpi?.sellers || []).forEach((seller) => {
      const displayName = resolveSellerDisplayName(seller) || 'Не сопоставлено с продавцом';
      const storeKey = normalizeText(seller.store_name || seller.store_id || 'Без магазина');
      const sellerKey = normalizeText(displayName);
      const key = `${sellerKey}|${storeKey}`;
      const current = grouped.get(key);
      if (!current) {
        grouped.set(key, { ...seller, seller_name: displayName });
        return;
      }
      current.seller_external_id = current.seller_external_id || seller.seller_external_id;
      current.store_id = current.store_id || seller.store_id;
      current.store_name = current.store_name || seller.store_name;
      current.revenue = Number(current.revenue || 0) + Number(seller.revenue || 0);
      current.checks = Number(current.checks || 0) + Number(seller.checks || 0);
      current.items_sold = Number(current.items_sold || 0) + Number(seller.items_sold || 0);
      if (Number(seller.revenue_plan || 0) > Number(current.revenue_plan || 0)) {
        current.revenue_plan = seller.revenue_plan;
        current.checks_plan = seller.checks_plan;
        current.items_plan = seller.items_plan;
        current.shifts_plan = seller.shifts_plan;
        current.hours_plan = seller.hours_plan;
        current.plan_source = seller.plan_source;
      }
      current.completion_percent = current.revenue_plan ? Math.round((Number(current.revenue || 0) / Number(current.revenue_plan || 0)) * 1000) / 10 : null;
    });
    return Array.from(grouped.values()).sort((a, b) => Number(b.revenue || 0) - Number(a.revenue || 0));
  }, [kpi?.sellers]);

  const currentStoreSellerRows = useMemo(() => {
    const storeFilter = normalizeText(selectedStoreName);
    return mergedSellerRows
      .filter((row) => !storeFilter || normalizeText(row.store_name) === storeFilter)
      .map((row, index) => ({
        ...row,
        rank: index + 1,
        revenueGap: Math.max(Number(row.revenue_plan || 0) - Number(row.revenue || 0), 0),
        avgCheckFact: Number(row.checks || 0) > 0 ? Number(row.revenue || 0) / Number(row.checks || 0) : null,
        itemsPerCheckFact: Number(row.checks || 0) > 0 ? Number(row.items_sold || 0) / Number(row.checks || 0) : null,
      }));
  }, [mergedSellerRows, selectedStoreName]);

  const currentStoreSellerSummary = useMemo(() => {
    const sellersCount = currentStoreSellerRows.length;
    const inRisk = currentStoreSellerRows.filter((row) => row.completion_percent !== null && row.completion_percent !== undefined && row.completion_percent < 85).length;
    const revenue = currentStoreSellerRows.reduce((sum, row) => sum + Number(row.revenue || 0), 0);
    const plan = currentStoreSellerRows.reduce((sum, row) => sum + Number(row.revenue_plan || 0), 0);
    return { sellersCount, inRisk, revenue, plan, completion: plan ? Math.round((revenue / plan) * 1000) / 10 : null };
  }, [currentStoreSellerRows]);

  const currentSellerKpi = useMemo(() => {
    const rows = mergedSellerRows;
    if (rows.length === 0) return null;
    if (kpi?.scope === 'self' || isSellerView) {
      const userName = normalizeText(user?.full_name || user?.email);
      const matched =
        rows.find((row) => normalizeText(row.seller_name) === userName) ||
        rows.find((row) => normalizeText(row.seller_name).includes(userName) && userName.length > 2) ||
        rows.find((row) => userName.includes(normalizeText(row.seller_name)) && normalizeText(row.seller_name).length > 2);
      if (matched) return matched;
      return rows.find((row) => Number(row.revenue_plan || 0) > 0) || rows.find((row) => normalizeText(row.seller_name) !== normalizeText('Не сопоставлено с продавцом')) || rows[0];
    }
    return null;
  }, [isSellerView, kpi?.scope, mergedSellerRows, user?.email, user?.full_name]);

  const currentSellerProfile = useMemo(() => {
    if (!isSellerView) return null;
    const userName = normalizeText(user?.full_name || user?.email);
    const kpiName = normalizeText(currentSellerKpi?.seller_name);
    return (
      sellers.find((seller) => normalizeText(seller.name) === userName || normalizeText(seller.email) === normalizeText(user?.email)) ||
      sellers.find((seller) => kpiName && normalizeText(seller.name) === kpiName) ||
      null
    );
  }, [currentSellerKpi?.seller_name, isSellerView, sellers, user?.email, user?.full_name]);



  const mergedStoreRows = useMemo(() => {
    const grouped = new Map<string, NonNullable<SellerKpiResponse['stores']>[number]>();
    mergedSellerRows.forEach((seller) => {
      const storeName = seller.store_name || 'Без магазина';
      const key = normalizeText(storeName || seller.store_id || 'Без магазина');
      const current = grouped.get(key);
      if (!current) {
        grouped.set(key, {
          store_id: seller.store_id,
          store_name: storeName,
          revenue: Number(seller.revenue || 0),
          revenue_plan: Number(seller.revenue_plan || 0),
          checks: Number(seller.checks || 0),
          completion_percent: null,
        });
        return;
      }
      current.revenue = Number(current.revenue || 0) + Number(seller.revenue || 0);
      current.revenue_plan = Number(current.revenue_plan || 0) + Number(seller.revenue_plan || 0);
      current.checks = Number(current.checks || 0) + Number(seller.checks || 0);
      current.store_id = current.store_id || seller.store_id;
      current.store_name = current.store_name || storeName;
    });
    grouped.forEach((store) => {
      store.completion_percent = store.revenue_plan ? Math.round((Number(store.revenue || 0) / Number(store.revenue_plan || 0)) * 1000) / 10 : null;
    });
    return Array.from(grouped.values()).sort((a, b) => Number(b.revenue || 0) - Number(a.revenue || 0));
  }, [mergedSellerRows]);

  const currentStoreKpi = useMemo(() => {
    if (!currentSellerKpi?.store_name) return null;
    return (mergedStoreRows || []).find((store) => store.store_id === currentSellerKpi.store_id || normalizeText(store.store_name) === normalizeText(currentSellerKpi.store_name)) || null;
  }, [currentSellerKpi?.store_id, currentSellerKpi?.store_name, mergedStoreRows]);

  const scheduleStoreName = isSellerView ? (currentSellerKpi?.store_name || currentSellerProfile?.store || '') : selectedStoreName;
  const scheduleDates = useMemo(() => dateRange(scheduleStart, scheduleEnd), [scheduleStart, scheduleEnd]);

  const availableScheduleSellers = useMemo(() => {
    const storeFilter = normalizeText(scheduleStoreName);
    const names = new Set<string>();
    shifts
      .filter((shift) => !storeFilter || normalizeText(shift.store_name) === storeFilter)
      .forEach((shift) => {
        if (shift.seller_name?.trim()) names.add(shift.seller_name.trim());
      });
    (kpi?.sellers || [])
      .filter((seller) => !storeFilter || normalizeText(seller.store_name) === storeFilter)
      .forEach((seller) => {
        if (seller.seller_name?.trim()) names.add(seller.seller_name.trim());
      });
    sellers
      .filter((seller) => !storeFilter || !seller.store || normalizeText(seller.store) === storeFilter)
      .forEach((seller) => {
        if (seller.name?.trim()) names.add(seller.name.trim());
      });
    return Array.from(names).sort((a, b) => a.localeCompare(b, 'ru'));
  }, [kpi?.sellers, scheduleStoreName, sellers, shifts]);

  useEffect(() => {
    if (selectedScheduleSeller && availableScheduleSellers.includes(selectedScheduleSeller)) return;
    setSelectedScheduleSeller(availableScheduleSellers[0] || '');
  }, [availableScheduleSellers, selectedScheduleSeller]);

  const shiftsByDate = useMemo(() => {
    const grouped: Record<string, SellerShift[]> = {};
    const storeFilter = isSellerView ? normalizeText(currentSellerKpi?.store_name || currentSellerProfile?.store) : normalizeText(selectedStoreName);
    shifts
      .filter((shift) => !storeFilter || normalizeText(shift.store_name) === storeFilter)
      .forEach((shift) => {
        grouped[shift.shift_date] = grouped[shift.shift_date] || [];
        grouped[shift.shift_date].push(shift);
      });
    return grouped;
  }, [currentSellerKpi?.store_name, currentSellerProfile?.store, isSellerView, selectedStoreName, shifts]);

  const currentScheduleSellerName = isSellerView
    ? (currentSellerKpi?.seller_name || currentSellerProfile?.name || user?.full_name || user?.email || '')
    : selectedScheduleSeller;
  const scheduleMonthKey = (scheduleEnd || scheduleStart || month).slice(0, 7);
  const currentSellerShiftsInMonth = useMemo(() => {
    if (!currentScheduleSellerName) return [];
    return shifts.filter((shift) =>
      shift.shift_date?.startsWith(scheduleMonthKey) &&
      samePerson(shift.seller_name, currentScheduleSellerName) &&
      (!scheduleStoreName || normalizeText(shift.store_name) === normalizeText(scheduleStoreName))
    );
  }, [currentScheduleSellerName, scheduleMonthKey, scheduleStoreName, shifts]);
  const currentSellerShiftDates = useMemo(() => new Set(currentSellerShiftsInMonth.map((shift) => shift.shift_date)), [currentSellerShiftsInMonth]);



  const sellerMetricRows = useMemo(() => {
    const preferred = new Set(['revenue', 'checks', 'average_check', 'average_item_price', 'check_length', 'items_sold', 'conversion']);
    return orderedTargetRows.filter((row) => preferred.has(row.key) || row.percent !== null).slice(0, 8);
  }, [orderedTargetRows]);

  const weakestSellerMetrics = useMemo(() => {
    return sellerMetricRows
      .filter((row) => row.percent !== null && row.percent !== undefined && row.percent < 100)
      .sort((a, b) => (a.percent || 0) - (b.percent || 0))
      .slice(0, 3);
  }, [sellerMetricRows]);

  const analyticsRows = useMemo(() => {
    return orderedTargetRows.filter((row) => row.plan !== null || row.fact !== null || row.percent !== null);
  }, [orderedTargetRows]);

  const criticalMetricRows = useMemo(() => {
    return analyticsRows
      .filter((row) => row.percent !== null && row.percent !== undefined && row.percent < 85)
      .sort((a, b) => (a.percent || 0) - (b.percent || 0))
      .slice(0, 4);
  }, [analyticsRows]);

  const strongMetricRows = useMemo(() => {
    return analyticsRows
      .filter((row) => row.percent !== null && row.percent !== undefined && row.percent >= 100)
      .sort((a, b) => (b.percent || 0) - (a.percent || 0))
      .slice(0, 4);
  }, [analyticsRows]);

  const averageMetricCompletion = useMemo(() => {
    const values = analyticsRows.map((row) => row.percent).filter((value): value is number => value !== null && value !== undefined);
    if (!values.length) return null;
    return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
  }, [analyticsRows]);

  const forecastRiskRows = useMemo(() => {
    return analyticsRows
      .filter((row) => row.forecast_percent !== null && row.forecast_percent !== undefined && row.forecast_percent < 100)
      .sort((a, b) => (a.forecast_percent || 0) - (b.forecast_percent || 0))
      .slice(0, 5);
  }, [analyticsRows]);

  const revenueTargetRow = analyticsRows.find((row) => row.key === 'revenue');
  const topSellerRows = useMemo(() => {
    return [...mergedSellerRows]
      .sort((a, b) => (b.completion_percent || 0) - (a.completion_percent || 0))
      .slice(0, 5);
  }, [mergedSellerRows]);
  const maxSellerRevenue = Math.max(1, ...topSellerRows.map((row) => row.revenue || 0));

  const kpiHistoryPoints = useMemo(() => {
    return [...kpiSnapshots]
      .sort((a, b) => a.snapshot_date.localeCompare(b.snapshot_date))
      .map((snapshot) => {
        const revenueRow = (snapshot.rows || []).find((row) => row.key === 'revenue');
        const checksRow = (snapshot.rows || []).find((row) => row.key === 'checks_count');
        const avgCheckRow = (snapshot.rows || []).find((row) => row.key === 'avg_check');
        const conversionRow = (snapshot.rows || []).find((row) => row.key === 'conversion');
        return {
          date: snapshot.snapshot_date,
          revenue: Number(snapshot.totals?.revenue || revenueRow?.fact || 0),
          revenuePlan: Number(snapshot.totals?.revenue_plan || revenueRow?.plan || 0),
          completion: Number(snapshot.totals?.completion_percent || revenueRow?.percent || 0),
          checks: Number(checksRow?.fact || snapshot.totals?.checks || 0),
          avgCheck: Number(avgCheckRow?.fact || 0),
          conversion: Number(conversionRow?.fact || 0),
        };
      });
  }, [kpiSnapshots]);

  const completionTrendPath = sparklinePath(kpiHistoryPoints.map((point) => point.completion));
  const revenueTrendPath = sparklinePath(kpiHistoryPoints.map((point) => point.revenue));
  const checksTrendPath = sparklinePath(kpiHistoryPoints.map((point) => point.checks));
  const latestHistoryPoint = kpiHistoryPoints[kpiHistoryPoints.length - 1];
  const previousHistoryPoint = kpiHistoryPoints[kpiHistoryPoints.length - 2];
  const revenueDelta = latestHistoryPoint && previousHistoryPoint ? latestHistoryPoint.revenue - previousHistoryPoint.revenue : null;
  const completionDelta = latestHistoryPoint && previousHistoryPoint ? latestHistoryPoint.completion - previousHistoryPoint.completion : null;

  const moveMetric = (targetKey: string) => {
    if (!draggedMetric || draggedMetric === targetKey) return;
    setTargetOrder((current) => {
      const base = current.length ? current : (kpiTargets?.rows || []).map((row) => row.key);
      const next = base.filter((key) => key !== draggedMetric);
      const targetIndex = next.indexOf(targetKey);
      next.splice(targetIndex < 0 ? next.length : targetIndex, 0, draggedMetric);
      return next;
    });
  };

  const saveTargetPlans = async () => {
    setSavingTargets(true);
    setError(null);
    setMessage(null);
    try {
      const metrics = Object.fromEntries(
        Object.entries(planInputs).map(([key, value]) => [key, parsePlanInput(value)]).filter(([, value]) => value !== null && !Number.isNaN(value))
      );
      const result = await api.saveSellerKpiTargets({ month, ...(selectedStoreName ? { store_name: selectedStoreName } : {}), metrics });
      setMessage(`План KPI сохранен: ${result.saved} показателей`);
      await loadKpi();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить план KPI');
    } finally {
      setSavingTargets(false);
    }
  };

  const updateAssortmentDraftRow = (index: number, patch: Partial<SellerKpiAssortmentGuidanceRow>) => {
    setAssortmentDraftRows((current) => current.map((row, rowIndex) => {
      if (rowIndex !== index) return row;
      const next = { ...row, ...patch };
      const currentStock = Number(next.current_stock || 0);
      const incoming = Number(next.incoming || 0);
      const available = patch.available_to_sell !== undefined ? Number(patch.available_to_sell || 0) : currentStock + incoming;
      const salesGuidance = Number(next.sales_guidance || 0);
      return {
        ...next,
        available_to_sell: available,
        stock_after_guidance: available - salesGuidance,
      };
    }));
  };

  const saveAssortmentGuidance = async () => {
    if (!selectedStoreName) {
      setError('Выберите магазин для ассортиментного ориентира');
      return;
    }
    setSavingAssortmentGuidance(true);
    setError(null);
    setMessage(null);
    try {
      const rows = assortmentDraftRows.map((row) => ({
        ...row,
        current_stock: Number(row.current_stock || 0),
        incoming: Number(row.incoming || 0),
        available_to_sell: Number(row.available_to_sell || 0),
        share: Number(row.share || 0),
        sales_guidance: Number(row.sales_guidance || 0),
        stock_after_guidance: Number(row.stock_after_guidance || 0),
        soft_guidance: row.soft_guidance !== false,
      }));
      const revenuePlan = kpiTargets?.rows?.find((row) => row.key === 'revenue')?.plan ?? kpi?.totals?.revenue_plan ?? null;
      const result = await api.saveSellerKpiAssortmentGuidance({ month, store_name: selectedStoreName, rows, store_revenue_plan: revenuePlan });
      setMessage(`Ассортиментный ориентир сохранен: ${result.saved} блоков`);
      await loadKpi();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить ассортиментный ориентир');
    } finally {
      setSavingAssortmentGuidance(false);
    }
  };

  const saveShift = async () => {
    if (!shiftForm.shift_date || !shiftForm.seller_name.trim()) {
      setError('Укажите дату и продавца для смены');
      return;
    }
    setSavingShift(true);
    setError(null);
    setMessage(null);
    try {
      await api.saveSellerShift({ ...shiftForm, seller_name: shiftForm.seller_name.trim(), store_name: scheduleStoreName || shiftForm.store_name });
      setMessage('Смена сохранена');
      setShiftForm({ shift_date: shiftForm.shift_date, seller_name: selectedScheduleSeller, store_name: scheduleStoreName, starts_at: '10:00', ends_at: '22:00', note: '' });
      await loadShifts();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить смену');
    } finally {
      setSavingShift(false);
    }
  };

  const quickAddShift = async (shiftDate: string) => {
    if (!selectedScheduleSeller) {
      setError('Выберите сотрудника для добавления в слот');
      return;
    }
    if (!scheduleStoreName) {
      setError('Выберите магазин для графика');
      return;
    }
    setSavingShift(true);
    setError(null);
    setMessage(null);
    try {
      await api.saveSellerShift({
        shift_date: shiftDate,
        seller_name: selectedScheduleSeller,
        store_name: scheduleStoreName,
        starts_at: shiftForm.starts_at || '10:00',
        ends_at: shiftForm.ends_at || '22:00',
        note: shiftForm.note || '',
      });
      setMessage(`Смена добавлена: ${selectedScheduleSeller}, ${shiftDate}`);
      await loadShifts();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось добавить смену в слот');
    } finally {
      setSavingShift(false);
    }
  };

  const moveShiftToDate = async (shiftDate: string) => {
    if (!draggedShift || !canEditSchedule) return;
    if (draggedShift.shift_date === shiftDate && normalizeText(draggedShift.store_name) === normalizeText(scheduleStoreName)) {
      setDraggedShift(null);
      return;
    }
    setSavingShift(true);
    setError(null);
    setMessage(null);
    try {
      await api.saveSellerShift({
        ...draggedShift,
        shift_date: shiftDate,
        store_name: scheduleStoreName || draggedShift.store_name,
        starts_at: draggedShift.starts_at?.slice(0, 5) || '10:00',
        ends_at: draggedShift.ends_at?.slice(0, 5) || '22:00',
      });
      setMessage(`Смена перенесена: ${draggedShift.seller_name}, ${shiftDate}`);
      setDraggedShift(null);
      await loadShifts();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось перенести смену');
    } finally {
      setSavingShift(false);
    }
  };

  const editShift = (shift: SellerShift) => {
    setSelectedScheduleSeller(shift.seller_name || selectedScheduleSeller);
    setShiftForm({
      ...shift,
      store_name: scheduleStoreName || shift.store_name,
      starts_at: shift.starts_at?.slice(0, 5) || '10:00',
      ends_at: shift.ends_at?.slice(0, 5) || '22:00',
      note: shift.note || '',
    });
  };

  const deleteShift = async (shift: SellerShift) => {
    if (!shift.id || !window.confirm(`Удалить смену ${shift.seller_name} ${shift.shift_date}?`)) return;
    setError(null);
    try {
      await api.deleteSellerShift(shift.id);
      setMessage('Смена удалена');
      await loadShifts();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось удалить смену');
    }
  };

  const runScheduleExcelImport = async (dryRun: boolean) => {
    if (!scheduleImportFile) {
      setError('Выберите Excel-файл с листом “График”');
      return;
    }
    if (!scheduleStoreName) {
      setError('Выберите магазин для импорта графика');
      return;
    }
    setImportingSchedule(true);
    setError(null);
    setMessage(null);
    try {
      const contentBase64 = await fileToBase64(scheduleImportFile);
      const result = await api.importSellerShiftsExcel({
        filename: scheduleImportFile.name,
        content_base64: contentBase64,
        store_name: scheduleStoreName,
        dry_run: dryRun,
        replace_existing: replaceExistingSchedule,
      });
      setScheduleImportPreview(result);
      if (dryRun) {
        setMessage(`Предпросмотр: найдено ${result.parsed} смен, сотрудников: ${result.stats?.sellers_count || '—'}`);
      } else {
        setMessage(`График импортирован: сохранено ${result.saved} смен за ${result.period_month}`);
        await loadShifts();
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось импортировать график из Excel');
    } finally {
      setImportingSchedule(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl p-6">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">План/Факт</h1>
          <p className="mt-2 text-sm text-gray-600">
            KPI продавцов, ручное планирование в админке, ежедневный факт из чеков 1С, исторические снимки и график смен.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refreshAll(true)}
          disabled={loading || refreshing}
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-gray-800 transition hover:bg-gray-50 disabled:opacity-50"
        >
          {refreshing ? 'Обновление…' : 'Обновить'}
        </button>
      </div>

      <div className="mb-5 flex flex-wrap gap-2">
        {!isSellerView && (
          <a href="/profile/sellers/dashboard" className="rounded-full bg-gray-950 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-gray-800">
            Главный дашборд
          </a>
        )}
        {(isSellerView
          ? [
              ['kpi', 'Мой план и выполнение'],
              ['schedule', 'График моего магазина'],
            ]
          : [
              ['kpi', 'KPI и выполнение'],
              ['schedule', 'График смен'],
              ['list', 'Список продавцов'],
            ]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveTab(key as TabKey)}
            className={`rounded-full px-4 py-2 text-sm font-semibold ${activeTab === key ? 'bg-gold-600 text-white' : 'bg-white text-gray-700 shadow-sm hover:bg-gray-50'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {message && <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}

      {activeTab === 'kpi' && (
        <div className="space-y-5">
          <div className="rounded-lg bg-white p-5 shadow-md">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <h2 className="text-xl font-bold text-gray-900">{isSellerView ? 'Мой план и выполнение' : 'KPI за месяц'}</h2>
                <p className="mt-1 text-sm text-gray-600">
                  {isSellerView
                    ? 'Личный кабинет продавца: ваши продажи, план магазина, персональный план, прогресс по показателям и рекомендации, что подтянуть.'
                    : 'План устанавливает только администратор. Управляющий видит план-факт, аналитику, графики и рекомендации без права правки плановых значений.'}
                </p>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                {!isSellerView && (
                  <label className="text-sm font-medium text-gray-700">
                    Магазин
                    <select value={selectedStoreName} onChange={(e) => setSelectedStoreName(e.target.value)} className="mt-1 block rounded-lg border border-gray-300 px-3 py-2">
                      <option value="">Все магазины</option>
                      {STORE_OPTIONS.map((store) => (
                        <option key={store.value} value={store.value}>{store.label}</option>
                      ))}
                    </select>
                  </label>
                )}
                <label className="text-sm font-medium text-gray-700">
                  Месяц
                  <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="mt-1 block rounded-lg border border-gray-300 px-3 py-2" />
                </label>
              </div>
            </div>
          </div>

          {isSellerView && (
            <div className="space-y-5">
              <div className="grid gap-4 lg:grid-cols-4">
                <div className="rounded-2xl border border-gold-100 bg-white p-5 shadow-sm lg:col-span-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Продавец</div>
                  <div className="mt-2 text-2xl font-bold text-gray-900">
                    {currentSellerKpi?.seller_name || currentSellerProfile?.name || user?.full_name || user?.email || 'Продавец'}
                  </div>
                  <div className="mt-2 text-sm text-gray-600">
                    Магазин: <span className="font-semibold text-gray-900">{currentSellerKpi?.store_name || currentSellerProfile?.store || 'не указан'}</span>
                  </div>
                  <div className="mt-1 text-xs text-gray-500">
                    Данные пересчитываются из продаж и чеков 1С. Если магазин или ФИО указаны неверно — нужна правка привязки сотрудника.
                  </div>
                </div>
                <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                  <div className="text-sm text-gray-500">План магазина</div>
                  <div className="mt-2 text-2xl font-bold text-gray-900">{formatMoney(currentStoreKpi?.revenue_plan)}</div>
                  <div className="mt-2 text-xs text-gray-500">Факт: {formatMoney(currentStoreKpi?.revenue)} · {formatPercent(currentStoreKpi?.completion_percent)}</div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-100">
                    <div className={`h-full rounded-full ${progressBarColor(currentStoreKpi?.completion_percent)}`} style={{ width: `${Math.min(currentStoreKpi?.completion_percent || 0, 100)}%` }} />
                  </div>
                </div>
                <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                  <div className="text-sm text-gray-500">Персональный план</div>
                  <div className="mt-2 text-2xl font-bold text-gray-900">{formatMoney(currentSellerKpi?.revenue_plan)}</div>
                  <div className="mt-2 text-xs text-gray-500">Факт: {formatMoney(currentSellerKpi?.revenue)} · {formatPercent(currentSellerKpi?.completion_percent)}</div>
                  {currentSellerKpi?.plan_source === 'excel_formula_hours_share' && (
                    <div className="mt-1 text-xs text-gold-700">
                      Формула Excel: план магазина × часы продавца / часы магазина
                      {currentSellerKpi.hours_plan ? ` · ${currentSellerKpi.hours_plan} ч` : ''}
                      {currentSellerKpi.shifts_plan ? ` · ${currentSellerKpi.shifts_plan} смен` : ''}
                    </div>
                  )}
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-100">
                    <div className={`h-full rounded-full ${progressBarColor(currentSellerKpi?.completion_percent)}`} style={{ width: `${Math.min(currentSellerKpi?.completion_percent || 0, 100)}%` }} />
                  </div>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-2xl bg-white p-5 shadow-sm"><div className="text-sm text-gray-500">Выручка</div><div className="mt-2 text-2xl font-bold text-gray-900">{formatMoney(currentSellerKpi?.revenue)}</div></div>
                <div className="rounded-2xl bg-white p-5 shadow-sm"><div className="text-sm text-gray-500">Чеки</div><div className="mt-2 text-2xl font-bold text-gray-900">{currentSellerKpi?.checks || 0}</div></div>
                <div className="rounded-2xl bg-white p-5 shadow-sm"><div className="text-sm text-gray-500">Выполнение личного плана</div><div className="mt-2 text-2xl font-bold text-gray-900">{formatPercent(currentSellerKpi?.completion_percent)}</div></div>
              </div>

              <div className="rounded-2xl bg-white p-5 shadow-md">
                <div className="mb-4">
                  <div className="text-lg font-bold text-gray-900">Показатели и рекомендации</div>
                  <div className="text-sm text-gray-600">Прогресс по пунктам плана: что уже в норме и на что сделать упор в следующих сменах.</div>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  {sellerMetricRows.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-gray-300 p-6 text-sm text-gray-500 lg:col-span-2">Пока нет показателей для анализа. Дождитесь ежедневного пересчета факта или заполнения плана.</div>
                  ) : sellerMetricRows.map((row) => (
                    <div key={row.key} className="rounded-xl border border-gray-200 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-semibold text-gray-900">{row.label}</div>
                          <div className="mt-1 text-xs text-gray-500">Факт: {formatMetricValue(row.fact, row.format)} · План: {formatMetricValue(row.plan, row.format)}</div>
                        </div>
                        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${completionColor(row.percent)}`}>{formatPercent(row.percent)}</span>
                      </div>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-100">
                        <div className={`h-full rounded-full ${progressBarColor(row.percent)}`} style={{ width: `${Math.min(row.percent || 0, 100)}%` }} />
                      </div>
                      <div className="mt-3 text-sm text-gray-700">{metricRecommendation(row.key, row.percent)}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-3">
                {(weakestSellerMetrics.length ? weakestSellerMetrics : sellerMetricRows.slice(0, 3)).map((row) => (
                  <div key={`focus-${row.key}`} className="rounded-2xl border border-amber-200 bg-amber-50 p-4 shadow-sm">
                    <div className="text-sm font-bold text-gray-900">Фокус: {row.label}</div>
                    <div className="mt-2 text-sm text-gray-700">{metricRecommendation(row.key, row.percent)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}


          {assortmentGuidance && assortmentGuidance.rows.length > 0 && (
            <div className="overflow-hidden rounded-2xl border border-gold-200 bg-white shadow-md">
              <div className="border-b border-gold-100 bg-gold-50/70 px-5 py-4">
                <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="text-lg font-bold text-gray-900">Ассортиментный ориентир</div>
                    <div className="mt-1 text-sm text-gray-700">
                      {assortmentGuidance.explanation || 'Ассортиментный ориентир — не жёсткая квота, а структура плана, чтобы продавать весь ассортимент и не делать перекос в одну группу.'}
                    </div>
                    <div className="mt-1 text-xs text-gray-600">Важно: задача — продавать весь ассортимент и не продавать бренды под ноль.</div>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs font-semibold">
                    <span className="rounded-full bg-white px-3 py-1 text-gold-800">{assortmentGuidance.store_name || selectedStoreName || 'Магазин'}</span>
                    <span className="rounded-full bg-white px-3 py-1 text-gold-800">Ориентир: {formatMoney(assortmentGuidance.sum_sales_guidance)}</span>
                    {assortmentGuidance.soft_guidance && <span className="rounded-full bg-white px-3 py-1 text-emerald-700">не жёсткая квота</span>}
                    {canEditPlans && (
                      <button type="button" onClick={saveAssortmentGuidance} disabled={savingAssortmentGuidance || !assortmentDraftRows.length} className="rounded-full bg-gray-900 px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
                        {savingAssortmentGuidance ? 'Сохранение…' : 'Сохранить ассортиментный ориентир'}
                      </button>
                    )}
                  </div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-[1180px] w-full border-collapse text-sm">
                  <thead className="bg-gray-50 text-xs font-semibold uppercase tracking-wide text-gray-600">
                    <tr>
                      <th className="border-b border-gray-200 px-4 py-3 text-left">Блок</th>
                      {canEditPlans && <th className="border-b border-gray-200 px-4 py-3 text-right">Текущий остаток</th>}
                      {canEditPlans && <th className="border-b border-gray-200 px-4 py-3 text-right">Поступление</th>}
                      <th className="border-b border-gray-200 px-4 py-3 text-right">Доступно</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-right">Доля</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-right">Ориентир продаж</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-right">Остаток после ориентира</th>
                      {isSellerView && <th className="border-b border-gray-200 px-4 py-3 text-right">Личный ориентир</th>}
                      <th className="border-b border-gray-200 px-4 py-3 text-right">Факт</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-left">Роль блока</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(canEditPlans ? assortmentDraftRows : assortmentGuidance.rows).map((row, index) => (
                      <tr key={`assortment-${row.assortment_block}`}>
                        <td className="border-b border-gray-100 px-4 py-3 font-semibold text-gray-900">{row.assortment_block}</td>
                        {canEditPlans && <td className="border-b border-gray-100 px-3 py-2 text-right"><input type="number" value={row.current_stock ?? 0} onChange={(e) => updateAssortmentDraftRow(index, { current_stock: Number(e.target.value) })} className="w-28 rounded-lg border border-gray-200 px-2 py-1 text-right" /></td>}
                        {canEditPlans && <td className="border-b border-gray-100 px-3 py-2 text-right"><input type="number" value={row.incoming ?? 0} onChange={(e) => updateAssortmentDraftRow(index, { incoming: Number(e.target.value) })} className="w-28 rounded-lg border border-gray-200 px-2 py-1 text-right" /></td>}
                        <td className="border-b border-gray-100 px-4 py-3 text-right">{canEditPlans ? <input type="number" value={row.available_to_sell ?? 0} onChange={(e) => updateAssortmentDraftRow(index, { available_to_sell: Number(e.target.value) })} className="w-28 rounded-lg border border-gray-200 px-2 py-1 text-right" /> : formatMoney(row.available_to_sell)}</td>
                        <td className="border-b border-gray-100 px-4 py-3 text-right">{canEditPlans ? <input type="number" step="0.0001" value={row.share ?? 0} onChange={(e) => updateAssortmentDraftRow(index, { share: Number(e.target.value) })} className="w-24 rounded-lg border border-gray-200 px-2 py-1 text-right" /> : formatPercent(Math.round((row.share || 0) * 10000) / 100)}</td>
                        <td className="border-b border-gray-100 px-4 py-3 text-right font-semibold">{canEditPlans ? <input type="number" value={row.sales_guidance ?? 0} onChange={(e) => updateAssortmentDraftRow(index, { sales_guidance: Number(e.target.value) })} className="w-28 rounded-lg border border-gray-200 px-2 py-1 text-right font-semibold" /> : formatMoney(row.sales_guidance)}</td>
                        <td className="border-b border-gray-100 px-4 py-3 text-right">{formatMoney(row.stock_after_guidance)}</td>
                        {isSellerView && <td className="border-b border-gray-100 px-4 py-3 text-right font-semibold text-gold-800">{formatMoney(row.personal_sales_guidance)}</td>}
                        <td className="border-b border-gray-100 px-4 py-3 text-right">{formatMoney(row.fact_sales)} · {formatPercent(row.completion_percent)}</td>
                        <td className="border-b border-gray-100 px-4 py-3 text-gray-600">
                          {canEditPlans ? <input value={row.comment || ''} onChange={(e) => updateAssortmentDraftRow(index, { comment: e.target.value })} className="w-72 rounded-lg border border-gray-200 px-2 py-1" /> : (row.comment || 'Мягкий ориентир по ассортиментному блоку.')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="grid gap-3 border-t border-gray-100 p-5 lg:grid-cols-3">
                <div className="rounded-xl bg-gray-50 p-4 text-sm text-gray-700 lg:col-span-1">
                  <div className="font-semibold text-gray-900">Как использовать</div>
                  <div className="mt-1">Это не штрафной KPI: ориентир помогает видеть, из чего должен состоять план, и не уходить только в SALE или привычные группы.</div>
                </div>
                <div className="lg:col-span-2">
                  <div className="mb-2 text-sm font-semibold text-gray-900">Диагностика перекосов</div>
                  <div className="grid gap-2 md:grid-cols-2">
                    {(assortmentGuidance.diagnostics || []).map((diagnostic, index) => (
                      <div key={`assortment-diagnostic-${index}`} className={`rounded-xl p-3 text-sm ${diagnostic.severity === 'warning' ? 'bg-amber-50 text-amber-900' : diagnostic.severity === 'success' ? 'bg-emerald-50 text-emerald-900' : 'bg-blue-50 text-blue-900'}`}>
                        <div className="font-semibold">{diagnostic.title}</div>
                        <div className="mt-1 text-xs opacity-80">{diagnostic.text}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {!isSellerView && (
          <div className="overflow-x-auto rounded-lg bg-white shadow-md">
            <div className="flex items-center justify-between gap-3 border-b border-gray-200 px-5 py-4">
              <div>
                <div className="font-semibold text-gray-900">Целевые показатели</div>
                <div className="text-xs text-gray-500">
                  Плановые значения редактирует только администратор. Управляющий видит план-факт и аналитику без права изменения планов.
                </div>
              </div>
              {canEditPlans && (
                <button type="button" onClick={saveTargetPlans} disabled={savingTargets} className="rounded-lg bg-gold-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                  {savingTargets ? 'Сохранение…' : 'Сохранить план'}
                </button>
              )}
            </div>
            <table className="min-w-[1100px] w-full border-collapse text-sm">
              <thead className="bg-cyan-100 text-xs font-semibold uppercase tracking-wide text-gray-700">
                <tr>
                  <th className="border border-gray-300 px-3 py-3 text-left">Показатель</th>
                  <th className="border border-gray-300 px-3 py-3 text-right">План</th>
                  <th className="border border-gray-300 px-3 py-3 text-right">Факт</th>
                  <th className="border border-gray-300 px-3 py-3 text-right">% выполнения</th>
                  <th className="border border-gray-300 px-3 py-3 text-right">Прогноз выполнения</th>
                  <th className="border border-gray-300 px-3 py-3 text-right">% выполнения по прогнозу</th>
                  <th className="border border-gray-300 px-3 py-3 text-right">Отклонение</th>
                  <th className="border border-gray-300 px-3 py-3 text-right">Факт аналогичного месяца прошлого года</th>
                  <th className="border border-gray-300 px-3 py-3 text-right">Отклонение LFL</th>
                </tr>
              </thead>
              <tbody>
                {orderedTargetRows.map((row) => (
                  <tr
                    key={row.key}
                    draggable
                    onDragStart={() => setDraggedMetric(row.key)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => moveMetric(row.key)}
                    onDragEnd={() => setDraggedMetric(null)}
                    className={`${row.key === 'conversion' ? 'font-bold' : ''} ${draggedMetric === row.key ? 'opacity-50' : ''}`}
                  >
                    <td className="border border-gray-200 px-3 py-2 text-gray-900">
                      <div className="flex items-center gap-2">
                        <span className="cursor-grab rounded bg-gray-100 px-2 py-1 text-xs text-gray-500">⋮⋮</span>
                        <span>{row.label}</span>
                      </div>
                    </td>
                    <td className="border border-gray-200 bg-lime-100 px-3 py-2 text-right">
                      {canEditPlans && row.editable_plan ? (
                        <input
                          value={planInputs[row.key] ?? ''}
                          onChange={(e) => setPlanInputs((prev) => ({ ...prev, [row.key]: e.target.value }))}
                          className="w-28 rounded border border-lime-300 bg-white px-2 py-1 text-right"
                        />
                      ) : (
                        formatMetricValue(row.plan, row.format)
                      )}
                    </td>
                    <td className="border border-gray-200 px-3 py-2 text-right font-semibold">{formatMetricValue(row.fact, row.format)}</td>
                    <td className="border border-gray-200 px-3 py-2 text-right">
                      <div className="flex flex-col items-end gap-1">
                        <span>{formatPercent(row.percent)}</span>
                        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-gray-100">
                          <div className={`h-full rounded-full ${(row.percent || 0) >= 100 ? 'bg-emerald-500' : (row.percent || 0) >= 75 ? 'bg-amber-500' : 'bg-red-500'}`} style={{ width: `${Math.min(row.percent || 0, 100)}%` }} />
                        </div>
                      </div>
                    </td>
                    <td className="border border-gray-200 px-3 py-2 text-right font-semibold">{formatMetricValue(row.forecast, row.format)}</td>
                    <td className="border border-gray-200 px-3 py-2 text-right font-semibold text-emerald-700">{formatPercent(row.forecast_percent)}</td>
                    <td className="border border-gray-200 px-3 py-2 text-right">{formatMetricValue(row.deviation, row.format)}</td>
                    <td className="border border-gray-200 bg-lime-100 px-3 py-2 text-right">{formatMetricValue(row.last_year_fact, row.format)}</td>
                    <td className="border border-gray-200 px-3 py-2 text-right">{formatMetricValue(row.lfl_deviation, row.format)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-5 py-3 text-xs text-gray-500">
              Прогноз считается по текущему темпу: факт / прошедшие дни × дней в месяце. Сейчас прошло {kpiTargets?.elapsed_days || '—'} из {kpiTargets?.days_in_month || '—'} дней.
            </div>
          </div>
          )}

          {!isSellerView && (
            <div className="overflow-hidden rounded-lg bg-white shadow-md">
              <div className="flex flex-col gap-3 border-b border-gray-200 px-5 py-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="font-semibold text-gray-900">Продавцы выбранного магазина: план / факт</div>
                  <div className="mt-1 text-xs text-gray-500">
                    После плана магазина — персональная детализация по продавцам. Нажатие по строке открывает личный план с KPI.
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 text-xs font-semibold">
                  <span className="rounded-full bg-gray-100 px-3 py-1 text-gray-700">{selectedStoreName || 'Все магазины'}</span>
                  <span className="rounded-full bg-gray-100 px-3 py-1 text-gray-700">Продавцов: {currentStoreSellerSummary.sellersCount}</span>
                  <span className={`rounded-full px-3 py-1 ${currentStoreSellerSummary.inRisk ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}`}>В зоне внимания: {currentStoreSellerSummary.inRisk}</span>
                  <span className="rounded-full bg-gold-50 px-3 py-1 text-gold-800">Итого: {formatMoney(currentStoreSellerSummary.revenue)} / {formatMoney(currentStoreSellerSummary.plan)} · {formatPercent(currentStoreSellerSummary.completion)}</span>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-[1050px] w-full border-collapse text-sm">
                  <thead className="bg-gray-50 text-xs font-semibold uppercase tracking-wide text-gray-600">
                    <tr>
                      <th className="border-b border-gray-200 px-4 py-3 text-left">#</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-left">Продавец</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-right">Факт</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-right">План</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-right">Осталось</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-center">% выполнения</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-right">Чеки</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-right">Изделия</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-right">Средний чек</th>
                      <th className="border-b border-gray-200 px-4 py-3 text-right">KPI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {currentStoreSellerRows.length === 0 ? (
                      <tr>
                        <td colSpan={10} className="px-5 py-6 text-sm text-gray-500">Нет продавцов с KPI за выбранный месяц и магазин.</td>
                      </tr>
                    ) : currentStoreSellerRows.map((row) => (
                      <tr
                        key={`store-seller-${row.seller_external_id || row.seller_name}-${row.store_id || row.store_name}`}
                        onClick={() => { window.location.href = sellerPersonalHref(row, month); }}
                        className="cursor-pointer transition hover:bg-gold-50"
                        title="Открыть персональный план и KPI продавца"
                      >
                        <td className="border-b border-gray-100 px-4 py-3 font-semibold text-gray-500">{row.rank}</td>
                        <td className="border-b border-gray-100 px-4 py-3">
                          <Link href={sellerPersonalHref(row, month)} className="font-semibold text-gray-900 hover:text-gold-700">
                            {resolveSellerDisplayName(row) || row.seller_name || 'Без имени'}
                          </Link>
                          <div className="mt-1 text-xs text-gray-500">
                            {row.store_name || 'Без магазина'}
                            {row.plan_source === 'excel_formula_hours_share' && ` · план по часам: ${row.hours_plan || 0} ч / ${row.shifts_plan || 0} смен`}
                          </div>
                        </td>
                        <td className="border-b border-gray-100 px-4 py-3 text-right font-semibold text-gray-900">{formatMoney(row.revenue)}</td>
                        <td className="border-b border-gray-100 px-4 py-3 text-right">{formatMoney(row.revenue_plan)}</td>
                        <td className="border-b border-gray-100 px-4 py-3 text-right text-gray-600">{formatMoney(row.revenueGap)}</td>
                        <td className="border-b border-gray-100 px-4 py-3 text-center">
                          <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${completionColor(row.completion_percent)}`}>{formatPercent(row.completion_percent)}</span>
                          <div className="mx-auto mt-2 h-1.5 w-24 overflow-hidden rounded-full bg-gray-100">
                            <div className={`h-full rounded-full ${progressBarColor(row.completion_percent)}`} style={{ width: `${Math.min(row.completion_percent || 0, 100)}%` }} />
                          </div>
                        </td>
                        <td className="border-b border-gray-100 px-4 py-3 text-right">{row.checks || 0}</td>
                        <td className="border-b border-gray-100 px-4 py-3 text-right">
                          <div>{row.items_sold || 0}</div>
                          <div className="text-xs text-gray-500">{formatMetricValue(row.itemsPerCheckFact, 'decimal')} / чек</div>
                        </td>
                        <td className="border-b border-gray-100 px-4 py-3 text-right">{formatMoney(row.avgCheckFact)}</td>
                        <td className="border-b border-gray-100 px-4 py-3 text-right">
                          <Link href={sellerPersonalHref(row, month)} className="font-semibold text-gold-700 hover:text-gold-800">
                            Открыть →
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!isSellerView && (
          <div className="grid gap-4 lg:grid-cols-3">
            {(kpiTargets?.insights || []).map((insight, index) => (
              <div key={`${insight.type}-${index}`} className={`rounded-2xl border p-4 shadow-sm ${insight.severity === 'critical' ? 'border-red-200 bg-red-50' : insight.severity === 'warning' ? 'border-amber-200 bg-amber-50' : insight.severity === 'success' ? 'border-emerald-200 bg-emerald-50' : 'border-blue-200 bg-blue-50'}`}>
                <div className="text-sm font-bold text-gray-900">{insight.title}</div>
                <div className="mt-2 text-sm text-gray-700">{insight.text}</div>
              </div>
            ))}
          </div>
          )}

          {canViewManagerAnalytics && (
          <div className="grid gap-4 md:grid-cols-4">
            <div className="rounded-lg bg-white p-5 shadow-md"><div className="text-sm text-gray-500">Выполнение</div><div className="mt-2 text-2xl font-bold text-gray-900">{formatMoney(kpi?.totals.revenue)}</div></div>
            <div className="rounded-lg bg-white p-5 shadow-md"><div className="text-sm text-gray-500">План</div><div className="mt-2 text-2xl font-bold text-gray-900">{formatMoney(kpi?.totals.revenue_plan)}</div></div>
            <div className="rounded-lg bg-white p-5 shadow-md"><div className="text-sm text-gray-500">% выполнения</div><div className="mt-2 text-2xl font-bold text-gray-900">{formatPercent(kpi?.totals.completion_percent)}</div></div>
            <div className="rounded-lg bg-white p-5 shadow-md"><div className="text-sm text-gray-500">Чеки</div><div className="mt-2 text-2xl font-bold text-gray-900">{kpi?.totals.checks || 0}</div></div>
          </div>
          )}

          {canViewManagerAnalytics && (
            <div className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
              <div className="rounded-2xl bg-white p-5 shadow-md">
                <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="text-lg font-bold text-gray-900">План-факт по всем KPI</div>
                    <div className="text-sm text-gray-600">Инфографика по каждому показателю: план, факт, выполнение и прогноз месяца.</div>
                  </div>
                  <div className="rounded-full bg-gray-100 px-3 py-1 text-sm font-semibold text-gray-700">Среднее выполнение: {formatPercent(averageMetricCompletion)}</div>
                </div>
                <div className="space-y-4">
                  {analyticsRows.map((row) => {
                    const factWidth = Math.min(Math.max(row.percent || 0, 0), 140);
                    const forecastWidth = Math.min(Math.max(row.forecast_percent || 0, 0), 140);
                    return (
                      <div key={`analytics-${row.key}`} className="rounded-xl border border-gray-100 p-4">
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                          <div className="font-semibold text-gray-900">{row.label}</div>
                          <div className="flex flex-wrap gap-2 text-xs">
                            <span className={`rounded-full px-2.5 py-1 font-semibold ${completionColor(row.percent)}`}>Факт {formatPercent(row.percent)}</span>
                            <span className={`rounded-full px-2.5 py-1 font-semibold ${completionColor(row.forecast_percent)}`}>Прогноз {formatPercent(row.forecast_percent)}</span>
                          </div>
                        </div>
                        <div className="grid gap-2 text-xs text-gray-600 md:grid-cols-4">
                          <div>План: <span className="font-semibold text-gray-900">{formatMetricValue(row.plan, row.format)}</span></div>
                          <div>Факт: <span className="font-semibold text-gray-900">{formatMetricValue(row.fact, row.format)}</span></div>
                          <div>Прогноз: <span className="font-semibold text-gray-900">{formatMetricValue(row.forecast, row.format)}</span></div>
                          <div>Отклонение: <span className={(row.deviation || 0) >= 0 ? 'font-semibold text-emerald-700' : 'font-semibold text-red-700'}>{formatMetricValue(row.deviation, row.format)}</span></div>
                        </div>
                        <div className="mt-3 space-y-1">
                          <div className="relative h-3 overflow-hidden rounded-full bg-gray-100">
                            <div className={`h-full rounded-full ${progressBarColor(row.percent)}`} style={{ width: `${factWidth}%` }} />
                            <div className="absolute left-[71.4%] top-0 h-full w-px bg-gray-500/50" />
                          </div>
                          <div className="relative h-1.5 overflow-hidden rounded-full bg-blue-50">
                            <div className="h-full rounded-full bg-blue-400" style={{ width: `${forecastWidth}%` }} />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-5">
                <div className="rounded-2xl bg-white p-5 shadow-md">
                  <div className="text-lg font-bold text-gray-900">Аналитические выводы</div>
                  <div className="mt-4 grid gap-3">
                    <div className="rounded-xl bg-red-50 p-4"><div className="text-sm font-semibold text-red-800">Зоны риска</div><div className="mt-1 text-2xl font-bold text-red-900">{criticalMetricRows.length}</div><div className="mt-1 text-xs text-red-700">показателей ниже 85%</div></div>
                    <div className="rounded-xl bg-emerald-50 p-4"><div className="text-sm font-semibold text-emerald-800">Выполнены</div><div className="mt-1 text-2xl font-bold text-emerald-900">{strongMetricRows.length}</div><div className="mt-1 text-xs text-emerald-700">показателей 100%+</div></div>
                    <div className="rounded-xl bg-gold-50 p-4"><div className="text-sm font-semibold text-gold-800">Выручка</div><div className="mt-1 text-2xl font-bold text-gold-900">{formatPercent(revenueTargetRow?.percent)}</div><div className="mt-1 text-xs text-gold-700">{formatMoney(revenueTargetRow?.fact)} из {formatMoney(revenueTargetRow?.plan)}</div></div>
                  </div>
                </div>

                <div className="rounded-2xl bg-white p-5 shadow-md">
                  <div className="mb-3 text-lg font-bold text-gray-900">Прогнозные риски месяца</div>
                  <div className="space-y-3">
                    {forecastRiskRows.length === 0 ? (
                      <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">По текущему темпу прогноз закрывает план.</div>
                    ) : forecastRiskRows.map((row) => (
                      <div key={`forecast-${row.key}`} className="text-sm">
                        <div className="mb-1 flex justify-between gap-3"><span className="font-medium text-gray-900">{row.label}</span><span className="text-red-700">{formatPercent(row.forecast_percent)}</span></div>
                        <div className="h-2 overflow-hidden rounded-full bg-gray-100"><div className="h-full rounded-full bg-red-400" style={{ width: `${Math.min(row.forecast_percent || 0, 100)}%` }} /></div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl bg-white p-5 shadow-md">
                  <div className="mb-3 text-lg font-bold text-gray-900">Топ продавцов по выполнению</div>
                  <div className="space-y-3">
                    {topSellerRows.map((row) => (
                      <Link key={`top-${row.seller_external_id || row.seller_name || row.store_name}`} href={sellerPersonalHref(row, month)} className="block rounded-lg p-2 text-sm transition hover:bg-gold-50">
                        <div className="mb-1 flex justify-between gap-3"><span className="font-medium text-gray-900">{resolveSellerDisplayName(row) || row.seller_name || 'Без имени'}</span><span>{formatPercent(row.completion_percent)}</span></div>
                        <div className="h-2 overflow-hidden rounded-full bg-gray-100"><div className="h-full rounded-full bg-gold-500" style={{ width: `${Math.min(((row.revenue || 0) / maxSellerRevenue) * 100, 100)}%` }} /></div>
                        <div className="mt-1 flex justify-between gap-2 text-xs text-gray-500"><span>{formatMoney(row.revenue)} / {formatMoney(row.revenue_plan)}</span><span className="font-semibold text-gold-700">KPI →</span></div>
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {canViewManagerAnalytics && (
            <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
              <div className="rounded-2xl bg-white p-5 shadow-md">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-bold text-gray-900">Динамика выполнения</div>
                    <div className="text-sm text-gray-600">История ежедневных снимков KPI за выбранный месяц.</div>
                  </div>
                  <div className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">{kpiHistoryPoints.length} снимков</div>
                </div>
                {kpiHistoryPoints.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-gray-300 p-6 text-sm text-gray-500">История появится после ежедневных пересчетов KPI. Текущий снимок сохраняется при открытии KPI.</div>
                ) : (
                  <div className="space-y-4">
                    <svg viewBox="0 0 320 120" className="h-44 w-full overflow-visible" role="img" aria-label="Динамика выполнения KPI">
                      <line x1="0" y1="96" x2="320" y2="96" stroke="#d1d5db" strokeDasharray="4 4" />
                      <line x1="0" y1="48" x2="320" y2="48" stroke="#f3f4f6" />
                      <path d={revenueTrendPath} fill="none" stroke="#a78bfa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.55" />
                      <path d={completionTrendPath} fill="none" stroke="#d6a84f" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                      <path d={checksTrendPath} fill="none" stroke="#38bdf8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.75" />
                    </svg>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <div className="rounded-xl bg-gold-50 p-4"><div className="text-xs font-semibold text-gold-700">Последний снимок</div><div className="mt-1 text-xl font-bold text-gold-900">{formatDateShort(latestHistoryPoint?.date)}</div></div>
                      <div className="rounded-xl bg-gray-50 p-4"><div className="text-xs font-semibold text-gray-600">Δ выручки</div><div className={(revenueDelta || 0) >= 0 ? 'mt-1 text-xl font-bold text-emerald-700' : 'mt-1 text-xl font-bold text-red-700'}>{revenueDelta === null ? '—' : formatMoney(revenueDelta)}</div></div>
                      <div className="rounded-xl bg-gray-50 p-4"><div className="text-xs font-semibold text-gray-600">Δ выполнения</div><div className={(completionDelta || 0) >= 0 ? 'mt-1 text-xl font-bold text-emerald-700' : 'mt-1 text-xl font-bold text-red-700'}>{completionDelta === null ? '—' : `${completionDelta.toFixed(1)} п.п.`}</div></div>
                    </div>
                  </div>
                )}
              </div>

              <div className="rounded-2xl bg-white p-5 shadow-md">
                <div className="mb-4">
                  <div className="text-lg font-bold text-gray-900">Выручка и план по магазину</div>
                  <div className="text-sm text-gray-600">Сравнение магазинов: факт, план и выполнение.</div>
                </div>
                <div className="space-y-4">
                  {mergedStoreRows.map((store) => (
                    <div key={`store-chart-${store.store_id || store.store_name}`} className="rounded-xl border border-gray-100 p-4">
                      <div className="mb-2 flex items-center justify-between gap-3"><span className="font-semibold text-gray-900">{store.store_name}</span><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${completionColor(store.completion_percent)}`}>{formatPercent(store.completion_percent)}</span></div>
                      <div className="relative h-4 overflow-hidden rounded-full bg-gray-100">
                        <div className="h-full rounded-full bg-gold-500" style={{ width: `${Math.min(store.completion_percent || 0, 100)}%` }} />
                        <div className="absolute left-[99%] top-0 h-full w-px bg-gray-600/40" />
                      </div>
                      <div className="mt-2 flex justify-between text-xs text-gray-500"><span>{formatMoney(store.revenue)}</span><span>план {formatMoney(store.revenue_plan)}</span></div>
                    </div>
                  ))}
                  {mergedStoreRows.length === 0 && <div className="rounded-xl border border-dashed border-gray-300 p-6 text-sm text-gray-500">Нет данных по магазинам для графика.</div>}
                </div>
              </div>
            </div>
          )}

          {kpi?.seller_field_status === 'missing_in_sales_records' && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              В локальных чековых данных пока нет продавца. Новая синхронизация чеков будет сохранять продавца из 1С, если поле есть в Document_ЧекККМ.
            </div>
          )}

        </div>
      )}

      {activeTab === 'schedule' && (
        <div className="space-y-5">
          <div className="rounded-lg bg-white p-5 shadow-md">
            <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
              <div>
                <h2 className="text-xl font-bold text-gray-900">{isSellerView ? 'График моего магазина' : 'График смен по магазину'}</h2>
                <p className="mt-1 text-sm text-gray-600">
                  {isSellerView
                    ? `Продавец видит график магазина ${currentSellerKpi?.store_name || currentSellerProfile?.store || ''} без права редактирования.`
                    : 'Администратор/управляющий выбирает магазин сверху, добавляет сотрудника через плюс в нужный день и редактирует график drag-and-drop.'}
                </p>
                {currentScheduleSellerName && (
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                    <span className="rounded-full bg-gold-100 px-3 py-1 font-semibold text-gold-800">
                      {currentScheduleSellerName}
                    </span>
                    <span className="rounded-full bg-gray-100 px-3 py-1 text-gray-700">
                      Смен в месяце {scheduleMonthKey}: <span className="font-semibold text-gray-900">{currentSellerShiftsInMonth.length}</span>
                    </span>
                    <span className="text-xs text-gray-500">Рабочие дни сотрудника подсвечены золотым.</span>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-3">
                {!isSellerView && (
                  <label className="text-sm text-gray-700">Магазин<select value={selectedStoreName} onChange={(e) => setSelectedStoreName(e.target.value)} className="mt-1 block rounded-lg border border-gray-300 px-3 py-2"><option value="">Все магазины</option>{STORE_OPTIONS.map((store) => <option key={store.value} value={store.value}>{store.label}</option>)}</select></label>
                )}
                <label className="text-sm text-gray-700">С<input type="date" value={scheduleStart} onChange={(e) => setScheduleStart(e.target.value)} className="mt-1 block rounded-lg border border-gray-300 px-3 py-2" /></label><label className="text-sm text-gray-700">По<input type="date" value={scheduleEnd} onChange={(e) => setScheduleEnd(e.target.value)} className="mt-1 block rounded-lg border border-gray-300 px-3 py-2" /></label>
              </div>
            </div>
          </div>

          {canEditSchedule && (
            <div className="rounded-lg border border-gold-200 bg-gold-50/50 p-5 shadow-sm">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <h3 className="font-semibold text-gray-900">Загрузить график из Excel</h3>
                  <p className="mt-1 text-xs text-gray-600">
                    Агент прочитает лист “График”, возьмет только числовые отметки смен и заполнит календарь выбранного магазина. Метки “в”, “о”, “с”, “11с” не импортируются как рабочие смены.
                  </p>
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <input
                      type="file"
                      accept=".xlsx"
                      onChange={(event) => {
                        setScheduleImportFile(event.target.files?.[0] || null);
                        setScheduleImportPreview(null);
                      }}
                      className="block rounded-lg border border-gold-200 bg-white px-3 py-2 text-sm"
                    />
                    <label className="inline-flex items-center gap-2 text-xs text-gray-700">
                      <input type="checkbox" checked={replaceExistingSchedule} onChange={(event) => setReplaceExistingSchedule(event.target.checked)} />
                      Заменить все смены магазина за месяц файла
                    </label>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => runScheduleExcelImport(true)} disabled={importingSchedule || !scheduleImportFile || !scheduleStoreName} className="rounded-lg border border-gold-300 bg-white px-4 py-2 text-sm font-semibold text-gold-800 disabled:opacity-50">
                    {importingSchedule ? 'Чтение…' : 'Предпросмотр'}
                  </button>
                  <button type="button" onClick={() => runScheduleExcelImport(false)} disabled={importingSchedule || !scheduleImportFile || !scheduleStoreName} className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                    {importingSchedule ? 'Импорт…' : 'Применить импорт'}
                  </button>
                </div>
              </div>
              {scheduleImportPreview && (
                <div className="mt-4 rounded-xl border border-gold-100 bg-white p-4 text-sm text-gray-700">
                  <div className="font-semibold text-gray-900">
                    {scheduleImportPreview.dry_run ? 'Предпросмотр' : 'Результат импорта'}: {scheduleImportPreview.parsed} смен · {scheduleImportPreview.period_month} · {scheduleImportPreview.store_name}
                  </div>
                  <div className="mt-1 text-xs text-gray-500">
                    Сотрудников: {scheduleImportPreview.stats?.sellers_count || '—'} · пропущено отметок: {scheduleImportPreview.stats?.skipped_marks || 0} · сохранено: {scheduleImportPreview.saved}
                  </div>
                  {!!scheduleImportPreview.preview?.length && (
                    <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                      {scheduleImportPreview.preview.slice(0, 6).map((shift, index) => (
                        <div key={`${shift.shift_date}-${shift.seller_name}-${index}`} className="rounded-lg bg-gray-50 p-2 text-xs">
                          <span className="font-semibold text-gray-900">{shift.shift_date}</span> · {shift.seller_name} · {shift.starts_at?.slice(0, 5)}–{shift.ends_at?.slice(0, 5)}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {canEditSchedule && (
            <div className="rounded-lg bg-white p-5 shadow-md">
              <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <h3 className="font-semibold text-gray-900">Сотрудник для слотов</h3>
                  <p className="mt-1 text-xs text-gray-500">Выберите сотрудника и нажмите “+” в нужном дне. Карточки смен можно перетаскивать между днями.</p>
                </div>
                <div className="text-xs text-gray-500">Магазин: <span className="font-semibold text-gray-900">{scheduleStoreName || 'не выбран'}</span></div>
              </div>
              <div className="grid gap-3 md:grid-cols-5">
                <input type="date" value={shiftForm.shift_date} onChange={(e) => setShiftForm((f) => ({ ...f, shift_date: e.target.value }))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                <select
                  value={shiftForm.seller_name || selectedScheduleSeller}
                  onChange={(e) => {
                    setSelectedScheduleSeller(e.target.value);
                    setShiftForm((f) => ({ ...f, seller_name: e.target.value }));
                  }}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm md:col-span-2"
                >
                  <option value="">Выберите сотрудника</option>
                  {availableScheduleSellers.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
                <input type="time" value={shiftForm.starts_at || ''} onChange={(e) => setShiftForm((f) => ({ ...f, starts_at: e.target.value }))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                <input type="time" value={shiftForm.ends_at || ''} onChange={(e) => setShiftForm((f) => ({ ...f, ends_at: e.target.value }))} className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              </div>
              <div className="mt-3 flex gap-3"><input value={shiftForm.note || ''} onChange={(e) => setShiftForm((f) => ({ ...f, note: e.target.value }))} placeholder="Комментарий" className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" /><button type="button" onClick={saveShift} disabled={savingShift || !scheduleStoreName} className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{savingShift ? 'Сохранение…' : shiftForm.id ? 'Сохранить правку' : 'Сохранить'}</button></div>
            </div>
          )}

          <div className="overflow-x-auto rounded-lg bg-white shadow-md">
            <div className="grid min-w-[900px] grid-cols-7 divide-x divide-y divide-gray-200">
              {scheduleDates.length === 0 ? (
                <div className="col-span-7 p-8 text-center text-sm text-gray-500">Выберите корректный период графика.</div>
              ) : scheduleDates.map((date) => {
                const dayShifts = shiftsByDate[date] || [];
                const isCurrentEmployeeDay = currentSellerShiftDates.has(date);
                return (
                  <div
                    key={date}
                    onDragOver={(e) => canEditSchedule && e.preventDefault()}
                    onDrop={() => moveShiftToDate(date)}
                    className={`min-h-48 p-3 transition ${isCurrentEmployeeDay ? 'bg-gold-50 ring-2 ring-inset ring-gold-300' : draggedShift ? 'bg-gold-50/40' : ''}`}
                  >
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <div className={`font-semibold ${isCurrentEmployeeDay ? 'text-gold-900' : 'text-gray-900'}`}>{date}</div>
                      {canEditSchedule && (
                        <button
                          type="button"
                          onClick={() => quickAddShift(date)}
                          disabled={savingShift || !selectedScheduleSeller || !scheduleStoreName}
                          title={selectedScheduleSeller ? `Добавить ${selectedScheduleSeller}` : 'Выберите сотрудника'}
                          className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-gold-300 bg-gold-50 text-base font-bold leading-none text-gold-700 transition hover:bg-gold-100 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          +
                        </button>
                      )}
                    </div>
                    <div className="space-y-2">
                      {dayShifts.length === 0 && <div className="rounded-lg border border-dashed border-gray-200 p-3 text-xs text-gray-400">Свободный слот</div>}
                      {dayShifts.map((shift) => {
                        const isCurrentEmployeeShift = samePerson(shift.seller_name, currentScheduleSellerName);
                        return (
                        <div
                          key={shift.id || `${shift.shift_date}-${shift.seller_name}`}
                          draggable={canEditSchedule}
                          onDragStart={() => setDraggedShift(shift)}
                          onDragEnd={() => setDraggedShift(null)}
                          className={`rounded-lg border p-3 text-xs transition ${isCurrentEmployeeShift ? 'border-gold-300 bg-gold-100/80 shadow-sm' : 'border-gray-200 bg-gray-50'} ${canEditSchedule ? 'cursor-grab active:cursor-grabbing' : ''} ${draggedShift?.id && draggedShift.id === shift.id ? 'opacity-50' : ''}`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className={`font-semibold ${isCurrentEmployeeShift ? 'text-gold-950' : 'text-gray-900'}`}>{shift.seller_name}</div>
                            {canEditSchedule && <span className="rounded bg-white px-1.5 py-0.5 text-[10px] text-gray-400">⋮⋮</span>}
                          </div>
                          {isCurrentEmployeeShift && <div className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-gold-700">Текущий сотрудник</div>}
                          <div className="mt-1 text-gray-600">{shift.store_name || scheduleStoreName || 'Магазин не указан'}</div>
                          <div className="mt-1 text-gray-500">{shift.starts_at?.slice(0, 5) || '—'}–{shift.ends_at?.slice(0, 5) || '—'}</div>
                          {shift.note && <div className="mt-1 text-gray-500">{shift.note}</div>}
                          {canEditSchedule && <div className="mt-2 flex gap-2"><button type="button" onClick={() => editShift(shift)} className="text-gold-700 hover:underline">Изм.</button><button type="button" onClick={() => deleteShift(shift)} className="text-red-600 hover:underline">Удал.</button></div>}
                        </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'list' && (
        <div className="rounded-lg bg-white p-6 shadow-md">
          <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm text-gray-500">Активных продавцов</div>
              <div className="text-2xl font-bold text-gray-900">{loading ? '—' : sellers.length}</div>
              {endpoint && <div className="mt-1 text-xs text-gray-500">Источник 1С: {endpoint}</div>}
              {filteredOut !== null && filteredOut > 0 && <div className="mt-1 text-xs text-gray-500">Скрыто лишних записей: {filteredOut}{totalLoaded !== null ? ` из ${totalLoaded}` : ''}</div>}
            </div>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по имени, телефону, магазину…" className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm md:max-w-sm" />
          </div>
          {loading ? <div className="rounded-lg border border-gray-200 p-6 text-sm text-gray-500">Загружаем продавцов из 1С…</div> : filteredSellers.length === 0 ? <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-600">Продавцы не найдены</div> : (
            <div className="overflow-hidden rounded-lg border border-gray-200">
              <div className="hidden grid-cols-[1.4fr_1fr_0.8fr] gap-4 bg-gray-50 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500 md:grid"><div>Продавец</div><div>Контакты</div><div>Код</div></div>
              <div className="divide-y divide-gray-200">{filteredSellers.map((seller, index) => <div key={sellerKey(seller, index)} className="grid gap-3 px-4 py-4 text-sm md:grid-cols-[1.4fr_1fr_0.8fr] md:items-center md:gap-4"><div><div className="font-semibold text-gray-900">{seller.name || 'Без имени'}</div><div className="mt-1 text-xs text-gray-500">{seller.store || seller.position || 'Активный сотрудник'}</div></div><div className="space-y-1 text-gray-700"><div>{seller.phone || 'Телефон не указан'}</div><div className="text-xs text-gray-500">{seller.email || 'Email не указан'}</div></div><div className="text-gray-700">{seller.code || '—'}</div></div>)}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
