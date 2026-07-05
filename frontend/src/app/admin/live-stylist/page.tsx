'use client';

import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import {
  LiveStylistAttachableProduct,
  LiveStylistConversation,
  LiveStylistConversationDetail,
  LiveStylistInboxBadge,
  LiveStylistUserInfo,
  api,
  liveStylistAdmin,
} from '@/lib/api';
import type { Product } from '@/types';
import {
  getBrowserNotificationPermission,
  getLiveStylistBrowserNotificationsEnabled,
  getLiveStylistSoundNotificationsEnabled,
  getLiveStylistVibrationNotificationsEnabled,
  isLiveStylistVibrationSupported,
  requestBrowserNotificationPermission,
  setLiveStylistBrowserNotificationsEnabled,
  setLiveStylistSoundNotificationsEnabled,
  setLiveStylistVibrationNotificationsEnabled,
} from '@/lib/liveStylistNotifications';

function formatDateTime(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date);
}

function formatDurationMinutes(minutes?: number | null) {
  const total = Math.max(0, Math.floor(Number(minutes || 0)));
  if (total < 60) return `${total} мин`;
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (hours < 24) return rest ? `${hours} ч ${rest} мин` : `${hours} ч`;
  const days = Math.floor(hours / 24);
  const dayHours = hours % 24;
  return dayHours ? `${days} д ${dayHours} ч` : `${days} д`;
}

function minutesSince(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
}

function conversationWorkDurationMinutes(item: LiveStylistConversation) {
  if (item.status !== 'in_progress') return null;
  return minutesSince(item.first_response_at || item.updated_at || item.created_at);
}

function formatCurrencyKopec(value?: number | null) {
  const amount = Number(value || 0) / 100;
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(amount);
}

function attentionReasonLabel(reason?: string | null) {
  if (reason === 'overdue_first_response') return 'Просрочен первый ответ';
  if (reason === 'unassigned_request') return 'Новый запрос без назначения';
  if (reason === 'unread_customer_message') return 'Есть непрочитанное сообщение';
  return 'Требует внимания';
}

function buildCustomerSummary(detail: LiveStylistConversationDetail | null) {
  if (!detail) return '';
  const context = detail.customer_context;
  const customer = detail.conversation.customer;
  const parts: string[] = [];
  parts.push(
    `Покупатель: ${customer.full_name || customer.phone || customer.email || customer.id}.`
  );
  if (context.customer_segment) {
    parts.push(`Сегмент: ${context.customer_segment}.`);
  }
  if (context.discount_card_number) {
    parts.push(`Бонусная карта: ${context.discount_card_number}.`);
  }
  parts.push(`Баллы: ${context.loyalty_points}.`);
  parts.push(`Покупок: ${context.total_purchases}, сумма покупок: ${formatCurrencyKopec(context.total_spent)}.`);
  if (context.average_check) {
    parts.push(`Средний чек: ${formatCurrencyKopec(context.average_check)}.`);
  }
  if (context.favorite_categories.length) {
    parts.push(`Любимые категории: ${context.favorite_categories.slice(0, 4).join(', ')}.`);
  }
  if (context.favorite_brands.length) {
    parts.push(`Любимые бренды: ${context.favorite_brands.slice(0, 4).join(', ')}.`);
  }
  if (context.favorite_products.length) {
    parts.push(
      `Избранные товары: ${context.favorite_products
        .slice(0, 3)
        .map((item) => item.name || item.id)
        .join(', ')}.`
    );
  }
  if (context.favorite_looks.length) {
    parts.push(
      `Избранные образы: ${context.favorite_looks
        .slice(0, 2)
        .map((item) => item.look_name || item.look_id)
        .join(', ')}.`
    );
  }
  if (context.recent_purchases.length) {
    const latest = context.recent_purchases[0];
    parts.push(
      `Последняя покупка: ${latest.product_name || latest.product_id || 'товар'} ${latest.brand ? `(${latest.brand})` : ''}, ${formatCurrencyKopec(latest.total_amount)}.`
    );
  }
  return parts.join(' ');
}

type ComposerPhoto = {
  id: string;
  file: File;
  previewUrl: string;
  name: string;
};

type ProductCardPreview = {
  id: string;
  name?: string | null;
  brand?: string | null;
  category?: string | null;
  article?: string | null;
  external_code?: string | null;
  price?: number | null;
  image_url?: string | null;
  in_stock?: boolean;
};

type RecommendedProductCard = ProductCardPreview & {
  stock?: number | null;
};

function buildAttachmentPreviewText(
  text: string,
  products: LiveStylistAttachableProduct[],
  photos: ComposerPhoto[],
) {
  const cleanText = text.trim();
  if (cleanText) return cleanText;
  if (photos.length && products.length) return `Фото и товары: ${photos.length} / ${products.length}`;
  if (photos.length) return `Фотосообщение (${photos.length})`;
  if (products.length) return `Рекомендованы товары (${products.length})`;
  return 'Сообщение без текста';
}

const QUICK_REPLY_CHIPS = [
  'Для себя',
  'В подарок',
  'Под образ',
  'Нужен комплект',
  'Хочу примерить',
] as const;

