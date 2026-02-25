'use client';

import { useState, useEffect, useCallback } from 'react';
import { communication, GenerateMessageRequest, GenerateMessageResponse, CustomerMessageItem } from '@/lib/api';

interface MessageGeneratorProps {
  clientId: string;
  clientName?: string;
  purchaseHistory?: Array<{ brand: string; date: string; store?: string }>;
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  brand_arrival: 'Пришел бренд в бутик',
  loyalty_level_up: 'Новый уровень лояльности',
  bonus_balance: 'Напоминание о бонусах',
  no_purchase_180: 'Нет покупок более 180 дней',
  holiday_male: 'Праздничное сообщение (мужчинам)',
};

export default function MessageGenerator({ clientId, clientName, purchaseHistory = [] }: MessageGeneratorProps) {
  const [eventType, setEventType] = useState<'brand_arrival' | 'loyalty_level_up' | 'bonus_balance' | 'no_purchase_180' | 'holiday_male'>('brand_arrival');
  const [brand, setBrand] = useState('');
  const [store, setStore] = useState('');
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState<GenerateMessageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // История сообщений
  const [messages, setMessages] = useState<CustomerMessageItem[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const loadMessages = useCallback(async () => {
    if (!clientId) return;
    setLoadingMessages(true);
    try {
      const data = await communication.getCustomerMessages(clientId);
      setMessages(data.items);
    } catch {
      setMessages([]);
    } finally {
      setLoadingMessages(false);
    }
  }, [clientId]);

  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

  // Получаем уникальные бренды из истории покупок
  const availableBrands = Array.from(new Set(purchaseHistory.map(p => p.brand).filter(Boolean)));

  const handleDelete = async (msg: CustomerMessageItem) => {
    setActionLoading(msg.id);
    try {
      await communication.deleteCustomerMessage(msg.id);
      await loadMessages();
    } finally {
      setActionLoading(null);
    }
  };

  const handleMarkSent = async (msg: CustomerMessageItem) => {
    setActionLoading(msg.id);
    try {
      await communication.markMessageSent(msg.id);
      await loadMessages();
    } finally {
      setActionLoading(null);
    }
  };

  const handleGenerate = async () => {
    if (eventType === 'brand_arrival' && !brand) {
      setError('Для события "Пришел бренд" необходимо указать бренд');
      return;
    }

    setLoading(true);
    setProgress(0);
    setError(null);
    setMessage(null);

    try {
      // Показываем прогресс
      setProgress(20);
      
      const request: GenerateMessageRequest = {
        client_id: clientId,
        event: {
          type: eventType,
          brand: brand || undefined,
          store: store || undefined,
        }
      };

      // Симулируем прогресс во время запроса
      const progressInterval = setInterval(() => {
        setProgress(prev => {
          if (prev < 90) {
            return prev + 10;
          }
          return prev;
        });
      }, 200);

      setProgress(50);
      const response = await communication.generateMessage(request);
      
      clearInterval(progressInterval);
      setProgress(100);
      setMessage(response);
      await loadMessages();

      // Сбрасываем прогресс через секунду
      setTimeout(() => {
        setProgress(0);
      }, 1000);
    } catch (err: any) {
      setProgress(0);
      setError(err.response?.data?.detail || err.message || 'Ошибка при генерации сообщения');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (message) {
      const text = `${message.message}\n\n${message.cta}`;
      navigator.clipboard.writeText(text);
      alert('Сообщение скопировано в буфер обмена');
    }
  };

  return (
    <div className="space-y-6">
      {/* История сообщений */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-bold text-gray-900 mb-4">История сообщений</h2>
        <p className="text-sm text-gray-500 mb-4">
          Ранее сгенерированные сообщения для этого покупателя. Управляйте статусами и контекстом диалога.
        </p>
        {loadingMessages ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-pink-600" />
          </div>
        ) : messages.length === 0 ? (
          <p className="text-gray-500 py-4">Сообщений пока нет. Сгенерируйте первое сообщение ниже.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Дата</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Событие / бренд</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Текст</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Статус</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Действия</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {messages.map((msg) => (
                  <tr key={msg.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                      {new Date(msg.created_at).toLocaleString('ru-RU', {
                        day: '2-digit',
                        month: '2-digit',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      <span className="font-medium">{EVENT_TYPE_LABELS[msg.event_type || ''] || msg.event_type || '—'}</span>
                      {(msg.event_brand || msg.event_store) && (
                        <span className="block text-gray-500 text-xs">
                          {[msg.event_brand, msg.event_store].filter(Boolean).join(' · ')}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900 max-w-md">
                      <p className="line-clamp-2" title={msg.message}>
                        {msg.message}
                      </p>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {msg.status === 'sent' && msg.sent_at ? (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                          Отправлено {new Date(msg.sent_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
                          Новое
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-right text-sm">
                      {actionLoading === msg.id ? (
                        <span className="text-gray-400">...</span>
                      ) : (
                        <>
                          {msg.status === 'new' && (
                            <button
                              type="button"
                              onClick={() => handleMarkSent(msg)}
                              className="text-pink-600 hover:text-pink-800 font-medium mr-3"
                            >
                              Отправить
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => handleDelete(msg)}
                            className="text-red-600 hover:text-red-800 font-medium"
                          >
                            Удалить
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Форма генерации */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-bold text-gray-900 mb-4">Генерация персонального сообщения</h2>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Тип события
            </label>
            <select
              value={eventType}
              onChange={(e) => {
                setEventType(e.target.value as any);
                setError(null);
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
            >
              <option value="brand_arrival">Пришел бренд в бутик</option>
              <option value="loyalty_level_up">Новый уровень лояльности</option>
              <option value="bonus_balance">Напоминание о бонусах</option>
              <option value="no_purchase_180">Нет покупок более 180 дней</option>
              <option value="holiday_male">Праздничное сообщение (мужчинам)</option>
            </select>
          </div>

          {eventType === 'brand_arrival' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Бренд <span className="text-red-500">*</span>
              </label>
              {availableBrands.length > 0 ? (
                <>
                  <select
                    value={brand}
                    onChange={(e) => setBrand(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
                  >
                    <option value="">Выберите бренд</option>
                    {availableBrands.map((b) => (
                      <option key={b} value={b}>{b}</option>
                    ))}
                  </select>
                  <p className="mt-1 text-xs text-gray-500">
                    Бренды из истории покупок клиента
                  </p>
                </>
              ) : (
                <input
                  type="text"
                  value={brand}
                  onChange={(e) => setBrand(e.target.value)}
                  placeholder="Введите название бренда"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
                />
              )}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Бутик (опционально)
            </label>
            <input
              type="text"
              value={store}
              onChange={(e) => setStore(e.target.value)}
              placeholder="Например: Ялта, Симферополь"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
            />
          </div>

          <button
            onClick={handleGenerate}
            disabled={loading || (eventType === 'brand_arrival' && !brand)}
            className={`w-full px-4 py-2 rounded-md font-medium ${
              loading || (eventType === 'brand_arrival' && !brand)
                ? 'bg-gray-400 text-white cursor-not-allowed'
                : 'bg-pink-600 text-white hover:bg-pink-700'
            }`}
          >
            {loading ? 'Генерация...' : 'Сгенерировать сообщение'}
          </button>

          {/* Прогресс-бар */}
          {loading && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700">
                  Генерация персонального сообщения...
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
            </div>
          )}
        </div>

        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md text-red-700 text-sm">
            {error}
          </div>
        )}
      </div>

      {/* Результат */}
      {message && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-gray-900">Сгенерированное сообщение</h3>
            <button
              onClick={handleCopy}
              className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200"
            >
              📋 Копировать
            </button>
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-4 flex-wrap">
              <div>
                <p className="text-sm text-gray-500 mb-1">Сегмент клиента</p>
                <span className={`inline-block px-3 py-1 text-sm font-semibold rounded-full ${
                  message.segment === 'A' ? 'bg-yellow-100 text-yellow-800' :
                  message.segment === 'B' ? 'bg-green-100 text-green-800' :
                  message.segment === 'C' ? 'bg-blue-100 text-blue-800' :
                  message.segment === 'D' ? 'bg-gray-100 text-gray-800' :
                  'bg-purple-100 text-purple-800'
                }`}>
                  {message.segment}
                </span>
              </div>
              {message.name && (
                <div>
                  <p className="text-sm text-gray-500 mb-1">Имя клиента</p>
                  <span className="inline-block px-3 py-1 text-sm font-medium text-gray-900">
                    👤 {message.name}
                  </span>
                </div>
              )}
              {message.gender && (
                <div>
                  <p className="text-sm text-gray-500 mb-1">Пол</p>
                  <span className={`inline-block px-3 py-1 text-sm font-medium rounded-full ${
                    message.gender === 'female' ? 'bg-pink-100 text-pink-700' :
                    message.gender === 'male' ? 'bg-blue-100 text-blue-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {message.gender === 'female' ? '♀ Женский' : message.gender === 'male' ? '♂ Мужской' : '❓ Не определен'}
                  </span>
                </div>
              )}
              {message.phone && (
                <div>
                  <p className="text-sm text-gray-500 mb-1">Телефон</p>
                  <span className="inline-block px-3 py-1 text-sm font-medium text-gray-900">
                    📱 {message.phone}
                  </span>
                </div>
              )}
            </div>

            <div>
              <p className="text-sm text-gray-500 mb-2">Сообщение</p>
              <div className="p-4 bg-gray-50 rounded-md border border-gray-200">
                <p className="text-gray-900 whitespace-pre-wrap">{message.message}</p>
              </div>
            </div>

            <div>
              <p className="text-sm text-gray-500 mb-2">Призыв к действию</p>
              <div className="p-3 bg-pink-50 rounded-md border border-pink-200">
                <p className="text-pink-900 font-medium">{message.cta}</p>
              </div>
            </div>

            {(message.brand || message.store) && (
              <div className="flex gap-4 text-sm">
                {message.brand && (
                  <div>
                    <span className="text-gray-500">Бренд: </span>
                    <span className="font-medium text-gray-900">{message.brand}</span>
                  </div>
                )}
                {message.store && (
                  <div>
                    <span className="text-gray-500">Бутик: </span>
                    <span className="font-medium text-gray-900">{message.store}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
