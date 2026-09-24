'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import AgentBoardChat from '@/components/agents/AgentBoardChat';
import BoardHeader from '@/components/boards/BoardHeader';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { advertisingConnections, agentInteractions, aiMarketer, apiClient, type AdvertisingAuthorizationLink, type AdvertisingConnection, type AdvertisingConnectionInput, type AdvertisingOAuthReadiness, type AgentInteractionTask, type CampaignMediaResponse, type TrafficCampaignBrief, type TrafficCampaignBriefResponse, type TrafficProjectTopic, type YandexBusinessFeedFilters, type YandexBusinessFeedPreview, type YandexBusinessFeedPublicSettings } from '@/lib/api';

type MarketingCampaign = {
  id: string;
  name: string;
  type: string;
  status: string;
  budget?: number | null;
  target_audience?: Record<string, any> | null;
  channels?: string[] | null;
  metrics?: Record<string, any> | null;
  start_date: string;
  external_source?: string | null;
  external_id?: string | null;
  advertising_connection_id?: string | null;
};

type AdvertisingAnalytics = {
  period_days: number;
  scope?: { metrika_counter_id?: string | null; mode: 'all' | 'store' };
  freshness?: string | null;
  totals: { impressions: number; clicks: number; cost: number; conversions: number; ctr: number; cpc: number };
  campaigns: Array<{ campaign_id?: string | null; campaign_name: string; impressions: number; clicks: number; cost: number; conversions: number; ctr: number; cpc: number }>;
  sources: Record<string, { status: string; message: string }>;
  funnel?: { impressions: number; clicks: number; card_opens: number; routes: number; calls: number; website_visits: number; conversions: number };
  maps_facts?: { card_opens: number; routes: number; calls: number; messages: number; website_clicks: number };
  business_stores?: Array<{ connection_id: string; store_name: string; days: number; card_opens: number; routes: number; calls: number; messages: number; website_clicks: number }>;
  metrika_counters?: Array<{ id: string; name: string; counter_id: string; status: string; data?: { visits?: number; users?: number; pageviews?: number }; organization_actions?: { is_organization_counter?: boolean; card_opens?: number; routes?: number; calls?: number; route_starts?: number; messages?: number; website_clicks?: number } }>;
  metrika_organization_actions?: { card_opens: number; routes: number; calls: number; route_starts: number; messages: number; website_clicks: number };
};

const formatNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const formatCurrency = new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 });

const YALTA_CAMPAIGN_TEMPLATES = [
  {
    code: 'GLAME_YALTA_MAPS',
    title: 'GLAME Ялта — Яндекс Карты',
    channel: 'yandex_maps',
    description: 'Пилот продвижения карточки GLAME в Яндекс Картах: проверить карточку, маршрут, звонки, фото, оффер и KPI офлайн-визита.',
    budget: 700,
    kpi: 'Открытия карточки, маршруты, звонки и подтверждённые визиты',
  },
  {
    code: 'GLAME_YALTA_SEARCH_HOT',
    title: 'GLAME Ялта — горячий поиск',
    channel: 'yandex_search',
    description: 'Поисковая кампания Яндекса для горячего спроса на украшения и подарки в Ялте.',
    budget: 500,
    kpi: 'Горячие переходы, маршруты и визиты из поиска',
  },
  {
    code: 'GLAME_YALTA_GEO_NOW',
    title: 'GLAME Ялта — рядом сейчас',
    channel: 'yandex_rsy_geo',
    description: 'Гео-кампания для людей рядом с магазином: радиус, расписание, креативы и маршрут в Яндекс Картах.',
    budget: 500,
    kpi: 'Маршруты и визиты людей в радиусе 0,5–1 км',
  },
  {
    code: 'GLAME_YALTA_TOURIST_GEO',
    title: 'GLAME Ялта — туристический гео-трафик',
    channel: 'yandex_rsy_tourist_geo',
    description: 'Тест туристических геосегментов: набережная, пляж, отели, рестораны, прогулочные зоны и точки прибытия.',
    budget: 0,
    kpi: 'Охват доступного инвентаря, маршруты и визиты туристов',
  },
  {
    code: 'GLAME_YALTA_GIFT',
    title: 'GLAME Ялта — подарок',
    channel: 'yandex_search_gift',
    description: 'Поиск и РСЯ для подарочного спроса в Ялте: быстрый подбор, консультант и фирменная упаковка.',
    budget: 300,
    kpi: 'Визиты и покупки по подарочному сценарию',
  },
] as const;

const CARD_CHECKLIST_LABELS: Record<string, string> = {
  address: 'Адрес ялтинского магазина',
  hours: 'График работы',
  phone: 'Телефон',
  route: 'Построение маршрута',
  entrance_photo: 'Фото фасада и входа',
  interior_photo: 'Фото интерьера и витрины',
  reviews: 'Отзывы и ответы',
};

const EMPTY_CONNECTION_FORM: AdvertisingConnectionInput = {
  platform: 'yandex_direct',
  name: '',
  account_login: '',
  client_login: '',
  organization_name: 'GLAME Ялта',
  is_active: true,
};

const AD_PLATFORM_LABELS: Record<AdvertisingConnectionInput['platform'], string> = {
  yandex_direct: 'Яндекс Директ',
  yandex_business: 'Яндекс Бизнес',
  yandex_maps: 'Яндекс Карты',
};

const BUSINESS_PRODUCT_LABELS: Record<string, string> = {
  advertising_subscription: 'Рекламная подписка',
  maps_priority: 'Приоритетное размещение в Картах',
  maps_branded_priority: 'Брендированное размещение в Картах',
};

type CreativePreview = { name: string; headline: string; text: string; cta: string; banner: string };

function creativePreviews(task?: AgentInteractionTask): CreativePreview[] {
  const raw = String(task?.output_data?.result || task?.output_data?.text || '');
  if (!raw) return [];
  const blocks = raw.split(/(?=Вариант\s+\d+[.։])/i).filter((block) => /^Вариант\s+\d+/i.test(block.trim()));
  return blocks.slice(0, 3).map((block, index) => {
    const pick = (pattern: RegExp) => block.match(pattern)?.[1]?.trim().replace(/\n+/g, ' ') || '';
    return {
      name: block.match(/^Вариант\s+\d+\.\s*[“"]?([^\n”"]+)/i)?.[1]?.trim() || `Вариант ${index + 1}`,
      headline: pick(/Заголовок 1:\s*\n?([^\n]+)/i),
      text: pick(/Текст объявления:\s*\n?([\s\S]*?)(?=\n\s*CTA:|\n\s*Дополнительные CTA:|\n\s*Текст для РСЯ|$)/i),
      cta: pick(/CTA:\s*\n?([^\n]+)/i),
      banner: pick(/Текст для РСЯ\s*\/\s*баннера:\s*\n?([\s\S]*?)(?=\n\s*Короткая версия:|\n\s*ТЗ на баннер:|$)/i),
    };
  });
}

function isTrafficTask(task: AgentInteractionTask) {
  const text = `${task.source_agent} ${task.target_agent} ${task.task_type}`.toLowerCase();
  return text.includes('traffic') || text.includes('growth') || text.includes('retarget') || text.includes('ads');
}

function UtilityPanel({ title, description, onClose, children }: { title: string; description: string; onClose: () => void; children: ReactNode }) {
  return (
    <div role="dialog" aria-modal="true" aria-label={title} className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/45 p-3 sm:p-8">
      <div className="w-full max-w-6xl overflow-hidden rounded-xl bg-gray-50 shadow-2xl">
        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-gray-200 bg-white px-4 py-4 sm:px-6">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
            <p className="mt-1 text-sm text-gray-500">{description}</p>
          </div>
          <Button type="button" size="sm" variant="outline" onClick={onClose}>Закрыть</Button>
        </div>
        <div className="max-h-[calc(100vh-8rem)] overflow-y-auto p-4 sm:p-6">{children}</div>
      </div>
    </div>
  );
}

