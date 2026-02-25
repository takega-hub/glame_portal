'use client';

import { useState, useRef, useEffect } from 'react';
import { api, StylistResponse } from '@/lib/api';
import { ChatMessage, LookWithProducts, QuickAction } from '@/types';
import ProductCard from '../products/ProductCard';
import LookCard from '../looks/LookCard';
import { analytics, getSessionId, getUserId } from '@/lib/analytics';

const QUICK_ACTIONS: QuickAction[] = [
  {
    id: '1',
    label: 'Хочу образ для свидания',
    message: 'Хочу образ для свидания',
  },
  {
    id: '2',
    label: 'Подобрать украшения на работу',
    message: 'Подобрать украшения на работу',
  },
  {
    id: '3',
    label: 'Повседневный стиль',
    message: 'Повседневный стиль',
  },
  {
    id: '4',
    label: 'Вечерний образ',
    message: 'Нужен вечерний образ для особого случая',
  },
  {
    id: '5',
    label: 'Деловой стиль',
    message: 'Подбери украшения для делового образа',
  },
  {
    id: '6',
    label: 'Романтический образ',
    message: 'Хочу романтический образ',
  },
  {
    id: '7',
    label: 'Подарок для подруги',
    message: 'Ищу подарок украшение для подруги',
  },
  {
    id: '8',
    label: 'Минималистичный стиль',
    message: 'Люблю минимализм, что посоветуешь?',
  },
  {
    id: '9',
    label: 'Украшения на свадьбу',
    message: 'Подбери украшения на свадьбу (гость), хочу выглядеть элегантно',
  },
  {
    id: '10',
    label: 'Подарок маме',
    message: 'Нужен подарок украшение для мамы, бюджет до 15000',
  },
  {
    id: '11',
    label: 'На каждый день + спорт-шик',
    message: 'Хочу украшения на каждый день в стиле sport-chic',
  },
  {
    id: '12',
    label: 'С чем носить?',
    message: 'Подскажи, с чем носить массивные серьги, чтобы смотрелось гармонично',
  },
];

const STORAGE_KEY = 'glame_chat_history';
const SESSION_STORAGE_KEY = 'glame_session_id';
const MAX_STORED_MESSAGES = 100;

interface ChatInterfaceProps {
  userId?: string;
}

