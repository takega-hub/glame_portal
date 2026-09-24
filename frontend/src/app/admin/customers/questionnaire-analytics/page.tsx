'use client';

import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api';
import { Bar, BarChart, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

type Row = { value: string; count: number; share_pct: number };
type Analytics = {
  total_customers: number;
  questionnaires: number;
  coverage_pct: number;
  marketing_consent: number;
  do_not_contact: number;
  contactable: number;
  breakdowns: Record<string, Row[]>;
  performance: Record<string, Array<Row & { respondents: number; buyers: number; buyer_rate_pct: number; revenue_rub: number; revenue_per_respondent_rub: number }>>;
};

const COLORS = ['#8a6a4b', '#c6a780', '#2f2924', '#cf9f95', '#758b6c', '#9f8cae'];

const sections: Array<[string, string]> = [
  ['recommended_contact_channels', 'С какого канала CRM начинать'],
  ['contact_channels', 'Удобные каналы связи'],
  ['purchase_for', 'Для кого выбирают украшения'],
  ['glame_values', 'Что важно в GLAME'],
  ['discovery_channels', 'Как узнали о GLAME'],
  ['cities', 'Города'],
];

function Breakdown({ title, rows }: { title: string; rows: Row[] }) {
  return <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm"><h2 className="font-semibold text-gray-950">{title}</h2>{rows.length ? <div className="mt-4 space-y-3">{rows.map((row) => <div key={row.value}><div className="flex justify-between gap-3 text-sm"><span>{row.value}</span><span className="whitespace-nowrap text-gray-500">{row.count} · {row.share_pct}%</span></div><div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-100"><div className="h-full rounded-full bg-[#8a6a4b]" style={{ width: `${Math.min(row.share_pct, 100)}%` }} /></div></div>)}</div> : <p className="mt-4 text-sm text-gray-500">Данных пока нет.</p>}</section>;
}

function Donut({ title, rows }: { title: string; rows: Row[] }) {
  const data = rows.slice(0, 6).map((row) => ({ name: row.value, value: row.count }));
  return <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm"><h2 className="font-semibold text-gray-950">{title}</h2>{data.length ? <><div className="mt-2 h-72"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data} dataKey="value" nameKey="name" innerRadius={60} outerRadius={100} paddingAngle={3}>{data.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}</Pie><Tooltip formatter={(value) => [`${Number(value || 0)} анкет`, 'Ответов']} /><Legend /></PieChart></ResponsiveContainer></div><p className="text-xs text-gray-500">Один клиент мог выбрать несколько вариантов.</p></> : <p className="mt-4 text-sm text-gray-500">Данных пока нет.</p>}</section>;
}

function Performance({ title, rows }: { title: string; rows: Analytics['performance'][string] }) {
  const data = rows.slice(0, 7).map((row) => ({ name: row.value, 'Выручка на клиента': Math.round(row.revenue_per_respondent_rub) }));
  return <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm lg:col-span-2"><h2 className="font-semibold text-gray-950">{title}</h2><p className="mt-1 text-sm text-gray-500">Связь анкетных ответов с фактическими покупками и выручкой из 1С.</p>{data.length ? <><div className="mt-3 h-72"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout="vertical" margin={{ left: 18 }}><XAxis type="number" /><YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 12 }} /><Tooltip /><Legend /><Bar dataKey="Выручка на клиента" fill="#8a6a4b" radius={[0, 4, 4, 0]} /><Bar dataKey="Конверсия в покупку" fill="#758b6c" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer></div><div className="overflow-x-auto"><table className="min-w-full text-sm"><thead className="text-left text-gray-500"><tr><th>Ответ</th><th>Анкет</th><th>Покупателей</th><th>Конверсия</th><th>Выручка</th></tr></thead><tbody>{rows.map((row) => <tr key={row.value} className="border-t"><td className="py-2 font-medium">{row.value}</td><td>{row.respondents}</td><td>{row.buyers}</td><td>{row.buyer_rate_pct}%</td><td>{Math.round(row.revenue_rub).toLocaleString('ru-RU')} ₽</td></tr>)}</tbody></table></div></> : <p className="mt-4 text-sm text-gray-500">Появится после заполнения анкет и синхронизации покупок.</p>}</section>;
}

export default function QuestionnaireAnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { apiClient.get<Analytics>('/api/admin/customers/analytics/questionnaire').then((response) => setData(response.data)).catch((err) => setError(err?.response?.data?.detail || 'Не удалось загрузить аналитику анкет.')); }, []);
  if (error) return <main className="p-6 text-red-700">{error}</main>;
  if (!data) return <main className="p-6 text-gray-500">Загружаем аналитику анкет…</main>;
  return <main className="mx-auto max-w-6xl space-y-6 p-2"><header><p className="text-sm font-medium uppercase tracking-widest text-[#8a6a4b]">Покупатели</p><h1 className="mt-1 text-3xl font-semibold text-gray-950">Дашборд анкет</h1><p className="mt-2 text-gray-600">Обезличенная сводка для CRM, маркетинга и AI-агентов. Блок «Не беспокоить» исключается из маркетинговых касаний.</p></header><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><Metric label="Анкет заполнено" value={data.questionnaires} note={`${data.coverage_pct}% клиентской базы`} /><Metric label="Можно написать" value={data.contactable} note="есть разрешённый канал" /><Metric label="Согласие на новости" value={data.marketing_consent} note="аудитория для кампаний" /><Metric label="Не беспокоить" value={data.do_not_contact} note="исключать из касаний" danger /></div><div className="grid gap-5 lg:grid-cols-2"><Donut title="Откуда узнают о GLAME" rows={data.breakdowns.discovery_channels || []} /><Donut title="Удобные каналы связи" rows={data.breakdowns.contact_channels || []} /></div><div className="grid gap-5 lg:grid-cols-2">{sections.slice(2).map(([key, title]) => <Breakdown key={key} title={title} rows={data.breakdowns[key] || []} />)}</div><div className="grid gap-5 lg:grid-cols-2"><Performance title="Качество источников: выручка и конверсия" rows={data.performance.discovery_channels || []} /><Performance title="Мотив покупки и фактические продажи" rows={data.performance.purchase_for || []} /><Performance title="Ценности бренда и фактические продажи" rows={data.performance.glame_values || []} /></div></main>;
}

function Metric({ label, value, note, danger = false }: { label: string; value: number; note: string; danger?: boolean }) { return <div className={`rounded-2xl border p-5 ${danger ? 'border-rose-200 bg-rose-50' : 'border-gray-200 bg-white'}`}><p className="text-sm text-gray-600">{label}</p><p className="mt-2 text-3xl font-semibold text-gray-950">{value}</p><p className="mt-1 text-xs text-gray-500">{note}</p></div>; }
