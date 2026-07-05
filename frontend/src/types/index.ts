export interface Product {
  id: string;
  name: string;
  brand: string | null;
  price: number;
  category: string | null;
  images: string[];
  tags: string[];
  description: string | null;
  article?: string | null;
  vendor_code?: string | null;
  barcode?: string | null;
  unit?: string | null;
  weight?: number | null;
  volume?: number | null;
  country?: string | null;
  warranty?: string | null;
  full_description?: string | null;
  specifications?: Record<string, any> | null;
  external_id?: string | null;
  external_code?: string | null;
  is_active?: boolean;
  sync_status?: string | null;
  sync_metadata?: any;
  stock?: number | null; // Остаток товара (сумма по всем складам)
  is_core_assortment?: boolean;
  supports_brand_concept?: boolean;
}

export interface LookImage {
  url: string;
  generated_at?: string;
  use_default_model?: boolean;
  source?: string;
  type?: string;
}

export interface Look {
  id: string;
  name: string;
  product_ids: string[];
  style: string | null;
  mood: string | null;
  style_values?: string[];
  mood_values?: string[];
  style_dna?: string | null;
  radical?: string | null;
  style_dna_values?: string[];
  radical_values?: string[];
  description: string | null;
  image_url: string | null;
  image_urls?: LookImage[] | string[]; // Массив всех сгенерированных изображений
  current_image_index?: number | null; // Индекс текущего основного изображения
  status?: string | null;
  approval_status?: string | null;
  try_on_image_url?: string | null;
  generation_metadata?: Record<string, any>;
  fashion_trends?: Array<Record<string, any>>;
  client_requirements?: Record<string, any>;
  caption?: string | null;
  media_items?: LookFeedMediaItem[];
  product_layout?: Array<Record<string, any>>;
  source_provider?: string | null;
  source_media_id?: string | null;
  source_permalink?: string | null;
  is_published?: boolean;
  is_new?: boolean;
  published_at?: string | null;
  like_count?: number;
  favorite_count?: number;
  liked_by_me?: boolean;
  favorited_by_me?: boolean;
}

export interface LookWithProducts extends Look {
  products: Product[];
}

export interface LookFeedMediaItem {
  type: 'image' | 'video' | string;
  url: string;
  thumbnail_url?: string | null;
  source?: string | null;
}

export interface LookFeedPost extends LookWithProducts {
  caption: string | null;
  media_items: LookFeedMediaItem[];
  product_layout: Array<Record<string, any>>;
  is_published: boolean;
  published_at: string | null;
  like_count: number;
  favorite_count: number;
  liked_by_me: boolean;
  favorited_by_me: boolean;
}

