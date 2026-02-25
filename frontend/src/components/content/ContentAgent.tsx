'use client';

import { useEffect, useMemo, useState, useRef } from 'react';
import { api, apiClient } from '@/lib/api';
import CalendarView from './CalendarView';
import * as XLSX from 'xlsx';

const CHANNELS = [
  { value: 'website_main', label: 'Главная страница сайта' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'email', label: 'Email' },
  { value: 'vk', label: 'ВКонтакте' },
  { value: 'telegram', label: 'Telegram' },
];

function formatDateTime(value: string | Date) {
  try {
    const d = typeof value === 'string' ? new Date(value) : value;
    return new Intl.DateTimeFormat('ru-RU', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(d);
  } catch {
    return String(value);
  }
}

export default function ContentAgent() {
  const [name, setName] = useState<string>('AI Content Agent план');
  const [startDate, setStartDate] = useState<string>(() => {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  });
  const [endDate, setEndDate] = useState<string>(() => {
    const d = new Date();
    d.setDate(d.getDate() + 30);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  });
  const [timezone, setTimezone] = useState<string>('Europe/Moscow');
  const [channels, setChannels] = useState<string[]>(['instagram']);
  const [persona, setPersona] = useState<string>('');
  const [goal, setGoal] = useState<string>('');
  const [campaignContext, setCampaignContext] = useState<string>('');
  const [frequencyRulesJson, setFrequencyRulesJson] = useState<string>('{}');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [planId, setPlanId] = useState<string | null>(null);
  const [planPreview, setPlanPreview] = useState<any>(null);
  const [savedPlansLoading, setSavedPlansLoading] = useState(false);
  const [savedPlansError, setSavedPlansError] = useState<string | null>(null);
  const [savedPlans, setSavedPlans] = useState<any[]>([]);
  const [loadedPlanMeta, setLoadedPlanMeta] = useState<any>(null);

  const [itemsLoading, setItemsLoading] = useState(false);
  const [itemsError, setItemsError] = useState<string | null>(null);
  const [items, setItems] = useState<any[]>([]);
  const [generatingItemId, setGeneratingItemId] = useState<string | null>(null);
  const [generatedContentPreview, setGeneratedContentPreview] = useState<{
    itemId: string;
    generated: Record<string, any>;
  } | null>(null);
  const [regenerateFeedback, setRegenerateFeedback] = useState<string>('');

  const [yandexLoading, setYandexLoading] = useState(false);
  const [yandexError, setYandexError] = useState<string | null>(null);
  const [yandexCalendars, setYandexCalendars] = useState<Array<{ name: string | null; url: string | null }>>([]);
  const [yandexSyncResult, setYandexSyncResult] = useState<any>(null);

  // Edit plan modal states
  const [editingPlanId, setEditingPlanId] = useState<string | null>(null);
  const [editPlanName, setEditPlanName] = useState<string>('');
  const [editPlanStatus, setEditPlanStatus] = useState<string>('draft');
  const [editPlanStartDate, setEditPlanStartDate] = useState<string>('');
  const [editPlanEndDate, setEditPlanEndDate] = useState<string>('');
  const [editPlanTimezone, setEditPlanTimezone] = useState<string>('Europe/Moscow');
  const [updatingPlan, setUpdatingPlan] = useState(false);

  // Edit/Create item modal states
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [isCreatingItem, setIsCreatingItem] = useState(false);
  const [editItemScheduledAt, setEditItemScheduledAt] = useState<string>('');
  const [editItemTimezone, setEditItemTimezone] = useState<string>('Europe/Moscow');
  const [editItemChannel, setEditItemChannel] = useState<string>('instagram');
  const [editItemContentType, setEditItemContentType] = useState<string>('post');
  const [editItemTopic, setEditItemTopic] = useState<string>('');
  const [editItemHook, setEditItemHook] = useState<string>('');
  const [editItemCta, setEditItemCta] = useState<string>('');
  const [editItemPersona, setEditItemPersona] = useState<string>('');
  const [editItemCjmStage, setEditItemCjmStage] = useState<string>('');
  const [editItemGoal, setEditItemGoal] = useState<string>('');
  const [editItemStatus, setEditItemStatus] = useState<string>('planned');
  const [savingItem, setSavingItem] = useState(false);

  // View mode for slots: list or calendar
  const [viewMode, setViewMode] = useState<'list' | 'calendar'>('list');

  // Bulk operations states
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set());
  const [bulkOperationLoading, setBulkOperationLoading] = useState(false);
  const [showBulkStatusModal, setShowBulkStatusModal] = useState(false);
  const [bulkNewStatus, setBulkNewStatus] = useState<string>('ready');

  // Filters for plans
  const [planFilterStatus, setPlanFilterStatus] = useState<string>('');
  const [planFilterSearch, setPlanFilterSearch] = useState<string>('');
  const [planFilterDateFrom, setPlanFilterDateFrom] = useState<string>('');
  const [planFilterDateTo, setPlanFilterDateTo] = useState<string>('');

  // Filters for items (slots)
  const [itemFilterChannel, setItemFilterChannel] = useState<string>('');
  const [itemFilterStatus, setItemFilterStatus] = useState<string>('');
  const [itemFilterSearch, setItemFilterSearch] = useState<string>('');
  const [itemFilterDateFrom, setItemFilterDateFrom] = useState<string>('');
  const [itemFilterDateTo, setItemFilterDateTo] = useState<string>('');

  // Product Description states
  const [productsWithoutDesc, setProductsWithoutDesc] = useState<Array<{
    id: string;
    name: string;
    brand: string | null;
    category: string | null;
    price: number;
    tags: string[];
    has_description: boolean;
    description_length: number;
    external_code: string | null;
  }>>([]);
  const [productsLoading, setProductsLoading] = useState(false);
  const [productsError, setProductsError] = useState<string | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [descriptionLoading, setDescriptionLoading] = useState(false);
  const [descriptionResult, setDescriptionResult] = useState<any>(null);
  const [descriptionTargetLength, setDescriptionTargetLength] = useState<'short' | 'medium' | 'long'>('medium');
  const [descriptionRewrite, setDescriptionRewrite] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchResult, setBatchResult] = useState<any>(null);
  const [batchProgress, setBatchProgress] = useState<{
    current: number;
    total: number;
    currentProductName: string;
    successCount: number;
    errorCount: number;
    skippedCount: number;
  } | null>(null);
  const batchCancelledRef = useRef(false);
  const [productSearchQuery, setProductSearchQuery] = useState<string>('');
  const [allProductsWithoutDesc, setAllProductsWithoutDesc] = useState<Array<{
    id: string;
    name: string;
    brand: string | null;
    category: string | null;
    price: number;
    tags: string[];
    has_description: boolean;
    description_length: number;
    external_code: string | null;
  }>>([]);
  const [productSearchForRewrite, setProductSearchForRewrite] = useState<string>('');
  const [searchedProducts, setSearchedProducts] = useState<Array<{
    id: string;
    name: string;
    brand: string | null;
    category: string | null;
    price: number;
    tags: string[];
    has_description: boolean;
    description_length: number;
    external_code: string | null;
  }>>([]);
  const [searchingProducts, setSearchingProducts] = useState(false);

  // Обработка фото украшений
  const [jewelryArticle, setJewelryArticle] = useState('');
  const [jewelryFiles, setJewelryFiles] = useState<File[]>([]);
  const [jewelryProcessing, setJewelryProcessing] = useState(false);
  const [jewelryError, setJewelryError] = useState<string | null>(null);
  const [jewelryResultUrls, setJewelryResultUrls] = useState<string[] | null>(null);
  const [jewelryApplyLoading, setJewelryApplyLoading] = useState(false);
  const [jewelryRevisionDescription, setJewelryRevisionDescription] = useState('');
  const [jewelryHistory, setJewelryHistory] = useState<Array<{ article: string; urls: string[]; updated_at: string }>>([]);
  const [jewelryHistoryLoading, setJewelryHistoryLoading] = useState(false);
  const [jewelryLightboxUrl, setJewelryLightboxUrl] = useState<string | null>(null);
  const jewelryAbortRef = useRef<AbortController | null>(null);

  const jewelryImageFullUrl = (url: string) =>
    url.startsWith('/') ? `${process.env.NEXT_PUBLIC_API_URL || ''}${url}` : url;

  const icsUrl = useMemo(() => {
    if (!planId) return null;
    return api.getContentPlanIcsUrl(planId);
  }, [planId]);

  useEffect(() => {
    const loadLastPlan = async () => {
      try {
        const last = localStorage.getItem('content_agent_last_plan_id');
        if (last) {
          setPlanId(last);
          // Автоматически загружаем план, если есть ID в localStorage
          await loadPlan(last);
        }
      } catch {
        // ignore
      }
    };
    loadLastPlan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshSavedPlans = async () => {
    setSavedPlansLoading(true);
    setSavedPlansError(null);
    try {
      const params: any = { limit: 20 };
      if (planFilterStatus) params.status = planFilterStatus;
      if (planFilterSearch) params.search = planFilterSearch;
      if (planFilterDateFrom) params.start_date_from = planFilterDateFrom;
      if (planFilterDateTo) params.start_date_to = planFilterDateTo;
      
      const res = await api.listContentPlans(params);
      setSavedPlans(res || []);
    } catch (e: any) {
      setSavedPlansError(e.response?.data?.detail || 'Не удалось загрузить сохранённые планы');
    } finally {
      setSavedPlansLoading(false);
    }
  };

  const deletePlan = async (planIdToDelete: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Предотвращаем загрузку плана при клике на кнопку удаления
    
    if (!confirm('Вы уверены, что хотите удалить этот план? Это действие нельзя отменить.')) {
      return;
    }

    try {
      await api.deleteContentPlan(planIdToDelete);
      // Удаляем план из списка
      setSavedPlans((prev) => prev.filter((p: any) => p.id !== planIdToDelete));
      // Если удаляемый план был текущим, очищаем его
      if (planId === planIdToDelete) {
        setPlanId(null);
        setPlanPreview(null);
        setItems([]);
        try {
          localStorage.removeItem('content_agent_last_plan_id');
        } catch {
          // ignore
        }
      }
    } catch (e: any) {
      alert(e.response?.data?.detail || e.message || 'Ошибка при удалении плана');
    }
  };

  const openEditPlanModal = (plan: any) => {
    setEditingPlanId(plan.id);
    setEditPlanName(plan.name || '');
    setEditPlanStatus(plan.status || 'draft');
    // Форматируем даты для input[type="date"]
    const startDate = new Date(plan.start_date);
    const endDate = new Date(plan.end_date);
    setEditPlanStartDate(startDate.toISOString().split('T')[0]);
    setEditPlanEndDate(endDate.toISOString().split('T')[0]);
    setEditPlanTimezone(plan.timezone || 'Europe/Moscow');
  };

  const closeEditPlanModal = () => {
    setEditingPlanId(null);
    setEditPlanName('');
    setEditPlanStatus('draft');
    setEditPlanStartDate('');
    setEditPlanEndDate('');
    setEditPlanTimezone('Europe/Moscow');
  };

  const updatePlan = async () => {
    if (!editingPlanId) return;

    setUpdatingPlan(true);
    try {
      const updateRequest: any = {};
      if (editPlanName.trim()) updateRequest.name = editPlanName.trim();
      if (editPlanStatus) updateRequest.status = editPlanStatus;
      if (editPlanStartDate) updateRequest.start_date = editPlanStartDate;
      if (editPlanEndDate) updateRequest.end_date = editPlanEndDate;
      if (editPlanTimezone) updateRequest.timezone = editPlanTimezone;

      const updatedPlan = await api.updateContentPlan(editingPlanId, updateRequest);
      
      // Обновляем план в списке
      setSavedPlans((prev) => prev.map((p: any) => 
        p.id === editingPlanId ? updatedPlan : p
      ));
      
      // Если редактируемый план был текущим, обновляем его данные
      if (planId === editingPlanId) {
        setLoadedPlanMeta(updatedPlan);
      }

      closeEditPlanModal();
    } catch (e: any) {
      alert(e.response?.data?.detail || e.message || 'Ошибка при обновлении плана');
    } finally {
      setUpdatingPlan(false);
    }
  };

  // Item CRUD functions
  const openEditItemModal = (item: any) => {
    setEditingItemId(item.id);
    setIsCreatingItem(false);
    const scheduledDate = new Date(item.scheduled_at);
    // Форматируем для input[type="datetime-local"]
    const year = scheduledDate.getFullYear();
    const month = String(scheduledDate.getMonth() + 1).padStart(2, '0');
    const day = String(scheduledDate.getDate()).padStart(2, '0');
    const hours = String(scheduledDate.getHours()).padStart(2, '0');
    const minutes = String(scheduledDate.getMinutes()).padStart(2, '0');
    setEditItemScheduledAt(`${year}-${month}-${day}T${hours}:${minutes}`);
    setEditItemTimezone(item.timezone || 'Europe/Moscow');
    setEditItemChannel(item.channel || 'instagram');
    setEditItemContentType(item.content_type || 'post');
    setEditItemTopic(item.topic || '');
    setEditItemHook(item.hook || '');
    setEditItemCta(item.cta || '');
    setEditItemPersona(item.persona || '');
    setEditItemCjmStage(item.cjm_stage || '');
    setEditItemGoal(item.goal || '');
    setEditItemStatus(item.status || 'planned');
  };

  const openCreateItemModal = () => {
    setEditingItemId(null);
    setIsCreatingItem(true);
    // Устанавливаем текущую дату/время по умолчанию
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    setEditItemScheduledAt(`${year}-${month}-${day}T${hours}:${minutes}`);
    setEditItemTimezone(loadedPlanMeta?.timezone || 'Europe/Moscow');
    setEditItemChannel('instagram');
    setEditItemContentType('post');
    setEditItemTopic('');
    setEditItemHook('');
    setEditItemCta('');
    setEditItemPersona('');
    setEditItemCjmStage('');
    setEditItemGoal('');
    setEditItemStatus('planned');
  };

  const closeEditItemModal = () => {
    setEditingItemId(null);
    setIsCreatingItem(false);
    setEditItemScheduledAt('');
    setEditItemTimezone('Europe/Moscow');
    setEditItemChannel('instagram');
    setEditItemContentType('post');
    setEditItemTopic('');
    setEditItemHook('');
    setEditItemCta('');
    setEditItemPersona('');
    setEditItemCjmStage('');
    setEditItemGoal('');
    setEditItemStatus('planned');
  };

  const saveItem = async () => {
    if (!planId) return;

    setSavingItem(true);
    try {
      // Конвертируем datetime-local в ISO строку
      const scheduledDate = new Date(editItemScheduledAt);
      const isoString = scheduledDate.toISOString();

      if (isCreatingItem) {
        // Создание нового слота
        const newItem = await api.createContentItem(planId, {
          scheduled_at: isoString,
          timezone: editItemTimezone,
          channel: editItemChannel,
          content_type: editItemContentType,
          topic: editItemTopic || undefined,
          hook: editItemHook || undefined,
          cta: editItemCta || undefined,
          persona: editItemPersona || undefined,
          cjm_stage: editItemCjmStage || undefined,
          goal: editItemGoal || undefined,
          status: editItemStatus,
        });
        
        // Обновляем список слотов
        setItems((prev) => [...prev, newItem].sort((a, b) => 
          new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()
        ));
      } else if (editingItemId) {
        // Обновление существующего слота
        const updateRequest: any = {};
        if (editItemScheduledAt) updateRequest.scheduled_at = isoString;
        if (editItemTimezone) updateRequest.timezone = editItemTimezone;
        if (editItemChannel) updateRequest.channel = editItemChannel;
        if (editItemContentType) updateRequest.content_type = editItemContentType;
        updateRequest.topic = editItemTopic || undefined;
        updateRequest.hook = editItemHook || undefined;
        updateRequest.cta = editItemCta || undefined;
        updateRequest.persona = editItemPersona || undefined;
        updateRequest.cjm_stage = editItemCjmStage || undefined;
        updateRequest.goal = editItemGoal || undefined;
        if (editItemStatus) updateRequest.status = editItemStatus;

        const updatedItem = await api.updateContentItem(planId, editingItemId, updateRequest);
        
        // Обновляем список слотов
        setItems((prev) => prev.map((item) => 
          item.id === editingItemId ? updatedItem : item
        ).sort((a, b) => 
          new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()
        ));
      }

      closeEditItemModal();
    } catch (e: any) {
      alert(e.response?.data?.detail || e.message || 'Ошибка при сохранении слота');
    } finally {
      setSavingItem(false);
    }
  };

  const deleteItem = async (itemIdToDelete: string) => {
    if (!planId) return;
    
    if (!confirm('Вы уверены, что хотите удалить этот слот? Это действие нельзя отменить.')) {
      return;
    }

    try {
      await api.deleteContentItem(planId, itemIdToDelete);
      // Удаляем слот из списка
      setItems((prev) => prev.filter((item) => item.id !== itemIdToDelete));
      // Убираем из выбранных
      setSelectedItemIds((prev) => {
        const newSet = new Set(prev);
        newSet.delete(itemIdToDelete);
        return newSet;
      });
    } catch (e: any) {
      alert(e.response?.data?.detail || e.message || 'Ошибка при удалении слота');
    }
  };

  // Bulk operations
  const toggleItemSelection = (itemId: string) => {
    setSelectedItemIds((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(itemId)) {
        newSet.delete(itemId);
      } else {
        newSet.add(itemId);
      }
      return newSet;
    });
  };

  const toggleSelectAll = () => {
    if (selectedItemIds.size === items.length) {
      setSelectedItemIds(new Set());
    } else {
      setSelectedItemIds(new Set(items.map((item) => item.id)));
    }
  };

  const handleBulkUpdateStatus = async () => {
    if (!planId || selectedItemIds.size === 0) return;

    setBulkOperationLoading(true);
    try {
      const result = await api.bulkUpdateItemsStatus(
        planId,
        Array.from(selectedItemIds),
        bulkNewStatus
      );
      alert(`Статус изменен для ${result.updated_count} слотов`);
      setSelectedItemIds(new Set());
      setShowBulkStatusModal(false);
      await refreshItems();
    } catch (e: any) {
      alert(e.response?.data?.detail || e.message || 'Ошибка при массовом изменении статуса');
    } finally {
      setBulkOperationLoading(false);
    }
  };

  const handleBulkDelete = async () => {
    if (!planId || selectedItemIds.size === 0) return;

    if (!confirm(`Вы уверены, что хотите удалить ${selectedItemIds.size} слотов? Это действие нельзя отменить.`)) {
      return;
    }

    setBulkOperationLoading(true);
    try {
      const result = await api.bulkDeleteItems(planId, Array.from(selectedItemIds));
      alert(`Удалено ${result.deleted_count} слотов`);
      setSelectedItemIds(new Set());
      await refreshItems();
    } catch (e: any) {
      alert(e.response?.data?.detail || e.message || 'Ошибка при массовом удалении');
    } finally {
      setBulkOperationLoading(false);
    }
  };

  const handleBulkGenerate = async () => {
    if (!planId || selectedItemIds.size === 0) return;

    if (!confirm(`Сгенерировать контент для ${selectedItemIds.size} слотов? Это может занять некоторое время.`)) {
      return;
    }

    setBulkOperationLoading(true);
    try {
      const result = await api.bulkGenerateContent(planId, Array.from(selectedItemIds));
      if (result.failed_count > 0) {
        alert(`Контент сгенерирован для ${result.generated_count} слотов, ошибок: ${result.failed_count}${result.errors ? '\n' + result.errors.map(e => `${e.item_id}: ${e.error}`).join('\n') : ''}`);
      } else {
        alert(`Контент успешно сгенерирован для ${result.generated_count} слотов`);
      }
      setSelectedItemIds(new Set());
      await refreshItems();
    } catch (e: any) {
      alert(e.response?.data?.detail || e.message || 'Ошибка при массовой генерации контента');
    } finally {
      setBulkOperationLoading(false);
    }
  };

  const loadPlan = async (pid: string) => {
    setPlanId(pid);
    setPlanPreview(null);
    setLoadedPlanMeta(null);
    setYandexSyncResult(null);
    setError(null);
    setItemsError(null);
    try {
      const plan = await api.getContentPlan(pid);
      setLoadedPlanMeta(plan);
      // Для удобства: если в inputs лежит llm_plan — показываем его в превью
      const llmPlan = (plan?.inputs as any)?.llm_plan;
      if (llmPlan) setPlanPreview(llmPlan);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Не удалось загрузить план');
    }
    await refreshItems(pid);
  };

  useEffect(() => {
    refreshSavedPlans();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadJewelryHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!jewelryLightboxUrl) return;
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setJewelryLightboxUrl(null);
    };
    window.addEventListener('keydown', onEscape);
    return () => window.removeEventListener('keydown', onEscape);
  }, [jewelryLightboxUrl]);

  useEffect(() => {
    if (!planId) return;
    try {
      localStorage.setItem('content_agent_last_plan_id', planId);
    } catch {
      // ignore
    }
  }, [planId]);

  const parsedFrequencyRules = useMemo(() => {
    try {
      return JSON.parse(frequencyRulesJson || '{}');
    } catch {
      return null;
    }
  }, [frequencyRulesJson]);

  const toggleChannel = (value: string) => {
    setChannels((prev) => (prev.includes(value) ? prev.filter((c) => c !== value) : [...prev, value]));
  };

  const refreshItems = async (pid?: string) => {
    const id = pid || planId;
    if (!id) return;
    setItemsLoading(true);
    setItemsError(null);
    try {
      const params: any = {};
      if (itemFilterChannel) params.channel = itemFilterChannel;
      if (itemFilterStatus) params.status = itemFilterStatus;
      if (itemFilterSearch) params.search = itemFilterSearch;
      if (itemFilterDateFrom) params.scheduled_from = itemFilterDateFrom;
      if (itemFilterDateTo) params.scheduled_to = itemFilterDateTo;
      
      const res = await api.getContentPlanItems(id, params);
      setItems(res || []);
      if (res && res.length === 0) {
        // Если слотов нет, это не ошибка, просто пустой список
        console.log(`План ${id} загружен, но слотов пока нет`);
      }
    } catch (e: any) {
      const errorMsg = e.response?.data?.detail || e.message || 'Ошибка загрузки слотов плана';
      console.error('Ошибка загрузки слотов:', e);
      setItemsError(errorMsg);
    } finally {
      setItemsLoading(false);
    }
  };

  const onGeneratePlan = async () => {
    if (loading) return;
    setError(null);

    if (channels.length === 0) {
      setError('Выберите хотя бы один канал');
      return;
    }

    if (!parsedFrequencyRules) {
      setError('frequency_rules: некорректный JSON');
      return;
    }

    setLoading(true);
    setPlanPreview(null);
    setYandexSyncResult(null);

    try {
      const res = await api.generateContentPlan({
        name: name || undefined,
        start_date: startDate,
        end_date: endDate,
        timezone,
        channels,
        frequency_rules: parsedFrequencyRules,
        persona: persona || undefined,
        goal: goal || undefined,
        campaign_context: campaignContext || undefined,
        save: true,
      });

      setPlanPreview(res.plan);
      setPlanId(res.plan_id || null);
      setLoadedPlanMeta(null);

      if (res.plan_id) {
        await refreshItems(res.plan_id);
        await refreshSavedPlans();
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Ошибка генерации плана');
    } finally {
      setLoading(false);
    }
  };

  const onGenerateItem = async (itemId: string, feedback?: string) => {
    setItemsError(null);
    setGeneratingItemId(itemId);
    setRegenerateFeedback('');
    try {
      const result = await api.generateContentForItem(itemId, feedback);
      if (result && result.item_id && result.generated) {
        setGeneratedContentPreview({
          itemId: result.item_id,
          generated: result.generated,
        });
      } else {
        throw new Error('Неверный формат ответа от сервера');
      }
    } catch (e: any) {
      console.error('Error generating content for item:', e);
      const errorMessage = e.response?.data?.detail || e.message || 'Ошибка генерации контента для слота';
      setItemsError(errorMessage);
      setGeneratedContentPreview(null);
    } finally {
      setGeneratingItemId(null);
    }
  };

  const onApplyGeneratedContent = async () => {
    if (!generatedContentPreview) return;
    
    setGeneratingItemId(generatedContentPreview.itemId);
    try {
      await api.applyGeneratedContent(generatedContentPreview.itemId, generatedContentPreview.generated);
      setGeneratedContentPreview(null);
      setRegenerateFeedback('');
      await refreshItems();
    } catch (e: any) {
      setItemsError(e.response?.data?.detail || 'Ошибка применения контента');
    } finally {
      setGeneratingItemId(null);
    }
  };

  const onCancelGeneratedContent = () => {
    setGeneratedContentPreview(null);
    setRegenerateFeedback('');
  };

  const onRegenerateWithFeedback = () => {
    if (!generatedContentPreview) return;
    onGenerateItem(generatedContentPreview.itemId, regenerateFeedback || undefined);
  };

  const onPublishItem = async (itemId: string) => {
    setItemsError(null);
    try {
      await api.publishContentItem(itemId, { provider: 'glame' });
      await refreshItems();
    } catch (e: any) {
      setItemsError(e.response?.data?.detail || 'Ошибка публикации');
    }
  };

  const onLoadYandexCalendars = async () => {
    setYandexLoading(true);
    setYandexError(null);
    try {
      const res = await api.getYandexCalendars();
      setYandexCalendars(res.calendars || []);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (typeof detail === 'string' && detail.includes('YANDEX_CALDAV_USERNAME')) {
        setYandexError(
          'Интеграция с Яндекс.Календарём ещё не настроена. ' +
            'Укажите YANDEX_CALDAV_USERNAME и YANDEX_CALDAV_PASSWORD в настройках backend, ' +
            'или пока не используйте этот блок.'
        );
      } else {
        setYandexError(detail || 'Ошибка подключения к Яндекс.Календарю (CalDAV)');
      }
    } finally {
      setYandexLoading(false);
    }
  };

  const onSyncToYandex = async () => {
    if (!planId) {
      setYandexError('Сначала создайте/выберите план');
      return;
    }
    setYandexLoading(true);
    setYandexError(null);
    setYandexSyncResult(null);
    try {
      const res = await api.syncPlanToYandex(planId, {
        duration_minutes: 60, // Используем значение по умолчанию
      });
      setYandexSyncResult(res);
      await refreshItems();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (typeof detail === 'string' && detail.includes('YANDEX_CALDAV_USERNAME')) {
        setYandexError(
          'Интеграция с Яндекс.Календарём ещё не настроена. ' +
            'Укажите YANDEX_CALDAV_USERNAME и YANDEX_CALDAV_PASSWORD в настройках backend, ' +
            'или пока не используйте этот блок.'
        );
      } else {
        setYandexError(detail || 'Ошибка синхронизации с Яндекс.Календарём');
      }
    } finally {
      setYandexLoading(false);
    }
  };

  // Product Description functions
  const loadProductsWithoutDescription = async () => {
    setProductsLoading(true);
    setProductsError(null);
    try {
      const res = await api.getProductsWithoutDescription({ limit: 200, min_length: 50 });
      setAllProductsWithoutDesc(res || []);
      setProductsWithoutDesc(res || []);
    } catch (e: any) {
      // Правильно извлекаем сообщение об ошибке
      let errorMessage = 'Ошибка при загрузке товаров';
      if (e.response?.data) {
        if (typeof e.response.data.detail === 'string') {
          errorMessage = e.response.data.detail;
        } else if (Array.isArray(e.response.data.detail)) {
          errorMessage = e.response.data.detail.map((err: any) => 
            typeof err === 'string' ? err : err.msg || JSON.stringify(err)
          ).join(', ');
        } else if (typeof e.response.data.detail === 'object') {
          errorMessage = e.response.data.detail.msg || e.response.data.detail.message || JSON.stringify(e.response.data.detail);
        }
      } else if (e.message) {
        errorMessage = e.message;
      }
      setProductsError(errorMessage);
    } finally {
      setProductsLoading(false);
    }
  };

  const filterProductsBySearch = (products: typeof allProductsWithoutDesc) => {
    if (!productSearchQuery.trim()) {
      setProductsWithoutDesc(products);
      return;
    }

    const query = productSearchQuery.toLowerCase().trim();
    const filtered = products.filter((product) => {
      const nameMatch = product.name?.toLowerCase().includes(query);
      const codeMatch = product.external_code?.toLowerCase().includes(query);
      const brandMatch = product.brand?.toLowerCase().includes(query);
      return nameMatch || codeMatch || brandMatch;
    });
    setProductsWithoutDesc(filtered);
  };

  const handleProductSearchChange = (value: string) => {
    setProductSearchQuery(value);
    filterProductsBySearch(allProductsWithoutDesc);
  };

  const generateDescription = async (productId: string) => {
    setSelectedProductId(productId);
    setDescriptionLoading(true);
    setDescriptionResult(null);
    try {
      const res = await api.generateProductDescription({
        product_id: productId,
        rewrite_existing: descriptionRewrite,
        target_length: descriptionTargetLength,
      });
      setDescriptionResult(res);
      // Описание не сохраняется сразу, только предпросмотр
    } catch (e: any) {
      setDescriptionResult({ error: e.response?.data?.detail || e.message || 'Ошибка при генерации описания' });
    } finally {
      setDescriptionLoading(false);
      setSelectedProductId(null);
    }
  };

  const applyProductDescription = async () => {
    if (!descriptionResult || descriptionResult.error || !descriptionResult.product_id) {
      return;
    }
    
    setDescriptionLoading(true);
    try {
      await api.applyProductDescription(
        descriptionResult.product_id,
        descriptionResult.new_description
      );
      // Обновляем список товаров после применения
      await loadProductsWithoutDescription();
      // Закрываем результат
      setDescriptionResult(null);
      setSelectedProductId(null);
    } catch (e: any) {
      const errorMessage = e.response?.data?.detail || e.message || 'Ошибка при применении описания';
      setDescriptionResult({ 
        ...descriptionResult, 
        error: errorMessage 
      });
    } finally {
      setDescriptionLoading(false);
    }
  };

  const batchGenerateDescriptions = async () => {
    if (productsWithoutDesc.length === 0) return;
    
    setBatchLoading(true);
    setBatchResult(null);
    batchCancelledRef.current = false;
    
    const total = productsWithoutDesc.length;
    let successCount = 0;
    let errorCount = 0;
    let skippedCount = 0;
    const errors: Array<{ product_id: string; error: string }> = [];
    
    // Initialize progress
    setBatchProgress({
      current: 0,
      total,
      currentProductName: '',
      successCount: 0,
      errorCount: 0,
      skippedCount: 0,
    });
    
    try {
      for (let i = 0; i < productsWithoutDesc.length; i++) {
        // Check for cancellation
        if (batchCancelledRef.current) {
          setBatchResult({
            total,
            success: successCount,
            errors: errorCount,
            skipped: skippedCount,
            cancelled: true,
            errors_detail: errors,
          });
          break;
        }
        
        const product = productsWithoutDesc[i];
        
        // Update progress - show current product
        setBatchProgress({
          current: i + 1,
          total,
          currentProductName: product.name,
          successCount,
          errorCount,
          skippedCount,
        });
        
        try {
          // Check if we should skip (if description exists and rewrite is false)
          // Note: products in this list typically don't have descriptions, but we check for safety
          if (!descriptionRewrite && product.has_description && product.description_length >= 50) {
            skippedCount++;
            // Update progress after skipping
            setBatchProgress({
              current: i + 1,
              total,
              currentProductName: product.name,
              successCount,
              errorCount,
              skippedCount,
            });
            continue;
          }
          
          // Generate description
          const generateResult = await api.generateProductDescription({
            product_id: product.id,
            rewrite_existing: descriptionRewrite,
            target_length: descriptionTargetLength,
          });
          
          // Apply description to save it
          await api.applyProductDescription(product.id, generateResult.new_description);
          
          successCount++;
        } catch (e: any) {
          errorCount++;
          const errorMessage = e.response?.data?.detail || e.message || 'Неизвестная ошибка';
          errors.push({
            product_id: product.id,
            error: errorMessage,
          });
        }
        
        // Update progress after processing
        setBatchProgress({
          current: i + 1,
          total,
          currentProductName: product.name,
          successCount,
          errorCount,
          skippedCount,
        });
      }
      
      // Final result
      if (!batchCancelledRef.current) {
        setBatchResult({
          total,
          success: successCount,
          errors: errorCount,
          skipped: skippedCount,
          results: productsWithoutDesc.map((p, idx) => ({
            product_id: p.id,
            product_name: p.name,
            status: idx < successCount ? 'success' : 'error',
          })),
          errors_detail: errors,
        });
      }
      
      // Обновляем список товаров
      await loadProductsWithoutDescription();
    } catch (e: any) {
      setBatchResult({ 
        error: e.response?.data?.detail || e.message || 'Ошибка при массовой генерации',
        total,
        success: successCount,
        errors: errorCount,
        skipped: skippedCount,
        errors_detail: errors,
      });
    } finally {
      setBatchLoading(false);
      setBatchProgress(null);
    }
  };
  
  const cancelBatchGeneration = () => {
    batchCancelledRef.current = true;
    setBatchLoading(false);
  };

  const loadJewelryHistory = async () => {
    setJewelryHistoryLoading(true);
    try {
      const res = await apiClient.get<{ items: Array<{ article: string; urls: string[]; updated_at: string }> }>(
        '/api/content/jewelry-photo/history'
      );
      setJewelryHistory(Array.isArray(res.data?.items) ? res.data.items : []);
    } catch {
      setJewelryHistory([]);
    } finally {
      setJewelryHistoryLoading(false);
    }
  };

  const processJewelryPhotos = async () => {
    if (!jewelryArticle.trim() || jewelryFiles.length === 0) return;
    setJewelryError(null);
    setJewelryProcessing(true);
    jewelryAbortRef.current = new AbortController();
    try {
      const data = await api.processJewelryPhoto(
        jewelryFiles,
        jewelryArticle.trim(),
        jewelryAbortRef.current.signal,
        jewelryRevisionDescription.trim() || undefined
      );
      setJewelryResultUrls(Array.isArray(data?.urls) ? data.urls : []);
      await loadJewelryHistory();
    } catch (e: any) {
      if (e.name === 'CanceledError' || e.code === 'ERR_CANCELED') return;
      const msg = e.response?.data?.detail || e.message || 'Ошибка обработки фото';
      setJewelryError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      setJewelryResultUrls(null);
    } finally {
      setJewelryProcessing(false);
      jewelryAbortRef.current = null;
    }
  };

  const cancelJewelryGeneration = () => {
    if (jewelryAbortRef.current) {
      jewelryAbortRef.current.abort();
    }
  };

  const jewelryReset = () => {
    setJewelryResultUrls(null);
    setJewelryError(null);
    setJewelryRevisionDescription('');
  };

  const jewelryRegenerate = () => {
    setJewelryResultUrls(null);
    setJewelryError(null);
    processJewelryPhotos();
  };

  const applyJewelryToProduct = async (article?: string, urls?: string[]) => {
    const art = (article ?? jewelryArticle).trim();
    const list = urls ?? jewelryResultUrls ?? [];
    if (!art || list.length === 0) return;
    setJewelryApplyLoading(true);
    setJewelryError(null);
    try {
      await api.applyJewelryPhotoToProduct(art, list);
      alert(`Добавлено ${list.length} фото к карточке товара.`);
      if (!urls) setJewelryResultUrls(null);
      await loadJewelryHistory();
      setJewelryFiles([]);
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || 'Ошибка добавления к карточке';
      setJewelryError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setJewelryApplyLoading(false);
    }
  };

  const deleteJewelryHistoryFile = async (url: string) => {
    if (!confirm('Удалить это фото из истории?')) return;
    try {
      await apiClient.delete('/api/content/jewelry-photo/file', { params: { url } });
      await loadJewelryHistory();
      if (jewelryResultUrls?.includes(url)) {
        const next = jewelryResultUrls.filter((u) => u !== url);
        setJewelryResultUrls(next.length > 0 ? next : null);
      }
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || 'Ошибка удаления';
      setJewelryError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
  };

  const onJewelryFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files ? Array.from(e.target.files) : [];
    if (list.length > 5) {
      setJewelryError('Максимум 5 фото за раз.');
      setJewelryFiles(list.slice(0, 5));
    } else {
      setJewelryError(null);
      setJewelryFiles(list);
    }
  };

  const removeJewelryFile = (index: number) => {
    setJewelryFiles((prev) => prev.filter((_, i) => i !== index));
  };

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
      setProductsLoading(true);
      setProductsError(null);
      
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
      setProductsError(errorMessage);
      alert(`Ошибка при экспорте: ${errorMessage}`);
    } finally {
      setProductsLoading(false);
    }
  };

  const exportProductsToXLSX = async () => {
    try {
      setProductsLoading(true);
      setProductsError(null);
      
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
      setProductsError(errorMessage);
      alert(`Ошибка при экспорте: ${errorMessage}`);
    } finally {
      setProductsLoading(false);
    }
  };

  // Search product for rewriting description
  const searchProductForRewrite = async () => {
    if (!productSearchForRewrite.trim()) {
      setSearchedProducts([]);
      return;
    }
    
    setSearchingProducts(true);
    setProductsError(null);
    try {
      console.log('Searching for product:', productSearchForRewrite.trim());
      const res = await api.searchProductByCodeOrName(productSearchForRewrite.trim(), 10);
      console.log('Search result:', res);
      setSearchedProducts(res || []);
      if (!res || res.length === 0) {
        setProductsError('Товары не найдены');
      }
    } catch (e: any) {
      console.error('Search error:', e);
      // Правильно извлекаем сообщение об ошибке
      let errorMessage = 'Ошибка при поиске товара';
      if (e.response?.data) {
        if (typeof e.response.data.detail === 'string') {
          errorMessage = e.response.data.detail;
        } else if (Array.isArray(e.response.data.detail)) {
          // Если detail - массив ошибок валидации
          errorMessage = e.response.data.detail.map((err: any) => 
            typeof err === 'string' ? err : err.msg || JSON.stringify(err)
          ).join(', ');
        } else if (typeof e.response.data.detail === 'object') {
          errorMessage = e.response.data.detail.msg || e.response.data.detail.message || JSON.stringify(e.response.data.detail);
        }
      } else if (e.message) {
        errorMessage = e.message;
      }
      setProductsError(errorMessage);
      setSearchedProducts([]);
    } finally {
      setSearchingProducts(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-6 bg-gray-50 min-h-screen">
      <h1 className="text-3xl font-bold text-gray-900 mb-2">AI Content Agent</h1>
      <p className="text-gray-700 mb-6">
        Календарный контент‑план → генерация контента по слотам → экспорт/синк в Яндекс.Календарь.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        {/* Сохранённые планы */}
        <div className="bg-white rounded-lg shadow-md p-6 h-full flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xl font-semibold text-gray-900">Сохранённые планы</h2>
            <button
              onClick={refreshSavedPlans}
              disabled={savedPlansLoading}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 text-gray-900"
            >
              Обновить
            </button>
          </div>

          {/* Фильтры для планов */}
          <div className="mb-4 space-y-2 border-b pb-3">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Статус</label>
                <select
                  value={planFilterStatus}
                  onChange={(e) => {
                    setPlanFilterStatus(e.target.value);
                    setTimeout(refreshSavedPlans, 100);
                  }}
                  className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-gold-500"
                >
                  <option value="">Все</option>
                  <option value="draft">Черновик</option>
                  <option value="active">Активный</option>
                  <option value="completed">Завершён</option>
                  <option value="archived">Архив</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Поиск</label>
                <input
                  type="text"
                  value={planFilterSearch}
                  onChange={(e) => {
                    setPlanFilterSearch(e.target.value);
                  }}
                  onBlur={refreshSavedPlans}
                  placeholder="Название..."
                  className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-gold-500"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Дата от</label>
                <input
                  type="date"
                  value={planFilterDateFrom}
                  onChange={(e) => {
                    setPlanFilterDateFrom(e.target.value);
                    setTimeout(refreshSavedPlans, 100);
                  }}
                  className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-gold-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Дата до</label>
                <input
                  type="date"
                  value={planFilterDateTo}
                  onChange={(e) => {
                    setPlanFilterDateTo(e.target.value);
                    setTimeout(refreshSavedPlans, 100);
                  }}
                  className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-gold-500"
                />
              </div>
            </div>
            {(planFilterStatus || planFilterSearch || planFilterDateFrom || planFilterDateTo) && (
              <button
                onClick={() => {
                  setPlanFilterStatus('');
                  setPlanFilterSearch('');
                  setPlanFilterDateFrom('');
                  setPlanFilterDateTo('');
                  setTimeout(refreshSavedPlans, 100);
                }}
                className="text-xs text-gold-600 hover:text-gold-700"
              >
                Сбросить фильтры
              </button>
            )}
          </div>

          {savedPlansError && (
            <div className="mb-3">
              <p className="text-sm text-red-600 mb-2">{savedPlansError}</p>
              <div className="text-xs text-gray-600 mb-2">
                Вы можете загрузить план напрямую по ID ниже.
              </div>
            </div>
          )}

          <div className="flex-1 min-h-0">
            {savedPlansLoading ? (
              <p className="text-sm text-gray-700">Загрузка…</p>
            ) : savedPlans.length === 0 && !savedPlansError ? (
              <p className="text-sm text-gray-700">Планов пока нет. Сгенерируйте первый.</p>
            ) : savedPlans.length > 0 ? (
              <div className="space-y-2 overflow-auto pr-1 h-full">
                {savedPlans.map((p: any) => (
                  <div
                    key={p.id}
                    className={`w-full border rounded-lg p-3 hover:bg-gray-50 transition ${
                      planId === p.id ? 'border-gold-400 bg-gold-50' : 'border-gray-200'
                    }`}
                  >
                    <button onClick={() => loadPlan(p.id)} className="w-full text-left">
                      <div className="text-sm font-medium text-gray-900">{p.name || 'Без названия'}</div>
                      <div className="text-xs text-gray-600 mt-1">
                        {p.status} • {String(p.start_date).slice(0, 10)} → {String(p.end_date).slice(0, 10)}
                      </div>
                    </button>
                    <div className="mt-2 flex gap-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          openEditPlanModal(p);
                        }}
                        className="px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition"
                        title="Редактировать план"
                      >
                        Редактировать
                      </button>
                      <button
                        onClick={(e) => deletePlan(p.id, e)}
                        className="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200 transition"
                        title="Удалить план"
                      >
                        Удалить
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          {planId && (
            <div className="mt-auto pt-4 text-xs text-gray-800 break-all">
              <div className="font-medium text-gray-900 mb-1">Текущий plan_id</div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-gray-800 break-all">{planId}</span>
                <button
                  onClick={() => loadPlan(planId)}
                  className="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50 text-gray-900 whitespace-nowrap"
                  title="Загрузить план"
                >
                  Загрузить
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Генерация плана */}
        <div className="bg-white rounded-lg shadow-md p-6 h-full flex flex-col">
          <h2 className="text-xl font-semibold mb-4 text-gray-900">План на период</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Название</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Start</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">End</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Timezone</label>
              <input
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                placeholder="Europe/Moscow"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-gold-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Каналы</label>
              <div className="space-y-2">
                {CHANNELS.map((c) => (
                  <label key={c.value} className="flex items-center gap-2 text-sm text-gray-700">
                    <input
                      type="checkbox"
                      checked={channels.includes(c.value)}
                      onChange={() => toggleChannel(c.value)}
                      className="h-4 w-4"
                    />
                    <span>{c.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Персона (опционально)</label>
              <textarea
                value={persona}
                onChange={(e) => setPersona(e.target.value)}
                rows={2}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Цель (опционально)</label>
              <textarea
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                rows={2}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Контекст кампании (опционально)</label>
              <textarea
                value={campaignContext}
                onChange={(e) => setCampaignContext(e.target.value)}
                rows={2}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">frequency_rules (JSON)</label>
              <textarea
                value={frequencyRulesJson}
                onChange={(e) => setFrequencyRulesJson(e.target.value)}
                rows={4}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-gold-500"
              />
              {!parsedFrequencyRules && (
                <p className="text-xs text-red-600 mt-1">Некорректный JSON</p>
              )}
            </div>

            <button
              onClick={onGeneratePlan}
              disabled={loading}
              className="w-full px-6 py-3 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed transition font-semibold"
            >
              {loading ? 'Генерация…' : 'Сгенерировать план'}
            </button>

            {planId && (
              <div className="text-sm text-gray-900">
                <div className="mb-2">
                  <span className="font-medium text-gray-900">Plan ID:</span> <span className="font-mono text-gray-800">{planId}</span>
                </div>
                <button
                  onClick={() => refreshItems()}
                  className="px-3 py-2 bg-white border border-gray-300 text-gray-800 hover:bg-gray-50 rounded-lg transition text-sm font-medium"
                >
                  Обновить слоты
                </button>
                {icsUrl && (
                  <a
                    href={icsUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-2 px-3 py-2 bg-white border border-gray-300 text-gray-800 hover:bg-gray-50 rounded-lg transition text-sm inline-block font-medium"
                  >
                    Экспорт .ics
                  </a>
                )}
              </div>
            )}

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-red-800 font-medium">Ошибка</p>
                <p className="text-red-600 text-sm mt-1">{error}</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Слоты */}
      <div className="bg-white rounded-lg shadow-md p-6 mt-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">Календарь (слоты)</h2>
          <div className="flex gap-2">
            <button
              onClick={() => refreshItems()}
              disabled={!planId || itemsLoading}
              className="px-4 py-2 bg-white border border-gray-300 text-gray-800 hover:bg-gray-50 rounded-lg transition text-sm disabled:opacity-50 font-medium"
            >
              {itemsLoading ? 'Загрузка…' : 'Обновить'}
            </button>
          </div>
        </div>

        {itemsError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
            <p className="text-red-800 font-medium">Ошибка</p>
            <p className="text-red-600 text-sm mt-1">{itemsError}</p>
          </div>
        )}

        {!planId && <p className="text-gray-800">Сначала сгенерируйте план (слева).</p>}

        {planId && (
            <div>
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold text-gray-900">Слоты контент-плана</h3>
                <div className="flex gap-2">
                  <div className="flex bg-gray-100 rounded-lg p-1">
                    <button
                      onClick={() => setViewMode('list')}
                      className={`px-3 py-1 rounded text-sm font-medium transition ${
                        viewMode === 'list'
                          ? 'bg-white text-gray-900 shadow-sm'
                          : 'text-gray-600 hover:text-gray-900'
                      }`}
                    >
                      Список
                    </button>
                    <button
                      onClick={() => setViewMode('calendar')}
                      className={`px-3 py-1 rounded text-sm font-medium transition ${
                        viewMode === 'calendar'
                          ? 'bg-white text-gray-900 shadow-sm'
                          : 'text-gray-600 hover:text-gray-900'
                      }`}
                    >
                      Календарь
                    </button>
                  </div>
                  <button
                    onClick={openCreateItemModal}
                    className="px-4 py-2 bg-gold-600 text-white rounded-lg hover:bg-gold-700 transition text-sm font-medium"
                  >
                    + Создать слот
                  </button>
                </div>
              </div>

              {/* Фильтры для слотов */}
              <div className="mb-4 space-y-2 border-b pb-3">
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Канал</label>
                    <select
                      value={itemFilterChannel}
                      onChange={(e) => {
                        setItemFilterChannel(e.target.value);
                        setTimeout(() => refreshItems(), 100);
                      }}
                      className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-gold-500"
                    >
                      <option value="">Все</option>
                      {CHANNELS.map((ch) => (
                        <option key={ch.value} value={ch.value}>
                          {ch.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Статус</label>
                    <select
                      value={itemFilterStatus}
                      onChange={(e) => {
                        setItemFilterStatus(e.target.value);
                        setTimeout(() => refreshItems(), 100);
                      }}
                      className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-gold-500"
                    >
                      <option value="">Все</option>
                      <option value="planned">Запланирован</option>
                      <option value="draft">Черновик</option>
                      <option value="ready">Готов</option>
                      <option value="approved">Одобрен</option>
                      <option value="scheduled">Запланирован к публикации</option>
                      <option value="published">Опубликован</option>
                      <option value="failed">Ошибка</option>
                      <option value="cancelled">Отменен</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Поиск по теме</label>
                    <input
                      type="text"
                      value={itemFilterSearch}
                      onChange={(e) => {
                        setItemFilterSearch(e.target.value);
                      }}
                      onBlur={() => refreshItems()}
                      placeholder="Тема..."
                      className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-gold-500"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Дата от</label>
                    <input
                      type="datetime-local"
                      value={itemFilterDateFrom}
                      onChange={(e) => {
                        setItemFilterDateFrom(e.target.value);
                        setTimeout(() => refreshItems(), 100);
                      }}
                      className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-gold-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Дата до</label>
                    <input
                      type="datetime-local"
                      value={itemFilterDateTo}
                      onChange={(e) => {
                        setItemFilterDateTo(e.target.value);
                        setTimeout(() => refreshItems(), 100);
                      }}
                      className="w-full px-2 py-1.5 text-xs border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-gold-500"
                    />
                  </div>
                </div>
                {(itemFilterChannel || itemFilterStatus || itemFilterSearch || itemFilterDateFrom || itemFilterDateTo) && (
                  <button
                    onClick={() => {
                      setItemFilterChannel('');
                      setItemFilterStatus('');
                      setItemFilterSearch('');
                      setItemFilterDateFrom('');
                      setItemFilterDateTo('');
                      setTimeout(() => refreshItems(), 100);
                    }}
                    className="text-xs text-gold-600 hover:text-gold-700"
                  >
                    Сбросить фильтры
                  </button>
                )}
              </div>

              {viewMode === 'calendar' ? (
                <CalendarView
                  items={items}
                  onSelectEvent={(item) => openEditItemModal(item)}
                  onSelectSlot={(slotInfo) => {
                    // При клике на пустой слот создаем новый слот с этой датой
                    const year = slotInfo.start.getFullYear();
                    const month = String(slotInfo.start.getMonth() + 1).padStart(2, '0');
                    const day = String(slotInfo.start.getDate()).padStart(2, '0');
                    const hours = String(slotInfo.start.getHours()).padStart(2, '0');
                    const minutes = String(slotInfo.start.getMinutes()).padStart(2, '0');
                    setEditItemScheduledAt(`${year}-${month}-${day}T${hours}:${minutes}`);
                    setIsCreatingItem(true);
                    setEditingItemId(null);
                    setEditItemTimezone(loadedPlanMeta?.timezone || 'Europe/Moscow');
                    setEditItemChannel('instagram');
                    setEditItemContentType('post');
                    setEditItemTopic('');
                    setEditItemHook('');
                    setEditItemCta('');
                    setEditItemPersona('');
                    setEditItemCjmStage('');
                    setEditItemGoal('');
                    setEditItemStatus('planned');
                  }}
                />
              ) : (
                <div>
                  {/* Кнопки массовых операций */}
                  {selectedItemIds.size > 0 && (
                    <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-center justify-between">
                      <span className="text-sm font-medium text-blue-900">
                        Выбрано: {selectedItemIds.size} слотов
                      </span>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setShowBulkStatusModal(true)}
                          disabled={bulkOperationLoading}
                          className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition"
                        >
                          Изменить статус
                        </button>
                        <button
                          onClick={handleBulkGenerate}
                          disabled={bulkOperationLoading}
                          className="px-3 py-1.5 text-xs bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 transition"
                        >
                          {bulkOperationLoading ? 'Генерация...' : 'Сгенерировать контент'}
                        </button>
                        <button
                          onClick={handleBulkDelete}
                          disabled={bulkOperationLoading}
                          className="px-3 py-1.5 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 transition"
                        >
                          Удалить
                        </button>
                        <button
                          onClick={() => setSelectedItemIds(new Set())}
                          className="px-3 py-1.5 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300 transition"
                        >
                          Отменить выбор
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead>
                        <tr className="text-left text-gray-900 border-b">
                          <th className="py-2 pr-3 text-gray-900 w-10">
                            <input
                              type="checkbox"
                              checked={items.length > 0 && selectedItemIds.size === items.length}
                              onChange={toggleSelectAll}
                              className="h-4 w-4"
                            />
                          </th>
                          <th className="py-2 pr-3 text-gray-900">Дата</th>
                          <th className="py-2 pr-3 text-gray-900">Канал</th>
                          <th className="py-2 pr-3 text-gray-900">Тип</th>
                          <th className="py-2 pr-3 text-gray-900">Тема</th>
                          <th className="py-2 pr-3 text-gray-900">Статус</th>
                          <th className="py-2 pr-3 text-gray-900">Действия</th>
                        </tr>
                      </thead>
                      <tbody>
                        {items.map((it) => (
                          <tr key={it.id} className={`border-b align-top ${selectedItemIds.has(it.id) ? 'bg-blue-50' : ''}`}>
                            <td className="py-3 pr-3">
                              <input
                                type="checkbox"
                                checked={selectedItemIds.has(it.id)}
                                onChange={() => toggleItemSelection(it.id)}
                                className="h-4 w-4"
                              />
                            </td>
                            <td className="py-3 pr-3 whitespace-nowrap text-gray-900">{formatDateTime(it.scheduled_at)}</td>
                            <td className="py-3 pr-3 text-gray-900">{it.channel}</td>
                            <td className="py-3 pr-3 text-gray-900">{it.content_type}</td>
                            <td className="py-3 pr-3">
                              <div className="text-gray-900">{it.topic || <span className="text-gray-600">—</span>}</div>
                              {it.hook && <div className="text-xs text-gray-700 mt-1">Hook: {it.hook}</div>}
                              {it.cta && <div className="text-xs text-gray-700">CTA: {it.cta}</div>}
                            </td>
                            <td className="py-3 pr-3 text-gray-900">{it.status}</td>
                            <td className="py-3 pr-3">
                              <div className="flex flex-wrap gap-2">
                                <button
                                  onClick={() => openEditItemModal(it)}
                                  className="px-3 py-2 bg-blue-100 text-blue-700 hover:bg-blue-200 rounded-lg transition text-xs font-medium"
                                  title="Редактировать слот"
                                >
                                  Редактировать
                                </button>
                                <button
                                  onClick={() => deleteItem(it.id)}
                                  className="px-3 py-2 bg-red-100 text-red-700 hover:bg-red-200 rounded-lg transition text-xs font-medium"
                                  title="Удалить слот"
                                >
                                  Удалить
                                </button>
                                <button
                                  onClick={() => onGenerateItem(it.id)}
                                  disabled={generatingItemId === it.id}
                                  className="px-3 py-2 bg-white border border-gray-300 text-gray-800 hover:bg-gray-50 rounded-lg transition text-xs font-medium disabled:opacity-50"
                                >
                                  {generatingItemId === it.id ? 'Генерация...' : 'Сгенерировать'}
                                </button>
                                <button
                                  onClick={() => onPublishItem(it.id)}
                                  disabled={!it.generated_text}
                                  className="px-3 py-2 bg-white border border-gray-300 text-gray-800 hover:bg-gray-50 rounded-lg transition text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  Опубликовать
                                </button>
                              </div>
                              {it.generated_text && (
                                <details className="mt-2">
                                  <summary className="text-xs text-gold-600 cursor-pointer">Показать текст</summary>
                                  <textarea
                                    readOnly
                                    className="w-full mt-2 px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 font-mono text-xs"
                                    rows={6}
                                    value={it.generated_text}
                                  />
                                </details>
                              )}
                            </td>
                          </tr>
                        ))}
                        {items.length === 0 && (
                          <tr>
                            <td className="py-6 text-gray-800" colSpan={7}>
                              Слотов пока нет.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
        )}

        {/* Модальное окно для массового изменения статуса */}
        {showBulkStatusModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl p-6 max-w-md w-full mx-4">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">Изменить статус для {selectedItemIds.size} слотов</h2>
              
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">Новый статус</label>
                <select
                  value={bulkNewStatus}
                  onChange={(e) => setBulkNewStatus(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                >
                  <option value="planned">Запланирован</option>
                  <option value="draft">Черновик</option>
                  <option value="ready">Готов</option>
                  <option value="approved">Одобрен</option>
                  <option value="scheduled">Запланирован к публикации</option>
                  <option value="published">Опубликован</option>
                  <option value="failed">Ошибка</option>
                  <option value="cancelled">Отменен</option>
                </select>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setShowBulkStatusModal(false)}
                  disabled={bulkOperationLoading}
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-gray-700 disabled:opacity-50 transition"
                >
                  Отмена
                </button>
                <button
                  onClick={handleBulkUpdateStatus}
                  disabled={bulkOperationLoading}
                  className="flex-1 px-4 py-2 bg-gold-600 text-white rounded-lg hover:bg-gold-700 disabled:opacity-50 transition"
                >
                  {bulkOperationLoading ? 'Сохранение...' : 'Изменить'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Preview Generated Content */}
        {generatedContentPreview && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mt-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-semibold text-gray-900">Результат генерации контента</h3>
              <div className="flex gap-2">
                <button
                  onClick={onRegenerateWithFeedback}
                  disabled={generatingItemId === generatedContentPreview.itemId}
                  className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 text-sm font-medium border border-gray-700"
                >
                  {generatingItemId === generatedContentPreview.itemId ? 'Генерация...' : 'Новая генерация'}
                </button>
                <button
                  onClick={onCancelGeneratedContent}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium border border-red-700"
                >
                  Отменить
                </button>
                <button
                  onClick={onApplyGeneratedContent}
                  disabled={generatingItemId === generatedContentPreview.itemId}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium border border-green-700"
                >
                  {generatingItemId === generatedContentPreview.itemId ? 'Применение...' : 'Применить'}
                </button>
              </div>
            </div>

            {/* Feedback field for regeneration */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-900 mb-2">
                Пожелания для переделки (необязательно):
              </label>
              <textarea
                value={regenerateFeedback}
                onChange={(e) => setRegenerateFeedback(e.target.value)}
                placeholder="Например: сделай текст короче, добавь больше эмоций, используй другой стиль..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                rows={2}
              />
            </div>

            {/* Generated content preview */}
            <div className="space-y-3">
              {generatedContentPreview.generated.title && (
                <div>
                  <p className="text-xs text-gray-600 mb-1">Заголовок:</p>
                  <p className="text-sm font-semibold text-gray-900 bg-white border border-gray-200 rounded p-2">
                    {generatedContentPreview.generated.title}
                  </p>
                </div>
              )}
              {generatedContentPreview.generated.text && (
                <div>
                  <p className="text-xs text-gray-600 mb-1">Текст ({generatedContentPreview.generated.text.length} символов):</p>
                  <p className="text-sm text-gray-900 bg-white border border-gray-200 rounded p-2 whitespace-pre-wrap">
                    {generatedContentPreview.generated.text}
                  </p>
                </div>
              )}
              {generatedContentPreview.generated.variants && Array.isArray(generatedContentPreview.generated.variants) && generatedContentPreview.generated.variants.length > 0 && (
                <div>
                  <p className="text-xs text-gray-600 mb-1">Варианты:</p>
                  <ul className="list-disc list-inside text-sm text-gray-900 bg-white border border-gray-200 rounded p-2 space-y-1">
                    {generatedContentPreview.generated.variants.map((variant: string, idx: number) => (
                      <li key={idx}>{variant}</li>
                    ))}
                  </ul>
                </div>
              )}
              {generatedContentPreview.generated.hashtags && Array.isArray(generatedContentPreview.generated.hashtags) && generatedContentPreview.generated.hashtags.length > 0 && (
                <div>
                  <p className="text-xs text-gray-600 mb-1">Хэштеги:</p>
                  <div className="flex flex-wrap gap-1">
                    {generatedContentPreview.generated.hashtags.map((tag: string, idx: number) => (
                      <span key={idx} className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs border border-blue-300">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {generatedContentPreview.generated.cta && (
                <div>
                  <p className="text-xs text-gray-600 mb-1">Призыв к действию (CTA):</p>
                  <p className="text-sm text-gray-900 bg-white border border-gray-200 rounded p-2">
                    {generatedContentPreview.generated.cta}
                  </p>
                </div>
              )}
              {Object.keys(generatedContentPreview.generated).length === 0 && (
                <p className="text-sm text-gray-600">Результат генерации пуст</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Яндекс.Календарь */}
      <div className="bg-white rounded-lg shadow-md p-6 mt-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">Яндекс.Календарь (CalDAV)</h2>
          <div className="flex gap-2">
            <button
              onClick={onLoadYandexCalendars}
              disabled={yandexLoading}
              className="px-4 py-2 bg-white border border-gray-300 text-gray-800 hover:bg-gray-50 rounded-lg transition text-sm disabled:opacity-50 font-medium"
            >
              {yandexLoading ? 'Загрузка…' : 'Показать календари'}
            </button>
            <button
              onClick={onSyncToYandex}
              disabled={yandexLoading || !planId}
              className="px-4 py-2 bg-gold-500 text-white hover:bg-gold-600 rounded-lg transition text-sm disabled:opacity-50"
            >
              {yandexLoading ? 'Синк…' : 'Синхронизировать план'}
            </button>
          </div>
        </div>

        {yandexError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
            <p className="text-red-800 font-medium">Ошибка</p>
            <p className="text-red-600 text-sm mt-1">{yandexError}</p>
          </div>
        )}


        {yandexCalendars.length > 0 && (
          <div className="mb-4">
            <p className="text-sm font-medium text-gray-900 mb-2">Доступные календари</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {yandexCalendars.map((c, idx) => (
                <div key={idx} className="border border-gray-200 rounded-lg p-3 text-sm">
                  <div className="text-gray-900 font-medium">{c.name || 'Без названия'}</div>
                  <div className="text-xs text-gray-700 break-all">{c.url || ''}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {yandexSyncResult && (
          <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
            <p className="text-sm font-medium text-gray-900 mb-2">Результат синка</p>
            <pre className="text-xs overflow-auto text-gray-900">{JSON.stringify(yandexSyncResult, null, 2)}</pre>
          </div>
        )}
      </div>

      {loadedPlanMeta && (
        <div className="bg-white rounded-lg shadow-md p-6 mt-6">
          <h2 className="text-xl font-semibold mb-3 text-gray-900">План (метаданные)</h2>
          <pre className="text-xs overflow-auto bg-gray-50 border border-gray-200 rounded-lg p-4 text-gray-900">
            {JSON.stringify(loadedPlanMeta, null, 2)}
          </pre>
        </div>
      )}

      {/* Превью плана */}
      {planPreview && (
        <div className="bg-white rounded-lg shadow-md p-6 mt-6">
          <h2 className="text-xl font-semibold mb-3 text-gray-900">Превью плана (LLM)</h2>
          <pre className="text-xs overflow-auto bg-gray-50 border border-gray-200 rounded-lg p-4 text-gray-900">
            {JSON.stringify(planPreview, null, 2)}
          </pre>
        </div>
      )}

      {/* Product Descriptions Section */}
      <div className="bg-white rounded-lg shadow-md p-6 mt-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Описания товаров (SEO-оптимизация)</h2>
            <p className="text-sm text-gray-600 mt-1">
              Генерация SEO-оптимизированных описаний для карточек товаров. Описания оптимизированы для поисковых систем, AI-поиска и читаемы для человека.
            </p>
          </div>
          <button
            onClick={loadProductsWithoutDescription}
            disabled={productsLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
          >
            {productsLoading ? 'Загрузка...' : 'Найти товары без описания'}
          </button>
        </div>

        {productsError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
            <p className="text-sm text-red-600">{productsError}</p>
          </div>
        )}

        {/* Search for rewriting description */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
          <label className="block text-sm font-medium text-gray-900 mb-2">
            Поиск товара для переписывания описания (по артикулу или названию)
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={productSearchForRewrite}
              onChange={(e) => setProductSearchForRewrite(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  searchProductForRewrite();
                }
              }}
              placeholder="Введите артикул или название товара..."
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <button
              onClick={searchProductForRewrite}
              disabled={searchingProducts || !productSearchForRewrite.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {searchingProducts ? 'Поиск...' : 'Найти'}
            </button>
          </div>
          {searchedProducts.length > 0 ? (
            <div className="mt-4">
              <p className="text-sm text-gray-700 mb-2">
                Найдено товаров: <strong className="text-gray-900">{searchedProducts.length}</strong>
              </p>
              <div className="space-y-2">
                {searchedProducts.map((product) => (
                  <div key={product.id} className="bg-white border border-gray-200 rounded-lg p-3 shadow-sm hover:shadow-md transition-shadow">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-mono text-gray-600 bg-gray-100 px-2 py-1 rounded">
                            {product.external_code || '—'}
                          </span>
                          <span className="text-sm font-medium text-gray-900">{product.name}</span>
                        </div>
                        <div className="text-xs text-gray-600">
                          {product.brand && <span>Бренд: {product.brand}</span>}
                          {product.category && <span className="ml-2">Категория: {product.category}</span>}
                          <span className="ml-2">Цена: {(product.price / 100).toFixed(0)} ₽</span>
                        </div>
                        {product.has_description && (
                          <div className="mt-1">
                            <span className="text-xs text-yellow-600">
                              Текущее описание: {product.description_length} символов
                            </span>
                          </div>
                        )}
                      </div>
                      <button
                        onClick={() => generateDescription(product.id)}
                        disabled={descriptionLoading || (selectedProductId === product.id && descriptionLoading)}
                        className="ml-4 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-xs font-medium"
                      >
                        {descriptionLoading && selectedProductId === product.id ? 'Генерация...' : 'Сгенерировать'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : productSearchForRewrite.trim() && !searchingProducts ? (
            <div className="mt-4">
              <p className="text-sm text-gray-600">Товары не найдены</p>
            </div>
          ) : null}
        </div>

        {/* Settings */}
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-900 mb-2">Длина описания</label>
              <select
                value={descriptionTargetLength}
                onChange={(e) => setDescriptionTargetLength(e.target.value as 'short' | 'medium' | 'long')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="short">Краткое (150-200 символов)</option>
                <option value="medium">Среднее (300-500 символов)</option>
                <option value="long">Подробное (600-1000 символов)</option>
              </select>
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                id="rewrite-existing"
                checked={descriptionRewrite}
                onChange={(e) => setDescriptionRewrite(e.target.checked)}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              />
              <label htmlFor="rewrite-existing" className="ml-2 text-sm text-gray-900">
                Переписывать существующие описания
              </label>
            </div>
          </div>
        </div>

        {/* Products List */}
        {productsWithoutDesc.length > 0 && (
          <div className="mb-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm text-gray-700">
                Найдено товаров без описания или с коротким описанием: <strong className="text-gray-900">{productsWithoutDesc.length}</strong>
              </p>
              <div className="flex gap-2">
                <button
                  onClick={exportProductsToCSV}
                  disabled={productsLoading}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium shadow-sm"
                >
                  {productsLoading ? 'Загрузка...' : 'Выгрузить в CSV'}
                </button>
                <button
                  onClick={exportProductsToXLSX}
                  disabled={productsLoading}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium shadow-sm"
                >
                  {productsLoading ? 'Загрузка...' : 'Выгрузить в XLSX'}
                </button>
                <button
                  onClick={batchGenerateDescriptions}
                  disabled={batchLoading || productsWithoutDesc.length === 0}
                  className="px-4 py-2 bg-gold-600 text-white rounded-lg hover:bg-gold-700 disabled:opacity-50 text-sm font-medium shadow-sm"
                >
                  {batchLoading ? 'Генерация...' : `Сгенерировать для всех (${productsWithoutDesc.length})`}
                </button>
              </div>
            </div>
            
            {/* Progress Bar */}
            {batchProgress && (
              <div className="mt-4 bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-semibold text-gray-900">Генерация описаний...</h4>
                  <button
                    onClick={cancelBatchGeneration}
                    className="px-3 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700"
                  >
                    Отменить
                  </button>
                </div>
                
                {batchProgress.currentProductName && (
                  <p className="text-sm text-gray-700 mb-2">
                    Обрабатывается: <strong className="text-gray-900">{batchProgress.currentProductName}</strong>
                  </p>
                )}
                
                {/* Progress Bar */}
                <div className="w-full bg-gray-200 rounded-full h-4 mb-2">
                  <div
                    className="bg-blue-600 h-4 rounded-full transition-all duration-300"
                    style={{ width: `${(batchProgress.current / batchProgress.total) * 100}%` }}
                  ></div>
                </div>
                
                {/* Progress Info */}
                <div className="flex items-center justify-between text-xs text-gray-600">
                  <span>
                    {Math.round((batchProgress.current / batchProgress.total) * 100)}% ({batchProgress.current}/{batchProgress.total})
                  </span>
                  <span className="flex gap-3">
                    <span className="text-green-600">Успешно: {batchProgress.successCount}</span>
                    <span className="text-red-600">Ошибок: {batchProgress.errorCount}</span>
                    {batchProgress.skippedCount > 0 && (
                      <span className="text-yellow-600">Пропущено: {batchProgress.skippedCount}</span>
                    )}
                  </span>
                </div>
              </div>
            )}
            <div className="max-h-96 overflow-y-auto border border-gray-200 rounded-lg shadow-sm">
              <table className="w-full text-sm">
                <thead className="bg-gray-100 sticky top-0">
                  <tr>
                    <th className="px-4 py-2 text-left text-gray-900 font-semibold">Артикул</th>
                    <th className="px-4 py-2 text-left text-gray-900 font-semibold">Название</th>
                    <th className="px-4 py-2 text-left text-gray-900 font-semibold">Бренд</th>
                    <th className="px-4 py-2 text-left text-gray-900 font-semibold">Категория</th>
                    <th className="px-4 py-2 text-left text-gray-900 font-semibold">Цена</th>
                    <th className="px-4 py-2 text-left text-gray-900 font-semibold">Описание</th>
                    <th className="px-4 py-2 text-left text-gray-900 font-semibold">Действие</th>
                  </tr>
                </thead>
                <tbody>
                  {productsWithoutDesc.map((product) => (
                    <tr key={product.id} className="border-t border-gray-200 hover:bg-gray-50">
                      <td className="px-4 py-2 text-gray-900 font-mono text-xs">{product.external_code || '—'}</td>
                      <td className="px-4 py-2 text-gray-900">{product.name}</td>
                      <td className="px-4 py-2 text-gray-600">{product.brand || '—'}</td>
                      <td className="px-4 py-2 text-gray-600">{product.category || '—'}</td>
                      <td className="px-4 py-2 text-gray-900">{(product.price / 100).toFixed(0)} ₽</td>
                      <td className="px-4 py-2 text-gray-600">
                        {product.has_description ? (
                          <span className="text-xs text-yellow-600">{product.description_length} символов</span>
                        ) : (
                          <span className="text-xs text-red-600">Нет описания</span>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        <button
                          onClick={() => generateDescription(product.id)}
                          disabled={descriptionLoading || (selectedProductId === product.id && descriptionLoading)}
                          className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-xs font-medium"
                        >
                          {descriptionLoading && selectedProductId === product.id ? 'Генерация...' : 'Сгенерировать'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Description Result */}
        {descriptionResult && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mt-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-semibold text-gray-900">Результат генерации</h3>
              {!descriptionResult.error && (
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      if (descriptionResult.product_id) {
                        generateDescription(descriptionResult.product_id);
                      }
                    }}
                    disabled={descriptionLoading}
                    className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 text-sm font-medium shadow-sm"
                  >
                    {descriptionLoading ? 'Генерация...' : 'Новая генерация'}
                  </button>
                  <button
                    onClick={applyProductDescription}
                    disabled={descriptionLoading}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium shadow-sm"
                  >
                    {descriptionLoading ? 'Применение...' : 'Применить'}
                  </button>
                </div>
              )}
            </div>
            {descriptionResult.error ? (
              <p className="text-sm text-red-600">{descriptionResult.error}</p>
            ) : (
              <div className="space-y-3">
                <div>
                  <p className="text-sm font-medium text-gray-900 mb-1">Товар: {descriptionResult.product_name}</p>
                  {descriptionResult.old_description && (
                    <div className="mb-2">
                      <p className="text-xs text-gray-600 mb-1">Старое описание:</p>
                      <p className="text-sm text-gray-700 bg-white border border-gray-200 rounded p-2">{descriptionResult.old_description}</p>
                    </div>
                  )}
                  <div>
                    <p className="text-xs text-gray-600 mb-1">Новое описание ({descriptionResult.length} символов):</p>
                    <p className="text-sm text-gray-900 bg-white border border-gray-200 rounded p-2 whitespace-pre-wrap">{descriptionResult.new_description}</p>
                  </div>
                  <div className="mt-2">
                    <p className="text-xs text-gray-600">Использованные SEO-ключевые слова:</p>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {descriptionResult.seo_keywords_used.map((kw: string, idx: number) => (
                        <span key={idx} className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs border border-blue-300">{kw}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Batch Result */}
        {batchResult && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mt-4 shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Результат массовой генерации</h3>
            {batchResult.error ? (
              <p className="text-sm text-red-600">{batchResult.error}</p>
            ) : (
              <div className="space-y-2">
                <p className="text-sm text-gray-900">
                  Всего: <strong>{batchResult.total}</strong> | 
                  Успешно: <strong className="text-green-600">{batchResult.success}</strong> | 
                  Ошибок: <strong className="text-red-600">{batchResult.errors}</strong>
                </p>
                {batchResult.errors_detail && batchResult.errors_detail.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs text-gray-600 mb-1">Ошибки:</p>
                    <ul className="text-xs text-red-600 list-disc list-inside">
                      {batchResult.errors_detail.map((err: any, idx: number) => (
                        <li key={idx}>{err.product_id}: {err.error}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Обработка фото украшений */}
      <div className="bg-white rounded-lg shadow-md p-6 mt-6" id="jewelry-photo-section">
        <h2 className="text-xl font-semibold text-gray-900 mb-2">Обработка фото украшений</h2>
        <p className="text-sm text-gray-600 mb-4">
          Загрузите фото украшения (одно или несколько ракурсов). Обработанные изображения — белый фон, студийный вид, PNG 1:1 — можно добавить к карточке товара по артикулу. Можно загрузить несколько ракурсов одного изделия — они будут обработаны в едином стиле.
        </p>

        {/* История генераций */}
        <div className="mb-6">
          <h3 className="text-sm font-semibold text-gray-800 mb-2">История генераций</h3>
          {jewelryHistoryLoading ? (
            <p className="text-sm text-gray-500">Загрузка…</p>
          ) : jewelryHistory.length === 0 ? (
            <p className="text-sm text-gray-500">Пока нет сохранённых обработанных фото. Обработайте фото ниже — они появятся здесь.</p>
          ) : (
            <div className="space-y-4">
              {jewelryHistory.map((item) => (
                <div key={item.article} className="border border-gray-200 rounded-lg p-3 bg-gray-50/50">
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <span className="font-medium text-gray-900">Артикул: {item.article}</span>
                    <span className="text-xs text-gray-500">
                      {item.updated_at ? new Date(item.updated_at).toLocaleString('ru-RU') : ''}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {item.urls.map((url, i) => (
                      <div key={url} className="relative group">
                        <button
                          type="button"
                          onClick={() => setJewelryLightboxUrl(jewelryImageFullUrl(url))}
                          className="block w-20 h-20 rounded border border-gray-200 bg-white overflow-hidden focus:outline-none focus:ring-2 focus:ring-gold-500"
                          title="Открыть в полном размере"
                        >
                          <img
                            src={jewelryImageFullUrl(url)}
                            alt={`${item.article} ${i + 1}`}
                            className="w-full h-full object-contain"
                          />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); deleteJewelryHistoryFile(url); }}
                          className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition z-10"
                          aria-label="Удалить"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setJewelryArticle(item.article);
                        document.getElementById('jewelry-photo-section')?.scrollIntoView({ behavior: 'smooth' });
                      }}
                      className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-100 text-gray-700"
                    >
                      Перегенерировать (загрузить новые фото)
                    </button>
                    <button
                      type="button"
                      onClick={() => applyJewelryToProduct(item.article, item.urls)}
                      disabled={jewelryApplyLoading}
                      className="px-3 py-1.5 text-sm bg-gold-600 text-white rounded-lg hover:bg-gold-700 disabled:opacity-50"
                    >
                      {jewelryApplyLoading ? 'Добавление…' : `Добавить к карточке (${item.urls.length})`}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Артикул изделия *</label>
            <input
              type="text"
              value={jewelryArticle}
              onChange={(e) => setJewelryArticle(e.target.value)}
              placeholder="Введите артикул"
              className="w-full max-w-md px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Фото (до 5 шт., до 10 MB каждое)</label>
            <input
              type="file"
              accept="image/jpeg,image/png,image/jpg"
              multiple
              onChange={onJewelryFilesChange}
              className="block w-full text-sm text-gray-700 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:bg-gold-100 file:text-gold-800"
            />
            {jewelryFiles.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {jewelryFiles.map((f, idx) => (
                  <div key={idx} className="flex items-center gap-1 bg-gray-100 rounded px-2 py-1 text-sm">
                    <span className="text-gray-800 truncate max-w-[120px]">{f.name}</span>
                    <button
                      type="button"
                      onClick={() => removeJewelryFile(idx)}
                      className="text-red-600 hover:text-red-800"
                      aria-label="Удалить"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {jewelryError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-sm text-red-700">{jewelryError}</p>
            </div>
          )}

          {jewelryProcessing && (
            <div className="rounded-lg border border-gold-200 bg-gold-50/50 p-4">
              <p className="text-sm font-medium text-gray-900 mb-2">Обработка фото…</p>
              <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                <div
                  className="h-full bg-gold-500 rounded-full animate-pulse"
                  style={{ width: '70%' }}
                />
              </div>
              <p className="text-xs text-gray-600 mt-1">Может занять до 1–2 минут. Дождитесь завершения.</p>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={processJewelryPhotos}
              disabled={jewelryProcessing || !jewelryArticle.trim() || jewelryFiles.length === 0}
              className="px-4 py-2 bg-gold-600 text-white rounded-lg hover:bg-gold-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {jewelryProcessing ? 'Обработка фото…' : 'Обработать'}
            </button>
            {jewelryProcessing && (
              <button
                type="button"
                onClick={cancelJewelryGeneration}
                className="px-4 py-2 border border-red-300 text-red-700 rounded-lg hover:bg-red-50"
              >
                Отменить генерацию
              </button>
            )}
          </div>

          {jewelryResultUrls && jewelryResultUrls.length > 0 && (
            <div className="border-t pt-4 mt-4">
              <p className="text-sm font-medium text-gray-900 mb-2">Обработанные фото для каталога (одно изделие, разные ракурсы)</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                {jewelryResultUrls.map((url, i) => (
                  <div key={i} className="rounded-lg overflow-hidden border border-gray-200 bg-gray-50">
                    <button
                      type="button"
                      onClick={() => setJewelryLightboxUrl(jewelryImageFullUrl(url))}
                      className="w-full aspect-square block focus:outline-none focus:ring-2 focus:ring-gold-500 focus:ring-inset"
                      title="Открыть в полном размере"
                    >
                      <img
                        src={jewelryImageFullUrl(url)}
                        alt={`Ракурс ${i + 1}`}
                        className="w-full h-full object-contain"
                      />
                    </button>
                    <p className="text-xs text-center text-gray-600 py-1">Ракурс {i + 1}</p>
                  </div>
                ))}
              </div>
              <div className="mt-3">
                <label className="block text-sm font-medium text-gray-700 mb-1">Что доработать при перегенерации (необязательно)</label>
                <textarea
                  value={jewelryRevisionDescription}
                  onChange={(e) => setJewelryRevisionDescription(e.target.value)}
                  placeholder="Например: сделать фон чище белым, усилить блики, убрать тень"
                  rows={2}
                  className="w-full max-w-md px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 text-sm"
                />
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                <button
                  type="button"
                  onClick={jewelryReset}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-gray-700"
                >
                  Отменить
                </button>
                <button
                  type="button"
                  onClick={jewelryRegenerate}
                  disabled={jewelryProcessing}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-gray-700 disabled:opacity-50"
                >
                  Перегенерировать
                </button>
                <button
                  type="button"
                  onClick={() => applyJewelryToProduct()}
                  disabled={jewelryApplyLoading}
                  className="px-4 py-2 bg-gold-600 text-white rounded-lg hover:bg-gold-700 disabled:opacity-50"
                >
                  {jewelryApplyLoading ? 'Добавление…' : `Добавить к карточке товара (${jewelryResultUrls.length})`}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Просмотр фото украшения в полном разрешении */}
      {jewelryLightboxUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setJewelryLightboxUrl(null)}
          role="dialog"
          aria-modal="true"
          aria-label="Фото в полном размере"
        >
          <button
            type="button"
            onClick={() => setJewelryLightboxUrl(null)}
            className="absolute top-4 right-4 z-10 w-10 h-10 rounded-full bg-white/90 text-gray-800 flex items-center justify-center text-xl hover:bg-white"
            aria-label="Закрыть"
          >
            ×
          </button>
          <img
            src={jewelryLightboxUrl}
            alt="Фото в полном размере"
            className="max-w-[95vw] max-h-[90vh] w-auto h-auto object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}

      {/* Модальное окно редактирования плана */}
      {editingPlanId && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-md w-full mx-4">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Редактировать план</h2>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Название</label>
                <input
                  type="text"
                  value={editPlanName}
                  onChange={(e) => setEditPlanName(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                  placeholder="Название плана"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Статус</label>
                <select
                  value={editPlanStatus}
                  onChange={(e) => setEditPlanStatus(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                >
                  <option value="draft">Черновик</option>
                  <option value="active">Активный</option>
                  <option value="completed">Завершён</option>
                  <option value="archived">Архив</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Начало</label>
                  <input
                    type="date"
                    value={editPlanStartDate}
                    onChange={(e) => setEditPlanStartDate(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Конец</label>
                  <input
                    type="date"
                    value={editPlanEndDate}
                    onChange={(e) => setEditPlanEndDate(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Часовой пояс</label>
                <input
                  type="text"
                  value={editPlanTimezone}
                  onChange={(e) => setEditPlanTimezone(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                  placeholder="Europe/Moscow"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={closeEditPlanModal}
                disabled={updatingPlan}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-gray-700 disabled:opacity-50 transition"
              >
                Отмена
              </button>
              <button
                onClick={updatePlan}
                disabled={updatingPlan}
                className="flex-1 px-4 py-2 bg-gold-600 text-white rounded-lg hover:bg-gold-700 disabled:opacity-50 transition"
              >
                {updatingPlan ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Модальное окно редактирования/создания слота */}
      {(editingItemId || isCreatingItem) && planId && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              {isCreatingItem ? 'Создать новый слот' : 'Редактировать слот'}
            </h2>
            
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Дата и время</label>
                  <input
                    type="datetime-local"
                    value={editItemScheduledAt}
                    onChange={(e) => setEditItemScheduledAt(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Часовой пояс</label>
                  <input
                    type="text"
                    value={editItemTimezone}
                    onChange={(e) => setEditItemTimezone(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                    placeholder="Europe/Moscow"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Канал</label>
                  <select
                    value={editItemChannel}
                    onChange={(e) => setEditItemChannel(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                  >
                    {CHANNELS.map((ch) => (
                      <option key={ch.value} value={ch.value}>
                        {ch.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Тип контента</label>
                  <select
                    value={editItemContentType}
                    onChange={(e) => setEditItemContentType(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                  >
                    <option value="post">Пост</option>
                    <option value="story">История</option>
                    <option value="reel">Reel</option>
                    <option value="email">Email</option>
                    <option value="blog">Блог</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Тема</label>
                <input
                  type="text"
                  value={editItemTopic}
                  onChange={(e) => setEditItemTopic(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                  placeholder="Тема контента"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Hook (зацепка)</label>
                <input
                  type="text"
                  value={editItemHook}
                  onChange={(e) => setEditItemHook(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                  placeholder="Зацепка для привлечения внимания"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">CTA (призыв к действию)</label>
                <input
                  type="text"
                  value={editItemCta}
                  onChange={(e) => setEditItemCta(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                  placeholder="Призыв к действию"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Персона</label>
                  <input
                    type="text"
                    value={editItemPersona}
                    onChange={(e) => setEditItemPersona(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                    placeholder="Целевая персона"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">CJM этап</label>
                  <select
                    value={editItemCjmStage}
                    onChange={(e) => setEditItemCjmStage(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                  >
                    <option value="">Не указан</option>
                    <option value="awareness">Осведомленность</option>
                    <option value="consideration">Рассмотрение</option>
                    <option value="purchase">Покупка</option>
                    <option value="retention">Удержание</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Цель</label>
                <input
                  type="text"
                  value={editItemGoal}
                  onChange={(e) => setEditItemGoal(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                  placeholder="Цель контента"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Статус</label>
                <select
                  value={editItemStatus}
                  onChange={(e) => setEditItemStatus(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                >
                  <option value="planned">Запланирован</option>
                  <option value="draft">Черновик</option>
                  <option value="ready">Готов</option>
                  <option value="approved">Одобрен</option>
                  <option value="scheduled">Запланирован к публикации</option>
                  <option value="published">Опубликован</option>
                  <option value="failed">Ошибка</option>
                  <option value="cancelled">Отменен</option>
                </select>
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={closeEditItemModal}
                disabled={savingItem}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 text-gray-700 disabled:opacity-50 transition"
              >
                Отмена
              </button>
              <button
                onClick={saveItem}
                disabled={savingItem || !editItemScheduledAt}
                className="flex-1 px-4 py-2 bg-gold-600 text-white rounded-lg hover:bg-gold-700 disabled:opacity-50 transition"
              >
                {savingItem ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

