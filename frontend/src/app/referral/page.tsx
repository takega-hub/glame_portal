'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import QRCode from 'qrcode';
import { TonConnectButton, useTonAddress, useTonConnectModal, useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import {
  AlertTriangle,
  BadgeCheck,
  Banknote,
  BarChart3,
  Check,
  Clipboard,
  Download,
  FileCheck2,
  FileText,
  ImageIcon,
  Landmark,
  LockKeyhole,
  ReceiptText,
  RefreshCcw,
  ShieldCheck,
  UserRoundCheck,
  Users,
  WalletCards,
} from 'lucide-react';

type RewardType = 'points' | 'cash';
type PortalView =
  | 'landing'
  | 'login'
  | 'join'
  | 'cashSetup'
  | 'dashboard'
  | 'referrals'
  | 'commissions'
  | 'payouts'
  | 'crypto'
  | 'media'
  | 'profile'
  | 'states';

interface Summary {
  registrations: number;
  active_referrals: number;
  purchases: number;
  referral_revenue: number;
  pending_commission: number;
  approved_commission: number;
  accrued_in_1c: number;
  paid_commission: number;
  posted_points: number;
  pending_points: number;
  average_check: number;
}

interface TokenSummary {
  token_code: string;
  token_name: string;
  network: string;
  balance: number;
  hold_balance: number;
  lifetime_earned: number;
  lifetime_burned: number;
  earned_total: number;
  converted_total?: number;
  transferable: boolean;
  cash_out: boolean;
  claimable_balance?: number;
  pending_claim_amount?: number;
  pending_claim?: boolean;
  claim_enabled?: boolean;
  claim_allowed?: boolean;
  claim_wallet_address?: string | null;
  onchain_balance?: {
    status: string;
    source?: string;
    network?: string;
    wallet_address?: string | null;
    jetton_master_address?: string | null;
    jetton_wallet_address?: string | null;
    balance_raw: string;
    balance_glm: string;
    decimals: number;
    checked_at?: string;
    error?: string;
  };
  onchain_policy?: {
    network?: string;
    standard?: string;
    status?: string;
    claim_mode?: string;
    jetton_master_address?: string | null;
    treasury_address?: string | null;
    metadata_url?: string;
    metadata_status?: string;
    mainnet_enabled?: boolean;
    mainnet_gate?: string;
    implementation_package?: string;
    disclaimer?: string;
  };
  privilege_score?: number;
  privilege_score_basis?: string;
  privilege_progress_percent?: number;
  privilege_to_next?: number;
  privilege_tier?: {
    code: string;
    name: string;
    threshold: number;
    benefits?: string[];
  } | null;
  next_privilege_tier?: {
    code: string;
    name: string;
    threshold: number;
    benefits?: string[];
  } | null;
  privilege_tiers?: Array<{
    code: string;
    name: string;
    threshold: number;
    benefits?: string[];
  }>;
  use_cases?: Array<{
    code: string;
    title: string;
    description: string;
    status: string;
    min_tier: string;
  }>;
  acceptance_rules?: Array<{
    category: string;
    limit_percent: number;
    note: string;
  }>;
  expiry_policy?: {
    mode?: string;
    description: string;
  };
  bonus_conversion_policy?: {
    enabled: boolean;
    rate: string;
    min_points: number;
    max_points: number;
    monthly_limit: number;
    description: string;
  };
  loyalty_points_purchase_policy?: {
    enabled: boolean;
    bridge_type: string;
    spread_percent: number;
    min_points: number;
    max_points: number;
    points_expires_days?: number;
    description: string;
  };
  referral_campaign?: {
    active: boolean;
    code: string;
    name: string;
    multiplier: number;
    until?: string | null;
    description: string;
  };
  store_items?: Array<{
    id?: string;
    sku: string;
    title: string;
    description: string;
    price_glm?: number | null;
    price_points?: number | null;
    category: string;
    status: string;
    inventory_status: string;
    quantity_available?: number | null;
    image_url?: string | null;
  }>;
  internal_value_rule?: {
    value: string;
    disclaimer: string;
    max_discount_formula: string;
  };
  store_checkout_policy?: {
    mode: string;
    enabled: boolean;
    next_mode?: string;
    description: string;
  };
  risk_note?: string;
}

interface ReferralItem {
  id?: string;
  name: string;
  phone: string | null;
  source: string;
  status: string;
  purchases: number;
  spent: number;
  reward_amount?: number;
  reward_points?: number;
  created_at?: string | null;
  activated_at?: string | null;
}

interface CommissionItem {
  id?: string;
  date: string | null;
  hold_until?: string | null;
  base: number;
  rate: number;
  amount: number;
  points: number;
  status: string;
  reward_mode?: RewardType;
  onec_sync_status?: string | null;
  onec_document_id?: string | null;
  glm?: {
    amount: number;
    status?: string | null;
    available_at?: string | null;
    expires_at?: string | null;
  };
}

interface PayoutItem {
  id: string;
  period_start: string | null;
  period_end: string | null;
  amount: number;
  status: string;
  onec_payment_document_id?: string | null;
  requested_at?: string | null;
}

interface GlmTransactionItem {
  id: string;
  type: string;
  status: string;
  amount: number;
  balance_after: number;
  hold_balance_after: number;
  reason?: string | null;
  source?: string | null;
  source_id?: string | null;
  description?: string | null;
  available_at?: string | null;
  expires_at?: string | null;
  created_at?: string | null;
  tx_hash?: string | null;
  deposit_tx_hash?: string | null;
  ton_direction?: string | null;
  counterparty?: string | null;
  onchain?: boolean;
  ton_deposit_verification?: Record<string, any> | null;
  ton_deposit_status?: string | null;
  ton_deposit_requested_at?: string | null;
  ton_deposit_query_id?: string | null;
  ton_deposit_last_lookup?: Record<string, any> | null;
  debit_source?: string | null;
  expected_ton_sender_address?: string | null;
  treasury_address?: string | null;
  admin_comment?: string | null;
  bridge_type?: string | null;
  target_points?: number | null;
}

interface PartnerProfile {
  full_name?: string | null;
  phone?: string | null;
  email?: string | null;
  loyalty_points?: number;
  customer_id_1c?: string | null;
  discount_card_number?: string | null;
  telegram_chat_id?: string | null;
  telegram_notifications_enabled?: boolean;
}

interface PartnerMember {
  reward_mode?: RewardType;
  program_level?: string;
  rate_percent?: number;
  cash_eligible?: boolean;
  cash_status?: string;
  onec_counterparty_id?: string | null;
  onec_agency_contract_id?: string | null;
  onec_sync_status?: string | null;
  crypto_wallet?: {
    network?: string;
    address?: string;
    label?: string;
    status?: string;
    linked_at?: string;
    verified_at?: string;
    verification?: string;
    wallet_app?: string | null;
    next_step?: string;
  } | null;
}

interface RatePromotion {
  id: string;
  title: string;
  rate_percent: number;
  starts_at: string;
  ends_at: string;
  is_active: boolean;
  status: 'active' | 'scheduled' | 'finished' | 'paused' | string;
}

interface MediaMaterial {
  id: string;
  title: string;
  category: string;
  description?: string | null;
  file_url: string;
  preview_url?: string | null;
  original_file_name: string;
  content_type?: string | null;
  size: number;
}

const money = (value: number) =>
  new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(
    value / 100
  );

const dateRu = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('ru-RU').format(date);
};

const statusRu = (value?: string | null) => {
  const map: Record<string, string> = {
    pending: 'Ждет покупку',
    active: 'Активен',
    hold: 'В холде',
    earn: 'Начисление',
    release: 'Доступно',
    expire: 'Списание',
    conversion: 'Обмен',
    bridge: 'Обмен',
    claim: 'В TON',
    redemption: 'Покупка',
    pending_fulfillment: 'На сборке',
    available: 'Доступно',
    processed: 'Обработано',
    approved: 'Подтверждено',
    accrued_in_1c: 'Начислено в 1С',
    paid: 'Выплачено',
    canceled: 'Отменено',
    success: 'Синхронизировано',
    failed: 'Ошибка',
    unavailable: 'Недоступно',
    eligible: 'Доступно',
    wallet_request_prepared: 'Открыт кошелек',
    waiting_for_deposit: 'Ждем TON',
    sent_waiting_settlement: 'Отправлено в TON',
    blocked_hot_wallet_balance: 'Ждет пополнения',
    blocked_missing_wallet: 'Нужен кошелек',
    blocked_policy: 'Требуется проверка',
    verified: 'Проверено',
    not_found: 'TON не найден',
  };
  return map[value || ''] || value || '—';
};

const commissionStatusRu = (value?: string | null) => {
  const map: Record<string, string> = {
    hold: 'В холде',
    pending: 'В холде',
    approved: 'Начислено',
    credited: 'Начислено',
    accrued_in_1c: 'Начислено',
    paid: 'Начислено',
    processed: 'Начислено',
    available: 'Начислено',
    release: 'Начислено',
    canceled: 'Отмена (возврат)',
    cancelled: 'Отмена (возврат)',
    refunded: 'Отмена (возврат)',
    returned: 'Отмена (возврат)',
    failed: 'Отмена (возврат)',
  };
  return map[value || ''] || statusRu(value);
};

const dayWord = (days: number) => {
  const normalized = Math.abs(days) % 100;
  const last = normalized % 10;
  if (normalized > 10 && normalized < 20) return 'дней';
  if (last === 1) return 'день';
  if (last >= 2 && last <= 4) return 'дня';
  return 'дней';
};

const commissionStatusLabel = (item: Pick<CommissionItem, 'status' | 'hold_until'>) => {
  if (item.status !== 'hold' && item.status !== 'pending') return commissionStatusRu(item.status);
  if (!item.hold_until) return commissionStatusRu(item.status);

  const holdUntil = new Date(item.hold_until);
  if (Number.isNaN(holdUntil.getTime())) return commissionStatusRu(item.status);

  const daysLeft = Math.ceil((holdUntil.getTime() - Date.now()) / 86_400_000);
  if (daysLeft <= 0) return 'В холде, срок истек';
  return `В холде, осталось ${daysLeft} ${dayWord(daysLeft)}`;
};

const statusTone = (value?: string | null): 'neutral' | 'ok' | 'warn' | 'bad' => {
  if (value === 'active' || value === 'approved' || value === 'paid' || value === 'success' || value === 'accrued_in_1c' || value === 'available' || value === 'processed' || value === 'release' || value === 'conversion') return 'ok';
  if (value === 'hold' || value === 'pending' || value === 'eligible' || value === 'bridge' || value === 'claim' || value === 'wallet_request_prepared' || value === 'waiting_for_deposit' || value === 'not_found' || value === 'sent_waiting_settlement' || value?.startsWith('blocked_')) return 'warn';
  if (value === 'canceled' || value === 'failed') return 'bad';
  return 'neutral';
};

const commissionStatusTone = (value?: string | null): 'neutral' | 'ok' | 'warn' | 'bad' => {
  if (value === 'hold' || value === 'pending') return 'warn';
  if (value === 'canceled' || value === 'cancelled' || value === 'refunded' || value === 'returned' || value === 'failed') return 'bad';
  if (value === 'approved' || value === 'credited' || value === 'accrued_in_1c' || value === 'paid' || value === 'processed' || value === 'available' || value === 'release') return 'ok';
  return statusTone(value);
};

type BridgeStage = {
  code: string;
  title: string;
  text: string;
  tone: 'neutral' | 'ok' | 'warn' | 'bad';
};

const glmTransactionTypeLabel = (tx: GlmTransactionItem) => {
  if (tx.type === 'ton_incoming') return 'Входящий TON-перевод';
  if (tx.type === 'ton_outgoing') return 'Исходящий TON-перевод';
  if (tx.reason === 'points_to_ton_bridge' || tx.reason === 'points_to_glm_bridge') return 'Баллы → GLM';
  if (tx.reason === 'glm_to_points_bridge' || tx.reason === 'buy_loyalty_points') return 'GLM → баллы';
  if (tx.reason === 'referral_commission') return 'Реферальное начисление';
  if (tx.type === 'redemption') return 'Покупка за GLM';
  if (tx.type === 'release') return 'Доступно';
  if (tx.type === 'expire') return 'Списание';
  if (tx.type === 'earn') return 'Начисление';
  return statusRu(tx.type);
};

const glmTransactionStage = (tx: GlmTransactionItem): BridgeStage => {
  const amount = Math.abs(Number(tx.amount || 0));
  if (tx.status === 'canceled') {
    return {
      code: 'canceled',
      title: 'Операция отменена',
      text: tx.description || tx.admin_comment || 'Операция закрыта без движения GLM.',
      tone: 'bad',
    };
  }
  if (tx.status === 'failed') {
    return {
      code: 'failed',
      title: 'Требуется проверка',
      text: tx.admin_comment || tx.description || 'Операцию не удалось завершить автоматически.',
      tone: 'bad',
    };
  }
  if (tx.onchain || tx.type === 'ton_incoming' || tx.type === 'ton_outgoing') {
    const incoming = tx.type === 'ton_incoming' || tx.ton_direction === 'incoming';
    return {
      code: tx.type || 'ton_transfer',
      title: incoming ? 'GLM получены в TON' : 'GLM отправлены из TON',
      text: tx.tx_hash
        ? `TON tx: ${tx.tx_hash}`
        : tx.counterparty
          ? `${incoming ? 'Отправитель' : 'Получатель'}: ${tx.counterparty}`
          : 'Внешнее движение GLM в привязанном TON-кошельке.',
      tone: 'ok',
    };
  }
  if (tx.reason === 'points_to_ton_bridge' || tx.reason === 'points_to_glm_bridge') {
    if (tx.status === 'processed') {
      return {
        code: 'processed',
        title: 'GLM отправлены в TON',
        text: tx.tx_hash ? `TON tx: ${tx.tx_hash}` : 'Баллы списаны, GLM отправлены в подтвержденный TON-кошелек.',
        tone: 'ok',
      };
    }
    return {
      code: tx.status || 'pending',
      title: 'Отправляем GLM в TON',
      text: `${amount} баллов списаны в 1С, GLM ожидают отправки из банка GLAME в ваш TON-кошелек.`,
      tone: 'warn',
    };
  }
  if (tx.reason === 'glm_to_points_bridge' || tx.reason === 'buy_loyalty_points') {
    if (tx.status === 'processed') {
      return {
        code: 'processed',
        title: 'Баллы начислены',
        text: tx.tx_hash || tx.deposit_tx_hash ? `TON tx: ${tx.tx_hash || tx.deposit_tx_hash}` : 'TON-перевод проверен, баллы начислены в 1С.',
        tone: 'ok',
      };
    }
    if (tx.deposit_tx_hash || tx.ton_deposit_verification?.ok) {
      return {
        code: 'verified',
        title: 'TON-перевод найден',
        text: `GLAME проверяет TON-перевод и начислит ${tx.target_points || amount} баллов после обработки 1С.`,
        tone: 'warn',
      };
    }
    if (tx.ton_deposit_status === 'wallet_request_prepared') {
      return {
        code: 'wallet_request_prepared',
        title: 'Подтвердите в кошельке',
        text: `Подтвердите отправку ${amount} GLM в TON-кошельке. После появления транзакции баллы начислятся автоматически.`,
        tone: 'warn',
      };
    }
    return {
      code: tx.ton_deposit_status || tx.status || 'pending',
      title: 'Ждем TON-перевод',
      text: `Отправьте ${amount} GLM из подтвержденного кошелька в treasury GLAME. После проверки TON баллы начислятся в 1С.`,
      tone: 'warn',
    };
  }
  if (tx.status === 'processed' || tx.status === 'available') {
    return {
      code: tx.status,
      title: statusRu(tx.status),
      text: tx.description || tx.admin_comment || 'Операция завершена.',
      tone: 'ok',
    };
  }
  return {
    code: tx.status || 'pending',
    title: statusRu(tx.status),
    text: tx.description || tx.admin_comment || tx.source || 'Операция в обработке.',
    tone: statusTone(tx.status),
  };
};

