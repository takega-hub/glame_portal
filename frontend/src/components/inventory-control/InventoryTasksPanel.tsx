'use client';

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StoreSelect } from '@/components/inventory-control/StoreSelect';
import { PeriodSelect, type InventoryPeriodPreset } from '@/components/inventory-control/PeriodSelect';

type AgentId =
  | 'inventory-procurement-agent'
  | 'inventory-control-agent'
  | 'clearance-agent'
  | 'assortment-matrix-agent'
  | 'merchandising-agent'
  | 'pricing-agent'
  | 'marketing-inventory-agent';

const AGENTS: Array<{ id: AgentId; name: string }> = [
  { id: 'inventory-procurement-agent', name: 'Агент закупок' },
  { id: 'inventory-control-agent', name: 'Агент контроля запасов' },
  { id: 'clearance-agent', name: 'Агент чистки склада' },
  { id: 'assortment-matrix-agent', name: 'Агент матрицы ассортимента' },
  { id: 'merchandising-agent', name: 'Агент мерчандайзинга' },
  { id: 'pricing-agent', name: 'Ценообразование' },
  { id: 'marketing-inventory-agent', name: 'Агент «Маркетинг и склад»' },
];

export function InventoryTasksPanel() {
  const [agent, setAgent] = useState<AgentId>('inventory-procurement-agent');
  const [periodPreset, setPeriodPreset] = useState<InventoryPeriodPreset>('days');
  const [analysisPeriodDays, setAnalysisPeriodDays] = useState(90);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [storeId, setStoreId] = useState('');
  const [limit, setLimit] = useState(2000);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [taskId, setTaskId] = useState<string | null>(null);

  const run = async () => {
    try {
      setRunning(true);
      setResult(null);
      setTaskId(null);

      const createRes = await fetch('/api/agent-interactions/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_agent: 'ui',
          target_agent: agent,
          task_type: 'inventory_control',
          task_context: { module: 'product-analytics', source_tab: 'inventory-ai-tasks' },
          input_data: {
            analysis_period_days: analysisPeriodDays,
            period: periodPreset === 'days' ? undefined : periodPreset,
            start_date: periodPreset === 'custom' ? startDate : undefined,
            end_date: periodPreset === 'custom' ? endDate : undefined,
            store_id: storeId || undefined,
            limit,
          },
          priority: 3,
          timeout_seconds: 300,
        }),
      });
      if (!createRes.ok) throw new Error('Ошибка создания задачи');
      const created = await createRes.json();
      const id = created?.task_id || created?.id;
      if (!id) throw new Error('Не удалось получить task_id');
      setTaskId(String(id));

      const processRes = await fetch(`/api/agent-interactions/tasks/${id}/process`, { method: 'POST' });
      if (!processRes.ok) throw new Error('Ошибка выполнения задачи');
      const processed = await processRes.json();
      setResult(processed);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>ИИ-задачи по товару и запасам</CardTitle>
        <CardDescription>
          Запуск агентов закупок, контроля запасов, чистки склада, матрицы ассортимента и связки «маркетинг + склад» из единого раздела товарной аналитики.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1 block">Агент</label>
            <select
              value={agent}
              onChange={(e) => setAgent(e.target.value as AgentId)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm bg-white"
            >
              {AGENTS.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <PeriodSelect
              value={periodPreset}
              onChange={setPeriodPreset}
              days={analysisPeriodDays}
              onDaysChange={setAnalysisPeriodDays}
              startDate={startDate}
              endDate={endDate}
              onStartDateChange={setStartDate}
              onEndDateChange={setEndDate}
            />
          </div>
          <StoreSelect label="Магазин" value={storeId} onChange={setStoreId} />
          <InputNumber label="Лимит" value={limit} onChange={setLimit} />
        </div>

        <Button onClick={run} disabled={running}>
          {running ? 'Выполняется…' : 'Запустить'}
        </Button>

        {taskId && <div className="text-sm text-gray-600">task_id: {taskId}</div>}

        {result && (
          <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-3 overflow-x-auto">
            {JSON.stringify(result, null, 2)}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}

function InputNumber({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <div>
      <label className="text-sm font-medium text-gray-700 mb-1 block">{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseInt(e.target.value || '0', 10))}
        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
      />
    </div>
  );
}
