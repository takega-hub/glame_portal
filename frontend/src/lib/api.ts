import axios from 'axios';
import type {
  InstagramPreviewItem,
  LookFeedPost,
  LookWithProducts,
  DirectorChatMessage,
  DirectorChatResponse,
  DirectorTask,
  DirectorKnowledge,
  DirectorSearchResult,
} from '@/types';

// Prefer same-origin calls in the browser (nginx proxies /api -> backend in prod;
// next.config.js rewrites /api -> backend in local dev).
// If you want to bypass the proxy, set NEXT_PUBLIC_API_URL to the backend origin,
// e.g. http://localhost:8000 (without trailing /api).
//
// NOTE (Windows dev):
// Default to empty string in dev to use Next.js rewrites (proxy /api -> backend:8000).
// Set NEXT_PUBLIC_API_URL=http://localhost:8000 if you want to bypass the proxy.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? '';

export const apiClient = axios.create({
  baseURL: API_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 300000, // 5 минут для долгих операций (генерация сообщений)
});

// Interceptor для автоматической подстановки токена
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('glame_access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
      delete config.headers['Content-Type'];
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Interceptor для обработки 401 ошибок и обновления токена
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem('glame_refresh_token');
        if (refreshToken) {
          const response = await axios.post(`${API_URL}/api/auth/refresh`, null, {
            params: { refresh_token: refreshToken },
            withCredentials: true,
          });
          
          const { access_token, refresh_token } = response.data;
          localStorage.setItem('glame_access_token', access_token);
          localStorage.setItem('glame_refresh_token', refresh_token);
          
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
          return apiClient(originalRequest);
        }
      } catch (refreshError) {
        localStorage.removeItem('glame_access_token');
        localStorage.removeItem('glame_refresh_token');
        localStorage.removeItem('glame_user');
        
        if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export interface ChatRequest {
  user_id?: string;
  message: string;
  city?: string;
  session_id?: string;
}

export interface StylistAvailability {
  timezone: string;
  timezone_label: string;
  working_hours: string;
  status: 'open' | 'closed';
  is_open: boolean;
  status_text: string;
  opens_at: string;
  closes_at: string;
  current_time: string;
}

export interface StylistResponse {
  persona: string;
  cjm_stage: string;
  reply: string;
  looks: Array<{
    id: string;
    name: string;
    products: Array<{
      id: string;
      name: string;
      brand: string | null;
      price: number;
      images?: string[];
      category?: string | null;
      tags?: string[];
      external_code?: string | null;
    }>;
    mood: string | null;
    style: string | null;
  }>;
  products?: Array<{
    id: string;
    name: string;
    brand: string | null;
    price: number;
    images?: string[];
    category?: string | null;
    tags?: string[];
    external_code?: string | null;
  }>;  // Отдельный список товаров для карточек
  cta: string;
  session_id: string;
}

export interface ContentGenerateRequest {
  persona?: string;
  cjm_stage?: string;
  channel?: string;
  goal?: string;
}

export interface ContentResponse {
  content: string;
  persona?: string;
  cjm_stage?: string;
}

export interface ContentPlanGenerateRequest {
  name?: string;
  start_date: string;
  end_date: string;
  timezone: string;
  channels: string[];
  frequency_rules?: Record<string, any> | null;
  persona?: string;
  goal?: string;
  campaign_context?: string;
  save?: boolean;
}

export interface ContentPlanGenerateResponse {
  plan: any;
  items: any[];
  plan_id?: string | null;
}

export interface ContentPlanDTO {
  id: string;
  name?: string | null;
  status: string;
  start_date: string;
  end_date: string;
  timezone: string;
  inputs?: Record<string, any> | null;
}

export interface ContentPlanUpdateRequest {
  name?: string;
  status?: string; // draft, active, completed, archived
  start_date?: string;
  end_date?: string;
  timezone?: string;
}

export interface ContentItemDTO {
  id: string;
  plan_id: string;
  scheduled_at: string;
  timezone: string;
  channel: string;
  content_type: string;
  topic?: string | null;
  hook?: string | null;
  cta?: string | null;
  persona?: string | null;
  cjm_stage?: string | null;
  goal?: string | null;
  spec?: Record<string, any> | null;
  generated?: Record<string, any> | null;
  generated_text?: string | null;
  status: string;
  published_at?: string | null;
}

export interface ContentItemMediaEntry {
  id: string;
  type: string;
  url: string;
  source: string;
  is_active: boolean;
  version: number;
  created_at: string;
  prompt_used?: string | null;
  provider?: string | null;
  note?: string | null;
  parent_media_id?: string | null;
  use_case?: string | null;
  content_item_id?: string | null;
  plan_id?: string | null;
  channel?: string | null;
}

export interface ContentItemCreateRequest {
  scheduled_at: string; // ISO datetime string
  timezone?: string;
  channel: string;
  content_type?: string;
  topic?: string;
  hook?: string;
  cta?: string;
  persona?: string;
  cjm_stage?: string;
  goal?: string;
  spec?: Record<string, any>;
  status?: string;
}

export interface ContentItemUpdateRequest {
  scheduled_at?: string;
  timezone?: string;
  channel?: string;
  content_type?: string;
  topic?: string;
  hook?: string;
  cta?: string;
  persona?: string;
  cjm_stage?: string;
  goal?: string;
  spec?: Record<string, any>;
  generated?: Record<string, any>;
  generated_text?: string;
  status?: string;
}

export interface GenerateItemContentRequest {
  feedback?: string;
}

export interface GenerateItemContentResponse {
  item_id: string;
  generated: Record<string, any>;
  preview?: boolean;
}

export interface ApplyGeneratedContentRequest {
  generated: Record<string, any>;
}

export interface ApplyGeneratedContentResponse {
  item_id: string;
  status: string;
  message: string;
}

export interface PublishItemRequest {
  provider?: string;
  payload?: Record<string, any> | null;
}

export interface PublishItemResponse {
  item_id: string;
  publication_id: string;
  status: string;
}

export interface YandexCalendarsResponse {
  calendars: Array<{ name: string | null; url: string | null }>;
}

export interface YandexSyncRequest {
  calendar_url?: string;
  calendar_name?: string;
  duration_minutes?: number;
}

export interface KnowledgeItem {
  text: string;
  category?: string;
  source?: string;
  metadata?: Record<string, any>;
}

export interface KnowledgeUploadRequest {
  items: KnowledgeItem[];
}

export interface KnowledgeUploadResponse {
  success: boolean;
  message: string;
  uploaded_count: number;
  document_ids: string[];
}

export interface KnowledgeBatchFileResult {
  filename: string;
  success: boolean;
  message?: string;
  uploaded_count: number;
  document_id?: string;
  document_ids: string[];
}

export interface KnowledgeBatchUploadResponse {
  total_files: number;
  succeeded: number;
  failed: number;
  results: KnowledgeBatchFileResult[];
}

export interface KnowledgeCheckDuplicatesResponse {
  duplicates: string[];
}

export interface SyncProductsToKnowledgeResponse {
  success: boolean;
  collection_name: string;
  total_products: number;
  synced: number;
  failed: number;
  errors: string[];
}

export interface ModelSettingsResponse {
  default_model: string;
  source: 'db' | 'env' | 'default';
}

export interface ModelSettingsUpdateRequest {
  default_model: string;
}

export interface AiCoreSettingsResponse {
  ai_core_runtime: 'openrouter' | 'hermes' | 'local';
  source: 'db' | 'env' | 'default';
  options: Array<'openrouter' | 'hermes' | 'local'>;
}

export interface AiCoreSettingsUpdateRequest {
  ai_core_runtime: 'openrouter' | 'hermes' | 'local';
}

export interface AiRuntimeInfoResponse {
  ai_core_runtime: 'openrouter' | 'hermes' | 'local';
  source: 'db' | 'env' | 'default';
  agent_id: string;
  model: string;
  profile?: string | null;
  label: string;
}

export interface ImageGenerationModelSettingsResponse {
  image_generation_model: string;
  source: 'db' | 'env' | 'default';
}

export interface ImageGenerationModelSettingsUpdateRequest {
  image_generation_model: string;
}

export interface AiStylistSettingsResponse {
  enabled: boolean;
  source: 'db' | 'default';
}

export interface AiStylistSettingsUpdateRequest {
  enabled: boolean;
}

export interface EmailServerSettingsResponse {
  host: string;
  port: number;
  username: string;
  from_email: string;
  from_name: string;
  use_ssl: boolean;
  use_starttls: boolean;
  password_set: boolean;
  source: 'db' | 'env' | 'default';
}

export interface EmailServerSettingsUpdateRequest {
  host: string;
  port: number;
  username?: string;
  password?: string;
  from_email: string;
  from_name: string;
  use_ssl: boolean;
  use_starttls: boolean;
}

export interface EmailServerTestResponse {
  ok: boolean;
  message: string;
}

export interface OneCSeller {
  external_id: string | null;
  name: string;
  code: string | null;
  email: string | null;
  phone: string | null;
  store: string | null;
  position: string | null;
  is_deleted: boolean;
  raw?: Record<string, any>;
}

export interface OneCSellersResponse {
  success: boolean;
  endpoint: string | null;
  count: number;
  total_loaded?: number;
  filtered_out?: number;
  filter?: string;
  sellers: OneCSeller[];
  discovered_endpoints?: string[];
  errors?: Array<Record<string, any>>;
}

export interface SellerKpiRow {
  seller_external_id: string | null;
  seller_name: string | null;
  store_id: string | null;
  store_name: string | null;
  revenue: number;
  revenue_plan: number;
  completion_percent: number | null;
  checks: number;
  checks_plan?: number | null;
  items_sold?: number;
  items_plan?: number | null;
  shifts_plan?: number | null;
  hours_plan?: number | null;
  avg_check_plan?: number | null;
  avg_item_price_plan?: number | null;
  items_per_check_plan?: number | null;
  avg_sales_per_shift_plan?: number | null;
  traffic_plan?: number | null;
  revenue_per_visitor_plan?: number | null;
  conversion_plan?: number | null;
  plan_source?: string | null;
}

export interface SellerKpiTargetRow {
  key: string;
  label: string;
  format: 'money' | 'number' | 'decimal' | 'percent';
  editable_plan: boolean;
  plan: number | null;
  fact: number | null;
  percent: number | null;
  forecast: number | null;
  forecast_percent: number | null;
  deviation: number | null;
  last_year_fact: number | null;
  lfl_deviation: number | null;
}

export interface SellerKpiInsight {
  type: string;
  severity: 'success' | 'info' | 'warning' | 'critical';
  title: string;
  text: string;
  metric_key?: string;
  store_id?: string | null;
  seller_external_id?: string | null;
}


export interface SellerKpiAssortmentGuidanceRow {
  id?: string;
  store_id?: string | null;
  store_name: string;
  month: string;
  assortment_block: string;
  current_stock: number;
  incoming: number;
  available_to_sell: number;
  share: number;
  sales_guidance: number;
  stock_after_guidance: number;
  fact_sales?: number | null;
  completion_percent?: number | null;
  personal_sales_guidance?: number | null;
  comment?: string | null;
  soft_guidance: boolean;
}

export interface SellerKpiAssortmentDiagnostic {
  type: string;
  severity: 'success' | 'info' | 'warning' | 'critical';
  title: string;
  text: string;
}

export interface SellerKpiAssortmentGuidanceResponse {
  success: boolean;
  month: string;
  store_name?: string | null;
  seller_personal_plan?: number | null;
  sum_sales_guidance: number;
  soft_guidance: boolean;
  explanation: string;
  rows: SellerKpiAssortmentGuidanceRow[];
  diagnostics: SellerKpiAssortmentDiagnostic[];
}

export interface SellerKpiTargetsResponse {
  success: boolean;
  month: string;
  scope: 'all' | 'self';
  elapsed_days: number;
  days_in_month: number;
  rows: SellerKpiTargetRow[];
  insights?: SellerKpiInsight[];
  note?: string;
}

export interface SellerKpiSnapshot {
  id: string;
  snapshot_date: string;
  month: string;
  scope: 'all' | 'self' | string;
  rows: SellerKpiTargetRow[];
  totals: SellerKpiResponse['totals'];
  stores: SellerKpiResponse['stores'];
  sellers: SellerKpiRow[];
  insights: SellerKpiInsight[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SellerKpiSnapshotsResponse {
  success: boolean;
  snapshots: SellerKpiSnapshot[];
}

export interface SellerKpiResponse {
  success: boolean;
  month: string;
  scope: 'all' | 'self';
  totals: {
    revenue: number;
    revenue_plan: number;
    completion_percent: number | null;
    checks: number;
  };
  sellers: SellerKpiRow[];
  stores: Array<{
    store_id: string | null;
    store_name: string;
    revenue: number;
    revenue_plan: number;
    completion_percent: number | null;
    checks: number;
  }>;
  seller_field_status?: string;
}

export interface SellerKpiPlanSourceDetail {
  metric_key: string;
  plan_value: number;
  source: string;
  period: string;
  store: string;
  matching_status: 'matched_confirmed' | 'missing_or_unconfirmed' | string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SellerKpiDashboardStore {
  store_id?: string | null;
  store_name: string;
  revenue: number;
  revenue_plan: number;
  revenue_plan_source?: string | null;
  revenue_plan_period?: string | null;
  revenue_plan_store?: string | null;
  revenue_plan_matching_status?: 'matched_confirmed' | 'missing_or_unconfirmed' | string | null;
  revenue_plan_source_detail?: SellerKpiPlanSourceDetail | null;
  completion_percent: number | null;
  forecast_revenue: number | null;
  forecast_percent: number | null;
  checks: number;
  items_sold: number;
  shifts_count: number;
  avg_check: number | null;
  avg_item_price: number | null;
  items_per_check: number | null;
  avg_sales_per_shift: number | null;
  sellers_count: number;
  risk_level: 'ok' | 'warning' | 'critical';
}

export interface SellerKpiDashboardMetricCell {
  fact: number | null;
  plan: number | null;
  percent: number | null;
}

export interface SellerKpiDashboardResponse {
  success: boolean;
  month: string;
  elapsed_days: number;
  days_in_month: number;
  totals: {
    revenue: number;
    revenue_plan: number;
    completion_percent: number | null;
    forecast_revenue: number | null;
    forecast_percent: number | null;
    checks: number;
    items_sold: number;
    shifts_count: number;
    avg_check: number | null;
    avg_item_price: number | null;
    items_per_check: number | null;
    avg_sales_per_shift: number | null;
  };
  stores: SellerKpiDashboardStore[];
  sellers: SellerKpiRow[];
  metric_totals: Record<string, SellerKpiDashboardMetricCell>;
  metric_matrix: Array<{ store_name: string; metrics: Record<string, SellerKpiDashboardMetricCell> }>;
  insights: SellerKpiInsight[];
  data_quality: {
    unmatched_sellers: number;
    duplicate_store_rows: number;
    seller_field_status?: string | null;
    plan_warnings?: Array<{
      code: string;
      store_name?: string | null;
      period?: string | null;
      message: string;
    }>;
  };
}

export interface SellerShift {
  id?: string;
  shift_date: string;
  seller_external_id?: string | null;
  seller_name: string;
  store_id?: string | null;
  store_name?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  note?: string | null;
}

export interface SellerShiftsResponse {
  success: boolean;
  start_date: string;
  end_date: string;
  shifts: SellerShift[];
}

export interface SellerShiftExcelImportResponse {
  success: boolean;
  dry_run: boolean;
  parsed: number;
  saved: number;
  deleted_previous?: number | null;
  period_month: string;
  store_name: string;
  stats?: { parsed_shifts?: number; skipped_marks?: number; sellers_count?: number };
  preview?: SellerShift[];
}

export interface PersonalTrainingSummaryResponse {
  found: boolean;
  seller?: { id?: string; full_name?: string | null; email?: string | null; role?: string | null } | null;
  summary: {
    level?: string | null;
    completed_steps: number;
    total_steps: number;
    progress_percent: number;
    attestation_ready: boolean;
    achievements: Array<{ code?: string; title?: string }>;
    weakest_competencies: Array<{ code?: string; label: string; percent: number }>;
    next_program_title?: string | null;
    next_action?: { label?: string; target_id?: string | null };
    recommended_training_focus: string;
    kpi_focus: string[];
    priority: 'high' | 'medium' | 'observe' | string;
    manager_recommendation: string;
  };
  programs: Array<{ program?: { title?: string }; progress?: { completed_steps: number; total_steps: number }; next_action?: { label?: string } }>;
}

export interface ImageOptimizationStatusResponse {
  status: 'idle' | 'running' | 'completed' | 'failed';
  started_at?: string | null;
  finished_at?: string | null;
  scanned_files: number;
  eligible_files: number;
  optimized_files: number;
  skipped_small_files: number;
  failed_files: number;
  scanned_bytes: number;
  optimized_original_bytes: number;
  optimized_result_bytes: number;
  saved_bytes: number;
  changed_extensions: number;
  db_rows_updated: number;
  min_original_bytes: number;
  format: 'keep' | 'jpeg' | 'webp' | string;
  quality: number;
  max_side: number;
  dirs: string[];
  errors: string[];
  message?: string | null;
}

export interface OpenRouterModelInfo {
  id: string;
  name?: string | null;
  context_length?: number | null;
  pricing?: {
    prompt?: string | null;
    completion?: string | null;
  } | null;
}

export interface OpenRouterModelsResponse {
  models: OpenRouterModelInfo[];
  cached: boolean;
  fetched_at: number;
}

export interface OpenRouterModelStat {
  model: string;
  total_cost: number;
  requests: number;
}

export interface OpenRouterDayStat {
  date: string;
  total_cost: number;
  by_model: Record<string, number>;  // модель -> стоимость за день
}

export interface OpenRouterStatsResponse {
  avg_daily: number;  // средние дневные траты ($/день)
  remaining_credits: number;  // текущий остаток аккаунта ($)
  days_left: number;  // примерное число дней (остаток делить на средний расход)
  by_model: OpenRouterModelStat[];  // разбивка по моделям
  by_day: OpenRouterDayStat[];  // данные по дням для гистограммы
}

export interface OpenRouterTodaySummary {
  date: string;
  total_cost: number;
  by_model: Record<string, number>;
}

export interface OpenRouterCreditsInfo {
  total_credits: number;
  total_usage: number;
  remaining_credits: number;
  cached: boolean;
  fetched_at: number;
}

export interface KnowledgeSearchResult {
  query: string;
  results: Array<{
    id: string;
    score: number;
    payload: {
      text: string;
      category?: string;
      source?: string;
      [key: string]: any;
    };
  }>;
  count: number;
}

export interface KnowledgeStats {
  collection_name: string;
  total_documents: number;
  vector_size: number;
  distance: string;
}

export interface DigitalModelInfo {
  id: string;
  name: string;
  source_images: string[];
  source_images_count: number;
  portfolio_images_count: number;
  portfolio_images: string[];
}

export interface ManualLookOptionsResponse {
  styles: string[];
  moods: string[];
  style_dna: string[];
  radicals: string[];
}

export interface KnowledgeDocument {
  id: string;
  filename: string;
  file_type: string;
  file_size: number | null;
  source: string | null;
  collection_name: string;
  total_items: number;
  uploaded_items: number;
  failed_items: number;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string | null;
}

export const api = {
  // Stylist API
  async chatWithStylist(request: ChatRequest): Promise<StylistResponse> {
    try {
      const response = await apiClient.post<StylistResponse>('/api/stylist/chat', request);
      return response.data;
    } catch (error: any) {
      console.error('API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async getStylistHistory(sessionId: string) {
    const response = await apiClient.get(`/api/stylist/history/${sessionId}`);
    return response.data;
  },

  async getStylistLiveStatus(): Promise<StylistAvailability> {
    const response = await apiClient.get<StylistAvailability>('/api/stylist/live-status');
    return response.data;
  },

  async getTaskChatHistory(taskId: string): Promise<any[]> {
    const response = await apiClient.get(`/api/agent-interactions/tasks/${taskId}/chat`);
    return response.data;
  },

  async getTaskLogs(taskId: string): Promise<any[]> {
    const response = await apiClient.get(`/api/agent-interactions/tasks/${taskId}/logs`);
    return response.data;
  },

  async chatWithAgent(taskId: string, message: string, model: string, meta: any): Promise<any> {
    const response = await apiClient.post(`/api/agent-interactions/tasks/${taskId}/chat`, {
      message,
      model,
      meta,
    });
    return response.data;
  },

  // Activate a version
  async activateVersion(agentType: string, promptId: string): Promise<SystemPromptVersion> {
    const response = await apiClient.post<SystemPromptVersion>(
      `/api/agent-system-prompts/${agentType}/versions/${promptId}/activate`
    );
    return response.data;
  },

  // Update a version
  async updateVersion(agentType: string, promptId: string, data: {
    name?: string;
    description?: string;
    system_prompt?: string;
    version_name?: string;
  }): Promise<SystemPromptVersion> {
    const response = await apiClient.put<SystemPromptVersion>(
      `/api/agent-system-prompts/${agentType}/versions/${promptId}`,
      data
    );
    return response.data;
  },

  // Products API
  async deleteTestProducts(): Promise<{ message: string; deleted_count: number }> {
    try {
      const response = await apiClient.delete<{ message: string; deleted_count: number }>('/api/products/test/all');
      return response.data;
    } catch (error: any) {
      console.error('Delete test products API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async getProducts(params?: {
    skip?: number;
    limit?: number;
    category?: string;
    brand?: string;
    tags?: string;
    search?: string;
    variants_only?: boolean;
  }) {
    const response = await apiClient.get('/api/products', { params });
    return response.data;
  },

  async getProductsPaged(params?: {
    skip?: number;
    limit?: number;
    category?: string;
    brand?: string;
    tags?: string;
    search?: string;
    material?: string;
    vstavka?: string;
    pokrytie?: string;
    razmer?: string;
    tip_zamka?: string;
    color?: string;
    in_stock?: boolean;
  }): Promise<{ items: any[]; total: number; skip: number; limit: number }> {
    const response = await apiClient.get('/api/products/paged', { params });
    return response.data;
  },

  async getCharacteristicsValues(): Promise<Record<string, string[]>> {
    const response = await apiClient.get('/api/products/characteristics/values');
    return response.data;
  },

  async getProduct(id: string) {
    const response = await apiClient.get(`/api/products/${id}`);
    return response.data;
  },

  async getProductVariants(id: string) {
    const response = await apiClient.get(`/api/products/${id}/variants`);
    return response.data;
  },

  async getCatalogSections(): Promise<Array<{
    id: string;
    external_id: string;
    external_code: string | null;
    name: string;
    parent_external_id: string | null;
    description: string | null;
    is_active: boolean;
    sync_status: string | null;
  }>> {
    const response = await apiClient.get('/api/catalog-sections/');
    return response.data;
  },

  async syncProductsFromXML(xmlUrl: string, params?: {
    updateExisting?: boolean;
    asyncMode?: boolean;
  }): Promise<{
    status: string;
    message: string;
    task_id?: string;
    status_url?: string;
    products?: { created?: number; updated?: number; skipped?: number; error_count?: number; deactivated?: number };
  }> {
    let normalized = (xmlUrl || '').trim();
    if (normalized && !/\.xml(\?.*)?$/i.test(normalized)) {
      const trimmed = normalized.replace(/\/+$/, '');
      if (/\/uploaded\/?$/i.test(trimmed)) {
        normalized = `${trimmed}import.xml`;
      } else {
        normalized = `${trimmed}/uploaded/import.xml`;
      }
    }
    const response = await apiClient.post('/api/products/sync-xml', null, {
      params: {
        xml_url: normalized,
        update_existing: params?.updateExisting ?? true,
        async_mode: params?.asyncMode ?? true,
      },
    });
    return response.data;
  },

  async deleteAllProducts(confirm: boolean = true) {
    const response = await apiClient.delete('/api/products/delete-all', {
      params: { confirm: confirm.toString() },
    });
    return response.data;
  },

  async getSyncProgress(taskId?: string) {
    const response = await apiClient.get('/api/products/sync-1c/status', {
      params: taskId ? { task_id: taskId } : {},
    });
    return response.data;
  },

  // Looks API
  async getLooks(params?: {
    skip?: number;
    limit?: number;
    style?: string;
    mood?: string;
    is_new?: boolean;
    digital_model?: string;
  }) {
    const response = await apiClient.get('/api/looks', { params });
    return response.data;
  },

  async getLooksFeed(params?: {
    skip?: number;
    limit?: number;
    include_drafts?: boolean;
    is_new?: boolean;
  }): Promise<LookFeedPost[]> {
    const response = await apiClient.get<LookFeedPost[]>('/api/looks/feed', { params });
    return response.data;
  },

  async toggleLookLike(lookId: string): Promise<{ liked: boolean; like_count: number }> {
    const response = await apiClient.post(`/api/looks/feed/${lookId}/like`);
    return response.data;
  },

  async toggleLookFavorite(lookId: string): Promise<{ favorited: boolean; favorite_count: number }> {
    const response = await apiClient.post(`/api/looks/feed/${lookId}/favorite`);
    return response.data;
  },

  async publishLookFeedPost(lookId: string, isPublished: boolean): Promise<LookFeedPost> {
    const response = await apiClient.patch(`/api/looks/feed/${lookId}/publish`, {
      is_published: isPublished,
    });
    return response.data;
  },

  async previewInstagramLooks(limit: number = 12): Promise<InstagramPreviewItem[]> {
    const response = await apiClient.get<InstagramPreviewItem[]>('/api/looks/instagram/preview', {
      params: { limit },
    });
    return response.data;
  },

  async importInstagramLook(request: {
    instagram_media_id: string;
    name?: string;
    product_ids?: string[];
    product_layout?: Array<Record<string, any>>;
    publish?: boolean;
  }): Promise<LookFeedPost> {
    const response = await apiClient.post<LookFeedPost>('/api/looks/instagram/import', request);
    return response.data;
  },

  async getManualLookOptions(): Promise<ManualLookOptionsResponse> {
    const response = await apiClient.get<ManualLookOptionsResponse>('/api/looks/manual/options');
    return response.data;
  },

  async generateManualLookCopy(request: {
    product_ids: string[];
    style?: string;
    mood?: string;
    style_values?: string[];
    mood_values?: string[];
    style_dna?: string;
    radical?: string;
    style_dna_values?: string[];
    radical_values?: string[];
    source_provider?: 'manual' | 'real_shoot';
    current_name?: string;
    current_description?: string;
  }): Promise<{ name: string; description: string }> {
    const response = await apiClient.post<{ name: string; description: string }>(
      '/api/looks/manual/generate-copy',
      request,
      { timeout: 180000 }
    );
    return response.data;
  },

  async createManualLook(request: {
    name?: string;
    description?: string;
    digital_model?: string;
    source_provider: 'manual' | 'real_shoot';
    style?: string;
    mood?: string;
    style_values?: string[];
    mood_values?: string[];
    style_dna?: string;
    radical?: string;
    style_dna_values?: string[];
    radical_values?: string[];
    is_new?: boolean;
    main_image_ref?: string;
    ordered_image_refs?: string[];
    product_links: Array<{
      product_id: string;
      article?: string | null;
      position?: number;
      selected_image_urls?: string[];
    }>;
    photos?: File[];
    video?: File | null;
  }): Promise<LookWithProducts> {
    const formData = new FormData();
    formData.append('source_provider', request.source_provider);
    if (request.description?.trim()) {
      formData.append('description', request.description.trim());
    }
    if (request.name?.trim()) {
      formData.append('name', request.name.trim());
    }
    if (request.digital_model?.trim()) {
      formData.append('digital_model', request.digital_model.trim());
    }
    if (request.style?.trim()) {
      formData.append('style', request.style.trim());
    }
    if (request.mood?.trim()) {
      formData.append('mood', request.mood.trim());
    }
    formData.append('style_values_json', JSON.stringify(request.style_values || []));
    formData.append('mood_values_json', JSON.stringify(request.mood_values || []));
    if (request.style_dna?.trim()) {
      formData.append('style_dna', request.style_dna.trim());
    }
    if (request.radical?.trim()) {
      formData.append('radical', request.radical.trim());
    }
    formData.append('style_dna_values_json', JSON.stringify(request.style_dna_values || []));
    formData.append('radical_values_json', JSON.stringify(request.radical_values || []));
    formData.append('is_new', request.is_new ? 'true' : 'false');
    if (request.main_image_ref) {
      formData.append('main_image_ref', request.main_image_ref);
    }
    formData.append('ordered_image_refs_json', JSON.stringify(request.ordered_image_refs || []));
    formData.append('product_links_json', JSON.stringify(request.product_links || []));
    (request.photos || []).forEach((file) => {
      formData.append('photos', file);
    });
    if (request.video) {
      formData.append('video', request.video);
    }

    const response = await apiClient.post<LookWithProducts>('/api/looks/manual', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000,
    });
    return response.data;
  },

  async updateManualLookMedia(request: {
    look_id: string;
    keep_image_urls: string[];
    main_image_ref?: string;
    ordered_image_refs?: string[];
    remove_video?: boolean;
    photos?: File[];
    video?: File | null;
  }): Promise<LookWithProducts> {
    const formData = new FormData();
    formData.append('keep_image_urls_json', JSON.stringify(request.keep_image_urls || []));
    if (request.main_image_ref) {
      formData.append('main_image_ref', request.main_image_ref);
    }
    formData.append('ordered_image_refs_json', JSON.stringify(request.ordered_image_refs || []));
    formData.append('remove_video', request.remove_video ? 'true' : 'false');
    (request.photos || []).forEach((file) => {
      formData.append('photos', file);
    });
    if (request.video) {
      formData.append('video', request.video);
    }
    const response = await apiClient.post<LookWithProducts>(`/api/looks/${request.look_id}/manual-media`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000,
    });
    return response.data;
  },

  async getDigitalModels(): Promise<DigitalModelInfo[]> {
    const response = await apiClient.get<DigitalModelInfo[]>('/api/looks/models');
    return response.data;
  },

  async deleteModelPortfolioImage(modelId: string, imageUrl: string) {
    const response = await apiClient.delete(`/api/looks/models/${encodeURIComponent(modelId)}/portfolio-image`, {
      params: { image_url: imageUrl },
    });
    return response.data;
  },

  async createDigitalModel(name: string) {
    const formData = new FormData();
    formData.append('name', name);
    const response = await apiClient.post('/api/looks/models', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  async deleteDigitalModel(modelId: string) {
    const response = await apiClient.delete(`/api/looks/models/${encodeURIComponent(modelId)}`);
    return response.data;
  },

  async uploadModelSourceImages(modelId: string, files: File[]) {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });
    const response = await apiClient.post(`/api/looks/models/${encodeURIComponent(modelId)}/source-images`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  async deleteModelSourceImage(modelId: string, filename: string) {
    const response = await apiClient.delete(`/api/looks/models/${encodeURIComponent(modelId)}/source-images/${encodeURIComponent(filename)}`);
    return response.data;
  },

  async getLook(id: string) {
    const response = await apiClient.get(`/api/looks/${id}`);
    return response.data;
  },

  async generateLook(request: {
    user_id?: string;
    session_id?: string;
    style?: string;
    mood?: string;
    persona?: string;
    user_request?: string;
    generate_image?: boolean;
    use_default_model?: boolean;
    digital_model?: string;
  }) {
    try {
      const response = await apiClient.post('/api/looks/generate', request, {
        timeout: 600000, // 10 минут для генерации образа (включая генерацию изображения)
      });
      return response.data;
    } catch (error: any) {
      // Обработка таймаутов
      if (
        error.code === 'ECONNABORTED' ||
        error.message?.includes('timeout') ||
        error.message?.includes('Network Error')
      ) {
        throw new Error('Генерация образа занимает больше времени, чем ожидалось. Пожалуйста, подождите - образ может быть создан в фоновом режиме. Проверьте список образов через несколько минут.');
      }
      if ([502, 503, 504].includes(error.response?.status)) {
        throw new Error('Генерация образа занимает больше времени, чем ожидает сервер. Образ мог быть создан в фоновом режиме. Проверьте список образов через несколько минут.');
      }
      // Обработка ошибок сервера
      if (error.response?.status === 500) {
        const detail = error.response?.data?.detail || 'Ошибка сервера при генерации образа';
        // Если генерация началась, но не завершилась в срок, это может быть таймаут на сервере
        if (detail.includes('timeout') || detail.includes('Timeout')) {
          throw new Error('Генерация образа занимает больше времени, чем ожидалось. Пожалуйста, подождите - образ может быть создан в фоновом режиме. Проверьте список образов через несколько минут.');
        }
        throw new Error(`Ошибка сервера: ${detail}`);
      }
      throw error;
    }
  },

  async generateLookImage(
    lookId: string,
    useDefaultModel: boolean = false,
    digitalModel?: string
  ): Promise<{ look_id: string; image_url: string; use_default_model: boolean }> {
    const response = await apiClient.post<{ look_id: string; image_url: string; use_default_model: boolean }>(
      `/api/looks/${lookId}/generate-image`,
      null,
      {
        params: { use_default_model: useDefaultModel, digital_model: digitalModel },
        timeout: 300000, // 5 минут для генерации изображения (увеличено из-за длительной генерации)
      }
    );
    return response.data;
  },

  async tryOnLook(lookId: string, photo: File, userId?: string) {
    const formData = new FormData();
    formData.append('photo', photo);
    if (userId) {
      formData.append('user_id', userId);
    }
    
    const response = await apiClient.post(`/api/looks/${lookId}/try-on`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 180000, // 3 минуты для примерки
    });
    return response.data;
  },

  async approveLook(lookId: string, userId?: string) {
    const response = await apiClient.post(`/api/looks/${lookId}/approve`, {}, {
      params: userId ? { user_id: userId } : {},
    });
    return response.data;
  },

  async updateLook(lookId: string, request: {
    name?: string;
    style?: string;
    mood?: string;
    style_values?: string[];
    mood_values?: string[];
    style_dna?: string;
    radical?: string;
    style_dna_values?: string[];
    radical_values?: string[];
    is_new?: boolean;
    description?: string;
    product_ids?: string[];
    product_layout?: Array<Record<string, any>>;
    regenerate_image?: boolean;
    use_default_model?: boolean;
    digital_model?: string;
  }) {
    // Если запрашивается перегенерация изображения, используем отдельный endpoint
    if (request.regenerate_image) {
      return await api.generateLookImage(lookId, request.use_default_model || false, request.digital_model);
    }
    
    const response = await apiClient.put(`/api/looks/${lookId}`, request, {
      timeout: 30000, // 30 секунд для обычного обновления
    });
    return response.data;
  },

  async deleteLook(lookId: string) {
    const response = await apiClient.delete(`/api/looks/${lookId}`);
    return response.data;
  },

  async deleteTestLooks(confirm: boolean = false) {
    const response = await apiClient.delete('/api/looks', {
      params: { confirm },
    });
    return response.data;
  },

  async setMainImage(lookId: string, imageIndex: number) {
    const response = await apiClient.put(`/api/looks/${lookId}/set-main-image`, null, {
      params: { image_index: imageIndex },
    });
    return response.data;
  },

  async deleteLookImage(lookId: string, imageIndex: number) {
    const response = await apiClient.delete(`/api/looks/${lookId}/image/${imageIndex}`);
    return response.data;
  },

  async analyzePhoto(photo: File) {
    const formData = new FormData();
    formData.append('photo', photo);
    
    const response = await apiClient.post('/api/looks/analyze-photo', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 60000, // 1 минута для анализа
    });
    return response.data;
  },

  // Look Try-On API
  async uploadUserPhoto(photo: File) {
    const formData = new FormData();
    formData.append('photo', photo);

    const response = await apiClient.post('/api/look-tryon/upload-photo', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  async analyzeUserPhoto(photo: File) {
    const formData = new FormData();
    formData.append('photo', photo);
    
    const response = await apiClient.post('/api/look-tryon/analyze', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 60000,
    });
    return response.data;
  },

  async generateLookWithTryOn(request: {
    look_id?: string;
    user_request?: string;
  }, photo: File) {
    const formData = new FormData();
    formData.append('photo', photo);

    // Добавляем параметры в FormData
    if (request.look_id) {
      formData.append('look_id', request.look_id);
    }
    if (request.user_request) {
      formData.append('user_request', request.user_request);
    }
    
    const response = await apiClient.post('/api/look-tryon/generate', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 180000, // 3 минуты
    });
    return response.data;
  },

  // Content API
  async generateContent(request: ContentGenerateRequest): Promise<ContentResponse> {
    try {
      const response = await apiClient.post<ContentResponse>('/api/content/generate', request);
      return response.data;
    } catch (error: any) {
      console.error('Content API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async generateContentPlan(request: ContentPlanGenerateRequest): Promise<ContentPlanGenerateResponse> {
    try {
      // Генерация плана через LLM может занимать время, увеличиваем таймаут до 5 минут
      const response = await apiClient.post<ContentPlanGenerateResponse>(
        '/api/content/plans/generate',
        request,
        {
          timeout: 300000, // 5 минут
        }
      );
      return response.data;
    } catch (error: any) {
      console.error('Content Plan Generation API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      } else if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        throw new Error('Превышено время ожидания. Генерация плана занимает слишком много времени. Попробуйте уменьшить период или количество каналов.');
      } else if (error.code === 'ECONNRESET' || error.message?.includes('socket hang up')) {
        throw new Error('Соединение с backend разорвано. Убедитесь, что backend запущен и доступен на http://localhost:8000');
      }
      throw error;
    }
  },

  async getContentPlan(planId: string): Promise<ContentPlanDTO> {
    const response = await apiClient.get<ContentPlanDTO>(`/api/content/plans/${planId}`);
    return response.data;
  },

  async updateContentPlan(planId: string, request: ContentPlanUpdateRequest): Promise<ContentPlanDTO> {
    const response = await apiClient.put<ContentPlanDTO>(`/api/content/plans/${planId}`, request);
    return response.data;
  },

  async listContentPlans(params?: { 
    skip?: number; 
    limit?: number; 
    status?: string;
    search?: string;
    start_date_from?: string;
    start_date_to?: string;
  }): Promise<ContentPlanDTO[]> {
    const response = await apiClient.get<ContentPlanDTO[]>('/api/content/plans', { params });
    return response.data;
  },

  async deleteContentPlan(planId: string): Promise<{ message: string; plan_id: string }> {
    const response = await apiClient.delete<{ message: string; plan_id: string }>(`/api/content/plans/${planId}`);
    return response.data;
  },

  async getContentPlanItems(
    planId: string,
    params?: {
      channel?: string;
      status?: string;
      search?: string;
      scheduled_from?: string;
      scheduled_to?: string;
    }
  ): Promise<ContentItemDTO[]> {
    const response = await apiClient.get<ContentItemDTO[]>(`/api/content/plans/${planId}/items`, { params });
    return response.data;
  },

  async createContentItem(planId: string, request: ContentItemCreateRequest): Promise<ContentItemDTO> {
    const response = await apiClient.post<ContentItemDTO>(`/api/content/plans/${planId}/items`, request);
    return response.data;
  },

  async updateContentItem(planId: string, itemId: string, request: ContentItemUpdateRequest): Promise<ContentItemDTO> {
    const response = await apiClient.put<ContentItemDTO>(`/api/content/plans/${planId}/items/${itemId}`, request);
    return response.data;
  },

  async deleteContentItem(planId: string, itemId: string): Promise<{ message: string; item_id: string }> {
    const response = await apiClient.delete<{ message: string; item_id: string }>(`/api/content/plans/${planId}/items/${itemId}`);
    return response.data;
  },

  async bulkUpdateItemsStatus(
    planId: string,
    itemIds: string[],
    status: string
  ): Promise<{ message: string; updated_count: number; status: string }> {
    const response = await apiClient.put<{ message: string; updated_count: number; status: string }>(
      `/api/content/plans/${planId}/items/bulk/status`,
      { item_ids: itemIds, status }
    );
    return response.data;
  },

  async bulkDeleteItems(
    planId: string,
    itemIds: string[]
  ): Promise<{ message: string; deleted_count: number }> {
    const response = await apiClient.post<{ message: string; deleted_count: number }>(
      `/api/content/plans/${planId}/items/bulk/delete`,
      { item_ids: itemIds }
    );
    return response.data;
  },

  async bulkGenerateContent(
    planId: string,
    itemIds: string[],
    feedback?: string
  ): Promise<{ message: string; generated_count: number; failed_count: number; errors?: Array<{ item_id: string; error: string }> }> {
    const response = await apiClient.post<{ message: string; generated_count: number; failed_count: number; errors?: Array<{ item_id: string; error: string }> }>(
      `/api/content/plans/${planId}/items/bulk/generate`,
      { item_ids: itemIds, feedback }
    );
    return response.data;
  },

  async getCalendarItems(params: {
    start: string;
    end: string;
    channel?: string;
    status?: string;
    plan_id?: string;
  }): Promise<ContentItemDTO[]> {
    const response = await apiClient.get<ContentItemDTO[]>('/api/content/calendar', { params });
    return response.data;
  },

  async generateContentForItem(itemId: string, feedback?: string): Promise<GenerateItemContentResponse> {
    try {
      // Если feedback не указан, передаем пустой объект вместо null
      const requestBody = feedback ? { feedback } : {};
      const response = await apiClient.post<GenerateItemContentResponse>(
        `/api/content/items/${itemId}/generate`,
        requestBody,
        {
          timeout: 120000, // 2 минуты для генерации контента
        }
      );
      return response.data;
    } catch (error: any) {
      console.error('Generate Content For Item API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async applyGeneratedContent(itemId: string, generated: Record<string, any>): Promise<ApplyGeneratedContentResponse> {
    const response = await apiClient.post<ApplyGeneratedContentResponse>(
      `/api/content/items/${itemId}/apply`,
      { generated }
    );
    return response.data;
  },

  async publishContentItem(itemId: string, request?: PublishItemRequest): Promise<PublishItemResponse> {
    const response = await apiClient.post<PublishItemResponse>(`/api/content/items/${itemId}/publish`, request || {});
    return response.data;
  },

  async getItemMedia(itemId: string): Promise<{
    item_id: string;
    media: ContentItemMediaEntry[];
    active_media_id?: string | null;
  }> {
    const response = await apiClient.get(`/api/content/items/${itemId}/media`);
    return response.data;
  },

  async generateItemPhoto(
    itemId: string,
    revisionDescription?: string,
    options?: {
      no_text_on_image?: boolean;
      style_intensity?: 'classic' | 'bold' | 'edgy';
    }
  ): Promise<{
    item_id: string;
    media: ContentItemMediaEntry;
    active_media_id?: string | null;
    message: string;
  }> {
    const response = await apiClient.post(`/api/content/items/${itemId}/generate-photo`, {
      revision_description: revisionDescription || undefined,
      no_text_on_image: options?.no_text_on_image ?? true,
      style_intensity: options?.style_intensity ?? 'classic',
    });
    return response.data;
  },

  async uploadItemMedia(itemId: string, file: File, note?: string): Promise<{
    item_id: string;
    media: ContentItemMediaEntry;
    active_media_id?: string | null;
    message: string;
  }> {
    const form = new FormData();
    form.append('file', file);
    if (note?.trim()) {
      form.append('note', note.trim());
    }
    const response = await apiClient.post(`/api/content/items/${itemId}/media/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  async setActiveItemMedia(itemId: string, mediaId: string): Promise<{
    item_id: string;
    media: ContentItemMediaEntry;
    active_media_id?: string | null;
    message: string;
  }> {
    const response = await apiClient.post(`/api/content/items/${itemId}/media/${mediaId}/set-active`);
    return response.data;
  },

  async deleteItemMedia(itemId: string, mediaId: string): Promise<{
    item_id: string;
    deleted: boolean;
    active_media_id?: string | null;
    message: string;
  }> {
    const response = await apiClient.delete(`/api/content/items/${itemId}/media/${mediaId}`);
    return response.data;
  },

  async regenerateItemMedia(
    itemId: string,
    mediaId: string,
    revisionDescription?: string,
    options?: {
      no_text_on_image?: boolean;
      style_intensity?: 'classic' | 'bold' | 'edgy';
    }
  ): Promise<{
    item_id: string;
    media: ContentItemMediaEntry;
    active_media_id?: string | null;
    message: string;
  }> {
    const response = await apiClient.post(`/api/content/items/${itemId}/media/${mediaId}/regenerate`, {
      revision_description: revisionDescription || undefined,
      no_text_on_image: options?.no_text_on_image ?? true,
      style_intensity: options?.style_intensity ?? 'classic',
    });
    return response.data;
  },

  getContentPlanIcsUrl(planId: string) {
    return `${API_URL}/api/content/plans/${planId}/export/ics`;
  },

  async getYandexCalendars(): Promise<YandexCalendarsResponse> {
    const response = await apiClient.get<YandexCalendarsResponse>('/api/content/yandex/calendars');
    return response.data;
  },

  async syncPlanToYandex(planId: string, request: YandexSyncRequest): Promise<any> {
    const response = await apiClient.post(`/api/content/plans/${planId}/sync/yandex`, request);
    return response.data;
  },

  // Knowledge Base API
  async uploadKnowledge(request: KnowledgeUploadRequest, collectionName: string = 'brand_philosophy'): Promise<KnowledgeUploadResponse> {
    try {
      const response = await apiClient.post<KnowledgeUploadResponse>('/api/knowledge/upload', request, {
        params: { collection_name: collectionName },
      });
      return response.data;
    } catch (error: any) {
      console.error('Knowledge Upload API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async checkKnowledgeDuplicates(collectionName: string, filenames: string[]): Promise<KnowledgeCheckDuplicatesResponse> {
    if (filenames.length === 0) {
      return { duplicates: [] };
    }
    const response = await apiClient.get<KnowledgeCheckDuplicatesResponse>(
      '/api/knowledge/documents/check-duplicates',
      { params: { collection_name: collectionName, filenames: filenames.join(',') } }
    );
    return response.data;
  },

  async uploadKnowledgeFromFile(
    file: File,
    collectionName: string = 'brand_philosophy',
    replaceDuplicates: boolean = false
  ): Promise<KnowledgeUploadResponse> {
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      console.log(`Uploading file: ${file.name}, size: ${file.size} bytes`);
      
      const response = await apiClient.post<KnowledgeUploadResponse>(
        '/api/knowledge/upload/file',
        formData,
        {
          params: { collection_name: collectionName, replace_duplicates: replaceDuplicates },
          headers: {
            'Content-Type': 'multipart/form-data',
          },
          timeout: 300000, // 5 минут для больших PDF файлов с AI обработкой
          onUploadProgress: (progressEvent) => {
            if (progressEvent.total) {
              const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
              console.log(`Upload progress: ${percentCompleted}%`);
            }
          },
        }
      );
      console.log('Upload completed:', response.data);
      return response.data;
    } catch (error: any) {
      console.error('Knowledge File Upload API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async uploadKnowledgeBatch(
    files: File[],
    collectionName: string = 'brand_philosophy',
    replaceDuplicates: boolean = false
  ): Promise<KnowledgeBatchUploadResponse> {
    if (files.length === 0) {
      return { total_files: 0, succeeded: 0, failed: 0, results: [] };
    }
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    const response = await apiClient.post<KnowledgeBatchUploadResponse>(
      '/api/knowledge/upload/batch',
      formData,
      {
        params: { collection_name: collectionName, replace_duplicates: replaceDuplicates },
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 600000, // 10 минут для пакетной загрузки
        onUploadProgress: (e) => {
          if (e.total) console.log(`Batch upload: ${Math.round((e.loaded / e.total) * 100)}%`);
        },
      }
    );
    return response.data;
  },

  async searchKnowledge(query: string, limit: number = 5, scoreThreshold: number = 0.5, collectionName: string = 'brand_philosophy'): Promise<KnowledgeSearchResult> {
    try {
      const response = await apiClient.get<KnowledgeSearchResult>('/api/knowledge/search', {
        params: {
          query,
          limit,
          score_threshold: scoreThreshold,
          collection_name: collectionName,
        },
      });
      return response.data;
    } catch (error: any) {
      console.error('Knowledge Search API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async getKnowledgeStats(collectionName: string = 'brand_philosophy'): Promise<KnowledgeStats> {
    try {
      const response = await apiClient.get<KnowledgeStats>('/api/knowledge/stats', {
        params: { collection_name: collectionName },
      });
      return response.data;
    } catch (error: any) {
      console.error('Knowledge Stats API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async getKnowledgeDocuments(skip: number = 0, limit: number = 100, status?: string, collectionName?: string): Promise<KnowledgeDocument[]> {
    try {
      const params: any = { skip, limit };
      if (status) params.status = status;
      if (collectionName) params.collection_name = collectionName;
      
      const response = await apiClient.get<KnowledgeDocument[]>('/api/knowledge/documents', { params });
      return response.data;
    } catch (error: any) {
      console.error('Knowledge Documents API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async getKnowledgeDocument(documentId: string): Promise<KnowledgeDocument> {
    try {
      const response = await apiClient.get<KnowledgeDocument>(`/api/knowledge/documents/${documentId}`);
      return response.data;
    } catch (error: any) {
      console.error('Knowledge Document API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async changeKnowledgeDocumentCollection(
    documentId: string,
    collectionName: string
  ): Promise<KnowledgeDocument> {
    const response = await apiClient.patch<KnowledgeDocument>(
      `/api/knowledge/documents/${documentId}/collection`,
      { collection_name: collectionName }
    );
    return response.data;
  },

  async deleteKnowledgeDocument(documentId: string): Promise<{ success: boolean; message: string }> {
    try {
      const response = await apiClient.delete<{ success: boolean; message: string }>(`/api/knowledge/documents/${documentId}`);
      return response.data;
    } catch (error: any) {
      console.error('Delete Knowledge Document API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async clearKnowledgeCollection(collectionName: string): Promise<{ success: boolean; collection_name: string; deleted_history_records: number }> {
    try {
      const response = await apiClient.delete(`/api/knowledge/collections/${collectionName}/clear`);
      return response.data;
    } catch (error: any) {
      console.error('Clear Knowledge Collection API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async syncProductsToKnowledge(params?: {
    collection_name?: string;
    only_active?: boolean;
    limit?: number;
  }): Promise<SyncProductsToKnowledgeResponse> {
    const response = await apiClient.post<SyncProductsToKnowledgeResponse>(
      '/api/knowledge/sync/products',
      {},
      {
        params,
        timeout: 300000, // 5 минут (embeddings + upsert могут быть медленными)
      }
    );
    return response.data;
  },

  async getModelSettings(): Promise<ModelSettingsResponse> {
    const response = await apiClient.get<ModelSettingsResponse>('/api/settings/model');
    return response.data;
  },

  async setModelSettings(request: ModelSettingsUpdateRequest): Promise<ModelSettingsResponse> {
    const response = await apiClient.put<ModelSettingsResponse>('/api/settings/model', request);
    return response.data;
  },

  async getAiCoreSettings(): Promise<AiCoreSettingsResponse> {
    const response = await apiClient.get<AiCoreSettingsResponse>('/api/settings/ai-core');
    return response.data;
  },

  async setAiCoreSettings(request: AiCoreSettingsUpdateRequest): Promise<AiCoreSettingsResponse> {
    const response = await apiClient.put<AiCoreSettingsResponse>('/api/settings/ai-core', request);
    return response.data;
  },

  async getEmailServerSettings(): Promise<EmailServerSettingsResponse> {
    const response = await apiClient.get<EmailServerSettingsResponse>('/api/settings/email-server');
    return response.data;
  },

  async setEmailServerSettings(request: EmailServerSettingsUpdateRequest): Promise<EmailServerSettingsResponse> {
    const response = await apiClient.put<EmailServerSettingsResponse>('/api/settings/email-server', request);
    return response.data;
  },

  async testEmailServerSettings(toEmail: string): Promise<EmailServerTestResponse> {
    const response = await apiClient.post<EmailServerTestResponse>('/api/settings/email-server/test', {
      to_email: toEmail,
    });
    return response.data;
  },

  async getAiRuntimeInfo(agentId: string): Promise<AiRuntimeInfoResponse> {
    const response = await apiClient.get<AiRuntimeInfoResponse>(`/api/settings/ai-runtime/${encodeURIComponent(agentId)}`);
    return response.data;
  },

  async getOpenRouterModels(params?: { force_refresh?: boolean }): Promise<OpenRouterModelsResponse> {
    const response = await apiClient.get<OpenRouterModelsResponse>('/api/settings/openrouter/models', { params });
    return response.data;
  },

  async getOpenRouterImageModels(params?: { force_refresh?: boolean }): Promise<OpenRouterModelsResponse> {
    const response = await apiClient.get<OpenRouterModelsResponse>('/api/settings/openrouter/image-models', { params });
    return response.data;
  },

  async getOpenRouterStats(params?: { period?: 'today' | 'yesterday' | 'week' | 'month' }): Promise<OpenRouterStatsResponse> {
    const response = await apiClient.get<OpenRouterStatsResponse>('/api/settings/openrouter/stats', { params });
    return response.data;
  },

  async getOpenRouterToday(): Promise<OpenRouterTodaySummary> {
    const response = await apiClient.get<OpenRouterTodaySummary>('/api/settings/openrouter/today');
    return response.data;
  },

  async getOpenRouterCredits(): Promise<OpenRouterCreditsInfo> {
    const response = await apiClient.get<OpenRouterCreditsInfo>('/api/settings/openrouter/credits');
    return response.data;
  },

  async getImageGenerationModelSettings(): Promise<ImageGenerationModelSettingsResponse> {
    const response = await apiClient.get<ImageGenerationModelSettingsResponse>('/api/settings/image-generation-model');
    return response.data;
  },

  async setImageGenerationModelSettings(request: ImageGenerationModelSettingsUpdateRequest): Promise<ImageGenerationModelSettingsResponse> {
    const response = await apiClient.put<ImageGenerationModelSettingsResponse>('/api/settings/image-generation-model', request);
    return response.data;
  },

  async getImageOptimizationStatus(): Promise<ImageOptimizationStatusResponse> {
    const response = await apiClient.get<ImageOptimizationStatusResponse>('/api/settings/image-optimization/status');
    return response.data;
  },

  async runImageOptimization(): Promise<ImageOptimizationStatusResponse> {
    const response = await apiClient.post<ImageOptimizationStatusResponse>('/api/settings/image-optimization/run');
    return response.data;
  },

  async changePassword(currentPassword: string | null, newPassword: string): Promise<{ message: string }> {
    const response = await apiClient.post<{ message: string }>('/api/auth/change-password', {
      current_password: currentPassword ?? undefined,
      new_password: newPassword,
    });
    return response.data;
  },

  async getOneCSellers(params?: { limit?: number }): Promise<OneCSellersResponse> {
    const response = await apiClient.get<OneCSellersResponse>('/api/admin/1c/sellers', { params });
    return response.data;
  },

  async getSellerKpi(params?: { month?: string; store_name?: string }): Promise<SellerKpiResponse> {
    const response = await apiClient.get<SellerKpiResponse>('/api/admin/1c/sellers/kpi', { params });
    return response.data;
  },

  async getSellerKpiDashboard(params?: { month?: string }): Promise<SellerKpiDashboardResponse> {
    const response = await apiClient.get<SellerKpiDashboardResponse>('/api/admin/1c/sellers/kpi/dashboard', { params });
    return response.data;
  },

  async getSellerKpiTargets(params?: { month?: string; store_name?: string }): Promise<SellerKpiTargetsResponse> {
    const response = await apiClient.get<SellerKpiTargetsResponse>('/api/admin/1c/sellers/kpi/targets', { params });
    return response.data;
  },

  async saveSellerKpiTargets(payload: { month: string; store_name?: string; metrics: Record<string, number | string | null> }): Promise<{ success: boolean; saved: number; month: string }> {
    const response = await apiClient.put<{ success: boolean; saved: number; month: string }>('/api/admin/1c/sellers/kpi/targets', payload);
    return response.data;
  },


  async getSellerKpiAssortmentGuidance(params?: { month?: string; store_name?: string; seller_personal_plan?: number | null }): Promise<SellerKpiAssortmentGuidanceResponse> {
    const response = await apiClient.get<SellerKpiAssortmentGuidanceResponse>('/api/admin/1c/sellers/kpi/assortment-guidance', { params });
    return response.data;
  },

  async saveSellerKpiAssortmentGuidance(payload: { month: string; store_name: string; rows: SellerKpiAssortmentGuidanceRow[]; store_revenue_plan?: number | null }): Promise<{ success: boolean; saved: number; month: string; store_name: string }> {
    const response = await apiClient.put<{ success: boolean; saved: number; month: string; store_name: string }>('/api/admin/1c/sellers/kpi/assortment-guidance', payload);
    return response.data;
  },

  async getSellerKpiPlanMonths(params?: { limit?: number }): Promise<{ success: boolean; months: Array<{ month: string; metrics_count: number; updated_at?: string | null }> }> {
    const response = await apiClient.get<{ success: boolean; months: Array<{ month: string; metrics_count: number; updated_at?: string | null }> }>('/api/admin/1c/sellers/plan-months', { params });
    return response.data;
  },

  async getSellerKpiSnapshots(params?: { month?: string; limit?: number }): Promise<SellerKpiSnapshotsResponse> {
    const response = await apiClient.get<SellerKpiSnapshotsResponse>('/api/admin/1c/sellers/kpi/snapshots', { params });
    return response.data;
  },

  async getSellerShifts(params?: { start_date?: string; end_date?: string; store_name?: string }): Promise<SellerShiftsResponse> {
    const response = await apiClient.get<SellerShiftsResponse>('/api/admin/1c/sellers/shifts', { params });
    return response.data;
  },

  async importSellerShiftsExcel(payload: { filename: string; content_base64: string; store_name: string; dry_run?: boolean; replace_existing?: boolean }): Promise<SellerShiftExcelImportResponse> {
    const response = await apiClient.post<SellerShiftExcelImportResponse>('/api/admin/1c/sellers/shifts/import-excel', payload);
    return response.data;
  },

  async getSellerTrainingSummary(payload: { seller_external_id?: string | null; seller_name?: string | null; store_name?: string | null; kpi?: Record<string, any> }): Promise<PersonalTrainingSummaryResponse> {
    const response = await apiClient.post<PersonalTrainingSummaryResponse>('/api/admin/consultant-training/personal-summary', payload);
    return response.data;
  },

  async saveSellerShift(payload: SellerShift): Promise<{ success: boolean }> {
    const response = await apiClient.post<{ success: boolean }>('/api/admin/1c/sellers/shifts', payload);
    return response.data;
  },

  async deleteSellerShift(shiftId: string): Promise<{ success: boolean }> {
    const response = await apiClient.delete<{ success: boolean }>(`/api/admin/1c/sellers/shifts/${shiftId}`);
    return response.data;
  },

  async replaceKnowledgeDocument(documentId: string, file: File, collectionName?: string): Promise<KnowledgeUploadResponse> {
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await apiClient.post<KnowledgeUploadResponse>(
        `/api/knowledge/documents/${documentId}/replace`,
        formData,
        {
          params: collectionName ? { collection_name: collectionName } : undefined,
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );
      return response.data;
    } catch (error: any) {
      console.error('Replace Knowledge Document API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  // 1C Sync API
  async syncFromFile(file: File, updateExisting: boolean = true, deactivateMissing: boolean = false): Promise<OneCSyncResponse> {
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await apiClient.post<OneCSyncResponse>(
        '/api/1c/sync/file',
        formData,
        {
          params: {
            update_existing: updateExisting,
            deactivate_missing: deactivateMissing,
          },
          headers: {
            'Content-Type': 'multipart/form-data',
          },
          timeout: 300000, // 5 минут для больших файлов
          onUploadProgress: (progressEvent) => {
            if (progressEvent.total) {
              const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
              console.log(`Upload progress: ${percentCompleted}%`);
            }
          },
        }
      );
      return response.data;
    } catch (error: any) {
      console.error('1C Sync File Upload API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async getSyncStatus(): Promise<OneCSyncStatus> {
    try {
      const response = await apiClient.get<OneCSyncStatus>('/api/1c/sync/status');
      return response.data;
    } catch (error: any) {
      console.error('1C Sync Status API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async syncFromYml(
    ymlUrl: string,
    updateExisting: boolean = true,
    deactivateMissing: boolean = false
  ): Promise<OneCSyncResponse> {
    try {
      const response = await apiClient.post<OneCSyncResponse>(
        '/api/1c/sync/yml',
        {
          yml_url: ymlUrl,
          update_existing: updateExisting,
          deactivate_missing: deactivateMissing,
        },
        {
          timeout: 300000, // 5 минут для больших файлов
        }
      );
      return response.data;
    } catch (error: any) {
      console.error('YML Sync API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  // Product Description API (SEO-оптимизированные описания товаров)
  async getProductsWithoutDescription(params?: {
    skip?: number;
    limit?: number;
    min_length?: number;
  }): Promise<Array<{
    id: string;
    name: string;
    brand: string | null;
    category: string | null;
    price: number;
    tags: string[];
    has_description: boolean;
    description_length: number;
    external_code: string | null;
  }>> {
    try {
      const response = await apiClient.get('/api/content/products/without-description', { params });
      return response.data;
    } catch (error: any) {
      console.error('Get Products Without Description API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async searchProductByCodeOrName(query: string, limit?: number): Promise<Array<{
    id: string;
    name: string;
    brand: string | null;
    category: string | null;
    price: number;
    tags: string[];
    has_description: boolean;
    description_length: number;
    external_code: string | null;
  }>> {
    try {
      console.log('API: Searching products with query:', query, 'limit:', limit || 10);
      const response = await apiClient.get('/api/content/products/search', {
        params: { query: query.trim(), limit: limit || 10 },
      });
      console.log('API: Search response:', response.data);
      return response.data || [];
    } catch (error: any) {
      console.error('Search Product By Code Or Name API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
        console.error('Response headers:', error.response.headers);
      }
      throw error;
    }
  },

  async generateProductDescription(request: {
    product_id: string;
    rewrite_existing?: boolean;
    seo_keywords?: string[];
    target_length?: 'short' | 'medium' | 'long';
  }): Promise<{
    product_id: string;
    product_name: string;
    old_description: string | null;
    new_description: string;
    length: number;
    seo_keywords_used: string[];
    rewritten: boolean;
  }> {
    try {
      const response = await apiClient.post('/api/content/products/generate-description', request, {
        timeout: 120000, // 2 минуты для генерации описания
      });
      return response.data;
    } catch (error: any) {
      console.error('Generate Product Description API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async applyProductDescription(productId: string, description: string): Promise<{
    product_id: string;
    product_name: string;
    message: string;
  }> {
    try {
      const response = await apiClient.post(`/api/content/products/${productId}/apply-description`, {
        description,
      });
      return response.data;
    } catch (error: any) {
      console.error('Apply Product Description API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async batchGenerateDescriptions(request: {
    product_ids: string[];
    rewrite_existing?: boolean;
    target_length?: 'short' | 'medium' | 'long';
  }): Promise<{
    total: number;
    success: number;
    errors: number;
    results: Array<{
      product_id: string;
      product_name: string;
      status: string;
      description_length?: number;
      rewritten?: boolean;
      reason?: string;
    }>;
    errors_detail: Array<{
      product_id: string;
      error: string;
    }>;
  }> {
    try {
      const response = await apiClient.post('/api/content/products/batch-generate-descriptions', request.product_ids, {
        params: {
          rewrite_existing: request.rewrite_existing || false,
          target_length: request.target_length || 'medium',
        },
        timeout: 600000, // 10 минут для массовой генерации
      });
      return response.data;
    } catch (error: any) {
      console.error('Batch Generate Descriptions API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },

  async generateHermesImage(request: {
    prompt: string;
    reference_image_urls?: string[];
    model_profile?: string;
    provider?: 'auto' | 'openrouter' | 'platform' | 'comfyui';
    variants?: number;
    variant_options?: Array<{
      provider?: 'auto' | 'openrouter' | 'platform' | 'comfyui';
      prompt?: string;
      style_intensity?: 'classic' | 'bold' | 'edgy';
      model_profile?: string;
      reference_image_urls?: string[];
      aspect_ratio?: string;
      negative_prompt?: string;
    }>;
    asset_group?: string;
    filename_prefix?: string;
    aspect_ratio?: string;
    negative_prompt?: string;
    no_text_on_image?: boolean;
    allow_text_only_fallback?: boolean;
  }): Promise<{
    results: Array<{
      url: string;
      prompt_used: string;
      provider: string;
      model?: string | null;
      reference_images_count: number;
      model_reference_images_count: number;
      reference_image_urls: string[];
      model_reference_image_urls: string[];
      asset_group: string;
      attempts: Array<Record<string, any>>;
      variant_index: number;
      status: string;
      error?: string | null;
    }>;
    best_result?: any;
    requested_variants: number;
    succeeded: number;
    failed: number;
  }> {
    const response = await apiClient.post('/api/content/image-generation/generate', request, {
      timeout: 600000,
    });
    return response.data;
  },

  async processJewelryPhoto(
    files: File[],
    article: string,
    signal?: AbortSignal,
    revisionDescription?: string,
    promptOverride?: string
  ): Promise<{ urls: string[]; provider?: { runtime?: string; model?: string; profile?: string; quality?: string }; prompt_used?: string | null }> {
    const form = new FormData();
    form.append('article', article.trim());
    if (revisionDescription?.trim()) {
      form.append('revision_description', revisionDescription.trim());
    }
    if (promptOverride?.trim()) {
      form.append('prompt_override', promptOverride.trim());
    }
    if (files.length === 1) {
      form.append('file', files[0]);
    } else {
      files.forEach((f) => form.append('files', f));
    }
    const response = await apiClient.post<{ urls: string[]; provider?: { runtime?: string; model?: string; profile?: string; quality?: string }; prompt_used?: string | null }>(
      '/api/content/jewelry-photo/process',
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 360000,
        signal,
      }
    );
    return response.data;
  },

  async applyJewelryPhotoToProduct(
    article: string,
    imageUrls: string[]
  ): Promise<{ success: boolean; product_id: string; images_count: number }> {
    const response = await apiClient.post<{ success: boolean; product_id: string; images_count: number }>(
      '/api/content/jewelry-photo/apply',
      { article: article.trim(), image_urls: imageUrls }
    );
    return response.data;
  },

  async getJewelryPhotoHistory(): Promise<{ items: Array<{ article: string; urls: string[]; updated_at: string }> }> {
    const response = await apiClient.get<{ items: Array<{ article: string; urls: string[]; updated_at: string }> }>(
      '/api/content/jewelry-photo/history'
    );
    return response.data;
  },

  async deleteJewelryPhotoFile(url: string): Promise<{ deleted: boolean }> {
    const response = await apiClient.delete<{ deleted: boolean }>('/api/content/jewelry-photo/file', {
      params: { url },
    });
    return response.data;
  },

  // Analytics API
  async getDashboardMetrics(days: number = 30): Promise<any> {
    const response = await apiClient.get('/api/analytics/dashboard', {
      params: { days }
    });
    return response.data;
  },

  async getAppAdminKpiDashboard(params?: { days?: number; start_date?: string; end_date?: string }): Promise<any> {
    const response = await apiClient.get('/api/admin/app/kpi/dashboard', {
      params: {
        days: params?.days,
        start_date: params?.start_date,
        end_date: params?.end_date,
      },
    });
    return response.data;
  },

  async getAiStylistSettings(): Promise<AiStylistSettingsResponse> {
    const response = await apiClient.get<AiStylistSettingsResponse>('/api/settings/ai-stylist');
    return response.data;
  },

  async setAiStylistSettings(request: AiStylistSettingsUpdateRequest): Promise<AiStylistSettingsResponse> {
    const response = await apiClient.put<AiStylistSettingsResponse>('/api/settings/ai-stylist', request);
    return response.data;
  },

  async uploadAppAdminMedia(
    kind: 'banner' | 'lookbook' | 'promotion' | 'news' | 'store' | 'home_slide' | 'certificate_texture',
    file: File
  ): Promise<{ url: string }> {
    const form = new FormData();
    form.append('kind', kind);
    form.append('file', file);
    const response = await apiClient.post<{ url: string }>('/api/admin/app/media/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  async listGiftCertificateTextures(): Promise<any[]> {
    const response = await apiClient.get<any[]>('/api/admin/app/gift-certificate-textures');
    return response.data;
  },

  async listAppBanners(includeInactive: boolean = false): Promise<any[]> {
    const response = await apiClient.get<any[]>('/api/admin/app/banners', {
      params: { include_inactive: includeInactive },
    });
    return response.data;
  },
  async createAppBanner(payload: any): Promise<{ id: string }> {
    const response = await apiClient.post<{ id: string }>('/api/admin/app/banners', payload);
    return response.data;
  },
  async updateAppBanner(id: string, payload: any): Promise<{ success: boolean }> {
    const response = await apiClient.put<{ success: boolean }>(`/api/admin/app/banners/${id}`, payload);
    return response.data;
  },
  async deleteAppBanner(id: string): Promise<{ deleted: boolean }> {
    const response = await apiClient.delete<{ deleted: boolean }>(`/api/admin/app/banners/${id}`);
    return response.data;
  },

  async listAppHomeSlides(includeInactive: boolean = true, blockKey: string = 'style_inside'): Promise<any[]> {
    const response = await apiClient.get<any[]>('/api/admin/app/home-slides', {
      params: { include_inactive: includeInactive, block_key: blockKey },
    });
    return response.data;
  },
  async createAppHomeSlide(payload: any): Promise<{ id: string }> {
    const response = await apiClient.post<{ id: string }>('/api/admin/app/home-slides', payload);
    return response.data;
  },
  async updateAppHomeSlide(id: string, payload: any): Promise<{ success: boolean }> {
    const response = await apiClient.put<{ success: boolean }>(`/api/admin/app/home-slides/${id}`, payload);
    return response.data;
  },
  async deleteAppHomeSlide(id: string): Promise<{ deleted: boolean }> {
    const response = await apiClient.delete<{ deleted: boolean }>(`/api/admin/app/home-slides/${id}`);
    return response.data;
  },

  async listAppStores(includeInactive: boolean = true): Promise<any[]> {
    const response = await apiClient.get<any[]>('/api/admin/app/stores', {
      params: { include_inactive: includeInactive },
    });
    return response.data;
  },
  async createAppStore(payload: any): Promise<{ id: string }> {
    const response = await apiClient.post<{ id: string }>('/api/admin/app/stores', payload);
    return response.data;
  },
  async updateAppStore(id: string, payload: any): Promise<{ success: boolean }> {
    const response = await apiClient.put<{ success: boolean }>(`/api/admin/app/stores/${id}`, payload);
    return response.data;
  },
  async deleteAppStore(id: string): Promise<{ deleted: boolean }> {
    const response = await apiClient.delete<{ deleted: boolean }>(`/api/admin/app/stores/${id}`);
    return response.data;
  },

  async listAppLookbooks(includeUnpublished: boolean = true): Promise<any[]> {
    const response = await apiClient.get<any[]>('/api/admin/app/lookbooks', {
      params: { include_unpublished: includeUnpublished },
    });
    return response.data;
  },
  async createAppLookbook(payload: any): Promise<{ id: string }> {
    const response = await apiClient.post<{ id: string }>('/api/admin/app/lookbooks', payload);
    return response.data;
  },
  async updateAppLookbook(id: string, payload: any): Promise<{ success: boolean }> {
    const response = await apiClient.put<{ success: boolean }>(`/api/admin/app/lookbooks/${id}`, payload);
    return response.data;
  },
  async deleteAppLookbook(id: string): Promise<{ deleted: boolean }> {
    const response = await apiClient.delete<{ deleted: boolean }>(`/api/admin/app/lookbooks/${id}`);
    return response.data;
  },

  async listAppPromotions(status?: string): Promise<any[]> {
    const response = await apiClient.get<any[]>('/api/admin/app/promotions', {
      params: { status },
    });
    return response.data;
  },
  async createAppPromotion(payload: any): Promise<{ id: string }> {
    const response = await apiClient.post<{ id: string }>('/api/admin/app/promotions', payload);
    return response.data;
  },
  async updateAppPromotion(id: string, payload: any): Promise<{ success: boolean }> {
    const response = await apiClient.put<{ success: boolean }>(`/api/admin/app/promotions/${id}`, payload);
    return response.data;
  },
  async deleteAppPromotion(id: string): Promise<{ deleted: boolean }> {
    const response = await apiClient.delete<{ deleted: boolean }>(`/api/admin/app/promotions/${id}`);
    return response.data;
  },

  async listAppNews(status?: string): Promise<any[]> {
    const response = await apiClient.get<any[]>('/api/admin/app/news', {
      params: { status },
    });
    return response.data;
  },
  async createAppNews(payload: any): Promise<{ id: string }> {
    const response = await apiClient.post<{ id: string }>('/api/admin/app/news', payload);
    return response.data;
  },
  async updateAppNews(id: string, payload: any): Promise<{ success: boolean }> {
    const response = await apiClient.put<{ success: boolean }>(`/api/admin/app/news/${id}`, payload);
    return response.data;
  },
  async deleteAppNews(id: string): Promise<{ deleted: boolean }> {
    const response = await apiClient.delete<{ deleted: boolean }>(`/api/admin/app/news/${id}`);
    return response.data;
  },

  async getCdekSettings(): Promise<any> {
    const response = await apiClient.get<any>('/api/admin/shipping/cdek/settings');
    return response.data;
  },
  async updateCdekSettings(payload: any): Promise<{ success: boolean }> {
    const response = await apiClient.put<{ success: boolean }>('/api/admin/shipping/cdek/settings', payload);
    return response.data;
  },
  async getCdekOptions(): Promise<any> {
    const response = await apiClient.get<any>('/api/admin/shipping/cdek/options');
    return response.data;
  },
  async searchCdekCities(query: string, size: number = 20): Promise<any[]> {
    const response = await apiClient.get<any[]>('/api/admin/shipping/cdek/search/cities', {
      params: { q: query, size },
    });
    return response.data;
  },
  async searchCdekOffices(cityCode: number, query: string = '', size: number = 200): Promise<any[]> {
    const response = await apiClient.get<any[]>('/api/admin/shipping/cdek/search/offices', {
      params: { city_code: cityCode, q: query, size },
    });
    return response.data;
  },

  async getConversionMetrics(
    days?: number,
    startDate?: string,
    endDate?: string,
    cjmStage?: string,
    channel?: string
  ): Promise<any> {
    const response = await apiClient.get('/api/analytics/conversion', {
      params: { days, start_date: startDate, end_date: endDate, cjm_stage: cjmStage, channel }
    });
    return response.data;
  },

  async getAOVMetrics(
    days?: number,
    startDate?: string,
    endDate?: string,
    userId?: string,
    channel?: string
  ): Promise<any> {
    const response = await apiClient.get('/api/analytics/aov', {
      params: { days, start_date: startDate, end_date: endDate, user_id: userId, channel }
    });
    return response.data;
  },

  async getEngagementMetrics(
    days?: number,
    startDate?: string,
    endDate?: string,
    userId?: string
  ): Promise<any> {
    const response = await apiClient.get('/api/analytics/engagement', {
      params: { days, start_date: startDate, end_date: endDate, user_id: userId }
    });
    return response.data;
  },

  async getContentPerformance(
    days?: number,
    startDate?: string,
    endDate?: string,
    contentItemId?: string,
    channel?: string
  ): Promise<any> {
    const response = await apiClient.get('/api/analytics/content-performance', {
      params: { days, start_date: startDate, end_date: endDate, content_item_id: contentItemId, channel }
    });
    return response.data;
  },

  // Stores API
  async getNearestStores(
    latitude: number,
    longitude: number,
    radiusKm: number = 50,
    limit: number = 5
  ): Promise<{
    latitude: number;
    longitude: number;
    radius_km: number;
    stores: Array<{
      id: string;
      name: string;
      address: string | null;
      city: string | null;
      latitude: number | null;
      longitude: number | null;
      distance_km: number;
      is_active: boolean;
    }>;
  }> {
    try {
      const response = await apiClient.get('/api/stores/nearest', {
        params: {
          latitude,
          longitude,
          radius_km: radiusKm,
          limit
        }
      });
      return response.data;
    } catch (error: any) {
      console.error('Get Nearest Stores API Error:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
      }
      throw error;
    }
  },
};

export interface OneCSyncResponse {
  success: boolean;
  message: string;
  stats?: {
    created: number;
    updated: number;
    skipped: number;
    errors: number;
    deactivated: number;
  };
  details?: {
    products?: { created?: number; updated?: number; skipped?: number; error_count?: number; deactivated?: number };
    stocks?: { created?: number; updated?: number; skipped?: number; error_count?: number } | null;
    stores?: { created?: number; updated?: number; skipped?: number; error_count?: number; deactivated?: number } | null;
  };
}

export interface OneCSyncStatus {
  total_products: number;
  active_products: number;
  synced_products: number;
  last_sync: string | null;
  sync_coverage: number;
}

// Communication API
export interface GenerateMessageRequest {
  client_id: string;
  event: {
    type: 'brand_arrival' | 'loyalty_level_up' | 'bonus_balance' | 'no_purchase_180' | 'holiday_male';
    brand?: string;
    store?: string;
    metadata?: Record<string, any>;
  };
}

export interface GenerateMessageResponse {
  client_id: string;
  phone?: string;
  name?: string;
  gender?: 'male' | 'female' | null;  // Пол клиента, определенный по имени
  segment: string;
  reason: string;
  message: string;
  cta: string;
  brand?: string;
  store?: string;
}

export interface SearchCriteria {
  segments?: string[];
  segment_name?: string;
  segment_id?: string;
  min_total_spend_365?: number;
  max_total_spend_365?: number;
  min_purchases_365?: number;
  max_purchases_365?: number;
  min_days_since_last?: number;
  max_days_since_last?: number;
  min_bonus_balance?: number;
  max_bonus_balance?: number;
  is_local_only?: boolean;
  cities?: string[];
  must_have_brands?: string[];
  exclude_brands?: string[];
}

export interface BatchGenerateRequest {
  event: {
    type: 'brand_arrival' | 'loyalty_level_up' | 'bonus_balance' | 'no_purchase_180' | 'holiday_male';
    brand?: string;
    store?: string;
    metadata?: Record<string, any>;
  };
  client_ids?: string[];
  brand?: string;
  limit?: number;
  max_length?: number; // Максимальная длина сообщения в символах
  search_criteria?: SearchCriteria;
  auto_detect_store?: boolean; // Автоматическое определение бутика из истории покупок или города
}

export interface BatchGenerateResponse {
  status: string;
  messages: GenerateMessageResponse[];
  count: number;
  message?: string;
  errors?: Array<{ client_id: string; error: string }>;
  debug_info?: any;
  total_customers_in_db?: number;
}

export interface BatchGenerateAsyncResponse {
  status: string;
  generation_id: string;
  events_url: string;
}

export interface CustomerMessageItem {
  id: string;
  message: string;
  cta: string | null;
  segment: string | null;
  event_type: string | null;
  event_brand: string | null;
  event_store: string | null;
  message_kind?: 'individual' | 'broadcast';
  generation_id?: string | null;
  status: 'new' | 'sent';
  sent_at: string | null;
  created_at: string;
}

export interface CustomerMessagesListResponse {
  items: CustomerMessageItem[];
  total: number;
}

export interface GenerationHistoryRecord {
  id: string;
  status: string;
  event_type: string;
  segment?: string | null;
  started_at: string;
  completed_at?: string | null;
  total: number;
  processed: number;
  success: number;
  errors: number;
  params?: Record<string, any> | null;
  saved_file?: string | null;
  error_message?: string | null;
}

export const communication = {
  async generateMessage(request: GenerateMessageRequest): Promise<GenerateMessageResponse> {
    const response = await apiClient.post<GenerateMessageResponse>(
      '/api/communication/generate-message',
      request
    );
    return response.data;
  },

  async getCustomerMessages(
    customerId: string,
    limit?: number,
    offset?: number,
    params?: {
      kind?: 'all' | 'broadcast' | 'individual';
      date_from?: string;
      date_to?: string;
      sort_by?: string;
      desc?: boolean;
    }
  ): Promise<CustomerMessagesListResponse> {
    const response = await apiClient.get<CustomerMessagesListResponse>(
      `/api/communication/customers/${customerId}/messages`,
      { params: { limit: limit ?? 50, offset: offset ?? 0, ...(params || {}) } }
    );
    return response.data;
  },

  async deleteCustomerMessage(messageId: string): Promise<void> {
    await apiClient.delete(`/api/communication/messages/${messageId}`);
  },

  async markMessageSent(messageId: string): Promise<{ sent_at: string }> {
    const response = await apiClient.post<{ status: string; sent_at: string }>(
      `/api/communication/messages/${messageId}/send`
    );
    return { sent_at: response.data.sent_at };
  },

  async batchGenerate(request: BatchGenerateRequest): Promise<BatchGenerateResponse> {
    const response = await apiClient.post<BatchGenerateResponse>(
      '/api/communication/batch-generate',
      request,
      {
        timeout: 300000, // 5 минут для генерации сообщений
      }
    );
    return response.data;
  },

  async startBatchGenerateAsync(request: BatchGenerateRequest): Promise<BatchGenerateAsyncResponse> {
    const response = await apiClient.post<BatchGenerateAsyncResponse>(
      '/api/communication/batch-generate-async',
      request,
      {
        timeout: 30000,
      }
    );
    return response.data;
  },

  async getClientsByBrand(brand: string, limit: number = 100): Promise<{ client_ids: string[]; count: number }> {
    const response = await apiClient.get('/api/communication/clients/by-brand', {
      params: { brand, limit }
    });
    return response.data;
  },

  async getAvailableBrands(limit: number = 100): Promise<{ brands: Array<{ brand: string; client_count: number }>; count: number }> {
    const response = await apiClient.get<{ status: string; brands: Array<{ brand: string; client_count: number }>; count: number }>(
      '/api/communication/brands/available',
      { params: { limit } }
    );
    return { brands: response.data.brands ?? [], count: response.data.count ?? 0 };
  },

  async getClientData(clientId: string): Promise<any> {
    const response = await apiClient.get(`/api/communication/clients/${clientId}/data`);
    return response.data.client;
  },

  async listGenerations(params?: {
    status?: string;
    event_type?: string;
    date_from?: string;
    date_to?: string;
    search?: string;
    sort_by?: string;
    desc?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<{ total: number; items: GenerationHistoryRecord[] }> {
    const response = await apiClient.get('/api/communication/generations', { params });
    return response.data;
  },

  async getGeneration(id: string): Promise<GenerationHistoryRecord> {
    const response = await apiClient.get(`/api/communication/generations/${id}`);
    return response.data;
  },

  async exportGenerations(ids: string[], columns?: string[]): Promise<Blob> {
    const response = await apiClient.post(
      '/api/communication/generations/export',
      { ids, columns },
      { responseType: 'blob' }
    );
    return response.data;
  },

  async getGenerationResult(id: string): Promise<{ status?: string; messages: any[]; count?: number }> {
    const response = await apiClient.get(`/api/communication/generations/${id}/result`);
    // Унифицируем структуру
    const data = response.data || {};
    return {
      status: data.status,
      messages: data.messages || [],
      count: data.count ?? (Array.isArray(data.messages) ? data.messages.length : undefined),
    };
  },

  async updateGenerationMessage(genId: string, clientId: string, data: { message: string, cta?: string }): Promise<{ status: string; message: string }> {
    const response = await apiClient.put<{ status: string; message: string }>(
      `/api/communication/generations/${genId}/messages/${clientId}`,
      data
    );
    return response.data;
  },

  async sendGenerationSms(
    genId: string,
    data: { date_send?: string; periodicity?: string }
  ): Promise<{ status: string; message: string }> {
    const response = await apiClient.post<{ status: string; message: string }>(
      `/api/communication/generations/${genId}/send`,
      data
    );
    return response.data;
  },

  async deleteGenerationFiles(ids: string[]): Promise<{ deleted: string[]; failed: Record<string, string> }> {
    const response = await apiClient.post(`/api/communication/generations/delete-files`, { ids });
    return { deleted: response.data.deleted || [], failed: response.data.failed || {} };
  },
};

// System Prompts API
export interface SystemPromptVersion {
  id: string;
  agent_type: string;
  version: number;
  version_name?: string;
  name: string;
  description?: string;
  system_prompt: string;
  metadata: Record<string, any>;
  is_active: boolean;
  is_default: boolean;
  marketer_review_status?: string;
  marketer_feedback?: string;
  created_by?: string;
  approved_by?: string;
  created_at: string;
}

export interface PromptGenerationRequest {
  id: string;
  agent_type: string;
  user_description: string;
  generated_prompt?: string;
  status: string;
  error_message?: string;
  created_at: string;
  completed_at?: string;
}

export const systemPrompts = {
  // Get all prompt versions
  async getVersions(agentType: string, includeInactive: boolean = true): Promise<SystemPromptVersion[]> {
    const response = await apiClient.get<SystemPromptVersion[]>(
      `/api/agent-system-prompts/${agentType}/versions`,
      { params: { include_inactive: includeInactive } }
    );
    return response.data;
  },

  // Get active prompt
  async getActive(agentType: string): Promise<SystemPromptVersion | null> {
    const response = await apiClient.get<SystemPromptVersion | null>(
      `/api/agent-system-prompts/${agentType}/active`
    );
    return response.data;
  },

  // Create new version
  async createVersion(agentType: string, data: {
    name: string;
    system_prompt: string;
    description?: string;
    version_name?: string;
    metadata?: Record<string, any>;
  }): Promise<SystemPromptVersion> {
    const response = await apiClient.post<SystemPromptVersion>(
      `/api/agent-system-prompts/${agentType}/versions`,
      data
    );
    return response.data;
  },

  // Activate version
  async activateVersion(agentType: string, promptId: string): Promise<SystemPromptVersion> {
    const response = await apiClient.post<SystemPromptVersion>(
      `/api/agent-system-prompts/${agentType}/versions/${promptId}/activate`
    );
    return response.data;
  },

  // Submit for marketer review
  async submitForReview(agentType: string, promptId: string): Promise<SystemPromptVersion> {
    const response = await apiClient.put<SystemPromptVersion>(
      `/api/agent-system-prompts/${agentType}/versions/${promptId}/marketer-review`,
      { status: 'pending' }
    );
    return response.data;
  },

  // Review as marketer
  async reviewAsMarketer(
    agentType: string,
    promptId: string,
    status: 'approved' | 'rejected' | 'needs_revision',
    feedback?: string
  ): Promise<SystemPromptVersion> {
    const response = await apiClient.put<SystemPromptVersion>(
      `/api/agent-system-prompts/${agentType}/versions/${promptId}/marketer-review`,
      { status, feedback }
    );
    return response.data;
  },

  // Get version history
  async getVersionHistory(agentType: string, promptId: string): Promise<Array<{
    id: string;
    change_type: string;
    change_comment?: string;
    changed_by?: string;
    changed_at: string;
    previous_value?: Record<string, any>;
    new_value?: Record<string, any>;
  }>> {
    const response = await apiClient.get(
      `/api/agent-system-prompts/${agentType}/versions/${promptId}/history`
    );
    return response.data;
  },

  // Generate prompt from description
  async generateFromDescription(agentType: string, data: {
    user_description: string;
    target_tone?: string;
    target_audience?: string;
    constraints?: string[];
  }): Promise<PromptGenerationRequest> {
    const response = await apiClient.post<PromptGenerationRequest>(
      `/api/agent-system-prompts/${agentType}/generate-from-description`,
      data
    );
    return response.data;
  },

  // Get generation requests
  async getGenerationRequests(
    agentType: string,
    limit: number = 20,
    status?: string
  ): Promise<PromptGenerationRequest[]> {
    const response = await apiClient.get<PromptGenerationRequest[]>(
      `/api/agent-system-prompts/${agentType}/generation-requests`,
      { params: { status, limit } }
    );
    return response.data;
  },

  // Create prompt from generation request
  async createFromGenerationRequest(
    agentType: string,
    requestId: string,
    name: string
  ): Promise<SystemPromptVersion> {
    const response = await apiClient.post<SystemPromptVersion>(
      `/api/agent-system-prompts/${agentType}/generation-requests/${requestId}/create-prompt`,
      { name }
    );
    return response.data;
  },

  // Update prompt version
  async updateVersion(
    agentType: string,
    promptId: string,
    data: {
      name?: string;
      description?: string;
      system_prompt?: string;
      version_name?: string;
      metadata?: Record<string, any>;
    }
  ): Promise<SystemPromptVersion> {
    const response = await apiClient.put<SystemPromptVersion>(
      `/api/agent-system-prompts/${agentType}/versions/${promptId}`,
      data
    );
    return response.data;
  },
};

// Agent Interactions API
export interface AgentInteractionTask {
  id: string;
  source_agent: string;
  target_agent: string;
  task_type: string;
  task_context: Record<string, any>;
  input_data: Record<string, any>;
  target_metrics?: Record<string, any>;
  requirements?: Record<string, any>;
  constraints?: Record<string, any>;
  priority: number;
  status: string;
  output_data?: Record<string, any>;
  output_metadata?: Record<string, any>;
  error_message?: string;
  created_at: string;
  scheduled_at?: string;
  started_at?: string;
  completed_at?: string;
  deadline_at?: string;
}

export interface MassMailingSegmentInfo {
  id: string;
  name: string;
  customer_count: number;
}

export interface MassMailingSuggestedRequest {
  brand?: string | null;
  limit: number;
  auto_detect_store: boolean;
  event: Record<string, any>;
  search_criteria: Record<string, any>;
}

export interface MassMailingPrepareResponse {
  report: string;
  segment: MassMailingSegmentInfo;
  suggested_request: MassMailingSuggestedRequest;
}

export interface MassMailingRunResponse {
  report: string;
  segment: MassMailingSegmentInfo;
  generation_id: string;
  events_url: string;
}

export const agentInteractions = {
  async getTaskSegment(taskId: string): Promise<{ id?: string; name?: string; customer_count?: number; message?: string }> {
    const response = await apiClient.get<{ id?: string; name?: string; customer_count?: number; message?: string }>(
      `/api/agent-interactions/tasks/${taskId}/segment`
    );
    return response.data;
  },
  async bindTaskSegment(taskId: string, segmentId: string): Promise<MassMailingSegmentInfo> {
    const response = await apiClient.put<MassMailingSegmentInfo>(
      `/api/agent-interactions/tasks/${taskId}/segment`,
      { segment_id: segmentId }
    );
    return response.data;
  },
  async chat(taskId: string, data: {
    message: string;
    model?: string;
    metadata?: {
      step_type?: 'planning' | 'segmentation' | 'content' | 'analytics' | 'distribution' | 'other';
      task_type?: string;
      dialog_model?: string;
      analytics_model?: string;
      attachments?: Array<{ name?: string; kind?: string; size?: number }>;
      extra?: Record<string, any>;
    };
  }): Promise<{ reply: string; used_brand_context?: any[]; used_history_fragments?: any[]; user_log_id?: string; assistant_log_id?: string }> {
    const response = await apiClient.post(
      `/api/agent-interactions/tasks/${taskId}/chat`,
      data
    );
    return response.data;
  },

  async getChatHistory(taskId: string, limit: number = 200): Promise<ChatHistoryItem[]> {
    const response = await apiClient.get<ChatHistoryItem[]>(
      `/api/agent-interactions/tasks/${taskId}/chat`,
      { params: { limit } }
    );
    return response.data;
  },
  async deleteChatMessage(taskId: string, logId: string): Promise<{ status: string; id: string }> {
    const response = await apiClient.delete<{ status: string; id: string }>(
      `/api/agent-interactions/tasks/${taskId}/chat/${logId}`
    );
    return response.data;
  },
  // Get tasks for an agent
  async getTasks(agentType: string, status?: string, limit: number = 20): Promise<AgentInteractionTask[]> {
    const response = await apiClient.get<AgentInteractionTask[]>(
      `/api/agent-interactions/${agentType}/tasks`,
      { params: { status, limit } }
    );
    return response.data;
  },

  // Create a new task
  async createTask(data: {
    source_agent: string;
    target_agent: string;
    task_type: string;
    input_data: Record<string, any>;
    task_context?: Record<string, any>;
    target_metrics?: Record<string, any>;
    requirements?: Record<string, any>;
    constraints?: Record<string, any>;
    priority?: number;
    deadline_at?: string;
    timeout_seconds?: number;
  }): Promise<AgentInteractionTask> {
    const response = await apiClient.post<AgentInteractionTask>(
      '/api/agent-interactions/tasks',
      data
    );
    return response.data;
  },

  // Get task details
  async getTask(taskId: string): Promise<AgentInteractionTask> {
    const response = await apiClient.get<AgentInteractionTask>(
      `/api/agent-interactions/tasks/${taskId}`
    );
    return response.data;
  },

  async updateTask(taskId: string, data: Partial<AgentInteractionTask>): Promise<AgentInteractionTask> {
    const response = await apiClient.patch<AgentInteractionTask>(
      `/api/agent-interactions/tasks/${taskId}`,
      data
    );
    return response.data;
  },

  // List tasks with optional filters
  async listTasks(params?: {
    target_agent?: string;
    source_agent?: string;
    status?: string;
    task_type?: string;
    limit?: number;
  }): Promise<AgentInteractionTask[]> {
    const response = await apiClient.get<AgentInteractionTask[]>(
      '/api/agent-interactions/tasks',
      { params }
    );
    return response.data;
  },

  // Queue a task
  async queueTask(taskId: string): Promise<{ message: string; task_id: string; priority: number; status: string }> {
    const response = await apiClient.post<{ message: string; task_id: string; priority: number; status: string }>(
      `/api/agent-interactions/tasks/${taskId}/queue`
    );
    return response.data;
  },

  // Process a task
  async processTask(taskId: string): Promise<{ message: string; task_id: string; result_summary: Record<string, any> }> {
    const response = await apiClient.post<{ message: string; task_id: string; result_summary: Record<string, any> }>(
      `/api/agent-interactions/tasks/${taskId}/process`
    );
    return response.data;
  },

  async approveTask(taskId: string, comment?: string): Promise<{ message: string; task_id: string; new_status: string }> {
    const response = await apiClient.post<{ message: string; task_id: string; new_status: string }>(
      `/api/agent-interactions/tasks/${taskId}/approve`,
      { comment: comment || null }
    );
    return response.data;
  },

  async rejectTask(taskId: string, comment?: string): Promise<{ message: string; task_id: string; new_status: string; rejection_comment?: string | null }> {
    const response = await apiClient.post<{ message: string; task_id: string; new_status: string; rejection_comment?: string | null }>(
      `/api/agent-interactions/tasks/${taskId}/reject`,
      { comment: comment || null }
    );
    return response.data;
  },

  async reviseTask(taskId: string, comment?: string): Promise<{ message: string; task_id: string; new_status: string; revision_comment?: string | null }> {
    const response = await apiClient.post<{ message: string; task_id: string; new_status: string; revision_comment?: string | null }>(
      `/api/agent-interactions/tasks/${taskId}/revise`,
      { comment: comment || null }
    );
    return response.data;
  },

  // Cancel a task
  async cancelTask(taskId: string, reason?: string): Promise<{ message: string; task_id: string; status: string; reason?: string | null }> {
    const response = await apiClient.post<{ message: string; task_id: string; status: string; reason?: string | null }>(
      `/api/agent-interactions/tasks/${taskId}/cancel`,
      reason ? { reason } : undefined
    );
    return response.data;
  },

  // Delete a task (soft delete)
  async deleteTask(taskId: string, reason?: string): Promise<{ message: string; task_id: string; status: string }> {
    const response = await apiClient.delete<{ message: string; task_id: string; status: string }>(
      `/api/agent-interactions/tasks/${taskId}`,
      { params: reason ? { reason } : {} }
    );
    return response.data;
  },

  // Get task logs
  async getTaskLogs(taskId: string, limit: number = 100): Promise<TaskLog[]> {
    const response = await apiClient.get<TaskLog[]>(
      `/api/agent-interactions/tasks/${taskId}/logs`,
      { params: { limit } }
    );
    return response.data;
  },

  async prepareMassMailing(taskId: string, data: {
    plan_text: string;
    plan_title?: string;
    brand?: string;
    event_type?: string;
    message_count?: number;
    metadata?: Record<string, any>;
  }): Promise<MassMailingPrepareResponse> {
    const response = await apiClient.post<MassMailingPrepareResponse>(
      `/api/agent-interactions/tasks/${taskId}/mass-mailing/prepare`,
      data
    );
    return response.data;
  },

  async runMassMailing(taskId: string, data: {
    segment_id: string;
    event_type: string;
    brand?: string;
    message_count?: number;
    auto_detect_store?: boolean;
    metadata?: Record<string, any>;
  }): Promise<MassMailingRunResponse> {
    const response = await apiClient.post<MassMailingRunResponse>(
      `/api/agent-interactions/tasks/${taskId}/mass-mailing/run`,
      data
    );
    return response.data;
  },
};

export interface TaskLog {
  id: string;
  task_id: string;
  agent_name: string;
  event_type: string;
  message?: string | null;
  event_data: Record<string, any>;
  created_at: string;
}

export interface ChatHistoryItem {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at?: string | null;
}

export interface SegmentRulesFilter {
  field: string;
  operator: string;
  value: any;
}

export interface SegmentRules {
  logic: 'AND' | 'OR';
  filters: SegmentRulesFilter[];
}

export interface SegmentOut {
  id: string;
  name: string;
  description?: string | null;
  rules: SegmentRules;
  customer_count: number;
  is_auto_generated?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export const customerSegmentation = {
  async getSegments(): Promise<SegmentOut[]> {
    const response = await apiClient.get<SegmentOut[]>('/api/customer-segmentation/segments');
    return response.data;
  },
  async createSegment(data: { name: string; description?: string; rules: SegmentRules }): Promise<SegmentOut> {
    const response = await apiClient.post<SegmentOut>('/api/customer-segmentation/segments', data);
    return response.data;
  },
  async updateSegment(segmentId: string, data: Partial<{ name: string; description: string; rules: SegmentRules }>): Promise<SegmentOut> {
    const response = await apiClient.put<SegmentOut>(`/api/customer-segmentation/segments/${segmentId}`, data);
    return response.data;
  },
  async calculateSegmentCount(rules: SegmentRules): Promise<{ count: number }> {
    const response = await apiClient.post<{ count: number }>(
      '/api/customer-segmentation/segments/calculate-count',
      rules
    );
    return response.data;
  },
};

export interface SegmentAnalysisItem {
  segment_id: string;
  name: string;
  description?: string | null;
  size: number;
  average_ltv: number;
  average_purchases: number;
  insights: string;
}

export const aiMarketer = {
  async getBoardState(boardId: string, params?: { limit?: number }): Promise<{ board_id: string; tasks: AgentInteractionTask[]; stats: Record<string, number> }> {
    const response = await apiClient.get<{ board_id: string; tasks: AgentInteractionTask[]; stats: Record<string, number> }>(
      `/api/ai-marketer/boards/${boardId}`,
      { params }
    );
    return response.data;
  },
  async ensureBoardTask(boardId: string, data: {
    source_agent?: string;
    target_agent: string;
    task_type: string;
    input_data?: Record<string, any>;
    task_context?: Record<string, any>;
    target_metrics?: Record<string, any>;
    requirements?: Record<string, any>;
    constraints?: Record<string, any>;
    priority?: number;
    deadline_at?: string;
    idempotency_key?: string;
  }): Promise<{ created: boolean; task: AgentInteractionTask }> {
    const response = await apiClient.post<{ created: boolean; task: AgentInteractionTask }>(
      `/api/ai-marketer/boards/${boardId}/tasks/ensure`,
      data
    );
    return response.data;
  },
  async autoGenerateSegments(): Promise<{ success: boolean; stats: Record<string, any> }> {
    const response = await apiClient.post<{ success: boolean; stats: Record<string, any> }>(
      '/api/ai-marketer/segments/auto-generate',
      {}
    );
    return response.data;
  },
  async getSegmentsAnalysis(): Promise<{ segments: SegmentAnalysisItem[] }> {
    const response = await apiClient.get<{ segments: SegmentAnalysisItem[] }>(
      '/api/ai-marketer/segments/analysis'
    );
    return response.data;
  },
};

export const adminCustomers = {
  async getOverview(): Promise<{ total_customers: number; total_revenue: number }> {
    const response = await apiClient.get<{ total_customers: number; total_revenue: number }>(
      '/api/admin/customers/analytics/overview'
    );
    return response.data;
  },
  async exportXlsx(params?: { segment?: string; search?: string }): Promise<Blob> {
    const response = await apiClient.get('/api/admin/customers/export', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },
};

export interface AdminSection {
  id: string;
  name: string;
  href: string;
  group: string;
}

export interface RoleAccess {
  role_key: string;
  role_label: string;
  section_ids: string[];
  is_system: boolean;
}

export interface StaffUser {
  id: string;
  email: string | null;
  full_name?: string | null;
  role: string | null;
  role_label?: string | null;
  is_customer: boolean;
}

export interface LiveStylistUserInfo {
  id: string;
  full_name?: string | null;
  email?: string | null;
  phone?: string | null;
  city?: string | null;
  role?: string | null;
  role_label?: string | null;
}

export interface LiveStylistMessage {
  id: string;
  conversation_id?: string | null;
  user_id: string;
  sender_user_id?: string | null;
  role: string;
  text?: string | null;
  attachments: Array<Record<string, any>>;
  payload: Record<string, any>;
  created_at?: string | null;
  sender?: LiveStylistUserInfo | null;
}

export interface LiveStylistAttachableProduct {
  id: string;
  name?: string | null;
  brand?: string | null;
  category?: string | null;
  article?: string | null;
  external_code?: string | null;
  price?: number | null;
  image_url?: string | null;
  in_stock: boolean;
}

export interface LiveStylistConversation {
  id: string;
  source?: string | null;
  scenario?: string | null;
  status: 'requested' | 'in_progress' | 'completed' | string;
  status_label: string;
  priority: 'normal' | 'high' | string;
  priority_label: string;
  unread_for_stylist_count: number;
  unread_for_customer_count: number;
  created_at?: string | null;
  updated_at?: string | null;
  last_message_at?: string | null;
  first_response_at?: string | null;
  closed_at?: string | null;
  result_purchase_status: 'unknown' | 'not_purchased' | 'purchased_recommended' | 'purchased_other' | string;
  result_purchase_status_label: string;
  result_order_id?: string | null;
  result_source?: 'auto' | 'manual' | string | null;
  recommended_product_ids: string[];
  internal_notes?: string | null;
  result_notes?: string | null;
  needs_attention: boolean;
  attention_reason?: 'overdue_first_response' | 'unassigned_request' | 'unread_customer_message' | string | null;
  waiting_minutes: number;
  first_response_due_at?: string | null;
  customer: LiveStylistUserInfo;
  assigned_stylist?: LiveStylistUserInfo | null;
  last_message_preview?: string | null;
}

export interface LiveStylistOrderSummary {
  id: string;
  status: string;
  total_amount: number;
  created_at?: string | null;
  product_ids: string[];
}

export interface LiveStylistCustomerPurchaseItem {
  id: string;
  purchase_date?: string | null;
  product_id?: string | null;
  product_name?: string | null;
  category?: string | null;
  brand?: string | null;
  quantity: number;
  total_amount: number;
}

export interface LiveStylistCustomerFavoriteProduct {
  id: string;
  name?: string | null;
  brand?: string | null;
  category?: string | null;
  article?: string | null;
  price?: number | null;
  image_url?: string | null;
}

export interface LiveStylistCustomerFavoriteLook {
  id: string;
  look_id: string;
  look_name?: string | null;
  save_type?: string | null;
  look_style?: string | null;
  look_mood?: string | null;
  look_image_url?: string | null;
  created_at?: string | null;
}

export interface LiveStylistCustomerLoyaltyTransaction {
  id: string;
  transaction_type: string;
  points: number;
  balance_after: number;
  reason?: string | null;
  description?: string | null;
  created_at?: string | null;
}

export interface LiveStylistCustomerContext {
  customer_id: string;
  is_registered: boolean;
  has_bonus_card: boolean;
  discount_card_number?: string | null;
  loyalty_points: number;
  customer_segment?: string | null;
  total_purchases: number;
  total_spent: number;
  average_check?: number | null;
  last_purchase_date?: string | null;
  preferred_store_name?: string | null;
  secondary_store_name?: string | null;
  favorite_categories: string[];
  favorite_brands: string[];
  favorite_products: LiveStylistCustomerFavoriteProduct[];
  favorite_looks: LiveStylistCustomerFavoriteLook[];
  recent_purchases: LiveStylistCustomerPurchaseItem[];
  loyalty_transactions: LiveStylistCustomerLoyaltyTransaction[];
}

export interface LiveStylistConversationDetail {
  conversation: LiveStylistConversation;
  messages: LiveStylistMessage[];
  audit_events: LiveStylistConversationAuditEvent[];
  recent_orders: LiveStylistOrderSummary[];
  customer_context: LiveStylistCustomerContext;
  current_working_hours: Record<string, any>;
}

export interface LiveStylistConversationAuditEvent {
  id: string;
  event_type: string;
  event_label: string;
  description: string;
  created_at?: string | null;
  actor?: LiveStylistUserInfo | null;
  payload: Record<string, any>;
}

export interface LiveStylistInboxBadge {
  total_unread_messages: number;
  requested_conversations: number;
  high_priority_conversations: number;
  mine_unread_messages: number;
  open_conversations: number;
  unassigned_conversations: number;
  purchased_conversations: number;
  attention_conversations: number;
  overdue_first_response_conversations: number;
}

export const adminAccess = {
  async getSections(): Promise<AdminSection[]> {
    const response = await apiClient.get<AdminSection[]>('/api/admin/access/sections');
    return response.data;
  },
  async getRoles(): Promise<RoleAccess[]> {
    const response = await apiClient.get<RoleAccess[]>('/api/admin/access/roles');
    return response.data;
  },
  async updateRole(roleKey: string, sectionIds: string[]): Promise<RoleAccess> {
    const response = await apiClient.put<RoleAccess>(`/api/admin/access/roles/${roleKey}`, {
      section_ids: sectionIds,
    });
    return response.data;
  },
  async getStaff(): Promise<StaffUser[]> {
    const response = await apiClient.get<StaffUser[]>('/api/admin/access/staff');
    return response.data;
  },
  async createStaff(payload: {
    email: string;
    password: string;
    full_name?: string;
    role: string;
  }): Promise<StaffUser> {
    const response = await apiClient.post<StaffUser>('/api/admin/access/staff', payload);
    return response.data;
  },
  async updateStaff(
    id: string,
    payload: { email?: string; password?: string; full_name?: string; role?: string }
  ): Promise<StaffUser> {
    const response = await apiClient.put<StaffUser>(`/api/admin/access/staff/${id}`, payload);
    return response.data;
  },
  async deleteStaff(id: string): Promise<void> {
    await apiClient.delete(`/api/admin/access/staff/${id}`);
  },
};

export interface PlatformRestartResponse {
  status: string;
  service: string;
  message: string;
}

export const adminSystem = {
  async restartPlatform(): Promise<PlatformRestartResponse> {
    const response = await apiClient.post<PlatformRestartResponse>('/api/admin/system/restart');
    return response.data;
  },
};

export const liveStylistAdmin = {
  async listConversations(params?: {
    status?: string;
    purchase_status?: string;
    search?: string;
    mine_only?: boolean;
    unassigned_only?: boolean;
    attention_only?: boolean;
    limit?: number;
  }): Promise<LiveStylistConversation[]> {
    const response = await apiClient.get<LiveStylistConversation[]>('/api/admin/live-stylist/conversations', { params });
    return response.data;
  },
  async getConversation(id: string): Promise<LiveStylistConversationDetail> {
    const response = await apiClient.get<LiveStylistConversationDetail>(`/api/admin/live-stylist/conversations/${id}`);
    return response.data;
  },
  async getInboxBadge(): Promise<LiveStylistInboxBadge> {
    const response = await apiClient.get<LiveStylistInboxBadge>('/api/admin/live-stylist/inbox-badge');
    return response.data;
  },
  async listStylists(): Promise<LiveStylistUserInfo[]> {
    const response = await apiClient.get<LiveStylistUserInfo[]>('/api/admin/live-stylist/stylists');
    return response.data;
  },
  async searchProducts(query: string, limit: number = 8): Promise<LiveStylistAttachableProduct[]> {
    const response = await apiClient.get<LiveStylistAttachableProduct[]>('/api/admin/live-stylist/products/search', {
      params: { query, limit },
    });
    return response.data;
  },
  async assignConversation(conversationId: string, stylistUserId?: string | null): Promise<LiveStylistConversation> {
    const response = await apiClient.post<LiveStylistConversation>(
      `/api/admin/live-stylist/conversations/${conversationId}/assign`,
      { stylist_user_id: stylistUserId ?? undefined }
    );
    return response.data;
  },
  async updateConversation(
    conversationId: string,
    payload: {
      status?: string;
      priority?: string;
      assigned_stylist_user_id?: string | null;
      internal_notes?: string | null;
      result_purchase_status?: string;
      result_order_id?: string | null;
      result_notes?: string | null;
      recommended_product_ids?: string[];
    }
  ): Promise<LiveStylistConversation> {
    const response = await apiClient.patch<LiveStylistConversation>(
      `/api/admin/live-stylist/conversations/${conversationId}`,
      payload
    );
    return response.data;
  },
  async sendMessage(conversationId: string, text: string): Promise<LiveStylistConversationDetail> {
    const response = await apiClient.post<LiveStylistConversationDetail>(
      `/api/admin/live-stylist/conversations/${conversationId}/messages`,
      { text }
    );
    return response.data;
  },
  async sendComposedMessage(
    conversationId: string,
    payload: {
      text?: string;
      product_ids?: string[];
      photos?: File[];
    }
  ): Promise<LiveStylistConversationDetail> {
    const form = new FormData();
    if ((payload.text || '').trim()) {
      form.append('text', (payload.text || '').trim());
    }
    if (payload.product_ids?.length) {
      form.append('product_ids', payload.product_ids.join(','));
    }
    const photos = payload.photos || [];
    if (photos.length === 1) {
      form.append('photo', photos[0]);
    } else {
      for (const photo of photos) {
        form.append('photos', photo);
      }
    }
    const response = await apiClient.post<LiveStylistConversationDetail>(
      `/api/admin/live-stylist/conversations/${conversationId}/messages/compose`,
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
      }
    );
    return response.data;
  },
  async setTypingState(conversationId: string, isTyping: boolean): Promise<{ ok: boolean; is_typing: boolean }> {
    const response = await apiClient.post<{ ok: boolean; is_typing: boolean }>(
      `/api/admin/live-stylist/conversations/${conversationId}/typing`,
      { is_typing: isTyping }
    );
    return response.data;
  },
  async clearConversationMessages(conversationId: string): Promise<LiveStylistConversationDetail> {
    const response = await apiClient.delete<LiveStylistConversationDetail>(
      `/api/admin/live-stylist/conversations/${conversationId}/messages`
    );
    return response.data;
  },
};

export const director = {
  /** Отправить сообщение AI-директору */
  async chat(
    message: string,
    sessionId?: string | null,
    category?: string | null,
    model?: string | null
  ): Promise<DirectorChatResponse> {
    const response = await apiClient.post<DirectorChatResponse>('/api/director/chat', {
      message,
      session_id: sessionId || undefined,
      category: category || undefined,
      model: model || undefined,
    });
    return response.data;
  },

  /** Загрузить файл в чат директора */
  async uploadChatFile(
    file: File,
    params?: {
      sessionId?: string | null;
      message?: string;
      addToKnowledge?: boolean;
      knowledgeCategory?: string;
    }
  ): Promise<{
    user_message: DirectorChatMessage;
    director_message: DirectorChatMessage;
    file: Record<string, any>;
    knowledge: Record<string, any> | null;
  }> {
    const form = new FormData();
    form.append('file', file);
    if (params?.sessionId) form.append('session_id', params.sessionId);
    if (params?.message?.trim()) form.append('message', params.message.trim());
    form.append('add_to_knowledge', String(Boolean(params?.addToKnowledge)));
    form.append('knowledge_category', params?.knowledgeCategory || 'document');
    const response = await apiClient.post('/api/director/chat/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  /** Создать задачу */
  async createTask(
    title: string,
    description?: string | null,
    priority?: string,
    sourceMessageId?: string | null
  ): Promise<{ task: DirectorTask; subtasks: any[]; assigned_agents: string[] }> {
    const response = await apiClient.post('/api/director/tasks', {
      title,
      description: description || undefined,
      priority: priority || 'P2',
      source_message_id: sourceMessageId || undefined,
    });
    return response.data;
  },

  /** Список задач */
  async listTasks(params?: {
    status?: string;
    priority?: string;
    task_type?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ tasks: DirectorTask[]; total: number }> {
    const response = await apiClient.get('/api/director/tasks', { params });
    return response.data;
  },

  /** Канбан задач директора + рабочих задач агентов */
  async tasksKanban(params?: {
    board?: string;
    limit?: number;
  }): Promise<{ columns: Array<{ id: string; title: string; cards: any[] }>; total: number; stats: Record<string, number> }> {
    const response = await apiClient.get('/api/director/tasks/kanban', { params });
    return response.data;
  },

  /** Лента хода работы директора: агенты и инструменты */
  async workActivity(params?: { limit?: number }): Promise<{ activity: any[]; total: number }> {
    const response = await apiClient.get('/api/director/activity', { params });
    return response.data;
  },

  /** Переместить карточку на канбан-доске директора */
  async moveTaskCard(source: string, taskId: string, columnId: string): Promise<{ task: any }> {
    const response = await apiClient.patch(
      `/api/director/tasks/${source}/${taskId}/kanban`,
      { column_id: columnId }
    );
    return response.data;
  },

  /** Согласовать задачу прямо из чата директора */
  async approveTaskCard(
    source: string,
    taskId: string,
    params?: { comment?: string | null; sessionId?: string | null }
  ): Promise<{ task: any; director_message: DirectorChatMessage }> {
    const response = await apiClient.post(
      `/api/director/tasks/${source}/${taskId}/approve`,
      {
        comment: params?.comment || null,
        session_id: params?.sessionId || null,
      }
    );
    return response.data;
  },

  /** Отправить задачу на доработку прямо из чата директора */
  async reviseTaskCard(
    source: string,
    taskId: string,
    params?: { comment?: string | null; sessionId?: string | null }
  ): Promise<{ task: any; director_message: DirectorChatMessage }> {
    const response = await apiClient.post(
      `/api/director/tasks/${source}/${taskId}/revise`,
      {
        comment: params?.comment || null,
        session_id: params?.sessionId || null,
      }
    );
    return response.data;
  },

  /** Получить контекст памяти */
  async getMemory(
    memoryType?: string,
    limit?: number
  ): Promise<{
    memories: DirectorChatMessage[];
    medium_term: any[];
    long_term: any[];
    context: any;
  }> {
    const response = await apiClient.get('/api/director/memory', {
      params: { memory_type: memoryType, limit },
    });
    return response.data;
  },

  /** Добавить знание в базу */
  async addKnowledge(
    title: string,
    content: string,
    category?: string,
    source?: string | null,
    sourceMessageId?: string | null
  ): Promise<{ knowledge: DirectorKnowledge }> {
    const response = await apiClient.post('/api/director/knowledge', {
      title,
      content,
      category: category || 'fact',
      source: source || undefined,
      source_message_id: sourceMessageId || undefined,
    });
    return response.data;
  },

  /** Поиск по базе знаний */
  async searchKnowledge(
    query: string,
    category?: string,
    limit?: number
  ): Promise<{ results: DirectorKnowledge[]; total: number }> {
    const response = await apiClient.get('/api/director/knowledge/search', {
      params: { query, category, limit },
    });
    return response.data;
  },

  /** Поиск по истории чата */
  async searchChat(params: {
    query: string;
    message_type?: string;
    category?: string;
    date_from?: string;
    date_to?: string;
    page?: number;
    limit?: number;
  }): Promise<DirectorSearchResult> {
    const response = await apiClient.get('/api/director/chat/search', { params });
    return response.data;
  },

  /** История чата */
  async chatHistory(params?: {
    session_id?: string;
    message_type?: string;
    category?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ messages: DirectorChatMessage[]; total: number; limit: number; offset: number }> {
    const response = await apiClient.get('/api/director/chat/history', { params });
    return response.data;
  },

  /** Очистить историю чата директора */
  async clearChatHistory(params?: {
    session_id?: string | null;
    include_memory?: boolean;
  }): Promise<{
    status: string;
    deleted_messages: number;
    expired_contexts: number;
    archived_memory: number;
    archived_knowledge: number;
    session_id?: string | null;
  }> {
    const response = await apiClient.delete('/api/director/chat/history', {
      params: {
        session_id: params?.session_id || undefined,
        include_memory: params?.include_memory ?? true,
      },
    });
    return response.data;
  },

  /** Список базы знаний */
  async listKnowledge(params?: {
    category?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ knowledge: DirectorKnowledge[]; total: number; limit: number; offset: number }> {
    const response = await apiClient.get('/api/director/knowledge/list', { params });
    return response.data;
  },

  /** Удалить знание */
  async deleteKnowledge(knowledgeId: string): Promise<{ status: string; knowledge_id: string }> {
    const response = await apiClient.delete(`/api/director/knowledge/${knowledgeId}`);
    return response.data;
  },

  /** Проактивное приветствие директора с текущей сводкой */
  async getGreeting(sessionId?: string | null): Promise<{
    response: string;
    director_message_id: string;
    data_context: string;
    active_tasks_count: number;
  }> {
    const response = await apiClient.get('/api/director/greeting', {
      params: { session_id: sessionId || undefined },
    });
    return response.data;
  },
};