const tonPolicyModeLabel = (value?: string | null) => {
  const map: Record<string, string> = {
    operator_testnet_treasury_transfer: 'автоматический перевод GLM',
    offchain_pending_claim_only: 'ожидает TON-настройку',
  };
  return map[value || ''] || (value ? statusRu(value) : 'перевод через GLAME');
};


const PROGRAM_EMAIL = 'partner@glamejewelry.ru';
const OFFER_URL = '/docs/glame-referral-offer-v2.docx';
const CASH_UNLOCK_TURNOVER = 5000001;
const referralLevels = [
  ['Stylish Start / Стильный старт', 'до 50 000 ₽', '3%'],
  ['Stylish Pro / Стильный профи', '50 001 - 150 000 ₽', '5%'],
  ['Stylish Expert / Стильный эксперт', '150 001 - 300 000 ₽', '7%'],
  ['Stylish Privé / Стильный привилегированный', 'от 300 001 ₽', '10%'],
];

const tokenomicsRows = [
  ['Rewards/community', '40%', 'покупки, рефералы, активности'],
  ['GLAME treasury', '20%', 'резерв и операции по регламенту'],
  ['Liquidity', '15%', 'будущие пары GLM/TON и GLM/USDT'],
  ['Team', '10%', 'долгий vesting'],
  ['Partners/ambassadors', '10%', 'партнерские кампании и статусы'],
  ['Reserve', '5%', 'страховой и операционный резерв'],
];

const cryptoRoadmapRows = [
  ['01', 'История операций', 'Платформа фиксирует начисления, заявки и TON-транзакции; GLM хранится в TON-кошельке.'],
  ['02', 'Wallet link', 'Партнер привязывает TON-кошелек в кабинете.'],
  ['03', 'Обмен баллов', 'Перевод баллов в GLM и пилот внутреннего marketplace.'],
  ['04', 'TON transfer', 'Отправка GLM в TON-кошелек после проверки.'],
  ['05', 'DEX liquidity', 'Ограниченные пары GLM/TON и GLM/USDT без гарантии цены.'],
];

const emptySummary: Summary = {
  registrations: 0,
  active_referrals: 0,
  purchases: 0,
  referral_revenue: 0,
  pending_commission: 0,
  approved_commission: 0,
  accrued_in_1c: 0,
  paid_commission: 0,
  posted_points: 0,
  pending_points: 0,
  average_check: 0,
};

const emptyToken: TokenSummary = {
  token_code: 'GLM',
  token_name: 'GLAME Coin',
  network: 'off_chain_glame_ledger',
  balance: 0,
  hold_balance: 0,
  lifetime_earned: 0,
  lifetime_burned: 0,
  earned_total: 0,
  converted_total: 0,
  transferable: false,
  cash_out: false,
  claimable_balance: 0,
  pending_claim_amount: 0,
  pending_claim: false,
  claim_enabled: false,
  claim_allowed: false,
  claim_wallet_address: null,
  onchain_balance: {
    status: 'no_wallet',
    balance_raw: '0',
    balance_glm: '0',
    decimals: 9,
  },
  privilege_score: 0,
  privilege_progress_percent: 0,
  privilege_to_next: 0,
  privilege_tier: { code: 'glm_start', name: 'GLM Start', threshold: 0, benefits: [] },
  next_privilege_tier: null,
  privilege_tiers: [],
  use_cases: [],
  acceptance_rules: [],
  referral_campaign: undefined,
  store_items: [],
  internal_value_rule: undefined,
};

const navItems: Array<{ view: PortalView; label: string; icon: typeof BarChart3 }> = [
  { view: 'dashboard', label: 'Обзор', icon: BarChart3 },
  { view: 'referrals', label: 'Рефералы', icon: Users },
  { view: 'commissions', label: 'Начисления', icon: ReceiptText },
  { view: 'payouts', label: 'Выплаты', icon: WalletCards },
  { view: 'crypto', label: 'CryptoGLAME', icon: BadgeCheck },
  { view: 'media', label: 'Медиаматериалы', icon: ImageIcon },
  { view: 'profile', label: 'Профиль', icon: UserRoundCheck },
  { view: 'states', label: 'Статусы', icon: AlertTriangle },
];

const mediaCategoryLabels: Record<string, string> = {
  logos: 'Логотипы',
  patterns: 'Паттерны',
  phrases: 'Фирменные фразы',
  signs: 'Знак GLAME',
  other: 'Другое',
};

