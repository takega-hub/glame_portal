'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, ExternalLink, FileJson, Link2, RefreshCw } from 'lucide-react';

type AuditHash = {
  audit_date?: string;
  root_hash?: string;
  previous_root_hash?: string | null;
  transactions_count?: number;
  accounts_count?: number;
  balance_total?: number;
  hold_total?: number;
  lifetime_earned_total?: number;
  lifetime_burned_total?: number;
  public_reference?: string | null;
};

type AuditPayload = {
  schema?: string;
  token_code?: string;
  journal_url?: string;
  jsonl_url?: string;
  hashes?: AuditHash[];
};

function shortHash(value?: string | null) {
  if (!value) return '—';
  return value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-8)}` : value;
}

function formatNumber(value?: number) {
  return new Intl.NumberFormat('ru-RU').format(Number(value || 0));
}

function dateRu(value?: string) {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString('ru-RU');
}

export default function GlmAuditPage() {
  const [payload, setPayload] = useState<AuditPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const hashes = useMemo(() => payload?.hashes || [], [payload]);
  const latest = hashes[0];

  const loadAudit = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/referrals/glm-audit-hashes/public?limit=180', {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      setPayload(await response.json());
    } catch (err: any) {
      setError(err?.message || 'Не удалось загрузить audit journal');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAudit();
  }, []);

  return (
    <main className="min-h-screen bg-[#080909] text-white">
      <section className="border-b border-white/10">
        <div className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-12 md:px-10 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-xs uppercase tracking-[0.45em] text-[#c9b56a]">GLAME Coin</div>
            <h1 className="mt-4 text-4xl font-semibold tracking-normal text-white md:text-6xl">Audit journal</h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/64">
              Публичный журнал daily root hash для GLM ledger. Он помогает проверить, что опубликованные снимки операций связаны в цепочку и не менялись задним числом.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link href="/glm" className="border border-white/15 px-5 py-3 text-sm font-semibold text-white/75 hover:border-white/40 hover:text-white">
              GLM landing
            </Link>
            <button
              onClick={() => void loadAudit()}
              disabled={loading}
              className="inline-flex items-center gap-2 border border-[#c9b56a]/50 px-5 py-3 text-sm font-semibold text-[#e7d994] disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Обновить
            </button>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-10 md:px-10">
        {error ? (
          <div className="border border-red-500/40 bg-red-950/30 p-4 text-sm text-red-100">{error}</div>
        ) : null}

        <div className="grid gap-4 md:grid-cols-4">
          <div className="border border-white/12 bg-white/[0.03] p-5">
            <div className="text-xs uppercase tracking-[0.3em] text-white/45">Published days</div>
            <div className="mt-4 text-3xl font-semibold">{formatNumber(hashes.length)}</div>
          </div>
          <div className="border border-white/12 bg-white/[0.03] p-5">
            <div className="text-xs uppercase tracking-[0.3em] text-white/45">Latest date</div>
            <div className="mt-4 text-3xl font-semibold">{dateRu(latest?.audit_date)}</div>
          </div>
          <div className="border border-white/12 bg-white/[0.03] p-5">
            <div className="text-xs uppercase tracking-[0.3em] text-white/45">Transactions</div>
            <div className="mt-4 text-3xl font-semibold">{formatNumber(latest?.transactions_count)}</div>
          </div>
          <div className="border border-white/12 bg-white/[0.03] p-5">
            <div className="text-xs uppercase tracking-[0.3em] text-white/45">Accounts</div>
            <div className="mt-4 text-3xl font-semibold">{formatNumber(latest?.accounts_count)}</div>
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <a href="/api/referrals/glm-audit-hashes/public" target="_blank" rel="noreferrer" className="inline-flex items-center gap-3 border border-white/12 bg-white/[0.03] p-4 text-sm font-semibold text-white/75 hover:border-white/30 hover:text-white">
            <FileJson className="h-4 w-4 text-[#c9b56a]" /> Public API <ExternalLink className="ml-auto h-4 w-4" />
          </a>
          <a href="/static/glm_audit_journal/index.json" target="_blank" rel="noreferrer" className="inline-flex items-center gap-3 border border-white/12 bg-white/[0.03] p-4 text-sm font-semibold text-white/75 hover:border-white/30 hover:text-white">
            <FileJson className="h-4 w-4 text-[#c9b56a]" /> Journal JSON <ExternalLink className="ml-auto h-4 w-4" />
          </a>
          <a href="/static/glm_audit_journal/glame-audit-hashes.jsonl" target="_blank" rel="noreferrer" className="inline-flex items-center gap-3 border border-white/12 bg-white/[0.03] p-4 text-sm font-semibold text-white/75 hover:border-white/30 hover:text-white">
            <FileJson className="h-4 w-4 text-[#c9b56a]" /> Journal JSONL <ExternalLink className="ml-auto h-4 w-4" />
          </a>
        </div>

        <div className="mt-10 overflow-x-auto border border-white/12">
          <table className="min-w-full border-collapse text-left text-sm">
            <thead className="bg-white/[0.04] text-xs uppercase tracking-[0.26em] text-white/45">
              <tr>
                <th className="border-b border-white/10 px-4 py-4">Date</th>
                <th className="border-b border-white/10 px-4 py-4">Root hash</th>
                <th className="border-b border-white/10 px-4 py-4">Previous</th>
                <th className="border-b border-white/10 px-4 py-4">Totals</th>
                <th className="border-b border-white/10 px-4 py-4">Proof</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="px-4 py-8 text-white/56">Загружаем audit journal...</td></tr>
              ) : hashes.length ? hashes.map((item) => (
                <tr key={`${item.audit_date}-${item.root_hash}`} className="border-t border-white/10 align-top">
                  <td className="px-4 py-4 font-semibold">{dateRu(item.audit_date)}</td>
                  <td className="px-4 py-4">
                    <div className="max-w-[360px] break-all font-mono text-xs text-white/80">{item.root_hash}</div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="inline-flex items-center gap-2 font-mono text-xs text-white/56">
                      <Link2 className="h-3.5 w-3.5 text-[#c9b56a]" /> {shortHash(item.previous_root_hash)}
                    </div>
                  </td>
                  <td className="px-4 py-4 text-xs leading-6 text-white/60">
                    <div>transactions: {formatNumber(item.transactions_count)}</div>
                    <div>accounts: {formatNumber(item.accounts_count)}</div>
                    <div>balance: {formatNumber(item.balance_total)} GLM</div>
                    <div>hold: {formatNumber(item.hold_total)} GLM</div>
                  </td>
                  <td className="px-4 py-4">
                    {item.public_reference ? (
                      <a href={item.public_reference} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 border border-white/15 px-3 py-2 text-xs font-semibold text-white/70 hover:border-white/35 hover:text-white">
                        <CheckCircle2 className="h-4 w-4 text-emerald-300" /> Open
                      </a>
                    ) : '—'}
                  </td>
                </tr>
              )) : (
                <tr><td colSpan={5} className="px-4 py-8 text-white/56">Публичные audit hash еще не опубликованы.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
