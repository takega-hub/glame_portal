'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ACCOUNT_NAV_ITEMS, NAVIGATION_GROUPS, resolveNavHref } from '@/config/navigation';
import { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { agentInteractions, liveStylistAdmin, type AgentInteractionTask } from '@/lib/api';
import {
  buildLiveStylistAlertTitle,
  getBrowserNotificationPermission,
  getLiveStylistBrowserNotificationsEnabled,
  getLiveStylistSoundNotificationsEnabled,
  getLiveStylistVibrationNotificationsEnabled,
  hasLiveStylistPendingAlerts,
  isLiveStylistVibrationSupported,
  playLiveStylistNotificationSound,
  sendLiveStylistBrowserNotification,
  vibrateLiveStylistAlert,
} from '@/lib/liveStylistNotifications';

export default function GlobalSidebar() {
  const pathname = usePathname();
  const { user, isAuthenticated } = useAuth();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [stylistUnreadBadge, setStylistUnreadBadge] = useState(0);
  const [agentMenuStatuses, setAgentMenuStatuses] = useState<Record<string, { label: string; tone: 'active' | 'attention' | 'error' | 'waiting' }>>({});
  const [stylistPendingAlerts, setStylistPendingAlerts] = useState({
    total_unread_messages: 0,
    requested_conversations: 0,
    attention_conversations: 0,
  });
  const baseTitleRef = useRef('GLAME ИИ');
  const reminderSoundCooldownRef = useRef<number>(0);
  const previousBadgeRef = useRef<{
    total_unread_messages: number;
    requested_conversations: number;
    attention_conversations: number;
  } | null>(null);
  const toggleSidebar = () => setSidebarCollapsed((v) => !v);
  const allowedSections = new Set(user?.allowed_sections || []);
  const hasStylistAccess = Boolean(user?.allowed_sections?.includes('customer_stylist'));
  const hasAiMarketerAccess = Boolean(user?.allowed_sections?.includes('ai_marketer'));
  const visibleAccountItems = ACCOUNT_NAV_ITEMS.filter((item) => allowedSections.has(item.sectionId));
  const visibleGroups = NAVIGATION_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => allowedSections.has(item.sectionId)),
  })).filter((group) => group.items.length > 0);
  const profileActive = pathname === '/profile' || pathname.startsWith('/profile/');
  const hasGlobalStickyAlert =
    hasStylistAccess &&
    hasLiveStylistPendingAlerts(
      stylistPendingAlerts.total_unread_messages,
      stylistPendingAlerts.requested_conversations,
      stylistPendingAlerts.attention_conversations
    );
  const alertSummaryText = buildLiveStylistAlertTitle(
    stylistPendingAlerts.total_unread_messages,
    stylistPendingAlerts.requested_conversations,
    stylistPendingAlerts.attention_conversations
  );

  const agentStatusClass = (tone?: string) => {
    if (tone === 'active') return 'bg-green-100 text-green-700 border-green-200';
    if (tone === 'attention') return 'bg-orange-100 text-orange-700 border-orange-200';
    if (tone === 'error') return 'bg-red-100 text-red-700 border-red-200';
    return 'bg-gray-100 text-gray-600 border-gray-200';
  };

  const resolveAgentMenuStatus = (item: { href: string; statusLabel?: string; statusTone?: string }) => {
    const dynamicStatus = agentMenuStatuses[item.href];
    return {
      label: dynamicStatus?.label || item.statusLabel,
      tone: dynamicStatus?.tone || item.statusTone,
    };
  };

  // Track breakpoint and set initial collapsed state:
  // - On mobile: всегда свёрнут по умолчанию, не сохраняем в localStorage
  // - На десктопе: восстанавливаем состояние из localStorage
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia('(max-width: 767.98px)');
    const apply = (mobile: boolean) => {
      setIsMobile(mobile);
      if (mobile) {
        setSidebarCollapsed(true);
      } else {
        const stored = localStorage.getItem('glame-ui-desktop-collapsed');
        setSidebarCollapsed(stored ? stored === '1' : false);
      }
    };
    apply(mq.matches);
    const listener = (e: MediaQueryListEvent) => apply(e.matches);
    mq.addEventListener?.('change', listener);
    return () => {
      mq.removeEventListener?.('change', listener);
    };
  }, []);
  // Persist only для десктопа
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!isMobile) {
      localStorage.setItem('glame-ui-desktop-collapsed', sidebarCollapsed ? '1' : '0');
    }
  }, [sidebarCollapsed, isMobile]);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    baseTitleRef.current = document.title || 'GLAME ИИ';
  }, []);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const hasPending = hasLiveStylistPendingAlerts(
      stylistPendingAlerts.total_unread_messages,
      stylistPendingAlerts.requested_conversations,
      stylistPendingAlerts.attention_conversations
    );
    if (!hasStylistAccess || !hasPending) {
      document.title = baseTitleRef.current;
      return;
    }
    const alertTitle = buildLiveStylistAlertTitle(
      stylistPendingAlerts.total_unread_messages,
      stylistPendingAlerts.requested_conversations,
      stylistPendingAlerts.attention_conversations
    );
    let flip = false;
    const applyTitle = () => {
      flip = !flip;
      document.title = flip ? `${alertTitle} · ${baseTitleRef.current}` : `(!) ${baseTitleRef.current}`;
    };
    applyTitle();
    const interval = window.setInterval(applyTitle, 1200);
    return () => {
      window.clearInterval(interval);
      document.title = baseTitleRef.current;
    };
  }, [hasStylistAccess, stylistPendingAlerts]);

  useEffect(() => {
    if (!isAuthenticated || !hasStylistAccess) {
      setStylistUnreadBadge(0);
      previousBadgeRef.current = null;
      return;
    }

    let disposed = false;
    const loadBadge = async () => {
      try {
        const data = await liveStylistAdmin.getInboxBadge();
        if (!disposed) {
          setStylistUnreadBadge(data.total_unread_messages || 0);
          setStylistPendingAlerts({
            total_unread_messages: data.total_unread_messages || 0,
            requested_conversations: data.requested_conversations || 0,
            attention_conversations: data.attention_conversations || 0,
          });
          const previous = previousBadgeRef.current;
          const requestedDelta = Math.max(0, (data.requested_conversations || 0) - (previous?.requested_conversations || 0));
          const attentionDelta = Math.max(0, (data.attention_conversations || 0) - (previous?.attention_conversations || 0));
          const unreadDelta = Math.max(0, (data.total_unread_messages || 0) - (previous?.total_unread_messages || 0));
          if (previous && (requestedDelta > 0 || attentionDelta > 0 || unreadDelta > 0)) {
            if (getLiveStylistSoundNotificationsEnabled()) {
              reminderSoundCooldownRef.current = Date.now();
              playLiveStylistNotificationSound();
            }
            if (getLiveStylistVibrationNotificationsEnabled() && isLiveStylistVibrationSupported()) {
              reminderSoundCooldownRef.current = Date.now();
              vibrateLiveStylistAlert();
            }
            const canShowBrowser =
              getLiveStylistBrowserNotificationsEnabled() &&
              getBrowserNotificationPermission() === 'granted' &&
              (document.hidden || pathname !== '/admin/live-stylist');
            if (canShowBrowser) {
              const title =
                requestedDelta > 0
                  ? 'Новый запрос стилисту'
                  : attentionDelta > 0
                    ? 'Обращение требует внимания'
                    : 'Новое сообщение покупателя';
              const body =
                requestedDelta > 0
                  ? `Новых обращений: +${requestedDelta}`
                  : attentionDelta > 0
                    ? `Требуют внимания: +${attentionDelta}`
                    : `Новых сообщений: +${unreadDelta}`;
              sendLiveStylistBrowserNotification(title, body, 'glame-live-stylist');
            }
          }
          const hasPending = hasLiveStylistPendingAlerts(
            data.total_unread_messages || 0,
            data.requested_conversations || 0,
            data.attention_conversations || 0
          );
          const vibrationEnabled = getLiveStylistVibrationNotificationsEnabled() && isLiveStylistVibrationSupported();
          const shouldPlayReminder =
            hasPending &&
            (getLiveStylistSoundNotificationsEnabled() || vibrationEnabled);
          const now = Date.now();
          if (shouldPlayReminder && now - reminderSoundCooldownRef.current > 25000) {
            reminderSoundCooldownRef.current = now;
            if (getLiveStylistSoundNotificationsEnabled()) {
              playLiveStylistNotificationSound();
            }
            if (vibrationEnabled) {
              vibrateLiveStylistAlert();
            }
          }
          previousBadgeRef.current = {
            total_unread_messages: data.total_unread_messages || 0,
            requested_conversations: data.requested_conversations || 0,
            attention_conversations: data.attention_conversations || 0,
          };
        }
      } catch {
        if (!disposed) {
          setStylistUnreadBadge(0);
          setStylistPendingAlerts({
            total_unread_messages: 0,
            requested_conversations: 0,
            attention_conversations: 0,
          });
        }
      }
    };

    loadBadge();
    const interval = window.setInterval(loadBadge, 10000);
    return () => {
      disposed = true;
      window.clearInterval(interval);
    };
  }, [hasStylistAccess, isAuthenticated, pathname]);

  useEffect(() => {
    if (!isAuthenticated || !hasAiMarketerAccess) {
      setAgentMenuStatuses({});
      return;
    }

    const agentLinks = [
      { href: '/ai-marketer', aliases: ['director-agent', 'ai-marketer', 'marketing-director'] },
      { href: '/ai-marketer/boards/personal-media', aliases: ['personal-media-agent', 'personal-media'] },
      { href: '/ai-marketer/boards/content', aliases: ['brand-media-agent', 'content-agent', 'brand-media'] },
      { href: '/ai-marketer/boards/crm', aliases: ['crm-agent', 'communication-agent'] },
      { href: '/ai-marketer/boards/partnership', aliases: ['pr-partnerships-agent', 'pr-partnerships'] },
      { href: '/ai-marketer/boards/traffic', aliases: ['traffic-growth-agent', 'traffic-growth'] },
      { href: '/ai-marketer/boards/analytics', aliases: ['analytics-agent'] },
      { href: '/ai-marketer/boards/product', aliases: ['assortment-agent', 'marketing-inventory-agent'] },
    ];

    const matchesAgent = (task: AgentInteractionTask, aliases: string[]) => {
      const text = `${task.source_agent} ${task.target_agent} ${task.task_type} ${task.input_data?.source_board || ''} ${task.task_context?.board || ''}`.toLowerCase();
      return aliases.some((alias) => text.includes(alias.toLowerCase()));
    };

    const buildStatus = (items: AgentInteractionTask[]) => {
      if (items.some((task) => ['failed', 'error'].includes(task.status))) {
        return { label: 'Ошибка', tone: 'error' as const };
      }
      if (items.some((task) => ['pending_approval', 'validated', 'rejected'].includes(task.status))) {
        return { label: 'Требует внимания', tone: 'attention' as const };
      }
      if (items.some((task) => ['pending', 'validating', 'queued', 'processing', 'approved'].includes(task.status))) {
        return { label: 'В работе', tone: 'active' as const };
      }
      return { label: 'Жду задание', tone: 'waiting' as const };
    };

    let disposed = false;
    const loadAgentMenuStatuses = async () => {
      try {
        const tasks = await agentInteractions.listTasks({ limit: 200 });
        if (disposed) return;
        const nextStatuses: Record<string, { label: string; tone: 'active' | 'attention' | 'error' | 'waiting' }> = {};
        for (const link of agentLinks) {
          nextStatuses[link.href] = buildStatus(tasks.filter((task) => matchesAgent(task, link.aliases)));
        }
        setAgentMenuStatuses(nextStatuses);
      } catch {
        if (!disposed) setAgentMenuStatuses({});
      }
    };

    loadAgentMenuStatuses();
    const interval = window.setInterval(loadAgentMenuStatuses, 20000);
    return () => {
      disposed = true;
      window.clearInterval(interval);
    };
  }, [hasAiMarketerAccess, isAuthenticated]);

  // Закрытие по ESC на мобильных
  useEffect(() => {
    if (!isMobile || sidebarCollapsed) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSidebarCollapsed(true);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isMobile, sidebarCollapsed]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!isMobile) return;
    if (sidebarCollapsed) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = prev;
      return;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isMobile, sidebarCollapsed]);

  if (!isAuthenticated || pathname === '/login') {
    return null;
  }

  return (
    <>
      {hasGlobalStickyAlert && (
        <div className="fixed inset-x-0 top-0 z-[80] border-b border-red-800 bg-red-600 text-white shadow-lg">
          <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 px-4 py-2 md:px-6">
            <div className="min-w-0">
              <div className="text-sm font-semibold uppercase tracking-wide text-red-100">
                Внимание: новые сообщения клиентов
              </div>
              <div className="truncate text-sm text-white">
                {alertSummaryText || 'Есть новые обращения стилисту'}
                {' · '}Непрочитанных: <span className="font-semibold">{stylistPendingAlerts.total_unread_messages}</span>
                {' · '}Новых запросов: <span className="font-semibold">{stylistPendingAlerts.requested_conversations}</span>
                {' · '}Требуют внимания: <span className="font-semibold">{stylistPendingAlerts.attention_conversations}</span>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Link
                href="/admin/live-stylist"
                className="rounded-md border border-white/30 bg-white px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50"
              >
                Открыть live-stylist
              </Link>
            </div>
          </div>
        </div>
      )}
      {hasGlobalStickyAlert && <div className="h-14" aria-hidden="true" />}
      {/* Mobile top bar */}
      <div className={`md:hidden sticky z-40 bg-white border-b border-gray-200 ${hasGlobalStickyAlert ? 'top-14' : 'top-0'}`}>
        <div className="h-14 flex items-center px-4 justify-between">
          <button
            aria-label={sidebarCollapsed ? 'Открыть меню' : 'Закрыть меню'}
            aria-expanded={!sidebarCollapsed}
            aria-controls="glame-sidebar"
            onClick={toggleSidebar}
            className="p-2 rounded-md border hover:bg-gray-50 active:scale-95 transition-transform"
          >
            ☰
          </button>
          <div className="text-lg font-bold text-gold-600">GLAME ИИ</div>
          <div />
        </div>
      </div>

      {/* Screen overlay for mobile when sidebar is open */}
      {isMobile && !sidebarCollapsed && (
        <div
          aria-hidden="true"
          onPointerDown={() => setSidebarCollapsed(true)}
          onTouchStart={() => setSidebarCollapsed(true)}
          className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[1px] transition-opacity duration-200"
        />
      )}

      {/* Sidebar */}
      <aside
        id="glame-sidebar"
        role="navigation"
        aria-label="Боковое меню"
        className={`glame-sidebar fixed left-0 top-0 h-screen bg-white border-r border-gray-200 will-change-transform transition-transform duration-300 ease-out z-50
        ${sidebarCollapsed ? '-translate-x-full md:translate-x-0 md:w-16' : 'translate-x-0 w-72'}`}
        style={
          hasGlobalStickyAlert
            ? { top: '3.5rem', height: 'calc(100vh - 3.5rem)' }
            : undefined
        }
      >
        <div className="hidden md:flex items-center justify-between h-16 px-4 border-b border-gray-200">
          <div className={`font-bold text-xl ${sidebarCollapsed ? 'sr-only' : 'block'}`}>GLAME ИИ</div>
          <button
            onClick={toggleSidebar}
            aria-label={sidebarCollapsed ? 'Развернуть сайдбар' : 'Свернуть сайдбар'}
            className="p-2 rounded-md border hover:bg-gray-50 active:scale-95 transition-transform"
          >
            {sidebarCollapsed ? '»' : '«'}
          </button>
        </div>

        <nav className="p-3 overflow-y-auto h-[calc(100vh-4rem)] md:h-[calc(100vh-4rem)]">
          <div className="mb-6">
            <div
              className={`px-3 mb-2 text-xs font-semibold tracking-wide text-gray-500 ${
                sidebarCollapsed ? 'sr-only' : 'block'
              }`}
            >
              АККАУНТ
            </div>
            <Link
              href="/profile"
              onClick={isMobile ? () => setSidebarCollapsed(true) : undefined}
              className={`glame-nav-link flex items-center gap-3 px-3 py-2 rounded-md mb-1 transition-colors select-none
              ${profileActive ? 'glame-nav-link-active border' : 'hover:bg-gray-100 active:bg-gray-200'}`}
              title={sidebarCollapsed ? 'Профиль' : undefined}
            >
              <span className="text-xl">👤</span>
              <span className={`${sidebarCollapsed ? 'sr-only' : 'block'} glame-nav-item-label font-medium`}>Профиль</span>
            </Link>
            {visibleAccountItems.map((item) => {
              const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`) || Boolean(item.matchPrefixes?.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)));
              const isStylistSection = item.sectionId === 'customer_stylist';
              return (
                <Link
                  key={item.name}
                  href={resolveNavHref(item, user?.role)}
                  onClick={isMobile ? () => setSidebarCollapsed(true) : undefined}
                  className={`glame-nav-link relative flex items-center gap-3 px-3 py-2 rounded-md mb-1 transition-colors select-none
                  ${isActive ? 'glame-nav-link-active border' : 'hover:bg-gray-100 active:bg-gray-200'}`}
                  title={sidebarCollapsed ? item.name : undefined}
                >
                  <span className="text-xl">{item.icon}</span>
                  <span className={`${sidebarCollapsed ? 'sr-only' : 'block'} glame-nav-item-label min-w-0 flex-1 font-medium`}>
                    <span className="block truncate">{item.name}</span>
                  </span>
                  {isStylistSection && stylistUnreadBadge > 0 && (
                    <span
                      className={`ml-auto rounded-full bg-red-600 px-2 py-0.5 text-xs font-semibold text-white ring-2 ring-red-200 animate-pulse ${
                        sidebarCollapsed ? 'absolute right-2 top-1.5' : ''
                      }`}
                    >
                      {stylistUnreadBadge}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>

          {visibleGroups.map((group) => (
            <div key={group.title} className="mb-6">
              <div
                className={`px-3 mb-2 text-xs font-semibold tracking-wide text-gray-500 ${
                  sidebarCollapsed ? 'sr-only' : 'block'
                }`}
              >
                {group.title}
              </div>
              <div>
                {group.items.map((item) => {
                  const isActive = pathname === item.href || (item.href !== '/ai-marketer' && pathname.startsWith(item.href));
                  const isStylistSection = item.sectionId === 'customer_stylist';
                  const agentStatus = resolveAgentMenuStatus(item);
                  return (
                    <Link
                      key={item.name}
                      href={resolveNavHref(item, user?.role)}
                      onClick={isMobile ? () => setSidebarCollapsed(true) : undefined}
                      className={`glame-nav-link flex items-center gap-3 px-3 py-2 rounded-md mb-1 transition-colors select-none
                      ${isActive ? 'glame-nav-link-active border' : 'hover:bg-gray-100 active:bg-gray-200'}`}
                      title={sidebarCollapsed ? item.name : undefined}
                    >
                      <span className="text-xl">{item.icon}</span>
                      <span className={`${sidebarCollapsed ? 'sr-only' : 'block'} glame-nav-item-label min-w-0 flex-1 font-medium`}>
                        <span className="block truncate">{item.name}</span>
                        {agentStatus.label && (
                          <span className={`mt-1 inline-flex max-w-full truncate rounded-full border px-1.5 py-0.5 text-[10px] leading-none ${agentStatusClass(agentStatus.tone)}`}>
                            {agentStatus.label}
                          </span>
                        )}
                      </span>
                      {isStylistSection && stylistUnreadBadge > 0 && (
                        <span
                          className={`ml-auto rounded-full bg-red-600 px-2 py-0.5 text-xs font-semibold text-white ring-2 ring-red-200 animate-pulse ${
                            sidebarCollapsed ? 'absolute right-2 top-1.5' : ''
                          }`}
                        >
                          {stylistUnreadBadge}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </aside>
      {/* Content spacer for desktop */}
      <div className={`hidden md:block ${sidebarCollapsed ? 'w-16' : 'w-72'}`} />
    </>
  );
}