export default function LiveStylistAdminPage() {
  const [conversations, setConversations] = useState<LiveStylistConversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LiveStylistConversationDetail | null>(null);
  const [stylists, setStylists] = useState<LiveStylistUserInfo[]>([]);
  const [badge, setBadge] = useState<LiveStylistInboxBadge | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [messageText, setMessageText] = useState('');
  const [composerFocused, setComposerFocused] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [ownershipFilter, setOwnershipFilter] = useState('all');
  const [purchaseFilter, setPurchaseFilter] = useState('all');
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [browserNotificationsEnabled, setBrowserNotificationsEnabled] = useState(false);
  const [soundNotificationsEnabled, setSoundNotificationsEnabled] = useState(true);
  const [vibrationNotificationsEnabled, setVibrationNotificationsEnabled] = useState(true);
  const [vibrationSupported, setVibrationSupported] = useState(false);
  const [productSearch, setProductSearch] = useState('');
  const [productSearchLoading, setProductSearchLoading] = useState(false);
  const [productSearchResults, setProductSearchResults] = useState<LiveStylistAttachableProduct[]>([]);
  const [selectedProducts, setSelectedProducts] = useState<LiveStylistAttachableProduct[]>([]);
  const [selectedPhotos, setSelectedPhotos] = useState<ComposerPhoto[]>([]);
  const [previewProduct, setPreviewProduct] = useState<ProductCardPreview | null>(null);
  const [recommendedProducts, setRecommendedProducts] = useState<RecommendedProductCard[]>([]);
  const [workspaceTab, setWorkspaceTab] = useState<'chat' | 'selection' | 'case'>('chat');
  const [isInboxPanelOpen, setIsInboxPanelOpen] = useState(false);
  const [isCustomerPanelOpen, setIsCustomerPanelOpen] = useState(false);
  const [notificationPermission, setNotificationPermission] = useState<
    NotificationPermission | 'unsupported'
  >('unsupported');
  const [alertBannerPulse, setAlertBannerPulse] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const selectedIdRef = useRef<string | null>(null);
  const messagesScrollRef = useRef<HTMLDivElement | null>(null);
  const photoInputRef = useRef<HTMLInputElement | null>(null);
  const productSearchRequestRef = useRef(0);
  const typingDebounceRef = useRef<number | null>(null);
  const typingKeepAliveRef = useRef<number | null>(null);
  const activeTypingConversationRef = useRef<string | null>(null);

  const mergeConversationSummary = (updated: LiveStylistConversation) => {
    setConversations((current) => {
      const exists = current.some((item) => item.id === updated.id);
      if (!exists) {
        return [updated, ...current];
      }
      return current.map((item) => (item.id === updated.id ? updated : item));
    });
  };

  const releasePhotoPreviews = (photos: ComposerPhoto[]) => {
    for (const photo of photos) {
      URL.revokeObjectURL(photo.previewUrl);
    }
  };

  const clearTypingTimers = () => {
    if (typingDebounceRef.current) {
      window.clearTimeout(typingDebounceRef.current);
      typingDebounceRef.current = null;
    }
    if (typingKeepAliveRef.current) {
      window.clearInterval(typingKeepAliveRef.current);
      typingKeepAliveRef.current = null;
    }
  };

  const syncStylistTypingState = async (conversationId: string, isTyping: boolean) => {
    try {
      await liveStylistAdmin.setTypingState(conversationId, isTyping);
      if (isTyping) {
        activeTypingConversationRef.current = conversationId;
      } else if (activeTypingConversationRef.current === conversationId) {
        activeTypingConversationRef.current = null;
      }
    } catch {
      // Ignore typing state transport errors; they should not block the chat workflow.
    }
  };

  const loadList = async (keepSelection: boolean = true) => {
    setLoading(true);
    setError(null);
    try {
      const [nextConversations, nextStylists, nextBadge] = await Promise.all([
        liveStylistAdmin.listConversations({
          status: statusFilter === 'all' ? undefined : statusFilter,
          purchase_status: purchaseFilter === 'all' ? undefined : purchaseFilter,
          search: search.trim() || undefined,
          mine_only: ownershipFilter === 'mine' ? true : undefined,
          unassigned_only: ownershipFilter === 'unassigned' ? true : undefined,
          attention_only: attentionOnly ? true : undefined,
        }),
        liveStylistAdmin.listStylists(),
        liveStylistAdmin.getInboxBadge(),
      ]);
      setConversations(nextConversations);
      setStylists(nextStylists);
      setBadge(nextBadge);
      if (!keepSelection) {
        setSelectedId(null);
      } else if (selectedId && !nextConversations.some((item) => item.id === selectedId)) {
        setSelectedId(null);
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось загрузить обращения');
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (conversationId: string, options?: { background?: boolean }) => {
    if (!options?.background) {
      setDetailLoading(true);
      setError(null);
    }
    try {
      const nextDetail = await liveStylistAdmin.getConversation(conversationId);
      if (selectedIdRef.current !== conversationId) return;
      setDetail(nextDetail);
      mergeConversationSummary(nextDetail.conversation);
      const nextBadge = await liveStylistAdmin.getInboxBadge();
      if (selectedIdRef.current !== conversationId) return;
      setBadge(nextBadge);
    } catch (e: any) {
      if (!options?.background) {
        setError(e.response?.data?.detail || e.message || 'Не удалось загрузить диалог');
      }
    } finally {
      if (!options?.background) {
        setDetailLoading(false);
      }
    }
  };

  useEffect(() => {
    setBrowserNotificationsEnabled(getLiveStylistBrowserNotificationsEnabled());
    setSoundNotificationsEnabled(getLiveStylistSoundNotificationsEnabled());
    setVibrationNotificationsEnabled(getLiveStylistVibrationNotificationsEnabled());
    setVibrationSupported(isLiveStylistVibrationSupported());
    setNotificationPermission(getBrowserNotificationPermission());
  }, []);

  useEffect(() => {
    loadList(false);
    const interval = window.setInterval(() => {
      loadList(true);
    }, 10000);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, ownershipFilter, purchaseFilter, attentionOnly]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadList(true);
    }, 350);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    return () => {
      clearTypingTimers();
      if (activeTypingConversationRef.current) {
        void liveStylistAdmin.setTypingState(activeTypingConversationRef.current, false);
      }
    };
  }, []);

  useEffect(() => {
    const previousConversationId = activeTypingConversationRef.current;
    if (previousConversationId && previousConversationId !== selectedId) {
      clearTypingTimers();
      activeTypingConversationRef.current = null;
      void liveStylistAdmin.setTypingState(previousConversationId, false);
    }
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setRecommendedProducts([]);
      return;
    }
    void loadDetail(selectedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    const interval = window.setInterval(() => {
      if (!saving) {
        void loadDetail(selectedId, { background: true });
      }
    }, 3000);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, saving]);

  useEffect(() => {
    if (!detail?.messages?.length) return;
    const container = messagesScrollRef.current;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
  }, [detail?.messages]);

  useEffect(() => {
    setProductSearch('');
    setProductSearchResults([]);
    setSelectedProducts([]);
    setRecommendedProducts([]);
    setComposerFocused(false);
    releasePhotoPreviews(selectedPhotos);
    setSelectedPhotos([]);
    setWorkspaceTab('chat');
    setIsInboxPanelOpen(false);
    setIsCustomerPanelOpen(false);
    if (photoInputRef.current) {
      photoInputRef.current.value = '';
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  useEffect(() => {
    return () => {
      releasePhotoPreviews(selectedPhotos);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const query = productSearch.trim();
    if (!query) {
      setProductSearchResults([]);
      setProductSearchLoading(false);
      return;
    }
    if (query.length < 2) {
      setProductSearchResults([]);
      setProductSearchLoading(false);
      return;
    }
    const timer = window.setTimeout(() => {
      void searchProducts(query, { silentShortQuery: true, silentNoResults: true });
    }, 350);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productSearch]);

  useEffect(() => {
    const conversationId = selectedId;
    const hasTypingDraft = Boolean(conversationId && composerFocused && messageText.trim().length > 0);
    clearTypingTimers();

    if (!conversationId || !hasTypingDraft) {
      if (conversationId && activeTypingConversationRef.current === conversationId) {
        void syncStylistTypingState(conversationId, false);
      }
      return;
    }

    typingDebounceRef.current = window.setTimeout(() => {
      void syncStylistTypingState(conversationId, true);
      typingKeepAliveRef.current = window.setInterval(() => {
        void syncStylistTypingState(conversationId, true);
      }, 2500);
    }, 350);

    return () => {
      clearTypingTimers();
    };
  }, [composerFocused, messageText, selectedId]);

  useEffect(() => {
    const ids = detail?.conversation.recommended_product_ids || [];
    if (!ids.length) {
      setRecommendedProducts([]);
      return;
    }

    let cancelled = false;

    const loadRecommendedProducts = async () => {
      const products = await Promise.all(
        Array.from(new Set(ids)).map(async (id) => {
          try {
            const product = (await api.getProduct(id)) as Product;
            return {
              id: product.id,
              name: product.name,
              brand: product.brand,
              category: product.category,
              article: product.article,
              external_code: product.external_code,
              price: product.price,
              image_url: product.images?.[0] || null,
              stock: product.stock,
              in_stock: typeof product.stock === 'number' ? product.stock > 0 : undefined,
            } satisfies RecommendedProductCard;
          } catch {
            return {
              id,
              name: id,
            } satisfies RecommendedProductCard;
          }
        })
      );
      if (!cancelled) {
        setRecommendedProducts(products);
      }
    };

    void loadRecommendedProducts();

    return () => {
      cancelled = true;
    };
  }, [detail?.conversation.recommended_product_ids]);

  const selectedConversation = useMemo(
    () => conversations.find((item) => item.id === selectedId) || null,
    [conversations, selectedId]
  );
  const firstAlertConversation = useMemo(
    () =>
      conversations.find((item) => item.unread_for_stylist_count > 0) ||
      conversations.find((item) => item.needs_attention) ||
      conversations.find((item) => item.status === 'requested') ||
      null,
    [conversations]
  );
  const hasActiveAlerts = Boolean(
    (badge?.total_unread_messages || 0) > 0 ||
      (badge?.requested_conversations || 0) > 0 ||
      (badge?.attention_conversations || 0) > 0
  );
  const badgeTotalUnread = badge?.total_unread_messages || 0;
  const badgeRequested = badge?.requested_conversations || 0;
  const badgeAttention = badge?.attention_conversations || 0;
  const customerSummary = useMemo(() => buildCustomerSummary(detail), [detail]);
  const recommendedProductsMap = useMemo(
    () => new Map(recommendedProducts.map((item) => [item.id, item])),
    [recommendedProducts]
  );

  const handleBrowserNotificationsToggle = async (checked: boolean) => {
    if (!checked) {
      setLiveStylistBrowserNotificationsEnabled(false);
      setBrowserNotificationsEnabled(false);
      return;
    }
    const permission = await requestBrowserNotificationPermission();
    setNotificationPermission(permission);
    const enabled = permission === 'granted';
    setLiveStylistBrowserNotificationsEnabled(enabled);
    setBrowserNotificationsEnabled(enabled);
    if (!enabled) {
      setError('Браузер не разрешил desktop-уведомления');
    }
  };

  const handleSoundNotificationsToggle = (checked: boolean) => {
    setLiveStylistSoundNotificationsEnabled(checked);
    setSoundNotificationsEnabled(checked);
  };

  const handleVibrationNotificationsToggle = (checked: boolean) => {
    setLiveStylistVibrationNotificationsEnabled(checked);
    setVibrationNotificationsEnabled(checked);
  };

  useEffect(() => {
    const hasNewDelta = badgeTotalUnread > 0 || badgeRequested > 0 || badgeAttention > 0;
    if (!hasNewDelta) {
      setAlertBannerPulse(false);
      return;
    }
    setAlertBannerPulse(true);
    if (typeof window !== 'undefined' && window.innerWidth < 1280) {
      setIsInboxPanelOpen(true);
    }
    const timer = window.setTimeout(() => setAlertBannerPulse(false), 5000);
    return () => window.clearTimeout(timer);
  }, [badgeAttention, badgeRequested, badgeTotalUnread]);

  const focusFirstAlertConversation = () => {
    if (!firstAlertConversation) return;
    setSelectedId(firstAlertConversation.id);
    setWorkspaceTab('chat');
    setIsInboxPanelOpen(false);
  };

  const copyToClipboard = async (value: string, successMessage: string, emptyMessage: string) => {
    if (!value.trim()) {
      setError(emptyMessage);
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setError(null);
      setSuccess(successMessage);
    } catch {
      setError('Не удалось скопировать в буфер обмена');
    }
  };

  const openCustomerCard = () => {
    const customerId = detail?.customer_context.customer_id || selectedConversation?.customer.id;
    if (!customerId) return;
    window.open(`/admin/customers/${customerId}`, '_blank', 'noopener,noreferrer');
  };

  const openCustomerPurchases = () => {
    const customerId = detail?.customer_context.customer_id || selectedConversation?.customer.id;
    if (!customerId) return;
    window.open(`/admin/customers/${customerId}?tab=purchases`, '_blank', 'noopener,noreferrer');
  };

  const insertCustomerSummaryIntoReply = () => {
    if (!customerSummary.trim()) {
      setError('Резюме клиента пока недоступно');
      return;
    }
    setMessageText((current) => (current.trim() ? `${current.trim()}\n\n${customerSummary}` : customerSummary));
    setSuccess('Резюме клиента добавлено в ответ');
  };

  const openProductCard = (product: ProductCardPreview) => {
    setPreviewProduct(product);
  };

  const renderRecommendedProducts = (ids: string[], options?: { compact?: boolean; emptyText?: string }) => {
    if (!ids.length) {
      return <div className="text-sm text-gray-500">{options?.emptyText || 'Рекомендованных товаров пока нет.'}</div>;
    }

    return (
      <div className={options?.compact ? 'space-y-2' : 'grid gap-3 sm:grid-cols-2 xl:grid-cols-3'}>
        {ids.map((id) => {
          const product = recommendedProductsMap.get(id);
          const availabilityText =
            product?.in_stock === false
              ? 'Нет в наличии'
              : product?.stock && product.stock > 0
                ? `В наличии: ${Math.floor(product.stock)} шт.`
                : product?.in_stock === true
                  ? 'В наличии'
                  : 'Наличие уточняется';

          return (
            <button
              key={id}
              type="button"
              onClick={() => openProductCard(product || { id, name: id })}
              className={`w-full overflow-hidden rounded-md border border-gray-200 bg-white text-left transition hover:border-gray-300 hover:bg-gray-50 ${
                options?.compact ? 'p-2' : 'p-3'
              }`}
            >
              <div className="flex gap-3">
                <div
                  className={`shrink-0 overflow-hidden rounded border border-gray-200 bg-gray-50 ${
                    options?.compact ? 'h-14 w-14' : 'h-20 w-20'
                  }`}
                >
                  {product?.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={product.image_url} alt={product.name || product.id} className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-[10px] text-gray-400">Нет фото</div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-2 text-sm font-medium text-gray-900">{product?.name || id}</div>
                  <div className="mt-1 text-xs text-gray-500">
                    {[product?.brand, product?.article || product?.external_code].filter(Boolean).join(' · ') ||
                      'Товар из рекомендаций'}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="text-sm font-semibold text-gray-900">
                      {product?.price ? formatCurrencyKopec(product.price) : 'Цена уточняется'}
                    </span>
                    <span
                      className={`text-xs font-medium ${
                        product?.in_stock === false ? 'text-red-700' : 'text-emerald-700'
                      }`}
                    >
                      {availabilityText}
                    </span>
                  </div>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    );
  };

  const searchProducts = async (
    rawQuery?: string,
    options?: { silentShortQuery?: boolean; silentNoResults?: boolean }
  ) => {
    const query = (rawQuery ?? productSearch).trim();
    if (query.length < 2) {
      setProductSearchResults([]);
      if (!options?.silentShortQuery) {
        setError('Введите минимум 2 символа для поиска по артикулу, названию или бренду');
      }
      return;
    }
    const requestId = Date.now() + Math.random();
    productSearchRequestRef.current = requestId;
    setProductSearchLoading(true);
    setError(null);
    try {
      const results = await liveStylistAdmin.searchProducts(query, 8);
      if (productSearchRequestRef.current !== requestId) return;
      setProductSearchResults(results);
      if (!results.length && !options?.silentNoResults) {
        setSuccess('Товары по этому запросу не найдены');
      }
    } catch (e: any) {
      if (productSearchRequestRef.current !== requestId) return;
      setError(e.response?.data?.detail || e.message || 'Не удалось найти товары');
    } finally {
      if (productSearchRequestRef.current === requestId) {
        setProductSearchLoading(false);
      }
    }
  };

  const addSelectedProduct = (product: LiveStylistAttachableProduct) => {
    setSelectedProducts((current) => {
      if (current.some((item) => item.id === product.id)) return current;
      return [...current, product];
    });
    setSuccess('Карточка товара добавлена к сообщению');
  };

  const removeSelectedProduct = (productId: string) => {
    setSelectedProducts((current) => current.filter((item) => item.id !== productId));
  };

  const handlePhotoSelection = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    const imageFiles = files.filter((file) => file.type.startsWith('image/'));
    if (!imageFiles.length) {
      setError('Можно прикреплять только изображения');
      return;
    }
    const nextPhotos = imageFiles.map((file) => ({
      id: `${file.name}-${file.size}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      file,
      previewUrl: URL.createObjectURL(file),
      name: file.name,
    }));
    setSelectedPhotos((current) => [...current, ...nextPhotos]);
    if (photoInputRef.current) {
      photoInputRef.current.value = '';
    }
  };

  const removeSelectedPhoto = (photoId: string) => {
    setSelectedPhotos((current) => {
      const target = current.find((item) => item.id === photoId);
      if (target) {
        URL.revokeObjectURL(target.previewUrl);
      }
      return current.filter((item) => item.id !== photoId);
    });
  };

  const applyQuickReplyChip = (chip: string) => {
    const prompt = `Запрос клиента: ${chip}.`;
    setMessageText((current) => {
      if (!current.trim()) return prompt;
      if (current.includes(prompt)) return current;
      return `${current.trim()}\n${prompt}`;
    });
    setSuccess(`Добавлен сценарий: ${chip}`);
  };

  const updateConversation = async (payload: Parameters<typeof liveStylistAdmin.updateConversation>[1]) => {
    if (!selectedId) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await liveStylistAdmin.updateConversation(selectedId, payload);
      setConversations((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      if (detail) {
        setDetail({ ...detail, conversation: updated });
      }
      setBadge(await liveStylistAdmin.getInboxBadge());
      setSuccess('Изменения сохранены');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить изменения');
    } finally {
      setSaving(false);
    }
  };

  const assignToMe = async () => {
    if (!selectedId) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await liveStylistAdmin.assignConversation(selectedId);
      setConversations((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      if (detail) {
        setDetail({ ...detail, conversation: updated });
      }
      setSuccess('Обращение назначено');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось назначить обращение');
    } finally {
      setSaving(false);
    }
  };

  const clearConversationMessages = async () => {
    if (!selectedId) return;
    const confirmed = window.confirm(
      'Очистить чат в этом обращении? Вся история сообщений будет удалена без возможности восстановления.'
    );
    if (!confirmed) return;

    clearTypingTimers();
    setComposerFocused(false);
    void syncStylistTypingState(selectedId, false);
    releasePhotoPreviews(selectedPhotos);
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const nextDetail = await liveStylistAdmin.clearConversationMessages(selectedId);
      setDetail(nextDetail);
      mergeConversationSummary(nextDetail.conversation);
      setBadge(await liveStylistAdmin.getInboxBadge());
      setMessageText('');
      setSelectedProducts([]);
      setSelectedPhotos([]);
      setProductSearch('');
      setProductSearchResults([]);
      setRecommendedProducts([]);
      if (photoInputRef.current) {
        photoInputRef.current.value = '';
      }
      setSuccess('Чат очищен');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось очистить чат');
    } finally {
      setSaving(false);
    }
  };

  const sendReply = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedId || (!messageText.trim() && !selectedProducts.length && !selectedPhotos.length)) return;
    clearTypingTimers();
    setComposerFocused(false);
    void syncStylistTypingState(selectedId, false);
    const textValue = messageText.trim();
    const attachedProducts = [...selectedProducts];
    const attachedPhotos = [...selectedPhotos];
    const previousDetail = detail;
    const previousConversations = conversations;
    const tempMessageId = `temp-${Date.now()}`;
    const nowIso = new Date().toISOString();
    const optimisticAttachments = [
      ...attachedProducts.map((product) => ({
        type: 'product',
        product_id: product.id,
        name: product.name,
        brand: product.brand,
        category: product.category,
        article: product.article,
        external_code: product.external_code,
        price: product.price,
        image_url: product.image_url,
        in_stock: product.in_stock,
      })),
      ...attachedPhotos.map((photo) => ({
        type: 'image',
        url: photo.previewUrl,
        name: photo.name,
      })),
    ];
    const previewText = buildAttachmentPreviewText(textValue, attachedProducts, attachedPhotos);
    setSaving(true);
    setError(null);
    setSuccess(null);
    setMessageText('');
    setSelectedProducts([]);
    setSelectedPhotos([]);
    setProductSearch('');
    setProductSearchResults([]);
    if (photoInputRef.current) {
      photoInputRef.current.value = '';
    }
    setDetail((current) => {
      if (!current || current.conversation.id !== selectedId) return current;
      const mergedRecommended = Array.from(
        new Set([
          ...(current.conversation.recommended_product_ids || []),
          ...attachedProducts.map((item) => item.id),
        ]),
      );
      return {
        ...current,
        conversation: {
          ...current.conversation,
          status: current.conversation.status === 'requested' ? 'in_progress' : current.conversation.status,
          status_label: current.conversation.status === 'requested' ? 'В обработке' : current.conversation.status_label,
          last_message_at: nowIso,
          last_message_preview: previewText,
          unread_for_stylist_count: 0,
          assigned_stylist: current.conversation.assigned_stylist,
          recommended_product_ids: mergedRecommended,
        },
        messages: [
          ...current.messages,
          {
            id: tempMessageId,
            conversation_id: selectedId,
            user_id: current.conversation.customer.id,
            sender_user_id: current.conversation.assigned_stylist?.id || null,
            role: 'stylist',
            text: textValue || null,
            attachments: optimisticAttachments,
            payload: {
              pending: true,
              products: attachedProducts.map((product) => ({
                id: product.id,
                name: product.name,
                brand: product.brand,
                price: product.price,
                images: product.image_url ? [product.image_url] : [],
                category: product.category,
                article: product.article,
                external_code: product.external_code,
              })),
            },
            created_at: nowIso,
            sender: current.conversation.assigned_stylist || undefined,
          },
        ],
      };
    });
    setConversations((current) =>
      current.map((item) =>
        item.id === selectedId
          ? {
              ...item,
              status: item.status === 'requested' ? 'in_progress' : item.status,
              status_label: item.status === 'requested' ? 'В обработке' : item.status_label,
              last_message_at: nowIso,
              last_message_preview: previewText,
              unread_for_stylist_count: 0,
              recommended_product_ids: Array.from(
                new Set([
                  ...(item.recommended_product_ids || []),
                  ...attachedProducts.map((product) => product.id),
                ]),
              ),
            }
          : item
      )
    );
    try {
      const nextDetail = await liveStylistAdmin.sendComposedMessage(selectedId, {
        text: textValue,
        product_ids: attachedProducts.map((item) => item.id),
        photos: attachedPhotos.map((item) => item.file),
      });
      releasePhotoPreviews(attachedPhotos);
      setDetail(nextDetail);
      mergeConversationSummary(nextDetail.conversation);
      setBadge(await liveStylistAdmin.getInboxBadge());
      setSuccess('Сообщение отправлено');
    } catch (e: any) {
      setDetail(previousDetail);
      setConversations(previousConversations);
      setMessageText(textValue);
      setSelectedProducts(attachedProducts);
      setSelectedPhotos(attachedPhotos);
      setError(e.response?.data?.detail || e.message || 'Не удалось отправить сообщение');
    } finally {
      setSaving(false);
    }
  };

  const workspaceTabs = [
    { id: 'chat' as const, label: 'Чат' },
    { id: 'selection' as const, label: 'Подбор' },
    { id: 'case' as const, label: 'Обращение' },
  ];

  const draftProductsBlock = !!selectedProducts.length && (
      <div className="space-y-2 rounded-md border border-gray-200 bg-white p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500">Карточки в сообщении</div>
      <div className="space-y-2">
        {selectedProducts.map((product) => (
          <div key={product.id} className="flex items-center gap-3 rounded-md border border-gray-200 p-2">
            <div className="h-14 w-14 shrink-0 overflow-hidden rounded border border-gray-200 bg-gray-50">
              {product.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={product.image_url} alt={product.name || product.id} className="h-full w-full object-cover" />
              ) : null}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-gray-900">{product.name || product.id}</div>
              <div className="text-xs text-gray-500">
                {[product.brand, product.category, product.article || product.external_code].filter(Boolean).join(' · ') || 'Карточка товара'}
              </div>
            </div>
            <button
              type="button"
              onClick={() => openProductCard(product)}
              className="rounded-md border border-gray-300 px-4 py-3 text-sm text-gray-700 hover:bg-gray-50"
            >
              Карточка
            </button>
            <button
              type="button"
              onClick={() => removeSelectedProduct(product.id)}
            className="rounded-md border border-red-200 px-4 py-3 text-sm text-red-700 hover:bg-red-50"
            >
              Удалить
            </button>
          </div>
        ))}
      </div>
    </div>
  );

  const draftPhotosBlock = !!selectedPhotos.length && (
    <div className="space-y-2 rounded-md border border-gray-200 bg-white p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500">Фото в сообщении</div>
      <div className="flex flex-wrap gap-3">
        {selectedPhotos.map((photo) => (
          <div key={photo.id} className="rounded-md border border-gray-200 p-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={photo.previewUrl} alt={photo.name} className="h-24 w-24 rounded object-cover" />
            <div className="mt-2 w-24 truncate text-xs text-gray-500">{photo.name}</div>
            <button
              type="button"
              onClick={() => removeSelectedPhoto(photo.id)}
            className="mt-2 w-full rounded-md border border-red-200 px-3 py-2 text-sm text-red-700 hover:bg-red-50"
            >
              Удалить
            </button>
          </div>
        ))}
      </div>
    </div>
  );

  const selectionWorkspaceContent = (
    <div className="space-y-4 p-4">
      <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
        <div className="mb-2 text-sm font-medium text-gray-900">Подбор украшений</div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={productSearch}
            onChange={(e) => setProductSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void searchProducts();
              }
            }}
            placeholder="Артикул, название или бренд"
            className="min-w-[220px] flex-1 rounded-md border border-gray-300 bg-white px-4 py-3 text-base"
          />
          <button
            type="button"
            onClick={() => void searchProducts()}
            disabled={productSearchLoading}
            className="rounded-md border border-gray-300 bg-white px-4 py-3 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
          >
            {productSearchLoading ? 'Поиск...' : 'Найти товар'}
          </button>
          <button
            type="button"
            onClick={() => photoInputRef.current?.click()}
            className="rounded-md border border-gray-300 bg-white px-4 py-3 text-sm text-gray-700 hover:bg-gray-100"
          >
            Прикрепить фото
          </button>
          <input
            ref={photoInputRef}
            type="file"
            accept="image/*"
            multiple
            onChange={handlePhotoSelection}
            className="hidden"
          />
        </div>
          <div className="mt-2 text-xs text-gray-500">
          Поиск работает по артикулу, названию и бренду. Выбранные товары и фото прикрепляются к следующему сообщению стилиста.
        </div>
      </div>

      {!!productSearchResults.length && (
        <div className="space-y-2 rounded-md border border-gray-200 bg-white p-3">
          <div className="text-xs font-medium uppercase tracking-wide text-gray-500">Найденные товары</div>
          <div className="space-y-2">
            {productSearchResults.map((product) => (
              <div key={product.id} className="flex items-center gap-3 rounded-md border border-gray-200 p-2">
                <div className="h-14 w-14 shrink-0 overflow-hidden rounded border border-gray-200 bg-gray-50">
                  {product.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={product.image_url} alt={product.name || product.id} className="h-full w-full object-cover" />
                  ) : null}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-gray-900">{product.name || product.id}</div>
                  <div className="text-xs text-gray-500">
                    {[product.brand, product.category, product.article || product.external_code].filter(Boolean).join(' · ') || 'Без артикула'}
                  </div>
                  <div className="mt-1 text-sm text-gray-700">
                    {product.price ? formatCurrencyKopec(product.price) : 'Цена не указана'}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => openProductCard(product)}
                  className="rounded-md border border-gray-300 px-4 py-3 text-sm text-gray-700 hover:bg-gray-50"
                >
                  Карточка
                </button>
                <button
                  type="button"
                  onClick={() => addSelectedProduct(product)}
                  disabled={selectedProducts.some((item) => item.id === product.id)}
                  className="rounded-md border border-gray-300 px-4 py-3 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  {selectedProducts.some((item) => item.id === product.id) ? 'Добавлен' : 'Выбрать'}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {draftProductsBlock}
      {draftPhotosBlock}

      <div className="rounded-md border border-gray-200 bg-white p-3">
        <div className="mb-2 text-sm font-medium text-gray-900">Уже рекомендовано по этому обращению</div>
        <div className="mb-2 text-xs text-gray-500">
          Список пополняется автоматически из карточек товара, прикрепленных к сообщениям стилиста.
        </div>
        {renderRecommendedProducts(detail?.conversation.recommended_product_ids || [])}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-md border border-gray-200 bg-white p-3">
          <div className="mb-2 text-sm font-medium text-gray-900">Избранные товары покупателя</div>
          <div className="space-y-2">
            {(detail?.customer_context.favorite_products || []).map((product) => (
              <div key={product.id} className="rounded-md border border-gray-200 p-3 text-sm">
                <div className="font-medium text-gray-900">{product.name || product.id}</div>
                <div className="mt-1 text-xs text-gray-500">
                  {[product.brand, product.category, product.article].filter(Boolean).join(' · ') || 'Без категории'}
                </div>
                {product.price !== undefined && product.price !== null && (
                  <div className="mt-1 text-sm text-gray-700">{formatCurrencyKopec(product.price)}</div>
                )}
              </div>
            ))}
            {!detail?.customer_context.favorite_products?.length && (
              <div className="text-sm text-gray-500">Избранных товаров нет.</div>
            )}
          </div>
        </div>

        <div className="rounded-md border border-gray-200 bg-white p-3">
          <div className="mb-2 text-sm font-medium text-gray-900">История покупок</div>
          <div className="space-y-2">
            {(detail?.customer_context.recent_purchases || []).map((purchase) => (
              <div key={purchase.id} className="rounded-md border border-gray-200 p-3 text-sm">
                <div className="font-medium text-gray-900">{purchase.product_name || purchase.product_id || purchase.id}</div>
                <div className="mt-1 text-xs text-gray-500">
                  {[purchase.brand, purchase.category].filter(Boolean).join(' · ') || 'Без категории'}
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  {formatDateTime(purchase.purchase_date)} · {purchase.quantity} шт.
                </div>
                <div className="mt-1 text-sm text-gray-700">{formatCurrencyKopec(purchase.total_amount)}</div>
              </div>
            ))}
            {!detail?.customer_context.recent_purchases?.length && (
              <div className="text-sm text-gray-500">История покупок пока пуста.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  const customerProfileContent = (
    <div className="space-y-4 p-4">
      <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
        <div className="mb-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() =>
              void copyToClipboard(
                detail?.customer_context.discount_card_number || '',
                'Номер бонусной карты скопирован',
                'У покупателя нет бонусной карты'
              )
            }
            className="rounded-md border border-gray-300 bg-white px-4 py-3 text-sm text-gray-700 hover:bg-gray-100"
          >
            Скопировать карту
          </button>
          <button
            type="button"
            onClick={openCustomerCard}
            className="rounded-md border border-gray-300 bg-white px-4 py-3 text-sm text-gray-700 hover:bg-gray-100"
          >
            Открыть карточку клиента
          </button>
          <button
            type="button"
            onClick={openCustomerPurchases}
            className="rounded-md border border-gray-300 bg-white px-4 py-3 text-sm text-gray-700 hover:bg-gray-100"
          >
            Открыть покупки клиента
          </button>
          <button
            type="button"
            onClick={() =>
              void copyToClipboard(
                customerSummary,
                'Резюме клиента скопировано',
                'Резюме клиента пока недоступно'
              )
            }
            className="rounded-md border border-gray-300 bg-white px-4 py-3 text-sm text-gray-700 hover:bg-gray-100"
          >
            Скопировать резюме
          </button>
          <button
            type="button"
            onClick={insertCustomerSummaryIntoReply}
            className="rounded-md border border-gray-300 bg-white px-4 py-3 text-sm text-gray-700 hover:bg-gray-100"
          >
            Вставить резюме в ответ
          </button>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
          <div className="rounded border border-gray-200 bg-white px-3 py-2">
            Регистрация: <span className="font-semibold text-gray-900">{detail?.customer_context.is_registered ? 'Да' : 'Нет'}</span>
          </div>
          <div className="rounded border border-gray-200 bg-white px-3 py-2">
            Бонусная карта: <span className="font-semibold text-gray-900">{detail?.customer_context.has_bonus_card ? 'Есть' : 'Нет'}</span>
          </div>
          <div className="rounded border border-gray-200 bg-white px-3 py-2">
            Баллы: <span className="font-semibold text-gray-900">{detail?.customer_context.loyalty_points ?? 0}</span>
          </div>
          <div className="rounded border border-gray-200 bg-white px-3 py-2">
            Сегмент: <span className="font-semibold text-gray-900">{detail?.customer_context.customer_segment || '—'}</span>
          </div>
          <div className="rounded border border-gray-200 bg-white px-3 py-2">
            Покупок: <span className="font-semibold text-gray-900">{detail?.customer_context.total_purchases ?? 0}</span>
          </div>
          <div className="rounded border border-gray-200 bg-white px-3 py-2">
            Потратил: <span className="font-semibold text-gray-900">{formatCurrencyKopec(detail?.customer_context.total_spent ?? 0)}</span>
          </div>
        </div>
        <div className="mt-3 space-y-1 text-xs text-gray-600">
          <div>Карта: <span className="font-medium text-gray-900">{detail?.customer_context.discount_card_number || '—'}</span></div>
          <div>Последняя покупка: <span className="font-medium text-gray-900">{formatDateTime(detail?.customer_context.last_purchase_date)}</span></div>
          <div>Средний чек: <span className="font-medium text-gray-900">{detail?.customer_context.average_check ? formatCurrencyKopec(detail.customer_context.average_check) : '—'}</span></div>
          <div>Основной магазин: <span className="font-medium text-gray-900">{detail?.customer_context.preferred_store_name || '—'}</span></div>
        </div>
        {!!detail?.customer_context.favorite_categories?.length && (
          <div className="mt-3">
            <div className="mb-1 text-xs text-gray-500">Любимые категории</div>
            <div className="flex flex-wrap gap-1">
              {detail.customer_context.favorite_categories.map((item) => (
                <span key={item} className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}
        {!!detail?.customer_context.favorite_brands?.length && (
          <div className="mt-3">
            <div className="mb-1 text-xs text-gray-500">Любимые бренды</div>
            <div className="flex flex-wrap gap-1">
              {detail.customer_context.favorite_brands.map((item) => (
                <span key={item} className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="mt-3 rounded-md border border-gray-200 bg-white p-3">
          <div className="mb-1 text-xs text-gray-500">Краткое резюме клиента</div>
          <div className="text-sm leading-6 text-gray-700">
            {customerSummary || 'Резюме клиента пока недоступно.'}
          </div>
        </div>
      </div>

      <div className="rounded-md border border-gray-200 bg-white p-3">
        <div className="mb-2 text-sm font-medium text-gray-900">Избранные образы покупателя</div>
        <div className="space-y-2">
          {(detail?.customer_context.favorite_looks || []).map((look) => (
            <div key={look.id} className="rounded-md border border-gray-200 p-3 text-sm">
              <div className="font-medium text-gray-900">{look.look_name || look.look_id}</div>
              <div className="mt-1 text-xs text-gray-500">
                {[look.look_style, look.look_mood].filter(Boolean).join(' · ') || 'Образ без тегов'}
              </div>
              <div className="mt-1 text-xs text-gray-500">{formatDateTime(look.created_at)}</div>
            </div>
          ))}
          {!detail?.customer_context.favorite_looks?.length && (
            <div className="text-sm text-gray-500">Избранных образов нет.</div>
          )}
        </div>
      </div>

      <div className="rounded-md border border-gray-200 bg-white p-3">
        <div className="mb-2 text-sm font-medium text-gray-900">Последние бонусные операции</div>
        <div className="space-y-2">
          {(detail?.customer_context.loyalty_transactions || []).map((item) => (
            <div key={item.id} className="rounded-md border border-gray-200 p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium text-gray-900">{item.reason || item.transaction_type}</div>
                <div className={`text-sm font-semibold ${item.points >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                  {item.points > 0 ? '+' : ''}{item.points}
                </div>
              </div>
              <div className="mt-1 text-xs text-gray-500">
                Баланс после: {item.balance_after} · {formatDateTime(item.created_at)}
              </div>
              {item.description && <div className="mt-1 text-xs text-gray-600">{item.description}</div>}
            </div>
          ))}
          {!detail?.customer_context.loyalty_transactions?.length && (
            <div className="text-sm text-gray-500">Операций по бонусам пока нет.</div>
          )}
        </div>
      </div>
    </div>
  );

  const caseWorkspaceContent = (
    <div className="space-y-4 p-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-gray-200 bg-white p-3">
          <div className="mb-2 text-sm font-medium text-gray-900">Внутренние заметки</div>
          <textarea
            value={detail?.conversation.internal_notes || ''}
            onChange={(e) =>
              setDetail((current) =>
                current
                  ? { ...current, conversation: { ...current.conversation, internal_notes: e.target.value } }
                  : current
              )
            }
            rows={5}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={() => updateConversation({ internal_notes: detail?.conversation.internal_notes || '' })}
            disabled={saving}
            className="mt-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Сохранить заметки
          </button>
        </div>

        <div className="rounded-md border border-gray-200 bg-white p-3">
          <div className="mb-2 text-sm font-medium text-gray-900">Итог обращения</div>
          <input
            value={detail?.conversation.result_order_id || ''}
            onChange={(e) =>
              setDetail((current) =>
                current
                  ? { ...current, conversation: { ...current.conversation, result_order_id: e.target.value } }
                  : current
              )
            }
            placeholder="ID заказа"
            className="mb-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <textarea
            value={detail?.conversation.result_notes || ''}
            onChange={(e) =>
              setDetail((current) =>
                current
                  ? { ...current, conversation: { ...current.conversation, result_notes: e.target.value } }
                  : current
              )
            }
            rows={4}
            placeholder="Комментарий по результату"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={() =>
              updateConversation({
                result_order_id: detail?.conversation.result_order_id || '',
                result_notes: detail?.conversation.result_notes || '',
              })
            }
            disabled={saving}
            className="mt-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Сохранить итог
          </button>
        </div>
      </div>

      <div className="rounded-md border border-gray-200 bg-white p-3">
        <div className="mb-2 text-sm font-medium text-gray-900">Последние заказы</div>
        <div className="space-y-2">
          {(detail?.recent_orders || []).map((order) => (
            <div key={order.id} className="rounded-md border border-gray-200 p-3 text-sm">
              <div className="font-medium text-gray-900">{order.id}</div>
              <div className="mt-1 text-xs text-gray-500">
                {order.status} · {formatDateTime(order.created_at)}
              </div>
              <div className="mt-1 text-sm text-gray-700">{formatCurrencyKopec(order.total_amount)}</div>
              {!!order.product_ids.length && (
                <div className="mt-1 text-xs text-gray-500">
                  Товары: {order.product_ids.join(', ')}
                </div>
              )}
            </div>
          ))}
          {!detail?.recent_orders?.length && (
            <div className="text-sm text-gray-500">Заказы не найдены.</div>
          )}
          {!!detail?.conversation.result_order_id && (
            <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
              Заказ, связанный с результатом: {detail.conversation.result_order_id}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-md border border-gray-200 bg-white p-3">
        <div className="mb-2 text-sm font-medium text-gray-900">История действий</div>
        <div className="space-y-2">
          {(detail?.audit_events || []).map((event) => (
            <div key={event.id} className="rounded-md border border-gray-200 p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium text-gray-900">{event.event_label}</div>
                <div className="text-xs text-gray-500">{formatDateTime(event.created_at)}</div>
              </div>
              <div className="mt-1 text-xs text-gray-500">
                {event.actor?.full_name || event.actor?.email || 'Система'}
              </div>
              <div className="mt-2 text-sm text-gray-700">{event.description}</div>
            </div>
          ))}
          {!detail?.audit_events?.length && (
            <div className="text-sm text-gray-500">Действия пока не зафиксированы.</div>
          )}
        </div>
      </div>
    </div>
  );

  const compactSelectionPanel = (
    <div className="space-y-3 p-4">
      <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
        <div className="mb-2 text-sm font-medium text-gray-900">Быстрый подбор</div>
        <div className="space-y-2">
          <input
            value={productSearch}
            onChange={(e) => setProductSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void searchProducts();
              }
            }}
            placeholder="Артикул, название или бренд"
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-3 text-sm"
          />
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => void searchProducts()}
              disabled={productSearchLoading}
              className="rounded-md border border-gray-300 bg-white px-3 py-3 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
            >
              {productSearchLoading ? 'Поиск...' : 'Найти товар'}
            </button>
            <button
              type="button"
              onClick={() => photoInputRef.current?.click()}
              className="rounded-md border border-gray-300 bg-white px-3 py-3 text-sm text-gray-700 hover:bg-gray-100"
            >
              Прикрепить фото
            </button>
          </div>
        </div>
      </div>

      <div className="rounded-md border border-gray-200 bg-white p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="text-sm font-medium text-gray-900">Рекомендации в обращении</div>
          <button
            type="button"
            onClick={() => setWorkspaceTab('selection')}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-xs text-gray-700 hover:bg-gray-50"
          >
            Весь подбор
          </button>
        </div>
        {renderRecommendedProducts((detail?.conversation.recommended_product_ids || []).slice(0, 4), {
          compact: true,
          emptyText: 'Рекомендаций пока нет.',
        })}
      </div>

      {!!productSearchResults.length && (
        <div className="rounded-md border border-gray-200 bg-white p-3">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Найденные товары</div>
          <div className="space-y-2">
            {productSearchResults.slice(0, 4).map((product) => (
              <button
                key={product.id}
                type="button"
                onClick={() => addSelectedProduct(product)}
                disabled={selectedProducts.some((item) => item.id === product.id)}
                className="flex w-full items-center gap-3 rounded-md border border-gray-200 p-3 text-left hover:bg-gray-50 disabled:opacity-50"
              >
                <div className="h-14 w-14 shrink-0 overflow-hidden rounded border border-gray-200 bg-gray-50">
                  {product.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={product.image_url} alt={product.name || product.id} className="h-full w-full object-cover" />
                  ) : null}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-gray-900">{product.name || product.id}</div>
                  <div className="text-xs text-gray-500">
                    {[product.brand, product.article || product.external_code].filter(Boolean).join(' · ') || 'Без артикула'}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {(selectedProducts.length > 0 || selectedPhotos.length > 0) && (
        <div className="rounded-md border border-gray-200 bg-white p-3">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">К сообщению прикреплено</div>
          <div className="flex flex-wrap gap-2">
            {selectedProducts.map((product) => (
              <span
                key={product.id}
                className="rounded-full border border-gray-300 bg-gray-50 px-3 py-2 text-xs text-gray-700"
              >
                {product.article || product.external_code || product.name || product.id}
              </span>
            ))}
            {selectedPhotos.map((photo) => (
              <span
                key={photo.id}
                className="rounded-full border border-gray-300 bg-gray-50 px-3 py-2 text-xs text-gray-700"
              >
                {photo.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );

  const inboxSection = (
    <section className="overflow-hidden rounded-[28px] border border-[#eadfcd] bg-[#fbfaf7] shadow-sm">
      <div className="relative overflow-hidden border-b border-[#eadfcd] bg-[radial-gradient(circle_at_top_left,#fff7e6,transparent_34%),linear-gradient(135deg,#fffdf8_0%,#f5efe5_48%,#ffffff_100%)] p-5 md:p-7">
        <div className="absolute right-0 top-0 h-40 w-40 rounded-full bg-gold-200/20 blur-3xl" />
        {hasActiveAlerts && (
          <div
            className={`relative mb-5 rounded-2xl border px-4 py-3 shadow-sm ${
              alertBannerPulse ? 'border-red-300 bg-red-50 shadow-[0_0_0_3px_rgba(239,68,68,0.14)]' : 'border-amber-300 bg-amber-50'
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-gray-950">Нельзя пропустить новые сообщения покупателей</div>
                <div className="mt-1 text-sm text-gray-700">
                  Непрочитанных: <span className="font-semibold">{badge?.total_unread_messages ?? 0}</span>
                  {' · '}новых запросов: <span className="font-semibold">{badge?.requested_conversations ?? 0}</span>
                  {' · '}требуют внимания: <span className="font-semibold">{badge?.attention_conversations ?? 0}</span>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {firstAlertConversation && (
                  <button
                    type="button"
                    onClick={focusFirstAlertConversation}
                    className="rounded-full bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-red-700"
                  >
                    Открыть проблемный диалог
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setAttentionOnly((current) => !current)}
                  className="rounded-full border border-amber-300 bg-white px-4 py-2 text-sm font-semibold text-amber-900 hover:bg-amber-100"
                >
                  {attentionOnly ? 'Показать все обращения' : 'Только требующие внимания'}
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex rounded-full border border-[#e4d3b6] bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-[#8a6a32]">
              Live Stylist · очередь обращений
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-gray-950 md:text-4xl">Связь со стилистом</h1>
            <p className="mt-2 text-sm leading-6 text-gray-600 md:text-base">
              Рабочая очередь для стилиста: сначала оцените срочность, контекст клиента и последнее сообщение, затем откройте отдельный диалог с подбором и инструментами ответа.
            </p>
          </div>
          <div className="grid min-w-[230px] grid-cols-2 gap-3 rounded-3xl border border-white/70 bg-white/80 p-3 shadow-sm backdrop-blur lg:grid-cols-1">
            <div className="rounded-2xl bg-gray-950 px-4 py-3 text-white">
              <div className="text-3xl font-semibold leading-none">{badge?.total_unread_messages ?? 0}</div>
              <div className="mt-1 text-xs text-white/70">неотвеченных сообщений</div>
            </div>
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
              <div className="text-3xl font-semibold leading-none text-amber-900">{badge?.attention_conversations ?? 0}</div>
              <div className="mt-1 text-xs text-amber-800">требуют внимания</div>
            </div>
          </div>
        </div>

        <div className="relative mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-2xl border border-blue-100 bg-white/85 p-4 shadow-sm">
            <div className="text-xs font-medium uppercase tracking-wide text-blue-700">Новые</div>
            <div className="mt-2 text-2xl font-semibold text-gray-950">{badge?.requested_conversations ?? 0}</div>
            <div className="mt-1 text-xs text-gray-500">ожидают первого контакта</div>
          </div>
          <div className="rounded-2xl border border-red-100 bg-white/85 p-4 shadow-sm">
            <div className="text-xs font-medium uppercase tracking-wide text-red-700">Срочные</div>
            <div className="mt-2 text-2xl font-semibold text-gray-950">{badge?.high_priority_conversations ?? 0}</div>
            <div className="mt-1 text-xs text-gray-500">высокий приоритет</div>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-white/85 p-4 shadow-sm">
            <div className="text-xs font-medium uppercase tracking-wide text-gray-500">В работе</div>
            <div className="mt-2 text-2xl font-semibold text-gray-950">{badge?.open_conversations ?? 0}</div>
            <div className="mt-1 text-xs text-gray-500">активных обращений</div>
          </div>
          <div className="rounded-2xl border border-emerald-100 bg-white/85 p-4 shadow-sm">
            <div className="text-xs font-medium uppercase tracking-wide text-emerald-700">Купили</div>
            <div className="mt-2 text-2xl font-semibold text-gray-950">{badge?.purchased_conversations ?? 0}</div>
            <div className="mt-1 text-xs text-gray-500">результативных диалогов</div>
          </div>
        </div>

        <div className="relative mt-4 grid gap-3 lg:grid-cols-[1fr_1fr]">
          <div className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-900">
            <span className="font-semibold">Без назначения: {badge?.unassigned_conversations ?? 0}</span>
            <span className="text-amber-800"> · быстро распределите обращения между стилистами</span>
          </div>
          <div className="rounded-2xl border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-900">
            <span className="font-semibold">Просрочен 1-й ответ: {badge?.overdue_first_response_conversations ?? 0}</span>
            <span className="text-red-800"> · приоритет для немедленного ответа</span>
          </div>
        </div>

        <div className="relative mt-5 rounded-2xl border border-[#eadfcd] bg-white/80 p-4 shadow-sm">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-sm font-semibold text-gray-950">Оповещения стилиста</div>
              <div className="mt-1 text-xs text-gray-500">Desktop, звук и вибрация помогают не пропустить новый запрос на планшете или рабочем компьютере.</div>
            </div>
            <div className="grid gap-2 text-sm text-gray-700 sm:grid-cols-3 lg:min-w-[640px]">
              <label className="flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2">
                <input
                  type="checkbox"
                  checked={browserNotificationsEnabled}
                  onChange={(e) => void handleBrowserNotificationsToggle(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 accent-gray-950"
                />
                <span className="min-w-0">
                  <span className="font-medium text-gray-900">Desktop</span>
                  <span className="ml-1 text-xs text-gray-500">
                    {notificationPermission === 'granted'
                      ? 'разрешены'
                      : notificationPermission === 'denied'
                        ? 'запрещены'
                        : notificationPermission === 'default'
                          ? 'нужно разрешить'
                          : 'нет поддержки'}
                  </span>
                </span>
              </label>
              <label className="flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2">
                <input
                  type="checkbox"
                  checked={soundNotificationsEnabled}
                  onChange={(e) => handleSoundNotificationsToggle(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 accent-gray-950"
                />
                <span className="font-medium text-gray-900">Звук</span>
              </label>
              <label className="flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2">
                <input
                  type="checkbox"
                  checked={vibrationNotificationsEnabled}
                  onChange={(e) => handleVibrationNotificationsToggle(e.target.checked)}
                  disabled={!vibrationSupported}
                  className="h-4 w-4 rounded border-gray-300 accent-gray-950 disabled:opacity-50"
                />
                <span className="font-medium text-gray-900">Вибрация</span>
                <span className="text-xs text-gray-500">{vibrationSupported ? 'ok' : 'нет'}</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <div className="border-b border-[#eadfcd] bg-white p-4 md:p-5">
        <div className="grid gap-3">
          <div className="relative">
            <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">⌕</span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по имени, телефону, email или source"
              className="w-full rounded-2xl border border-gray-200 bg-[#fbfaf7] px-10 py-3 text-sm outline-none transition focus:border-[#c8a86a] focus:bg-white focus:ring-2 focus:ring-[#eadfcd]"
            />
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm outline-none focus:border-[#c8a86a] focus:ring-2 focus:ring-[#eadfcd]"
            >
              <option value="all">Все статусы</option>
              <option value="requested">Запрос</option>
              <option value="in_progress">В обработке</option>
              <option value="completed">Завершено</option>
            </select>
            <select
              value={ownershipFilter}
              onChange={(e) => setOwnershipFilter(e.target.value)}
              className="rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm outline-none focus:border-[#c8a86a] focus:ring-2 focus:ring-[#eadfcd]"
            >
              <option value="all">Все обращения</option>
              <option value="mine">Только мои</option>
              <option value="unassigned">Без стилиста</option>
            </select>
            <select
              value={purchaseFilter}
              onChange={(e) => setPurchaseFilter(e.target.value)}
              className="rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm outline-none focus:border-[#c8a86a] focus:ring-2 focus:ring-[#eadfcd]"
            >
              <option value="all">Любой итог</option>
              <option value="unknown">Без итога</option>
              <option value="purchased_recommended">Купил подобранные</option>
              <option value="purchased_other">Купил другие</option>
              <option value="not_purchased">Не купил</option>
            </select>
          </div>
          <label className="inline-flex w-fit items-center gap-2 rounded-full border border-gray-200 bg-[#fbfaf7] px-4 py-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={attentionOnly}
              onChange={(e) => setAttentionOnly(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 accent-gray-950"
            />
            Только обращения, требующие внимания
          </label>
        </div>
      </div>

      <div className="max-h-[calc(100vh-310px)] space-y-3 overflow-y-auto bg-[#f7f3ed] p-4 md:p-5">
        {loading && <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-6 text-sm text-gray-500">Загрузка обращений...</div>}
        {!loading && conversations.length === 0 && (
          <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500">Обращений пока нет.</div>
        )}
        {conversations.map((item) => {
          const workDuration = conversationWorkDurationMinutes(item);
          const totalAge = minutesSince(item.created_at);
          const assignee = item.assigned_stylist?.full_name || item.assigned_stylist?.email || 'Не назначен';
          const customerName = item.customer.full_name || item.customer.phone || item.customer.email || item.customer.id;
          return (
          <button
            key={item.id}
            type="button"
            onClick={() => {
              setSelectedId(item.id);
              setIsInboxPanelOpen(false);
            }}
            className={`group block w-full rounded-[24px] border bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-[#d5b875] hover:shadow-md ${
              item.id === selectedId ? 'border-[#c8a86a] ring-2 ring-[#eadfcd]' : item.needs_attention ? 'border-amber-300' : 'border-white'
            }`}
          >
            <div className="grid gap-4 xl:grid-cols-[minmax(260px,1.2fr)_minmax(260px,1fr)_minmax(320px,1.25fr)_auto] xl:items-center">
              <div className="min-w-0">
                <div className="flex items-center gap-3">
                  <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-base font-semibold ${item.needs_attention ? 'bg-amber-100 text-amber-900' : 'bg-gray-100 text-gray-700'}`}>
                    {String(customerName || 'К').trim().slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <div className="truncate text-lg font-semibold text-gray-950">{customerName}</div>
                      {item.unread_for_stylist_count > 0 && (
                        <span className="rounded-full bg-gray-950 px-2 py-0.5 text-xs font-semibold text-white">
                          {item.unread_for_stylist_count}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 truncate text-sm text-gray-500">
                      {item.customer.phone || item.customer.email || 'Контакт не указан'}
                      {item.customer.city ? ` · ${item.customer.city}` : ''}
                    </div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-500">
                  <span className="rounded-full bg-gray-100 px-2.5 py-1">Источник: {item.source || 'unknown'}</span>
                  <span className="rounded-full bg-gray-100 px-2.5 py-1">{formatDateTime(item.created_at)}</span>
                </div>
              </div>

              <div className="flex flex-wrap content-start gap-2 text-xs">
                <span className={`rounded-full border px-3 py-1.5 font-semibold ${item.status === 'requested' ? 'border-blue-200 bg-blue-50 text-blue-800' : item.status === 'in_progress' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'}`}>
                  {item.status_label}
                </span>
                <span className={`rounded-full border px-3 py-1.5 font-semibold ${item.priority === 'high' ? 'border-red-200 bg-red-50 text-red-700' : 'border-gray-200 bg-gray-50 text-gray-700'}`}>
                  {item.priority_label}
                </span>
                <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-gray-700">
                  Итог: {item.result_purchase_status_label}
                </span>
                {item.needs_attention && (
                  <span className="rounded-full border border-amber-300 bg-amber-50 px-3 py-1.5 font-semibold text-amber-900">
                    {attentionReasonLabel(item.attention_reason)}
                  </span>
                )}
              </div>

              <div className="grid gap-2 text-xs text-gray-600 sm:grid-cols-3">
                <div className="rounded-2xl border border-gray-100 bg-[#fbfaf7] px-3 py-2.5">
                  <div className="text-gray-500">У кого в работе</div>
                  <div className="mt-1 truncate font-semibold text-gray-950">{assignee}</div>
                </div>
                <div className="rounded-2xl border border-gray-100 bg-[#fbfaf7] px-3 py-2.5">
                  <div className="text-gray-500">Длится</div>
                  <div className="mt-1 font-semibold text-gray-950">{totalAge === null ? '—' : formatDurationMinutes(totalAge)}</div>
                </div>
                <div className="rounded-2xl border border-gray-100 bg-[#fbfaf7] px-3 py-2.5">
                  <div className="text-gray-500">В работе</div>
                  <div className="mt-1 font-semibold text-gray-950">{workDuration === null ? '—' : formatDurationMinutes(workDuration)}</div>
                </div>
              </div>

              <div className="flex items-center justify-end">
                <span className="rounded-full bg-gray-950 px-5 py-3 text-sm font-semibold text-white shadow-sm transition group-hover:bg-[#8a6a32]">
                  Открыть диалог →
                </span>
              </div>
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_auto] lg:items-end">
              <div className="line-clamp-2 rounded-2xl bg-[#fbfaf7] px-4 py-3 text-sm leading-6 text-gray-700">
                {item.last_message_preview || 'Сообщений пока нет'}
              </div>
              <div className="flex flex-wrap justify-between gap-2 text-xs text-gray-500 lg:min-w-[340px] lg:justify-end">
                <span className="rounded-full bg-white px-2.5 py-1 ring-1 ring-gray-100">Scenario: {item.scenario || '—'}</span>
                <span className={`rounded-full px-2.5 py-1 ring-1 ${item.needs_attention ? 'bg-amber-50 text-amber-900 ring-amber-100' : 'bg-white ring-gray-100'}`}>
                  {item.needs_attention ? `Ждет ответа ${formatDurationMinutes(item.waiting_minutes)}` : `Последнее: ${formatDateTime(item.last_message_at || item.created_at)}`}
                </span>
              </div>
            </div>
          </button>
          );
        })}
      </div>
    </section>
  );

  return (
    <div className="min-h-screen bg-[#f7f3ed] p-3 md:p-4">
      {!selectedConversation ? (
        <div className="mx-auto max-w-7xl">{inboxSection}</div>
      ) : (
        <section className="mx-auto max-w-7xl overflow-hidden rounded-[28px] border border-[#eadfcd] bg-white shadow-sm">
            <div className="grid h-full min-h-[70vh] grid-rows-[auto_auto_auto_1fr_auto]">
              <div className="border-b border-[#eadfcd] bg-[linear-gradient(135deg,#fffdf8_0%,#f5efe5_55%,#ffffff_100%)] p-5 md:p-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="truncate text-xl font-semibold text-gray-900">
                        {selectedConversation.customer.full_name ||
                          selectedConversation.customer.phone ||
                          selectedConversation.customer.email ||
                          selectedConversation.customer.id}
                      </h2>
                      <span className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-700">
                        {detail?.conversation.status_label || selectedConversation.status_label}
                      </span>
                      <span className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-700">
                        {detail?.conversation.priority_label || selectedConversation.priority_label}
                      </span>
                    </div>
                    <div className="mt-1 text-sm text-gray-600">
                      {selectedConversation.customer.phone || 'Телефон не указан'} · {selectedConversation.customer.city || 'Город не указан'}
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      Source: {selectedConversation.source || '—'} · Scenario: {selectedConversation.scenario || '—'}
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      Итог: {detail?.conversation.result_purchase_status_label || selectedConversation.result_purchase_status_label}
                      {((detail?.conversation.result_source || selectedConversation.result_source) === 'auto') && ' · авто по заказу'}
                      {((detail?.conversation.result_source || selectedConversation.result_source) === 'manual') && ' · отмечено вручную'}
                    </div>
                    {(detail?.conversation.needs_attention || selectedConversation.needs_attention) && (
                      <div className="mt-2 inline-flex rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-800">
                        {attentionReasonLabel(detail?.conversation.attention_reason || selectedConversation.attention_reason)}
                        {' · '}
                        {detail?.conversation.waiting_minutes || selectedConversation.waiting_minutes} мин
                      </div>
                    )}
                  </div>

                  <div className="flex flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedId(null)}
                      className="rounded-full border border-[#d8c7aa] bg-white px-4 py-2 text-sm font-semibold text-gray-800 hover:bg-[#fbfaf7]"
                    >
                      ← К списку обращений
                    </button>
                    <button
                      type="button"
                      onClick={() => setIsCustomerPanelOpen(true)}
                      className="rounded-full border border-[#d8c7aa] bg-white px-4 py-2 text-sm font-semibold text-gray-800 hover:bg-[#fbfaf7]"
                    >
                      Профиль покупателя
                    </button>
                    <button
                      type="button"
                      onClick={clearConversationMessages}
                      disabled={saving || detailLoading}
                      className="rounded-md border border-red-300 bg-white px-3 py-2 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
                    >
                      Очистить чат
                    </button>
                    <button
                      type="button"
                      onClick={assignToMe}
                      disabled={saving}
                      className="rounded-full bg-gray-950 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#8a6a32] disabled:opacity-50"
                    >
                      Взять в работу
                    </button>
                  </div>
                </div>
              </div>

              <div className="grid gap-3 border-b border-gray-200 p-4 md:grid-cols-2 xl:grid-cols-4">
                <label className="text-sm text-gray-700">
                  <div className="mb-1 text-xs text-gray-500">Статус</div>
                  <select
                    value={detail?.conversation.status || selectedConversation.status}
                    onChange={(e) => updateConversation({ status: e.target.value })}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  >
                    <option value="requested">Запрос</option>
                    <option value="in_progress">В обработке</option>
                    <option value="completed">Завершено</option>
                  </select>
                </label>

                <label className="text-sm text-gray-700">
                  <div className="mb-1 text-xs text-gray-500">Приоритет</div>
                  <select
                    value={detail?.conversation.priority || selectedConversation.priority}
                    onChange={(e) => updateConversation({ priority: e.target.value })}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  >
                    <option value="normal">Обычный</option>
                    <option value="high">Высокий</option>
                  </select>
                </label>

                <label className="text-sm text-gray-700">
                  <div className="mb-1 text-xs text-gray-500">Стилист</div>
                  <select
                    value={detail?.conversation.assigned_stylist?.id || ''}
                    onChange={(e) =>
                      updateConversation({ assigned_stylist_user_id: e.target.value || '' })
                    }
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  >
                    <option value="">Не назначен</option>
                    {stylists.map((stylist) => (
                      <option key={stylist.id} value={stylist.id}>
                        {stylist.full_name || stylist.email || stylist.id}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="text-sm text-gray-700">
                  <div className="mb-1 text-xs text-gray-500">Итог покупки</div>
                  <select
                    value={detail?.conversation.result_purchase_status || selectedConversation.result_purchase_status}
                    onChange={(e) => updateConversation({ result_purchase_status: e.target.value })}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  >
                    <option value="unknown">Не отмечено</option>
                    <option value="purchased_recommended">Купил подобранные</option>
                    <option value="purchased_other">Купил другие</option>
                    <option value="not_purchased">Не купил</option>
                  </select>
                </label>
              </div>

              <div className="border-b border-gray-200 px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap gap-2">
                    {workspaceTabs.map((tab) => (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => setWorkspaceTab(tab.id)}
                        className={`rounded-md px-3 py-2 text-sm ${
                          workspaceTab === tab.id
                            ? 'bg-gray-900 text-white'
                            : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                        }`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>
                  <div className="text-right text-xs text-gray-500">
                    <div>{detail?.current_working_hours?.status_text || 'Статус работы загружается'}</div>
                    <div>
                      SLA 1-го ответа:{' '}
                      {detail?.conversation.first_response_due_at
                        ? formatDateTime(detail.conversation.first_response_due_at)
                        : 'выполнен'}
                    </div>
                  </div>
                </div>
              </div>

              <div className="min-h-0 overflow-hidden">
                {workspaceTab === 'chat' && (
                  <div className="grid h-full min-h-0 grid-rows-[auto_1fr] xl:grid-cols-[minmax(0,1fr)_340px] xl:grid-rows-1">
                    <div className="grid min-h-0 grid-rows-[auto_1fr] border-b border-gray-200 xl:border-b-0 xl:border-r">
                      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
                        <div className="text-sm font-medium text-gray-900">Диалог</div>
                        <div className="text-xs text-gray-500">
                          Непрочитано у покупателя: {detail?.conversation.unread_for_customer_count ?? 0}
                        </div>
                      </div>
                      <div ref={messagesScrollRef} className="h-full space-y-3 overflow-y-auto p-4">
                        {detailLoading && <div className="text-sm text-gray-500">Загрузка диалога...</div>}
                        {!detailLoading && detail?.messages.length === 0 && (
                          <div className="text-sm text-gray-500">Сообщений пока нет.</div>
                        )}
                        {detail?.messages.map((message) => {
                          const outgoing = message.role === 'stylist' || message.role === 'assistant';
                          const productAttachments = (message.attachments || []).filter(
                            (item) => item?.type === 'product',
                          );
                          const imageAttachments = (message.attachments || []).filter(
                            (item) => item?.type === 'image' && item?.url,
                          );
                          return (
                            <div
                              key={message.id}
                              className={`max-w-[88%] rounded-md border px-3 py-3 text-sm md:max-w-[80%] ${
                                outgoing
                                  ? 'ml-auto border-gray-900 bg-gray-900 text-white'
                                  : 'border-gray-200 bg-white text-gray-900'
                              }`}
                            >
                              <div className={`mb-1 text-xs ${outgoing ? 'text-gray-300' : 'text-gray-500'}`}>
                                {message.sender?.full_name ||
                                  (message.role === 'user' ? 'Покупатель' : message.role === 'assistant' ? 'AI' : 'Стилист')}
                                {' · '}
                                {formatDateTime(message.created_at)}
                              </div>
                              {!!message.text && <div className="whitespace-pre-wrap leading-6">{message.text}</div>}
                              {!message.text && !message.attachments?.length && (
                                <div className="whitespace-pre-wrap">Сообщение без текста</div>
                              )}
                              {!!productAttachments.length && (
                                <div className="mt-3 space-y-2">
                                  {productAttachments.map((attachment, index) => (
                                    <div
                                      key={`${message.id}-product-${attachment.product_id || index}`}
                                      className={`rounded-md border p-3 ${
                                        outgoing ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-gray-50'
                                      }`}
                                    >
                                      <div className="flex gap-3">
                                        <div className="h-16 w-16 shrink-0 overflow-hidden rounded border border-gray-200 bg-white">
                                          {attachment.image_url ? (
                                            // eslint-disable-next-line @next/next/no-img-element
                                            <img
                                              src={attachment.image_url}
                                              alt={attachment.name || attachment.article || 'Товар'}
                                              className="h-full w-full object-cover"
                                            />
                                          ) : (
                                            <div className="flex h-full w-full items-center justify-center text-[10px] text-gray-400">
                                              Нет фото
                                            </div>
                                          )}
                                        </div>
                                        <div className="min-w-0 flex-1">
                                          <div className={`truncate font-medium ${outgoing ? 'text-white' : 'text-gray-900'}`}>
                                            {attachment.name || attachment.product_id}
                                          </div>
                                          <div className={`mt-1 text-xs ${outgoing ? 'text-gray-300' : 'text-gray-500'}`}>
                                            {[attachment.brand, attachment.category, attachment.article].filter(Boolean).join(' · ') || 'Карточка товара'}
                                          </div>
                                          <div className={`mt-1 text-sm ${outgoing ? 'text-gray-100' : 'text-gray-700'}`}>
                                            {attachment.price ? formatCurrencyKopec(attachment.price) : 'Цена не указана'}
                                          </div>
                                          <button
                                            type="button"
                                            onClick={() =>
                                              openProductCard({
                                                id: attachment.product_id || attachment.id || `attachment-${index}`,
                                                name: attachment.name,
                                                brand: attachment.brand,
                                                category: attachment.category,
                                                article: attachment.article,
                                                external_code: attachment.external_code,
                                                price: attachment.price,
                                                image_url: attachment.image_url,
                                                in_stock: attachment.in_stock,
                                              })
                                            }
                                            className={`mt-2 rounded-md border px-3 py-2 text-xs ${
                                              outgoing
                                                ? 'border-gray-600 bg-gray-900 text-white hover:bg-gray-700'
                                                : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-100'
                                            }`}
                                          >
                                            Открыть карточку
                                          </button>
                                        </div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                              {!!imageAttachments.length && (
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {imageAttachments.map((attachment, index) => (
                                    <a
                                      key={`${message.id}-image-${index}`}
                                      href={attachment.url}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="block"
                                    >
                                      {/* eslint-disable-next-line @next/next/no-img-element */}
                                      <img
                                        src={attachment.url}
                                        alt={attachment.name || 'Фото'}
                                        className="h-28 w-28 rounded-md border border-gray-200 object-cover"
                                      />
                                    </a>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <aside className="hidden min-h-0 overflow-y-auto border-t border-gray-200 bg-gray-50 xl:block xl:border-t-0">
                      {compactSelectionPanel}
                    </aside>
                  </div>
                )}
                
                {workspaceTab === 'selection' && (
                  <div className="h-full overflow-y-auto">{selectionWorkspaceContent}</div>
                )}

                {workspaceTab === 'case' && (
                  <div className="h-full overflow-y-auto">{caseWorkspaceContent}</div>
                )}
              </div>

              <form onSubmit={sendReply} className="sticky bottom-0 z-10 border-t border-gray-200 bg-white/95 p-4 backdrop-blur">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div className="text-sm font-medium text-gray-900">Ответ покупателю</div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => setWorkspaceTab('selection')}
                      className="rounded-md border border-gray-300 bg-white px-4 py-3 text-sm text-gray-700 hover:bg-gray-50"
                    >
                      Подбор украшений
                    </button>
                    <button
                      type="button"
                      onClick={() => photoInputRef.current?.click()}
                      className="rounded-md border border-gray-300 bg-white px-4 py-3 text-sm text-gray-700 hover:bg-gray-50"
                    >
                      Прикрепить фото
                    </button>
                    <input
                      ref={photoInputRef}
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={handlePhotoSelection}
                      className="hidden"
                    />
                  </div>
                </div>

                <div className="mb-3 flex flex-wrap gap-2">
                  {QUICK_REPLY_CHIPS.map((chip) => (
                    <button
                      key={chip}
                      type="button"
                      onClick={() => applyQuickReplyChip(chip)}
                      className="rounded-full border border-gray-300 bg-gray-50 px-4 py-2.5 text-sm text-gray-700 hover:bg-white"
                    >
                      {chip}
                    </button>
                  ))}
                </div>

                {(selectedProducts.length > 0 || selectedPhotos.length > 0) && (
                  <div className="mb-3 rounded-md border border-gray-200 bg-gray-50 p-3">
                    <div className="mb-2 text-xs text-gray-500">
                      К следующему сообщению прикреплено: товаров {selectedProducts.length}, фото {selectedPhotos.length}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {selectedProducts.map((product) => (
                        <span
                          key={product.id}
                          className="rounded-full border border-gray-300 bg-white px-3 py-2 text-xs text-gray-700"
                        >
                          {product.article || product.external_code || product.name || product.id}
                        </span>
                      ))}
                      {selectedPhotos.map((photo) => (
                        <span
                          key={photo.id}
                          className="rounded-full border border-gray-300 bg-white px-3 py-2 text-xs text-gray-700"
                        >
                          {photo.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex flex-col gap-3 md:flex-row">
                  <textarea
                    value={messageText}
                    onChange={(e) => setMessageText(e.target.value)}
                    onFocus={() => setComposerFocused(true)}
                    onBlur={() => {
                      setComposerFocused(false);
                      clearTypingTimers();
                      if (selectedId && activeTypingConversationRef.current === selectedId) {
                        void syncStylistTypingState(selectedId, false);
                      }
                    }}
                    placeholder="Напишите ответ покупателю"
                    rows={4}
                    className="min-h-[112px] flex-1 rounded-md border border-gray-300 px-4 py-3 text-base"
                  />
                  <button
                    type="submit"
                    disabled={saving || (!messageText.trim() && !selectedProducts.length && !selectedPhotos.length)}
                    className="min-h-[52px] rounded-md bg-gray-900 px-5 py-3 text-base font-medium text-white hover:bg-gray-800 disabled:opacity-50 md:self-end"
                    style={{ backgroundColor: '#111827', color: '#ffffff' }}
                  >
                    Отправить
                  </button>
                </div>
              </form>
            </div>
          {(error || success) && (
            <div className="border-t border-gray-200 p-4">
              {error && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
              {success && (
                <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
                  {success}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {isInboxPanelOpen && (
        <div className="fixed inset-0 z-40 bg-black/30 px-2 py-4 xl:hidden">
          <div className="mx-auto flex h-full max-w-xl flex-col overflow-hidden rounded-md bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
              <div className="text-sm font-medium text-gray-900">Очередь обращений</div>
              <button
                type="button"
                onClick={() => setIsInboxPanelOpen(false)}
                className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                Закрыть
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">{inboxSection}</div>
          </div>
        </div>
      )}

      {isCustomerPanelOpen && selectedConversation && (
        <div className="fixed inset-0 z-50 bg-black/30 px-2 py-4">
          <div className="ml-auto flex h-full max-w-2xl flex-col overflow-hidden rounded-md bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
              <div>
                <div className="text-sm font-medium text-gray-900">Профиль покупателя</div>
                <div className="text-xs text-gray-500">
                  {selectedConversation.customer.full_name ||
                    selectedConversation.customer.phone ||
                    selectedConversation.customer.email ||
                    selectedConversation.customer.id}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsCustomerPanelOpen(false)}
                className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                Закрыть
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">{customerProfileContent}</div>
          </div>
        </div>
      )}

      {previewProduct && (
        <div className="fixed inset-0 z-[60] bg-black/40 px-2 py-4">
          <div className="mx-auto flex h-full max-w-2xl flex-col overflow-hidden rounded-md bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
              <div>
                <div className="text-sm font-medium text-gray-900">Карточка товара</div>
                <div className="text-xs text-gray-500">
                  {previewProduct.article || previewProduct.external_code || previewProduct.id}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setPreviewProduct(null)}
                className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                Закрыть
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              <div className="grid gap-4 md:grid-cols-[280px_minmax(0,1fr)]">
                <div className="overflow-hidden rounded-md border border-gray-200 bg-gray-50">
                  {previewProduct.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={previewProduct.image_url}
                      alt={previewProduct.name || previewProduct.id}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-72 items-center justify-center text-sm text-gray-400">Нет фото</div>
                  )}
                </div>
                <div className="space-y-3">
                  <div>
                    <div className="text-xl font-semibold text-gray-900">
                      {previewProduct.name || previewProduct.id}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      {previewProduct.brand && (
                        <span className="rounded border border-gray-200 bg-gray-50 px-2 py-1 text-gray-700">
                          {previewProduct.brand}
                        </span>
                      )}
                      {previewProduct.category && (
                        <span className="rounded border border-gray-200 bg-gray-50 px-2 py-1 text-gray-700">
                          {previewProduct.category}
                        </span>
                      )}
                      {previewProduct.article && (
                        <span className="rounded border border-gray-200 bg-gray-50 px-2 py-1 text-gray-700">
                          Артикул: {previewProduct.article}
                        </span>
                      )}
                      {previewProduct.external_code && (
                        <span className="rounded border border-gray-200 bg-gray-50 px-2 py-1 text-gray-700">
                          Код: {previewProduct.external_code}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                    <div className="text-xs text-gray-500">Цена</div>
                    <div className="mt-1 text-lg font-semibold text-gray-900">
                      {previewProduct.price ? formatCurrencyKopec(previewProduct.price) : 'Цена не указана'}
                    </div>
                  </div>
                  <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                    <div className="text-xs text-gray-500">Наличие</div>
                    <div className="mt-1 text-sm font-medium text-gray-900">
                      {previewProduct.in_stock === false
                        ? 'Нет в наличии'
                        : previewProduct.in_stock === true
                          ? 'Есть в наличии'
                          : 'Статус не указан'}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
