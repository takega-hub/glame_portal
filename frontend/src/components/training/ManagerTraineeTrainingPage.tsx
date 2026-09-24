'use client';

import { useEffect, useMemo, useState } from 'react';
import { Award, ChevronDown, ChevronUp, ClipboardCheck, Plus, Users } from 'lucide-react';
import { apiClient } from '@/lib/api';

type Attestation = {
  status: string;
  ai_score?: number | null;
  ai_evaluation?: { overall_summary?: string; gaps?: string[]; manager_recommendation?: string; assessment_mode?: string; question_results?: Array<{ question_id: string; score: number; max_score: number; status: string; comment: string }> };
  task_payload?: { title?: string; source?: string; questions?: Array<{ id: string; section: string; question: string }> };
  answers?: Record<string, string>;
};

type LessonReport = {
  step_title: string;
  status: string;
  score?: number | null;
  submitted_at?: string | null;
  report: { passed: boolean; correct_answers?: number | null; total_questions?: number | null; duration_seconds?: number | null };
};

type Trainee = {
  seller: { id: string; full_name?: string | null; email?: string | null };
  assigned: boolean;
  progress: { completed_steps: number; total_steps: number; percent: number };
  next_assignment?: { title?: string } | null;
  attestation?: Attestation | null;
  lesson_reports?: LessonReport[];
};

type Dashboard = {
  program: { title: string; description?: string | null };
  summary: { trainees: number; in_progress: number; completed_learning: number; awaiting_review: number };
  trainees: Trainee[];
};

const assessmentStatus: Record<string, string> = {
  draft: 'Не начата', review_pending: 'Ожидает проверки', certified: 'Подтверждена', passed: 'Пройдена', failed: 'Не пройдена', revision_requested: 'Нужна доработка',
};

function durationLabel(value?: number | null) {
  const seconds = Math.max(0, Number(value || 0));
  if (seconds < 60) return `${seconds} сек`;
  return `${Math.floor(seconds / 60)} мин ${seconds % 60} сек`;
}

export default function ManagerTraineeTrainingPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [selectedSellerId, setSelectedSellerId] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.get('/api/manager/training/trainees');
      setData(response.data);
    } catch (cause: any) {
      setError(cause.response?.data?.detail || cause.message || 'Не удалось загрузить обучение стажёров');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);
  const availableSellers = useMemo(() => (data?.trainees || []).filter((item) => !item.assigned), [data]);

  const assign = async () => {
    if (!selectedSellerId) return;
    setAssigning(true);
    setError(null);
    try {
      const response = await apiClient.post('/api/manager/training/trainees/assign', { seller_user_id: selectedSellerId });
      setMessage(response.data?.message || 'Программа стажёра назначена');
      setSelectedSellerId('');
      await load();
    } catch (cause: any) {
      setError(cause.response?.data?.detail || cause.message || 'Не удалось назначить программу');
    } finally {
      setAssigning(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-6xl p-6 text-sm text-slate-500">Загружаем стажёров…</div>;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:py-10">
      <header className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-amber-700">GLAME Academy · кабинет управляющего</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">Стажёры</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Назначайте только программу стажёра, следите за прохождением и смотрите предварительную оценку AI. Настройка программ и материалов доступна только администратору обучения.</p>
        </div>
      </header>

      {error ? <div role="alert" className="mt-5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div> : null}
      {message ? <div role="status" className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">{message}</div> : null}

      <section className="mt-6 grid gap-3 sm:grid-cols-4">
        {[
          ['Стажёров', data?.summary.trainees || 0, Users], ['В обучении', data?.summary.in_progress || 0, ClipboardCheck], ['Закрыли уроки', data?.summary.completed_learning || 0, Award], ['Ждут проверки', data?.summary.awaiting_review || 0, ClipboardCheck],
        ].map(([label, value, Icon]: any) => <div key={label} className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200"><Icon size={18} className="text-amber-700" /><div className="mt-4 text-2xl font-semibold text-slate-950">{value}</div><div className="mt-1 text-sm text-slate-500">{label}</div></div>)}
      </section>

      <section className="mt-6 rounded-3xl bg-slate-950 p-5 text-white shadow-lg sm:p-7">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-amber-300">Назначить обучение</p>
        <h2 className="mt-1 text-xl font-semibold">{data?.program.title || 'Программа стажёра'}</h2>
        <p className="mt-2 text-sm text-slate-300">{data?.program.description || 'Новый продавец получит последовательный учебный маршрут.'}</p>
        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
          <select value={selectedSellerId} onChange={(event) => setSelectedSellerId(event.target.value)} className="min-w-0 flex-1 rounded-xl border border-white/10 bg-white px-4 py-3 text-sm text-slate-950 outline-none">
            <option value="">Выберите нового продавца</option>
            {availableSellers.map((item) => <option key={item.seller.id} value={item.seller.id}>{item.seller.full_name || item.seller.email || 'Продавец'}</option>)}
          </select>
          <button type="button" onClick={assign} disabled={!selectedSellerId || assigning} className="inline-flex items-center justify-center gap-2 rounded-xl bg-amber-300 px-5 py-3 text-sm font-semibold text-slate-950 disabled:bg-slate-500"><Plus size={17} />{assigning ? 'Назначаем…' : 'Назначить программу'}</button>
        </div>
      </section>

      <section className="mt-6 rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:p-7">
        <div><p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">Контроль обучения</p><h2 className="mt-1 text-xl font-semibold text-slate-950">Прогресс и итоговая проверка</h2></div>
        <div className="mt-5 space-y-3">
          {(data?.trainees || []).filter((item) => item.assigned).map((item) => {
            const exam = item.attestation;
            const opened = expandedId === item.seller.id;
            const latestLessonReport = item.lesson_reports?.[0];
            return <article key={item.seller.id} className="rounded-2xl border border-slate-200 p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div><h3 className="font-semibold text-slate-950">{item.seller.full_name || item.seller.email || 'Продавец'}</h3><p className="mt-1 text-sm text-slate-500">{item.next_assignment?.title ? `Следующий урок: ${item.next_assignment.title}` : item.progress.percent >= 100 ? 'Уроки завершены — можно пройти итоговую проверку' : 'Ожидается следующий урок'}</p></div>
                <div className="text-right"><div className="text-lg font-semibold text-slate-950">{item.progress.percent}%</div><div className="text-xs text-slate-500">{item.progress.completed_steps} из {item.progress.total_steps} уроков</div></div>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-slate-950" style={{ width: `${item.progress.percent}%` }} /></div>
              {latestLessonReport ? <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-100 bg-emerald-50/60 px-4 py-3 text-sm"><span className="text-slate-700"><b>Последний урок:</b> {latestLessonReport.step_title}</span><span className={latestLessonReport.report.passed ? 'font-semibold text-emerald-800' : 'font-semibold text-amber-800'}>{latestLessonReport.report.correct_answers}/{latestLessonReport.report.total_questions} · {durationLabel(latestLessonReport.report.duration_seconds)}</span></div> : null}
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 px-4 py-3 text-sm"><span className="text-slate-600">Итоговая проверка: <b className="text-slate-950">{exam ? (assessmentStatus[exam.status] || exam.status) : 'Ещё не открыта'}</b></span>{exam?.ai_score !== null && exam?.ai_score !== undefined ? <span className="font-semibold text-amber-800">AI: {exam.ai_score}/100</span> : null}{(exam || item.lesson_reports?.length) ? <button type="button" onClick={() => setExpandedId(opened ? null : item.seller.id)} className="inline-flex items-center gap-1 font-semibold text-slate-900">{opened ? <>Скрыть <ChevronUp size={16} /></> : <>Открыть результаты <ChevronDown size={16} /></>}</button> : null}</div>
              {opened && item.lesson_reports?.length ? <div className="mt-4 rounded-2xl border border-slate-200 p-4"><p className="text-sm font-semibold text-slate-950">Отчёты по урокам</p><div className="mt-3 space-y-2">{item.lesson_reports.map((report, index) => <div key={`${report.step_title}-${index}`} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-3 text-sm"><span className="font-medium text-slate-800">{report.step_title}</span><span className={report.report.passed ? 'text-emerald-700' : 'text-amber-700'}>{report.report.passed ? 'Пройден' : 'Повторить'} · {report.report.correct_answers}/{report.report.total_questions} · {durationLabel(report.report.duration_seconds)}</span></div>)}</div></div> : null}
              {opened && exam ? <div className="mt-4 rounded-2xl border border-amber-100 bg-amber-50/60 p-4 text-sm text-slate-700"><p className="font-semibold text-slate-950">{exam.task_payload?.title || 'Итоговая проверка'} · {exam.task_payload?.source || 'GLAME'}</p><p className="mt-2 leading-6">{exam.ai_evaluation?.overall_summary || 'Результат появится после отправки ответов.'}</p>{exam.ai_evaluation?.gaps?.length ? <p className="mt-3"><b>Темы для разбора:</b> {exam.ai_evaluation.gaps.join(', ')}</p> : null}<p className="mt-3"><b>Рекомендация AI:</b> {exam.ai_evaluation?.manager_recommendation || 'Ожидается отправка ответов.'}</p><div className="mt-4 space-y-3">{(exam.task_payload?.questions || []).map((question) => { const result = exam.ai_evaluation?.question_results?.find((value) => value.question_id === question.id); return <div key={question.id} className="rounded-xl bg-white p-3"><p className="font-medium text-slate-950">{question.section}: {question.question}</p><p className="mt-2 whitespace-pre-wrap text-slate-600"><b>Ответ:</b> {exam.answers?.[question.id] || 'Нет ответа'}</p>{result ? <p className="mt-2 text-xs text-slate-500">Оценка {result.score}/{result.max_score} · {result.comment}</p> : null}</div>; })}</div></div> : null}
            </article>;
          })}
          {!data?.summary.trainees ? <div className="rounded-2xl bg-slate-50 p-5 text-sm text-slate-600">Пока никому не назначена программа стажёра. Выберите продавца выше.</div> : null}
        </div>
      </section>
    </div>
  );
}