export default function TrafficGrowthBoard() {
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [projectTopics, setProjectTopics] = useState<TrafficProjectTopic[]>([]);
  const [campaigns, setCampaigns] = useState<MarketingCampaign[]>([]);
  const [visits, setVisits] = useState<Record<string, any> | null>(null);
  const [advertisingAnalytics, setAdvertisingAnalytics] = useState<AdvertisingAnalytics | null>(null);
  const [selectedAnalyticsCounterId, setSelectedAnalyticsCounterId] = useState('');
  const [campaignCounterSavingId, setCampaignCounterSavingId] = useState('');
  const [campaignLinkSavingId, setCampaignLinkSavingId] = useState('');
  const [selectedProjectTaskId, setSelectedProjectTaskId] = useState('');
  const [briefState, setBriefState] = useState<TrafficCampaignBriefResponse | null>(null);
  const [feedPreview, setFeedPreview] = useState<YandexBusinessFeedPreview | null>(null);
  const [feedFilterOptions, setFeedFilterOptions] = useState<YandexBusinessFeedFilters | null>(null);
  const [feedFilters, setFeedFilters] = useState({ minPrice: '', maxPrice: '', availability: 'all', brand: '', category: '', storeId: '' });
  const [publicFeedSettings, setPublicFeedSettings] = useState<YandexBusinessFeedPublicSettings | null>(null);
  const [publicFeedSaving, setPublicFeedSaving] = useState(false);
  const [adConnections, setAdConnections] = useState<AdvertisingConnection[]>([]);
  const [oauthReadiness, setOauthReadiness] = useState<AdvertisingOAuthReadiness | null>(null);
  const [oauthForm, setOauthForm] = useState({ client_id: '', client_secret: '' });
  const [oauthFormOpen, setOauthFormOpen] = useState(false);
  const [oauthSaving, setOauthSaving] = useState(false);
  const [authorizationInfo, setAuthorizationInfo] = useState<(AdvertisingAuthorizationLink & { connectionId: string }) | null>(null);
  const [authorizationCreatingId, setAuthorizationCreatingId] = useState('');
  const [connectionForm, setConnectionForm] = useState<AdvertisingConnectionInput>(EMPTY_CONNECTION_FORM);
  const [editingConnectionId, setEditingConnectionId] = useState<string | null>(null);
  const [connectionFormOpen, setConnectionFormOpen] = useState(false);
  const [connectionSaving, setConnectionSaving] = useState(false);
  const [deletingConnectionId, setDeletingConnectionId] = useState('');
  const [syncingConnectionId, setSyncingConnectionId] = useState('');
  const [directTestCreatingId, setDirectTestCreatingId] = useState('');
  const [mapsMetricsForm, setMapsMetricsForm] = useState({ connection_id: '', metric_date: new Date().toISOString().slice(0, 10), card_opens: '', routes: '', calls: '', messages: '', website_clicks: '' });
  const [mapsMetricsSaving, setMapsMetricsSaving] = useState(false);
  const [businessMetricsFile, setBusinessMetricsFile] = useState<File | null>(null);
  const [businessMetricsImporting, setBusinessMetricsImporting] = useState(false);
  const [businessMetricsImportResult, setBusinessMetricsImportResult] = useState<string | null>(null);
  const [businessMetricsImportError, setBusinessMetricsImportError] = useState<string | null>(null);
  const [metrikaSettings, setMetrikaSettings] = useState<{ configured: boolean; counter_id?: string | null; oauth_token_configured: boolean; counters?: Array<{ id: string; name: string; counter_id: string }> } | null>(null);
  const [metrikaForm, setMetrikaForm] = useState({ name: '', counter_id: '', oauth_token: '' });
  const [metrikaSaving, setMetrikaSaving] = useState(false);
  const [metrikaFormOpen, setMetrikaFormOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [returnStrategyAssignment, setReturnStrategyAssignment] = useState('');
  const [deletingProjectId, setDeletingProjectId] = useState('');
  const [briefSaving, setBriefSaving] = useState(false);
  const [creativeCreating, setCreativeCreating] = useState(false);
  const [creativeReviewNote, setCreativeReviewNote] = useState('');
  const [creativeReviewSaving, setCreativeReviewSaving] = useState(false);
  const [productionArming, setProductionArming] = useState(false);
  const [productionDraftCreating, setProductionDraftCreating] = useState(false);
  const [publicationChecklistSaving, setPublicationChecklistSaving] = useState(false);
  const [publicationChecklist, setPublicationChecklist] = useState({ media_rights_confirmed: false, promo_code_confirmed: false, landing_confirmed: false });
  const [directPackageSaving, setDirectPackageSaving] = useState(false);
  const [directGroupCreating, setDirectGroupCreating] = useState(false);
  const [directAdsSaving, setDirectAdsSaving] = useState(false);
  const [directAdsCreating, setDirectAdsCreating] = useState(false);
  const [directAdsForm, setDirectAdsForm] = useState({ titles: '', texts: '' });
  const [directKeywordsSaving, setDirectKeywordsSaving] = useState(false);
  const [directKeywordsCreating, setDirectKeywordsCreating] = useState(false);
  const [directKeywords, setDirectKeywords] = useState('');
  const [directImageIds, setDirectImageIds] = useState<string[]>([]);
  const [directImagesUploading, setDirectImagesUploading] = useState(false);
  const [directImagesAttaching, setDirectImagesAttaching] = useState(false);
  const [directModerationSubmitting, setDirectModerationSubmitting] = useState(false);
  const [directModerationAcknowledged, setDirectModerationAcknowledged] = useState(false);
  const [directModerationChecking, setDirectModerationChecking] = useState(false);
  const [directPackage, setDirectPackage] = useState({ ad_group_name: '', region_id: '', landing_url: '', promo_code: '', utm_template: '' });
  const [productionForm, setProductionForm] = useState({ connectionId: '', metrikaCounterId: '' });
  const [creativeMedia, setCreativeMedia] = useState<CampaignMediaResponse | null>(null);
  const [selectedCreativeVariants, setSelectedCreativeVariants] = useState<number[]>([]);
  const [feedLoading, setFeedLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [utilityPanel, setUtilityPanel] = useState<'accounts' | 'direct-campaigns' | 'feed' | 'analytics' | null>(null);

  const directCampaigns = useMemo(() => campaigns.filter((campaign) => campaign.external_source === 'yandex_direct'), [campaigns]);
  const selectedProjectTask = useMemo(() => tasks.find((task) => task.id === selectedProjectTaskId), [tasks, selectedProjectTaskId]);

  const creativeTask = useMemo(() => tasks
    .filter((task) => task.task_type === 'advertising_creatives' && (task.input_data?.parent_traffic_task_id === selectedProjectTaskId || task.task_context?.parent_traffic_task_id === selectedProjectTaskId))
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())[0], [selectedProjectTaskId, tasks]);
  const creativeButtonLabel = creativeCreating
    ? 'Передача...'
    : creativeTask?.status === 'completed'
      ? 'Креативы готовы'
      : creativeTask
        ? 'Креативы в работе'
        : 'Подготовить креативы';
  const creativePreviewItems = useMemo(() => creativePreviews(creativeTask), [creativeTask]);
  const directCompatibleMedia = useMemo(() => (creativeMedia?.assets || []).filter((asset) => /^\/static\/.+\.(jpe?g|png|gif)(?:\?.*)?$/i.test(asset.url)), [creativeMedia]);
  const productionRelease = selectedProjectTask?.task_context?.direct_production_release;
  const publicationChecksComplete = Boolean(
    productionRelease?.publication_checklist?.media_rights_confirmed
    && productionRelease?.publication_checklist?.promo_code_confirmed
    && productionRelease?.publication_checklist?.landing_confirmed,
  );
  const directLaunchTimeline = [
    { key: 'armed', label: 'Кабинет, счётчик и лимит зафиксированы', done: ['armed', 'direct_draft_created', 'direct_group_created', 'direct_ads_draft_created', 'direct_targeting_draft_created', 'direct_images_uploaded', 'direct_images_attached', 'direct_moderation_requested'].includes(productionRelease?.status) },
    { key: 'campaign', label: 'Черновик ЕПК создан', done: ['direct_draft_created', 'direct_group_created', 'direct_ads_draft_created', 'direct_targeting_draft_created', 'direct_images_uploaded', 'direct_images_attached', 'direct_moderation_requested'].includes(productionRelease?.status) },
    { key: 'group', label: 'Пустая Unified-группа создана', done: ['direct_group_created', 'direct_ads_draft_created', 'direct_targeting_draft_created', 'direct_images_uploaded', 'direct_images_attached', 'direct_moderation_requested'].includes(productionRelease?.status) },
    { key: 'ad', label: 'Комбинаторное объявление создано как черновик', done: ['direct_ads_draft_created', 'direct_targeting_draft_created', 'direct_images_uploaded', 'direct_images_attached', 'direct_moderation_requested'].includes(productionRelease?.status) },
    { key: 'keywords', label: 'Ключевые фразы добавлены', done: ['direct_targeting_draft_created', 'direct_images_uploaded', 'direct_images_attached', 'direct_moderation_requested'].includes(productionRelease?.status) },
    { key: 'images', label: 'Изображения загружены и привязаны', done: ['direct_images_attached', 'direct_moderation_requested'].includes(productionRelease?.status) },
    { key: 'moderation', label: 'Отправлено на модерацию по подтверждению', done: productionRelease?.status === 'direct_moderation_requested' },
  ];
  const directExecutionHistory = useMemo(() => {
    if (!productionRelease) return [];
    return [
      productionRelease.direct_campaign_created_at ? { label: `ЕПК-черновик № ${productionRelease.direct_campaign_id}`, at: productionRelease.direct_campaign_created_at, detail: 'Создан в Яндекс Директе без групп и объявлений.' } : null,
      productionRelease.direct_group_created_at ? { label: `Unified-группа № ${productionRelease.direct_group_id}`, at: productionRelease.direct_group_created_at, detail: 'Создана как пустая группа.' } : null,
      productionRelease.direct_ad_created_at ? { label: `Объявление-черновик № ${productionRelease.direct_ad_id}`, at: productionRelease.direct_ad_created_at, detail: 'Комбинаторное объявление, до модерации не показывается.' } : null,
      productionRelease.direct_keywords_created_at ? { label: `Добавлены ключевые фразы (${productionRelease.direct_keyword_ids?.length || 0})`, at: productionRelease.direct_keywords_created_at, detail: 'Условия сохранены в черновике.' } : null,
      productionRelease.direct_images_uploaded_at ? { label: `Изображения загружены (${productionRelease.direct_image_hashes?.length || 0})`, at: productionRelease.direct_images_uploaded_at, detail: 'Импортированы в библиотеку Директа.' } : null,
      productionRelease.direct_images_attached_at ? { label: 'Изображения привязаны к объявлению', at: productionRelease.direct_images_attached_at, detail: 'Внешняя модерация ещё не запускалась на этом шаге.' } : null,
      productionRelease.moderation_requested_at ? { label: 'Запрос на модерацию', at: productionRelease.moderation_requested_at, detail: `Подтверждён администратором ${productionRelease.moderation_requested_by || 'GLAME'}.` } : null,
      productionRelease.direct_moderation_last_check?.checked_at ? { label: 'Проверен статус модерации', at: productionRelease.direct_moderation_last_check.checked_at, detail: `${productionRelease.direct_moderation_last_check.state || '—'} · ${productionRelease.direct_moderation_last_check.status || '—'}` } : null,
    ].filter(Boolean) as Array<{ label: string; at: string; detail: string }>;
  }, [productionRelease]);
  const latestGrowthStrategies = useMemo(() => {
    const latest: Record<string, AgentInteractionTask> = {};
    for (const task of tasks) {
      const key = task.task_type === 'traffic_amplification' ? 'amplification' : task.task_type === 'return_strategy' ? `return:${task.input_data?.channel || 'growth'}` : '';
      if (!key || (latest[key]?.created_at || '') >= (task.created_at || '')) continue;
      latest[key] = task;
    }
    return latest;
  }, [tasks]);

  useEffect(() => {
    loadData();
    loadFeedPreview();
    loadFeedFilterOptions();
    loadPublicFeedSettings();
    loadAdvertisingConnections();
    loadMetrikaSettings();
  }, []);

  useEffect(() => {
    if (!selectedProjectTaskId) {
      setBriefState(null);
      return;
    }
    agentInteractions.getTrafficCampaignBrief(selectedProjectTaskId)
      .then(setBriefState)
      .catch(() => setBriefState(null));
  }, [selectedProjectTaskId]);

  useEffect(() => {
    if (!creativeTask?.id) {
      setCreativeMedia(null);
      return;
    }
    agentInteractions.getContentProjectCampaignMedia(creativeTask.id).then(setCreativeMedia).catch(() => setCreativeMedia(null));
  }, [creativeTask?.id]);

  useEffect(() => {
    const checklist = selectedProjectTask?.task_context?.direct_production_release?.publication_checklist;
    setPublicationChecklist({
      media_rights_confirmed: checklist?.media_rights_confirmed === true,
      promo_code_confirmed: checklist?.promo_code_confirmed === true,
      landing_confirmed: checklist?.landing_confirmed === true,
    });
  }, [selectedProjectTaskId, selectedProjectTask?.task_context?.direct_production_release?.created_at]);

  useEffect(() => {
    const release = selectedProjectTask?.task_context?.direct_production_release;
    const saved = release?.direct_publication_package;
    const code = briefState?.brief.campaign_code || selectedProjectTask?.input_data?.campaign_code || 'GLAME';
    setDirectPackage({
      ad_group_name: saved?.ad_group_name || `${code} — локальная группа`,
      region_id: saved?.region_id || '',
      landing_url: saved?.landing_url || briefState?.brief.maps_card_url || '',
      promo_code: saved?.promo_code || '',
      utm_template: saved?.utm_template || 'utm_source=yandex&utm_medium=cpc&utm_campaign={campaign_id}&utm_content={ad_id}',
    });
  }, [selectedProjectTaskId, productionRelease?.created_at, briefState?.brief.campaign_code, briefState?.brief.maps_card_url]);

  useEffect(() => {
    const saved = selectedProjectTask?.task_context?.direct_production_release?.direct_ads_package;
    setDirectAdsForm({
      titles: Array.isArray(saved?.titles) ? saved.titles.join('\n') : creativePreviewItems.slice(0, 3).map((item) => item.headline).join('\n'),
      texts: Array.isArray(saved?.texts) ? saved.texts.join('\n') : creativePreviewItems.slice(0, 3).map((item) => item.text).join('\n'),
    });
  }, [selectedProjectTaskId, productionRelease?.direct_group_id, creativeTask?.id]);

  useEffect(() => {
    const saved = selectedProjectTask?.task_context?.direct_production_release?.direct_keywords_package;
    setDirectKeywords(Array.isArray(saved?.keywords) ? saved.keywords.join('\n') : 'ювелирный магазин ялта\nукрашения ялта\nподарок ялта\nкольца ялта\nсерьги ялта');
  }, [selectedProjectTaskId, productionRelease?.direct_ad_id]);

  useEffect(() => {
    const imported = selectedProjectTask?.task_context?.direct_production_release?.direct_image_assets;
    if (Array.isArray(imported) && imported.length) {
      setDirectImageIds(imported.map((item: any) => String(item.id)));
      return;
    }
    setDirectImageIds(directCompatibleMedia.slice(0, 3).map((asset) => asset.id));
  }, [selectedProjectTaskId, Array.isArray(productionRelease?.direct_keyword_ids) ? productionRelease.direct_keyword_ids.join(',') : '', directCompatibleMedia]);

  async function loadData(counterScope = selectedAnalyticsCounterId) {
    setLoading(true);
    setError(null);
    const [loadedTasks, loadedCampaigns, visitsData, loadedProjects, analyticsData] = await Promise.all([
      agentInteractions.listTasks({ limit: 150 }).then((items) => items.filter(isTrafficTask)).catch(() => []),
      apiClient.get<MarketingCampaign[]>('/api/marketing/campaigns').then((response) => response.data || []).catch(() => []),
      apiClient.get<Record<string, any>>('/api/analytics/store-visits/daily?days=14').then((response) => response.data).catch(() => null),
      agentInteractions.listTrafficProjects(50).catch(() => []),
      apiClient.get<AdvertisingAnalytics>(`/api/marketing/advertising-analytics?days=14${counterScope ? `&metrika_counter_id=${encodeURIComponent(counterScope)}` : ''}`).then((response) => response.data).catch(() => null),
    ]);
    setTasks(loadedTasks);
    setProjectTopics(loadedProjects);
    setCampaigns(loadedCampaigns.filter((campaign) => ['paid', 'social', 'ads', 'traffic', 'retargeting'].includes(campaign.type)));
    setVisits(visitsData);
    setAdvertisingAnalytics(analyticsData);
    if (!selectedProjectTaskId && loadedProjects[0]?.task_id) {
      setSelectedProjectTaskId(loadedProjects[0].task_id);
    } else if (selectedProjectTaskId && !loadedProjects.some((project) => project.task_id === selectedProjectTaskId)) {
      setSelectedProjectTaskId(loadedProjects[0]?.task_id || '');
    }
    setLoading(false);
  }

  async function loadAdvertisingConnections() {
    try {
      const [connections, readiness] = await Promise.all([
        advertisingConnections.list(),
        advertisingConnections.oauthReadiness(),
      ]);
      setAdConnections(connections);
      setOauthReadiness(readiness);
      setOauthForm({ client_id: readiness.client_id || '', client_secret: '' });
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось загрузить рекламные кабинеты');
    }
  }

  async function loadMetrikaSettings() {
    try {
      const settings = (await apiClient.get<{ configured: boolean; counter_id?: string | null; oauth_token_configured: boolean; counters?: Array<{ id: string; name: string; counter_id: string }> }>('/api/marketing/advertising-analytics/yandex-metrika-settings')).data;
      setMetrikaSettings(settings);
      setMetrikaForm({ name: '', counter_id: '', oauth_token: '' });
    } catch {
      setMetrikaSettings(null);
    }
  }

  async function saveMetrikaSettings() {
    if (metrikaSaving) return;
    setMetrikaSaving(true);
    setError(null);
    try {
      const settings = (await apiClient.put<{ configured: boolean; counter_id?: string | null; oauth_token_configured: boolean; counters?: Array<{ id: string; name: string; counter_id: string }> }>('/api/marketing/advertising-analytics/yandex-metrika-settings', metrikaForm)).data;
      setMetrikaSettings(settings);
      setMetrikaForm({ name: '', counter_id: '', oauth_token: '' });
      setMetrikaFormOpen(false);
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить доступ Яндекс Метрики');
    } finally {
      setMetrikaSaving(false);
    }
  }

  async function saveBusinessMapsMetrics() {
    if (!mapsMetricsForm.connection_id || mapsMetricsSaving) return;
    setMapsMetricsSaving(true);
    setError(null);
    try {
      await apiClient.post('/api/marketing/advertising-analytics/yandex-business-maps-daily', {
        connection_id: mapsMetricsForm.connection_id,
        metric_date: mapsMetricsForm.metric_date,
        card_opens: Number(mapsMetricsForm.card_opens) || 0,
        routes: Number(mapsMetricsForm.routes) || 0,
        calls: Number(mapsMetricsForm.calls) || 0,
        messages: Number(mapsMetricsForm.messages) || 0,
        website_clicks: Number(mapsMetricsForm.website_clicks) || 0,
      });
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить показатели Яндекс Бизнес/Карт');
    } finally {
      setMapsMetricsSaving(false);
    }
  }

  async function importBusinessMapsMetrics() {
    if (!mapsMetricsForm.connection_id || !businessMetricsFile || businessMetricsImporting) return;
    setBusinessMetricsImporting(true);
    setBusinessMetricsImportResult(null);
    setBusinessMetricsImportError(null);
    setError(null);
    try {
      const payload = new FormData();
      payload.append('connection_id', mapsMetricsForm.connection_id);
      payload.append('file', businessMetricsFile);
      const result = (await apiClient.post<{ created: number; updated: number; skipped: number }>('/api/marketing/advertising-analytics/yandex-business-maps-import', payload)).data;
      setBusinessMetricsImportResult(`Загружено: ${result.created + result.updated}; новых: ${result.created}, обновлено: ${result.updated}${result.skipped ? `, пропущено: ${result.skipped}` : ''}.`);
      setBusinessMetricsFile(null);
      await loadData();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : detail?.message || 'Не удалось импортировать статистику Яндекс Бизнеса';
      setBusinessMetricsImportError(message);
      setError(message);
    } finally {
      setBusinessMetricsImporting(false);
    }
  }

  async function saveOAuthSettings() {
    if (oauthSaving) return;
    setOauthSaving(true);
    setError(null);
    try {
      const saved = await advertisingConnections.saveOAuthSettings(oauthForm);
      setOauthReadiness(saved);
      setOauthForm({ client_id: saved.client_id || oauthForm.client_id, client_secret: '' });
      setOauthFormOpen(false);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить настройки OAuth Яндекса');
    } finally {
      setOauthSaving(false);
    }
  }

  function openConnectionForm(connection?: AdvertisingConnection) {
    setEditingConnectionId(connection?.id || null);
    setConnectionForm(connection ? {
      platform: connection.platform,
      name: connection.name,
      account_login: connection.account_login || '',
      client_login: connection.client_login || '',
      organization_name: connection.organization_name || '',
      metrika_counter_id: connection.metrika_counter_id || '',
      permissions: connection.permissions || {},
      is_active: connection.is_active,
    } : { ...EMPTY_CONNECTION_FORM });
    setConnectionFormOpen(true);
  }

  function openBusinessConnectionForm() {
    setEditingConnectionId(null);
    setConnectionForm({
      platform: 'yandex_business',
      name: 'GLAME Ялта — Яндекс Бизнес',
      account_login: '',
      client_login: '',
      organization_name: 'GLAME Ялта',
      metrika_counter_id: '',
      permissions: { business_product: 'advertising_subscription' },
      is_active: true,
    });
    setConnectionFormOpen(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function saveAdvertisingConnection() {
    if (!connectionForm.name.trim() || connectionSaving) {
      if (!connectionForm.name.trim()) setError('Укажите понятное название рекламного кабинета.');
      return;
    }
    setConnectionSaving(true);
    setError(null);
    try {
      const payload = {
        ...connectionForm,
        name: connectionForm.name.trim(),
        account_login: connectionForm.account_login?.trim() || null,
        client_login: connectionForm.client_login?.trim() || null,
        organization_name: connectionForm.organization_name?.trim() || null,
        metrika_counter_id: connectionForm.metrika_counter_id?.trim() || null,
      };
      if (editingConnectionId) await advertisingConnections.update(editingConnectionId, payload);
      else await advertisingConnections.create(payload);
      setConnectionFormOpen(false);
      setEditingConnectionId(null);
      setConnectionForm({ ...EMPTY_CONNECTION_FORM });
      await loadAdvertisingConnections();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить рекламный кабинет');
    } finally {
      setConnectionSaving(false);
    }
  }

  async function assignCampaignAnalyticsStore(campaign: MarketingCampaign, counterId: string) {
    if (campaignCounterSavingId) return;
    setCampaignCounterSavingId(campaign.id);
    setError(null);
    try {
      await apiClient.patch(`/api/marketing/campaigns/${campaign.id}/analytics-store`, { metrika_counter_id: counterId || null });
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось привязать кампанию к магазину');
    } finally {
      setCampaignCounterSavingId('');
    }
  }

  async function linkDirectCampaign(campaign: MarketingCampaign, projectTaskId: string) {
    if (campaignLinkSavingId) return;
    setCampaignLinkSavingId(campaign.id);
    setError(null);
    try {
      await apiClient.patch(`/api/marketing/campaigns/${campaign.id}/platform-link`, { traffic_project_task_id: projectTaskId || null });
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось связать кампанию Директа с проектом GLAME');
    } finally {
      setCampaignLinkSavingId('');
    }
  }

  async function deleteAdvertisingConnection(connection: AdvertisingConnection) {
    if (deletingConnectionId || !window.confirm(`Удалить подключение «${connection.name}»? OAuth-доступ и импортированные метрики этого источника будут удалены. Кампании GLAME останутся.`)) return;
    setDeletingConnectionId(connection.id);
    setError(null);
    try {
      await apiClient.delete(`/api/marketing/advertising-connections/${connection.id}`);
      await loadAdvertisingConnections();
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось удалить подключение');
    } finally {
      setDeletingConnectionId('');
    }
  }

  async function syncAdvertisingConnection(connection: AdvertisingConnection) {
    if (syncingConnectionId) return;
    setSyncingConnectionId(connection.id);
    setError(null);
    try {
      await advertisingConnections.sync(connection.id);
      await loadAdvertisingConnections();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Синхронизация пока недоступна');
      await loadAdvertisingConnections();
    } finally {
      setSyncingConnectionId('');
    }
  }

  async function createDirectTestCampaign(connection: AdvertisingConnection) {
    if (directTestCreatingId) return;
    const approved = window.confirm(`Создать безопасный тестовый черновик ЕПК в «${connection.name}»? В нём не будет групп и объявлений: показы, модерация и списания невозможны.`);
    if (!approved) return;
    setDirectTestCreatingId(connection.id);
    setError(null);
    try {
      const created = await advertisingConnections.createTestDirectCampaign(connection.id);
      await loadAdvertisingConnections();
      window.alert(`Создан тестовый черновик ЕПК «${created.test_campaign_name}» (ID ${created.test_campaign_id}). В нём нет групп и объявлений, поэтому показы и списания невозможны.`);
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message || e?.response?.data?.detail || 'Не удалось создать тестовый черновик ЕПК');
    } finally {
      setDirectTestCreatingId('');
    }
  }

  async function beginOwnerAuthorization(connection: AdvertisingConnection) {
    if (authorizationCreatingId) return;
    setAuthorizationCreatingId(connection.id);
    setError(null);
    try {
      const link = await advertisingConnections.createAuthorizationLink(connection.id);
      setAuthorizationInfo({ ...link, connectionId: connection.id });
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось подготовить ссылку авторизации Яндекса');
    } finally {
      setAuthorizationCreatingId('');
    }
  }

  async function createGrowthTask(seed: { title: string; description: string; taskType?: string; channel?: string; campaignCode?: string; budget?: number; kpi?: string; runNow?: boolean }) {
    setCreating(true);
    setError(null);
    try {
      const { task: created, created: wasCreated } = await aiMarketer.ensureBoardTask('traffic', {
        source_agent: 'traffic-board',
        target_agent: 'traffic-growth-agent',
        task_type: seed.taskType || 'growth_campaign',
        priority: 2,
        input_data: {
          title: seed.title,
          description: seed.description,
          expected_result: 'Паспорт кампании: аудитория, гео, бюджет, KPI, креативы, согласование, запуск и измерение',
          channel: seed.channel || 'growth',
          campaign_code: seed.campaignCode,
          daily_budget_rub: seed.budget,
          user_assignment: seed.runNow ? returnStrategyAssignment.trim() : undefined,
          source_board: 'traffic',
        },
        task_context: {
          board: 'traffic',
          created_from: 'traffic_growth_board',
          campaign_code: seed.campaignCode,
          project_topic: seed.campaignCode,
          target_kpi: seed.kpi,
          visits_snapshot: visits,
        },
        target_metrics: seed.kpi ? { primary_kpi: seed.kpi, daily_budget_rub: seed.budget } : undefined,
      });
      setSelectedProjectTaskId(created.id);
      if (seed.runNow && created.status !== 'completed') {
        if (wasCreated || ['pending_approval', 'validated'].includes(created.status)) {
          await agentInteractions.approveTask(created.id, 'Запущено пользователем из блока рекомендаций. Подготовить только стратегию на согласование, без внешних действий.');
        }
        await agentInteractions.processTask(created.id);
      }
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось создать growth-задачу');
    } finally {
      setCreating(false);
    }
  }

  async function deleteProject(taskId: string, title: string) {
    if (deletingProjectId || !window.confirm(`Удалить проект «${title}» из списка? История сообщений и аудит сохранятся.`)) return;
    setDeletingProjectId(taskId);
    setError(null);
    try {
      await agentInteractions.deleteTrafficProject(taskId);
      const remaining = projectTopics.filter((project) => project.task_id !== taskId);
      setProjectTopics(remaining);
      if (selectedProjectTaskId === taskId) setSelectedProjectTaskId(remaining[0]?.task_id || '');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось удалить рекламный проект');
    } finally {
      setDeletingProjectId('');
    }
  }

  async function saveBrief() {
    if (!selectedProjectTaskId || !briefState || briefSaving) return;
    setBriefSaving(true);
    setError(null);
    try {
      setBriefState(await agentInteractions.saveTrafficCampaignBrief(selectedProjectTaskId, briefState.brief));
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить бриф кампании');
    } finally {
      setBriefSaving(false);
    }
  }

  async function loadFeedPreview() {
    setFeedLoading(true);
    try {
      setFeedPreview(await agentInteractions.previewYandexBusinessFeed(feedFilterParams()));
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось проверить товарный фид');
    } finally {
      setFeedLoading(false);
    }
  }

  async function loadFeedFilterOptions() {
    try {
      setFeedFilterOptions(await agentInteractions.getYandexBusinessFeedFilters());
    } catch {
      setFeedFilterOptions(null);
    }
  }

  async function loadPublicFeedSettings() {
    try {
      setPublicFeedSettings(await agentInteractions.getYandexBusinessFeedPublicSettings());
    } catch {
      setPublicFeedSettings(null);
    }
  }

  async function resetFeedFilters() {
    setFeedFilters({ minPrice: '', maxPrice: '', availability: 'all', brand: '', category: '', storeId: '' });
    setFeedLoading(true);
    try {
      setFeedPreview(await agentInteractions.previewYandexBusinessFeed());
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сбросить фильтры фида');
    } finally {
      setFeedLoading(false);
    }
  }

  function feedFilterParams() {
    const minPrice = Number(feedFilters.minPrice);
    const maxPrice = Number(feedFilters.maxPrice);
    return {
      ...(feedFilters.minPrice && Number.isFinite(minPrice) ? { min_price: minPrice } : {}),
      ...(feedFilters.maxPrice && Number.isFinite(maxPrice) ? { max_price: maxPrice } : {}),
      ...(feedFilters.availability !== 'all' ? { availability: feedFilters.availability as 'in_stock' | 'out_of_stock' | 'unknown' } : {}),
      ...(feedFilters.brand ? { brands: feedFilters.brand } : {}),
      ...(feedFilters.category ? { categories: feedFilters.category } : {}),
      ...(feedFilters.storeId ? { store_id: feedFilters.storeId } : {}),
    };
  }

  function feedDownloadUrl() {
    const search = new URLSearchParams(Object.entries(feedFilterParams()).map(([key, value]) => [key, String(value)])).toString();
    return `/api/agent-interactions/traffic/yandex-business-feed.xml${search ? `?${search}` : ''}`;
  }

  async function publishAutomaticFeed() {
    if (publicFeedSaving) return;
    setPublicFeedSaving(true);
    setError(null);
    try {
      setPublicFeedSettings(await agentInteractions.saveYandexBusinessFeedPublicSettings(feedFilterParams()));
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить настройки автоматического фида');
    } finally {
      setPublicFeedSaving(false);
    }
  }

  async function submitBriefForApproval() {
    if (!selectedProjectTaskId || !briefState || briefSaving) return;
    setBriefSaving(true);
    setError(null);
    try {
      setBriefState(await agentInteractions.submitTrafficCampaignForApproval(selectedProjectTaskId));
      await loadData();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'object' ? detail.message || 'Бриф ещё не готов к согласованию' : detail || 'Не удалось передать кампанию на согласование');
    } finally {
      setBriefSaving(false);
    }
  }

  async function armProductionLaunch() {
    if (!selectedProjectTaskId || !briefState || productionArming) return;
    if (!briefState.ready_for_approval) {
      setError('Сначала заполните паспорт запуска.');
      return;
    }
    if (creativeTask?.status !== 'completed' || creativeTask.task_context?.creative_review_status !== 'approved') {
      setError('Для боевого запуска сначала согласуйте весь пакет креативов.');
      return;
    }
    const connection = adConnections.find((item) => item.id === productionForm.connectionId && item.platform === 'yandex_direct' && item.status === 'connected');
    const counter = metrikaSettings?.counters?.find((item) => item.id === productionForm.metrikaCounterId);
    if (!connection || !counter) {
      setError('Выберите авторизованный кабинет Яндекс Директа и счётчик Метрики для этой кампании.');
      return;
    }
    if (!window.confirm(`Подготовить боевой запуск для «${briefState.brief.campaign_code || 'кампании'}»? Будут зафиксированы кабинет, счётчик и лимит ${formatCurrency.format(briefState.brief.daily_budget_rub)} в день. Кампания в Яндексе и показы на этом шаге не создаются.`)) return;
    setProductionArming(true);
    setError(null);
    try {
      const project = await agentInteractions.getTask(selectedProjectTaskId);
      const release = {
        status: 'armed',
        armed_at: new Date().toISOString(),
        direct_connection_id: connection.id,
        direct_connection_name: connection.name,
        metrika_counter_id: counter.id,
        metrika_counter_name: counter.name,
        metrika_counter_number: counter.counter_id,
        daily_budget_rub: briefState.brief.daily_budget_rub,
        test_days: briefState.brief.test_days,
        radius_km: briefState.brief.radius_km,
        creative_task_id: creativeTask.id,
        creative_review_status: 'approved',
        external_action: 'not_started',
      };
      const saved = await agentInteractions.updateTask(selectedProjectTaskId, { task_context: { ...(project.task_context || {}), direct_production_release: release } });
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      window.alert('Боевой запуск подготовлен. Следующий этап — создание черновика реальной ЕПК и её предпросмотр перед публикацией.');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось подготовить боевой запуск');
    } finally {
      setProductionArming(false);
    }
  }

  async function createProductionDraft() {
    if (!selectedProjectTaskId || productionDraftCreating) return;
    const release = selectedProjectTask?.task_context?.direct_production_release;
    if (release?.status !== 'armed') {
      setError('Сначала подготовьте боевой запуск и зафиксируйте кабинет и счётчик.');
      return;
    }
    const confirmation = `Создать в Яндекс Директе черновик реальной ЕПК для «${briefState?.brief.campaign_code || 'кампании'}»? Счётчик ${release.metrika_counter_name || 'Метрики'} будет привязан к кампании. Группы и объявления не будут созданы — показы и списания останутся невозможны.`;
    if (!window.confirm(confirmation)) return;
    setProductionDraftCreating(true);
    setError(null);
    try {
      const response = await apiClient.post<{
        status: string;
        direct_campaign_id: string;
        direct_campaign_name: string;
        weekly_spend_limit_rub: number;
      }>(`/api/marketing/traffic-projects/${selectedProjectTaskId}/direct-production-draft`, { confirmation: 'СОЗДАТЬ ЧЕРНОВИК' });
      const saved = await agentInteractions.getTask(selectedProjectTaskId);
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      await loadData();
      window.alert(`Черновик ЕПК № ${response.data.direct_campaign_id} создан. В нём пока нет групп и объявлений, поэтому показы и списания невозможны.`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'object' ? detail.message || 'Не удалось создать черновик ЕПК' : detail || 'Не удалось создать черновик ЕПК');
    } finally {
      setProductionDraftCreating(false);
    }
  }

  async function savePublicationChecklist() {
    if (!selectedProjectTaskId || publicationChecklistSaving || productionRelease?.status !== 'direct_draft_created') return;
    if (!publicationChecklist.media_rights_confirmed || !publicationChecklist.promo_code_confirmed || !publicationChecklist.landing_confirmed) {
      setError('Перед следующим этапом подтвердите права на медиа, промокод и посадочную страницу.');
      return;
    }
    if (!window.confirm('Зафиксировать готовность к следующему этапу — созданию групп и объявлений? Это не создаст объявления, не отправит их на модерацию и не включит показы.')) return;
    setPublicationChecklistSaving(true);
    setError(null);
    try {
      const project = await agentInteractions.getTask(selectedProjectTaskId);
      const release = project.task_context?.direct_production_release || {};
      const saved = await agentInteractions.updateTask(selectedProjectTaskId, {
        task_context: {
          ...(project.task_context || {}),
          direct_production_release: {
            ...release,
            publication_checklist: { ...publicationChecklist, confirmed_at: new Date().toISOString() },
            next_step_ready: 'create_ad_groups_and_ads_for_approval',
          },
        },
      });
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      window.alert('Готовность зафиксирована. Следующий этап будет отдельным: создание групп и объявлений для предварительного просмотра.');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить контрольный лист публикации');
    } finally {
      setPublicationChecklistSaving(false);
    }
  }

  async function saveDirectPublicationPackage() {
    if (!selectedProjectTaskId || directPackageSaving || !publicationChecksComplete) return;
    const regionId = directPackage.region_id.trim();
    const landingUrl = directPackage.landing_url.trim();
    const promoCode = directPackage.promo_code.trim();
    if (!directPackage.ad_group_name.trim() || !/^\d+$/.test(regionId) || !/^https?:\/\//i.test(landingUrl) || !promoCode) {
      setError('Для пакета нужны название группы, числовой ID региона Директа, ссылка с http(s) и промокод кампании.');
      return;
    }
    setDirectPackageSaving(true);
    setError(null);
    try {
      const project = await agentInteractions.getTask(selectedProjectTaskId);
      const release = project.task_context?.direct_production_release || {};
      const saved = await agentInteractions.updateTask(selectedProjectTaskId, {
        task_context: {
          ...(project.task_context || {}),
          direct_production_release: {
            ...release,
            direct_publication_package: {
              ...directPackage,
              region_id: regionId,
              landing_url: landingUrl,
              promo_code: promoCode,
              prepared_at: new Date().toISOString(),
              safety: 'not_sent_to_yandex',
            },
          },
        },
      });
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      window.alert('Пакет для группы сохранён в GLAME. В Яндекс Директ ничего не передано.');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить пакет публикации');
    } finally {
      setDirectPackageSaving(false);
    }
  }

  async function createProductionGroup() {
    if (!selectedProjectTaskId || directGroupCreating || productionRelease?.status !== 'direct_draft_created' || !productionRelease?.direct_publication_package) return;
    if (!window.confirm(`Создать пустую локальную группу «${productionRelease.direct_publication_package.ad_group_name}» в черновике ЕПК? Группа не будет содержать объявлений, ключевых фраз или условий показа — модерация, показы и списания невозможны.`)) return;
    setDirectGroupCreating(true);
    setError(null);
    try {
      const response = await apiClient.post<{ direct_group_id: string; direct_group_name: string }>(`/api/marketing/traffic-projects/${selectedProjectTaskId}/direct-production-group`, { confirmation: 'СОЗДАТЬ ГРУППУ' });
      const saved = await agentInteractions.getTask(selectedProjectTaskId);
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      await loadData();
      window.alert(`Пустая группа № ${response.data.direct_group_id} создана. Следующий этап — создать объявления для предпросмотра и отдельного согласования.`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'object' ? detail.message || 'Не удалось создать пустую группу' : detail || 'Не удалось создать пустую группу');
    } finally {
      setDirectGroupCreating(false);
    }
  }

  function parsedAdCopy(value: string) {
    return value.split('\n').map((item) => item.trim()).filter(Boolean);
  }

  async function saveDirectAdsPackage() {
    if (!selectedProjectTaskId || directAdsSaving || productionRelease?.status !== 'direct_group_created') return;
    const titles = parsedAdCopy(directAdsForm.titles);
    const texts = parsedAdCopy(directAdsForm.texts);
    if (!titles.length || titles.length > 7 || !texts.length || texts.length > 3) {
      setError('Для комбинированного объявления нужны 1–7 заголовков и 1–3 текста: по одному варианту в строке.');
      return;
    }
    setDirectAdsSaving(true);
    setError(null);
    try {
      const project = await agentInteractions.getTask(selectedProjectTaskId);
      const release = project.task_context?.direct_production_release || {};
      const saved = await agentInteractions.updateTask(selectedProjectTaskId, { task_context: { ...(project.task_context || {}), direct_production_release: { ...release, direct_ads_package: { titles, texts, prepared_at: new Date().toISOString(), safety: 'not_sent_to_yandex' } } } });
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      window.alert('Пакет комбинаторного объявления сохранён в GLAME. В Директ ничего не передано.');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить пакет объявления');
    } finally {
      setDirectAdsSaving(false);
    }
  }

  async function createProductionAds() {
    if (!selectedProjectTaskId || directAdsCreating || productionRelease?.status !== 'direct_group_created' || !productionRelease?.direct_ads_package) return;
    const { titles, texts } = productionRelease.direct_ads_package;
    if (!window.confirm(`Создать одно комбинаторное объявление-черновик из ${titles.length} заголовков и ${texts.length} текстов? Оно не будет отправлено на модерацию; в группе нет условий показа, поэтому списания невозможны.`)) return;
    setDirectAdsCreating(true);
    setError(null);
    try {
      const response = await apiClient.post<{ direct_ad_id: string }>(`/api/marketing/traffic-projects/${selectedProjectTaskId}/direct-production-ads`, { confirmation: 'СОЗДАТЬ ОБЪЯВЛЕНИЕ', titles, texts });
      const saved = await agentInteractions.getTask(selectedProjectTaskId);
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      await loadData();
      window.alert(`Комбинаторное объявление № ${response.data.direct_ad_id} создано как черновик. Модерация и показы не запускались.`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'object' ? detail.message || 'Не удалось создать черновик объявления' : detail || 'Не удалось создать черновик объявления');
    } finally {
      setDirectAdsCreating(false);
    }
  }

  async function saveDirectKeywordsPackage() {
    if (!selectedProjectTaskId || directKeywordsSaving || productionRelease?.status !== 'direct_ads_draft_created') return;
    const keywords = parsedAdCopy(directKeywords);
    if (!keywords.length || keywords.length > 100) {
      setError('Укажите от 1 до 100 ключевых фраз: по одной в строке.');
      return;
    }
    setDirectKeywordsSaving(true);
    setError(null);
    try {
      const project = await agentInteractions.getTask(selectedProjectTaskId);
      const release = project.task_context?.direct_production_release || {};
      const saved = await agentInteractions.updateTask(selectedProjectTaskId, { task_context: { ...(project.task_context || {}), direct_production_release: { ...release, direct_keywords_package: { keywords, prepared_at: new Date().toISOString(), safety: 'not_sent_to_yandex' } } } });
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      window.alert('Пакет ключевых фраз сохранён в GLAME. В Директ ничего не передано.');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить пакет ключевых фраз');
    } finally {
      setDirectKeywordsSaving(false);
    }
  }

  async function createProductionKeywords() {
    if (!selectedProjectTaskId || directKeywordsCreating || productionRelease?.status !== 'direct_ads_draft_created' || !productionRelease?.direct_keywords_package) return;
    const keywords = productionRelease.direct_keywords_package.keywords;
    if (!window.confirm(`Добавить ${keywords.length} ключевых фраз в группу? Объявление останется черновиком, модерация и показы не запускаются.`)) return;
    setDirectKeywordsCreating(true);
    setError(null);
    try {
      const response = await apiClient.post<{ keyword_ids: string[] }>(`/api/marketing/traffic-projects/${selectedProjectTaskId}/direct-production-keywords`, { confirmation: 'ДОБАВИТЬ КЛЮЧИ', keywords });
      const saved = await agentInteractions.getTask(selectedProjectTaskId);
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      await loadData();
      window.alert(`Добавлено ключевых фраз: ${response.data.keyword_ids.length}. Объявление не отправлено на модерацию и не показывается.`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'object' ? detail.message || 'Не удалось добавить ключевые фразы' : detail || 'Не удалось добавить ключевые фразы');
    } finally {
      setDirectKeywordsCreating(false);
    }
  }

  async function uploadDirectImages() {
    if (!selectedProjectTaskId || directImagesUploading || productionRelease?.status !== 'direct_targeting_draft_created') return;
    const assets = directCompatibleMedia.filter((asset) => directImageIds.includes(asset.id));
    if (!assets.length || assets.length > 3) {
      setError('Выберите от 1 до 3 JPG, PNG или GIF из медиатеки GLAME.');
      return;
    }
    if (!window.confirm(`Загрузить ${assets.length} выбранных файлов из медиатеки GLAME в библиотеку изображений Директа? Файлы пока не будут привязаны к объявлению и не попадут на модерацию.`)) return;
    setDirectImagesUploading(true);
    setError(null);
    try {
      const response = await apiClient.post<{ image_hashes: string[] }>(`/api/marketing/traffic-projects/${selectedProjectTaskId}/direct-production-images`, { confirmation: 'ЗАГРУЗИТЬ ИЗОБРАЖЕНИЯ', assets: assets.map(({ id, url, title }) => ({ id, url, title })) });
      const saved = await agentInteractions.getTask(selectedProjectTaskId);
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      window.alert(`Изображений загружено в библиотеку Директа: ${response.data.image_hashes.length}. Они ещё не привязаны к объявлению.`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'object' ? detail.message || 'Не удалось загрузить изображения' : detail || 'Не удалось загрузить изображения');
    } finally {
      setDirectImagesUploading(false);
    }
  }

  async function attachDirectImages() {
    if (!selectedProjectTaskId || directImagesAttaching || productionRelease?.status !== 'direct_images_uploaded') return;
    if (!window.confirm('Привязать импортированные изображения к объявлению-черновику? Объявление не будет отправлено на модерацию и не начнёт показываться.')) return;
    setDirectImagesAttaching(true);
    setError(null);
    try {
      const response = await apiClient.post<{ image_hashes: string[] }>(`/api/marketing/traffic-projects/${selectedProjectTaskId}/direct-production-attach-images`, { confirmation: 'ПРИВЯЗАТЬ ИЗОБРАЖЕНИЯ' });
      const saved = await agentInteractions.getTask(selectedProjectTaskId);
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      window.alert(`Изображения (${response.data.image_hashes.length}) привязаны к объявлению-черновику. Модерация не запускалась.`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'object' ? detail.message || 'Не удалось привязать изображения' : detail || 'Не удалось привязать изображения');
    } finally {
      setDirectImagesAttaching(false);
    }
  }

  async function requestDirectModeration() {
    if (!selectedProjectTaskId || directModerationSubmitting || productionRelease?.status !== 'direct_images_attached') return;
    if (!directModerationAcknowledged) {
      setError('Подтвердите, что понимаете: после одобрения Директом возможны показы и расходы в рамках заданного лимита.');
      return;
    }
    if (!window.confirm('Отправить объявление на модерацию Яндекс Директа? Это фактическое внешнее действие. После одобрения и при наличии средств показы могут начаться в пределах дневного лимита кампании.')) return;
    setDirectModerationSubmitting(true);
    setError(null);
    try {
      await apiClient.post(`/api/marketing/traffic-projects/${selectedProjectTaskId}/direct-production-moderation`, { confirmation: 'ОТПРАВИТЬ НА МОДЕРАЦИЮ', spending_acknowledged: true });
      const saved = await agentInteractions.getTask(selectedProjectTaskId);
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
      window.alert('Объявление передано в Яндекс Директ на модерацию. Запрос и подтверждение сохранены в журнале проекта.');
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'object' ? detail.message || 'Не удалось отправить объявление на модерацию' : detail || 'Не удалось отправить объявление на модерацию');
    } finally {
      setDirectModerationSubmitting(false);
    }
  }

  async function checkDirectModerationStatus() {
    if (!selectedProjectTaskId || directModerationChecking || productionRelease?.status !== 'direct_moderation_requested') return;
    setDirectModerationChecking(true);
    setError(null);
    try {
      await apiClient.get(`/api/marketing/traffic-projects/${selectedProjectTaskId}/direct-production-moderation-status`);
      const saved = await agentInteractions.getTask(selectedProjectTaskId);
      setTasks((current) => current.map((item) => item.id === saved.id ? saved : item));
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'object' ? detail.message || 'Не удалось проверить статус модерации' : detail || 'Не удалось проверить статус модерации');
    } finally {
      setDirectModerationChecking(false);
    }
  }

  function updateBrief(patch: Partial<TrafficCampaignBrief>) {
    setBriefState((current) => current ? { ...current, brief: { ...current.brief, ...patch } } : current);
  }

  async function createCreativeTask() {
    if (!selectedProjectTaskId || !briefState || creativeCreating) return;
    setCreativeCreating(true);
    setError(null);
    try {
      const project = await agentInteractions.getTask(selectedProjectTaskId);
      const campaignCode = briefState.brief.campaign_code || project.input_data?.campaign_code || 'GLAME_YALTA_CAMPAIGN';
      const { task: created } = await aiMarketer.ensureBoardTask('content', {
        source_agent: 'traffic-growth-agent',
        target_agent: 'brand-media-agent',
        task_type: 'advertising_creatives',
        priority: 2,
        idempotency_key: `traffic-creative:${selectedProjectTaskId}`,
        input_data: {
          title: `Креативы для ${campaignCode}`,
          description: `Подготовить рекламные креативы и тексты объявлений для ${campaignCode}. ${briefState.brief.goal}`,
          expected_result: 'Пакет на согласование: 3 варианта текстов, заголовки, CTA, ТЗ на баннеры/видео, перечень исходных медиа и форматы для Яндекса.',
          content_type: 'advertising_creatives',
          platform: 'Яндекс Директ / Яндекс Бизнес',
          city: 'Ялта',
          campaign_code: campaignCode,
          parent_traffic_task_id: selectedProjectTaskId,
          campaign_brief: briefState.brief,
          source_board: 'traffic',
        },
        task_context: {
          board: 'content',
          created_from: 'traffic_growth_board',
          parent_traffic_task_id: selectedProjectTaskId,
          campaign_code: campaignCode,
          handoff_type: 'traffic_to_brand_media_creatives',
        },
        target_metrics: { primary_kpi: briefState.brief.kpi?.primary || 'Маршруты и визиты', campaign_code: campaignCode },
        requirements: {
          must_use_glame_media: true,
          must_not_publish_externally: true,
          variants_required: 3,
          formats: ['поиск', 'РСЯ/баннер', 'короткое видео'],
        },
      });
      await agentInteractions.updateTask(selectedProjectTaskId, {
        task_context: { ...project.task_context, creative_task_id: created.id },
      });
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось передать ТЗ на креативы AI Brand Media');
    } finally {
      setCreativeCreating(false);
    }
  }

  async function approveCreativePackage() {
    if (!creativeTask || creativeReviewSaving) return;
    setCreativeReviewSaving(true);
    setError(null);
    try {
      await agentInteractions.updateTask(creativeTask.id, {
        task_context: { ...creativeTask.task_context, creative_review_status: 'approved', creative_review_comment: creativeReviewNote.trim() || null, creative_reviewed_at: new Date().toISOString() },
      });
      setCreativeReviewNote('');
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось зафиксировать согласование креативов');
    } finally {
      setCreativeReviewSaving(false);
    }
  }

  async function approveCreativeVariant(index: number) {
    if (!creativeTask || creativeReviewSaving) return;
    setCreativeReviewSaving(true);
    try {
      const reviews = { ...(creativeTask.task_context?.creative_variant_reviews || {}), [String(index)]: { status: 'approved', comment: creativeReviewNote.trim() || null, reviewed_at: new Date().toISOString() } };
      await agentInteractions.updateTask(creativeTask.id, { task_context: { ...creativeTask.task_context, creative_variant_reviews: reviews } });
      setCreativeReviewNote('');
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось согласовать вариант');
    } finally {
      setCreativeReviewSaving(false);
    }
  }

  async function cycleCreativeVariantMedia(index: number) {
    if (!creativeTask || !creativeMedia?.assets?.length || creativeReviewSaving) return;
    setCreativeReviewSaving(true);
    try {
      const mapping = { ...(creativeTask.task_context?.creative_variant_media || {}) } as Record<string, string>;
      const currentId = mapping[String(index)] || creativeMedia.assets[(index - 1) % creativeMedia.assets.length]?.id;
      const currentIndex = creativeMedia.assets.findIndex((asset) => asset.id === currentId);
      const next = creativeMedia.assets[(Math.max(currentIndex, -1) + 1) % creativeMedia.assets.length];
      mapping[String(index)] = next.id;
      await agentInteractions.updateTask(creativeTask.id, { task_context: { ...creativeTask.task_context, creative_variant_media: mapping } });
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сменить фото в предпросмотре');
    } finally {
      setCreativeReviewSaving(false);
    }
  }

  async function requestCreativeRevision() {
    if (!creativeTask || !creativeReviewNote.trim() || creativeReviewSaving) {
      if (!creativeReviewNote.trim()) setError('Опишите, что нужно изменить в креативах.');
      return;
    }
    setCreativeReviewSaving(true);
    setError(null);
    try {
      await agentInteractions.createTask({
        source_agent: 'traffic-growth-agent',
        target_agent: 'brand-media-agent',
        task_type: 'advertising_creatives',
        input_data: { ...creativeTask.input_data, title: `${creativeTask.input_data?.title || 'Креативы'} — доработка`, description: `${creativeTask.input_data?.description || ''}\n\nДоработать варианты: ${(selectedCreativeVariants.length ? selectedCreativeVariants : [1, 2, 3]).join(', ')}.\nЗамечания: ${creativeReviewNote.trim()}`, revision_notes: creativeReviewNote.trim(), revision_variants: selectedCreativeVariants.length ? selectedCreativeVariants : [1, 2, 3], parent_traffic_task_id: selectedProjectTaskId },
        task_context: { ...creativeTask.task_context, parent_traffic_task_id: selectedProjectTaskId, parent_creative_task_id: creativeTask.id, creative_revision_requested_at: new Date().toISOString(), creative_revision_variants: selectedCreativeVariants.length ? selectedCreativeVariants : [1, 2, 3] },
        target_metrics: creativeTask.target_metrics || {}, requirements: creativeTask.requirements || {}, constraints: creativeTask.constraints || {}, priority: creativeTask.priority,
      });
      await agentInteractions.updateTask(creativeTask.id, { task_context: { ...creativeTask.task_context, creative_review_status: 'revision_requested', creative_review_comment: creativeReviewNote.trim() } });
      setCreativeReviewNote('');
      setSelectedCreativeVariants([]);
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось передать креативы на доработку');
    } finally {
      setCreativeReviewSaving(false);
    }
  }

  const missingYaltaTemplates = useMemo(
    () => YALTA_CAMPAIGN_TEMPLATES.filter((template) => !projectTopics.some((project) => project.campaign_code === template.code)),
    [projectTopics]
  );

  const totalVisitors = useMemo(() => {
    const rows = visits?.daily_data || visits?.data || [];
    return Array.isArray(rows) ? rows.reduce((sum, row) => sum + Number(row.visitors ?? row.visitor_count ?? row.visits ?? 0), 0) : 0;
  }, [visits]);


  return (
    <div className="min-h-screen bg-gray-50">
      <BoardHeader
        title="Traffic & Growth Board"
        description="Привлечение трафика, рекламные кампании, ретаргетинг и рост аудитории."
        boardId="traffic"
        actions={<Button variant="default" size="sm" onClick={() => createGrowthTask({ ...YALTA_CAMPAIGN_TEMPLATES[0], campaignCode: YALTA_CAMPAIGN_TEMPLATES[0].code })} disabled={creating}>{creating ? 'Создание...' : 'Создать кампанию'}</Button>}
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {error && <Card className="p-3 text-sm text-red-700 border-red-200 bg-red-50">{error}</Card>}
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <button type="button" onClick={() => setUtilityPanel('accounts')} className="rounded-xl border border-blue-200 bg-white p-5 text-left shadow-sm transition hover:border-blue-400 hover:shadow">
            <span className="text-base font-semibold text-gray-900">Рекламные кабинеты</span>
            <span className="mt-2 block text-sm text-gray-600">Подключения Директа, Яндекс Бизнеса и Карт</span>
            <span className="mt-3 block text-xs font-medium text-blue-700">{adConnections.length} в реестре →</span>
          </button>
          <button type="button" onClick={() => setUtilityPanel('feed')} className="rounded-xl border border-amber-200 bg-white p-5 text-left shadow-sm transition hover:border-amber-400 hover:shadow">
            <span className="text-base font-semibold text-gray-900">Товарный фид</span>
            <span className="mt-2 block text-sm text-gray-600">Фильтры каталога и автоматическое обновление</span>
            <span className="mt-3 block text-xs font-medium text-amber-700">{feedPreview ? `${formatNumber.format(feedPreview.included)} товаров в фиде` : 'Настроить фид'} →</span>
          </button>
          <button type="button" onClick={() => setUtilityPanel('analytics')} className="rounded-xl border border-indigo-200 bg-white p-5 text-left shadow-sm transition hover:border-indigo-400 hover:shadow">
            <span className="text-base font-semibold text-gray-900">Рекламная аналитика</span>
            <span className="mt-2 block text-sm text-gray-600">Воронка, Метрика и факты по карточкам</span>
            <span className="mt-3 block text-xs font-medium text-indigo-700">Открыть аналитику →</span>
          </button>
          <button type="button" onClick={() => setUtilityPanel('direct-campaigns')} className="rounded-xl border border-emerald-200 bg-white p-5 text-left shadow-sm transition hover:border-emerald-400 hover:shadow">
            <span className="text-base font-semibold text-gray-900">Кампании Директа</span>
            <span className="mt-2 block text-sm text-gray-600">Импорт из кабинета и связь с проектами GLAME</span>
            <span className="mt-3 block text-xs font-medium text-emerald-700">{directCampaigns.length} импортировано →</span>
          </button>
        </div>
        <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
          <Card className="p-3">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">Рекламные проекты</h2>
                <p className="text-xs text-gray-500">Кампания — отдельная тема и история работы агента.</p>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="default"
                  size="sm"
                  onClick={() => createGrowthTask({ ...YALTA_CAMPAIGN_TEMPLATES[0], campaignCode: YALTA_CAMPAIGN_TEMPLATES[0].code })}
                  disabled={creating}
                  aria-label="Добавить рекламный проект"
                  title="Добавить рекламный проект"
                  className="h-8 w-8 p-0 text-lg"
                >
                  +
                </Button>
                <Button variant="outline" size="sm" onClick={() => loadData()} disabled={loading} aria-label="Обновить рекламные проекты">↻</Button>
              </div>
            </div>

            <div className="space-y-2">
              {projectTopics.map((project) => (
                <div
                  key={project.task_id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedProjectTaskId(project.task_id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      setSelectedProjectTaskId(project.task_id);
                    }
                  }}
                  className={`w-full rounded-lg border p-3 text-left transition ${selectedProjectTaskId === project.task_id ? 'border-gold-400 bg-amber-50' : 'border-gray-200 bg-white hover:bg-gray-50'}`}
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <Badge variant="outline">{project.channel || 'growth'}</Badge>
                    <span className="text-[11px] text-gray-400">{project.history_count} сообщ.</span>
                  </div>
                  <div className="text-sm font-medium text-gray-900">{project.title}</div>
                  <div className="mt-1 text-xs text-gray-500">Статус: {project.status}</div>
                  {project.discussion_result ? (
                    <div className="mt-2 line-clamp-3 text-xs text-gray-600">Результат: {project.discussion_result}</div>
                  ) : (
                    <div className="mt-2 text-xs text-gray-400">Результат обсуждения пока не зафиксирован.</div>
                  )}
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={(event) => {
                      event.stopPropagation();
                      deleteProject(project.task_id, project.title);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        event.stopPropagation();
                        deleteProject(project.task_id, project.title);
                      }
                    }}
                    aria-disabled={deletingProjectId === project.task_id}
                    className={`mt-3 inline-block text-xs text-red-600 hover:text-red-800 ${deletingProjectId === project.task_id ? 'pointer-events-none opacity-50' : ''}`}
                  >
                    {deletingProjectId === project.task_id ? 'Удаление...' : 'Удалить проект'}
                  </span>
                </div>
              ))}
              {missingYaltaTemplates.map((template) => (
                <button
                  key={template.code}
                  type="button"
                  onClick={() => createGrowthTask({ ...template, campaignCode: template.code })}
                  disabled={creating}
                  className="w-full rounded-lg border border-dashed border-gray-300 bg-gray-50 p-3 text-left hover:bg-white disabled:opacity-60"
                >
                  <div className="text-sm font-medium text-gray-700">{template.title}</div>
                  <div className="mt-1 text-xs text-gray-500">Создать проект кампании и вести историю работы внутри него.</div>
                </button>
              ))}
              {!loading && projectTopics.length === 0 && missingYaltaTemplates.length === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-3 text-xs text-gray-500">Создайте первую кампанию — в ней появится отдельный чат и история решений.</div>
              ) : null}
            </div>
          </Card>

          <div className="space-y-4">
            {briefState ? (
              <Card className="p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="font-semibold text-gray-900">Паспорт запуска: {briefState.brief.campaign_code || 'рекламная кампания'}</h2>
                    <p className="mt-1 text-xs text-gray-500">Черновик GLAME. Сохранение и согласование не публикуют рекламу в Яндексе.</p>
                  </div>
                  <Badge className={briefState.ready_for_approval ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}>
                    {briefState.ready_for_approval ? 'Готов к согласованию' : 'Нужно заполнить'}
                  </Badge>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <label className="text-xs text-gray-600">Карточка Яндекс Карт
                    <input value={briefState.brief.maps_card_url} onChange={(event) => updateBrief({ maps_card_url: event.target.value })} placeholder="https://yandex.ru/maps/..." className="mt-1 h-9 w-full rounded-md border border-gray-300 px-2 text-sm" />
                  </label>
                  <label className="text-xs text-gray-600">Дневной бюджет, ₽
                    <input type="number" min="0" value={briefState.brief.daily_budget_rub} onChange={(event) => updateBrief({ daily_budget_rub: Number(event.target.value) || 0 })} className="mt-1 h-9 w-full rounded-md border border-gray-300 px-2 text-sm" />
                  </label>
                  <label className="text-xs text-gray-600">Радиус, км
                    <input type="number" min="0.1" step="0.1" value={briefState.brief.radius_km} onChange={(event) => updateBrief({ radius_km: Number(event.target.value) || 0.1 })} className="mt-1 h-9 w-full rounded-md border border-gray-300 px-2 text-sm" />
                  </label>
                  <label className="text-xs text-gray-600">Тест, дней
                    <input type="number" min="1" value={briefState.brief.test_days} onChange={(event) => updateBrief({ test_days: Number(event.target.value) || 1 })} className="mt-1 h-9 w-full rounded-md border border-gray-300 px-2 text-sm" />
                  </label>
                </div>
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {Object.entries(CARD_CHECKLIST_LABELS).map(([key, label]) => (
                    <label key={key} className="flex items-center gap-2 text-xs text-gray-700">
                      <input type="checkbox" checked={briefState.brief.card_checklist?.[key] === true} onChange={(event) => updateBrief({ card_checklist: { ...briefState.brief.card_checklist, [key]: event.target.checked } })} />
                      {label}
                    </label>
                  ))}
                </div>
                {!briefState.ready_for_approval ? <p className="mt-3 text-xs text-amber-700">Осталось: {briefState.missing_requirements.join('; ')}.</p> : null}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={saveBrief} disabled={briefSaving}>{briefSaving ? 'Сохранение...' : 'Сохранить черновик'}</Button>
                  <Button size="sm" variant="outline" onClick={createCreativeTask} disabled={creativeCreating || Boolean(creativeTask)}>{creativeButtonLabel}</Button>
                  <Button size="sm" onClick={submitBriefForApproval} disabled={briefSaving || !briefState.ready_for_approval}>Передать на согласование</Button>
                </div>
                <div className="mt-4 rounded-lg border border-indigo-200 bg-indigo-50 p-3">
                  <div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-sm font-semibold text-indigo-950">Боевой запуск Директа</p><p className="mt-1 text-xs text-indigo-800">Фиксирует кабинет, счётчик и лимиты для этой кампании. Создание ЕПК и включение показов выполняются только отдельным подтверждением.</p></div><Badge className={['armed', 'direct_draft_created', 'direct_group_created', 'direct_ads_draft_created', 'direct_targeting_draft_created', 'direct_images_uploaded', 'direct_images_attached', 'direct_moderation_requested'].includes(selectedProjectTask?.task_context?.direct_production_release?.status) ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-700'}>{selectedProjectTask?.task_context?.direct_production_release?.status === 'direct_moderation_requested' ? 'На модерации' : selectedProjectTask?.task_context?.direct_production_release?.status === 'direct_images_attached' ? 'Изображения привязаны' : selectedProjectTask?.task_context?.direct_production_release?.status === 'direct_images_uploaded' ? 'Изображения импортированы' : selectedProjectTask?.task_context?.direct_production_release?.status === 'direct_targeting_draft_created' ? 'Условия добавлены' : selectedProjectTask?.task_context?.direct_production_release?.status === 'direct_ads_draft_created' ? 'Объявление-черновик создано' : selectedProjectTask?.task_context?.direct_production_release?.status === 'direct_group_created' ? 'Группа создана' : selectedProjectTask?.task_context?.direct_production_release?.status === 'direct_draft_created' ? 'Черновик создан' : selectedProjectTask?.task_context?.direct_production_release?.status === 'armed' ? 'Подготовлен' : 'Не подготовлен'}</Badge></div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-xs text-indigo-900">Кабинет Яндекс Директа<select value={productionForm.connectionId} onChange={(event) => setProductionForm((current) => ({ ...current, connectionId: event.target.value }))} className="mt-1 h-9 w-full rounded-md border border-indigo-200 bg-white px-2 text-sm text-gray-900"><option value="">Выберите кабинет</option>{adConnections.filter((item) => item.platform === 'yandex_direct' && item.status === 'connected' && item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.account_login || 'аккаунт'}</option>)}</select></label><label className="text-xs text-indigo-900">Счётчик Метрики<select value={productionForm.metrikaCounterId} onChange={(event) => setProductionForm((current) => ({ ...current, metrikaCounterId: event.target.value }))} className="mt-1 h-9 w-full rounded-md border border-indigo-200 bg-white px-2 text-sm text-gray-900"><option value="">Выберите счётчик</option>{metrikaSettings?.counters?.map((item) => <option key={item.id} value={item.id}>{item.name} · № {item.counter_id}</option>)}</select></label></div>
                  <div className="mt-3 flex flex-wrap items-center gap-2"><Button size="sm" onClick={armProductionLaunch} disabled={productionArming || ['direct_draft_created', 'direct_group_created', 'direct_ads_draft_created', 'direct_targeting_draft_created', 'direct_images_uploaded', 'direct_images_attached', 'direct_moderation_requested'].includes(selectedProjectTask?.task_context?.direct_production_release?.status) || !briefState.ready_for_approval || creativeTask?.task_context?.creative_review_status !== 'approved'}>{productionArming ? 'Подготовка…' : 'Подготовить боевой запуск'}</Button>{selectedProjectTask?.task_context?.direct_production_release?.status === 'armed' ? <Button size="sm" variant="outline" onClick={createProductionDraft} disabled={productionDraftCreating}>{productionDraftCreating ? 'Создание черновика…' : 'Создать черновик реальной ЕПК'}</Button> : null}<span className="text-[11px] text-indigo-800">Лимит: {formatCurrency.format(briefState.brief.daily_budget_rub)} в день · {briefState.brief.test_days} дней · радиус {briefState.brief.radius_km} км.</span></div>
                  {selectedProjectTask?.task_context?.direct_production_release?.status === 'armed' ? <p className="mt-2 text-xs text-green-800">Подготовлено: {selectedProjectTask.task_context.direct_production_release.direct_connection_name} · {selectedProjectTask.task_context.direct_production_release.metrika_counter_name} · внешних действий пока не было.</p> : null}
                  {selectedProjectTask?.task_context?.direct_production_release?.status === 'direct_draft_created' ? <p className="mt-2 text-xs text-green-800">Черновик ЕПК № {selectedProjectTask.task_context.direct_production_release.direct_campaign_id} создан и связан с проектом. В нём нет групп и объявлений: он не показывается и не расходует бюджет.</p> : null}
                  {selectedProjectTask?.task_context?.direct_production_release?.status === 'direct_group_created' ? <p className="mt-2 text-xs text-green-800">Пустая группа № {selectedProjectTask.task_context.direct_production_release.direct_group_id} создана в черновике ЕПК. В ней нет объявлений, ключевых фраз и условий: она не показывается и не расходует бюджет.</p> : null}
                  {selectedProjectTask?.task_context?.direct_production_release?.status === 'direct_ads_draft_created' ? <p className="mt-2 text-xs text-green-800">Комбинаторное объявление № {selectedProjectTask.task_context.direct_production_release.direct_ad_id} создано как черновик. Модерация не запускалась, а в группе нет условий показа: оно не показывается и не расходует бюджет.</p> : null}
                  {selectedProjectTask?.task_context?.direct_production_release?.status === 'direct_targeting_draft_created' ? <p className="mt-2 text-xs text-green-800">Добавлено ключевых фраз: {selectedProjectTask.task_context.direct_production_release.direct_keyword_ids?.length || 0}. Объявление не отправлялось на модерацию, поэтому показы и списания не начнутся.</p> : null}
                  {productionRelease ? <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3"><div className="flex items-center justify-between gap-2"><p className="text-xs font-semibold text-slate-900">Таймлайн запуска</p><span className="text-[11px] text-slate-500">Внешние действия фиксируются по отдельности</span></div><div className="mt-2 grid gap-2 md:grid-cols-3">{directLaunchTimeline.map((step, index) => <div key={step.key} className={`rounded border px-2 py-1.5 text-xs ${step.done ? 'border-green-200 bg-green-50 text-green-800' : index === directLaunchTimeline.length - 1 ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-slate-200 bg-white text-slate-500'}`}><span className="mr-1 font-semibold">{step.done ? '✓' : index + 1}.</span>{step.label}</div>)}</div>{productionRelease.status === 'direct_targeting_draft_created' ? <p className="mt-2 text-[11px] text-amber-800">Следующий шаг намеренно не автоматизирован: перед отправкой на модерацию нужно отдельно подтвердить итоговые тексты, изображения, права на медиа, юридическую маркировку и готовность расходовать бюджет.</p> : null}</div> : null}
                  {directExecutionHistory.length ? <div className="mt-3 rounded-md border border-slate-200 bg-white/70 p-3"><p className="text-xs font-semibold text-slate-900">История внешних действий</p><div className="mt-2 space-y-2">{directExecutionHistory.map((entry) => <div key={`${entry.label}-${entry.at}`} className="flex flex-wrap items-start justify-between gap-2 rounded border border-slate-100 bg-slate-50 px-2 py-1.5 text-[11px]"><span><b>{entry.label}</b><span className="ml-1 text-slate-600">— {entry.detail}</span></span><time className="shrink-0 text-slate-500">{new Date(entry.at).toLocaleString('ru-RU')}</time></div>)}</div></div> : null}
                  {['direct_draft_created', 'direct_group_created'].includes(selectedProjectTask?.task_context?.direct_production_release?.status) ? <div className="mt-3 rounded-md border border-indigo-200 bg-white/70 p-3"><p className="text-xs font-semibold text-indigo-950">Контрольный лист перед созданием групп и объявлений</p><p className="mt-1 text-[11px] text-indigo-800">Этот этап только фиксирует готовность. Следующая операция всё ещё потребует отдельного подтверждения и сначала создаст материалы для проверки, а не включит рекламу.</p><div className="mt-2 grid gap-2 sm:grid-cols-3">{([{ key: 'media_rights_confirmed', label: 'Есть права на выбранные фото и видео' }, { key: 'promo_code_confirmed', label: 'Промокод и правило первой покупки проверены' }, { key: 'landing_confirmed', label: 'Карточка/посадочная и маршрут проверены' }] as const).map((item) => <label key={item.key} className="flex items-start gap-2 text-xs text-gray-700"><input type="checkbox" checked={publicationChecklist[item.key]} onChange={(event) => setPublicationChecklist((current) => ({ ...current, [item.key]: event.target.checked }))} />{item.label}</label>)}</div><div className="mt-3 flex flex-wrap items-center gap-2"><Button size="sm" variant="outline" onClick={savePublicationChecklist} disabled={publicationChecklistSaving || publicationChecksComplete}>{publicationChecklistSaving ? 'Сохраняем…' : publicationChecksComplete ? 'Готовность подтверждена' : 'Зафиксировать готовность'}</Button>{publicationChecksComplete ? <span className="text-xs text-green-800">Можно переходить к подготовке групп и объявлений для согласования; запуск показов остаётся отдельным действием.</span> : null}</div></div> : null}
                  {['direct_draft_created', 'direct_group_created'].includes(selectedProjectTask?.task_context?.direct_production_release?.status) && publicationChecksComplete ? <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50/60 p-3"><p className="text-xs font-semibold text-emerald-950">Пакет группы для Директа</p><p className="mt-1 text-[11px] text-emerald-800">Сохраняется только в GLAME. ID региона нужен Директу для геотаргетинга: не подставляйте «0», если нужен локальный показ. Радиус кампании останется частью согласованного брифа.</p><div className="mt-2 grid gap-2 md:grid-cols-2"><label className="text-xs text-gray-700">Название группы<input value={directPackage.ad_group_name} onChange={(event) => setDirectPackage((current) => ({ ...current, ad_group_name: event.target.value }))} disabled={productionRelease?.status === 'direct_group_created'} className="mt-1 h-8 w-full rounded border border-emerald-200 bg-white px-2 text-sm disabled:bg-gray-100" /></label><label className="text-xs text-gray-700">ID региона Яндекс Директа<input inputMode="numeric" value={directPackage.region_id} onChange={(event) => setDirectPackage((current) => ({ ...current, region_id: event.target.value }))} disabled={productionRelease?.status === 'direct_group_created'} placeholder="Например, ID региона из справочника Директа" className="mt-1 h-8 w-full rounded border border-emerald-200 bg-white px-2 text-sm disabled:bg-gray-100" /></label><label className="text-xs text-gray-700">Посадочная ссылка<input value={directPackage.landing_url} onChange={(event) => setDirectPackage((current) => ({ ...current, landing_url: event.target.value }))} className="mt-1 h-8 w-full rounded border border-emerald-200 bg-white px-2 text-sm" /></label><label className="text-xs text-gray-700">Промокод кампании<input value={directPackage.promo_code} onChange={(event) => setDirectPackage((current) => ({ ...current, promo_code: event.target.value.toUpperCase() }))} className="mt-1 h-8 w-full rounded border border-emerald-200 bg-white px-2 text-sm" /></label></div><label className="mt-2 block text-xs text-gray-700">UTM-шаблон<input value={directPackage.utm_template} onChange={(event) => setDirectPackage((current) => ({ ...current, utm_template: event.target.value }))} className="mt-1 h-8 w-full rounded border border-emerald-200 bg-white px-2 text-sm" /></label><div className="mt-3 flex flex-wrap items-center gap-2"><Button size="sm" variant="outline" onClick={saveDirectPublicationPackage} disabled={directPackageSaving || productionRelease?.status === 'direct_group_created'}>{directPackageSaving ? 'Сохраняем…' : productionRelease?.direct_publication_package ? 'Обновить пакет группы' : 'Сохранить пакет группы'}</Button>{productionRelease?.status === 'direct_draft_created' && productionRelease?.direct_publication_package ? <Button size="sm" variant="outline" onClick={createProductionGroup} disabled={directGroupCreating}>{directGroupCreating ? 'Создаём группу…' : 'Создать пустую группу в Директе'}</Button> : null}{productionRelease?.status === 'direct_group_created' ? <span className="text-xs text-green-800">Пустая группа № {productionRelease.direct_group_id} создана. В ней нет объявлений, ключей и условий показа.</span> : productionRelease?.direct_publication_package ? <span className="text-xs text-green-800">Пакет сохранён в GLAME; в Директ не отправлен.</span> : null}</div></div> : null}
                  {productionRelease?.status === 'direct_group_created' ? <div className="mt-3 rounded-md border border-violet-200 bg-violet-50/60 p-3"><p className="text-xs font-semibold text-violet-950">Пакет комбинаторного объявления</p><p className="mt-1 text-[11px] text-violet-800">По одному варианту в строке. Новые объявления в ЕПК создаются как комбинаторные: Директ подбирает сочетания согласованных заголовков и текстов. Изображения в этот шаг не отправляются — для них будет отдельный контролируемый импорт.</p><div className="mt-2 grid gap-2 md:grid-cols-2"><label className="text-xs text-gray-700">Заголовки, 1–7 строк<textarea value={directAdsForm.titles} onChange={(event) => setDirectAdsForm((current) => ({ ...current, titles: event.target.value }))} className="mt-1 min-h-24 w-full rounded border border-violet-200 bg-white p-2 text-sm" /></label><label className="text-xs text-gray-700">Тексты, 1–3 строки<textarea value={directAdsForm.texts} onChange={(event) => setDirectAdsForm((current) => ({ ...current, texts: event.target.value }))} className="mt-1 min-h-24 w-full rounded border border-violet-200 bg-white p-2 text-sm" /></label></div><div className="mt-1 grid gap-2 text-[11px] text-violet-800 md:grid-cols-2"><span>Заголовки: {parsedAdCopy(directAdsForm.titles).map((item) => item.length).join(' · ') || '—'} / максимум 56 символов.</span><span>Тексты: {parsedAdCopy(directAdsForm.texts).map((item) => item.length).join(' · ') || '—'} / максимум 81 символ.</span></div><div className="mt-3 flex flex-wrap items-center gap-2"><Button size="sm" variant="outline" onClick={saveDirectAdsPackage} disabled={directAdsSaving}>{directAdsSaving ? 'Сохраняем…' : productionRelease.direct_ads_package ? 'Обновить пакет объявления' : 'Сохранить пакет объявления'}</Button>{productionRelease.direct_ads_package ? <Button size="sm" variant="outline" onClick={createProductionAds} disabled={directAdsCreating}>{directAdsCreating ? 'Создаём черновик…' : 'Создать объявление-черновик в Директе'}</Button> : null}{productionRelease.direct_ads_package ? <span className="text-xs text-green-800">Пакет сохранён в GLAME; модерация не запустится автоматически.</span> : null}</div></div> : null}
                  {productionRelease?.status === 'direct_ads_draft_created' ? <div className="mt-3 rounded-md border border-cyan-200 bg-cyan-50/60 p-3"><p className="text-xs font-semibold text-cyan-950">Пакет ключевых фраз</p><p className="mt-1 text-[11px] text-cyan-800">По одной фразе в строке. Это условия показа для поиска и тематик РСЯ, но добавление фраз не отправляет объявление на модерацию и не запускает рекламу.</p><label className="mt-2 block text-xs text-gray-700">Ключевые фразы<textarea value={directKeywords} onChange={(event) => setDirectKeywords(event.target.value)} className="mt-1 min-h-32 w-full rounded border border-cyan-200 bg-white p-2 text-sm" /></label><div className="mt-1 text-[11px] text-cyan-800">Фраз: {parsedAdCopy(directKeywords).length} / максимум 100. До 7 слов в каждой; минус-слова можно указать через «-слово».</div><div className="mt-3 flex flex-wrap items-center gap-2"><Button size="sm" variant="outline" onClick={saveDirectKeywordsPackage} disabled={directKeywordsSaving}>{directKeywordsSaving ? 'Сохраняем…' : productionRelease.direct_keywords_package ? 'Обновить пакет ключей' : 'Сохранить пакет ключей'}</Button>{productionRelease.direct_keywords_package ? <Button size="sm" variant="outline" onClick={createProductionKeywords} disabled={directKeywordsCreating}>{directKeywordsCreating ? 'Добавляем ключи…' : 'Добавить ключи в черновик Директа'}</Button> : null}{productionRelease.direct_keywords_package ? <span className="text-xs text-green-800">Пакет сохранён в GLAME; модерация не запускается автоматически.</span> : null}</div></div> : null}
                  {productionRelease?.status === 'direct_targeting_draft_created' ? <div className="mt-3 rounded-md border border-rose-200 bg-rose-50/60 p-3"><p className="text-xs font-semibold text-rose-950">Изображения для объявления</p><p className="mt-1 text-[11px] text-rose-800">Можно загрузить до трёх файлов из выбранной медиатеки GLAME. Для API Директа доступны только локальные JPG, PNG и GIF; сторонние ссылки и WebP намеренно не передаются.</p>{directCompatibleMedia.length ? <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">{directCompatibleMedia.slice(0, 18).map((asset) => { const selected = directImageIds.includes(asset.id); return <label key={asset.id} className={`overflow-hidden rounded border text-[11px] ${selected ? 'border-rose-400 bg-white' : 'border-rose-100 bg-white/60'}`}><img src={asset.url} alt={asset.title} className="h-24 w-full object-cover" /><span className="flex gap-1 p-1"><input type="checkbox" checked={selected} onChange={() => setDirectImageIds((current) => selected ? current.filter((id) => id !== asset.id) : current.length >= 3 ? current : [...current, asset.id])} />{asset.title}</span></label>; })}</div> : <p className="mt-2 text-xs text-amber-800">В выбранной медиатеке нет подходящих локальных JPG/PNG/GIF. Добавьте оригинал через медиатеку GLAME; WebP можно подготовить отдельной конвертацией.</p>}<div className="mt-3 flex flex-wrap items-center gap-2"><Button size="sm" variant="outline" onClick={uploadDirectImages} disabled={directImagesUploading || !directCompatibleMedia.length || !directImageIds.length}>{directImagesUploading ? 'Загружаем…' : `Загрузить в библиотеку Директа (${directImageIds.length})`}</Button><span className="text-xs text-rose-800">Файлы не будут автоматически привязаны, отправлены на модерацию или показаны.</span></div></div> : null}
                  {productionRelease?.status === 'direct_images_uploaded' ? <div className="mt-3 rounded-md border border-rose-200 bg-rose-50/60 p-3"><p className="text-xs font-semibold text-rose-950">Изображения загружены в Директ</p><p className="mt-1 text-xs text-rose-800">Импортировано: {productionRelease.direct_image_hashes?.length || 0}. Пока это только библиотека Директа; изображения не связаны с объявлением.</p><Button size="sm" variant="outline" className="mt-3" onClick={attachDirectImages} disabled={directImagesAttaching}>{directImagesAttaching ? 'Привязываем…' : 'Привязать к объявлению-черновику'}</Button></div> : null}
                  {productionRelease?.status === 'direct_images_attached' ? <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3"><p className="text-xs font-semibold text-amber-950">Финальное согласование перед модерацией</p><p className="mt-1 text-xs text-amber-900">Все материалы уже находятся в черновике Директа. Отправка ниже — отдельное фактическое действие: после одобрения и при наличии средств показы могут начаться в пределах дневного лимита.</p><label className="mt-3 flex items-start gap-2 text-xs text-amber-950"><input type="checkbox" checked={directModerationAcknowledged} onChange={(event) => setDirectModerationAcknowledged(event.target.checked)} />Подтверждаю права на тексты и изображения, корректность промокода и посадочной ссылки, а также понимаю возможные расходы.</label><Button size="sm" className="mt-3" onClick={requestDirectModeration} disabled={directModerationSubmitting || !directModerationAcknowledged}>{directModerationSubmitting ? 'Отправляем на модерацию…' : 'Отправить на модерацию'}</Button><p className="mt-2 text-[11px] text-amber-900">Запрос будет записан в журнал проекта с пользователем и временем. Автоматически его не отправляет ни агент, ни синхронизация.</p></div> : null}
                  {productionRelease?.status === 'direct_moderation_requested' ? <div className="mt-3 rounded-md border border-green-200 bg-green-50 p-3 text-xs text-green-900"><div className="flex flex-wrap items-center justify-between gap-2"><p className="font-semibold">Объявление передано на модерацию Яндекс Директа</p><Button size="sm" variant="outline" onClick={checkDirectModerationStatus} disabled={directModerationChecking}>{directModerationChecking ? 'Проверяем…' : 'Проверить статус в Директе'}</Button></div><p className="mt-1">Запрос зафиксирован {productionRelease.moderation_requested_at ? new Date(productionRelease.moderation_requested_at).toLocaleString('ru-RU') : ''}. Дождитесь решения в кабинете Директа; при одобрении и наличии средств возможны показы в рамках лимита.</p>{productionRelease.direct_moderation_last_check ? <p className="mt-2 rounded border border-green-200 bg-white/70 p-2">Последняя проверка: {productionRelease.direct_moderation_last_check.checked_at ? new Date(productionRelease.direct_moderation_last_check.checked_at).toLocaleString('ru-RU') : '—'} · состояние: <b>{productionRelease.direct_moderation_last_check.state || '—'}</b> · статус: <b>{productionRelease.direct_moderation_last_check.status || '—'}</b>{productionRelease.direct_moderation_last_check.clarification ? ` · ${productionRelease.direct_moderation_last_check.clarification}` : ''}</p> : <p className="mt-2 text-[11px]">Статус ещё не проверялся из GLAME.</p>}</div> : null}
                </div>
                {creativeTask ? <p className="mt-3 text-xs text-blue-700">ТЗ передано AI Brand Media (статус: {creativeTask.status}): <Link href={`/ai-marketer/tasks/${creativeTask.id}`} className="underline">открыть задачу креативов</Link>.</p> : null}
                {creativeTask?.status === 'completed' && creativePreviewItems.length ? <div className="mt-5 border-t border-gray-200 pt-4"><div className="mb-3"><h3 className="text-sm font-semibold text-gray-900">Предпросмотр рекламных объявлений</h3><p className="text-xs text-gray-500">Макеты для согласования. Стрелка на карточке меняет только фото, без передачи на доработку.</p></div><div className="grid gap-3 lg:grid-cols-3">{creativePreviewItems.map((preview, index) => { const variantId = index + 1; const review = creativeTask.task_context?.creative_variant_reviews?.[String(variantId)]; const variantMedia = creativeTask.task_context?.creative_variant_media?.[String(variantId)]; const media = creativeMedia?.assets.find((asset) => asset.id === variantMedia) || creativeMedia?.assets[index % Math.max(creativeMedia?.assets.length || 1, 1)]; const selectedForRevision = selectedCreativeVariants.includes(variantId); return <div key={preview.name} className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"><div className="relative min-h-52 bg-gradient-to-br from-stone-800 via-stone-700 to-amber-800 p-4 text-white">{media?.url ? <img src={media.url} alt={media.title} className="absolute inset-0 h-full w-full object-cover opacity-70" /> : null}<button type="button" onClick={() => cycleCreativeVariantMedia(variantId)} disabled={!creativeMedia?.assets.length || creativeReviewSaving} title="Сменить фото на следующее из медиатеки" className="absolute right-2 top-2 z-20 rounded-full bg-white/90 px-2 py-1 text-sm text-gray-800 shadow hover:bg-white disabled:opacity-50">↻</button><div className="relative z-10"><div className="mb-6 flex items-center justify-between pr-9 text-xs"><span className="rounded bg-black/35 px-2 py-1">РСЯ · GLAME Ялта</span><span className="rounded bg-black/35 px-2 py-1">{media ? media.kind : 'фото не выбрано'}</span></div><div className="text-lg font-semibold leading-tight drop-shadow">{preview.banner || preview.headline}</div><div className="mt-5 rounded bg-white/25 px-2 py-1 text-xs">{preview.cta || 'Открыть карточку'}</div></div></div><div className="p-3"><div className="flex items-center justify-between gap-2"><div className="text-[11px] text-gray-500">Поисковое объявление · вариант {variantId}</div><Badge className={review?.status === 'approved' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}>{review?.status === 'approved' ? 'Согласован' : 'На проверке'}</Badge></div><div className="mt-1 text-sm font-semibold text-blue-700">{preview.headline}</div><p className="mt-1 text-xs leading-relaxed text-gray-600">{preview.text}</p><div className="mt-3 text-xs font-medium text-gray-900">CTA: {preview.cta || '—'}</div><div className="mt-3 flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => approveCreativeVariant(variantId)} disabled={creativeReviewSaving || review?.status === 'approved'}>{review?.status === 'approved' ? 'Согласовано' : 'Согласовать'}</Button><label className="flex items-center gap-1 text-xs text-gray-600"><input type="checkbox" checked={selectedForRevision} onChange={() => setSelectedCreativeVariants((current) => selectedForRevision ? current.filter((item) => item !== variantId) : [...current, variantId])} /> Доработать</label></div></div></div>; })}</div><div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3"><label className="block text-xs font-medium text-gray-700">Комментарий к согласованию или замечания к доработке<textarea value={creativeReviewNote} onChange={(event) => setCreativeReviewNote(event.target.value)} placeholder="Например: в варианте 2 заменить акцент на упаковку и добавить фото витрины" className="mt-1 min-h-20 w-full rounded-md border border-gray-300 bg-white p-2 text-sm" /></label><div className="mt-2 flex flex-wrap gap-2"><Button size="sm" onClick={approveCreativePackage} disabled={creativeReviewSaving || creativeTask.task_context?.creative_review_status === 'approved'}>{creativeReviewSaving ? 'Сохранение...' : 'Согласовать весь пакет'}</Button><Button size="sm" variant="outline" onClick={requestCreativeRevision} disabled={creativeReviewSaving}>Вернуть выбранные ({selectedCreativeVariants.length || 3}) на доработку</Button></div></div></div> : null}
              </Card>
            ) : null}
            <AgentBoardChat
              key={selectedProjectTaskId || 'traffic-empty'}
              agentId="traffic-growth-agent"
              agentName="AI Traffic & Growth"
              boardId="traffic"
              aliases={['traffic-growth', 'traffic-board', 'growth']}
              hiddenTaskContextKey="traffic_project_hidden"
              selectedTaskIdOverride={selectedProjectTaskId}
              onSelectedTaskChange={setSelectedProjectTaskId}
            />
          </div>
        </div>

        {utilityPanel === 'accounts' ? <UtilityPanel title="Рекламные кабинеты" description="Подключения Яндекс Директа, Бизнеса и Карт для работы агента." onClose={() => setUtilityPanel(null)}>
        <section>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Рекламные кабинеты</h2>
              <p className="mt-1 text-sm text-gray-600">Реестр аккаунтов GLAME для Яндекс Директа, Бизнеса и Карт. Кампании импортируются только после OAuth-подключения владельца.</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={loadAdvertisingConnections}>Обновить</Button>
              <Button size="sm" onClick={() => openConnectionForm()}>Подключить кабинет</Button>
            </div>
          </div>
          <Card className="p-5">
            <div className={`mb-4 rounded-md border p-4 text-sm ${oauthReadiness?.configured ? 'border-green-200 bg-green-50 text-green-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <span className="font-medium">OAuth Яндекса: </span>{oauthReadiness?.message || 'Проверяем конфигурацию…'}
                  <ol className="mt-3 list-decimal space-y-1 pl-4 text-xs leading-5">
                    <li>Откройте <a className="underline" href="https://oauth.yandex.ru/client/new/id/" target="_blank" rel="noreferrer">страницу создания OAuth-приложения Яндекса</a> и войдите под владельцем рекламного кабинета.</li>
                    <li>Создайте приложение типа «Для авторизации пользователей», включите «Веб-сервисы» и добавьте право <b>direct:api</b>.</li>
                    <li>Скопируйте выданные <b>Client ID</b> и <b>Client secret</b> в защищённые поля ниже.</li>
                    <li>Добавьте кабинет в реестр. После сохранения OAuth-настройки он будет готов к авторизации владельца и импорту кампаний.</li>
                  </ol>
                </div>
                <Button variant="outline" size="sm" onClick={() => setOauthFormOpen((open) => !open)}>{oauthFormOpen ? 'Скрыть настройку' : oauthReadiness?.configured ? 'Изменить OAuth' : 'Ввести Client ID'}</Button>
              </div>
              {oauthFormOpen ? (
                <div className="mt-4 grid gap-3 border-t border-current/20 pt-4 md:grid-cols-2">
                  <label className="text-xs">Client ID из OAuth-приложения
                    <input value={oauthForm.client_id} onChange={(event) => setOauthForm((current) => ({ ...current, client_id: event.target.value }))} placeholder="например, 1234567890abcdef" className="mt-1 h-9 w-full rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900" />
                  </label>
                  <label className="text-xs">Client secret
                    <input type="password" autoComplete="new-password" value={oauthForm.client_secret} onChange={(event) => setOauthForm((current) => ({ ...current, client_secret: event.target.value }))} placeholder={oauthReadiness?.client_secret_configured ? 'Секрет сохранён — введите новый только для замены' : 'Вставьте Client secret'} className="mt-1 h-9 w-full rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900" />
                  </label>
                  <div className="md:col-span-2">
                    <p className="mb-2 text-xs">Client secret шифруется до записи в БД, не показывается повторно и не передаётся в чаты или задачи агента. Точный Callback URL GLAME появится после нажатия «Авторизовать владельца» у нужного кабинета.</p>
                    <Button size="sm" onClick={saveOAuthSettings} disabled={oauthSaving}>{oauthSaving ? 'Сохранение…' : 'Сохранить OAuth-настройку'}</Button>
                  </div>
                </div>
              ) : null}
            </div>

            {connectionFormOpen ? (
              <div className="mb-5 rounded-lg border border-amber-200 bg-amber-50/60 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h3 className="font-medium text-gray-900">{editingConnectionId ? 'Изменить кабинет' : 'Подключить рекламный кабинет'}</h3>
                  <Button variant="outline" size="sm" onClick={() => setConnectionFormOpen(false)}>Закрыть</Button>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="text-xs text-gray-600">Площадка
                    <select value={connectionForm.platform} onChange={(event) => setConnectionForm((current) => ({ ...current, platform: event.target.value as AdvertisingConnectionInput['platform'] }))} className="mt-1 h-9 w-full rounded-md border border-gray-300 bg-white px-2 text-sm">
                      {Object.entries(AD_PLATFORM_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                  </label>
                  <label className="text-xs text-gray-600">Название в GLAME
                    <input value={connectionForm.name} onChange={(event) => setConnectionForm((current) => ({ ...current, name: event.target.value }))} placeholder="GLAME — основной Директ" className="mt-1 h-9 w-full rounded-md border border-gray-300 px-2 text-sm" />
                  </label>
                  <label className="text-xs text-gray-600">Логин владельца / аккаунт
                    <input value={connectionForm.account_login || ''} onChange={(event) => setConnectionForm((current) => ({ ...current, account_login: event.target.value }))} placeholder="login@yandex.ru" className="mt-1 h-9 w-full rounded-md border border-gray-300 px-2 text-sm" />
                  </label>
                  <label className="text-xs text-gray-600">ClientLogin (для агентского доступа)
                    <input value={connectionForm.client_login || ''} onChange={(event) => setConnectionForm((current) => ({ ...current, client_login: event.target.value }))} placeholder="необязательно" className="mt-1 h-9 w-full rounded-md border border-gray-300 px-2 text-sm" />
                  </label>
                  <label className="text-xs text-gray-600">Организация
                    <input value={connectionForm.organization_name || ''} onChange={(event) => setConnectionForm((current) => ({ ...current, organization_name: event.target.value }))} placeholder="GLAME Ялта" className="mt-1 h-9 w-full rounded-md border border-gray-300 px-2 text-sm" />
                  </label>
                  {connectionForm.platform === 'yandex_business' ? <label className="text-xs text-gray-600">Продукт Яндекс Бизнес
                    <select value={String(connectionForm.permissions?.business_product || 'advertising_subscription')} onChange={(event) => setConnectionForm((current) => ({ ...current, permissions: { ...(current.permissions || {}), business_product: event.target.value } }))} className="mt-1 h-9 w-full rounded-md border border-gray-300 bg-white px-2 text-sm">
                      {Object.entries(BUSINESS_PRODUCT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                  </label> : null}
                  {connectionForm.platform === 'yandex_business' ? <label className="text-xs text-gray-600">Номер Рекламной подписки
                    <input value={String(connectionForm.permissions?.business_campaign_id || '')} onChange={(event) => setConnectionForm((current) => ({ ...current, permissions: { ...(current.permissions || {}), business_campaign_id: event.target.value.replace(/\D/g, '') } }))} placeholder="Например, 54356889" inputMode="numeric" className="mt-1 h-9 w-full rounded-md border border-gray-300 px-2 text-sm" />
                    <span className="mt-1 block text-[11px] text-gray-500">Номер из заголовка кампании в Яндекс Бизнесе. GLAME не создаёт подписку, а связывает её выгрузку и аналитику.</span>
                  </label> : null}
                  {connectionForm.platform === 'yandex_business' || connectionForm.platform === 'yandex_maps' ? <label className="text-xs text-gray-600">Счётчик магазина для аналитики
                    <select value={connectionForm.metrika_counter_id || ''} onChange={(event) => setConnectionForm((current) => ({ ...current, metrika_counter_id: event.target.value }))} className="mt-1 h-9 w-full rounded-md border border-gray-300 bg-white px-2 text-sm"><option value="">Не привязан</option>{metrikaSettings?.counters?.map((counter) => <option key={counter.id} value={counter.id}>{counter.name} · № {counter.counter_id}</option>)}</select>
                  </label> : null}
                  <label className="mt-5 flex items-center gap-2 text-xs text-gray-700">
                    <input type="checkbox" checked={connectionForm.is_active !== false} onChange={(event) => setConnectionForm((current) => ({ ...current, is_active: event.target.checked }))} />
                    Кабинет активен для агента
                  </label>
                </div>
                <p className="mt-3 text-xs text-gray-600">Яндекс Бизнес — отдельный продукт от Директа: Рекламная подписка сама распределяет показы между Поиском, РСЯ и Картами. Здесь сохраняется связь с GLAME — без паролей и OAuth-токенов.</p>
                <Button className="mt-3" size="sm" onClick={saveAdvertisingConnection} disabled={connectionSaving}>{connectionSaving ? 'Сохранение…' : editingConnectionId ? 'Сохранить изменения' : 'Добавить кабинет'}</Button>
              </div>
            ) : null}

            {authorizationInfo ? (
              <div className="mb-5 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="font-medium">Авторизация владельца кабинета</h3>
                    <p className="mt-1 text-xs">{authorizationInfo.instruction}</p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => setAuthorizationInfo(null)}>Закрыть</Button>
                </div>
                <ol className="mt-3 list-decimal space-y-1 pl-4 text-xs leading-5">
                  <li>В Яндекс OAuth откройте созданное приложение, включите тип «Веб-сервисы» и добавьте этот Callback URL:</li>
                </ol>
                <div className="mt-2 break-all rounded border border-blue-200 bg-white p-2 font-mono text-xs text-gray-800">{authorizationInfo.callback_url}</div>
                <p className="mt-3 text-xs">После сохранения настройки откройте ссылку ниже. Она действует до {new Date(authorizationInfo.expires_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}; входите под владельцем рекламного кабинета.</p>
                <a href={authorizationInfo.authorization_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex h-9 items-center rounded-md bg-blue-700 px-3 text-sm font-medium text-white hover:bg-blue-800">Авторизовать в Яндексе</a>
              </div>
            ) : null}

            <div className="space-y-3">
              {adConnections.map((connection) => (
                <div key={connection.id} className="rounded-lg border border-gray-200 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-medium text-gray-900">{connection.name}</h3>
                        <Badge variant="outline">{AD_PLATFORM_LABELS[connection.platform]}</Badge>
                        {connection.platform === 'yandex_business' ? <Badge className="bg-blue-50 text-blue-800">{BUSINESS_PRODUCT_LABELS[String(connection.permissions?.business_product || 'advertising_subscription')] || 'Рекламная подписка'}</Badge> : null}
                        {connection.platform === 'yandex_business' && connection.permissions?.business_campaign_id ? <Badge variant="outline">Подписка № {connection.permissions.business_campaign_id}</Badge> : null}
                        <Badge className={connection.status === 'connected' ? 'bg-green-100 text-green-800' : connection.status === 'awaiting_account_authorization' ? 'bg-blue-100 text-blue-800' : 'bg-amber-100 text-amber-800'}>{connection.status}</Badge>
                        {!connection.is_active ? <Badge variant="outline">отключён</Badge> : null}
                      </div>
                      <p className="mt-1 text-xs text-gray-600">Аккаунт: {connection.account_login || 'не указан'}{connection.client_login ? ` · ClientLogin: ${connection.client_login}` : ''}{connection.organization_name ? ` · ${connection.organization_name}` : ''}</p>
                      {connection.metrika_counter_id ? <p className="mt-1 text-xs text-indigo-700">Привязан к срезу магазина: {metrikaSettings?.counters?.find((counter) => counter.id === connection.metrika_counter_id)?.name || 'счётчик Метрики'}</p> : null}
                      {connection.platform === 'yandex_business' && connection.permissions?.business_campaign_id ? <p className="mt-1 text-xs text-indigo-700">Для аналитики связана Рекламная подписка № {connection.permissions.business_campaign_id}.</p> : null}
                      <p className="mt-1 text-xs text-gray-500">Синхронизация: {connection.last_sync_at ? new Date(connection.last_sync_at).toLocaleString('ru-RU') : 'ещё не запускалась'}{connection.last_sync_summary?.message ? ` · ${connection.last_sync_summary.message}` : ''}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" size="sm" onClick={() => openConnectionForm(connection)}>Изменить</Button>
                      <Button variant="outline" size="sm" className="text-red-700 hover:text-red-800" onClick={() => deleteAdvertisingConnection(connection)} disabled={deletingConnectionId === connection.id}>{deletingConnectionId === connection.id ? 'Удаляем…' : 'Удалить'}</Button>
                      {connection.platform === 'yandex_direct' ? <><Button variant="outline" size="sm" onClick={() => beginOwnerAuthorization(connection)} disabled={authorizationCreatingId === connection.id || !connection.is_active}>{authorizationCreatingId === connection.id ? 'Подготовка…' : connection.status === 'connected' ? 'Переавторизовать владельца' : 'Авторизовать владельца'}</Button><Button variant="outline" size="sm" onClick={() => createDirectTestCampaign(connection)} disabled={directTestCreatingId === connection.id || !connection.is_active} title="Создаёт ЕПК без групп и объявлений; показы и списания невозможны">{directTestCreatingId === connection.id ? 'Создаём…' : 'Тестовая ЕПК'}</Button><Button variant="outline" size="sm" onClick={() => syncAdvertisingConnection(connection)} disabled={syncingConnectionId === connection.id || !connection.is_active}>{syncingConnectionId === connection.id ? 'Проверка…' : 'Синхронизировать'}</Button></> : <span className="self-center text-xs text-gray-500">Факты карточки вводятся в единой аналитике</span>}
                    </div>
                  </div>
                </div>
              ))}
              {adConnections.length === 0 ? <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 text-sm text-gray-500">Пока нет подключённых кабинетов. Добавьте Яндекс Директ или Яндекс Бизнес для GLAME Ялта.</div> : null}
            </div>
          </Card>
        </section>
        </UtilityPanel> : null}

        {utilityPanel === 'direct-campaigns' ? <UtilityPanel title="Кампании Яндекс Директа" description="Кампании из подключённого кабинета. Свяжите каждую с рекламным проектом GLAME — это не меняет настройки Директа." onClose={() => setUtilityPanel(null)}>
        <section className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4">
            <div>
              <p className="font-medium text-emerald-950">Импорт из Яндекс Директа</p>
              <p className="mt-1 text-sm text-emerald-800">Синхронизация читает кампании и статистику. Связь с проектом GLAME нужна для общей истории, креативов и аналитики.</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => { setUtilityPanel('accounts'); }}>Открыть кабинеты</Button>
          </div>
          {directCampaigns.map((campaign) => {
            const linkedProjectId = String(campaign.metrics?.linked_traffic_project_task_id || '');
            const linkedProject = projectTopics.find((project) => project.task_id === linkedProjectId);
            return <Card key={campaign.id} className="p-4">
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className="bg-emerald-100 text-emerald-800">Яндекс Директ</Badge>
                    <Badge variant="outline">№ {campaign.external_id || campaign.metrics?.yandex_campaign_id || '—'}</Badge>
                    <Badge className={campaign.status === 'active' ? 'bg-green-100 text-green-800' : campaign.status === 'paused' ? 'bg-gray-100 text-gray-700' : 'bg-amber-100 text-amber-800'}>{campaign.status === 'draft' ? 'черновик' : campaign.status}</Badge>
                  </div>
                  <h3 className="mt-2 font-semibold text-gray-900">{campaign.name}</h3>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
                    <Metric label="Тип" value={String(campaign.metrics?.yandex_type || '—')} />
                    <Metric label="Бюджет" value={campaign.budget ? formatCurrency.format(campaign.budget) : '—'} />
                    <Metric label="Режим" value="только чтение" />
                  </div>
                </div>
                <div className="space-y-3">
                  <label className="block text-xs text-gray-600">Рекламный проект GLAME
                    <select value={linkedProjectId} onChange={(event) => void linkDirectCampaign(campaign, event.target.value)} disabled={campaignLinkSavingId === campaign.id} className="mt-1 h-9 w-full rounded-md border border-emerald-200 bg-white px-2 text-sm text-gray-900">
                      <option value="">Не связан</option>
                      {projectTopics.map((project) => <option key={project.task_id} value={project.task_id}>{project.title}</option>)}
                    </select>
                    <span className="mt-1 block text-[11px] text-emerald-800">{campaignLinkSavingId === campaign.id ? 'Сохраняем связь…' : linkedProject ? `Связана с: ${linkedProject.title}` : 'Выберите тему работы traffic-growth агента.'}</span>
                  </label>
                  <label className="block text-xs text-gray-600">Счётчик Метрики для аналитики
                    <select value={String(campaign.metrics?.metrika_counter_id || '')} onChange={(event) => void assignCampaignAnalyticsStore(campaign, event.target.value)} disabled={campaignCounterSavingId === campaign.id} className="mt-1 h-9 w-full rounded-md border border-indigo-200 bg-white px-2 text-sm text-gray-900">
                      <option value="">Не привязан</option>
                      {metrikaSettings?.counters?.map((counter) => <option key={counter.id} value={counter.id}>{counter.name} · № {counter.counter_id}</option>)}
                    </select>
                    <span className="mt-1 block text-[11px] text-indigo-700">{campaignCounterSavingId === campaign.id ? 'Сохраняем счётчик…' : 'Привязка действует только в аналитике GLAME и не меняет кампанию в Директе.'}</span>
                  </label>
                </div>
              </div>
            </Card>;
          })}
          {!directCampaigns.length ? <Card className="p-5 text-sm text-gray-600">Кампании ещё не импортированы. В «Рекламных кабинетах» нажмите «Синхронизировать» у авторизованного Яндекс Директа.</Card> : null}
        </section>
        </UtilityPanel> : null}

        {utilityPanel === 'feed' ? <UtilityPanel title="Товарный фид" description="Настройка каталога и постоянной YML-ссылки для Яндекс Бизнеса." onClose={() => setUtilityPanel(null)}>
        <section>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Товарный фид для Яндекс Бизнес</h2>
              <p className="mt-1 text-sm text-gray-600">YML-файл для раздела «Товары и услуги» в карточке GLAME Ялта.</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={loadFeedPreview} disabled={feedLoading}>{feedLoading ? 'Проверка...' : 'Проверить каталог'}</Button>
              <a href={feedDownloadUrl()} className="inline-flex h-9 items-center rounded-md bg-amber-500 px-3 text-sm font-medium text-white hover:bg-amber-600">Скачать XML</a>
            </div>
          </div>
          <Card className="p-5">
            <div className="grid grid-cols-1 gap-3 border-b border-gray-100 pb-4 sm:grid-cols-2 lg:grid-cols-3">
              <label className="text-xs font-medium text-gray-600">Цена от, ₽<input inputMode="decimal" value={feedFilters.minPrice} onChange={(event) => setFeedFilters((current) => ({ ...current, minPrice: event.target.value }))} placeholder={feedFilterOptions?.min_price ? String(Math.floor(feedFilterOptions.min_price)) : '0'} className="mt-1 h-9 w-full rounded-md border border-gray-300 px-2 text-sm" /></label>
              <label className="text-xs font-medium text-gray-600">Цена до, ₽<input inputMode="decimal" value={feedFilters.maxPrice} onChange={(event) => setFeedFilters((current) => ({ ...current, maxPrice: event.target.value }))} placeholder={feedFilterOptions?.max_price ? String(Math.ceil(feedFilterOptions.max_price)) : 'Без лимита'} className="mt-1 h-9 w-full rounded-md border border-gray-300 px-2 text-sm" /></label>
              <label className="text-xs font-medium text-gray-600">Наличие<select value={feedFilters.storeId ? 'in_stock' : feedFilters.availability} onChange={(event) => setFeedFilters((current) => ({ ...current, availability: event.target.value }))} disabled={Boolean(feedFilters.storeId)} className="mt-1 h-9 w-full rounded-md border border-gray-300 bg-white px-2 text-sm disabled:bg-gray-100"><option value="all">Любое</option><option value="in_stock">В наличии</option><option value="out_of_stock">Нет в наличии</option><option value="unknown">Неизвестно</option></select></label>
              <label className="text-xs font-medium text-gray-600">Бренд<select value={feedFilters.brand} onChange={(event) => setFeedFilters((current) => ({ ...current, brand: event.target.value }))} className="mt-1 h-9 w-full rounded-md border border-gray-300 bg-white px-2 text-sm"><option value="">Все бренды</option>{feedFilterOptions?.brands.map((brand) => <option key={brand} value={brand}>{brand}</option>)}</select></label>
              <label className="text-xs font-medium text-gray-600">Категория<select value={feedFilters.category} onChange={(event) => setFeedFilters((current) => ({ ...current, category: event.target.value }))} className="mt-1 h-9 w-full rounded-md border border-gray-300 bg-white px-2 text-sm"><option value="">Все категории</option>{feedFilterOptions?.categories.map((category) => <option key={category} value={category}>{category}</option>)}</select></label>
              <label className="text-xs font-medium text-gray-600">Магазин: товары в наличии<select value={feedFilters.storeId} onChange={(event) => setFeedFilters((current) => ({ ...current, storeId: event.target.value, availability: event.target.value ? 'in_stock' : 'all' }))} className="mt-1 h-9 w-full rounded-md border border-gray-300 bg-white px-2 text-sm"><option value="">Все магазины</option>{feedFilterOptions?.stores.map((store) => <option key={store.external_id} value={store.external_id}>{store.name}</option>)}</select></label>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3"><p className="text-xs text-gray-500">Фильтры применяются только к скачиваемому YML и предпросмотру — каталог GLAME не изменяется. При выборе магазина в фид попадут только товары с остатком именно в этой точке.</p><Button variant="outline" size="sm" onClick={resetFeedFilters} disabled={feedLoading}>Сбросить</Button></div>
            <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-blue-950">Автоматическое обновление в Яндекс Картах</p>
                  <p className="mt-1 text-xs text-blue-800">Сохраните нужные фильтры и вставьте постоянную ссылку ниже в Яндекс Бизнес один раз. Яндекс будет забирать актуальный каталог по этой ссылке ежедневно.</p>
                </div>
                <Button size="sm" onClick={publishAutomaticFeed} disabled={publicFeedSaving}>{publicFeedSaving ? 'Сохраняем...' : 'Сохранить для автообновления'}</Button>
              </div>
              {publicFeedSettings ? (
                <div className="mt-3">
                  <label className="text-xs font-medium text-blue-900">Постоянная ссылка YML</label>
                  <div className="mt-1 flex flex-col gap-2 sm:flex-row">
                    <input readOnly value={publicFeedSettings.public_url} className="h-9 min-w-0 flex-1 rounded-md border border-blue-200 bg-white px-2 text-xs text-gray-700" />
                    <Button type="button" variant="outline" size="sm" onClick={() => void navigator.clipboard?.writeText(publicFeedSettings.public_url)}>Копировать</Button>
                  </div>
                  <p className="mt-2 text-xs text-blue-800">Опубликованные фильтры: {publicFeedSettings.min_price != null ? `от ${formatNumber.format(publicFeedSettings.min_price)} ₽` : 'без минимальной цены'}{publicFeedSettings.max_price != null ? `, до ${formatNumber.format(publicFeedSettings.max_price)} ₽` : ''}{publicFeedSettings.store_id ? `, в наличии в магазине: ${feedFilterOptions?.stores.find((store) => store.external_id === publicFeedSettings.store_id)?.name || publicFeedSettings.store_id}` : publicFeedSettings.availability && publicFeedSettings.availability !== 'all' ? `, ${publicFeedSettings.availability === 'in_stock' ? 'только в наличии' : publicFeedSettings.availability === 'out_of_stock' ? 'только нет в наличии' : 'с неизвестным наличием'}` : ''}{publicFeedSettings.brands ? `, бренд: ${publicFeedSettings.brands}` : ''}{publicFeedSettings.categories ? `, категория: ${publicFeedSettings.categories}` : ''}.</p>
                  <p className="mt-1 text-xs text-blue-800">В Яндекс Бизнес: «О компании» → «Товары и услуги» → источник «YML-фид». Не меняйте URL после подключения.</p>
                </div>
              ) : null}
            </div>
            {feedPreview ? (
              <>
                <div className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
                  <Metric label="В выборке" value={formatNumber.format(feedPreview.total_active)} />
                  <Metric label="В фиде" value={formatNumber.format(feedPreview.included)} />
                  <Metric label="Исключено" value={formatNumber.format(feedPreview.skipped)} />
                  <Metric label="Категорий" value={formatNumber.format(feedPreview.categories)} />
                </div>
                {feedPreview.skipped_items.length > 0 ? <p className="mt-4 text-xs text-amber-700">Исключены товары без цены или публичного изображения. Проверьте первые: {feedPreview.skipped_items.slice(0, 3).map((item) => `${item.name || 'Без названия'} — ${item.reason}`).join('; ')}.</p> : <p className="mt-4 text-xs text-green-700">Все активные товары прошли базовую проверку и готовы к включению в фид.</p>}
              </>
            ) : <p className="text-sm text-gray-500">Проверьте каталог перед скачиванием: генератор исключит товары без цены или публичной фотографии.</p>}
          </Card>
        </section>
        </UtilityPanel> : null}

        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Active Growth Campaigns — Активные кампании</h2>
            <Button variant="outline" size="sm" onClick={() => loadData()} disabled={loading}>Обновить</Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {campaigns.map((campaign) => (
              <Card key={campaign.id} className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <Badge>{campaign.type}</Badge>
                      {(campaign.channels || []).map((channel) => <Badge key={channel} variant="outline">{channel}</Badge>)}
                      <Badge className={campaign.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}>{campaign.status}</Badge>
                    </div>
                    <h3 className="font-medium text-gray-900">{campaign.name}</h3>
                    <div className="grid grid-cols-3 gap-4 mt-3 text-sm">
                      <Metric label="Бюджет" value={campaign.budget ? formatCurrency.format(campaign.budget) : '—'} />
                      <Metric label="Аудитория" value={String(campaign.target_audience?.name || campaign.target_audience?.segment || '—')} />
                      <Metric label="KPI" value={String(campaign.metrics?.kpi || campaign.metrics?.goal || '—')} />
                    </div>
                    {campaign.metrics?.yandex_campaign_id ? <label className="mt-4 block text-xs text-indigo-900">Магазин для аналитики Директа
                      <select value={String(campaign.metrics?.metrika_counter_id || '')} onChange={(event) => void assignCampaignAnalyticsStore(campaign, event.target.value)} disabled={campaignCounterSavingId === campaign.id} className="mt-1 h-9 w-full rounded-md border border-indigo-200 bg-white px-2 text-sm text-gray-900"><option value="">Не привязана</option>{metrikaSettings?.counters?.map((counter) => <option key={counter.id} value={counter.id}>{counter.name} · № {counter.counter_id}</option>)}</select>
                      <span className="mt-1 block text-xs text-indigo-700">{campaignCounterSavingId === campaign.id ? 'Сохраняем…' : 'Привязка применяется к этой кампании, а не к аккаунту Директа.'}</span>
                    </label> : null}
                  </div>
                </div>
              </Card>
            ))}
            {!loading && campaigns.length === 0 && tasks.length === 0 ? <Card className="p-5 text-sm text-gray-500">Growth-кампаний и задач пока нет.</Card> : null}
          </div>
        </section>

        {utilityPanel === 'analytics' ? <UtilityPanel title="Рекламная аналитика" description="Единая воронка Директа, Яндекс Бизнеса/Карт и Метрики." onClose={() => setUtilityPanel(null)}>
        <section>
          <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Единая рекламная аналитика</h2>
              <p className="text-sm text-gray-500">Директ, Яндекс Бизнес/Карты и Метрика в одной воронке. Источник и способ получения каждого показателя видны отдельно.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2"><label className="text-xs text-gray-600">Срез<select value={selectedAnalyticsCounterId} onChange={(event) => { const counterId = event.target.value; setSelectedAnalyticsCounterId(counterId); void loadData(counterId); }} className="ml-1 h-9 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900"><option value="">Все источники</option>{metrikaSettings?.counters?.map((counter) => <option key={counter.id} value={counter.id}>{counter.name}</option>)}</select></label><Button variant="outline" size="sm" onClick={() => loadData()} disabled={loading}>Обновить данные</Button></div>
          </div>
          <Card className="p-5">
            {advertisingAnalytics ? (
              <>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
                  <Metric label="Показы" value={formatNumber.format(advertisingAnalytics.totals.impressions)} />
                  <Metric label="Клики" value={formatNumber.format(advertisingAnalytics.totals.clicks)} />
                  <Metric label="Расход" value={formatCurrency.format(advertisingAnalytics.totals.cost)} />
                  <Metric label="CTR" value={`${advertisingAnalytics.totals.ctr.toFixed(2)}%`} />
                  <Metric label="CPC" value={formatCurrency.format(advertisingAnalytics.totals.cpc)} />
                  <Metric label="Конверсии" value={formatNumber.format(advertisingAnalytics.totals.conversions)} />
                </div>
                {advertisingAnalytics.funnel ? <div className="mt-5 rounded-lg border border-blue-100 bg-blue-50 p-4"><p className="text-sm font-semibold text-blue-950">Воронка за 14 дней{advertisingAnalytics.scope?.mode === 'store' ? ' — выбранный магазин' : ''}</p><p className="mt-1 text-xs text-blue-800">{advertisingAnalytics.scope?.mode === 'store' ? 'Показы и расход скрыты, пока рекламные кабинеты не привязаны к конкретному счётчику магазина.' : 'Действия карточек — Метрика; рекламные показатели — Яндекс Директ и Бизнес.'}</p><div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-7"><Metric label="Показы" value={formatNumber.format(advertisingAnalytics.funnel.impressions)} /><Metric label="Клики" value={formatNumber.format(advertisingAnalytics.funnel.clicks)} /><Metric label="Открытия карточки" value={formatNumber.format(advertisingAnalytics.funnel.card_opens)} /><Metric label="Маршруты" value={formatNumber.format(advertisingAnalytics.funnel.routes)} /><Metric label="Звонки" value={formatNumber.format(advertisingAnalytics.funnel.calls)} /><Metric label="Визиты сайта" value={formatNumber.format(advertisingAnalytics.funnel.website_visits)} /><Metric label="Конверсии" value={formatNumber.format(advertisingAnalytics.funnel.conversions)} /></div></div> : null}
                {advertisingAnalytics.business_stores?.length ? <div className="mt-5 overflow-x-auto rounded-lg border border-amber-200 bg-amber-50 p-4"><div className="mb-3"><p className="text-sm font-semibold text-amber-950">Данные карточек Яндекс Бизнеса / Карт</p><p className="mt-1 text-xs text-amber-800">Отображаются отдельно от рекламных показов и Метрики. Период — последние {advertisingAnalytics.period_days} дней.</p></div><table className="w-full min-w-[680px] text-sm"><thead className="text-left text-xs text-amber-900"><tr><th className="pb-2 font-medium">Магазин</th><th className="pb-2 font-medium">Дней</th><th className="pb-2 font-medium">Открытия</th><th className="pb-2 font-medium">Маршруты</th><th className="pb-2 font-medium">Звонки</th><th className="pb-2 font-medium">Сообщения</th><th className="pb-2 font-medium">Сайт</th></tr></thead><tbody>{advertisingAnalytics.business_stores.map((store) => <tr key={store.connection_id} className="border-t border-amber-200"><td className="py-2 font-medium text-gray-900">{store.store_name}</td><td className="py-2">{formatNumber.format(store.days)}</td><td className="py-2">{formatNumber.format(store.card_opens)}</td><td className="py-2">{formatNumber.format(store.routes)}</td><td className="py-2">{formatNumber.format(store.calls)}</td><td className="py-2">{formatNumber.format(store.messages)}</td><td className="py-2">{formatNumber.format(store.website_clicks)}</td></tr>)}</tbody></table></div> : null}
                {advertisingAnalytics.campaigns.length ? <div className="mt-5 overflow-x-auto border-t border-gray-100 pt-4"><table className="w-full min-w-[700px] text-sm"><thead className="text-left text-xs text-gray-500"><tr><th className="pb-2 font-medium">Кампания</th><th className="pb-2 font-medium">Показы</th><th className="pb-2 font-medium">Клики</th><th className="pb-2 font-medium">Расход</th><th className="pb-2 font-medium">CTR</th><th className="pb-2 font-medium">CPC</th></tr></thead><tbody>{advertisingAnalytics.campaigns.map((campaign) => <tr key={`${campaign.campaign_id || campaign.campaign_name}`} className="border-t border-gray-100"><td className="py-2 font-medium text-gray-900">{campaign.campaign_name}</td><td className="py-2">{formatNumber.format(campaign.impressions)}</td><td className="py-2">{formatNumber.format(campaign.clicks)}</td><td className="py-2">{formatCurrency.format(campaign.cost)}</td><td className="py-2">{campaign.ctr.toFixed(2)}%</td><td className="py-2">{formatCurrency.format(campaign.cpc)}</td></tr>)}</tbody></table></div> : <p className="mt-4 text-sm text-amber-700">Пока нет импортированных дневных строк. В «Рекламных кабинетах» нажмите «Синхронизировать» для авторизованного Яндекс Директа.</p>}
                <div className="mt-5 grid gap-3 border-t border-gray-100 pt-4 md:grid-cols-3">{Object.entries(advertisingAnalytics.sources).map(([source, info]) => <div key={source} className="rounded-md border border-gray-200 p-3"><p className="text-sm font-medium text-gray-900">{source === 'yandex_direct' ? 'Яндекс Директ' : source === 'yandex_business_maps' ? 'Яндекс Бизнес и Карты' : 'Яндекс Метрика'}</p><p className={`mt-1 text-xs ${info.status === 'ready' ? 'text-green-700' : info.status === 'error' ? 'text-red-700' : 'text-amber-700'}`}>{info.status === 'ready' ? 'Данные доступны' : info.status === 'not_configured' ? 'Требуется подключение' : info.status === 'not_connected' ? 'Кабинет не подключён' : info.status === 'awaiting_input' ? 'Нужен ввод фактов' : 'Данных пока нет'}</p><p className="mt-1 text-xs text-gray-500">{info.message}</p>{source === 'yandex_business_maps' && info.status === 'not_connected' ? <Button className="mt-3" size="sm" variant="outline" onClick={openBusinessConnectionForm}>Подключить Яндекс Бизнес</Button> : null}</div>)}</div>
                <div className="mt-5 rounded-lg border border-indigo-200 bg-indigo-50 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm font-semibold text-indigo-950">Яндекс Метрика</p><p className="mt-1 text-xs text-indigo-800">Каждый счётчик — самостоятельный источник: сайт GLAME, приложение или сайт партнёра. Посещения суммируются в воронке, но видны и по отдельности.</p></div><Button size="sm" variant="outline" onClick={() => setMetrikaFormOpen((current) => !current)}>{metrikaFormOpen ? 'Закрыть' : 'Добавить счётчик'}</Button></div>{metrikaSettings?.counters?.length ? <div className="mt-3 grid gap-2 sm:grid-cols-2">{metrikaSettings.counters.map((counter) => { const fact = advertisingAnalytics.metrika_counters?.find((item) => item.id === counter.id); return <div key={counter.id} className="rounded-md border border-indigo-100 bg-white p-2 text-xs text-indigo-950"><span className="font-medium">{counter.name}</span><span className="ml-2 text-indigo-700">№ {counter.counter_id}</span><span className="ml-2 text-green-700">{fact?.status === 'ready' ? `${formatNumber.format(fact.data?.visits || 0)} визитов` : 'нет ответа'}</span></div>})}</div> : <p className="mt-2 text-xs text-amber-700">Пока нет подключённых счётчиков.</p>}{metrikaFormOpen || !metrikaSettings?.configured ? <div className="mt-3 grid gap-3 sm:grid-cols-3"><label className="text-xs text-indigo-900">Название<input value={metrikaForm.name} onChange={(event) => setMetrikaForm((current) => ({ ...current, name: event.target.value }))} placeholder="Например, Приложение GLAME" className="mt-1 h-9 w-full rounded-md border border-indigo-200 bg-white px-2 text-sm" /></label><label className="text-xs text-indigo-900">ID счётчика<input value={metrikaForm.counter_id} onChange={(event) => setMetrikaForm((current) => ({ ...current, counter_id: event.target.value }))} placeholder="Например, 12345678" className="mt-1 h-9 w-full rounded-md border border-indigo-200 bg-white px-2 text-sm" /></label><label className="text-xs text-indigo-900">OAuth‑токен<input type="password" value={metrikaForm.oauth_token} onChange={(event) => setMetrikaForm((current) => ({ ...current, oauth_token: event.target.value }))} placeholder={metrikaSettings?.oauth_token_configured ? 'Уже сохранён — можно не вводить' : 'Токен с доступом к счётчику'} className="mt-1 h-9 w-full rounded-md border border-indigo-200 bg-white px-2 text-sm" /></label><p className="sm:col-span-3 text-xs text-indigo-800">{metrikaSettings?.oauth_token_configured ? 'Для нового счётчика будет использован уже защищённо сохранённый доступ GLAME. Введите новый токен только если счётчик доступен другому аккаунту Яндекса.' : 'Токен потребуется только при первом подключении Метрики; он сохраняется зашифрованно и не показывается повторно.'}</p><div className="sm:col-span-3"><Button size="sm" onClick={saveMetrikaSettings} disabled={metrikaSaving || !metrikaForm.counter_id || (!metrikaForm.oauth_token && !metrikaSettings?.oauth_token_configured)}>{metrikaSaving ? 'Сохраняем...' : 'Сохранить счётчик'}</Button></div></div> : null}</div>
                <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm font-semibold text-amber-950">Факты из Яндекс Бизнеса / Карт</p><p className="mt-1 text-xs text-amber-800">Выберите магазин и загрузите Excel/CSV из «Статистика → Рекламная» Яндекс Бизнеса с детализацией по дням. Маршруты, звонки и переходы распознаются автоматически.</p></div><Button size="sm" onClick={saveBusinessMapsMetrics} disabled={!mapsMetricsForm.connection_id || mapsMetricsSaving}>{mapsMetricsSaving ? 'Сохраняем...' : 'Сохранить факты'}</Button></div><div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7"><label className="text-xs text-amber-900">Кабинет<select value={mapsMetricsForm.connection_id} onChange={(event) => setMapsMetricsForm((current) => ({ ...current, connection_id: event.target.value }))} className="mt-1 h-9 w-full rounded-md border border-amber-200 bg-white px-2 text-sm"><option value="">Выберите</option>{adConnections.filter((item) => item.platform === 'yandex_business' || item.platform === 'yandex_maps').map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="text-xs text-amber-900">Дата<input type="date" value={mapsMetricsForm.metric_date} onChange={(event) => setMapsMetricsForm((current) => ({ ...current, metric_date: event.target.value }))} className="mt-1 h-9 w-full rounded-md border border-amber-200 bg-white px-2 text-sm" /></label>{([['card_opens', 'Открытия'], ['routes', 'Маршруты'], ['calls', 'Звонки'], ['messages', 'Сообщения'], ['website_clicks', 'Сайт']] as const).map(([field, label]) => <label key={field} className="text-xs text-amber-900">{label}<input inputMode="numeric" value={mapsMetricsForm[field]} onChange={(event) => setMapsMetricsForm((current) => ({ ...current, [field]: event.target.value }))} placeholder="0" className="mt-1 h-9 w-full rounded-md border border-amber-200 bg-white px-2 text-sm" /></label>)}</div><div className="mt-4 flex flex-wrap items-end gap-2 border-t border-amber-200 pt-3"><label className="min-w-[250px] flex-1 text-xs text-amber-900">Выгрузка Яндекс Бизнеса (XLSX, XLS, CSV)<input type="file" accept=".xlsx,.xls,.csv" onChange={(event) => { setBusinessMetricsFile(event.target.files?.[0] || null); setBusinessMetricsImportResult(null); setBusinessMetricsImportError(null); }} className="mt-1 block w-full text-xs" /></label><Button size="sm" variant="outline" onClick={importBusinessMapsMetrics} disabled={!mapsMetricsForm.connection_id || !businessMetricsFile || businessMetricsImporting}>{businessMetricsImporting ? 'Импортируем...' : 'Импортировать выгрузку'}</Button></div>{businessMetricsImportResult ? <p className="mt-2 text-xs text-green-700">{businessMetricsImportResult}</p> : null}{businessMetricsImportError ? <p className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-800">{businessMetricsImportError}</p> : null}</div>
                <p className="mt-3 text-xs text-amber-800">Нужна выгрузка? <a href="https://business.yandex.ru/" target="_blank" rel="noreferrer" className="font-medium underline">Открыть Яндекс Бизнес</a> → выберите магазин → «Статистика» → «Рекламная» → детализация по дням → скачать Excel.</p>
                {advertisingAnalytics.freshness ? <p className="mt-3 text-xs text-gray-500">Последнее обновление: {new Date(advertisingAnalytics.freshness).toLocaleString('ru-RU')}.</p> : null}
              </>
            ) : <p className="text-sm text-gray-500">Рекламная аналитика станет доступна после первой синхронизации Яндекс Директа.</p>}
          </Card>
        </section>
        </UtilityPanel> : null}

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Amplification Recommendations — Рекомендации по усилению</h2>
          <div className="space-y-3">
            <Card className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-medium text-gray-900">Трафик за 14 дней: {loading ? '...' : formatNumber.format(totalVisitors)}</p>
                  <p className="text-sm text-blue-600 mt-1">Агент проанализирует текущий срез и подготовит только предложение на согласование — без запуска рекламы или изменения бюджета.</p>
                  {latestGrowthStrategies.amplification ? <p className="mt-2 text-xs text-gray-600">Последняя задача: <b>{latestGrowthStrategies.amplification.status === 'completed' ? 'стратегия готова' : latestGrowthStrategies.amplification.status}</b>{latestGrowthStrategies.amplification.output_data?.summary ? ` — ${String(latestGrowthStrategies.amplification.output_data.summary).slice(0, 220)}…` : ''}</p> : null}
                </div>
                <Button size="sm" onClick={() => latestGrowthStrategies.amplification ? setSelectedProjectTaskId(latestGrowthStrategies.amplification.id) : createGrowthTask({ title: 'Проанализировать усиление трафика', description: 'Найти канал роста по текущим визитам, кампаниям и CRM-данным', taskType: 'traffic_amplification', runNow: true })} disabled={creating}>{creating ? 'Готовим…' : latestGrowthStrategies.amplification ? 'Открыть стратегию' : 'Подготовить стратегию'}</Button>
              </div>
            </Card>
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">App Return Layer — Стратегии возврата пользователей</h2>
          <Card className="mb-4 border-indigo-200 bg-indigo-50/60 p-4">
            <label className="block text-sm font-medium text-indigo-950">Задание для стратегии возврата (необязательно)<textarea value={returnStrategyAssignment} onChange={(event) => setReturnStrategyAssignment(event.target.value)} placeholder="Например: вернуть покупателей колец из Ялты, которые смотрели новинки в последние 30 дней; предложить промокод на первую повторную покупку." className="mt-2 min-h-20 w-full rounded-md border border-indigo-200 bg-white p-2 text-sm text-gray-900" /></label>
            <p className="mt-2 text-xs text-indigo-800">Traffic‑агент объединит это задание с аналитикой, сформирует ТЗ и передаст его AI CRM. CRM‑задача создаётся только для подготовки сегмента и материалов — отправка сообщений остаётся отдельным согласованием.</p>
          </Card>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              ['Push-уведомления', 'Персональные push о новых поступлениях', 'push'],
              ['CRM-ретаргетинг', 'Рассылки по сохраненным товарам и образам', 'crm-retargeting'],
              ['Рекламный ретаргетинг', 'Кампании в соцсетях по некупившим пользователям', 'ads-retargeting'],
            ].map(([title, description, channel]) => {
              const task = latestGrowthStrategies[`return:${channel}`];
              return <Card key={channel} className="p-4">
                <h3 className="font-medium text-gray-900">{title}</h3>
                <p className="text-sm text-gray-600 mt-1">{description}</p>
                <p className="mt-2 text-xs text-gray-500">{task ? task.status === 'completed' ? 'Стратегия подготовлена для согласования.' : `Задача: ${task.status}.` : 'Пока не запускалось.'}</p>
                {task?.output_data?.summary ? <p className="mt-2 line-clamp-3 text-xs text-gray-600">{String(task.output_data.summary)}</p> : null}
                {task?.output_data?.crm_handoff_task_id ? <Link href={`/ai-marketer/tasks/${task.output_data.crm_handoff_task_id}`} className="mt-2 inline-block text-xs font-medium text-blue-700 underline">ТЗ передано AI CRM →</Link> : null}
                <Button size="sm" variant="outline" className="mt-3" onClick={() => task ? setSelectedProjectTaskId(task.id) : createGrowthTask({ title, description, taskType: 'return_strategy', channel, runNow: true })} disabled={creating}>{creating ? 'Готовим…' : task ? 'Открыть стратегию' : 'Подготовить стратегию'}</Button>
              </Card>;
            })}
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><p className="text-gray-500">{label}</p><p className="font-medium text-xs">{value}</p></div>;
}