const fileSizeRu = (value: number) => {
  if (!value) return '—';
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} КБ`;
  return `${(value / 1024 / 1024).toFixed(1).replace('.', ',')} МБ`;
};

function StatusBadge({ children, tone = 'neutral' }: { children: string; tone?: 'neutral' | 'ok' | 'warn' | 'bad' }) {
  const cls =
    tone === 'ok'
      ? 'border-[#43564a] bg-[#17251d] text-[#b9dec5]'
      : tone === 'warn'
        ? 'border-[#615438] bg-[#2a2418] text-[#e1cf9c]'
        : tone === 'bad'
          ? 'border-[#6b3c3c] bg-[#2b1717] text-[#efb1aa]'
          : 'border-[#44474a] bg-[#1e2022] text-[#c5c6ca]';
  return <span className={`inline-flex border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] ${cls}`}>{children}</span>;
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="border border-[#44474a] bg-[#121416] p-4">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8f9194]">{label}</div>
      <div className="mt-4 text-2xl font-semibold text-[#e2e2e5]">{value}</div>
      {sub ? <div className="mt-2 text-xs text-[#8f9194]">{sub}</div> : null}
    </div>
  );
}

function DataTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: Array<Array<string | number | JSX.Element>>;
}) {
  return (
    <div className="w-full max-w-full overflow-x-auto border border-[#44474a] [-webkit-overflow-scrolling:touch]">
      <table className="w-full min-w-[720px] border-collapse text-xs sm:text-sm">
        <thead className="bg-[#1e2022] text-[#8f9194]">
          <tr>
            {headers.map((header) => (
              <th key={header} className="border-b border-r border-[#44474a] px-2 py-3 text-left text-[10px] font-semibold uppercase tracking-[0.14em] last:border-r-0 sm:px-3 sm:text-[11px]">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row, idx) => (
              <tr key={idx} className="bg-[#0c0e10] text-[#e2e2e5]">
                {row.map((cell, cellIdx) => (
                  <td key={cellIdx} className="border-b border-r border-[#333537] px-2 py-3 align-top last:border-r-0 sm:px-3">
                    {cell}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr className="bg-[#0c0e10] text-[#8f9194]">
              <td className="px-3 py-6 text-center" colSpan={headers.length}>
                Данных пока нет
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function ReferralPortalPage() {
  const [view, setView] = useState<PortalView>('landing');
  const [rewardType, setRewardType] = useState<RewardType>('points');
  const [copied, setCopied] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary>(emptySummary);
  const [token, setToken] = useState<TokenSummary>(emptyToken);
  const [referrals, setReferrals] = useState<ReferralItem[]>([]);
  const [commissions, setCommissions] = useState<CommissionItem[]>([]);
  const [payouts, setPayouts] = useState<PayoutItem[]>([]);
  const [glmTransactions, setGlmTransactions] = useState<GlmTransactionItem[]>([]);
  const [mediaMaterials, setMediaMaterials] = useState<MediaMaterial[]>([]);
  const [profile, setProfile] = useState<PartnerProfile>({});
  const [member, setMember] = useState<PartnerMember>({});
  const [ratePromotion, setRatePromotion] = useState<RatePromotion | null>(null);
  const [, setAccessToken] = useState<string | null>(null);
  const [joinForm, setJoinForm] = useState({ fullName: '', phone: '', password: '', offerAccepted: false });
  const [joinError, setJoinError] = useState<string | null>(null);
  const [joinLoading, setJoinLoading] = useState(false);
  const [loginForm, setLoginForm] = useState({ phone: '', password: '' });
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);
  const [passwordForm, setPasswordForm] = useState({ current: '', next: '', confirm: '' });
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [telegramMessage, setTelegramMessage] = useState<string | null>(null);
  const [telegramError, setTelegramError] = useState<string | null>(null);
  const [telegramLoading, setTelegramLoading] = useState(false);
  const [mediaLoading, setMediaLoading] = useState(false);
  const [manualSyncLoading, setManualSyncLoading] = useState(false);
  const [manualSyncMessage, setManualSyncMessage] = useState<string | null>(null);
  const [manualSyncError, setManualSyncError] = useState<string | null>(null);
  const [walletForm, setWalletForm] = useState({ address: '', label: 'TON Wallet' });
  const [walletMessage, setWalletMessage] = useState<string | null>(null);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [walletLoading, setWalletLoading] = useState(false);
  const [redeemMessage, setRedeemMessage] = useState<string | null>(null);
  const [redeemError, setRedeemError] = useState<string | null>(null);
  const [redeemLoadingSku, setRedeemLoadingSku] = useState<string | null>(null);
  const [convertPoints, setConvertPoints] = useState('');
  const [convertMessage, setConvertMessage] = useState<string | null>(null);
  const [convertError, setConvertError] = useState<string | null>(null);
  const [convertLoading, setConvertLoading] = useState(false);
  const [glmToPointsAmount, setGlmToPointsAmount] = useState('');
  const [glmToPointsMessage, setGlmToPointsMessage] = useState<string | null>(null);
  const [glmToPointsError, setGlmToPointsError] = useState<string | null>(null);
  const [glmToPointsLoading, setGlmToPointsLoading] = useState(false);
  const [tonConnectUI] = useTonConnectUI();
  const { open: openTonConnectModal } = useTonConnectModal();
  const tonWallet = useTonWallet();
  const tonFriendlyAddress = useTonAddress();
  const tonRawAddress = useTonAddress(false);
  const [tonProofLoading, setTonProofLoading] = useState(false);
  const [tonProofReady, setTonProofReady] = useState(false);
  const [verifiedTonProofKey, setVerifiedTonProofKey] = useState<string | null>(null);
  const [partnerCode, setPartnerCode] = useState<string | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const cashUpgradeEligible = summary.referral_revenue >= CASH_UNLOCK_TURNOVER;
  const referralCode = partnerCode || '—';
  const referralRmkCode = partnerCode ? `${partnerCode}@ref.glame` : '';
  const baseRate = Number(member.rate_percent ?? (cashUpgradeEligible ? 5 : 3));
  const promoRate = ratePromotion && rewardType === 'points' ? Number(ratePromotion.rate_percent || 0) : 0;
  const effectiveRate = ratePromotion?.status === 'active' && promoRate > 0 ? promoRate : baseRate;
  const onchainGlmBalance = Number.parseFloat(String(token.onchain_balance?.balance_glm ?? '0')) || 0;
  const onchainGlmLabel = token.onchain_balance?.status === 'ok' ? `${token.onchain_balance.balance_glm} ${token.token_code}` : '—';
  const onchainStatusLabel =
    token.onchain_balance?.status === 'ok'
      ? 'считано из TON'
      : token.onchain_balance?.status === 'no_wallet'
        ? 'кошелек не подключен'
        : token.onchain_balance?.status === 'not_configured'
          ? 'Jetton не настроен'
          : 'TON API недоступен';
  const visibleCommissions = useMemo(
    () =>
      commissions.filter((item) => {
        const isTinyZeroReward =
          Number(item.base || 0) <= 100 &&
          Number(item.points || 0) === 0 &&
          !item.glm?.amount;
        return !isTinyZeroReward;
      }),
    [commissions]
  );
  const isPortalView = view !== 'landing' && view !== 'login' && view !== 'join' && view !== 'cashSetup';
  const groupedMediaMaterials = useMemo(() => {
    return mediaMaterials.reduce<Record<string, MediaMaterial[]>>((acc, item) => {
      const key = item.category || 'other';
      acc[key] = [...(acc[key] || []), item];
      return acc;
    }, {});
  }, [mediaMaterials]);

  useEffect(() => {
    if (!partnerCode) {
      setQrDataUrl(null);
      return;
    }
    let active = true;
    QRCode.toDataURL(referralRmkCode, {
      errorCorrectionLevel: 'M',
      margin: 1,
      width: 224,
      color: {
        dark: '#171c1f',
        light: '#e2e2e5',
      },
    })
      .then((url) => {
        if (active) setQrDataUrl(url);
      })
      .catch(() => {
        if (active) setQrDataUrl(null);
      });
    return () => {
      active = false;
    };
  }, [partnerCode, referralRmkCode]);

  const applyDashboard = (data: any) => {
    if (data?.summary) setSummary({ ...emptySummary, ...data.summary });
    setToken({ ...emptyToken, ...(data?.token || {}) });
    setReferrals(Array.isArray(data?.referrals) ? data.referrals : []);
    setCommissions(Array.isArray(data?.commissions) ? data.commissions : []);
    setPayouts(Array.isArray(data?.payouts) ? data.payouts : []);
    setGlmTransactions(Array.isArray(data?.glm_transactions) ? data.glm_transactions : []);
    setProfile(data?.profile || {});
    setMember(data?.member || {});
    setRatePromotion(data?.rate_promotion || null);
    const wallet = data?.member?.crypto_wallet;
    if (wallet?.address) {
      setWalletForm({
        address: wallet.address,
        label: wallet.label || 'TON Wallet',
      });
    }
    if (data?.referral_code?.code) setPartnerCode(data.referral_code.code);
    if (data?.member?.reward_mode === 'cash' || data?.member?.reward_mode === 'points') setRewardType(data.member.reward_mode);
  };

  const loadDashboard = async (token?: string | null, goDashboard = false) => {
    const authToken = token || window.localStorage.getItem('glame_partner_access_token');
    setAccessToken(authToken);
    if (!authToken) return false;
    const resp = await fetch('/api/referrals/me/dashboard?period=30d', {
      credentials: 'include',
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (!resp.ok) return false;
    const data = await resp.json();
    applyDashboard(data);
    if (goDashboard) setView('dashboard');
    return true;
  };

  const prepareTonConnectProof = useCallback(async () => {
    const token = window.localStorage.getItem('glame_partner_access_token');
    if (!token) {
      setWalletError('Нужно войти заново.');
      return false;
    }
    setTonProofLoading(true);
    setTonProofReady(false);
    setWalletError(null);
    tonConnectUI.setConnectRequestParameters({ state: 'loading' });
    try {
      const resp = await fetch('/api/referrals/me/crypto-wallet/challenge', {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.payload) {
        tonConnectUI.setConnectRequestParameters(null);
        setWalletError(data?.detail || 'Не удалось подготовить TON Connect challenge.');
        return false;
      }
      tonConnectUI.setConnectRequestParameters({
        state: 'ready',
        value: { tonProof: data.payload },
      });
      setTonProofReady(true);
      return true;
    } catch {
      tonConnectUI.setConnectRequestParameters(null);
      setWalletError('Не удалось связаться с сервером.');
      return false;
    } finally {
      setTonProofLoading(false);
    }
  }, [tonConnectUI]);

  const reconnectTonWalletForProof = async () => {
    if (tonWallet) {
      await tonConnectUI.disconnect();
      setTonProofReady(false);
    }
    const ready = await prepareTonConnectProof();
    if (!ready) return;
    setWalletMessage('Откройте TON Connect и подтвердите подключение в кошельке. Proof подписывается именно в момент подключения.');
    window.setTimeout(() => openTonConnectModal(), 200);
  };

  useEffect(() => {
    if (view !== 'crypto' || tonWallet || tonProofReady || tonProofLoading) return;
    void prepareTonConnectProof();
  }, [prepareTonConnectProof, tonProofLoading, tonProofReady, tonWallet, view]);

  useEffect(() => {
    const proofItem = (tonWallet as any)?.connectItems?.tonProof;
    if (!tonWallet || !proofItem || !('proof' in proofItem)) return;
    const proofKey = `${tonWallet.account.address}:${proofItem.proof.signature}`;
    if (verifiedTonProofKey === proofKey) return;
    if (member.crypto_wallet?.status === 'verified' && member.crypto_wallet?.address === tonWallet.account.address) return;

    const verifyTonProof = async () => {
      const token = window.localStorage.getItem('glame_partner_access_token');
      if (!token) {
        setWalletError('Нужно войти заново.');
        return;
      }
      if (!tonWallet.account.publicKey) {
        setWalletError('Кошелек не вернул public key. Попробуйте другой TON-кошелек или переподключение.');
        return;
      }
      setWalletLoading(true);
      setWalletError(null);
      setWalletMessage(null);
      try {
        const resp = await fetch('/api/referrals/me/crypto-wallet/ton-connect', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({
            network: 'ton',
            address: tonWallet.account.address,
            public_key: tonWallet.account.publicKey,
            wallet_state_init: tonWallet.account.walletStateInit,
            proof: proofItem.proof,
            wallet_app: tonWallet.device?.appName || (tonWallet as any).name || 'TON Wallet',
          }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          setWalletError(data?.detail || 'TON proof не прошел проверку.');
          return;
        }
        setVerifiedTonProofKey(proofKey);
        setWalletMessage('TON-кошелек подтвержден криптографической подписью.');
        setMember((prev) => ({ ...prev, crypto_wallet: data.crypto_wallet }));
        setWalletForm({
          address: data.crypto_wallet?.address || tonFriendlyAddress || tonRawAddress,
          label: data.crypto_wallet?.label || 'TON Wallet',
        });
      } catch {
        setWalletError('Не удалось связаться с сервером.');
      } finally {
        setWalletLoading(false);
      }
    };

    void verifyTonProof();
  }, [member.crypto_wallet?.address, member.crypto_wallet?.status, tonFriendlyAddress, tonRawAddress, tonWallet, verifiedTonProofKey]);

  const loadMediaMaterials = async (token?: string | null) => {
    const authToken = token || window.localStorage.getItem('glame_partner_access_token');
    if (!authToken) return;
    setMediaLoading(true);
    try {
      const resp = await fetch('/api/referrals/media-materials', {
        credentials: 'include',
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!resp.ok) return;
      const data = await resp.json();
      setMediaMaterials(Array.isArray(data) ? data : []);
    } finally {
      setMediaLoading(false);
    }
  };

  useEffect(() => {
    void loadDashboard(null, true);
  }, []);

  useEffect(() => {
    if (isPortalView) void loadMediaMaterials();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPortalView]);

  const submitJoin = async () => {
    setJoinError(null);
    const fullName = joinForm.fullName.trim();
    const phone = joinForm.phone.trim();
    const password = joinForm.password;
    if (!fullName || !phone || password.length < 6) {
      setJoinError('Укажите ФИО, телефон и пароль от 6 символов.');
      return;
    }
    if (!joinForm.offerAccepted) {
      setJoinError('Перед регистрацией нужно ознакомиться с офертой.');
      return;
    }
    setJoinLoading(true);
    try {
      const resp = await fetch('/api/referrals/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: fullName, phone, password, offer_accepted: joinForm.offerAccepted }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setJoinError(data?.detail || 'Не удалось подключить программу.');
        return;
      }
      if (data?.access_token) {
        window.localStorage.setItem('glame_partner_access_token', data.access_token);
        setAccessToken(data.access_token);
      }
      applyDashboard(data?.dashboard);
      setRewardType('points');
      setView('dashboard');
    } catch {
      setJoinError('Не удалось связаться с сервером.');
    } finally {
      setJoinLoading(false);
    }
  };

  const submitLogin = async () => {
    setLoginError(null);
    setLoginLoading(true);
    try {
      const form = new URLSearchParams();
      form.set('username', loginForm.phone.trim());
      form.set('password', loginForm.password);
      const resp = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: form.toString(),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.access_token) {
        setLoginError('Неверный телефон или пароль.');
        return;
      }
      window.localStorage.setItem('glame_partner_access_token', data.access_token);
      window.localStorage.setItem('glame_partner_refresh_token', data.refresh_token || '');
      window.localStorage.setItem('glame_access_token', data.access_token);
      window.localStorage.setItem('glame_refresh_token', data.refresh_token || '');
      const ok = await loadDashboard(data.access_token, true);
      if (!ok) setLoginError('Партнерская программа еще не подключена для этого пользователя.');
    } catch {
      setLoginError('Не удалось войти.');
    } finally {
      setLoginLoading(false);
    }
  };

  const submitPasswordChange = async () => {
    setPasswordError(null);
    setPasswordMessage(null);
    if (passwordForm.next.length < 6) {
      setPasswordError('Новый пароль должен быть не короче 6 символов.');
      return;
    }
    if (passwordForm.next !== passwordForm.confirm) {
      setPasswordError('Пароли не совпадают.');
      return;
    }
    const token = window.localStorage.getItem('glame_partner_access_token');
    if (!token) {
      setPasswordError('Нужно войти заново.');
      return;
    }
    setPasswordLoading(true);
    try {
      const resp = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ current_password: passwordForm.current || undefined, new_password: passwordForm.next }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setPasswordError(data?.detail || 'Не удалось изменить пароль.');
        return;
      }
      setPasswordForm({ current: '', next: '', confirm: '' });
      setPasswordMessage('Пароль изменен.');
    } catch {
      setPasswordError('Не удалось изменить пароль.');
    } finally {
      setPasswordLoading(false);
    }
  };

  const submitTelegramBind = async () => {
    setTelegramError(null);
    setTelegramMessage(null);
    const token = window.localStorage.getItem('glame_partner_access_token');
    if (!token) {
      setTelegramError('Нужно войти заново.');
      return;
    }
    setTelegramLoading(true);
    try {
      const resp = await fetch('/api/referrals/me/telegram-notifications/link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setTelegramError(data?.detail || 'Не удалось создать ссылку Telegram.');
        return;
      }
      if (data?.connect_url) window.open(data.connect_url, '_blank', 'noopener,noreferrer');
      setTelegramMessage('Откройте Telegram и нажмите Start. Ссылка действует 15 минут.');
    } catch {
      setTelegramError('Не удалось создать ссылку Telegram.');
    } finally {
      setTelegramLoading(false);
    }
  };

  const copy = async (value: string, key: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      setCopied(null);
    }
  };

  const syncReferralsFromOneC = async () => {
    const token = window.localStorage.getItem('glame_partner_access_token');
    if (!token) {
      setManualSyncError('Нужно войти заново.');
      return;
    }
    setManualSyncLoading(true);
    setManualSyncMessage(null);
    setManualSyncError(null);
    try {
      const resp = await fetch('/api/referrals/me/sync-referrals', {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setManualSyncError(data?.detail || 'Не удалось выполнить синхронизацию с 1С.');
        return;
      }
      setManualSyncMessage(data?.message || 'Синхронизация с 1С завершена.');
      await loadDashboard(token, false);
    } catch {
      setManualSyncError('Не удалось связаться с сервером 1С.');
    } finally {
      setManualSyncLoading(false);
    }
  };

  const submitCryptoWallet = async () => {
    const token = window.localStorage.getItem('glame_partner_access_token');
    if (!token) {
      setWalletError('Нужно войти заново.');
      return;
    }
    setWalletLoading(true);
    setWalletMessage(null);
    setWalletError(null);
    try {
      const resp = await fetch('/api/referrals/me/crypto-wallet', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          network: 'ton',
          address: walletForm.address.trim(),
          label: walletForm.label.trim() || 'TON Wallet',
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setWalletError(data?.detail || 'Не удалось привязать кошелек.');
        return;
      }
      setWalletMessage('Адрес сохранен как резервный. Для статуса verified нажмите «Подключить с proof» и подтвердите TON Connect в кошельке.');
      setMember((prev) => ({ ...prev, crypto_wallet: data.crypto_wallet }));
    } catch {
      setWalletError('Не удалось связаться с сервером.');
    } finally {
      setWalletLoading(false);
    }
  };

  const submitGlmStoreRedeem = async (sku: string) => {
    const tokenValue = window.localStorage.getItem('glame_partner_access_token');
    if (!tokenValue) {
      setRedeemError('Нужно войти заново.');
      return;
    }
    if (!tonWallet) {
      setRedeemError('Подключите подтвержденный TON-кошелек.');
      return;
    }
    if (token.claim_wallet_address && tonWallet.account.address !== token.claim_wallet_address) {
      setRedeemError('Подключенный TON-кошелек отличается от подтвержденного кошелька партнера.');
      return;
    }
    setRedeemLoadingSku(`glm:${sku}`);
    setRedeemMessage(null);
    setRedeemError(null);
    try {
      const resp = await fetch('/api/referrals/me/glm-store/redeem', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenValue}` },
        body: JSON.stringify({ sku }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setRedeemError(data?.detail || 'Не удалось оформить покупку за GLM.');
        return;
      }
      const redemptionId = data?.redemption?.id;
      if (!redemptionId) {
        setRedeemError('Заказ создан, но не удалось подготовить TON-оплату. Обновите страницу и повторите.');
        return;
      }
      const tonResp = await fetch(`/api/referrals/me/glm-store/redemptions/${redemptionId}/ton-transaction`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${tokenValue}` },
      });
      const tonData = await tonResp.json().catch(() => ({}));
      if (!tonResp.ok) {
        setRedeemError(tonData?.detail || 'Не удалось подготовить TON-транзакцию.');
        return;
      }
      await tonConnectUI.sendTransaction(tonData.transaction);
      setToken((prev) => ({ ...prev, ...(data.token || {}) }));
      setRedeemMessage('TON-транзакция отправлена в кошелек. После подтверждения в сети заказ попадет в очередь выдачи.');
      await loadDashboard(tokenValue, false);
    } catch (error: any) {
      const message = String(error?.message || '');
      setRedeemError(
        message.toLowerCase().includes('insufficient')
          ? 'В кошельке не хватает testnet GRAM для комиссии TON. Пополните testnet-кошелек и повторите оплату.'
          : message || 'TON-транзакция отменена или не отправлена.'
      );
    } finally {
      setRedeemLoadingSku(null);
    }
  };

  const submitRewardStorePointsRedeem = async (sku: string) => {
    const tokenValue = window.localStorage.getItem('glame_partner_access_token');
    if (!tokenValue) {
      setRedeemError('Нужно войти заново.');
      return;
    }
    setRedeemLoadingSku(`points:${sku}`);
    setRedeemMessage(null);
    setRedeemError(null);
    try {
      const resp = await fetch('/api/referrals/me/reward-store/redeem-points', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenValue}` },
        body: JSON.stringify({ sku }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setRedeemError(data?.detail || 'Не удалось оформить покупку за баллы.');
        return;
      }
      setToken((prev) => ({ ...prev, ...(data.token || {}) }));
      if (data.profile) setProfile((prev) => ({ ...prev, ...data.profile }));
      setRedeemMessage('Заказ в Reward Store создан. Баллы списаны в 1С, товар ожидает выдачи.');
      await loadDashboard(tokenValue, false);
    } catch {
      setRedeemError('Не удалось связаться с сервером.');
    } finally {
      setRedeemLoadingSku(null);
    }
  };

  const submitBonusConversion = async () => {
    const tokenValue = window.localStorage.getItem('glame_partner_access_token');
    if (!tokenValue) {
      setConvertError('Нужно войти заново.');
      return;
    }
    const points = Number.parseInt(convertPoints, 10);
    if (!points || points <= 0) {
      setConvertError('Укажите количество бонусных баллов.');
      return;
    }
    setConvertLoading(true);
    setConvertMessage(null);
    setConvertError(null);
    try {
      const resp = await fetch('/api/referrals/me/glm-bridge/points-to-ton', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenValue}` },
        body: JSON.stringify({ points }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setConvertError(data?.detail || 'Не удалось перевести баллы в GLM и создать вывод в TON.');
        return;
      }
      setToken((prev) => ({ ...prev, ...(data.token || {}) }));
      setProfile((prev) => ({ ...prev, loyalty_points: data.profile?.loyalty_points ?? prev.loyalty_points }));
      setConvertPoints('');
      setConvertMessage(`${data.bridge?.amount || points} баллов списаны в 1С. GLM отправятся из банка GLAME в ваш подтвержденный TON-кошелек автоматически.`);
      await loadDashboard(tokenValue, false);
    } catch {
      setConvertError('Не удалось связаться с сервером.');
    } finally {
      setConvertLoading(false);
    }
  };

  const submitGlmToPointsBridge = async () => {
    const tokenValue = window.localStorage.getItem('glame_partner_access_token');
    if (!tokenValue) {
      setGlmToPointsError('Нужно войти заново.');
      return;
    }
    const amount = Number.parseInt(glmToPointsAmount, 10);
    if (!amount || amount <= 0) {
      setGlmToPointsError('Укажите количество GLM.');
      return;
    }
    setGlmToPointsLoading(true);
    setGlmToPointsMessage(null);
    setGlmToPointsError(null);
    try {
      const resp = await fetch('/api/referrals/me/glm-bridge/glm-to-points', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenValue}` },
        body: JSON.stringify({ amount }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setGlmToPointsError(data?.detail || 'Не удалось создать заявку GLM -> баллы.');
        return;
      }
      setToken((prev) => ({ ...prev, ...(data.token || {}) }));
      setGlmToPointsAmount('');
      setGlmToPointsMessage(null);
      await loadDashboard(tokenValue, false);
    } catch {
      setGlmToPointsError('Не удалось связаться с сервером.');
    } finally {
      setGlmToPointsLoading(false);
    }
  };

  const pendingGlmToPointsBridge = useMemo(
    () =>
      glmTransactions.find(
        (item) =>
          item.type === 'bridge' &&
          item.status === 'pending' &&
          (item.reason === 'glm_to_points_bridge' || item.reason === 'buy_loyalty_points')
      ) || null,
    [glmTransactions]
  );
  const glmDepositTreasuryAddress = pendingGlmToPointsBridge?.treasury_address || token.onchain_policy?.treasury_address || null;
  const pendingGlmToPointsStatus = useMemo(() => {
    if (!pendingGlmToPointsBridge) return null;
    if (pendingGlmToPointsBridge.deposit_tx_hash || pendingGlmToPointsBridge.ton_deposit_verification?.ok) {
      return {
        code: 'verified',
        title: 'TON-перевод найден',
        text: `TON-транзакция найдена. GLAME проверяет перевод и начислит ${pendingGlmToPointsBridge.target_points || Math.abs(pendingGlmToPointsBridge.amount)} баллов после обработки 1С.`,
      };
    }
    const depositStatus = pendingGlmToPointsBridge.ton_deposit_status || pendingGlmToPointsBridge.ton_deposit_last_lookup?.status || null;
    if (depositStatus === 'waiting_for_deposit' || depositStatus === 'not_found') {
      return {
        code: 'waiting_for_deposit',
        title: 'Ждем TON-перевод',
        text: `Если вы уже подтвердили перевод, дождитесь появления транзакции в TON. GLAME проверит поступление автоматически. Сумма: ${Math.abs(pendingGlmToPointsBridge.amount)} GLM.`,
      };
    }
    if (depositStatus === 'wallet_request_prepared') {
      return {
        code: 'wallet_request_prepared',
        title: 'Подтвердите в кошельке',
        text: `Подтвердите отправку ${Math.abs(pendingGlmToPointsBridge.amount)} GLM в TON-кошельке. После появления транзакции баллы начислятся автоматически.`,
      };
    }
    return {
      code: 'pending',
      title: 'Ожидает подтверждения',
      text: `Подтвердите отправку ${Math.abs(pendingGlmToPointsBridge.amount)} GLM из привязанного кошелька в GLAME. После проверки TON-перевода баллы начислятся автоматически.`,
    };
  }, [pendingGlmToPointsBridge]);

  const confirmPendingGlmToPointsBridgeTransfer = async () => {
    const tokenValue = window.localStorage.getItem('glame_partner_access_token');
    if (!tokenValue) {
      setGlmToPointsError('Нужно войти заново.');
      return;
    }
    if (!pendingGlmToPointsBridge) {
      setGlmToPointsError('Нет pending-заявки GLM -> баллы.');
      return;
    }
    if (!tonWallet) {
      setGlmToPointsMessage('Подключите подтвержденный TON-кошелек, затем подтвердите перевод GLM.');
      openTonConnectModal();
      return;
    }
    if (token.claim_wallet_address && tonWallet.account.address !== token.claim_wallet_address) {
      setGlmToPointsError('Подключенный TON-кошелек отличается от подтвержденного кошелька партнера.');
      return;
    }
    setGlmToPointsLoading(true);
    setGlmToPointsError(null);
    setGlmToPointsMessage('Откройте кошелек и подтвердите перевод GLM в GLAME.');
    try {
      const resp = await fetch(`/api/referrals/me/glm-bridge/glm-to-points/${pendingGlmToPointsBridge.id}/ton-transaction`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${tokenValue}` },
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setGlmToPointsError(data?.detail || 'Не удалось подготовить TON-транзакцию.');
        setGlmToPointsMessage(null);
        return;
      }
      await tonConnectUI.sendTransaction(data.transaction);
      setGlmToPointsMessage('TON-транзакция отправлена в кошелек. После подтверждения в сети GLAME проверит перевод и начислит баллы автоматически.');
      await loadDashboard(tokenValue, false);
    } catch (error: any) {
      const message = String(error?.message || '');
      setGlmToPointsError(
        message.toLowerCase().includes('insufficient')
          ? 'В кошельке не хватает testnet GRAM для комиссии TON. Пополните testnet-кошелек через faucet и повторите подтверждение.'
          : message || 'TON-транзакция отменена или не отправлена.'
      );
      setGlmToPointsMessage(null);
    } finally {
      setGlmToPointsLoading(false);
    }
  };

  const cancelPendingGlmToPointsBridge = async () => {
    const tokenValue = window.localStorage.getItem('glame_partner_access_token');
    if (!tokenValue) {
      setGlmToPointsError('Нужно войти заново.');
      return;
    }
    if (!pendingGlmToPointsBridge) {
      setGlmToPointsError('Нет pending-заявки GLM -> баллы.');
      return;
    }
    setGlmToPointsLoading(true);
    setGlmToPointsError(null);
    setGlmToPointsMessage(null);
    try {
      const resp = await fetch(`/api/referrals/me/glm-bridge/glm-to-points/${pendingGlmToPointsBridge.id}/cancel`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: `Bearer ${tokenValue}` },
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setGlmToPointsError(data?.detail || 'Не удалось отменить заявку.');
        return;
      }
      setToken((prev) => ({ ...prev, ...(data.token || {}) }));
      setGlmToPointsMessage('Заявка GLM -> баллы отменена. GLM не списывались, потому что TON-перевод не был подтвержден.');
      await loadDashboard(tokenValue, false);
    } catch {
      setGlmToPointsError('Не удалось связаться с сервером.');
    } finally {
      setGlmToPointsLoading(false);
    }
  };

  const rows = useMemo(
    () =>
      referrals.map((item) => [
        item.name,
        item.phone || '—',
        item.source,
        <StatusBadge key={item.status} tone={statusTone(item.status)}>{statusRu(item.status)}</StatusBadge>,
        item.purchases,
        money(item.spent),
        rewardType === 'cash' ? money(item.reward_amount || 0) : `${item.reward_points || 0} баллов`,
      ]),
    [referrals, rewardType]
  );
  return (
    <div className="min-h-screen bg-[#0c0e10] text-[#e2e2e5]" style={{ fontFamily: 'Geist, Inter, system-ui, sans-serif' }}>
      <div className="flex min-h-screen min-w-0">
        {isPortalView ? (
          <aside className="hidden w-72 shrink-0 border-r border-[#44474a] bg-[#121416] lg:block">
            <div className="border-b border-[#44474a] p-6">
              <div className="text-2xl font-bold tracking-[0.22em]">GLAME</div>
              <div className="mt-2 text-[10px] uppercase tracking-[0.28em] text-[#8f9194]">Referral Portal</div>
            </div>
            <nav className="p-3">
              {navItems.map((item) => {
                const Icon = item.icon;
                const active = view === item.view;
                return (
                  <button
                    key={item.view}
                    onClick={() => setView(item.view)}
                    className={`flex w-full items-center gap-3 border border-transparent px-4 py-3 text-left text-sm font-semibold uppercase tracking-[0.12em] transition ${
                      active ? 'border-[#c6c6c9] bg-[#e2e2e5] text-[#171c1f]' : 'text-[#c5c6ca] hover:border-[#44474a] hover:bg-[#1e2022]'
                    }`}
                  >
                    <Icon size={18} />
                    {item.label}
                  </button>
                );
              })}
            </nav>
            <div className="mx-3 mt-6 border border-[#44474a] bg-[#1a1c1e] p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-[#8f9194]">Режим вознаграждения</div>
              <div className="mt-3 text-lg font-semibold">{rewardType === 'cash' ? 'Деньги' : 'Баллы GLAME'}</div>
              <p className="mt-3 text-xs leading-5 text-[#c5c6ca]">
                Денежное вознаграждение открывается после достижения уровня партнера и оформления агентского договора.
              </p>
            </div>
          </aside>
        ) : null}

        <main className="min-w-0 flex-1 overflow-hidden">
          {isPortalView ? (
            <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-[#44474a] bg-[#121416]/95 px-3 py-4 backdrop-blur sm:px-4 lg:px-6">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8f9194]">partner.glamejewelry.ru</div>
                <div className="mt-1 text-lg font-semibold">Кабинет партнера</div>
              </div>
              <div className="hidden items-center gap-2 md:flex">
                <StatusBadge tone="ok">Программа активна</StatusBadge>
                {rewardType === 'cash' && member.onec_agency_contract_id ? <StatusBadge tone="ok">Договор активен</StatusBadge> : <StatusBadge>{rewardType === 'cash' ? statusRu(member.cash_status) : 'Баллы GLAME'}</StatusBadge>}
              </div>
            </header>
          ) : null}

          {isPortalView ? (
            <nav className="border-b border-[#44474a] bg-[#0c0e10]/95 px-3 py-2 backdrop-blur lg:hidden">
              <div className="flex max-w-full gap-2 overflow-x-auto pb-1 [-webkit-overflow-scrolling:touch]">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const active = view === item.view;
                  return (
                    <button
                      key={item.view}
                      onClick={() => setView(item.view)}
                      className={`flex shrink-0 items-center gap-2 border px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] transition ${
                        active ? 'border-[#c6c6c9] bg-[#e2e2e5] text-[#171c1f]' : 'border-[#44474a] text-[#c5c6ca]'
                      }`}
                    >
                      <Icon size={16} />
                      {item.label}
                    </button>
                  );
                })}
              </div>
            </nav>
          ) : null}

          <div className="min-w-0 p-3 sm:p-4 lg:p-6">
            {view === 'landing' ? (
              <section className="mx-auto grid min-h-[calc(100vh-48px)] max-w-7xl content-center gap-8 lg:grid-cols-[1.1fr_0.9fr]">
                <div className="border border-[#44474a] bg-[#121416] p-6 md:p-10">
                  <div className="text-sm font-semibold uppercase tracking-[0.28em] text-[#8f9194]">GLAME Referral</div>
                  <h1 className="mt-8 max-w-3xl text-5xl font-semibold leading-[0.98] tracking-tight md:text-7xl">
                    Реферальная программа для партнеров GLAME
                  </h1>
                  <p className="mt-6 max-w-2xl text-lg leading-7 text-[#c5c6ca]">
                    Передавайте клиентам персональный код, отслеживайте регистрации, покупки, баллы или денежные агентские начисления в одном кабинете.
                  </p>
                  <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                    <button onClick={() => setView('login')} className="border border-[#e2e2e5] bg-[#e2e2e5] px-5 py-4 text-sm font-semibold uppercase tracking-[0.14em] text-[#171c1f]">
                      Войти в кабинет
                    </button>
                    <button onClick={() => { setRewardType('points'); setView('join'); }} className="border border-[#44474a] px-5 py-4 text-sm font-semibold uppercase tracking-[0.14em] text-[#e2e2e5]">
                      Стать партнером
                    </button>
                  </div>
                  <a href={`mailto:${PROGRAM_EMAIL}`} className="mt-6 inline-block text-sm text-[#c5c6ca] underline-offset-4 hover:underline">
                    {PROGRAM_EMAIL}
                  </a>
                  <a href={OFFER_URL} target="_blank" rel="noreferrer" className="ml-0 mt-3 block text-sm text-[#c5c6ca] underline-offset-4 hover:underline sm:ml-4 sm:mt-0 sm:inline-block">
                    Оферта реферальной программы
                  </a>
                </div>
                <div className="grid gap-4">
                  {[
                    ['01', 'Баллы GLAME', 'Стартовый режим для всех партнеров. Уровни по годовому реферальному обороту: 3%, 5%, 7% или 10%.'],
                    ['02', 'Деньги', 'Доступно с уровня Stylish Pro. Нужны статус ИП или самозанятого, данные для документов и агентское оформление.'],
                    ['03', 'Бонус клиенту', 'Рекомендованный клиент может получить 1 000 бонусов на первую покупку по условиям оферты.'],
                  ].map(([num, title, text]) => (
                    <div key={num} className="border border-[#44474a] bg-[#121416] p-5">
                      <div className="text-xs uppercase tracking-[0.18em] text-[#8f9194]">{num}</div>
                      <div className="mt-5 text-xl font-semibold">{title}</div>
                      <p className="mt-3 text-sm leading-6 text-[#c5c6ca]">{text}</p>
                    </div>
                  ))}
                  <div className="border border-[#44474a] bg-[#121416] p-5">
                    <div className="text-xs uppercase tracking-[0.18em] text-[#8f9194]">Уровни</div>
                    <div className="mt-4 grid gap-2">
                      {referralLevels.map(([level, turnover, percent]) => (
                        <div key={level} className="grid grid-cols-[1fr_auto] gap-3 border-b border-[#333537] py-2 text-sm last:border-b-0">
                          <div>
                            <div className="font-semibold">{level}</div>
                            <div className="mt-1 text-xs text-[#8f9194]">{turnover}</div>
                          </div>
                          <div className="text-lg font-semibold">{percent}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </section>
            ) : null}

            {view === 'login' ? (
              <section className="mx-auto flex min-h-[calc(100vh-48px)] max-w-xl items-center">
                <div className="w-full border border-[#44474a] bg-[#121416] p-6 md:p-8">
                  <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">Вход</div>
                  <h1 className="mt-4 text-4xl font-semibold">Кабинет партнера</h1>
                  <label className="mt-8 block text-xs uppercase tracking-[0.16em] text-[#8f9194]">Телефон</label>
                  <input value={loginForm.phone} onChange={(event) => setLoginForm((prev) => ({ ...prev, phone: event.target.value }))} className="mt-3 w-full border border-[#44474a] bg-[#0c0e10] px-4 py-4 text-[#e2e2e5] outline-none" placeholder="+7" />
                  <label className="mt-4 block text-xs uppercase tracking-[0.16em] text-[#8f9194]">Пароль</label>
                  <input value={loginForm.password} onChange={(event) => setLoginForm((prev) => ({ ...prev, password: event.target.value }))} type="password" className="mt-3 w-full border border-[#44474a] bg-[#0c0e10] px-4 py-4 text-[#e2e2e5] outline-none" />
                  {loginError ? <div className="mt-4 border border-[#7a3a3a] bg-[#1a1111] p-3 text-sm text-[#f0c7c7]">{loginError}</div> : null}
                  <button disabled={loginLoading} onClick={() => void submitLogin()} className="mt-4 w-full border border-[#e2e2e5] bg-[#e2e2e5] px-5 py-4 text-sm font-semibold uppercase tracking-[0.14em] text-[#171c1f] disabled:cursor-wait disabled:opacity-60">
                    {loginLoading ? 'Входим...' : 'Войти'}
                  </button>
                  <a href={`mailto:${PROGRAM_EMAIL}`} className="mt-5 block text-sm text-[#c5c6ca] underline-offset-4 hover:underline">
                    Написать в партнерскую программу: {PROGRAM_EMAIL}
                  </a>
                  <button onClick={() => setView('landing')} className="mt-4 text-sm text-[#8f9194]">Назад к программе</button>
                </div>
              </section>
            ) : null}

            {view === 'join' || view === 'cashSetup' ? (
              <section className="mx-auto max-w-5xl">
                <button onClick={() => setView('landing')} className="mb-4 text-sm text-[#8f9194]">Назад</button>
                <div className="border border-[#44474a] bg-[#121416]">
                  <div className="border-b border-[#44474a] p-6">
                    <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">{view === 'join' ? 'Подключение' : 'Денежное вознаграждение'}</div>
                    <h1 className="mt-3 text-3xl font-semibold">{view === 'join' ? 'Подключение к партнерской программе' : 'Оформление агентского договора'}</h1>
                    {view === 'join' ? (
                      <p className="mt-3 max-w-3xl text-sm leading-6 text-[#c5c6ca]">
                        При регистрации партнер автоматически подключается к программе с вознаграждением баллами GLAME. Денежное вознаграждение станет доступно позже, после достижения нужного уровня и проверки данных.
                      </p>
                    ) : null}
                  </div>
                  {view === 'join' ? (
                    <>
                      <div className="grid gap-px bg-[#44474a] md:grid-cols-2">
                        <div className="bg-[#121416] p-6 outline outline-1 outline-[#e2e2e5]">
                          <WalletCards />
                          <div className="mt-4 text-xl font-semibold">Баллы GLAME</div>
                          <p className="mt-3 text-sm leading-6 text-[#c5c6ca]">Стартовый режим для всех партнеров. Процент зависит от годового реферального оборота по уровням оферты.</p>
                          <StatusBadge tone="ok">Подключается сразу</StatusBadge>
                        </div>
                        <div className="bg-[#121416] p-6 opacity-70">
                          <LockKeyhole />
                          <div className="mt-4 text-xl font-semibold">Деньги</div>
                          <p className="mt-3 text-sm leading-6 text-[#c5c6ca]">Открывается с уровня Stylish Pro: годовой реферальный оборот от 50 001 ₽. Для перехода нужны ИНН, паспортные данные, реквизиты и агентское оформление.</p>
                          <StatusBadge tone="warn">После уровня Stylish Pro</StatusBadge>
                        </div>
                      </div>
                      <div className="grid gap-4 border-t border-[#44474a] p-6 md:grid-cols-3">
                        <label className="block">
                          <span className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">ФИО</span>
                          <input value={joinForm.fullName} onChange={(event) => setJoinForm((prev) => ({ ...prev, fullName: event.target.value }))} className="mt-2 w-full border border-[#44474a] bg-[#0c0e10] px-4 py-3 text-[#e2e2e5] outline-none" />
                        </label>
                        <label className="block">
                          <span className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">Телефон</span>
                          <input value={joinForm.phone} onChange={(event) => setJoinForm((prev) => ({ ...prev, phone: event.target.value }))} className="mt-2 w-full border border-[#44474a] bg-[#0c0e10] px-4 py-3 text-[#e2e2e5] outline-none" placeholder="+7" />
                        </label>
                        <label className="block">
                          <span className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">Пароль</span>
                          <input value={joinForm.password} onChange={(event) => setJoinForm((prev) => ({ ...prev, password: event.target.value }))} type="password" className="mt-2 w-full border border-[#44474a] bg-[#0c0e10] px-4 py-3 text-[#e2e2e5] outline-none" />
                        </label>
                        <label className="flex items-start gap-3 border border-[#44474a] bg-[#1a1c1e] p-4 text-sm leading-6 text-[#c5c6ca] md:col-span-3">
                          <input
                            type="checkbox"
                            checked={joinForm.offerAccepted}
                            onChange={(event) => setJoinForm((prev) => ({ ...prev, offerAccepted: event.target.checked }))}
                            className="mt-1"
                          />
                          <span>
                            Ознакомлен с условиями оферты реферальной программы GLAME.{' '}
                            <a href={OFFER_URL} target="_blank" rel="noreferrer" className="text-[#e2e2e5] underline underline-offset-4">
                              Открыть оферту
                            </a>
                          </span>
                        </label>
                        {joinError ? <div className="border border-[#7a3a3a] bg-[#1a1111] p-4 text-sm text-[#f0c7c7] md:col-span-3">{joinError}</div> : null}
                      </div>
                    </>
                  ) : null}
                  {rewardType === 'cash' ? (
                    <div className="grid gap-4 p-6 md:grid-cols-2">
                      {['ФИО', 'ИНН', 'Паспортные данные', 'Платежные реквизиты'].map((label) => (
                        <label key={label} className="block">
                          <span className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">{label}</span>
                          <input className="mt-2 w-full border border-[#44474a] bg-[#0c0e10] px-4 py-3 text-[#e2e2e5] outline-none" />
                        </label>
                      ))}
                      <div className="border border-[#44474a] bg-[#1a1c1e] p-4 md:col-span-2">
                        <label className="flex items-start gap-3 text-sm leading-6 text-[#c5c6ca]">
                          <input type="checkbox" className="mt-1" />
                          Подтверждаю, что являюсь ИП или самозанятым и самостоятельно оплачиваю налоги за себя.
                        </label>
                      </div>
                    </div>
                  ) : null}
                  <div className="border-t border-[#44474a] p-6">
                    <button disabled={joinLoading} onClick={() => { if (view === 'cashSetup') { setRewardType('cash'); setView('dashboard'); } else { void submitJoin(); } }} className="border border-[#e2e2e5] bg-[#e2e2e5] px-5 py-4 text-sm font-semibold uppercase tracking-[0.14em] text-[#171c1f] disabled:cursor-wait disabled:opacity-60">
                      {view === 'cashSetup' ? 'Отправить данные на проверку' : joinLoading ? 'Подключаем...' : 'Подключить программу'}
                    </button>
                  </div>
                </div>
              </section>
            ) : null}

            {view === 'dashboard' ? (
              <section className="space-y-6">
                <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                  <div className="border border-[#44474a] bg-[#121416] p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">Ваш код</div>
                        <div className="mt-3 text-4xl font-semibold tracking-[0.08em]">{referralCode}</div>
                      </div>
                      <div className="grid h-32 w-32 place-items-center border border-[#44474a] bg-[#e2e2e5] p-2 text-[#171c1f]">
                        {qrDataUrl ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={qrDataUrl} alt={`QR для РМК ${referralRmkCode}`} className="h-full w-full" />
                        ) : (
                          <span className="text-center text-[10px] font-semibold uppercase tracking-[0.12em] text-[#171c1f]">QR появится после загрузки кода</span>
                        )}
                      </div>
                    </div>
                    <div className="mt-5 flex flex-col gap-3 md:flex-row">
                      <button onClick={() => copy(referralCode, 'code')} className="inline-flex items-center justify-center gap-2 border border-[#44474a] px-4 py-3 text-sm uppercase tracking-[0.12em]">
                        <Clipboard size={16} /> {copied === 'code' ? 'Скопировано' : 'Скопировать код'}
                      </button>
                      <button disabled={manualSyncLoading} onClick={() => void syncReferralsFromOneC()} className="inline-flex items-center justify-center gap-2 border border-[#44474a] px-4 py-3 text-sm uppercase tracking-[0.12em] disabled:cursor-wait disabled:opacity-60">
                        <RefreshCcw size={16} /> {manualSyncLoading ? 'Обновление...' : 'Обновить данные о покупках рефералов'}
                      </button>
                    </div>
                    {manualSyncMessage ? <div className="mt-4 border border-[#43564a] bg-[#17251d] p-3 text-sm text-[#b9dec5]">{manualSyncMessage}</div> : null}
                    {manualSyncError ? <div className="mt-4 border border-[#7a3a3a] bg-[#1a1111] p-3 text-sm text-[#f0c7c7]">{manualSyncError}</div> : null}
                  </div>
                  <div className="border border-[#44474a] bg-[#121416] p-5">
                    <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">Учетный статус</div>
                    <div className="mt-5 grid gap-3">
                      {rewardType === 'cash' ? (
                        <>
                          <div className="flex items-center gap-3"><ShieldCheck className="text-[#b9dec5]" /> Паспортные данные проверены</div>
                          <div className="flex items-center gap-3"><Landmark className="text-[#b9dec5]" /> Контрагент 1С создан</div>
                          <div className="flex items-center gap-3"><FileCheck2 className="text-[#b9dec5]" /> {member.onec_agency_contract_id ? 'Агентский договор активен' : 'Агентский договор ожидает оформления'}</div>
                        </>
                      ) : (
                        <>
                          <div className="flex items-center gap-3"><Check className="text-[#b9dec5]" /> Балльный режим активен</div>
                          <div className="flex items-center gap-3"><WalletCards className="text-[#c5c6ca]" /> Доступно {profile.loyalty_points || 0} баллов</div>
                          <div className="flex items-start gap-3 text-[#c5c6ca]">
                            <LockKeyhole className="mt-0.5 shrink-0" />
                            <span>Денежное вознаграждение откроется с уровня Stylish Pro: годовой реферальный оборот от 50 001 ₽.</span>
                          </div>
                          <button
                            disabled={!cashUpgradeEligible}
                            onClick={() => { setRewardType('cash'); setView('cashSetup'); }}
                            className={`mt-2 border px-4 py-3 text-sm uppercase tracking-[0.12em] ${cashUpgradeEligible ? 'border-[#e2e2e5] bg-[#e2e2e5] text-[#171c1f]' : 'cursor-not-allowed border-[#44474a] text-[#8f9194]'}`}
                          >
                            Перейти на денежное вознаграждение
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {ratePromotion && rewardType === 'points' ? (
                  <div className="border border-[#d8c88c] bg-[#19170f] p-5">
                    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-[#d8c88c]">
                          <BadgeCheck size={16} /> Акция для партнеров
                        </div>
                        <h2 className="mt-3 text-2xl font-semibold text-[#f4f0dd]">{ratePromotion.title}</h2>
                        <p className="mt-2 max-w-3xl text-sm leading-6 text-[#d8d0aa]">
                          {ratePromotion.status === 'active' ? 'Сейчас действует повышенное начисление:' : 'Запланировано повышенное начисление:'}{' '}
                          {ratePromotion.rate_percent}% от суммы покупок рефералов в баллах GLAME.
                        </p>
                      </div>
                      <div className="border border-[#6a6040] px-5 py-4 text-left md:min-w-72">
                        <div className="text-xs uppercase tracking-[0.2em] text-[#a9a17a]">{ratePromotion.status === 'active' ? 'Действует до' : 'Период'}</div>
                        <div className="mt-2 text-lg font-semibold text-[#f4f0dd]">
                          {ratePromotion.status === 'active'
                            ? dateRu(ratePromotion.ends_at)
                            : `${dateRu(ratePromotion.starts_at)} — ${dateRu(ratePromotion.ends_at)}`}
                        </div>
                        <div className="mt-1 text-sm text-[#bfb68a]">Стандартная ставка: {baseRate}%</div>
                      </div>
                    </div>
                  </div>
                ) : null}

                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <Metric label="Регистрации" value={`${summary.registrations}`} sub="за 30 дней" />
                  <Metric label="Покупки" value={`${summary.purchases}`} sub={`${summary.active_referrals} активных рефералов`} />
                  <Metric label="Оборот" value={money(summary.referral_revenue)} sub="без доставки" />
                  <Metric label={rewardType === 'cash' ? 'Начислено в 1С' : 'Зачислено баллов'} value={rewardType === 'cash' ? money(summary.accrued_in_1c) : `${summary.posted_points} баллов`} sub="после холда" />
                </div>

                <div className="border border-[#44474a] bg-[#121416] p-5">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                      <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">{token.token_name}</div>
                      <div className="mt-3 text-3xl font-semibold">{onchainGlmLabel}</div>
                      <p className="mt-2 max-w-2xl text-sm leading-6 text-[#c5c6ca]">
                        GLM хранится в TON-кошельке. Баллы GLAME, GLM в TON и внутренний холд показаны отдельно, чтобы обмены не смешивались в один баланс.
                      </p>
                    </div>
                    <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4 md:min-w-[560px]">
                      <div className="border border-[#2c3033] bg-[#0c0e10] p-4">
                        <div className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">Баллы GLAME</div>
                        <div className="mt-2 text-xl font-semibold">{profile.loyalty_points || 0}</div>
                        <div className="mt-1 text-xs text-[#8f9194]">для скидки и обмена</div>
                      </div>
                      <div className="border border-[#2c3033] bg-[#0c0e10] p-4">
                        <div className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">GLM в TON</div>
                        <div className="mt-2 text-xl font-semibold">{onchainGlmLabel}</div>
                        <div className="mt-1 text-xs text-[#8f9194]">{onchainStatusLabel}</div>
                      </div>
                      <div className="border border-[#2c3033] bg-[#0c0e10] p-4">
                        <div className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">GLM в холде</div>
                        <div className="mt-2 text-xl font-semibold">{token.hold_balance} {token.token_code}</div>
                        <div className="mt-1 text-xs text-[#8f9194]">ожидает release</div>
                      </div>
                      <div className="border border-[#2c3033] bg-[#0c0e10] p-4">
                        <div className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">TON-заявки</div>
                        <div className="mt-2 text-xl font-semibold">{token.pending_claim_amount || 0} {token.token_code}</div>
                        <div className="mt-1 text-xs text-[#8f9194]">в обработке</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid gap-6 xl:grid-cols-2">
                  <div>
                    <div className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#8f9194]">Последние рефералы</div>
                    <DataTable headers={['Имя', 'Телефон', 'Источник', 'Статус', 'Покупки', 'Сумма', 'Вознаграждение']} rows={rows} />
                  </div>
                  <div>
                    <div className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#8f9194]">Начисления</div>
                    <DataTable
                      headers={['Дата', 'База', 'Ставка', 'Вознаграждение', 'GLM', 'Статус']}
                      rows={visibleCommissions.map((item) => [dateRu(item.date), money(item.base), `${item.rate}%`, rewardType === 'cash' ? money(item.amount) : `${item.points} баллов`, item.glm?.amount ? `${item.glm.amount} GLM` : '—', <StatusBadge key={item.id || item.date || item.status} tone={commissionStatusTone(item.status)}>{commissionStatusLabel(item)}</StatusBadge>])}
                    />
                  </div>
                </div>
              </section>
            ) : null}

            {view === 'referrals' ? (
              <section>
                <PageTitle title="Рефералы" subtitle="Регистрации, первые покупки и накопленная статистика по каждому приглашенному клиенту." />
                <DataTable headers={['Имя', 'Телефон', 'Источник', 'Статус', 'Покупки', 'Сумма', 'Вознаграждение']} rows={rows} />
              </section>
            ) : null}

            {view === 'commissions' ? (
              <section>
                <PageTitle title={rewardType === 'cash' ? 'Агентские начисления' : 'Балльные начисления'} subtitle="Все начисления проходят холд и получают итоговый статус после проверки покупки." />
                <DataTable
                  headers={rewardType === 'cash' ? ['Дата', 'Холд до', 'База', 'Сумма', 'GLM', '1С', 'Документ'] : ['Дата', 'Холд до', 'База', 'Баллы', 'GLM', 'Статус', 'Документ']}
                  rows={visibleCommissions.map((item) =>
                    rewardType === 'cash'
                      ? [dateRu(item.date), dateRu(item.hold_until), money(item.base), money(item.amount), item.glm?.amount ? `${item.glm.amount} GLM` : '—', commissionStatusLabel(item), item.onec_document_id || '—']
                      : [dateRu(item.date), dateRu(item.hold_until), money(item.base), `${item.points} баллов`, item.glm?.amount ? `${item.glm.amount} GLM` : '—', commissionStatusLabel(item), item.onec_document_id || 'loyalty_transactions']
                  )}
                />
              </section>
            ) : null}

            {view === 'payouts' ? (
              <section>
                <PageTitle title={rewardType === 'cash' ? 'Выплаты' : 'Баллы GLAME'} subtitle={rewardType === 'cash' ? 'Денежные выплаты доступны после активного агентского договора и начисления в 1С.' : 'Баллы хранятся в 1С и могут быть переведены в GLM.'} />
                <div className={`grid gap-3 ${rewardType === 'cash' ? 'md:grid-cols-3' : 'md:grid-cols-4'}`}>
                  <Metric label={rewardType === 'cash' ? 'Доступно к выплате' : 'Доступно баллов'} value={rewardType === 'cash' ? money(summary.approved_commission) : `${profile.loyalty_points || 0} баллов`} />
                  {rewardType === 'points' ? <Metric label="Баллы в холде" value={`${summary.pending_points || 0} баллов`} /> : null}
                  <Metric label={rewardType === 'cash' ? 'Выплачено' : 'Зачислено'} value={rewardType === 'cash' ? money(summary.paid_commission) : `${summary.posted_points} баллов`} />
                  <Metric label="GLAME Coin" value={onchainGlmLabel} sub={onchainStatusLabel} />
                </div>
                <div className="mt-6">
                  <DataTable
                    headers={rewardType === 'cash' ? ['Период', 'Сумма', 'Статус', 'Документ 1С'] : ['Дата', 'Сумма', 'Статус', 'Документ']}
                    rows={payouts.map((item) => [
                      item.period_start || item.period_end ? `${dateRu(item.period_start)} - ${dateRu(item.period_end)}` : dateRu(item.requested_at),
                      money(item.amount),
                      <StatusBadge key={item.id} tone={statusTone(item.status)}>{statusRu(item.status)}</StatusBadge>,
                      item.onec_payment_document_id || '—',
                    ])}
                  />
                </div>
              </section>
            ) : null}

            {view === 'crypto' ? (
              <section>
                <PageTitle title="CryptoGLAME" subtitle="GLAME Coin, TON-кошелек, обмен баллов и дорожная карта полноценного токена GLM." />

                <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
                  <div className="border border-[#44474a] bg-[#121416] p-5">
                    <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">GLAME Coin</div>
                    <div className="mt-4 text-4xl font-semibold">{token.token_code} в TON</div>
                    <p className="mt-3 text-sm leading-6 text-[#c5c6ca]">
                      GLM — клубная валюта GLAME в TON-кошельке. Платформа показывает операции, заявки и правила обмена, а фактический GLM-баланс хранится в вашем кошельке.
                    </p>
                    <div className="mt-4 flex flex-wrap gap-2 text-xs">
                      <a href="/static/glm_policy/token-policy.md" target="_blank" rel="noreferrer" className="border border-[#44474a] px-3 py-2 text-[#c5c6ca]">Token policy</a>
                      <a href="/static/glm_policy/risk-disclosure.md" target="_blank" rel="noreferrer" className="border border-[#44474a] px-3 py-2 text-[#c5c6ca]">Risk disclosure</a>
                        <a href="/static/glm_policy/bridge-rules.md" target="_blank" rel="noreferrer" className="border border-[#44474a] px-3 py-2 text-[#c5c6ca]">Правила обмена</a>
                      <a href="/api/referrals/glm-audit-hashes/public" target="_blank" rel="noreferrer" className="border border-[#44474a] px-3 py-2 text-[#c5c6ca]">Audit journal</a>
                    </div>
                    <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                      <Metric label="Баллы GLAME" value={`${profile.loyalty_points || 0}`} sub="доступны к списанию" />
                      <Metric label="GLM в TON" value={onchainGlmLabel} sub={onchainStatusLabel} />
                      <Metric label="TON wallet" value={token.claim_wallet_address ? 'Подключен' : 'Не подключен'} sub={token.claim_enabled ? 'вывод разрешен' : 'нужна проверка'} />
                      <Metric label="GLM в отправке" value={`${token.pending_claim_amount || 0} GLM`} sub="ожидает TON" />
                    </div>
                    <div className="mt-5 border border-[#44474a] bg-[#0c0e10] p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <div className="text-xs uppercase tracking-[0.18em] text-[#8f9194]">Referral campaign</div>
                          <div className="mt-2 text-xl font-semibold text-[#e2e2e5]">{token.referral_campaign?.active ? token.referral_campaign.name : 'Обычный GLM-режим'}</div>
                          <div className="mt-1 text-xs leading-5 text-[#8f9194]">
                            {token.referral_campaign?.active
                              ? `Множитель x${token.referral_campaign.multiplier}${token.referral_campaign.until ? ` до ${dateRu(token.referral_campaign.until)}` : ''}.`
                              : 'Новые реферальные начисления идут по базовому правилу 1 GLM за 1 ₽ вознаграждения.'}
                          </div>
                        </div>
                        <StatusBadge tone={token.referral_campaign?.active ? 'ok' : 'neutral'}>{token.referral_campaign?.active ? `x${token.referral_campaign.multiplier}` : 'Base'}</StatusBadge>
                      </div>
                    </div>
                    <div className="mt-5 border border-[#44474a] bg-[#0c0e10] p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <div className="text-xs uppercase tracking-[0.18em] text-[#8f9194]">GLM статус</div>
                          <div className="mt-2 text-2xl font-semibold text-[#e2e2e5]">{token.privilege_tier?.name || 'GLM Start'}</div>
                          <div className="mt-1 text-xs leading-5 text-[#8f9194]">
                            Статусный счет: {token.privilege_score || 0} GLM{token.privilege_score_basis === 'ton_wallet_balance' ? ' · по TON-балансу' : ''}
                            {token.next_privilege_tier ? ` · до ${token.next_privilege_tier.name}: ${token.privilege_to_next || 0} GLM` : ' · максимальный уровень'}
                          </div>
                        </div>
                        <StatusBadge tone={token.next_privilege_tier ? 'warn' : 'ok'}>
                          {token.next_privilege_tier ? `${token.privilege_progress_percent || 0}%` : 'Max'}
                        </StatusBadge>
                      </div>
                      <div className="mt-4 h-2 overflow-hidden bg-[#1e2022]">
                        <div className="h-full bg-[#e2e2e5]" style={{ width: `${Math.min(100, Math.max(0, token.privilege_progress_percent || 0))}%` }} />
                      </div>
                      <div className="mt-4 grid gap-2 sm:grid-cols-2">
                        {(token.privilege_tier?.benefits || []).map((benefit) => (
                          <div key={benefit} className="border border-[#333537] bg-[#121416] px-3 py-2 text-xs leading-5 text-[#c5c6ca]">{benefit}</div>
                        ))}
                      </div>
                    </div>
                    <div className="mt-5 border border-[#44474a] bg-[#0c0e10] p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                        <div>
                          <div className="text-sm font-semibold text-[#e2e2e5]">Баллы -&gt; GLM в TON</div>
                          <div className="mt-1 text-xs leading-5 text-[#8f9194]">
                            Доступно {profile.loyalty_points || 0} баллов. Баллы списываются в 1С, а GLM отправляется в подтвержденный TON-кошелек автоматически.
                          </div>
                          <div className="mt-2 text-xs leading-5 text-[#8f9194]">
                            Курс: 1 балл = 1 GLM · лимит операции {token.bonus_conversion_policy?.min_points || 100}-{token.bonus_conversion_policy?.max_points || 10000} · месяц {token.bonus_conversion_policy?.monthly_limit || 50000} GLM
                            {token.pending_claim ? ' · уже есть заявка в обработке' : token.claim_allowed ? '' : ' · нужен подтвержденный TON-кошелек и разрешение администратора'}
                          </div>
                        </div>
                        <div className="grid gap-2 sm:grid-cols-[minmax(140px,1fr)_auto]">
                          <input
                            value={convertPoints}
                            onChange={(event) => setConvertPoints(event.target.value.replace(/[^\d]/g, ''))}
                            placeholder="1000"
                            inputMode="numeric"
                            className="min-h-[44px] border border-[#44474a] bg-[#121416] px-4 py-3 text-[#e2e2e5] outline-none"
                          />
                          <button
                            disabled={convertLoading || !(profile.loyalty_points || 0) || !token.claim_allowed || !!token.pending_claim}
                            onClick={() => void submitBonusConversion()}
                            className="inline-flex min-h-[44px] items-center justify-center gap-2 border border-[#e2e2e5] bg-[#e2e2e5] px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#171c1f] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <RefreshCcw size={15} /> {convertLoading ? 'Создаем...' : 'В TON'}
                          </button>
                        </div>
                      </div>
                      {convertMessage ? <div className="mt-3 border border-[#43564a] bg-[#17251d] p-3 text-sm text-[#b9dec5]">{convertMessage}</div> : null}
                      {convertError ? <div className="mt-3 border border-[#7a3a3a] bg-[#1a1111] p-3 text-sm text-[#f0c7c7]">{convertError}</div> : null}
                      <div className="mt-3 grid gap-3 sm:grid-cols-3">
                        <Metric label="TON network" value={token.onchain_policy?.network || 'testnet'} sub={token.onchain_policy?.standard || 'TON Jetton / TEP-74'} />
                        <Metric label="Jetton status" value={token.onchain_policy?.status || 'draft_not_deployed'} sub={tonPolicyModeLabel(token.onchain_policy?.claim_mode)} />
                        <Metric label="Mainnet" value={token.onchain_policy?.mainnet_enabled ? 'Enabled' : 'Blocked'} sub={token.onchain_policy?.mainnet_gate || 'legal/security approval'} />
                      </div>
                      {token.onchain_policy?.jetton_master_address || token.onchain_policy?.metadata_url ? (
                        <div className="mt-3 border border-[#333537] bg-[#121416] p-3 text-xs leading-5 text-[#8f9194]">
                          {token.onchain_policy?.jetton_master_address ? (
                            <div className="break-all font-mono text-[#c5c6ca]">master: {token.onchain_policy.jetton_master_address}</div>
                          ) : null}
                          {token.onchain_policy?.metadata_url ? (
                            <a href={token.onchain_policy.metadata_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-[#c5c6ca] underline underline-offset-4">Jetton metadata</a>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                    <div className="mt-5 border border-[#44474a] bg-[#0c0e10] p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                        <div>
                          <div className="text-sm font-semibold text-[#e2e2e5]">GLM из TON -&gt; баллы GLAME</div>
                          <div className="mt-1 text-xs leading-5 text-[#8f9194]">
                            Создайте заявку, затем подтвердите перевод GLM из вашего TON-кошелька в GLAME. Баллы начисляются после проверки TON-перевода и обработки 1С.
                          </div>
                          <div className="mt-2 text-xs leading-5 text-[#8f9194]">
                            Ориентир MVP: 1 GLM = 1 балл. Баллы GLAME живут по правилам программы, GLM списывается только фактическим переводом в TON.
                          </div>
                        </div>
                        <div className="grid gap-2 sm:grid-cols-[minmax(140px,1fr)_auto]">
                          <input
                            value={glmToPointsAmount}
                            onChange={(event) => setGlmToPointsAmount(event.target.value.replace(/[^\d]/g, ''))}
                            placeholder="1000"
                            inputMode="numeric"
                            className="min-h-[44px] border border-[#44474a] bg-[#121416] px-4 py-3 text-[#e2e2e5] outline-none"
                          />
                          <button
                            disabled={glmToPointsLoading || !token.claim_wallet_address || !!pendingGlmToPointsBridge}
                            onClick={() => void submitGlmToPointsBridge()}
                            className="inline-flex min-h-[44px] items-center justify-center gap-2 border border-[#e2e2e5] bg-[#e2e2e5] px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#171c1f] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <RefreshCcw size={15} /> {glmToPointsLoading ? 'Создаем...' : 'В баллы'}
                          </button>
                        </div>
                      </div>
                      <div className="mt-3 grid gap-3 lg:grid-cols-2">
                        <div className="border border-[#333537] bg-[#121416] p-3">
                          <div className="text-[10px] uppercase tracking-[0.18em] text-[#8f9194]">Отправитель</div>
                          <div className="mt-2 break-all font-mono text-xs text-[#c5c6ca]">
                            {pendingGlmToPointsBridge?.expected_ton_sender_address || token.claim_wallet_address || 'Подтвердите TON-кошелек'}
                          </div>
                        </div>
                        <div className="border border-[#333537] bg-[#121416] p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-[10px] uppercase tracking-[0.18em] text-[#8f9194]">Treasury GLAME</div>
                              <div className="mt-2 break-all font-mono text-xs text-[#c5c6ca]">{glmDepositTreasuryAddress || 'Treasury не настроен'}</div>
                            </div>
                            {glmDepositTreasuryAddress ? (
                              <button
                                onClick={() => void copy(glmDepositTreasuryAddress, 'glm-treasury')}
                                className="inline-flex min-h-[34px] shrink-0 items-center justify-center gap-2 border border-[#44474a] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#e2e2e5]"
                              >
                                <Clipboard size={13} /> {copied === 'glm-treasury' ? 'OK' : 'Copy'}
                              </button>
                            ) : null}
                          </div>
                        </div>
                      </div>
                      {pendingGlmToPointsBridge ? (
                        <div className="mt-3 border border-[#6d5b2f] bg-[#1d190f] p-3 text-sm text-[#f0d99c]">
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                            <div>
                              <div className="text-sm font-semibold text-[#f7e2a8]">{pendingGlmToPointsStatus?.title || 'Заявка GLM -> баллы'}</div>
                              <div className="mt-1 text-sm leading-5">{pendingGlmToPointsStatus?.text}</div>
                            </div>
                            <span className="inline-flex shrink-0 border border-[#6d5b2f] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em]">
                              {statusRu(pendingGlmToPointsStatus?.code)}
                            </span>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            <button
                              disabled={glmToPointsLoading}
                              onClick={() => void confirmPendingGlmToPointsBridgeTransfer()}
                              className="inline-flex min-h-[40px] items-center justify-center gap-2 border border-[#e2e2e5] bg-[#e2e2e5] px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#171c1f] disabled:cursor-wait disabled:opacity-60"
                            >
                              <WalletCards size={15} /> {glmToPointsLoading ? 'Открываем кошелек...' : 'Подтвердить в кошельке'}
                            </button>
                            <button
                              disabled={glmToPointsLoading}
                              onClick={() => void cancelPendingGlmToPointsBridge()}
                              className="inline-flex min-h-[40px] items-center justify-center gap-2 border border-[#6d5b2f] px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#f0d99c] disabled:cursor-wait disabled:opacity-60"
                            >
                              Отменить заявку
                            </button>
                          </div>
                          <div className="mt-2 text-xs leading-5 text-[#d7c485]">
                            Резервный вариант: вручную отправьте GLM на адрес GLAME {glmDepositTreasuryAddress || ''}. Если автоматическая проверка не увидит перевод, администратор сможет проверить его по TON tx.
                          </div>
                        </div>
                      ) : null}
                      {glmToPointsMessage ? <div className="mt-3 border border-[#43564a] bg-[#17251d] p-3 text-sm text-[#b9dec5]">{glmToPointsMessage}</div> : null}
                      {glmToPointsError ? <div className="mt-3 border border-[#7a3a3a] bg-[#1a1111] p-3 text-sm text-[#f0c7c7]">{glmToPointsError}</div> : null}
                    </div>
                  </div>

                  <div className="border border-[#44474a] bg-[#121416] p-5">
                    <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">TON-кошелек</div>
                    <div className="mt-4 flex flex-wrap items-center gap-3">
                      <TonConnectButton />
                      <button
                        disabled={tonProofLoading || walletLoading}
                        onClick={() => void reconnectTonWalletForProof()}
                        className="inline-flex min-h-[40px] items-center justify-center gap-2 border border-[#44474a] px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#e2e2e5] disabled:cursor-wait disabled:opacity-60"
                      >
                        <ShieldCheck size={15} /> {tonProofLoading ? 'Готовим...' : tonWallet ? 'Переподключить с proof' : 'Подключить с proof'}
                      </button>
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <Metric label="TON Connect" value={tonWallet ? 'Подключен' : 'Не подключен'} sub={tonWallet?.device?.appName || 'Wallet modal'} />
                      <Metric
                        label="Proof"
                        value={member.crypto_wallet?.status === 'verified' ? 'Verified' : tonProofReady ? 'Нужно подключить' : 'Ожидает'}
                        sub={member.crypto_wallet?.status === 'verified' ? 'подпись кошелька' : 'резервный адрес'}
                      />
                    </div>
                    {tonWallet ? (
                      <div className="mt-4 border border-[#44474a] bg-[#0c0e10] p-3 text-xs leading-5 text-[#c5c6ca]">
                        TON Connect: {tonFriendlyAddress || tonRawAddress}
                      </div>
                    ) : null}
                    <div className="mt-4 grid gap-4">
                      <label className="block">
                        <span className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">Метка</span>
                        <input
                          value={walletForm.label}
                          onChange={(event) => setWalletForm((prev) => ({ ...prev, label: event.target.value }))}
                          className="mt-2 w-full border border-[#44474a] bg-[#0c0e10] px-4 py-3 text-[#e2e2e5] outline-none"
                        />
                      </label>
                      <label className="block">
                        <span className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">TON address</span>
                        <input
                          value={walletForm.address}
                          onChange={(event) => setWalletForm((prev) => ({ ...prev, address: event.target.value }))}
                          placeholder="EQ... или UQ..."
                          className="mt-2 w-full border border-[#44474a] bg-[#0c0e10] px-4 py-3 text-[#e2e2e5] outline-none"
                        />
                      </label>
                    </div>
                    {member.crypto_wallet?.address ? (
                      <div className="mt-4 border border-[#43564a] bg-[#17251d] p-3 text-sm text-[#b9dec5]">
                        {member.crypto_wallet.status === 'verified' ? 'Подтвержден' : 'Привязан'}: {member.crypto_wallet.address}
                      </div>
                    ) : null}
                    {walletMessage ? <div className="mt-4 border border-[#43564a] bg-[#17251d] p-3 text-sm text-[#b9dec5]">{walletMessage}</div> : null}
                    {walletError ? <div className="mt-4 border border-[#7a3a3a] bg-[#1a1111] p-3 text-sm text-[#f0c7c7]">{walletError}</div> : null}
                    <button
                      disabled={walletLoading}
                      onClick={() => void submitCryptoWallet()}
                      className="mt-4 inline-flex items-center justify-center gap-2 border border-[#e2e2e5] bg-[#e2e2e5] px-5 py-4 text-sm font-semibold uppercase tracking-[0.14em] text-[#171c1f] disabled:cursor-wait disabled:opacity-60"
                    >
                      <WalletCards size={16} /> {walletLoading ? 'Сохраняем...' : 'Сохранить кошелек'}
                    </button>
                    <p className="mt-3 text-xs leading-5 text-[#8f9194]">
                      Основной путь — TON Connect с ton_proof подписью. Ручной адрес ниже остается как резерв, но не дает статус verified.
                    </p>
                  </div>
                </div>

                <div className="mt-6 border border-[#44474a] bg-[#121416] p-5">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                      <div>
                        <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">GLM Store</div>
                      <h3 className="mt-2 text-lg font-semibold text-[#e2e2e5]">Товары, сервисы и доступы только за GLM</h3>
                    </div>
                    <div className="text-xs leading-5 text-[#8f9194]">Холдеры, travel pouch, стилист, закрытые подборки и private sale pass.</div>
                  </div>
                  <div className="mt-4 grid gap-4 lg:grid-cols-3">
                    {(token.store_items || []).map((item) => {
                      const priceGlm = Number(item.price_glm || 0);
                      const pricePoints = Number(item.price_points || 0);
                      const storeCheckoutEnabled = Boolean(token.store_checkout_policy?.enabled || token.store_checkout_policy?.mode === 'ton_deposit_required');
                      const quantityAvailable = item.quantity_available === null || item.quantity_available === undefined ? null : Number(item.quantity_available);
                      const hasStock = quantityAvailable === null || quantityAvailable > 0;
                      const itemAvailable = ['available', 'limited'].includes(item.status) && hasStock;
                      const canBuy = storeCheckoutEnabled && priceGlm > 0 && onchainGlmBalance >= priceGlm && itemAvailable;
                      const canBuyWithPoints = pricePoints > 0 && Number(profile.loyalty_points || 0) >= pricePoints && itemAvailable;
                      const glmLoadingKey = `glm:${item.sku}`;
                      const pointsLoadingKey = `points:${item.sku}`;
                      const buttonLabel = redeemLoadingSku === glmLoadingKey
                        ? 'Оформляем...'
                        : !priceGlm
                          ? 'Только за баллы'
                          : !storeCheckoutEnabled
                            ? 'TON checkout скоро'
                            : !hasStock
                              ? 'Нет в наличии'
                              : canBuy
                              ? 'Оплатить GLM в TON'
                              : 'Не хватает GLM';
                      return (
                        <div key={item.sku} className="border border-[#333537] bg-[#0c0e10] p-4">
                          {item.image_url ? (
                            <div className="mb-4 aspect-[4/3] overflow-hidden border border-[#333537] bg-[#121416]">
                              <img src={item.image_url} alt={item.title} className="h-full w-full object-cover" />
                            </div>
                          ) : null}
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-sm font-semibold text-[#e2e2e5]">{item.title}</div>
                              <div className="mt-2 text-xs leading-5 text-[#8f9194]">{item.description}</div>
                            </div>
                            <StatusBadge tone={item.inventory_status === 'limited' ? 'warn' : 'ok'}>
                              {item.category === 'service' ? 'Service' : item.category === 'access_pass' ? 'Access' : item.inventory_status === 'limited' ? 'Limited' : 'Pilot'}
                            </StatusBadge>
                          </div>
                          <div className="mt-4 text-2xl font-semibold text-[#e2e2e5]">{priceGlm ? `${priceGlm} GLM` : 'GLM —'}</div>
                          {item.price_points ? <div className="mt-1 text-sm text-[#b4b6ba]">{item.price_points} баллов GLAME</div> : null}
                          {quantityAvailable !== null ? (
                            <div className={`mt-2 text-xs uppercase tracking-[0.14em] ${quantityAvailable > 0 ? 'text-[#b9dec5]' : 'text-[#f0c7c7]'}`}>
                              {quantityAvailable > 0 ? `Осталось ${quantityAvailable} шт.` : 'Нет в наличии'}
                            </div>
                          ) : null}
                          <button
                            disabled={!priceGlm || !canBuy || redeemLoadingSku === glmLoadingKey}
                            onClick={() => void submitGlmStoreRedeem(item.sku)}
                            className="mt-4 w-full border border-[#e2e2e5] bg-[#e2e2e5] px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#171c1f] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {buttonLabel}
                          </button>
                          {pricePoints > 0 ? (
                            <button
                              disabled={!canBuyWithPoints || redeemLoadingSku === pointsLoadingKey}
                              onClick={() => void submitRewardStorePointsRedeem(item.sku)}
                              className="mt-2 w-full border border-[#55585c] px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#e2e2e5] disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {redeemLoadingSku === pointsLoadingKey ? 'Списываем баллы...' : !hasStock ? 'Нет в наличии' : canBuyWithPoints ? 'Купить за баллы' : 'Не хватает баллов'}
                            </button>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                  {token.store_checkout_policy?.description ? (
                    <div className="mt-4 border border-[#3a3d40] bg-[#0c0e10] p-3 text-xs leading-5 text-[#8f9194]">
                      {token.store_checkout_policy.description}
                    </div>
                  ) : null}
                  {redeemMessage ? <div className="mt-4 border border-[#43564a] bg-[#17251d] p-3 text-sm text-[#b9dec5]">{redeemMessage}</div> : null}
                  {redeemError ? <div className="mt-4 border border-[#7a3a3a] bg-[#1a1111] p-3 text-sm text-[#f0c7c7]">{redeemError}</div> : null}
                </div>

                <div className="mt-6 grid gap-6 xl:grid-cols-2">
                  <div className="border border-[#44474a] bg-[#121416] p-5">
                    <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">Где использовать GLM</div>
                    <div className="mt-4 grid gap-3">
                      {(token.use_cases || []).map((item) => (
                        <div key={item.code} className="border border-[#333537] bg-[#0c0e10] p-4">
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                            <div>
                              <div className="text-sm font-semibold text-[#e2e2e5]">{item.title}</div>
                              <div className="mt-1 text-xs leading-5 text-[#8f9194]">{item.description}</div>
                            </div>
                            <StatusBadge tone={item.status === 'pilot_ready' ? 'ok' : 'warn'}>{item.status === 'pilot_ready' ? 'Pilot' : 'Draft'}</StatusBadge>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="border border-[#44474a] bg-[#121416] p-5">
                    <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">GLM обмен внутри GLAME</div>
                    <p className="mt-3 text-sm leading-6 text-[#c5c6ca]">
                      {token.internal_value_rule?.disclaimer || 'Внутренняя ценность GLM применяется только по правилам программы и не является обещанием обратного выкупа.'}
                    </p>
                    <p className="mt-3 text-xs leading-5 text-[#8f9194]">
                      {token.expiry_policy?.description || 'GLM не сгорает по календарю. Бонусные баллы GLAME живут по текущим правилам и могут сгорать до перевода в GLM.'}
                    </p>
                    <div className="mt-4">
                      <DataTable
                        headers={['Категория', 'Лимит', 'Правило']}
                        rows={(token.acceptance_rules || []).map((rule) => [
                          rule.category,
                          `${rule.limit_percent}%`,
                          rule.note,
                        ])}
                      />
                    </div>
                  </div>
                </div>

                <div className="mt-6 grid gap-6 xl:grid-cols-2">
                  <div>
                    <div className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#8f9194]">Токеномика</div>
                    <DataTable headers={['Пул', 'Доля', 'Назначение']} rows={tokenomicsRows} />
                  </div>
                  <div>
                    <div className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#8f9194]">Roadmap</div>
                    <DataTable headers={['Этап', 'Название', 'Суть']} rows={cryptoRoadmapRows} />
                  </div>
                </div>

                <div className="mt-6">
                  <div className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#8f9194]">GLM уровни</div>
                  <DataTable
                    headers={['Уровень', 'Порог', 'Привилегии']}
                    rows={(token.privilege_tiers || []).map((tier) => [
                      tier.name,
                      `${tier.threshold} GLM`,
                      (tier.benefits || []).join(', ') || '—',
                    ])}
                  />
                </div>

                <div className="mt-6 border border-[#44474a] bg-[#121416] p-5">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">GLM история</div>
                      <h3 className="mt-2 text-lg font-semibold text-[#e2e2e5]">История GLAME Coin</h3>
                    </div>
                    <div className="text-xs leading-5 text-[#8f9194]">Начисления, покупки и обмены. Фактический GLM-баланс читается из TON-кошелька.</div>
                  </div>
                  <div className="mt-4">
                    <DataTable
                      headers={['Дата', 'Тип', 'Статус', 'Сумма', 'Основание']}
                      rows={glmTransactions.map((tx) => {
                        const stage = glmTransactionStage(tx);
                        return [
                          dateRu(tx.created_at),
                          <StatusBadge key={`type-${tx.id}`} tone={stage.tone}>{glmTransactionTypeLabel(tx)}</StatusBadge>,
                          <StatusBadge key={`status-${tx.id}`} tone={stage.tone}>{stage.title}</StatusBadge>,
                          `${tx.amount} GLM`,
                          <div key={`reason-${tx.id}`} className="max-w-[320px]">
                            <div className="text-sm text-[#e2e2e5]">{stage.text}</div>
                            {(tx.tx_hash || tx.deposit_tx_hash) ? (
                              <div className="mt-1 break-all text-xs leading-5 text-[#8f9194]">TON tx: {tx.tx_hash || tx.deposit_tx_hash}</div>
                            ) : null}
                          </div>,
                        ];
                      })}
                    />
                  </div>
                </div>

                <div className="mt-6 grid gap-4 lg:grid-cols-3">
                  <StateCard icon={BadgeCheck} title="1 GLM = 1 ₽ внутри GLAME" text="Внутренний прием работает по правилам программы и лимитам списания, а не как обязательный выкуп за рубли." />
                  <StateCard icon={RefreshCcw} title="GLM -> баллы GLAME" text="Для физического магазина GLM сначала переводится в баллы, а на кассе списываются уже баллы GLAME." />
                  <StateCard icon={LockKeyhole} title="Без обещания цены" text="GLM может стать торгуемым TON Jetton, но рыночная цена определяется спросом, ликвидностью и utility." />
                </div>

                <div className="mt-6 border border-[#44474a] bg-[#121416] p-5">
                  <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">Правила запуска</div>
                  <div className="mt-4 grid gap-3 text-sm leading-6 text-[#c5c6ca] md:grid-cols-2">
                    <div>GLM появляется из реальных покупок, рефералов, бонусов и полезных действий, а не из пустой эмиссии.</div>
                    <div>GLM можно будет передавать и обменивать только после отдельного legal/KYC/AML трека.</div>
                    <div>GLAME не гарантирует рыночную цену, но развивает применение GLM в онлайн-покупках, сервисах и закрытых дропах.</div>
                    <div>Лимиты списания защищают маржу: новые коллекции, основной ассортимент и clearance получают разные правила.</div>
                  </div>
                </div>
              </section>
            ) : null}

            {view === 'media' ? (
              <section>
                <PageTitle title="Медиаматериалы" subtitle="Логотипы, паттерны и фирменные фразы GLAME для публикаций, презентаций и клиентских коммуникаций." />
                {mediaLoading ? <div className="border border-[#44474a] bg-[#121416] p-6 text-sm text-[#8f9194]">Загружаем материалы...</div> : null}
                {!mediaLoading && !mediaMaterials.length ? <div className="border border-[#44474a] bg-[#121416] p-6 text-sm text-[#8f9194]">Материалы пока не загружены.</div> : null}
                <div className="space-y-6">
                  {Object.entries(groupedMediaMaterials).map(([category, items]) => (
                    <div key={category}>
                      <div className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-[#8f9194]">{mediaCategoryLabels[category] || category}</div>
                      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                        {items.map((item) => {
                          const previewUrl = item.preview_url || (item.content_type?.startsWith('image/') ? item.file_url : null);
                          return (
                            <article key={item.id} className="flex min-h-full flex-col border border-[#44474a] bg-[#121416]">
                              <div className="grid aspect-[4/3] place-items-center border-b border-[#44474a] bg-[#0c0e10] p-4">
                                {previewUrl ? (
                                  // eslint-disable-next-line @next/next/no-img-element
                                  <img src={previewUrl} alt={item.title} className="max-h-full max-w-full object-contain" />
                                ) : (
                                  <div className="flex flex-col items-center gap-3 text-[#c5c6ca]">
                                    <FileText size={42} />
                                    <span className="text-xs font-semibold uppercase tracking-[0.16em]">PDF</span>
                                  </div>
                                )}
                              </div>
                              <div className="flex flex-1 flex-col p-4">
                                <div className="text-lg font-semibold">{item.title}</div>
                                {item.description ? <p className="mt-2 flex-1 text-sm leading-6 text-[#8f9194]">{item.description}</p> : <div className="flex-1" />}
                                <div className="mt-4 flex items-center justify-between gap-3 text-xs text-[#8f9194]">
                                  <span>{item.original_file_name}</span>
                                  <span>{fileSizeRu(item.size)}</span>
                                </div>
                                <a href={item.file_url} download className="mt-4 inline-flex items-center justify-center gap-2 border border-[#e2e2e5] bg-[#e2e2e5] px-4 py-3 text-sm font-semibold uppercase tracking-[0.12em] text-[#171c1f]">
                                  <Download size={16} /> Скачать
                                </a>
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            {view === 'profile' ? (
              <section>
                <PageTitle title="Профиль программы" subtitle="Контактные данные, режим вознаграждения и юридический статус." />
                <div className="grid gap-4 lg:grid-cols-2">
                  <ProfileLine label="ФИО" value={profile.full_name || '—'} />
                  <ProfileLine label="Телефон" value={profile.phone || '—'} />
                  <ProfileLine label="Email" value={profile.email || '—'} />
                  <ProfileLine label="Режим" value={rewardType === 'cash' ? 'Денежное вознаграждение' : 'Баллы GLAME'} />
                  <ProfileLine label="Ставка" value={`${effectiveRate}%${ratePromotion?.status === 'active' && rewardType === 'points' ? ' по акции' : ''}`} />
                  {ratePromotion && rewardType === 'points' ? (
                    <ProfileLine
                      label={ratePromotion.status === 'active' ? 'Акция действует' : 'Акция запланирована'}
                      value={`${ratePromotion.title}: ${ratePromotion.rate_percent}% с ${dateRu(ratePromotion.starts_at)} по ${dateRu(ratePromotion.ends_at)}`}
                    />
                  ) : null}
                  <ProfileLine label="GLAME Coin" value={`${onchainGlmLabel} в TON-кошельке; ${token.hold_balance} ${token.token_code} в операционном холде`} />
                  <ProfileLine label="Статус программы" value="Активна" />
                  <ProfileLine label="Покупатель 1С" value={profile.customer_id_1c ? 'Создан' : 'Ожидает синхронизации'} />
                  <ProfileLine label="Карта/телефон 1С" value={profile.discount_card_number || '—'} />
                  <ProfileLine label="Налоговая ответственность" value={rewardType === 'cash' ? 'Подтверждена партнером' : 'Не требуется'} />
                  <ProfileLine label="Паспортные данные" value={rewardType === 'cash' ? 'Проверены' : 'Не требуются'} />
                  <ProfileLine label="Агентский договор" value={rewardType === 'cash' ? (member.onec_agency_contract_id ? 'Активен' : 'Ожидает оформления') : 'Не требуется'} />
                  <ProfileLine label="Контакт программы" value={PROGRAM_EMAIL} />
                </div>
                <div className="mt-6 border border-[#44474a] bg-[#121416] p-5">
                  <div className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">Telegram-уведомления</div>
                  <div className="mt-4 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                      <div className="text-xl font-semibold text-[#e2e2e5]">
                        {profile.telegram_notifications_enabled ? 'Подключены' : 'Не подключены'}
                      </div>
                      <div className="mt-2 text-sm text-[#c5c6ca]">
                        {profile.telegram_chat_id ? `chat id: ${profile.telegram_chat_id}` : 'Подключение подтверждается через Telegram bot.'}
                      </div>
                    </div>
                    <button disabled={telegramLoading} onClick={() => void submitTelegramBind()} className="border border-[#e2e2e5] bg-[#e2e2e5] px-5 py-4 text-sm font-semibold uppercase tracking-[0.14em] text-[#171c1f] disabled:cursor-wait disabled:opacity-60">
                      {telegramLoading ? 'Открываем...' : profile.telegram_notifications_enabled ? 'Переподключить' : 'Открыть Telegram'}
                    </button>
                  </div>
                  {telegramError ? <div className="mt-4 border border-[#7a3a3a] bg-[#1a1111] p-3 text-sm text-[#f0c7c7]">{telegramError}</div> : null}
                  {telegramMessage ? <div className="mt-4 border border-[#43564a] bg-[#17251d] p-3 text-sm text-[#b9dec5]">{telegramMessage}</div> : null}
                </div>
                <div className="mt-6 border border-[#44474a] bg-[#121416] p-5">
                  <div className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">Безопасность</div>
                  <div className="mt-4 grid gap-4 md:grid-cols-3">
                    <label className="block">
                      <span className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">Текущий пароль</span>
                      <input value={passwordForm.current} onChange={(event) => setPasswordForm((prev) => ({ ...prev, current: event.target.value }))} type="password" className="mt-2 w-full border border-[#44474a] bg-[#0c0e10] px-4 py-3 text-[#e2e2e5] outline-none" />
                    </label>
                    <label className="block">
                      <span className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">Новый пароль</span>
                      <input value={passwordForm.next} onChange={(event) => setPasswordForm((prev) => ({ ...prev, next: event.target.value }))} type="password" className="mt-2 w-full border border-[#44474a] bg-[#0c0e10] px-4 py-3 text-[#e2e2e5] outline-none" />
                    </label>
                    <label className="block">
                      <span className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">Повторите пароль</span>
                      <input value={passwordForm.confirm} onChange={(event) => setPasswordForm((prev) => ({ ...prev, confirm: event.target.value }))} type="password" className="mt-2 w-full border border-[#44474a] bg-[#0c0e10] px-4 py-3 text-[#e2e2e5] outline-none" />
                    </label>
                  </div>
                  {passwordError ? <div className="mt-4 border border-[#7a3a3a] bg-[#1a1111] p-3 text-sm text-[#f0c7c7]">{passwordError}</div> : null}
                  {passwordMessage ? <div className="mt-4 border border-[#43564a] bg-[#17251d] p-3 text-sm text-[#b9dec5]">{passwordMessage}</div> : null}
                  <button disabled={passwordLoading} onClick={() => void submitPasswordChange()} className="mt-4 border border-[#e2e2e5] bg-[#e2e2e5] px-5 py-4 text-sm font-semibold uppercase tracking-[0.14em] text-[#171c1f] disabled:cursor-wait disabled:opacity-60">
                    {passwordLoading ? 'Сохраняем...' : 'Изменить пароль'}
                  </button>
                </div>
              </section>
            ) : null}

            {view === 'states' ? (
              <section>
                <PageTitle title="Состояния аккаунта" subtitle="Сценарии, которые портал показывает при модерации, ошибке 1С или блокировке." />
                <div className="grid gap-4 md:grid-cols-3">
                  <StateCard icon={RefreshCcw} title="На проверке" text="Данные отправлены, договор и контрагент создаются после проверки." />
                  <StateCard icon={LockKeyhole} title="Выплаты недоступны" text="Для денежного режима нужен активный агентский договор в 1С." />
                  <StateCard icon={AlertTriangle} title="Ошибка синхронизации" text={`Напишите в партнерскую программу: ${PROGRAM_EMAIL}. Технические логи партнеру не показываем.`} />
                </div>
              </section>
            ) : null}
          </div>
        </main>
      </div>
    </div>
  );
}

function PageTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="mb-6 border border-[#44474a] bg-[#121416] p-5">
      <div className="text-xs uppercase tracking-[0.2em] text-[#8f9194]">GLAME Referral</div>
      <h1 className="mt-3 text-3xl font-semibold">{title}</h1>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-[#c5c6ca]">{subtitle}</p>
    </div>
  );
}

function ProfileLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-[#44474a] bg-[#121416] p-5">
      <div className="text-xs uppercase tracking-[0.16em] text-[#8f9194]">{label}</div>
      <div className="mt-3 text-lg font-semibold">{value}</div>
    </div>
  );
}

function StateCard({ icon: Icon, title, text }: { icon: typeof AlertTriangle; title: string; text: string }) {
  return (
    <div className="border border-[#44474a] bg-[#121416] p-5">
      <Icon className="text-[#c5c6ca]" />
      <div className="mt-4 text-xl font-semibold">{title}</div>
      <p className="mt-3 text-sm leading-6 text-[#8f9194]">{text}</p>
    </div>
  );
}
