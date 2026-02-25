import axios from 'axios';

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
          });
          
          const { access_token, refresh_token } = response.data;
          localStorage.setItem('glame_access_token', access_token);
          localStorage.setItem('glame_refresh_token', refresh_token);
          
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
          return apiClient(originalRequest);
        }
      } catch (refreshError) {
        // Если refresh token невалиден, перенаправляем на логин
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

export interface ImageGenerationModelSettingsResponse {
  image_generation_model: string;
  source: 'db' | 'env' | 'default';
}

export interface ImageGenerationModelSettingsUpdateRequest {
  image_generation_model: string;
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
  }): Promise<{ status: string; message: string; task_id?: string; status_url?: string }> {
    const response = await apiClient.post('/api/products/sync-xml', null, {
      params: {
        xml_url: xmlUrl,
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
  }) {
    const response = await apiClient.get('/api/looks', { params });
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
  }) {
    try {
      const response = await apiClient.post('/api/looks/generate', request, {
        timeout: 600000, // 10 минут для генерации образа (включая генерацию изображения)
      });
      return response.data;
    } catch (error: any) {
      // Обработка таймаутов
      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        throw new Error('Генерация образа занимает больше времени, чем ожидалось. Пожалуйста, подождите - образ может быть создан в фоновом режиме. Проверьте список образов через несколько минут.');
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
    useDefaultModel: boolean = false
  ): Promise<{ look_id: string; image_url: string; use_default_model: boolean }> {
    const response = await apiClient.post<{ look_id: string; image_url: string; use_default_model: boolean }>(
      `/api/looks/${lookId}/generate-image`,
      null,
      {
        params: { use_default_model: useDefaultModel },
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
    description?: string;
    product_ids?: string[];
    regenerate_image?: boolean;
    use_default_model?: boolean;
  }) {
    // Если запрашивается перегенерация изображения, используем отдельный endpoint
    if (request.regenerate_image) {
      return await api.generateLookImage(lookId, request.use_default_model || false);
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
  async uploadUserPhoto(photo: File, userId: string) {
    const formData = new FormData();
    formData.append('photo', photo);
    
    const response = await apiClient.post('/api/look-tryon/upload-photo', formData, {
      params: { user_id: userId },
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
    user_id?: string;
    look_id?: string;
    user_request?: string;
  }, photo: File) {
    const formData = new FormData();
    formData.append('photo', photo);
    
    // Добавляем параметры в FormData
    if (request.user_id) {
      formData.append('user_id', request.user_id);
    }
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

  async getOpenRouterModels(params?: { force_refresh?: boolean }): Promise<OpenRouterModelsResponse> {
    const response = await apiClient.get<OpenRouterModelsResponse>('/api/settings/openrouter/models', { params });
    return response.data;
  },

  async getOpenRouterImageModels(params?: { force_refresh?: boolean }): Promise<OpenRouterModelsResponse> {
    const response = await apiClient.get<OpenRouterModelsResponse>('/api/settings/openrouter/image-models', { params });
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

  async processJewelryPhoto(
    files: File[],
    article: string,
    signal?: AbortSignal,
    revisionDescription?: string
  ): Promise<{ urls: string[] }> {
    const form = new FormData();
    form.append('article', article.trim());
    if (revisionDescription?.trim()) {
      form.append('revision_description', revisionDescription.trim());
    }
    if (files.length === 1) {
      form.append('file', files[0]);
    } else {
      files.forEach((f) => form.append('files', f));
    }
    const response = await apiClient.post<{ urls: string[] }>(
      '/api/content/jewelry-photo/process',
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000,
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

export interface CustomerMessageItem {
  id: string;
  message: string;
  cta: string | null;
  segment: string | null;
  event_type: string | null;
  event_brand: string | null;
  event_store: string | null;
  status: 'new' | 'sent';
  sent_at: string | null;
  created_at: string;
}

export interface CustomerMessagesListResponse {
  items: CustomerMessageItem[];
  total: number;
}

export const communication = {
  async generateMessage(request: GenerateMessageRequest): Promise<GenerateMessageResponse> {
    const response = await apiClient.post<GenerateMessageResponse>(
      '/api/communication/generate-message',
      request
    );
    return response.data;
  },

  async getCustomerMessages(customerId: string, limit?: number, offset?: number): Promise<CustomerMessagesListResponse> {
    const response = await apiClient.get<CustomerMessagesListResponse>(
      `/api/communication/customers/${customerId}/messages`,
      { params: { limit: limit ?? 50, offset: offset ?? 0 } }
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

  async getClientsByBrand(brand: string, limit: number = 100): Promise<{ client_ids: string[]; count: number }> {
    const response = await apiClient.get('/api/communication/clients/by-brand', {
      params: { brand, limit }
    });
    return response.data;
  },

  async getClientData(clientId: string): Promise<any> {
    const response = await apiClient.get(`/api/communication/clients/${clientId}/data`);
    return response.data.client;
  },
};
