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
}

export interface LookImage {
  url: string;
  generated_at?: string;
  use_default_model?: boolean;
}

export interface Look {
  id: string;
  name: string;
  product_ids: string[];
  style: string | null;
  mood: string | null;
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
}

export interface LookWithProducts extends Look {
  products: Product[];
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
