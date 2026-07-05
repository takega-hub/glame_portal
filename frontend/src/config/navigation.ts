export type NavItem = {
  name: string;
  href: string;
  icon: string;
  sectionId: string;
  sellerHref?: string;
  matchPrefixes?: string[];
  statusLabel?: string;
  statusTone?: 'active' | 'attention' | 'error' | 'waiting';
};

export const ACCOUNT_NAV_ITEMS: NavItem[] = [
  { name: 'Связь со стилистом', href: '/admin/live-stylist', icon: '💬', sectionId: 'customer_stylist' },
  { name: 'План/Факт', href: '/profile/sellers/dashboard', sellerHref: '/profile/sellers/personal', icon: '🛍️', sectionId: 'sellers', matchPrefixes: ['/profile/sellers'] },
  { name: 'Фото украшений', href: '/profile/sellers/jewelry-photo', icon: '📷', sectionId: 'sellers' },
  { name: 'Обучение GLAME', href: '/profile/training', icon: '🎓', sectionId: 'seller_training' },
];

export const NAVIGATION_GROUPS: Array<{ title: string; items: NavItem[] }> = [
  {
    title: 'AI ИНСТРУМЕНТЫ',
    items: [
      { name: 'AI Директор', href: '/ai-marketer', icon: '🎛️', sectionId: 'ai_marketer', statusLabel: 'Активен', statusTone: 'active' },
      { name: 'AI Personal Media', href: '/ai-marketer/boards/personal-media', icon: '👤', sectionId: 'ai_marketer', statusLabel: 'Жду задание', statusTone: 'waiting' },
      { name: 'AI Brand Media', href: '/ai-marketer/boards/content', icon: '🏷️', sectionId: 'ai_marketer', statusLabel: 'Требует внимания', statusTone: 'attention' },
      { name: 'AI CRM', href: '/ai-marketer/boards/crm', icon: '👥', sectionId: 'ai_marketer', statusLabel: 'Жду задание', statusTone: 'waiting' },
      { name: 'AI PR & Partnerships', href: '/ai-marketer/boards/partnership', icon: '🤝', sectionId: 'ai_marketer', statusLabel: 'Жду задание', statusTone: 'waiting' },
      { name: 'AI Traffic & Growth', href: '/ai-marketer/boards/traffic', icon: '📈', sectionId: 'ai_marketer', statusLabel: 'Жду задание', statusTone: 'waiting' },
      { name: 'AI Analytics', href: '/ai-marketer/boards/analytics', icon: '📊', sectionId: 'ai_marketer', statusLabel: 'Жду задание', statusTone: 'waiting' },
      { name: 'AI Assortment', href: '/ai-marketer/boards/product', icon: '💎', sectionId: 'ai_marketer', statusLabel: 'Требует внимания', statusTone: 'attention' },
      { name: 'AI Тренер консультантов', href: '/admin/consultant-training', icon: '🎓', sectionId: 'consultant_training', statusLabel: 'MVP', statusTone: 'active' },
    ],
  },
  {
    title: 'АРХИВ',
    items: [
      { name: 'Генератор контента', href: '/content-generator', icon: '✍️', sectionId: 'content_generator', statusLabel: 'Архив', statusTone: 'waiting' },
      { name: 'Массовая генерация', href: '/admin/batch-messages', icon: '📨', sectionId: 'batch_messages', statusLabel: 'Архив', statusTone: 'waiting' },
      { name: 'AI Контент-агент', href: '/content-agent', icon: '🗓️', sectionId: 'content_agent', statusLabel: 'Архив', statusTone: 'waiting' },
    ],
  },
  {
    title: 'УПРАВЛЕНИЕ',
    items: [
      { name: 'База знаний', href: '/knowledge-base', icon: '📚', sectionId: 'knowledge_base' },
      { name: 'Каталог товаров', href: '/products', icon: '💍', sectionId: 'products' },
      { name: 'Образы', href: '/looks', icon: '👗', sectionId: 'looks' },
      { name: 'Покупатели', href: '/admin/customers', icon: '👥', sectionId: 'customers' },
      { name: 'Партнеры', href: '/admin/referrals', icon: '🤝', sectionId: 'referrals_admin' },
      { name: 'Товары за баллы', href: '/admin/referrals#reward-store', icon: '🎁', sectionId: 'referrals_admin', matchPrefixes: ['/admin/referrals'] },
    ],
  },
  {
    title: 'АНАЛИТИКА',
    items: [
      { name: 'Аналитика', href: '/analytics', icon: '📊', sectionId: 'analytics' },
      { name: 'Аналитика товара', href: '/product-analytics', icon: '📦', sectionId: 'product_analytics' },
    ],
  },
  {
    title: 'СИСТЕМА',
    items: [
      { name: 'Настройки', href: '/settings', icon: '⚙️', sectionId: 'settings' },
      { name: 'CRON регламенты', href: '/admin/cron', icon: '⏱️', sectionId: 'admin_cron' },
      { name: 'Администрирование приложения', href: '/admin/app', icon: '📱', sectionId: 'app_admin' },
      { name: 'Администрирование доставки', href: '/admin/shipping', icon: '🚚', sectionId: 'shipping_admin' },
      { name: 'Админка запасов', href: '/admin/inventory-control', icon: '🧩', sectionId: 'inventory_admin' },
      { name: 'Системные промпты', href: '/admin/prompts', icon: '🧠', sectionId: 'system_prompts' },
      { name: 'Роли и доступы', href: '/admin/roles', icon: '🔐', sectionId: 'roles_access' },
    ],
  },
];

export const ALL_NAV_ITEMS = [...ACCOUNT_NAV_ITEMS, ...NAVIGATION_GROUPS.flatMap((group) => group.items)];

export function resolveNavHref(item: NavItem, role?: string | null): string {
  if (role === 'seller' && item.sellerHref) return item.sellerHref;
  return item.href;
}

export function getFirstAllowedHref(sectionIds: string[] | undefined | null, role?: string | null): string {
  const allowed = new Set(sectionIds || []);
  const item = ALL_NAV_ITEMS.find((navItem) => allowed.has(navItem.sectionId));
  return item ? resolveNavHref(item, role) : '/login';
}

export function findSectionForPath(pathname: string): NavItem | null {
  const candidates = [...ALL_NAV_ITEMS].sort((a, b) => b.href.length - a.href.length);
  return candidates.find((item) => {
    if (pathname === item.href || pathname.startsWith(`${item.href}/`)) return true;
    return item.matchPrefixes?.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
  }) || null;
}
