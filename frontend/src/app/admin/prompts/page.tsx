'use client';

import { useState } from 'react';
import SystemPromptPanel from '@/components/content/SystemPromptPanel';
import ModelDropdown from '@/components/ai/ModelDropdown';

// Согласно иерархии AI-агентов из ТЗ GLAME AI Platform
const AGENTS = [
  // Основные маркетинговые агенты из иерархии
  { 
    id: 'director-agent', 
    name: '🤖 AI Marketing Director (главный)',
    description: 'Центральный управляющий агент системы. Собирает бизнес-данные из всех источников (1С, соцсети, аналитика, CRM), переводит бизнес-задачи в маркетинговые задачи для всех остальных агентов, формирует ежедневные/недельные/месячные отчеты, контролирует статусы всех задач, отправляет план на согласование Елене. Взаимодействует со всеми агентами системы.'
  },
  { 
    id: 'personal-media-agent', 
    name: '👤 AI Personal Media (блог Елены)',
    description: 'Управляет личным медиа-блогом Елены как отдельным контуром. Создает и публикует контент для личного бренда, взаимодействует с аудиторией в комментариях, анализирует вовлеченность. Передает задачи контент-продюсеру, отчитывается в AI Marketing Director.'
  },
  { 
    id: 'brand-media-agent', 
    name: '🏷️ AI Brand Media (GLAME бренд)',
    description: 'Управляет всеми брендовыми медиа GLAME, поддерживает единую идентичность бренда. Адаптирует контент под городские среды: Симферополь (классика/драматизм) и Ялта (курорт/романтика/натурализм). Планирует публикации, получает материалы от контент-продюсера, отчитывается в AI Marketing Director.'
  },
  { 
    id: 'crm-agent', 
    name: '💬 AI CRM (клиентские коммуникации)',
    description: 'Управляет всеми CRM-коммуникациями с клиентами: рассылки, уведомления, программы лояльности. Анализирует сегменты покупателей, запускает персонализированные кампании, отслеживает эффективность коммуникаций. Взаимодействует с системой лояльности, отчитывается в AI Marketing Director.'
  },
  { 
    id: 'pr-partnerships-agent', 
    name: '📢 AI PR & Partnerships',
    description: 'Управляет PR-активностями и партнерскими программами. Ищет и согласовывает коллаборации с инфлюенсерами и другими брендами, готовит пресс-релизы, контролирует выполнение партнерских условий. Взаимодействует с PR-менеджером, отчитывается в AI Marketing Director.'
  },
  { 
    id: 'traffic-growth-agent', 
    name: '🚀 AI Traffic & Growth',
    description: 'Отвечает за привлечение трафика и рост аудитории во всех каналах: соцсети, сайт, приложение. Анализирует эффективность рекламных кампаний, оптимизирует бюджеты, предлагает точки роста. Взаимодействует с аналитическими системами (Яндекс.Метрика), отчитывается в AI Marketing Director.'
  },
  { 
    id: 'assortment-agent', 
    name: '📦 AI Assortment (ассортимент)',
    description: 'Управляет ассортиментной политикой бренда. Анализирует остатки на складах, выявляет топ-продаваемые товары, формирует рекомендации по расширению или сокращению ассортимента, готовит планы по запуску новых коллекций. Взаимодействует с управляющими и стилистами, отчитывается в AI Marketing Director.'
  },
  { 
    id: 'analytics-agent', 
    name: '📉 AI Analytics (аналитика)',
    description: 'Собирает и анализирует все данные системы: продажи, трафик, вовлеченность, конверсии. Генерирует отчеты по всем метрикам, выявляет тренды, строит прогнозы. Взаимодействует со всеми агентами, поставляет данные AI Marketing Director для формирования стратегических отчетов.'
  },
  
  // Остальные системные агенты
  { 
    id: 'content-agent', 
    name: '✍️ AI Контент-агент',
    description: 'Вспомогательный агент для генерации и планирования контента. Получает ТЗ от AI Personal Media или AI Brand Media, генерирует варианты контента, планирует публикации по календарю. Передает готовый контент на утверждение.'
  },
  { id: 'stylist', name: 'AI Стилист', description: 'Создает рекомендации по стилю, собирает образы для клиентов, анализирует предпочтения покупателей. Взаимодействует с модулями примерки образов в приложении.' },
  { id: 'photo-analysis-interpreter', name: 'Агент описания внешности по фото', description: 'Анализирует загруженные пользователями фото, определяет особенности внешности, подбирает релевантные товары и стилистические решения.' },
  { id: 'manual-look-copywriter', name: 'Ручные образы: название и описание', description: 'Генерирует названия и описания для созданных вручную образов, подготавливает их к публикации в каталоге приложения.' },
  { id: 'inventory-procurement-agent', name: 'Агент закупок', description: 'Планирует и контролирует процесс закупок, анализирует потребность в товарах, взаимодействует с поставщиками. Работает в связке с AI Assortment.' },
  { id: 'inventory-control-agent', name: 'Агент контроля запасов', description: 'Отслеживает остатки на складах, автоматизирует процессы пополнения, предупреждает о рисках дефицита или перезакупа. Взаимодействует с 1С.' },
  { id: 'clearance-agent', name: 'Агент чистки склада', description: 'Анализирует неликвидные товары, формирует рекомендации по распродажам, планирует акции по очистке склада от остатков.' },
  { id: 'assortment-matrix-agent', name: 'Агент матрицы ассортимента', description: 'Поддерживает и актуализирует матрицу ассортимента, следит за балансом ценовых сегментов и категорий товаров. Работает с AI Assortment.' },
  { id: 'merchandising-agent', name: 'Агент мерчандайзинга', description: 'Планирует выкладку товаров в магазинах, генерирует рекомендации по презентации коллекций, анализирует эффективность мерчандайзинговых решений.' },
  { id: 'pricing-agent', name: 'Ценообразование', description: 'Анализирует рынок, формирует рекомендации по ценообразованию, управляет скидками и акциями, отслеживает маржинальность.' },
  { id: 'marketing-inventory-agent', name: 'Агент «Маркетинг и склад»', description: 'Синхронизирует маркетинговые кампании с складскими остатками, планирует рекламные активности под наличие товаров. Связывает маркетинг и логистику.' },
  { id: 'training-material-reformatter-agent', name: '🎓 Агент учебных материалов', description: 'Переформатирует загруженные исходники/PDF/DOC/Markdown в draft learning pack для обучения продавцов: слайды, практику, шаблон ответа, критерии проверки и admin-only visual/speaker notes. Не публикует без проверки руководителя.' },
];

