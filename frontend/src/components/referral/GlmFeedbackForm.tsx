'use client';

import { useState } from 'react';
import { Send } from 'lucide-react';

const isValidEmail = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());

export default function GlmFeedbackForm() {
  const [form, setForm] = useState({ name: '', email: '', contact: '', subject: '', message: '' });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!isValidEmail(form.email)) {
      setError('Укажите email для ответа.');
      return;
    }
    if (form.message.trim().length < 3) {
      setError('Напишите сообщение чуть подробнее.');
      return;
    }
    setLoading(true);
    setStatus(null);
    setError(null);
    try {
      const resp = await fetch('/api/referrals/public/support-messages', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name.trim() || null,
          email: form.email.trim(),
          contact: form.contact.trim() || null,
          subject: form.subject.trim() || 'CryptoGLAME',
          message: form.message.trim(),
          page: 'glm',
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setError(data?.detail || 'Не удалось отправить сообщение.');
        return;
      }
      setForm({ name: '', email: '', contact: '', subject: '', message: '' });
      setStatus(`Сообщение отправлено. Код обращения: ${data?.ticket_code || '—'}.`);
    } catch {
      setError('Не удалось связаться с сервером.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border border-white/10 bg-white/[0.03] p-6">
      <div className="text-xs font-semibold uppercase tracking-[0.34em] text-[#c9b56a]">Обратная связь</div>
      <h2 className="mt-4 text-3xl font-semibold tracking-normal text-white">Вопрос по GLM</h2>
      <p className="mt-3 text-sm leading-6 text-white/60">
        Сообщение уйдет администратору партнерской программы. Ответ отправим на email.
      </p>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="text-xs uppercase tracking-[0.18em] text-white/45">Имя</span>
          <input value={form.name} onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))} className="mt-2 w-full border border-white/15 bg-black/30 px-4 py-3 text-white outline-none" />
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-[0.18em] text-white/45">Email для ответа</span>
          <input value={form.email} onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} className="mt-2 w-full border border-white/15 bg-black/30 px-4 py-3 text-white outline-none" />
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-[0.18em] text-white/45">Telegram или телефон</span>
          <input value={form.contact} onChange={(event) => setForm((prev) => ({ ...prev, contact: event.target.value }))} className="mt-2 w-full border border-white/15 bg-black/30 px-4 py-3 text-white outline-none" />
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-[0.18em] text-white/45">Тема</span>
          <input value={form.subject} onChange={(event) => setForm((prev) => ({ ...prev, subject: event.target.value }))} className="mt-2 w-full border border-white/15 bg-black/30 px-4 py-3 text-white outline-none" />
        </label>
      </div>
      <label className="mt-4 block">
        <span className="text-xs uppercase tracking-[0.18em] text-white/45">Сообщение</span>
        <textarea value={form.message} onChange={(event) => setForm((prev) => ({ ...prev, message: event.target.value }))} className="mt-2 min-h-[150px] w-full resize-y border border-white/15 bg-black/30 px-4 py-3 text-white outline-none" />
      </label>
      {error ? <div className="mt-4 border border-red-400/40 bg-red-950/30 p-3 text-sm text-red-100">{error}</div> : null}
      {status ? <div className="mt-4 border border-emerald-400/30 bg-emerald-950/30 p-3 text-sm text-emerald-100">{status}</div> : null}
      <button disabled={loading} onClick={() => void submit()} className="mt-5 inline-flex w-full items-center justify-center gap-2 bg-white px-6 py-4 text-sm font-semibold uppercase tracking-[0.18em] text-black transition hover:bg-[#d8d8d8] disabled:cursor-wait disabled:opacity-60 md:w-auto">
        <Send className="h-4 w-4" /> {loading ? 'Отправляем...' : 'Отправить вопрос'}
      </button>
    </div>
  );
}
