'use client';

import { useState, useEffect } from 'react';
import * as XLSX from 'xlsx';
import { communication, BatchGenerateRequest, GenerateMessageResponse, apiClient, BatchGenerateAsyncResponse } from '@/lib/api';

const STORAGE_KEY_CUSTOM_EVENTS = 'glame_custom_event_types';

export default function BatchMessageGenerator() {
  // Загружаем сохраненные кастомные события из localStorage
  const loadCustomEvents = (): string[] => {
    if (typeof window === 'undefined') return [];
    try {
      const stored = localStorage.getItem(STORAGE_KEY_CUSTOM_EVENTS);
      return stored ? JSON.parse(stored) : [];
    } catch (e) {
      console.error('Error loading custom events:', e);
      return [];
    }
  };

  // Сохраняем кастомные события в localStorage
  const saveCustomEvents = (events: string[]) => {
    if (typeof window === 'undefined') return;
    try {
      localStorage.setItem(STORAGE_KEY_CUSTOM_EVENTS, JSON.stringify(events));
    } catch (e) {
      console.error('Error saving custom events:', e);
    }
  };

  const [customEvents, setCustomEvents] = useState<string[]>(loadCustomEvents);
  const [eventType, setEventType] = useState<string>('brand_arrival');
  const [customEventType, setCustomEventType] = useState('');
  const [customEventDescription, setCustomEventDescription] = useState('');
  const [isCustomEvent, setIsCustomEvent] = useState(false);
  const [brand, setBrand] = useState('');
  const [store, setStore] = useState('');
  const [autoDetectStore, setAutoDetectStore] = useState(false);
  const [limit, setLimit] = useState(100);
  const [maxLength, setMaxLength] = useState<number | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressText, setProgressText] = useState('');
  const [totalClients, setTotalClients] = useState(0);
  const [messages, setMessages] = useState<GenerateMessageResponse[]>([]);
  const [errors, setErrors] = useState<Array<{ client_id: string; error: string }>>([]);
  const [showResults, setShowResults] = useState(false);
  const [lastResponse, setLastResponse] = useState<any>(null);
  const [availableBrands, setAvailableBrands] = useState<Array<{ brand: string; client_count: number }>>([]);
  const [showBrandsList, setShowBrandsList] = useState(false);
  const [showAdvancedCriteria, setShowAdvancedCriteria] = useState(false);
  const [segmentsList, setSegmentsList] = useState<Array<{ id: string; name: string }>>([]);
  const [selectedSegmentName, setSelectedSegmentName] = useState<string>('');
  
  // Критерии поиска
  const [searchCriteria, setSearchCriteria] = useState({
    segments: [] as string[],
    gender: '' as string, // 'male', 'female', или '' (все)
    min_total_spend_365: '',
    max_total_spend_365: '',
    min_purchases_365: '',
    max_purchases_365: '',
    min_days_since_last: '',
    max_days_since_last: '',
    min_bonus_balance: '',
    max_bonus_balance: '',
    is_local_only: false,
    cities: [] as string[],
  });

  // Загружаем список сегментов для обязательного выбора
  useEffect(() => {
    const loadSegments = async () => {
      try {
        const resp = await apiClient.get<Array<{ id: string; name: string }>>('/api/admin/customers/segments/list');
        setSegmentsList(resp.data || []);
      } catch (e) {
        console.error('Error loading segments list:', e);
      }
    };
    loadSegments();
  }, []);

  const handleGenerate = async () => {
    // Определяем финальный тип события
    // Если выбрано сохраненное кастомное событие, используем его
    let finalEventType: string;
    if (isCustomEvent) {
      if (customEvents.includes(eventType)) {
        // Выбрано сохраненное событие из списка
        finalEventType = eventType;
      } else {
        // Введено новое событие
        finalEventType = customEventType.trim();
      }
    } else {
      finalEventType = eventType;
    }
    
    if (!finalEventType) {
      alert('Необходимо выбрать или указать тип события');
      return;
    }

    if ((finalEventType === 'brand_arrival' || finalEventType.toLowerCase().includes('бренд')) && !brand) {
      alert('Для события "Пришел бренд" необходимо указать бренд');
      return;
    }

    // Обязательная валидация: выбранный сегмент
    if (!selectedSegmentName) {
      alert('Пожалуйста, выберите сегмент перед запуском массовой генерации.');
      return;
    }

    setLoading(true);
    setProgress(0);
    setProgressText(`Инициализация для сегмента: «${selectedSegmentName}»...`);
    setTotalClients(0);
    setErrors([]);
    setMessages([]);
    setShowResults(false);

    try {
      // Показываем начальный прогресс
      setProgressText(`Поиск клиентов в сегменте «${selectedSegmentName}»...`);
      setProgress(10);

      // Формируем критерии поиска
      const criteria: any = {};
      // Приоритетно используем выбранный сегмент из выпадающего списка
      criteria.segment_name = selectedSegmentName;

      // Игнорируем чекбоксы A–E, если выбран именованный сегмент
      if (searchCriteria.gender) {
        criteria.gender = searchCriteria.gender;
      }
      if (searchCriteria.min_total_spend_365) {
        criteria.min_total_spend_365 = parseInt(searchCriteria.min_total_spend_365) * 100; // В копейки
      }
      if (searchCriteria.max_total_spend_365) {
        criteria.max_total_spend_365 = parseInt(searchCriteria.max_total_spend_365) * 100;
      }
      if (searchCriteria.min_purchases_365) {
        criteria.min_purchases_365 = parseInt(searchCriteria.min_purchases_365);
      }
      if (searchCriteria.max_purchases_365) {
        criteria.max_purchases_365 = parseInt(searchCriteria.max_purchases_365);
      }
      if (searchCriteria.min_days_since_last) {
        criteria.min_days_since_last = parseInt(searchCriteria.min_days_since_last);
      }
      if (searchCriteria.max_days_since_last) {
        criteria.max_days_since_last = parseInt(searchCriteria.max_days_since_last);
      }
      if (searchCriteria.min_bonus_balance) {
        criteria.min_bonus_balance = parseInt(searchCriteria.min_bonus_balance);
      }
      if (searchCriteria.max_bonus_balance) {
        criteria.max_bonus_balance = parseInt(searchCriteria.max_bonus_balance);
      }
      if (searchCriteria.is_local_only) {
        criteria.is_local_only = true;
      }
      if (searchCriteria.cities.length > 0) {
        criteria.cities = searchCriteria.cities;
      }

      const request: BatchGenerateRequest = {
        event: {
          type: finalEventType as BatchGenerateRequest['event']['type'],
          brand: brand || undefined,
          store: autoDetectStore ? undefined : (store || undefined), // Если автопределение включено, не передаем store
          metadata: isCustomEvent && customEventDescription ? { description: customEventDescription } : undefined,
        },
        brand: (finalEventType === 'brand_arrival' || finalEventType.toLowerCase().includes('бренд')) ? brand : undefined,
        limit: limit,
        max_length: maxLength,
        search_criteria: Object.keys(criteria).length > 0 ? criteria : undefined,
        auto_detect_store: autoDetectStore // Добавляем флаг автопределения
      };

      setProgressText(`Генерация сообщений для сегмента «${selectedSegmentName}»...`);
      setProgress(20);

      let eventSource: any = null;
      const startResponse: BatchGenerateAsyncResponse = await communication.startBatchGenerateAsync(request);

      const generationId = startResponse.generation_id;
      const eventsUrl = startResponse.events_url || `/api/communication/generations/${generationId}/events`;

      const runPolling = async () => {
        const startedAt = Date.now();
        const maxWaitMs = 15 * 60 * 1000;
        for (;;) {
          const rec = await communication.getGeneration(generationId);
          const total = rec.total || 0;
          const processed = rec.processed || 0;
          if (total > 0) {
            const pct = Math.round((processed / total) * 100);
            setProgress(pct);
            setTotalClients(total);
            setProgressText(`Обработано ${processed} из ${total} клиентов`);
          } else {
            setProgress(30);
          }
          if (rec.status === 'completed') {
            setProgress(100);
            setProgressText('Генерация завершена, подробности в истории генераций ниже');
            break;
          }
          if (rec.status === 'failed') {
            throw new Error(rec.error_message || 'Задача генерации завершилась с ошибкой');
          }
          if (Date.now() - startedAt > maxWaitMs) {
            throw new Error('Превышено время ожидания выполнения генерации');
          }
          await new Promise(resolve => setTimeout(resolve, 2000));
        }
      };

      const canUseSse = typeof window !== 'undefined' && typeof EventSource !== 'undefined';

      if (canUseSse) {
        try {
          await new Promise<void>((resolve, reject) => {
            eventSource = new EventSource(eventsUrl);
            eventSource.onmessage = (ev: MessageEvent) => {
              if (!ev.data) {
                return;
              }
              let rec: any;
              try {
                rec = JSON.parse(ev.data);
              } catch {
                return;
              }
              if (rec.event === 'not_found') {
                reject(new Error('История генерации не найдена'));
                return;
              }
              const total = rec.total || 0;
              const processed = rec.processed || 0;
              if (total > 0) {
                const pct = Math.round((processed / total) * 100);
                setProgress(pct);
                setTotalClients(total);
                setProgressText(`Обработано ${processed} из ${total} клиентов`);
              }
              if (rec.status === 'completed') {
                setProgress(100);
                setProgressText('Генерация завершена, подробности в истории генераций ниже');
                eventSource?.close();
                resolve();
              } else if (rec.status === 'failed') {
                eventSource?.close();
                reject(new Error(rec.error_message || 'Задача генерации завершилась с ошибкой'));
              }
            };
            eventSource.onerror = () => {
              eventSource?.close();
              reject(new Error('Ошибка SSE соединения'));
            };
          });
        } catch (sseError) {
          await runPolling();
        } finally {
          eventSource?.close();
        }
      } else {
        await runPolling();
      }

      setShowResults(false);
      setLastResponse(null);
    } catch (err: any) {
      setProgress(0);
      setProgressText('');
      setLoading(false);
      
      console.error('Batch generate error:', err);
      console.error('Error response:', err.response?.data);
      console.error('Error code:', err.code);
      
      // Проверяем, не таймаут ли это
      const isTimeout = err.code === 'ECONNABORTED' || err.message?.includes('timeout') || err.message?.includes('Timeout');
      
      // Показываем результаты даже при ошибке, если они есть
      if (err.response?.data) {
        const errorData = err.response.data;
        if (errorData.messages || errorData.errors) {
          setMessages(errorData.messages || []);
          setErrors(errorData.errors || []);
          setLastResponse(errorData);
          setShowResults(true);
          setTotalClients((errorData.messages?.length || 0) + (errorData.errors?.length || 0));
        }
      }
      
      let errorMessage = err.response?.data?.detail || err.response?.data?.message || err.message || 'Ошибка при генерации сообщений';
      
      if (isTimeout) {
        errorMessage = 'Генерация сообщений занимает больше времени, чем ожидалось. Пожалуйста, попробуйте уменьшить лимит клиентов или попробуйте позже.';
      }
      
      alert(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = () => {
    if (messages.length === 0) {
      alert('Нет сообщений для экспорта');
      return;
    }

    try {
      // Подготавливаем данные для таблицы
      const data = messages.map(m => ({
        'Номер телефона': m.phone || '',
        'Имя': m.name || '',
        'Пол': m.gender === 'male' ? 'Мужской' : m.gender === 'female' ? 'Женский' : 'Не определен',
        'Сегмент': m.segment,
        'Сообщение': m.message || '',
        'CTA': m.cta || ''
      }));

      console.log('Exporting data:', data.length, 'messages');

      // Создаем рабочую книгу
      const wb = XLSX.utils.book_new();
      const ws = XLSX.utils.json_to_sheet(data);

      // Настраиваем ширину колонок
      const colWidths = [
        { wch: 20 }, // Номер телефона
        { wch: 20 }, // Имя
        { wch: 15 }, // Пол
        { wch: 10 }, // Сегмент
        { wch: 60 }, // Сообщение
        { wch: 40 }  // CTA
      ];
      ws['!cols'] = colWidths;

      // Добавляем лист в книгу
      XLSX.utils.book_append_sheet(wb, ws, 'Сообщения');

      // Сохраняем файл
      const fileName = `messages_${new Date().toISOString().split('T')[0]}_${Date.now()}.xlsx`;
      XLSX.writeFile(wb, fileName);
      
      console.log('File exported successfully:', fileName);
      alert(`Файл ${fileName} успешно сохранен!`);
    } catch (error) {
      console.error('Export error:', error);
      alert('Ошибка при экспорте файла: ' + (error instanceof Error ? error.message : String(error)));
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-bold text-gray-900 mb-4">Массовая генерация сообщений</h2>
      
      <div className="space-y-4">
        {/* Обязательный выбор сегмента */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Сегмент <span className="text-red-500">*</span>
          </label>
          <select
            value={selectedSegmentName}
            onChange={(e) => setSelectedSegmentName(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
          >
            <option value="">Выберите сегмент</option>
            {segmentsList.map(s => (
              <option key={s.id} value={s.name}>{s.name}</option>
            ))}
          </select>
          <p className="mt-1 text-xs text-gray-500">
            Массовая генерация учитывает только клиентов выбранного сегмента.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Тип события
          </label>
          <select
            value={isCustomEvent ? (customEvents.includes(eventType) ? eventType : 'custom') : eventType}
            onChange={(e) => {
              if (e.target.value === 'custom') {
                setIsCustomEvent(true);
                setCustomEventType('');
                setCustomEventDescription('');
                setEventType('custom');
              } else if (customEvents.includes(e.target.value)) {
                // Выбрано сохраненное кастомное событие
                setIsCustomEvent(true);
                setEventType(e.target.value);
                setCustomEventType(e.target.value);
                setCustomEventDescription(''); // Можно было бы загружать, если сохраняли
              } else {
                setIsCustomEvent(false);
                setEventType(e.target.value);
                setCustomEventDescription('');
                if (e.target.value !== 'brand_arrival') {
                  setBrand('');
                }
              }
            }}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
          >
            <optgroup label="Стандартные события">
              <option value="brand_arrival">Пришел бренд в бутик</option>
              <option value="loyalty_level_up">Новый уровень лояльности</option>
              <option value="bonus_balance">Напоминание о бонусах</option>
              <option value="no_purchase_180">Нет покупок более 180 дней</option>
              <option value="holiday_male">Праздничное сообщение (мужчинам)</option>
            </optgroup>
            {customEvents.length > 0 && (
              <optgroup label="Сохраненные события">
                {customEvents.map((event, idx) => (
                  <option key={idx} value={event}>{event}</option>
                ))}
              </optgroup>
            )}
            <optgroup label="Действия">
              <option value="custom">➕ Создать новый тип события</option>
            </optgroup>
          </select>
          
          {isCustomEvent && (
            <div className="mt-2">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={customEventType}
                  onChange={(e) => setCustomEventType(e.target.value)}
                  placeholder="Введите название нового типа события"
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
                />
                {customEventType.trim() && !customEvents.includes(customEventType.trim()) && (
                  <button
                    type="button"
                    onClick={() => {
                      const trimmed = customEventType.trim();
                      if (trimmed && !customEvents.includes(trimmed)) {
                        const updated = [...customEvents, trimmed];
                        setCustomEvents(updated);
                        saveCustomEvents(updated);
                        setEventType(trimmed);
                        setCustomEventType(trimmed);
                        alert(`Событие "${trimmed}" сохранено!`);
                      }
                    }}
                    className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 text-sm font-medium whitespace-nowrap"
                    title="Сохранить это событие"
                  >
                    💾 Сохранить
                  </button>
                )}
              </div>
              
              <div className="mt-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Описание события (для AI)
                </label>
                <textarea
                  value={customEventDescription}
                  onChange={(e) => setCustomEventDescription(e.target.value)}
                  placeholder="Опишите, о чем нужно написать клиенту. Например: 'Предложи скидку 20% на новую коллекцию платьев' или 'Пригласи на закрытую распродажу'."
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500 text-sm"
                  rows={3}
                />
              </div>

              <p className="mt-1 text-xs text-gray-500">
                Введите название нового типа события (например: &quot;Новая коллекция&quot;, &quot;Скидка на товары&quot; и т.д.)
                {customEvents.length > 0 && (
                  <span className="block mt-1">
                    Сохраненные события: {customEvents.join(', ')}
                  </span>
                )}
              </p>
              {customEvents.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs text-gray-600 mb-1">Управление сохраненными событиями:</p>
                  <div className="flex flex-wrap gap-2">
                    {customEvents.map((event, idx) => (
                      <div key={idx} className="flex items-center gap-1 bg-gray-100 px-2 py-1 rounded text-xs">
                        <span>{event}</span>
                        <button
                          type="button"
                          onClick={() => {
                            if (confirm(`Удалить событие "${event}"?`)) {
                              const updated = customEvents.filter(e => e !== event);
                              setCustomEvents(updated);
                              saveCustomEvents(updated);
                              if (eventType === event) {
                                setIsCustomEvent(false);
                                setEventType('brand_arrival');
                                setCustomEventType('');
                              }
                            }
                          }}
                          className="text-red-600 hover:text-red-800 font-bold"
                          title="Удалить событие"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {((!isCustomEvent && eventType === 'brand_arrival') || (isCustomEvent && (customEventType.toLowerCase().includes('бренд') || (customEvents.includes(eventType) && eventType.toLowerCase().includes('бренд'))))) && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700">
                Бренд <span className="text-red-500">*</span>
              </label>
              <button
                type="button"
                onClick={async () => {
                  try {
                    const brandsData = await communication.getAvailableBrands(50);
                    setAvailableBrands(brandsData.brands || []);
                    setShowBrandsList(!showBrandsList);
                  } catch (err) {
                    console.error('Error loading brands:', err);
                  }
                }}
                className="text-xs text-pink-600 hover:text-pink-700 underline"
              >
                {showBrandsList ? 'Скрыть' : 'Показать'} доступные бренды
              </button>
            </div>
            <input
              type="text"
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              placeholder="Введите название бренда"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
              list="available-brands-list"
            />
            {showBrandsList && availableBrands.length > 0 && (
              <div className="mt-2 p-3 bg-gray-50 rounded-md border border-gray-200 max-h-40 overflow-y-auto">
                <p className="text-xs font-medium text-gray-700 mb-2">Доступные бренды:</p>
                <div className="space-y-1">
                  {availableBrands.map((b, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => {
                        setBrand(b.brand);
                        setShowBrandsList(false);
                      }}
                      className="block w-full text-left text-xs text-gray-600 hover:text-pink-600 hover:bg-pink-50 px-2 py-1 rounded"
                    >
                      {b.brand} <span className="text-gray-400">({b.client_count} клиентов)</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            <p className="mt-1 text-xs text-gray-500">
              Будут найдены все клиенты, у которых в истории есть этот бренд
            </p>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Бутик (опционально)
          </label>
          <div className="space-y-2">
            <input
              type="text"
              value={store}
              onChange={(e) => setStore(e.target.value)}
              placeholder="Например: Ялта, Симферополь"
              disabled={autoDetectStore}
              className={`w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500 ${
                autoDetectStore ? 'bg-gray-100 cursor-not-allowed' : ''
              }`}
            />
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={autoDetectStore}
                onChange={(e) => {
                  setAutoDetectStore(e.target.checked);
                  if (e.target.checked) {
                    setStore(''); // Очищаем поле при включении автопределения
                  }
                }}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">
                Определить из истории покупок
              </span>
            </label>
            {autoDetectStore && (
              <p className="text-xs text-gray-500">
                Бутик будет определен автоматически для каждого клиента: из истории покупок (приоритет: последняя покупка → больше всего покупок → наибольшая сумма) или из города в профиле, если истории покупок нет.
              </p>
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Лимит клиентов
          </label>
          <input
            type="number"
            value={limit}
            onChange={(e) => setLimit(parseInt(e.target.value) || 100)}
            min={1}
            max={1000}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Длина сообщения (символов)
          </label>
          <div className="flex gap-2">
            <input
              type="number"
              value={maxLength || ''}
              onChange={(e) => {
                const val = parseInt(e.target.value);
                setMaxLength(isNaN(val) ? undefined : val);
              }}
              placeholder="Не ограничено"
              min={10}
              max={2000}
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
            />
            <div className="flex gap-1">
              {[
                { label: 'SMS (70)', value: 70 },
                { label: 'SMS (140)', value: 140 },
                { label: 'Push (250)', value: 250 },
                { label: 'WhatsApp (1000)', value: 1000 }
              ].map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setMaxLength(opt.value)}
                  className={`px-2 py-1 text-xs rounded border ${
                    maxLength === opt.value
                      ? 'bg-pink-100 border-pink-300 text-pink-700 font-medium'
                      : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            Оставьте пустым для автоопределения оптимальной длины. AI постарается уложиться в этот лимит.
          </p>
        </div>

        {/* Расширенные критерии поиска */}
        <div className="border-t border-gray-200 pt-4">
          <button
            type="button"
            onClick={() => setShowAdvancedCriteria(!showAdvancedCriteria)}
            className="flex items-center justify-between w-full text-sm font-medium text-gray-700 hover:text-pink-600"
          >
            <span>⚙️ Расширенные критерии поиска</span>
            <span>{showAdvancedCriteria ? '▼' : '▶'}</span>
          </button>

          {showAdvancedCriteria && (
            <div className="mt-4 space-y-4 p-4 bg-gray-50 rounded-md border border-gray-200">
              {/* Сегменты */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Сегменты клиентов
                </label>
                <div className="flex flex-wrap gap-2">
                  {['A', 'B', 'C', 'D', 'E'].map(segment => (
                    <label key={segment} className="flex items-center">
                      <input
                        type="checkbox"
                        checked={searchCriteria.segments.includes(segment)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSearchCriteria(prev => ({
                              ...prev,
                              segments: [...prev.segments, segment]
                            }));
                          } else {
                            setSearchCriteria(prev => ({
                              ...prev,
                              segments: prev.segments.filter(s => s !== segment)
                            }));
                          }
                        }}
                        className="mr-2"
                      />
                      <span className="text-sm text-gray-700">Сегмент {segment}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Пол */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Пол
                </label>
                <div className="flex gap-4">
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="gender"
                      value=""
                      checked={searchCriteria.gender === ''}
                      onChange={(e) => setSearchCriteria(prev => ({ ...prev, gender: e.target.value }))}
                      className="mr-2"
                    />
                    <span className="text-sm text-gray-700">Все</span>
                  </label>
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="gender"
                      value="male"
                      checked={searchCriteria.gender === 'male'}
                      onChange={(e) => setSearchCriteria(prev => ({ ...prev, gender: e.target.value }))}
                      className="mr-2"
                    />
                    <span className="text-sm text-gray-700">♂ Мужчины</span>
                  </label>
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="gender"
                      value="female"
                      checked={searchCriteria.gender === 'female'}
                      onChange={(e) => setSearchCriteria(prev => ({ ...prev, gender: e.target.value }))}
                      className="mr-2"
                    />
                    <span className="text-sm text-gray-700">♀ Женщины</span>
                  </label>
                </div>
              </div>

              {/* Сумма покупок за 365 дней */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Мин. сумма покупок (₽)
                  </label>
                  <input
                    type="number"
                    value={searchCriteria.min_total_spend_365}
                    onChange={(e) => setSearchCriteria(prev => ({
                      ...prev,
                      min_total_spend_365: e.target.value
                    }))}
                    placeholder="0"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Макс. сумма покупок (₽)
                  </label>
                  <input
                    type="number"
                    value={searchCriteria.max_total_spend_365}
                    onChange={(e) => setSearchCriteria(prev => ({
                      ...prev,
                      max_total_spend_365: e.target.value
                    }))}
                    placeholder="Без ограничений"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
              </div>

              {/* Количество покупок */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Мин. количество покупок
                  </label>
                  <input
                    type="number"
                    value={searchCriteria.min_purchases_365}
                    onChange={(e) => setSearchCriteria(prev => ({
                      ...prev,
                      min_purchases_365: e.target.value
                    }))}
                    placeholder="0"
                    min="0"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Макс. количество покупок
                  </label>
                  <input
                    type="number"
                    value={searchCriteria.max_purchases_365}
                    onChange={(e) => setSearchCriteria(prev => ({
                      ...prev,
                      max_purchases_365: e.target.value
                    }))}
                    placeholder="Без ограничений"
                    min="0"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
              </div>

              {/* Дни с последней покупки */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Мин. дней с последней покупки
                  </label>
                  <input
                    type="number"
                    value={searchCriteria.min_days_since_last}
                    onChange={(e) => setSearchCriteria(prev => ({
                      ...prev,
                      min_days_since_last: e.target.value
                    }))}
                    placeholder="0"
                    min="0"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Макс. дней с последней покупки
                  </label>
                  <input
                    type="number"
                    value={searchCriteria.max_days_since_last}
                    onChange={(e) => setSearchCriteria(prev => ({
                      ...prev,
                      max_days_since_last: e.target.value
                    }))}
                    placeholder="Без ограничений"
                    min="0"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
              </div>

              {/* Баланс бонусов */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Мин. баланс бонусов
                  </label>
                  <input
                    type="number"
                    value={searchCriteria.min_bonus_balance}
                    onChange={(e) => setSearchCriteria(prev => ({
                      ...prev,
                      min_bonus_balance: e.target.value
                    }))}
                    placeholder="0"
                    min="0"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Макс. баланс бонусов
                  </label>
                  <input
                    type="number"
                    value={searchCriteria.max_bonus_balance}
                    onChange={(e) => setSearchCriteria(prev => ({
                      ...prev,
                      max_bonus_balance: e.target.value
                    }))}
                    placeholder="Без ограничений"
                    min="0"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                  />
                </div>
              </div>

              {/* Местоположение */}
              <div>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={searchCriteria.is_local_only}
                    onChange={(e) => setSearchCriteria(prev => ({
                      ...prev,
                      is_local_only: e.target.checked
                    }))}
                    className="mr-2"
                  />
                  <span className="text-sm text-gray-700">Только местные клиенты (Крым)</span>
                </label>
              </div>

              {/* Города */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Города (через запятую)
                </label>
                <input
                  type="text"
                  value={searchCriteria.cities.join(', ')}
                  onChange={(e) => {
                    const cities = e.target.value.split(',').map(c => c.trim()).filter(Boolean);
                    setSearchCriteria(prev => ({ ...prev, cities }));
                  }}
                  placeholder="Ялта, Симферополь, Севастополь"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Оставьте пустым, чтобы не фильтровать по городам
                </p>
              </div>
            </div>
          )}
        </div>

        <button
          onClick={handleGenerate}
          disabled={loading || (isCustomEvent && !customEventType.trim()) || (!isCustomEvent && eventType === 'brand_arrival' && !brand)}
          className={`w-full px-4 py-2 rounded-md font-medium ${
            loading || (isCustomEvent && !customEventType.trim()) || (!isCustomEvent && eventType === 'brand_arrival' && !brand)
              ? 'bg-gray-400 text-white cursor-not-allowed'
              : 'bg-pink-600 text-white hover:bg-pink-700'
          }`}
        >
          {loading ? 'Генерация...' : 'Сгенерировать сообщения'}
        </button>

        {/* Прогресс-бар */}
        {loading && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-700">
                {progressText || 'Генерация сообщений...'}
              </span>
              <span className="text-sm text-gray-500">
                {progress}%
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2.5">
              <div
                className="bg-pink-600 h-2.5 rounded-full transition-all duration-300 ease-out"
                style={{ width: `${progress}%` }}
              ></div>
            </div>
            {totalClients > 0 && (
              <p className="text-xs text-gray-500 mt-1">
                Обработано клиентов: {totalClients}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Результаты */}
      {showResults && (
        <div className="mt-6 border-t border-gray-200 pt-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-bold text-gray-900">
                Результаты генерации
              </h3>
              <p className="text-sm text-gray-500 mt-1">
                Сгенерировано: {messages.length} сообщений
                {errors.length > 0 && `, ошибок: ${errors.length}`}
                {totalClients > 0 && `, обработано: ${totalClients} клиентов`}
              </p>
            </div>
             {messages.length > 0 && (
               <button
                 onClick={handleExport}
                 className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 text-sm font-medium"
                 title="Экспортировать сообщения в Excel"
               >
                 📥 Экспорт в Excel
               </button>
             )}
          </div>

          {messages.length > 0 && (
            <div className="space-y-4 max-h-96 overflow-y-auto">
               {messages.map((msg, idx) => (
                 <div key={idx} className="p-4 bg-gray-50 rounded-md border border-gray-200">
                   <div className="flex items-center justify-between mb-2">
                     <div className="flex items-center gap-2 flex-wrap">
                       <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                         msg.segment === 'A' ? 'bg-yellow-100 text-yellow-800' :
                         msg.segment === 'B' ? 'bg-green-100 text-green-800' :
                         msg.segment === 'C' ? 'bg-blue-100 text-blue-800' :
                         msg.segment === 'D' ? 'bg-gray-100 text-gray-800' :
                         'bg-purple-100 text-purple-800'
                       }`}>
                         Сегмент {msg.segment}
                       </span>
                       {msg.name && (
                         <span className="text-xs text-gray-700 font-medium">
                           👤 {msg.name}
                         </span>
                       )}
                       {msg.gender && (
                         <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                           msg.gender === 'female' ? 'bg-pink-100 text-pink-700' :
                           msg.gender === 'male' ? 'bg-blue-100 text-blue-700' :
                           'bg-gray-100 text-gray-600'
                         }`}>
                           {msg.gender === 'female' ? '♀ Женский' : msg.gender === 'male' ? '♂ Мужской' : '❓ Не определен'}
                         </span>
                       )}
                       {msg.phone && (
                         <span className="text-xs text-gray-600 font-medium">
                           📱 {msg.phone}
                         </span>
                       )}
                     </div>
                     <span className="text-xs text-gray-500">
                       ID: {msg.client_id.substring(0, 8)}...
                     </span>
                   </div>
                   <p className="text-sm text-gray-900 mb-2">{msg.message}</p>
                   <p className="text-xs text-pink-600 font-medium">{msg.cta}</p>
                 </div>
               ))}
            </div>
          )}

          {errors.length > 0 && (
            <div className="mt-4">
              <h4 className="text-sm font-medium text-red-700 mb-2">Ошибки:</h4>
              <div className="space-y-1">
                {errors.map((err, idx) => (
                  <div key={idx} className="text-xs text-red-600 bg-red-50 p-2 rounded">
                    {err.client_id}: {err.error}
                  </div>
                ))}
              </div>
            </div>
          )}

          {messages.length === 0 && errors.length === 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4">
              <p className="text-yellow-800 font-medium mb-2">
                Клиенты не найдены
              </p>
              <p className="text-yellow-700 text-sm mb-3">
                {lastResponse?.message || 'Клиенты не найдены для указанных критериев. Проверьте параметры поиска.'}
              </p>
              {lastResponse?.total_customers_in_db !== undefined && (
                <p className="text-xs text-yellow-600 mb-3">
                  Всего клиентов в базе: <strong>{lastResponse.total_customers_in_db}</strong>
                </p>
              )}
              <div className="mt-3 text-xs text-yellow-600">
                <p className="font-medium mb-1">Возможные причины:</p>
                <ul className="list-disc list-inside space-y-1">
                  <li>Бренд указан неверно или отсутствует в истории покупок</li>
                  <li>В базе данных нет клиентов (выполните синхронизацию с 1С)</li>
                  <li>Критерии поиска слишком строгие</li>
                  <li>Название бренда не совпадает точно (проверьте регистр и пробелы)</li>
                </ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