export default function ChatInterface({ userId }: ChatInterfaceProps = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentResponse, setCurrentResponse] = useState<StylistResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [nearestStores, setNearestStores] = useState<any[]>([]);
  const [locationError, setLocationError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Загрузка истории при монтировании компонента
  useEffect(() => {
    try {
      const savedMessages = localStorage.getItem(STORAGE_KEY);
      const savedSessionId = localStorage.getItem(SESSION_STORAGE_KEY);
      
      if (savedMessages) {
        const parsedMessages = JSON.parse(savedMessages);
        // Восстанавливаем даты из строк
        const restoredMessages = parsedMessages.map((msg: any) => ({
          ...msg,
          timestamp: new Date(msg.timestamp),
        }));
        setMessages(restoredMessages);
      }
      
      if (savedSessionId) {
        setSessionId(savedSessionId);
      }
      
      // Запрос геолокации для поиска ближайших магазинов
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          async (position) => {
            try {
              const response = await api.getNearestStores(
                position.coords.latitude,
                position.coords.longitude,
                50, // радиус 50 км
                5   // максимум 5 магазинов
              );
              setNearestStores(response.stores || []);
            } catch (e: any) {
              console.error('Error fetching nearest stores:', e);
            }
          },
          (error) => {
            setLocationError('Не удалось получить геолокацию');
            console.error('Geolocation error:', error);
          }
        );
      }
    } catch (error) {
      console.error('Error loading chat history:', error);
    }
  }, []);

  // Сохранение истории при изменении сообщений
  useEffect(() => {
    try {
      if (messages.length > 0) {
        const trimmed = messages.slice(-MAX_STORED_MESSAGES);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
      }
      if (sessionId) {
        localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
      }
    } catch (error) {
      console.error('Error saving chat history:', error);
    }
  }, [messages, sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentResponse]);

  // Очистка истории
  const clearHistory = () => {
    if (confirm('Вы уверены, что хотите очистить историю диалога?')) {
      setMessages([]);
      setCurrentResponse(null);
      setSessionId(null);
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(SESSION_STORAGE_KEY);
      setError(null);
      setRetryCount(0);
    }
  };

  const sendMessage = async (messageText: string, retryAttempt = 0) => {
    if (!messageText.trim() || loading) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: messageText,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setCurrentResponse(null);
    setError(null);

    // Трекинг сообщения
    try {
      await analytics.trackChatMessage(
        sessionId || getSessionId(),
        messageText,
        getUserId(),
        'chat'
      );
    } catch (e) {
      console.error('Error tracking chat message:', e);
    }

    try {
      const response = await api.chatWithStylist({
        message: messageText,
        session_id: sessionId || undefined,
        user_id: userId || undefined,
      });

      setSessionId(response.session_id);
      setCurrentResponse(response);
      setRetryCount(0);

      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.reply,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error: any) {
      console.error('Error sending message:', error);
      
      let errorMessage = 'Извините, произошла ошибка.';
      let canRetry = false;

      if (error.response) {
        // Ошибка от сервера
        const status = error.response.status;
        const data = error.response.data;
        const serverDetail =
          typeof data?.detail === 'string'
            ? data.detail
            : data?.detail
              ? JSON.stringify(data.detail)
              : null;

        if (status === 400) {
          errorMessage = 'Неверный запрос. Проверьте формат сообщения.';
        } else if (status === 401) {
          errorMessage = 'Ошибка авторизации. Пожалуйста, обновите страницу.';
        } else if (status === 403) {
          errorMessage = 'Доступ запрещен.';
        } else if (status === 404) {
          errorMessage = 'Сервис не найден. Проверьте подключение к серверу.';
        } else if (status === 429) {
          errorMessage = 'Слишком много запросов. Подождите немного и попробуйте снова.';
          canRetry = true;
        } else if (status >= 500) {
          errorMessage = 'Ошибка на сервере. Попробуйте позже.';
          canRetry = retryAttempt < 2; // Максимум 2 повтора
        } else {
          errorMessage = serverDetail || `Ошибка ${status}. Попробуйте еще раз.`;
          canRetry = retryAttempt < 2;
        }

        // Не показываем пользователю огромные traceback'и
        if (serverDetail && serverDetail.length > 300) {
          errorMessage = errorMessage.replace(/\s+/g, ' ').slice(0, 220) + '…';
        }
      } else if (error.request) {
        // Запрос отправлен, но ответа нет
        errorMessage = 'Не удалось подключиться к серверу. Проверьте интернет-соединение.';
        canRetry = retryAttempt < 2;
      } else {
        // Ошибка при настройке запроса
        errorMessage = 'Ошибка при отправке запроса. Попробуйте еще раз.';
      }

      setError(errorMessage);

      const errorChatMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: errorMessage + (canRetry && retryAttempt < 2 ? ' Попробую еще раз...' : ''),
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, errorChatMessage]);

      // Автоматический retry для сетевых ошибок
      if (canRetry && retryAttempt < 2) {
        setRetryCount(retryAttempt + 1);
        setTimeout(() => {
          sendMessage(messageText, retryAttempt + 1);
        }, 2000 * (retryAttempt + 1)); // Экспоненциальная задержка
        return;
      }
    } finally {
      setLoading(false);
    }
  };

  const retryLastMessage = () => {
    if (messages.length > 0) {
      // Находим последнее пользовательское сообщение
      const lastUserMessage = [...messages].reverse().find(msg => msg.role === 'user');
      if (lastUserMessage) {
        // Удаляем последнее сообщение об ошибке, если оно есть
        setMessages(prev => {
          const lastIndex = prev.length - 1;
          if (lastIndex >= 0 && prev[lastIndex].role === 'assistant') {
            const lastMsg = prev[lastIndex].content.toLowerCase();
            if (lastMsg.includes('извините') || lastMsg.includes('ошибка') || lastMsg.includes('не удалось')) {
              return prev.slice(0, -1);
            }
          }
          return prev;
        });
        setError(null);
        sendMessage(lastUserMessage.content);
      }
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleQuickAction = (action: QuickAction) => {
    sendMessage(action.message);
  };

  return (
    <div className="flex flex-col h-screen max-w-4xl mx-auto p-4">
      {/* Заголовок с кнопкой очистки истории */}
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold text-concrete-800">GLAME AI Stylist</h1>
        {messages.length > 0 && (
          <button
            onClick={clearHistory}
            className="px-4 py-2 text-sm text-concrete-600 hover:text-concrete-800 border border-concrete-300 rounded-lg hover:bg-concrete-50 transition"
            title="Очистить историю диалога"
          >
            Очистить историю
          </button>
        )}
      </div>

      {/* Ближайшие магазины */}
      {nearestStores.length > 0 && (
        <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <h3 className="text-sm font-semibold text-blue-900 mb-2">Ближайшие магазины</h3>
          <div className="space-y-2">
            {nearestStores.map((store) => (
              <div key={store.id} className="text-sm text-blue-800">
                <strong>{store.name}</strong> - {store.distance_km} км
                {store.address && <div className="text-xs text-blue-600">{store.address}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto mb-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-concrete-500 mt-8">
            <h2 className="text-2xl font-bold mb-4">Добро пожаловать в GLAME AI Stylist!</h2>
            <p className="mb-6">Я помогу вам подобрать идеальный образ. Выберите быстрый вариант или напишите свой запрос.</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 max-w-4xl mx-auto">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.id}
                  onClick={() => handleQuickAction(action)}
                  className="px-4 py-2 bg-gold-500 text-white rounded-lg hover:bg-gold-600 transition text-sm shadow-gold"
                >
                  {action.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-lg p-4 ${
                message.role === 'user'
                  ? 'bg-metallic-400 text-white'
                  : 'bg-concrete-200 text-concrete-800'
              }`}
            >
              <p className="whitespace-pre-wrap">{message.content}</p>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-concrete-200 rounded-lg p-4">
              <div className="flex items-center gap-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gold-500"></div>
                <p className="text-concrete-600">
                  {retryCount > 0 ? `Повторная попытка (${retryCount})...` : 'Думаю...'}
                </p>
              </div>
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <p className="text-red-800 font-medium">Ошибка</p>
                <p className="text-red-600 text-sm mt-1">{error}</p>
              </div>
              <button
                onClick={retryLastMessage}
                className="ml-4 px-3 py-1 text-sm bg-red-500 text-white rounded hover:bg-red-600 transition"
              >
                Повторить
              </button>
            </div>
          </div>
        )}

        {currentResponse && (
          <div className="space-y-4">
            {currentResponse.looks.length > 0 && (
              <div>
                <h3 className="text-lg font-semibold mb-2">Рекомендованные образы:</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {currentResponse.looks.map((look) => {
                    const normalized = {
                      ...look,
                      product_ids: (look as LookWithProducts).product_ids ?? look.products?.map((p) => p.id) ?? [],
                      description: (look as LookWithProducts).description ?? null,
                      image_url: (look as LookWithProducts).image_url ?? null,
                    };
                    return <LookCard key={normalized.id} look={normalized as LookWithProducts} />;
                  })}
                </div>
              </div>
            )}

            {/* Показываем товары из отдельного поля products, если оно есть */}
            {currentResponse.products && currentResponse.products.length > 0 && (
              <div>
                <h3 className="text-lg font-semibold mb-2">Рекомендованные товары:</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {currentResponse.products.map((product) => (
                    <ProductCard key={product.id} product={product as any} />
                  ))}
                </div>
              </div>
            )}

            {/* Fallback: показываем товары из образов, если отдельного поля products нет */}
            {(!currentResponse.products || currentResponse.products.length === 0) &&
              currentResponse.looks.some((look) => look.products.length > 0) && (
                <div>
                  <h3 className="text-lg font-semibold mb-2">Товары в образах:</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {currentResponse.looks.flatMap((look) =>
                      look.products.map((product) => (
                        <ProductCard key={product.id} product={product as any} />
                      ))
                    )}
                  </div>
                </div>
              )}

            {currentResponse.cta && (
              <div className="text-center">
                <button className="px-6 py-3 bg-gold-500 text-white rounded-lg hover:bg-gold-600 transition font-semibold shadow-gold">
                  {currentResponse.cta}
                </button>
              </div>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Напишите ваш запрос..."
          className="flex-1 px-4 py-2 border border-concrete-300 rounded-lg bg-white text-concrete-900 placeholder:text-concrete-400 caret-gold-500 focus:outline-none focus:ring-2 focus:ring-gold-500"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="px-6 py-2 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed transition shadow-gold"
        >
          Отправить
        </button>
      </form>

      {/* Quick actions всегда доступны (после первого сообщения тоже) */}
      <div className="mt-3 flex flex-wrap gap-2">
        {QUICK_ACTIONS.slice(0, 8).map((action) => (
          <button
            key={action.id}
            onClick={() => handleQuickAction(action)}
            disabled={loading}
            className="px-3 py-1.5 text-xs border border-concrete-300 rounded-full hover:bg-concrete-50 disabled:opacity-50 disabled:cursor-not-allowed transition"
            title={action.message}
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  );
}
