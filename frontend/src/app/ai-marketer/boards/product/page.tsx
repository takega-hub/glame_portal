'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import AgentBoardChat from '@/components/agents/AgentBoardChat';
import BoardHeader from '@/components/boards/BoardHeader';
import { InventoryAssortmentStructurePanel } from '@/components/inventory-control/InventoryAssortmentStructurePanel';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { agentInteractions, aiMarketer, apiClient, type AgentInteractionTask } from '@/lib/api';

type ProductRow = {
  id: string;
  name: string;
  brand: string;
  cityAvailability: string[];
  salesAnalytics: number;
  stockStatus: string;
  campaignFit: boolean;
  href?: string;
  raw?: Record<string, any>;
};

const formatNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });

function taskTitle(task: AgentInteractionTask) {
  return task.input_data?.title || task.task_context?.title || task.task_type.replaceAll('_', ' ');
}

function isProductTask(task: AgentInteractionTask) {
  const text = `${task.source_agent} ${task.target_agent} ${task.task_type}`.toLowerCase();
  return text.includes('product') || text.includes('assortment') || text.includes('inventory') || text.includes('stock');
}

export default function ProductFocusBoard() {
  const router = useRouter();
  const [inventory, setInventory] = useState<Record<string, any> | null>(null);
  const [marketingLink, setMarketingLink] = useState<Record<string, any> | null>(null);
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    const [inventoryData, marketingData, loadedTasks] = await Promise.all([
      apiClient.get<Record<string, any>>('/api/inventory/dashboard?period=month').then((response) => response.data).catch(() => null),
      apiClient.get<Record<string, any>>('/api/inventory/marketing-link?period=month&limit=50').then((response) => response.data).catch(() => null),
      agentInteractions.listTasks({ limit: 150 }).then((items) => items.filter(isProductTask)).catch(() => []),
    ]);
    setInventory(inventoryData);
    setMarketingLink(marketingData);
    setTasks(loadedTasks);
    setLoading(false);
  }

  async function createProductTask(seed?: Partial<ProductRow>) {
    setCreating(true);
    setError(null);
    try {
      const { task: created } = await aiMarketer.ensureBoardTask('product', {
        source_agent: 'product-board',
        target_agent: 'assortment-agent',
        task_type: 'product_focus',
        priority: seed?.stockStatus === 'critical' || seed?.stockStatus === 'low' ? 1 : 2,
        input_data: {
          title: seed?.name ? `Разобрать продуктовый фокус: ${seed.name}` : 'Подготовить продуктовый фокус',
          description: 'Связать ассортимент, остатки, продажи и маркетинговые кампании',
          expected_result: 'Список товарных решений: продвигать, дозаказать, распродать, исключить из кампаний',
          product: seed,
          source_board: 'product',
        },
        task_context: {
          board: 'product',
          created_from: 'product_focus_board',
          inventory_snapshot: inventory,
          marketing_link_snapshot: marketingLink,
        },
      });
      router.push(`/ai-marketer/tasks/${created.id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось создать продуктовую задачу');
    } finally {
      setCreating(false);
    }
  }

  const products = useMemo<ProductRow[]>(() => {
    const rows = marketingLink?.items || marketingLink?.products || marketingLink?.data || marketingLink?.recommendations || [];
    if (Array.isArray(rows) && rows.length > 0) {
      return rows.slice(0, 12).map((item: any, idx: number) => ({
        id: String(item.id || item.product_id || item.product_id_1c || idx),
        name: item.name || item.product_name || item.title || 'Товар',
        brand: item.brand || item.brand_name || '—',
        cityAvailability: [item.city, item.store_city, item.store_name].filter(Boolean),
        salesAnalytics: Number(item.sales_qty ?? item.sold_qty ?? item.sales_count ?? item.quantity_sold ?? 0),
        stockStatus: item.stock_status || item.status || (Number(item.stock_qty ?? item.quantity ?? 0) <= 1 ? 'low' : 'in_stock'),
        campaignFit: Boolean(item.campaign_fit ?? item.marketing_fit ?? item.recommended ?? item.priority),
        raw: item,
      }));
    }
    return tasks.slice(0, 8).map((task) => ({
      id: task.id,
      name: taskTitle(task),
      brand: task.input_data?.brand || 'Задача',
      cityAvailability: [task.input_data?.city].filter(Boolean),
      salesAnalytics: Number(task.input_data?.sales_qty || task.output_data?.sales_qty || 0),
      stockStatus: task.status,
      campaignFit: Boolean(task.input_data?.campaign || task.task_context?.campaign),
      href: `/ai-marketer/tasks/${task.id}`,
    }));
  }, [marketingLink, tasks]);

  return (
    <div className="min-h-screen bg-gray-50">
      <BoardHeader
        title="Product Focus Board"
        description="Ассортимент, остатки 1С, продажи и связь товарной матрицы с маркетинговыми задачами."
        boardId="product"
        actions={<Button variant="default" size="sm" onClick={() => createProductTask()} disabled={creating}>{creating ? 'Создание...' : 'Создать фокус'}</Button>}
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {error && <Card className="p-3 text-sm text-red-700 border-red-200 bg-red-50">{error}</Card>}
        <AgentBoardChat
          agentId="assortment-agent"
          agentName="AI Assortment"
          boardId="product"
          aliases={['marketing-inventory-agent', 'product-board', 'inventory']}
        />

        <section>
          <div className="flex items-center justify-between gap-3 mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Текущий фокус: товары</h2>
            <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>Обновить</Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {loading ? <Card className="p-5 text-sm text-gray-500">Загрузка...</Card> : null}
            {!loading && products.length === 0 ? <Card className="p-5 text-sm text-gray-500">Нет данных product focus. Проверьте inventory marketing-link или создайте задачу.</Card> : null}
            {products.map((product) => (
              <Card key={product.id} className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <Badge>{product.brand}</Badge>
                      {product.cityAvailability.map((city) => <Badge key={city} variant="outline">{city}</Badge>)}
                      <Badge className={product.stockStatus === 'in_stock' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}>{product.stockStatus}</Badge>
                    </div>
                    <h3 className="font-medium text-gray-900">{product.name}</h3>
                    <div className="grid grid-cols-2 gap-4 mt-3 text-sm">
                      <Metric label="Продано за месяц" value={`${formatNumber.format(product.salesAnalytics)} шт.`} />
                      <Metric label="Используется в кампаниях" value={product.campaignFit ? 'Да' : 'Нет'} />
                    </div>
                    <p className="text-xs text-gray-500 mt-2">Критические остатки: {formatNumber.format(Number(inventory?.stock?.critical_count || 0))}</p>
                  </div>
                  {product.href ? <LinkButton href={product.href}>Детали</LinkButton> : <Button size="sm" variant="outline" onClick={() => createProductTask(product)} disabled={creating}>В задачу</Button>}
                </div>
              </Card>
            ))}
          </div>
        </section>

        <InventoryAssortmentStructurePanel />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><p className="text-gray-500">{label}</p><p className="font-medium">{value}</p></div>;
}

function LinkButton({ href, children }: { href: string; children: React.ReactNode }) {
  return <Link href={href} className="inline-flex h-9 items-center rounded-md border px-3 text-sm font-medium hover:bg-gray-50">{children}</Link>;
}