export default function PromptsAdminPage() {
  const [selectedAgent, setSelectedAgent] = useState(AGENTS[0].id);
  const [dialogModel, setDialogModel] = useState<string | null>(null);
  const [segModel, setSegModel] = useState<string | null>(null);

  return (
    <div className="max-w-7xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Управление системными промптами</h1>
      
      {/* Настройки моделей ИИ - перенесены с главного дашборда, здесь они более уместны */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-xl font-bold text-gray-900 mb-4">Настройки моделей ИИ</h2>
        <p className="text-gray-600 mb-4">Выберите какие LLM-модели будут использоваться для диалогов с агентами и сегментации аудитории.</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ModelDropdown
            category="dialog"
            taskType="dialog"
            label="Модель для диалогов"
            onChange={(m) => setDialogModel(m)}
            requireSelection
          />
          <ModelDropdown
            category="segmentation"
            taskType="customer_segmentation"
            label="Модель для сегментации"
            onChange={(m) => setSegModel(m)}
            requireSelection
          />
        </div>
      </div>
      
      <div className="mb-8">
        <label className="block text-sm font-medium text-gray-700 mb-2">Выберите агента</label>
        <div className="flex gap-2 flex-wrap mb-6">
          {AGENTS.map((agent) => (
            <button
              key={agent.id}
              onClick={() => setSelectedAgent(agent.id)}
              className={`px-4 py-2 rounded-lg transition-colors ${
                selectedAgent === agent.id
                  ? 'bg-pink-600 text-white'
                  : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              {agent.name}
            </button>
          ))}
        </div>

        {/* Описание выбранного агента */}
        {AGENTS.find(a => a.id === selectedAgent)?.description && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-5">
            <h3 className="font-bold text-lg text-blue-900 mb-2">
              {AGENTS.find(a => a.id === selectedAgent)?.name}
            </h3>
            <p className="text-blue-800 leading-relaxed">
              {AGENTS.find(a => a.id === selectedAgent)?.description}
            </p>
          </div>
        )}
      </div>

      <div key={selectedAgent}>
        <SystemPromptPanel agentType={selectedAgent} />
      </div>
    </div>
  );
}