export interface InstagramPreviewItem {
  instagram_media_id: string;
  media_type: string;
  caption: string;
  timestamp?: string | null;
  permalink?: string | null;
  media_items: LookFeedMediaItem[];
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export interface StylistResponse {
  persona: string;
  cjm_stage: string;
  reply: string;
  looks: LookWithProducts[];
  products?: Product[];  // Отдельный список товаров для карточек
  cta: string;
  session_id: string;
}

export interface QuickAction {
  id: string;
  label: string;
  message: string;
}

export interface AppBanner {
  id: string;
  title: string;
  placement: string;
  media_type: 'image' | 'video';
  image_url: string;
  video_url?: string | null;
  link_url: string | null;
  sort_order: number;
  is_active: boolean;
  starts_at: string | null;
  ends_at: string | null;
  updated_at: string | null;
}

export interface AppHomeSlide {
  id: string;
  block_key: string;
  title: string | null;
  subtitle: string | null;
  background_image_url: string | null;
  image_url: string;
  image_action_link: string | null;
  image_action_type: string | null;
  image_action_payload: Record<string, unknown> | null;
  primary_button_text: string | null;
  primary_button_link: string | null;
  primary_button_action_type: string | null;
  primary_button_action_payload: Record<string, unknown> | null;
  secondary_button_text: string | null;
  secondary_button_link: string | null;
  secondary_button_action_type: string | null;
  secondary_button_action_payload: Record<string, unknown> | null;
  sort_order: number;
  is_active: boolean;
  updated_at: string | null;
}

export interface AppLookbook {
  id: string;
  title: string;
  cover_image_url: string;
  description: string | null;
  items: Array<Record<string, any>>;
  is_published: boolean;
  updated_at: string | null;
}

export type AppPublicationStatus = 'draft' | 'published' | 'archived';

export interface AppPromotion {
  id: string;
  title: string;
  banner_image_url: string | null;
  body: string;
  starts_at: string | null;
  ends_at: string | null;
  status: AppPublicationStatus;
  updated_at: string | null;
}

export interface AppNews {
  id: string;
  title: string;
  preview_image_url: string | null;
  body: string;
  published_at: string | null;
  status: AppPublicationStatus;
  updated_at: string | null;
}

export interface AppStore {
  id: string;
  city: string;
  title: string;
  address: string;
  working_hours: string | null;
  phone: string | null;
  comment: string | null;
  image_url: string | null;
  image_urls?: string[];
  latitude: number | null;
  longitude: number | null;
  slug?: string | null;
  card_image_url?: string | null;
  hero_image_url?: string | null;
  gallery_image_urls?: string[];
  sort_order: number;
  is_active: boolean;
  updated_at: string | null;
}

export interface AppAdminKpiDashboard {
  period: { start: string; end: string };
  sales: { revenue: number; orders: number };
  users: { total: number; customers: number };
  events: { total: number; by_type: Record<string, number> };
}

// ===== Директор AI (система управления маркетингом) =====

export interface DirectorChatMessage {
  id: string;
  user_id: string;
  message: string;
  message_type: string; // text, task, report, approval, knowledge
  message_direction: string; // user, director
  category: string | null;
  priority: string | null;
  session_id: string | null;
  created_at: string; // ISO datetime
  updated_at: string | null;
  vector_id: string | null;
  extra_data: Record<string, any>;
  status: string;
  is_important: boolean;
  parent_message_id: string | null;
  related_task_id: string | null;
}

export interface DirectorChatResponse {
  response: string;
  session_id: string;
  message_type: string;
  category: string;
  priority: string;
  message_id: string;
  response_id: string;
  action: string;
  extracted_task: Record<string, any> | null;
  suggested_knowledge: string | null;
  extra_data?: Record<string, any>;
}

export interface DirectorTask {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  task_type: string;
  target_agent: string | null;
  priority: string;
  status: string;
  deadline_at: string | null;
  created_at: string | null;
  completed_at: string | null;
  assigned_to: string | null;
  execution_notes: string | null;
  result_summary: string | null;
  detailed_result: Record<string, any> | null;
  vector_id: string | null;
  extra_data: Record<string, any>;
  related_message_id: string | null;
}

export interface DirectorMemory {
  id: string;
  user_id: string;
  memory_type: string;
  content: string;
  content_type: string | null;
  vector_id: string | null;
  extra_data: Record<string, any>;
  source_message_id: string | null;
  source_task_id: string | null;
  importance: number;
  relevance_score: number | null;
  created_at: string | null;
  last_accessed_at: string | null;
  expires_at: string | null;
  status: string;
}

export interface DirectorKnowledge {
  id: string;
  user_id: string;
  title: string;
  category: string;
  content: string;
  content_type: string | null;
  vector_id: string | null;
  extra_data: Record<string, any>;
  source: string | null;
  source_message_id: string | null;
  source_task_id: string | null;
  importance: number;
  usage_count: number;
  last_used_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  status: string;
}

export interface DirectorConversationContext {
  id: string;
  user_id: string;
  session_id: string;
  current_topic: string | null;
  current_phase: string | null;
  context_data: Record<string, any>;
  started_at: string | null;
  last_activity_at: string | null;
  expires_at: string | null;
  status: string;
}

export interface DirectorSearchResult {
  messages: DirectorChatMessage[];
  total: number;
  page: number;
  limit: number;
}
