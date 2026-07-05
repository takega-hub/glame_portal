'use client';

import { useEffect, useMemo, useState } from 'react';
import { TonConnectButton, useTonConnectModal, useTonConnectUI, useTonWallet } from '@tonconnect/ui-react';
import { apiClient } from '@/lib/api';

type Summary = {
  registrations: number;
  active_referrals: number;
  purchases: number;
  referral_revenue: number;
  pending_commission: number;
  approved_commission: number;
  accrued_in_1c: number;
  paid_commission: number;
  posted_points: number;
  average_check: number;
};

type PartnerPayload = {
  member: {
    id: string;
    status: string;
    reward_mode: 'points' | 'cash';
    program_level: string;
    rate_percent: number;
    cash_eligible: boolean;
    cash_status: string;
    onec_counterparty_id?: string | null;
    onec_agency_contract_id?: string | null;
    onec_sync_status?: string | null;
    crypto_wallet?: {
      network?: string;
      address?: string;
      raw_address?: string;
      label?: string;
      status?: string;
      verification?: string;
      verified_at?: string;
      wallet_app?: string | null;
      glm_claim_enabled?: boolean;
      glm_claim_updated_at?: string;
      glm_claim_comment?: string;
    } | null;
  };
  profile: {
    id: string;
    full_name?: string | null;
    phone?: string | null;
    email?: string | null;
    loyalty_points?: number;
    customer_id_1c?: string | null;
    discount_card_number?: string | null;
    legal_status?: string | null;
    inn?: string | null;
    passport_data?: Record<string, any>;
    payout_details?: Record<string, any>;
    tax_responsibility_confirmed_at?: string | null;
  };
  referral_code?: { code: string; referral_url: string; status: string } | null;
  summary: Summary;
  token?: {
    token_code?: string;
    balance?: number;
    hold_balance?: number;
    claimable_balance?: number;
    pending_claim_amount?: number;
    pending_claim?: boolean;
  };
  cash_upgrade?: Record<string, any>;
  referrals?: Array<Record<string, any>>;
  commissions?: Array<Record<string, any>>;
  payouts?: Array<Record<string, any>>;
  cash_requests?: Array<Record<string, any>>;
};

type ListResponse = {
  partners: PartnerPayload[];
  total: number;
  limit: number;
  offset: number;
  overview: {
    partners_total: number;
    partners_active: number;
    cash_pending: number;
    payouts_pending_kopecks: number;
    ton_verified: number;
    glm_claim_enabled: number;
  };
};

type TelegramBroadcastResponse = {
  status: string;
  audience: string;
  recipients_count: number;
  sent?: number;
  failed?: number;
  sample?: Array<{ member_id: string; partner_name: string; status: string }>;
  errors?: Array<{ member_id: string; partner_name: string; error: string }>;
};

type GlmClaim = {
  id: string;
  bridge_operation_id?: string | null;
  member_id?: string | null;
  partner_name?: string | null;
  partner_phone?: string | null;
  amount: number;
  status: string;
  wallet_address?: string | null;
  wallet_app?: string | null;
  tx_hash?: string | null;
  admin_comment?: string | null;
  created_at?: string | null;
  processed_at?: string | null;
};

type GlmClaimsResponse = {
  claims: GlmClaim[];
  total: number;
  limit: number;
  offset: number;
};

type GlmTransaction = {
  id: string;
  bridge_operation_id?: string | null;
  member_id?: string | null;
  partner_name?: string | null;
  partner_phone?: string | null;
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
  debit_source?: string | null;
  expected_ton_sender_address?: string | null;
  treasury_address?: string | null;
  deposit_tx_hash?: string | null;
  ton_deposit_status?: string | null;
  ton_deposit_verification?: Record<string, any> | null;
  admin_comment?: string | null;
  bridge_type?: string | null;
  target_points?: number | null;
  processed_points?: number | null;
  onec_document_id?: string | null;
  onec_sync_status?: string | null;
  onec_sync_error?: string | null;
  onec_request_payload?: Record<string, any> | null;
  refunded_glm?: number | null;
  ton_refund_required?: boolean | null;
  loyalty_points_expires_at?: string | null;
  loyalty_points_expires_days?: number | null;
  sku?: string | null;
  item_title?: string | null;
  payment_method?: string | null;
  price_glm?: number | null;
  price_points?: number | null;
  refunded_points?: number | null;
  onec_spend_document_id?: string | null;
  onec_spend_sync_status?: string | null;
  onec_spend_sync_error?: string | null;
  fulfillment_status?: string | null;
  delivery_note?: string | null;
};

type GlmTransactionsResponse = {
  transactions: GlmTransaction[];
  total: number;
  limit: number;
  offset: number;
};

type GlmRedemptionsResponse = {
  redemptions: GlmTransaction[];
  total: number;
  limit: number;
  offset: number;
};

type GlmToPointsBridgeResponse = {
  bridges: GlmTransaction[];
  total: number;
  limit: number;
  offset: number;
};

type GlmBridgeOperation = {
  id: string;
  transaction_id: string;
  member_id?: string | null;
  partner_name?: string | null;
  partner_phone?: string | null;
  direction: string;
  status: string;
  idempotency_key?: string | null;
  points_amount: number;
  glm_amount: number;
  ton_network?: string | null;
  ton_sender_address?: string | null;
  ton_recipient_address?: string | null;
  ton_treasury_address?: string | null;
  ton_tx_hash?: string | null;
  ton_status?: string | null;
  onec_document_id?: string | null;
  onec_status?: string | null;
  onec_error?: string | null;
  source?: string | null;
  source_id?: string | null;
  requested_at?: string | null;
  processed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type GlmBridgeOperationsResponse = {
  count: number;
  limit: number;
  operations: GlmBridgeOperation[];
};

type GlmBridgeReconciliation = {
  generated_at: string;
  stale_hours: number;
  bridge_operations_source?: string;
  checked_bridge_operations?: number;
  bridge_operations_total?: number;
  bridge_operations_missing_domain_count?: number;
  bridge_operations_stale_pending_count?: number;
  bridge_operations_consistency_issue_count?: number;
  bridge_operations_by_direction?: Record<string, { count?: number; amount_glm?: number; statuses?: Record<string, number> }>;
  bridge_operations_by_status?: Record<string, { count?: number; amount_glm?: number }>;
  checked_bridge_transactions: number;
  checked_points_to_glm_transactions?: number;
  checked_total_transactions?: number;
  pending_count: number;
  pending_reserved_glm: number;
  processed_count: number;
  processed_points: number;
  points_to_glm_pending_count?: number;
  points_to_glm_processed_count?: number;
  points_to_glm_canceled_count?: number;
  ton_sent_waiting_count?: number;
  ton_processed_without_tx_count?: number;
  onec_ready_count: number;
  onec_failed_count: number;
  onec_spend_ready_count?: number;
  onec_spend_failed_count?: number;
  onec_cancel_spend_failed_count?: number;
  negative_accounts_count: number;
  issues_count: number;
  issues: Array<{
    severity: string;
    code: string;
    operation?: string;
    bridge_operation_id?: string;
    transaction_id?: string;
    account_id?: string;
    onec_document_id?: string | null;
    ton_tx_hash?: string | null;
    ton_status?: string | null;
    message: string;
  }>;
};

type GlmLoyaltyReconciliationItem = {
  member_id: string;
  user_id: string;
  partner_name?: string | null;
  partner_phone?: string | null;
  discount_card_id_1c?: string | null;
  discount_card_number?: string | null;
  customer_id_1c?: string | null;
  platform_points: number;
  onec_working_balance?: number | null;
  onec_lots_balance?: number | null;
  platform_vs_working_delta?: number | null;
  working_vs_lots_delta?: number | null;
  status: string;
  errors?: string[];
};

type GlmLoyaltyReconciliation = {
  generated_at: string;
  checked: number;
  count: number;
  issues_count: number;
  items: GlmLoyaltyReconciliationItem[];
};

type GlmHotWalletRefillCheck = {
  id: string;
  event_type: string;
  status: string;
  reason?: string | null;
  network?: string | null;
  treasury_address?: string | null;
  hot_wallet_address?: string | null;
  ton_tx_hash?: string | null;
  refill_glm_amount?: number | null;
  refill_ton_amount?: number | null;
  manual_glm_amount?: number | null;
  manual_ton_amount?: number | null;
  hot_wallet_glm_balance?: number | null;
  hot_wallet_ton_balance?: number | null;
  treasury_glm_balance?: number | null;
  treasury_ton_balance?: number | null;
  target_glm?: number | null;
  target_ton?: number | null;
  errors?: string[];
  comment?: string | null;
  created_by?: string | null;
  created_at?: string | null;
};

type TonConnectTransactionPayload = {
  status?: string;
  network?: string;
  source_address?: string;
  destination_address?: string;
  refill_glm_amount?: number;
  refill_ton_amount?: number;
  transaction: {
    validUntil: number;
    network?: string;
    from?: string;
    messages: Array<{
      address: string;
      amount: string;
      payload?: string;
    }>;
  };
};

type GlmAuditHash = {
  id: string;
  audit_date: string;
  token_code: string;
  root_hash: string;
  previous_root_hash?: string | null;
  transactions_count: number;
  accounts_count: number;
  balance_total: number;
  hold_total: number;
  lifetime_earned_total: number;
  lifetime_burned_total: number;
  public_status: string;
  public_reference?: string | null;
  generated_at?: string | null;
  payload?: {
    transaction_hashes?: Array<{ id: string; hash: string }>;
    account_hash?: string;
    totals?: Record<string, number>;
  };
};

type GlmAuditHashesResponse = {
  hashes: GlmAuditHash[];
};

type GlmTonReadiness = {
  status: string;
  generated_at: string;
  policy: {
    network?: string;
    status?: string;
    claim_mode?: string;
    jetton_master_address?: string | null;
    treasury_address?: string | null;
    metadata_url?: string | null;
    mainnet_enabled?: boolean;
  };
  env_status: Record<string, string | boolean | null>;
  artifact: {
    exists?: boolean;
    path?: string;
    error?: string | null;
    deployment_status?: string | null;
    jetton_master_address?: string | null;
    treasury_address?: string | null;
    deploy_tx_hash?: string | null;
    deployed_at?: string | null;
  };
  reference?: {
    exists?: boolean;
    path?: string;
    error?: string | null;
    name?: string | null;
    repo?: string | null;
    branch?: string | null;
    expected_commit?: string | null;
    actual_commit?: string | null;
    vendor_exists?: boolean;
    matches_lock?: boolean;
  };
  pending_claims: {
    count: number;
    amount_glm: number;
    auto_transfer_status_counts?: Record<string, number>;
    auto_transfer_amounts_by_status?: Record<string, number>;
    auto_transfer_health?: {
      blocked_count?: number;
      blocked_amount_glm?: number;
      waiting_settlement_count?: number;
      waiting_settlement_amount_glm?: number;
      not_started_count?: number;
      not_started_amount_glm?: number;
      oldest_pending_age_minutes?: number;
      oldest_pending_created_at?: string | null;
      needs_attention?: boolean;
    };
    sample_limit?: number;
    sample?: Array<{
      id: string;
      amount_glm: number;
      created_at?: string | null;
      onec_spend_sync_status?: string | null;
      auto_transfer_status?: string | null;
      auto_transfer_error?: string | null;
      tx_hash?: string | null;
    }>;
    operator_csv_url: string;
  };
  pending_glm_to_points?: {
    count: number;
    amount_glm: number;
    deposit_status_counts?: Record<string, number>;
    deposit_amounts_by_status?: Record<string, number>;
    health?: {
      waiting_deposit_count?: number;
      waiting_deposit_amount_glm?: number;
      tx_found_count?: number;
      tx_found_amount_glm?: number;
      onec_issue_count?: number;
      onec_issue_amount_glm?: number;
      oldest_pending_age_minutes?: number;
      oldest_pending_created_at?: string | null;
      needs_attention?: boolean;
    };
    sample_limit?: number;
    sample?: Array<{
      id: string;
      amount_glm: number;
      target_points?: number | null;
      created_at?: string | null;
      ton_deposit_status?: string | null;
      deposit_tx_hash?: string | null;
      expected_ton_sender_address?: string | null;
      treasury_address?: string | null;
      last_lookup_status?: string | null;
      onec_sync_status?: string | null;
    }>;
  };
  bridge_operations?: {
    count?: number;
    amount_glm?: number;
    missing_domain_count?: number;
    health?: {
      needs_attention?: boolean;
      stale_pending_count?: number;
      stale_pending_amount_glm?: number;
      ton_waiting_count?: number;
      ton_waiting_amount_glm?: number;
      onec_issue_count?: number;
      onec_issue_amount_glm?: number;
      domain_gap_count?: number;
      oldest_pending_age_minutes?: number;
      oldest_pending_created_at?: string | null;
      sample?: Array<Record<string, any>>;
    };
    by_direction?: Record<string, { count?: number; amount_glm?: number; statuses?: Record<string, { count?: number; amount_glm?: number }> }>;
    by_status?: Record<string, { count?: number; amount_glm?: number }>;
    list_endpoint?: string;
  };
  settlement?: Record<string, any>;
  auto_transfer?: Record<string, any>;
  treasury_balances?: {
    status?: string;
    generated_at?: string;
    config?: {
      network?: string;
      hot_wallet_refill_glm_threshold?: number;
      hot_wallet_refill_ton_threshold?: number;
      hot_wallet_refill_glm_target?: number;
      hot_wallet_refill_ton_target?: number;
      limits_override?: Record<string, any>;
    };
    requirements?: {
      pending_points_to_glm_count?: number;
      pending_points_to_glm_amount_glm?: number;
      required_glm?: number;
      required_ton?: number;
      glm_buffer?: number;
      ton_buffer?: number;
    };
    wallets?: Array<{
      role?: string;
      address?: string | null;
      network?: string;
      glm_balance?: number;
      ton_balance?: number;
      required_glm?: number;
      required_ton?: number;
      safe_transfer_capacity_glm?: number;
      safe_transfer_capacity_ton?: number;
      refill_threshold_glm?: number | null;
      refill_threshold_ton?: number | null;
      refill_target_glm?: number | null;
      refill_target_ton?: number | null;
      jetton_wallet_address?: string | null;
      status?: string;
      errors?: string[];
    }>;
    refill_plan?: {
      status?: string;
      required?: boolean;
      reason?: string;
      network?: string;
      source_address?: string | null;
      destination_address?: string | null;
      refill_glm_amount?: number;
      refill_ton_amount?: number;
      hot_wallet_glm_balance?: number;
      hot_wallet_ton_balance?: number;
      treasury_glm_balance?: number;
      treasury_ton_balance?: number;
      target_glm?: number;
      target_ton?: number;
      threshold_glm?: number;
      threshold_ton?: number;
      errors?: string[];
      instructions?: string[];
    };
    alerts?: Array<{ code: string; severity?: string; message: string }>;
    telegram_alert_state?: {
      state_file_exists?: boolean;
      alerts?: Record<string, {
        fingerprint?: string | null;
        last_sent_at?: string | null;
        message?: string | null;
      }>;
    };
  };
  security?: {
    pilot_only?: boolean;
    mainnet_ready?: boolean;
    production_hot_wallet_address?: string | null;
    production_hot_wallet_bounceable?: string | null;
    production_hot_wallet_raw?: string | null;
    production_candidate_ready?: boolean;
    production_ready?: boolean;
    production_signer_mode?: string | null;
    production_signer_endpoint_configured?: boolean;
    production_legal_approved?: boolean;
    production_security_approved?: boolean;
    production_treasury_approved?: boolean;
    production_approvals_ready?: boolean;
    warnings?: Array<{ code: string; severity?: string; message: string }>;
    mainnet_blockers?: Array<{ code: string; message: string }>;
  };
  alerts?: Array<{ code: string; severity?: string; message: string }>;
  schedulers?: Record<string, {
    enabled?: boolean;
    status?: string;
    interval_minutes?: number;
    batch_limit?: number;
  }>;
  commands?: Record<string, string>;
  next_steps?: string[];
  checks: Array<{ code: string; ok: boolean; message: string }>;
  blockers: Array<{ code: string; ok: boolean; message: string }>;
};

type GlmDashboard = {
  accounts_total: number;
  balance_total: number;
  hold_total: number;
  lifetime_earned_total: number;
  lifetime_burned_total: number;
  earn_total: number;
  release_total: number;
  claim_total: number;
  pending_claim_total: number;
  processed_claim_total: number;
  due_hold_total: number;
  pending_claim_count: number;
  due_hold_count: number;
  monthly_earn_total: number;
  monthly_referral_emission_limit: number;
  monthly_referral_emission_remaining: number;
  monthly_referral_emission_percent: number;
  referral_campaign?: {
    active: boolean;
    code: string;
    name: string;
    multiplier: number;
    until?: string | null;
    description: string;
  };
  conversion_total: number;
  redemption_total: number;
  burned_total: number;
  emission_total: number;
  real_turnover_backed_total: number;
  real_turnover_backed_percent: number;
  top_partners: Array<{
    member_id: string;
    partner_name?: string | null;
    partner_phone?: string | null;
    balance: number;
    hold_balance: number;
    lifetime_earned: number;
  }>;
};

type GlmEffectiveness = {
  generated_at: string;
  period: { current_month_start: string };
  accounts_total: number;
  active_balance_accounts: number;
  redeemers_count: number;
  redemption_conversion_percent: number;
  redemption_count: number;
  redemption_total: number;
  burn_ratio_percent: number;
  lifetime_earned_total: number;
  lifetime_burned_total: number;
  conversion_accounts: number;
  conversion_total: number;
  conversion_to_redemption_percent: number;
  ready_to_redeem_count: number;
  high_balance_count: number;
  high_balance_no_redemption_count: number;
  monthly_earn_total: number;
  monthly_conversion_total: number;
  monthly_redemption_total: number;
  redemption_by_category: Array<{ category: string; count: number; amount: number }>;
  top_redemption_items: Array<{ sku: string; title: string; count: number; amount: number }>;
};

type GlmSegmentItem = {
  member_id: string;
  partner_name?: string | null;
  partner_phone?: string | null;
  balance: number;
  hold_balance: number;
  privilege_score: number;
  tier?: string | null;
  next_tier?: string | null;
  to_next: number;
  redemption_total: number;
  redemption_count: number;
  converted_total: number;
};

type GlmSegment = {
  code: string;
  title: string;
  description: string;
  count: number;
  items: GlmSegmentItem[];
};

type GlmSegmentsResponse = {
  segments: GlmSegment[];
};

type GlmRefundCandidate = {
  commission_id: string;
  member_id: string;
  partner_name?: string | null;
  partner_phone?: string | null;
  commission_status: string;
  commission_base: number;
  commission_amount_kopecks: number;
  points: number;
  reward_mode: string;
  order_id?: string | null;
  order_status?: string | null;
  purchase_id?: string | null;
  purchase_total_amount?: number | null;
  purchase_quantity?: number | null;
  glm_amount: number;
  glm_status?: string | null;
  signals: string[];
  severity: string;
  auto_apply_eligible?: boolean;
  created_at?: string | null;
};

type GlmRefundCandidatesResponse = {
  count: number;
  candidates: GlmRefundCandidate[];
  policy: string;
};

type BonusExpiryAudienceItem = {
  user_id: string;
  full_name?: string | null;
  phone?: string | null;
  email?: string | null;
  loyalty_points: number;
  expiring_points: number;
  nearest_expiry?: string | null;
  lots_count: number;
  campaign_message: string;
};

type BonusExpiryAudienceResponse = {
  days: number;
  items: BonusExpiryAudienceItem[];
};

type MediaMaterial = {
  id: string;
  title: string;
  category: string;
  description?: string | null;
  file_url: string;
  preview_url?: string | null;
  original_file_name: string;
  content_type?: string | null;
  size: number;
  is_active: boolean;
  sort_order: number;
};

type RatePromotion = {
  id: string;
  title: string;
  rate_percent: number;
  starts_at: string;
  ends_at: string;
  is_active: boolean;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
};

type RewardStoreItem = {
  id: string;
  sku: string;
  title: string;
  description?: string | null;
  category: string;
  inventory_status: string;
  status: string;
  price_glm?: number | null;
  price_points?: number | null;
  quantity_available?: number | null;
  image_url?: string | null;
  sort_order: number;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

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
  average_check: 0,
};

const statusLabels: Record<string, string> = {
  active: 'Активен',
  blocked: 'Заблокирован',
  paused: 'Пауза',
  pending: 'На проверке',
  approved: 'Одобрено',
  rejected: 'Отклонено',
  paid: 'Оплачено',
  canceled: 'Отменено',
  hold: 'Холд',
  earn: 'Начисление',
  release: 'Доступно',
  expire: 'Списание',
  conversion: 'Баллы→GLM',
  bridge: 'Обмен',
  claim: 'Баллы→GLM',
  adjustment: 'Корректировка',
  redemption: 'Покупка',
  reversal: 'Возврат GLM',
  partial: 'Частично',
  pending_fulfillment: 'На сборке',
  fulfilled: 'Выдано',
  available: 'Доступно',
  accrued_in_1c: 'Начислено в 1С',
  unavailable: 'Недоступно',
  eligible: 'Доступно',
  success: 'Успешно',
  failed: 'Ошибка',
  processed: 'Обработано',
  verified: 'Проверено',
  linked: 'Привязан',
  missing: 'Нет кошелька',
  claim_enabled: 'GLM разрешен',
  glm_to_points_bridge: 'GLM→баллы',
  points_to_glm: 'Баллы→GLM',
  points_to_ton: 'Баллы→GLM',
  buy_loyalty_points: 'Покупка баллов',
  ready_for_1c: 'Готово для 1С',
  ready_for_1c_spend: 'Готово к списанию 1С',
  missing_discount_card: 'Нет карты 1С',
  manual_document_recorded: 'Документ внесен',
  manual_spend_document_recorded: 'Списание внесено',
  posted_without_balance_change: 'Проведен без изменения баланса',
  created_without_ref_key: 'Создан без Ref',
  internal: 'Внутренний',
  published: 'Опубликован',
  ready_for_operator_mint: 'Готов',
  ready_for_treasury_transfer: 'Готов к переводу',
  draft_not_deployed: 'Draft',
  testnet_deployed: 'Testnet deployed',
  scheduled: 'Запланирована',
  finished: 'Завершена',
  invalid: 'Ошибка',
  not_started: 'Ждет отправки',
  sent: 'Отправлено',
  sent_waiting_settlement: 'Ждет подтверждения TON',
  blocked_hot_wallet_balance: 'Нужно пополнить hot-wallet',
  blocked_missing_wallet: 'Нет TON-кошелька',
  blocked_policy: 'Требуется проверка',
  waiting_for_deposit: 'Ждет TON-перевод',
  wallet_request_prepared: 'Кошелек открыт',
  tx_hash_present: 'TON tx найден',
  not_found: 'TON не найден',
  retry_onec: 'Повторить 1С',
  record_manual_document: 'Внести документ 1С',
  record_manual_spend_document: 'Внести списание 1С',
  settle_ton_transfer: 'Проверить TON',
  cancel_onec_spend: 'Отменить списание 1С',
  mark_legacy_manual: 'Закрыть как проверенное',
  mark_reviewed: 'Отметить проверенным',
  ton_sent_waiting_settlement: 'GLM отправлены, ждем TON',
  closed_points_to_glm_without_1c_spend_unpost: 'Закрыто, нужно отменить списание 1С',
  processed_points_to_glm_without_1c_spend: 'Нет документа списания 1С',
  ready: 'Готово',
  ok: 'OK',
  warning: 'Внимание',
  critical: 'Критично',
  error: 'Ошибка',
  not_configured: 'Не настроено',
  below_refill_threshold: 'Ниже лимита',
  hot_wallet_above_threshold: 'Пополнение не требуется',
  treasury_glm_insufficient: 'В treasury недостаточно GLM',
  treasury_ton_insufficient: 'В treasury недостаточно TON',
  balance_check: 'Проверка баланса',
  manual_refill: 'Ручное пополнение',
};

const mediaCategoryLabels: Record<string, string> = {
  logos: 'Логотипы',
  patterns: 'Паттерны',
  phrases: 'Фирменные фразы',
  signs: 'Знак GLAME',
  other: 'Другое',
};

function fileSizeRu(value: number) {
  if (!value) return '—';
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} КБ`;
  return `${(value / 1024 / 1024).toFixed(1).replace('.', ',')} МБ`;
}

function money(value?: number | null) {
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format((value || 0) / 100);
}

function dateRu(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('ru-RU');
}

function dateTimeRu(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function toDateTimeLocal(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function label(value?: string | null) {
  return statusLabels[value || ''] || value || '—';
}

function sumStatusCounts(counts: Record<string, number> | undefined, predicate: (status: string) => boolean) {
  return Object.entries(counts || {}).reduce((total, [status, count]) => total + (predicate(status) ? Number(count || 0) : 0), 0);
}

function pointsToGlmStage(item: GlmClaim | GlmBridgeOperation | Record<string, any>) {
  const record = item as Record<string, any>;
  const status = String(record.status || '');
  const tonStatus = String(record.ton_status || record.auto_transfer_status || '');
  const onecStatus = String(record.onec_status || record.onec_spend_sync_status || '');
  if (status === 'processed') return { label: 'GLM отправлены', detail: 'TON-перевод подтвержден', value: 'processed' };
  if (status === 'failed') return { label: 'Требуется проверка', detail: 'Операция завершилась ошибкой', value: 'failed' };
  if (status === 'canceled') return { label: 'Отменено', detail: 'Операция закрыта без отправки GLM', value: 'canceled' };
  if (tonStatus === 'sent_waiting_settlement' || tonStatus === 'sent') return { label: 'GLM отправлены, ждем TON', detail: 'Нужно подтверждение транзакции в сети', value: tonStatus };
  if (tonStatus === 'blocked_hot_wallet_balance') return { label: 'Нужно пополнить hot-wallet', detail: 'GLM в hot-wallet ниже лимита', value: tonStatus };
  if (tonStatus.startsWith('blocked_')) return { label: label(tonStatus), detail: 'Auto-transfer остановлен проверкой', value: tonStatus };
  if (onecStatus && !['success', 'manual_spend_document_recorded'].includes(onecStatus)) return { label: 'Ждет 1С', detail: label(onecStatus), value: onecStatus };
  return { label: 'Ждет отправки GLM', detail: 'Баллы списаны, ожидается перевод в TON', value: 'pending' };
}

function glmToPointsStage(item: GlmTransaction | GlmBridgeOperation | Record<string, any>) {
  const record = item as Record<string, any>;
  const status = String(record.status || '');
  const tonStatus = String(record.ton_deposit_status || record.ton_status || '');
  const onecStatus = String(record.onec_sync_status || record.onec_status || '');
  const hasTx = Boolean(record.deposit_tx_hash || record.ton_tx_hash || record.ton_deposit_verification?.verified);
  if (status === 'processed') return { label: 'Баллы начислены', detail: 'TON-перевод и 1С закрыты', value: 'processed' };
  if (status === 'failed') return { label: 'Требуется проверка', detail: record.onec_sync_error || 'Операция завершилась ошибкой', value: 'failed' };
  if (status === 'canceled') return { label: 'Отменено', detail: 'TON-перевод не был принят в обработку', value: 'canceled' };
  if (onecStatus && ['failed', 'ready_for_1c', 'created_without_ref_key', 'posted_without_balance_change'].includes(onecStatus)) return { label: 'Требуется 1С', detail: label(onecStatus), value: onecStatus };
  if (hasTx || tonStatus === 'tx_hash_present') return { label: 'TON найден', detail: 'Ожидает начисления баллов в 1С', value: 'tx_hash_present' };
  if (tonStatus === 'wallet_request_prepared') return { label: 'Кошелек открыт', detail: 'Партнер должен подтвердить перевод', value: tonStatus };
  return { label: 'Ждет TON-перевод', detail: 'GLM еще не поступили в GLAME', value: tonStatus || 'waiting_for_deposit' };
}

function bridgeDirectionLabel(value?: string | null) {
  if (value === 'points_to_glm' || value === 'points_to_ton') return 'Баллы→GLM';
  if (value === 'glm_to_points') return 'GLM→баллы';
  return label(value);
}

function Badge({ value }: { value?: string | null }) {
  const tone = value === 'active' || value === 'approved' || value === 'paid' || value === 'success' || value === 'processed' || value === 'fulfilled' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : value === 'blocked' || value === 'rejected' || value === 'failed' || value === 'canceled' ? 'border-red-200 bg-red-50 text-red-700' : 'border-slate-200 bg-slate-50 text-slate-700';
  return <span className={`inline-flex rounded border px-2 py-1 text-xs font-medium ${tone}`}>{label(value)}</span>;
}

function Metric({ title, value, hint }: { title: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</div>
      <div className="mt-2 text-2xl font-semibold text-slate-900">{value}</div>
      {hint ? <div className="mt-1 text-xs text-slate-500">{hint}</div> : null}
    </div>
  );
}

function DataTable({ headers, rows }: { headers: string[]; rows: Array<Array<string | number | JSX.Element>> }) {
  return (
    <div className="w-full max-w-full overflow-x-auto rounded-md border border-slate-200 bg-white">
      <table className="w-full min-w-[720px] border-collapse text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>{headers.map((header) => <th key={header} className="border-b border-slate-200 px-3 py-3 text-left font-semibold">{header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length ? rows.map((row, index) => (
            <tr key={index} className="border-b border-slate-100 last:border-b-0">
              {row.map((cell, cellIndex) => <td key={cellIndex} className="px-3 py-3 align-top text-slate-700">{cell}</td>)}
            </tr>
          )) : (
            <tr><td colSpan={headers.length} className="px-3 py-8 text-center text-slate-500">Данных пока нет</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function JsonBlock({ value }: { value?: Record<string, any> }) {
  const entries = Object.entries(value || {}).filter(([, item]) => item !== null && item !== undefined && item !== '');
  if (!entries.length) return <div className="text-sm text-slate-500">Нет данных</div>;
  return (
    <div className="space-y-2">
      {entries.map(([key, item]) => (
        <div key={key} className="rounded border border-slate-200 bg-slate-50 p-3">
          <div className="text-xs uppercase tracking-wide text-slate-500">{key}</div>
          <div className="mt-1 break-words text-sm text-slate-900">{typeof item === 'object' ? JSON.stringify(item) : String(item)}</div>
        </div>
      ))}
    </div>
  );
}

export default function AdminReferralsPage() {
  const [tonConnectUI] = useTonConnectUI();
  const { open: openTonConnectModal } = useTonConnectModal();
  const tonWallet = useTonWallet();
  const [partners, setPartners] = useState<PartnerPayload[]>([]);
  const [selected, setSelected] = useState<PartnerPayload | null>(null);
  const [overview, setOverview] = useState<ListResponse['overview'] | null>(null);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [rewardMode, setRewardMode] = useState('');
  const [tonStatus, setTonStatus] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contractId, setContractId] = useState('');
  const [payoutAmount, setPayoutAmount] = useState('');
  const [payoutDocument, setPayoutDocument] = useState('');
  const [payoutComment, setPayoutComment] = useState('');
  const [glmClaims, setGlmClaims] = useState<GlmClaim[]>([]);
  const [glmClaimStatus, setGlmClaimStatus] = useState('pending');
  const [glmClaimTxHash, setGlmClaimTxHash] = useState('');
  const [glmClaimComment, setGlmClaimComment] = useState('');
  const [glmRedemptions, setGlmRedemptions] = useState<GlmTransaction[]>([]);
  const [glmRedemptionStatus, setGlmRedemptionStatus] = useState('pending_fulfillment');
  const [glmFulfillmentComment, setGlmFulfillmentComment] = useState('');
  const [glmToPointsBridges, setGlmToPointsBridges] = useState<GlmTransaction[]>([]);
  const [glmToPointsStatus, setGlmToPointsStatus] = useState('pending');
  const [glmToPointsValue, setGlmToPointsValue] = useState('');
  const [glmToPointsDocument, setGlmToPointsDocument] = useState('');
  const [glmToPointsComment, setGlmToPointsComment] = useState('');
  const [glmToPointsDepositHashes, setGlmToPointsDepositHashes] = useState<Record<string, string>>({});
  const [glmBridgeOperations, setGlmBridgeOperations] = useState<GlmBridgeOperation[]>([]);
  const [glmBridgeReconciliation, setGlmBridgeReconciliation] = useState<GlmBridgeReconciliation | null>(null);
  const [glmLoyaltyReconciliation, setGlmLoyaltyReconciliation] = useState<GlmLoyaltyReconciliation | null>(null);
  const [glmTonReadiness, setGlmTonReadiness] = useState<GlmTonReadiness | null>(null);
  const [hotWalletLimitResult, setHotWalletLimitResult] = useState<string | null>(null);
  const [hotWalletRefillResult, setHotWalletRefillResult] = useState<string | null>(null);
  const [hotWalletRefillTonResult, setHotWalletRefillTonResult] = useState<string | null>(null);
  const [hotWalletRefillChecks, setHotWalletRefillChecks] = useState<GlmHotWalletRefillCheck[]>([]);
  const [hotWalletRefillForm, setHotWalletRefillForm] = useState({
    manual_glm_amount: '',
    manual_ton_amount: '',
    ton_tx_hash: '',
    comment: '',
  });
  const [hotWalletLimitForm, setHotWalletLimitForm] = useState({
    hot_wallet_refill_glm_threshold: '5000',
    hot_wallet_refill_ton_threshold: '0.5',
    hot_wallet_refill_glm_target: '5000',
    hot_wallet_refill_ton_target: '2',
  });
  const [glmAuditHashes, setGlmAuditHashes] = useState<GlmAuditHash[]>([]);
  const [glmAuditDate, setGlmAuditDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [glmAuditResult, setGlmAuditResult] = useState<string | null>(null);
  const [glmTransactions, setGlmTransactions] = useState<GlmTransaction[]>([]);
  const [glmDashboard, setGlmDashboard] = useState<GlmDashboard | null>(null);
  const [glmEffectiveness, setGlmEffectiveness] = useState<GlmEffectiveness | null>(null);
  const [glmSegments, setGlmSegments] = useState<GlmSegment[]>([]);
  const [glmRefundCandidates, setGlmRefundCandidates] = useState<GlmRefundCandidate[]>([]);
  const [glmRefundAutoApplyResult, setGlmRefundAutoApplyResult] = useState<string | null>(null);
  const [glmTxType, setGlmTxType] = useState('');
  const [glmTxStatus, setGlmTxStatus] = useState('');
  const [glmReleaseResult, setGlmReleaseResult] = useState<string | null>(null);
  const [bonusExpiryDays, setBonusExpiryDays] = useState('30');
  const [bonusExpiryAudience, setBonusExpiryAudience] = useState<BonusExpiryAudienceItem[]>([]);
  const [bonusExpiryDraftResult, setBonusExpiryDraftResult] = useState<string | null>(null);
  const [telegramBroadcastTitle, setTelegramBroadcastTitle] = useState('');
  const [telegramBroadcastMessage, setTelegramBroadcastMessage] = useState('');
  const [telegramBroadcastAudience, setTelegramBroadcastAudience] = useState<'active_connected' | 'all_connected'>('active_connected');
  const [telegramBroadcastResult, setTelegramBroadcastResult] = useState<TelegramBroadcastResponse | null>(null);
  const [glmAdjustDirection, setGlmAdjustDirection] = useState<'credit' | 'debit'>('credit');
  const [glmAdjustAmount, setGlmAdjustAmount] = useState('');
  const [glmAdjustReason, setGlmAdjustReason] = useState('');
  const [glmAdjustComment, setGlmAdjustComment] = useState('');
  const [commissionCancelComment, setCommissionCancelComment] = useState('');
  const [posPhone, setPosPhone] = useState('');
  const [posCode, setPosCode] = useState('');
  const [posName, setPosName] = useState('');
  const [posResult, setPosResult] = useState<string | null>(null);
  const [glmPosCode, setGlmPosCode] = useState('');
  const [glmPosResult, setGlmPosResult] = useState<string | null>(null);
  const [mediaMaterials, setMediaMaterials] = useState<MediaMaterial[]>([]);
  const [mediaTitle, setMediaTitle] = useState('');
  const [mediaCategory, setMediaCategory] = useState('logos');
  const [mediaDescription, setMediaDescription] = useState('');
  const [mediaSortOrder, setMediaSortOrder] = useState('100');
  const [mediaFile, setMediaFile] = useState<File | null>(null);
  const [mediaResult, setMediaResult] = useState<string | null>(null);
  const [ratePromotions, setRatePromotions] = useState<RatePromotion[]>([]);
  const [promoTitle, setPromoTitle] = useState('Акция по баллам');
  const [promoRate, setPromoRate] = useState('10');
  const [promoStartsAt, setPromoStartsAt] = useState(() => toDateTimeLocal(new Date().toISOString()));
  const [promoEndsAt, setPromoEndsAt] = useState('');
  const [promoResult, setPromoResult] = useState<string | null>(null);
  const [rewardStoreItems, setRewardStoreItems] = useState<RewardStoreItem[]>([]);
  const [rewardStoreEditingId, setRewardStoreEditingId] = useState<string | null>(null);
  const [rewardStoreResult, setRewardStoreResult] = useState<string | null>(null);
  const [rewardStoreImageFile, setRewardStoreImageFile] = useState<File | null>(null);
  const [rewardStoreForm, setRewardStoreForm] = useState({
    sku: '',
    title: '',
    description: '',
    category: 'branded_goods',
    inventory_status: 'pilot_batch',
    status: 'available',
    price_glm: '',
    price_points: '',
    quantity_available: '',
    image_url: '',
    sort_order: '100',
    is_active: true,
  });

  const selectedSummary = selected?.summary || emptySummary;
  const selectedId = selected?.member.id || null;
  const selectedWallet = selected?.member.crypto_wallet || null;
  const glmHotWalletBalance = glmTonReadiness?.treasury_balances?.wallets?.find((wallet) => wallet.role === 'hot_wallet');
  const glmTreasuryBalance = glmTonReadiness?.treasury_balances?.wallets?.find((wallet) => wallet.role === 'treasury');
  const hotWalletRefillPlan = glmTonReadiness?.treasury_balances?.refill_plan;
  const hotWalletAlertState = glmTonReadiness?.treasury_balances?.telegram_alert_state?.alerts || {};
  const hotWalletLatestAlert = Object.entries(hotWalletAlertState)
    .filter(([code]) => code.startsWith('hot_wallet_'))
    .sort(([, left], [, right]) => String(right.last_sent_at || '').localeCompare(String(left.last_sent_at || '')))[0]?.[1];

  async function loadPartners(keepSelected = true) {
    setError(null);
    try {
      const response = await apiClient.get<ListResponse>('/api/referrals/admin/partners', {
        params: {
          search: search.trim() || undefined,
          status: status || undefined,
          reward_mode: rewardMode || undefined,
          ton_status: tonStatus || undefined,
          limit: 100,
        },
      });
      setPartners(response.data.partners || []);
      setOverview(response.data.overview);
      const nextSelected = keepSelected && selectedId
        ? response.data.partners.find((partner) => partner.member.id === selectedId)
        : response.data.partners[0];
      if (nextSelected) await loadPartner(nextSelected.member.id);
      else setSelected(null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось загрузить партнеров');
    } finally {
      setLoading(false);
    }
  }

  async function loadPartner(memberId: string) {
    const response = await apiClient.get<PartnerPayload>(`/api/referrals/admin/partners/${memberId}`);
    setSelected(response.data);
    setContractId(response.data.member.onec_agency_contract_id || '');
  }

  async function loadMediaMaterials() {
    const response = await apiClient.get<MediaMaterial[]>('/api/referrals/admin/media-materials');
    setMediaMaterials(response.data || []);
  }

  async function loadRatePromotions() {
    const response = await apiClient.get<RatePromotion[]>('/api/referrals/admin/rate-promotions');
    setRatePromotions(response.data || []);
  }

  async function loadRewardStoreItems() {
    const response = await apiClient.get<RewardStoreItem[]>('/api/referrals/admin/reward-store-items', {
      params: { include_archived: true },
    });
    setRewardStoreItems(response.data || []);
  }

  function resetRewardStoreForm() {
    setRewardStoreEditingId(null);
    setRewardStoreImageFile(null);
    setRewardStoreForm({
      sku: '',
      title: '',
      description: '',
      category: 'branded_goods',
      inventory_status: 'pilot_batch',
      status: 'available',
      price_glm: '',
      price_points: '',
      quantity_available: '',
      image_url: '',
      sort_order: '100',
      is_active: true,
    });
  }

  function editRewardStoreItem(item: RewardStoreItem) {
    setRewardStoreEditingId(item.id);
    setRewardStoreResult(null);
    setRewardStoreForm({
      sku: item.sku || '',
      title: item.title || '',
      description: item.description || '',
      category: item.category || 'branded_goods',
      inventory_status: item.inventory_status || 'pilot_batch',
      status: item.status || 'available',
      price_glm: item.price_glm === null || item.price_glm === undefined ? '' : String(item.price_glm),
      price_points: item.price_points === null || item.price_points === undefined ? '' : String(item.price_points),
      quantity_available: item.quantity_available === null || item.quantity_available === undefined ? '' : String(item.quantity_available),
      image_url: item.image_url || '',
      sort_order: String(item.sort_order ?? 100),
      is_active: Boolean(item.is_active),
    });
  }

  async function saveRewardStoreItem() {
    setSaving(true);
    setError(null);
    setRewardStoreResult(null);
    try {
      const payload = {
        ...rewardStoreForm,
        price_glm: rewardStoreForm.price_glm.trim() ? Number.parseInt(rewardStoreForm.price_glm, 10) : null,
        price_points: rewardStoreForm.price_points.trim() ? Number.parseInt(rewardStoreForm.price_points, 10) : null,
        quantity_available: rewardStoreForm.quantity_available.trim() ? Number.parseInt(rewardStoreForm.quantity_available, 10) : null,
        image_url: rewardStoreForm.image_url.trim() || null,
        sort_order: Number.parseInt(rewardStoreForm.sort_order, 10) || 100,
      };
      if (rewardStoreEditingId) {
        await apiClient.patch(`/api/referrals/admin/reward-store-items/${rewardStoreEditingId}`, payload);
        setRewardStoreResult('Товар обновлен');
      } else {
        await apiClient.post('/api/referrals/admin/reward-store-items', payload);
        setRewardStoreResult('Товар добавлен');
      }
      resetRewardStoreForm();
      await loadRewardStoreItems();
      await loadGlmDashboard();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось сохранить товар');
    } finally {
      setSaving(false);
    }
  }

  async function uploadRewardStoreImage() {
    if (!rewardStoreImageFile) {
      setError('Выберите фото товара');
      return;
    }
    setSaving(true);
    setError(null);
    setRewardStoreResult(null);
    try {
      const form = new FormData();
      form.append('file', rewardStoreImageFile);
      const response = await apiClient.post('/api/referrals/admin/reward-store-items/image', form);
      setRewardStoreForm((prev) => ({ ...prev, image_url: response.data?.image_url || '' }));
      setRewardStoreImageFile(null);
      const fileInput = document.getElementById('reward-store-image-file') as HTMLInputElement | null;
      if (fileInput) fileInput.value = '';
      setRewardStoreResult('Фото загружено. Сохраните товар, чтобы применить его в витрине.');
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось загрузить фото товара');
    } finally {
      setSaving(false);
    }
  }

  async function setRewardStoreItemArchived(item: RewardStoreItem, archived: boolean) {
    setSaving(true);
    setError(null);
    setRewardStoreResult(null);
    try {
      await apiClient.post(`/api/referrals/admin/reward-store-items/${item.id}/${archived ? 'archive' : 'restore'}`);
      setRewardStoreResult(archived ? 'Товар архивирован' : 'Товар восстановлен');
      await loadRewardStoreItems();
      await loadGlmDashboard();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось изменить статус товара');
    } finally {
      setSaving(false);
    }
  }

  async function loadGlmClaims() {
    const response = await apiClient.get<GlmClaimsResponse>('/api/referrals/admin/glm-claims', {
      params: { status: glmClaimStatus || undefined, limit: 100 },
    });
    setGlmClaims(response.data.claims || []);
  }

  async function loadGlmRedemptions() {
    const response = await apiClient.get<GlmRedemptionsResponse>('/api/referrals/admin/glm-redemptions', {
      params: { status: glmRedemptionStatus || undefined, limit: 100 },
    });
    setGlmRedemptions(response.data.redemptions || []);
  }

  async function loadGlmToPointsBridges() {
    const response = await apiClient.get<GlmToPointsBridgeResponse>('/api/referrals/admin/glm-bridge/glm-to-points', {
      params: { status: glmToPointsStatus || undefined, limit: 100 },
    });
    setGlmToPointsBridges(response.data.bridges || []);
  }

  async function loadGlmBridgeReconciliation() {
    const response = await apiClient.get<GlmBridgeReconciliation>('/api/referrals/admin/glm-bridge/reconciliation', {
      params: { stale_hours: 48, limit: 500 },
    });
    setGlmBridgeReconciliation(response.data);
  }

  async function loadGlmLoyaltyReconciliation() {
    const response = await apiClient.get<GlmLoyaltyReconciliation>('/api/referrals/admin/glm-loyalty-reconciliation', {
      params: { limit: 50 },
    });
    setGlmLoyaltyReconciliation(response.data);
  }

  async function loadGlmBridgeOperations() {
    const response = await apiClient.get<GlmBridgeOperationsResponse>('/api/referrals/admin/glm-bridge/operations', {
      params: { limit: 50 },
    });
    setGlmBridgeOperations(response.data.operations || []);
  }

  async function loadGlmTonReadiness() {
    const response = await apiClient.get<GlmTonReadiness>('/api/referrals/admin/glm-ton-readiness');
    setGlmTonReadiness(response.data);
    const limits = response.data.treasury_balances?.config;
    if (limits) {
      setHotWalletLimitForm({
        hot_wallet_refill_glm_threshold: String(limits.hot_wallet_refill_glm_threshold ?? 5000),
        hot_wallet_refill_ton_threshold: String(limits.hot_wallet_refill_ton_threshold ?? 0.5),
        hot_wallet_refill_glm_target: String(limits.hot_wallet_refill_glm_target ?? 5000),
        hot_wallet_refill_ton_target: String(limits.hot_wallet_refill_ton_target ?? 2),
      });
    }
  }

  async function loadHotWalletRefillChecks() {
    const response = await apiClient.get<{ items: GlmHotWalletRefillCheck[] }>('/api/referrals/admin/glm-hot-wallet-refill-checks', {
      params: { limit: 20 },
    });
    setHotWalletRefillChecks(response.data.items || []);
  }

  async function loadGlmAuditHashes() {
    const response = await apiClient.get<GlmAuditHashesResponse>('/api/referrals/admin/glm-audit-hashes', {
      params: { limit: 30 },
    });
    setGlmAuditHashes(response.data.hashes || []);
  }

  async function generateGlmAuditHash() {
    setSaving(true);
    setError(null);
    setGlmAuditResult(null);
    try {
      const response = await apiClient.post('/api/referrals/admin/glm-audit-hashes/generate', {
        audit_date: glmAuditDate || undefined,
      });
      const auditHash = response.data?.audit_hash;
      setGlmAuditResult(`Audit hash ${auditHash?.audit_date || glmAuditDate}: ${auditHash?.root_hash || 'сформирован'}`);
      await loadGlmAuditHashes();
      await loadGlmDashboard();
      await loadGlmBridgeReconciliation();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось сформировать GLM audit hash');
    } finally {
      setSaving(false);
    }
  }

  async function publishGlmAuditHash() {
    setSaving(true);
    setError(null);
    setGlmAuditResult(null);
    try {
      const response = await apiClient.post('/api/referrals/admin/glm-audit-hashes/publish', {
        audit_date: glmAuditDate || undefined,
      });
      const auditHash = response.data?.audit_hash;
      setGlmAuditResult(`Audit hash опубликован: ${auditHash?.audit_date || glmAuditDate}`);
      await loadGlmAuditHashes();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось опубликовать GLM audit hash');
    } finally {
      setSaving(false);
    }
  }

  async function loadGlmTransactions() {
    const response = await apiClient.get<GlmTransactionsResponse>('/api/referrals/admin/glm-transactions', {
      params: {
        type: glmTxType || undefined,
        status: glmTxStatus || undefined,
        limit: 100,
      },
    });
    setGlmTransactions(response.data.transactions || []);
  }

  async function loadGlmDashboard() {
    const response = await apiClient.get<GlmDashboard>('/api/referrals/admin/glm-dashboard');
    setGlmDashboard(response.data);
  }

  async function loadGlmEffectiveness() {
    const response = await apiClient.get<GlmEffectiveness>('/api/referrals/admin/glm-effectiveness');
    setGlmEffectiveness(response.data);
  }

  async function loadGlmSegments() {
    const response = await apiClient.get<GlmSegmentsResponse>('/api/referrals/admin/glm-segments');
    setGlmSegments(response.data.segments || []);
  }

  async function loadGlmRefundCandidates() {
    const response = await apiClient.get<GlmRefundCandidatesResponse>('/api/referrals/admin/glm-refund-candidates');
    setGlmRefundCandidates(response.data.candidates || []);
  }

  async function autoApplyGlmRefundCandidates(dryRun: boolean) {
    setSaving(true);
    setError(null);
    setGlmRefundAutoApplyResult(null);
    try {
      const response = await apiClient.post('/api/referrals/admin/glm-refund-candidates/auto-apply', {
        dry_run: dryRun,
        limit: 50,
        comment: dryRun ? 'Dry run GLM refund candidates' : 'Auto-apply trusted GLM refund candidates',
      });
      const plannedCount = Number(response.data?.planned_count || 0);
      const appliedCount = Number(response.data?.applied_count || 0);
      const errorCount = Number(response.data?.error_count || 0);
      setGlmRefundAutoApplyResult(dryRun
        ? `Dry run: найдено ${plannedCount} кандидатов для auto-apply.`
        : `Применено ${appliedCount} отмен GLM${errorCount ? `, ошибок: ${errorCount}` : ''}.`
      );
      await loadGlmRefundCandidates();
      await loadGlmTransactions();
      await loadGlmDashboard();
      await loadGlmEffectiveness();
      await loadGlmSegments();
      await loadPartners(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось выполнить auto-apply возвратов GLM');
    } finally {
      setSaving(false);
    }
  }

  async function loadBonusExpiryAudience() {
    const response = await apiClient.get<BonusExpiryAudienceResponse>('/api/referrals/admin/bonus-expiry-audience', {
      params: { days: Number.parseInt(bonusExpiryDays, 10) || 30, limit: 100 },
    });
    setBonusExpiryAudience(response.data.items || []);
  }

  async function createBonusExpiryDrafts() {
    setSaving(true);
    setError(null);
    setBonusExpiryDraftResult(null);
    try {
      const response = await apiClient.post('/api/referrals/admin/bonus-expiry-drafts', {
        days: Number.parseInt(bonusExpiryDays, 10) || 30,
        limit: 100,
      });
      setBonusExpiryDraftResult(`Создано ${response.data?.created_count || 0} draft-сообщений, пропущено ${response.data?.skipped_count || 0}.`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось создать draft-сообщения');
    } finally {
      setSaving(false);
    }
  }

  async function sendTelegramBroadcast(dryRun: boolean) {
    setSaving(true);
    setError(null);
    setTelegramBroadcastResult(null);
    try {
      const response = await apiClient.post<TelegramBroadcastResponse>('/api/referrals/admin/telegram-notifications/broadcast', {
        title: telegramBroadcastTitle.trim(),
        message: telegramBroadcastMessage.trim(),
        audience: telegramBroadcastAudience,
        dry_run: dryRun,
      });
      setTelegramBroadcastResult(response.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось отправить Telegram-рассылку партнерам');
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => void loadPartners(true), search ? 400 : 0);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, status, rewardMode, tonStatus]);

  useEffect(() => {
    void loadMediaMaterials();
    void loadRatePromotions();
    void loadRewardStoreItems();
  }, []);

  useEffect(() => {
    void loadGlmClaims();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [glmClaimStatus]);

  useEffect(() => {
    void loadGlmRedemptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [glmRedemptionStatus]);

  useEffect(() => {
    void loadGlmToPointsBridges();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [glmToPointsStatus]);

  useEffect(() => {
    void loadGlmTransactions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [glmTxType, glmTxStatus]);

  useEffect(() => {
    void loadGlmDashboard();
    void loadGlmEffectiveness();
    void loadGlmSegments();
    void loadGlmRefundCandidates();
    void loadGlmToPointsBridges();
    void loadGlmBridgeOperations();
    void loadGlmBridgeReconciliation();
    void loadGlmLoyaltyReconciliation();
    void loadGlmTonReadiness();
    void loadHotWalletRefillChecks();
    void loadGlmAuditHashes();
  }, []);

  useEffect(() => {
    void loadBonusExpiryAudience();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bonusExpiryDays]);

  async function updatePartner(patch: Record<string, any>) {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      const response = await apiClient.patch<PartnerPayload>(`/api/referrals/admin/partners/${selected.member.id}`, patch);
      setSelected((current) => current ? { ...current, ...response.data } : response.data);
      await loadPartners(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось сохранить изменения');
    } finally {
      setSaving(false);
    }
  }

  async function setGlmClaimAccess(enabled: boolean) {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      const response = await apiClient.post<PartnerPayload>(`/api/referrals/admin/partners/${selected.member.id}/glm-claim`, {
        enabled,
      });
      setSelected(response.data);
      await loadPartners(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось обновить GLM claim');
    } finally {
      setSaving(false);
    }
  }

  async function releaseGlmHold() {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      const response = await apiClient.post<PartnerPayload>(`/api/referrals/admin/partners/${selected.member.id}/glm-release`, {
        reason: 'admin_test_release',
      });
      setSelected(response.data);
      await loadPartners(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось перевести GLM из hold');
    } finally {
      setSaving(false);
    }
  }

  async function updateGlmClaim(id: string, nextStatus: 'processed' | 'failed' | 'canceled', operationId?: string | null) {
    setSaving(true);
    setError(null);
    try {
      const endpoint = operationId
        ? `/api/referrals/admin/glm-bridge/operations/${operationId}/claim`
        : `/api/referrals/admin/glm-claims/${id}`;
      await apiClient.patch(endpoint, {
        status: nextStatus,
        tx_hash: glmClaimTxHash.trim() || null,
        comment: glmClaimComment.trim() || null,
      });
      setGlmClaimTxHash('');
      setGlmClaimComment('');
      await loadGlmClaims();
      await loadGlmBridgeOperations();
      await loadGlmBridgeReconciliation();
      await loadGlmTransactions();
      await loadGlmDashboard();
      await loadGlmEffectiveness();
      await loadGlmSegments();
      await loadGlmRefundCandidates();
      await loadPartners(true);
      if (selected?.member.id) await loadPartner(selected.member.id);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось обработать GLM claim');
    } finally {
      setSaving(false);
    }
  }

  async function runGlmTonAutoTransfer() {
    setSaving(true);
    setError(null);
    try {
      const limit = Number(glmTonReadiness?.schedulers?.ton_auto_transfer?.batch_limit || 20);
      await apiClient.post('/api/referrals/admin/glm-ton-auto-transfer/run', {
        limit: Math.max(1, Math.min(limit || 20, 100)),
      });
      await loadGlmTonReadiness();
      await loadGlmClaims();
      await loadGlmTransactions();
      await loadGlmDashboard();
      await loadGlmBridgeReconciliation();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось запустить GLM auto-transfer');
    } finally {
      setSaving(false);
    }
  }

  async function setGlmTonAutoTransferOverride(enabled: boolean) {
    setSaving(true);
    setError(null);
    try {
      await apiClient.post('/api/referrals/admin/glm-ton-auto-transfer/override', {
        enabled,
        reason: enabled ? 'Admin resumed GLM auto-transfer from readiness panel.' : 'Admin paused GLM auto-transfer from readiness panel.',
      });
      await loadGlmTonReadiness();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось изменить GLM auto-transfer override');
    } finally {
      setSaving(false);
    }
  }

  async function saveHotWalletLimits() {
    setSaving(true);
    setError(null);
    setHotWalletLimitResult(null);
    try {
      await apiClient.post('/api/referrals/admin/glm-hot-wallet-limits', {
        hot_wallet_refill_glm_threshold: Number(hotWalletLimitForm.hot_wallet_refill_glm_threshold || 0),
        hot_wallet_refill_ton_threshold: Number(hotWalletLimitForm.hot_wallet_refill_ton_threshold || 0),
        hot_wallet_refill_glm_target: Number(hotWalletLimitForm.hot_wallet_refill_glm_target || 0),
        hot_wallet_refill_ton_target: Number(hotWalletLimitForm.hot_wallet_refill_ton_target || 0),
      });
      setHotWalletLimitResult('Лимиты hot-wallet сохранены');
      await loadGlmTonReadiness();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось сохранить лимиты hot-wallet');
    } finally {
      setSaving(false);
    }
  }

  async function checkTreasuryBalances() {
    setSaving(true);
    setError(null);
    setHotWalletRefillResult(null);
    try {
      const response = await apiClient.post<{ treasury_balances?: GlmTonReadiness['treasury_balances'] }>('/api/referrals/admin/glm-treasury-balances/check');
      setGlmTonReadiness((current) => current ? { ...current, treasury_balances: response.data.treasury_balances || response.data as any } : current);
      setHotWalletRefillResult('Балансы treasury/hot-wallet пересчитаны');
      await loadGlmTonReadiness();
      await loadHotWalletRefillChecks();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось проверить treasury/hot-wallet balances');
    } finally {
      setSaving(false);
    }
  }

  async function recordHotWalletRefill() {
    setSaving(true);
    setError(null);
    setHotWalletRefillResult(null);
    try {
      await apiClient.post('/api/referrals/admin/glm-hot-wallet-refill-checks/refill-record', {
        manual_glm_amount: Number(hotWalletRefillForm.manual_glm_amount || 0),
        manual_ton_amount: Number(hotWalletRefillForm.manual_ton_amount || 0),
        ton_tx_hash: hotWalletRefillForm.ton_tx_hash.trim() || null,
        comment: hotWalletRefillForm.comment.trim() || null,
      });
      setHotWalletRefillResult('Ручное пополнение записано в журнал');
      setHotWalletRefillForm({ manual_glm_amount: '', manual_ton_amount: '', ton_tx_hash: '', comment: '' });
      await loadGlmTonReadiness();
      await loadHotWalletRefillChecks();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось записать пополнение hot-wallet');
    } finally {
      setSaving(false);
    }
  }

  async function confirmHotWalletRefillInWallet() {
    setSaving(true);
    setError(null);
    setHotWalletRefillResult(null);
    setHotWalletRefillTonResult(null);
    try {
      if (!tonWallet) {
        setHotWalletRefillTonResult('Подключите treasury-кошелек GLAME, затем повторите пополнение.');
        openTonConnectModal();
        setSaving(false);
        return;
      }
      setHotWalletRefillTonResult('Готовим TON Connect транзакцию для treasury-кошелька...');
      const response = await apiClient.post<TonConnectTransactionPayload>('/api/referrals/admin/glm-hot-wallet-refill-plan/ton-transaction');
      const payload = response.data;
      if (payload.transaction?.from && tonWallet.account.address !== payload.transaction.from) {
        setHotWalletRefillTonResult(`Проверьте кошелек: нужен treasury ${payload.transaction.from}, сейчас подключен ${tonWallet.account.address}.`);
      }
      setHotWalletRefillTonResult('Откройте кошелек и подтвердите refill hot-wallet.');
      await tonConnectUI.sendTransaction(payload.transaction);
      await apiClient.post('/api/referrals/admin/glm-hot-wallet-refill-checks/refill-record', {
        manual_glm_amount: Number(payload.refill_glm_amount || 0),
        manual_ton_amount: Number(payload.refill_ton_amount || 0),
        ton_tx_hash: null,
        comment: `TON Connect refill submitted from admin. Messages: ${payload.transaction.messages.length}.`,
      });
      setHotWalletRefillTonResult('TON Connect refill отправлен в кошелек. Запись пополнения добавлена, после подтверждения в сети нажмите “Проверить балансы”.');
      await loadGlmTonReadiness();
      await loadHotWalletRefillChecks();
    } catch (e: any) {
      const message = String(e?.response?.data?.detail || e?.message || '');
      setHotWalletRefillTonResult(
        message.toLowerCase().includes('insufficient')
          ? 'В treasury-кошельке не хватает testnet TON gas для комиссии.'
          : message || 'Не удалось отправить refill через TON Connect'
      );
    } finally {
      setSaving(false);
    }
  }

  async function copyHotWalletRefillPlan() {
    const plan = hotWalletRefillPlan;
    if (!plan) return;
    const lines = [
      'GLAME hot-wallet refill plan',
      `status: ${label(plan.status)}`,
      `network: ${plan.network || glmTonReadiness?.treasury_balances?.config?.network || '—'}`,
      `from treasury: ${plan.source_address || '—'}`,
      `to hot-wallet: ${plan.destination_address || '—'}`,
      `send GLM: ${plan.refill_glm_amount || 0}`,
      `send TON gas: ${plan.refill_ton_amount || 0}`,
      `hot-wallet now: ${plan.hot_wallet_glm_balance || 0} GLM / ${plan.hot_wallet_ton_balance || 0} TON`,
      `treasury now: ${plan.treasury_glm_balance || 0} GLM / ${plan.treasury_ton_balance || 0} TON`,
      `target: ${plan.target_glm || 0} GLM / ${plan.target_ton || 0} TON`,
      `errors: ${(plan.errors || []).join(', ') || 'none'}`,
    ];
    await navigator.clipboard.writeText(lines.join('\n'));
    setHotWalletRefillResult('План пополнения скопирован');
  }

  async function updateGlmRedemption(id: string, nextStatus: 'fulfilled' | 'failed' | 'canceled') {
    setSaving(true);
    setError(null);
    try {
      await apiClient.patch(`/api/referrals/admin/glm-redemptions/${id}`, {
        status: nextStatus,
        comment: glmFulfillmentComment.trim() || null,
      });
      setGlmFulfillmentComment('');
      await loadGlmRedemptions();
      await loadGlmTransactions();
      await loadGlmDashboard();
      await loadGlmEffectiveness();
      await loadGlmSegments();
      await loadGlmToPointsBridges();
      await loadPartners(true);
      if (selected?.member.id) await loadPartner(selected.member.id);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось обработать GLM Store заказ');
    } finally {
      setSaving(false);
    }
  }

  async function updateGlmToPointsBridge(id: string, nextStatus: 'processed' | 'failed' | 'canceled', operationId?: string | null) {
    setSaving(true);
    setError(null);
    try {
      const endpoint = operationId
        ? `/api/referrals/admin/glm-bridge/operations/${operationId}/glm-to-points`
        : `/api/referrals/admin/glm-bridge/glm-to-points/${id}`;
      await apiClient.patch(endpoint, {
        status: nextStatus,
        points: glmToPointsValue.trim() ? Number.parseInt(glmToPointsValue, 10) : null,
        onec_document_id: glmToPointsDocument.trim() || null,
        comment: glmToPointsComment.trim() || null,
      });
      setGlmToPointsValue('');
      setGlmToPointsDocument('');
      setGlmToPointsComment('');
      await loadGlmToPointsBridges();
      await loadGlmBridgeOperations();
      await loadGlmBridgeReconciliation();
      await loadGlmTransactions();
      await loadGlmDashboard();
      await loadGlmEffectiveness();
      await loadGlmSegments();
      await loadPartners(true);
      if (selected?.member.id) await loadPartner(selected.member.id);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось обработать GLM -> баллы bridge');
    } finally {
      setSaving(false);
    }
  }

  async function settleGlmToPointsBridgeDeposit(id: string, operationId?: string | null) {
    const txHash = (glmToPointsDepositHashes[id] || '').trim();
    if (!txHash) {
      setError('Укажите TON tx hash депозита GLM');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const endpoint = operationId
        ? `/api/referrals/admin/glm-bridge/operations/${operationId}/glm-to-points-ton-deposit`
        : `/api/referrals/admin/glm-bridge/glm-to-points/${id}/ton-deposit`;
      await apiClient.post(endpoint, {
        tx_hash: txHash,
        require_verified: true,
        comment: glmToPointsComment.trim() || null,
      });
      setGlmToPointsDepositHashes((current) => {
        const next = { ...current };
        delete next[id];
        return next;
      });
      setGlmToPointsComment('');
      await loadGlmToPointsBridges();
      await loadGlmBridgeOperations();
      await loadGlmBridgeReconciliation();
      await loadGlmTransactions();
      await loadGlmDashboard();
      await loadGlmEffectiveness();
      await loadGlmSegments();
      await loadPartners(true);
      if (selected?.member.id) await loadPartner(selected.member.id);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось подтвердить TON deposit GLM');
    } finally {
      setSaving(false);
    }
  }

  async function repairGlmBridge(id: string, action: 'retry_onec' | 'record_manual_document' | 'mark_reviewed', operationId?: string | null) {
    setSaving(true);
    setError(null);
    try {
      const endpoint = operationId
        ? `/api/referrals/admin/glm-bridge/operations/${operationId}/repair`
        : `/api/referrals/admin/glm-bridge/${id}/repair`;
      await apiClient.post(endpoint, {
        action,
        onec_document_id: glmToPointsDocument.trim() || null,
        comment: glmToPointsComment.trim() || null,
      });
      setGlmToPointsDocument('');
      setGlmToPointsComment('');
      await loadGlmToPointsBridges();
      await loadGlmBridgeOperations();
      await loadGlmBridgeReconciliation();
      await loadGlmTransactions();
      await loadGlmDashboard();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось выполнить repair GLM bridge');
    } finally {
      setSaving(false);
    }
  }

  async function repairPointsToGlmSpend(id: string, action: 'retry_onec_spend' | 'record_manual_spend_document' | 'mark_reviewed', operationId?: string | null) {
    setSaving(true);
    setError(null);
    try {
      const endpoint = operationId
        ? `/api/referrals/admin/glm-bridge/operations/${operationId}/points-to-glm-spend-repair`
        : `/api/referrals/admin/glm-bridge/points-to-glm/${id}/spend-repair`;
      await apiClient.post(endpoint, {
        action,
        onec_document_id: glmToPointsDocument.trim() || null,
        comment: glmToPointsComment.trim() || null,
      });
      setGlmToPointsDocument('');
      setGlmToPointsComment('');
      await loadGlmBridgeOperations();
      await loadGlmBridgeReconciliation();
      await loadGlmTransactions();
      await loadGlmDashboard();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось выполнить repair списания 1С для points -> GLM');
    } finally {
      setSaving(false);
    }
  }

  async function runGlmBridgeIssueAction(
    id: string,
    action: 'settle_ton_transfer' | 'cancel_onec_spend' | 'mark_legacy_manual' | 'mark_reviewed',
    issueCode?: string,
    operationId?: string | null,
  ) {
    setSaving(true);
    setError(null);
    try {
      const endpoint = operationId
        ? `/api/referrals/admin/glm-bridge/operations/${operationId}/reconciliation-action`
        : `/api/referrals/admin/glm-bridge/reconciliation/${id}/action`;
      await apiClient.post(endpoint, {
        action,
        issue_code: issueCode || null,
        tx_hash: glmToPointsDepositHashes[id]?.trim() || null,
        comment: glmToPointsComment.trim() || null,
      });
      setGlmToPointsComment('');
      await loadGlmBridgeOperations();
      await loadGlmBridgeReconciliation();
      await loadGlmTransactions();
      await loadGlmDashboard();
      await loadGlmClaims();
      await loadGlmToPointsBridges();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось выполнить действие reconciliation');
    } finally {
      setSaving(false);
    }
  }

  async function releaseDueGlmHolds() {
    setSaving(true);
    setError(null);
    setGlmReleaseResult(null);
    try {
      const response = await apiClient.post('/api/referrals/admin/glm-release-due', { limit: 500 });
      const releasedCount = Number(response.data?.released_count || 0);
      const releasedAmount = Number(response.data?.released_amount || 0);
      const skippedCount = Number(response.data?.skipped_count || 0);
      setGlmReleaseResult(`Выпущено ${releasedAmount} GLM по ${releasedCount} hold-транзакциям${skippedCount ? `, пропущено ${skippedCount}` : ''}.`);
      await loadGlmTransactions();
      await loadGlmClaims();
      await loadGlmDashboard();
      await loadGlmEffectiveness();
      await loadGlmSegments();
      await loadPartners(true);
      if (selected?.member.id) await loadPartner(selected.member.id);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось выпустить истекший GLM hold');
    } finally {
      setSaving(false);
    }
  }

  async function adjustGlmBalance() {
    if (!selected) return;
    const amount = Number.parseInt(glmAdjustAmount, 10);
    if (!amount || amount <= 0) {
      setError('Укажите сумму корректировки GLM');
      return;
    }
    if (glmAdjustReason.trim().length < 5) {
      setError('Укажите причину корректировки GLM');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const response = await apiClient.post<PartnerPayload>(`/api/referrals/admin/partners/${selected.member.id}/glm-adjustment`, {
        amount,
        direction: glmAdjustDirection,
        reason: glmAdjustReason.trim(),
        comment: glmAdjustComment.trim() || null,
      });
      setSelected(response.data);
      setGlmAdjustAmount('');
      setGlmAdjustReason('');
      setGlmAdjustComment('');
      await loadGlmTransactions();
      await loadGlmDashboard();
      await loadGlmEffectiveness();
      await loadGlmSegments();
      await loadPartners(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось скорректировать GLM balance');
    } finally {
      setSaving(false);
    }
  }

  async function cancelReferralCommission(commissionId: string, memberId?: string) {
    const targetMemberId = memberId || selected?.member.id;
    if (!targetMemberId) return;
    setSaving(true);
    setError(null);
    try {
      const response = await apiClient.post<PartnerPayload>(`/api/referrals/admin/partners/${targetMemberId}/commissions/${commissionId}/cancel`, {
        reason: 'order_return_or_cancel',
        comment: commissionCancelComment.trim() || null,
      });
      setSelected(response.data);
      setCommissionCancelComment('');
      await loadGlmTransactions();
      await loadGlmDashboard();
      await loadGlmEffectiveness();
      await loadGlmSegments();
      await loadGlmRefundCandidates();
      await loadPartners(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось отменить комиссию и GLM');
    } finally {
      setSaving(false);
    }
  }

  async function createPayout() {
    if (!selected) return;
    const rub = Number(String(payoutAmount).replace(',', '.'));
    if (!rub || rub <= 0) {
      setError('Укажите сумму выплаты в рублях');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await apiClient.post(`/api/referrals/admin/partners/${selected.member.id}/payouts`, {
        amount_kopecks: Math.round(rub * 100),
        status: 'pending',
        onec_payment_document_id: payoutDocument.trim() || null,
        comment: payoutComment.trim() || null,
      });
      setPayoutAmount('');
      setPayoutDocument('');
      setPayoutComment('');
      await loadPartner(selected.member.id);
      await loadPartners(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось создать выплату');
    } finally {
      setSaving(false);
    }
  }

  async function updatePayout(id: string, nextStatus: string) {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      await apiClient.patch(`/api/referrals/admin/payouts/${id}`, {
        status: nextStatus,
        onec_payment_document_id: payoutDocument.trim() || undefined,
      });
      await loadPartner(selected.member.id);
      await loadPartners(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось обновить выплату');
    } finally {
      setSaving(false);
    }
  }

  async function reviewCashRequest(id: string, nextStatus: 'approved' | 'rejected') {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      await apiClient.patch(`/api/referrals/admin/cash-requests/${id}`, {
        status: nextStatus,
        onec_agency_contract_id: contractId.trim() || null,
      });
      await loadPartner(selected.member.id);
      await loadPartners(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось рассмотреть заявку');
    } finally {
      setSaving(false);
    }
  }

  async function attachPosReferral() {
    if (!posPhone.trim() || !posCode.trim()) {
      setError('Для РМК укажите телефон покупателя и реферальный код');
      return;
    }
    setSaving(true);
    setError(null);
    setPosResult(null);
    try {
      const response = await apiClient.post('/api/referrals/admin/pos-attribution', {
        phone: posPhone.trim(),
        code: posCode.trim(),
        full_name: posName.trim() || null,
      });
      const points = Number(response.data?.welcome_points || 0);
      setPosResult(points > 0 ? `Покупатель привязан. Начислено ${points} бонусов.` : 'Покупатель уже был привязан, повторное начисление не выполнено.');
      setPosPhone('');
      setPosCode('');
      setPosName('');
      await loadPartners(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось привязать покупателя из РМК');
    } finally {
      setSaving(false);
    }
  }

  async function lookupGlmPosCode() {
    if (!glmPosCode.trim()) {
      setError('Укажите GLM POS-код');
      return;
    }
    setSaving(true);
    setError(null);
    setGlmPosResult(null);
    try {
      const response = await apiClient.get(`/api/referrals/admin/glm-pos/${encodeURIComponent(glmPosCode.trim())}`);
      setGlmPosResult(`${response.data?.partner_name || 'Партнер GLAME'} · ${response.data?.partner_phone || 'телефон не указан'} · balance ${response.data?.balance || 0} GLM · hold ${response.data?.hold_balance || 0} GLM`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'GLM POS-код не найден');
    } finally {
      setSaving(false);
    }
  }

  async function uploadMediaMaterial() {
    if (!mediaFile) {
      setError('Выберите файл медиаматериала');
      return;
    }
    setSaving(true);
    setError(null);
    setMediaResult(null);
    try {
      const form = new FormData();
      form.append('file', mediaFile);
      form.append('title', mediaTitle.trim() || mediaFile.name);
      form.append('category', mediaCategory);
      form.append('description', mediaDescription.trim());
      form.append('sort_order', mediaSortOrder || '100');
      form.append('is_active', 'true');
      await apiClient.post('/api/referrals/admin/media-materials', form);
      setMediaTitle('');
      setMediaDescription('');
      setMediaSortOrder('100');
      setMediaFile(null);
      const fileInput = document.getElementById('referral-media-file') as HTMLInputElement | null;
      if (fileInput) fileInput.value = '';
      setMediaResult('Материал загружен и доступен партнерам.');
      await loadMediaMaterials();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось загрузить медиаматериал');
    } finally {
      setSaving(false);
    }
  }

  async function updateMediaMaterial(id: string, patch: Partial<MediaMaterial>) {
    setSaving(true);
    setError(null);
    try {
      await apiClient.patch(`/api/referrals/admin/media-materials/${id}`, patch);
      await loadMediaMaterials();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось обновить медиаматериал');
    } finally {
      setSaving(false);
    }
  }

  async function deleteMediaMaterial(id: string) {
    setSaving(true);
    setError(null);
    try {
      await apiClient.delete(`/api/referrals/admin/media-materials/${id}`);
      await loadMediaMaterials();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось удалить медиаматериал');
    } finally {
      setSaving(false);
    }
  }

  async function createRatePromotion() {
    setSaving(true);
    setError(null);
    setPromoResult(null);
    try {
      if (!promoStartsAt || !promoEndsAt) {
        setError('Укажите дату начала и окончания акции');
        return;
      }
      await apiClient.post('/api/referrals/admin/rate-promotions', {
        title: promoTitle.trim() || 'Акция по баллам',
        rate_percent: Number.parseFloat(promoRate.replace(',', '.')) || 0,
        starts_at: new Date(promoStartsAt).toISOString(),
        ends_at: new Date(promoEndsAt).toISOString(),
        is_active: true,
      });
      setPromoResult('Акция сохранена. В период действия новые начисления баллов партнерам будут считаться по этому проценту.');
      setPromoTitle('Акция по баллам');
      setPromoRate('10');
      setPromoStartsAt(toDateTimeLocal(new Date().toISOString()));
      setPromoEndsAt('');
      await loadRatePromotions();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось сохранить акцию');
    } finally {
      setSaving(false);
    }
  }

  async function updateRatePromotion(id: string, patch: Partial<RatePromotion>) {
    setSaving(true);
    setError(null);
    try {
      await apiClient.patch(`/api/referrals/admin/rate-promotions/${id}`, patch);
      await loadRatePromotions();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось обновить акцию');
    } finally {
      setSaving(false);
    }
  }

  async function deleteRatePromotion(id: string) {
    setSaving(true);
    setError(null);
    try {
      await apiClient.delete(`/api/referrals/admin/rate-promotions/${id}`);
      await loadRatePromotions();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось удалить акцию');
    } finally {
      setSaving(false);
    }
  }

  const totals = useMemo(
    () => overview || { partners_total: 0, partners_active: 0, cash_pending: 0, payouts_pending_kopecks: 0, ton_verified: 0, glm_claim_enabled: 0 },
    [overview]
  );

  return (
    <div className="min-w-0 space-y-6">
      <div className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="text-sm font-medium uppercase tracking-wide text-slate-500">Партнерская программа</div>
        <div className="mt-2 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-slate-900">Администрирование партнеров</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-600">Статистика партнеров, рефералы, начисления, выплаты и данные для агентского договора.</p>
          </div>
          <button onClick={() => void loadPartners(true)} disabled={loading || saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Обновить</button>
        </div>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Metric title="Партнеров" value={`${totals.partners_total}`} />
        <Metric title="Активных" value={`${totals.partners_active}`} />
        <Metric title="Заявок на деньги" value={`${totals.cash_pending}`} />
        <Metric title="К выплате" value={money(totals.payouts_pending_kopecks)} />
        <Metric title="TON verified" value={`${totals.ton_verified || 0}`} />
        <Metric title="GLM в TON" value={`${totals.glm_claim_enabled || 0}`} />
      </div>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">Telegram</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Рассылка партнерам</div>
            <p className="mt-2 max-w-3xl text-sm text-slate-600">
              Сообщение отправляется от имени партнерской программы всем партнерам, которые подключили Telegram-бота в профиле.
            </p>
          </div>
          <select
            value={telegramBroadcastAudience}
            onChange={(event) => setTelegramBroadcastAudience(event.target.value as 'active_connected' | 'all_connected')}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="active_connected">Активные с Telegram</option>
            <option value="all_connected">Все с Telegram</option>
          </select>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-[0.8fr_1.6fr_auto_auto]">
          <input
            value={telegramBroadcastTitle}
            onChange={(event) => setTelegramBroadcastTitle(event.target.value)}
            maxLength={120}
            placeholder="Тема: новая акция, условия, новости"
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <textarea
            value={telegramBroadcastMessage}
            onChange={(event) => setTelegramBroadcastMessage(event.target.value)}
            maxLength={3000}
            rows={3}
            placeholder="Текст сообщения для партнеров"
            className="min-h-[44px] rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            onClick={() => void sendTelegramBroadcast(true)}
            disabled={saving || telegramBroadcastTitle.trim().length < 3 || telegramBroadcastMessage.trim().length < 3}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60"
          >
            Проверить
          </button>
          <button
            onClick={() => void sendTelegramBroadcast(false)}
            disabled={saving || telegramBroadcastTitle.trim().length < 3 || telegramBroadcastMessage.trim().length < 3}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            Отправить
          </button>
        </div>
        {telegramBroadcastResult ? (
          <div className={`mt-3 rounded-md border p-3 text-sm ${
            telegramBroadcastResult.status === 'dry_run'
              ? 'border-sky-200 bg-sky-50 text-sky-800'
              : telegramBroadcastResult.failed
                ? 'border-amber-200 bg-amber-50 text-amber-800'
                : 'border-emerald-200 bg-emerald-50 text-emerald-800'
          }`}>
            {telegramBroadcastResult.status === 'dry_run'
              ? `Найдено получателей: ${telegramBroadcastResult.recipients_count}.`
              : `Отправлено: ${telegramBroadcastResult.sent || 0} из ${telegramBroadcastResult.recipients_count}${telegramBroadcastResult.failed ? `, ошибок: ${telegramBroadcastResult.failed}` : ''}.`}
            {telegramBroadcastResult.sample?.length ? (
              <div className="mt-2 text-xs">
                Пример: {telegramBroadcastResult.sample.map((item) => item.partner_name).join(', ')}
              </div>
            ) : null}
            {telegramBroadcastResult.errors?.length ? (
              <div className="mt-2 text-xs">
                Ошибки: {telegramBroadcastResult.errors.map((item) => item.partner_name).join(', ')}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">Настройки начислений</div>
        <div className="mt-1 text-lg font-semibold text-slate-900">Акции по баллам для партнеров</div>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Акция временно заменяет стандартный процент уровня партнера только для режима «Баллы GLAME». После окончания периода новые начисления снова считаются по обычным условиям.
        </p>
        <div className="mt-4 grid gap-3 lg:grid-cols-[1.2fr_0.45fr_0.8fr_0.8fr_auto]">
          <input value={promoTitle} onChange={(event) => setPromoTitle(event.target.value)} placeholder="Название акции" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          <input value={promoRate} onChange={(event) => setPromoRate(event.target.value)} placeholder="%" inputMode="decimal" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          <input value={promoStartsAt} onChange={(event) => setPromoStartsAt(event.target.value)} type="datetime-local" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          <input value={promoEndsAt} onChange={(event) => setPromoEndsAt(event.target.value)} type="datetime-local" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          <button onClick={() => void createRatePromotion()} disabled={saving} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">Сохранить</button>
        </div>
        {promoResult ? <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{promoResult}</div> : null}
        <div className="mt-5 grid gap-3 lg:grid-cols-2">
          {ratePromotions.map((item) => (
            <div key={item.id} className="rounded-md border border-slate-200 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="font-semibold text-slate-900">{item.title}</div>
                  <div className="mt-1 text-sm text-slate-600">{item.rate_percent}% от суммы покупки в баллах</div>
                </div>
                <Badge value={item.status} />
              </div>
              <div className="mt-4 grid gap-2 text-sm text-slate-600 sm:grid-cols-2">
                <div>
                  <span className="text-slate-400">Начало:</span> {dateTimeRu(item.starts_at)}
                </div>
                <div>
                  <span className="text-slate-400">Окончание:</span> {dateTimeRu(item.ends_at)}
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button disabled={saving} onClick={() => void updateRatePromotion(item.id, { is_active: !item.is_active })} className="rounded border border-slate-300 px-3 py-2 text-xs text-slate-700 disabled:opacity-50">
                  {item.is_active ? 'Поставить на паузу' : 'Включить'}
                </button>
                <button disabled={saving} onClick={() => void deleteRatePromotion(item.id)} className="rounded border border-red-200 px-3 py-2 text-xs text-red-700 disabled:opacity-50">Удалить</button>
              </div>
            </div>
          ))}
          {!ratePromotions.length ? <div className="text-sm text-slate-500">Акций пока нет. Стандартные проценты берутся из уровня партнера.</div> : null}
        </div>
      </section>

      <section id="reward-store" className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">РМК</div>
        <div className="mt-1 text-lg font-semibold text-slate-900">Привязать покупателя к партнеру</div>
        <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_1fr_1fr_auto]">
          <input value={posPhone} onChange={(event) => setPosPhone(event.target.value)} placeholder="Телефон покупателя" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          <input value={posCode} onChange={(event) => setPosCode(event.target.value.toUpperCase())} placeholder="Реферальный код" className="rounded-md border border-slate-300 px-3 py-2 text-sm uppercase" />
          <input value={posName} onChange={(event) => setPosName(event.target.value)} placeholder="ФИО, если есть" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          <button onClick={() => void attachPosReferral()} disabled={saving} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">Привязать</button>
        </div>
        {posResult ? <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{posResult}</div> : null}
        <p className="mt-3 text-xs text-slate-500">Используйте, если покупатель создается в РМК 1С, где нет отдельного поля реферального кода.</p>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">GLM POS</div>
        <div className="mt-1 text-lg font-semibold text-slate-900">Проверить GLM-код в магазине</div>
        <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto]">
          <input value={glmPosCode} onChange={(event) => setGlmPosCode(event.target.value.toUpperCase())} placeholder="GLM-XXXXXXXXXX" className="rounded-md border border-slate-300 px-3 py-2 text-sm uppercase" />
          <button onClick={() => void lookupGlmPosCode()} disabled={saving} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">Проверить</button>
        </div>
        {glmPosResult ? <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{glmPosResult}</div> : null}
        <p className="mt-3 text-xs text-slate-500">Пилотный режим: код подтверждает GLM-аккаунт и доступный balance; списание проводится через GLM Store/redemption или админскую корректировку.</p>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">Медиаматериалы</div>
        <div className="mt-1 text-lg font-semibold text-slate-900">Материалы для кабинета партнера</div>
        <div className="mt-4 grid gap-3 lg:grid-cols-[1.1fr_0.8fr_1.2fr_0.45fr]">
          <input value={mediaTitle} onChange={(event) => setMediaTitle(event.target.value)} placeholder="Название материала" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          <select value={mediaCategory} onChange={(event) => setMediaCategory(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
            <option value="logos">Логотипы</option>
            <option value="patterns">Паттерны</option>
            <option value="phrases">Фирменные фразы</option>
            <option value="signs">Знак GLAME</option>
            <option value="other">Другое</option>
          </select>
          <input value={mediaDescription} onChange={(event) => setMediaDescription(event.target.value)} placeholder="Описание" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          <input value={mediaSortOrder} onChange={(event) => setMediaSortOrder(event.target.value)} placeholder="Порядок" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_auto]">
          <input id="referral-media-file" type="file" accept="image/*,application/pdf" onChange={(event) => setMediaFile(event.target.files?.[0] || null)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          <button onClick={() => void uploadMediaMaterial()} disabled={saving} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">Загрузить</button>
        </div>
        {mediaResult ? <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{mediaResult}</div> : null}
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {mediaMaterials.map((item) => (
            <div key={item.id} className="rounded-md border border-slate-200 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate font-semibold text-slate-900">{item.title}</div>
                  <div className="mt-1 text-xs text-slate-500">{mediaCategoryLabels[item.category] || item.category} · {fileSizeRu(item.size)}</div>
                </div>
                <Badge value={item.is_active ? 'active' : 'paused'} />
              </div>
              <div className="mt-3 truncate text-xs text-slate-500">{item.original_file_name}</div>
              <div className="mt-4 flex flex-wrap gap-2">
                <a href={item.file_url} target="_blank" rel="noreferrer" className="rounded border border-slate-300 px-3 py-2 text-xs text-slate-700">Открыть</a>
                <button disabled={saving} onClick={() => void updateMediaMaterial(item.id, { is_active: !item.is_active })} className="rounded border border-slate-300 px-3 py-2 text-xs text-slate-700 disabled:opacity-50">
                  {item.is_active ? 'Скрыть' : 'Показать'}
                </button>
                <button disabled={saving} onClick={() => void deleteMediaMaterial(item.id)} className="rounded border border-red-200 px-3 py-2 text-xs text-red-700 disabled:opacity-50">Удалить</button>
              </div>
            </div>
          ))}
          {!mediaMaterials.length ? <div className="text-sm text-slate-500">Материалы пока не загружены</div> : null}
        </div>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">GLM Effectiveness</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Экономика использования CryptoGLAME</div>
          </div>
          <button onClick={() => void loadGlmEffectiveness()} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Обновить</button>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Metric title="Redemption conversion" value={`${glmEffectiveness?.redemption_conversion_percent || 0}%`} hint={`${glmEffectiveness?.redeemers_count || 0} из ${glmEffectiveness?.accounts_total || 0} accounts`} />
          <Metric title="Burn ratio" value={`${glmEffectiveness?.burn_ratio_percent || 0}%`} hint={`${glmEffectiveness?.lifetime_burned_total || 0} / ${glmEffectiveness?.lifetime_earned_total || 0} GLM`} />
          <Metric title="Store usage" value={`${glmEffectiveness?.redemption_total || 0} GLM`} hint={`${glmEffectiveness?.redemption_count || 0} заказов`} />
          <Metric title="Points→GLM" value={`${glmEffectiveness?.conversion_total || 0} GLM`} hint={`${glmEffectiveness?.conversion_accounts || 0} accounts`} />
          <Metric title="Ready to spend" value={`${glmEffectiveness?.ready_to_redeem_count || 0}`} hint={`${glmEffectiveness?.active_balance_accounts || 0} с балансом`} />
          <Metric title="Need activation" value={`${glmEffectiveness?.high_balance_no_redemption_count || 0}`} hint={`из ${glmEffectiveness?.high_balance_count || 0} high-balance`} />
        </div>
        <div className="mt-4 grid gap-4 xl:grid-cols-[0.75fr_1.25fr]">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Текущий месяц</div>
            <div className="mt-3 grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
              <Metric title="Earn" value={`${glmEffectiveness?.monthly_earn_total || 0} GLM`} />
              <Metric title="Points→GLM" value={`${glmEffectiveness?.monthly_conversion_total || 0} GLM`} />
              <Metric title="Redeemed" value={`${glmEffectiveness?.monthly_redemption_total || 0} GLM`} />
            </div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Категории списаний</div>
              <div className="mt-3 space-y-2">
                {(glmEffectiveness?.redemption_by_category || []).map((item) => (
                  <div key={item.category} className="flex items-center justify-between gap-3 rounded border border-slate-200 bg-white p-3 text-sm">
                    <span className="truncate font-medium text-slate-900">{item.category}</span>
                    <span className="shrink-0 text-slate-600">{item.amount} GLM · {item.count}</span>
                  </div>
                ))}
                {!(glmEffectiveness?.redemption_by_category || []).length ? <div className="text-sm text-slate-500">Списаний GLM Store пока нет</div> : null}
              </div>
            </div>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Топ товаров GLM Store</div>
              <div className="mt-3 space-y-2">
                {(glmEffectiveness?.top_redemption_items || []).map((item) => (
                  <div key={item.sku} className="rounded border border-slate-200 bg-white p-3 text-sm">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate font-medium text-slate-900">{item.title || item.sku}</div>
                        <div className="mt-1 break-all text-xs text-slate-500">{item.sku}</div>
                      </div>
                      <div className="shrink-0 text-right text-slate-600">{item.amount} GLM<div className="mt-1 text-xs text-slate-400">{item.count} шт.</div></div>
                    </div>
                  </div>
                ))}
                {!(glmEffectiveness?.top_redemption_items || []).length ? <div className="text-sm text-slate-500">Топ появится после первых списаний</div> : null}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">GLM Refund Control</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Кандидаты на отмену GLM по возвратам</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => void autoApplyGlmRefundCandidates(true)} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Dry run</button>
            <button onClick={() => void autoApplyGlmRefundCandidates(false)} disabled={saving} className="rounded-md border border-red-200 px-4 py-2 text-sm font-medium text-red-700 disabled:opacity-60">Auto-apply</button>
            <button onClick={() => void loadGlmRefundCandidates()} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Обновить</button>
          </div>
        </div>
        {glmRefundAutoApplyResult ? <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{glmRefundAutoApplyResult}</div> : null}
        <div className="mt-4">
          <DataTable
            headers={['Дата', 'Партнер', 'Причина', 'Комиссия', 'GLM', 'Источник', 'Действие']}
            rows={glmRefundCandidates.map((item) => [
              dateRu(item.created_at),
              <div key={`partner-${item.commission_id}`}>
                <div className="font-medium text-slate-900">{item.partner_name || 'Партнер GLAME'}</div>
                <div className="mt-1 text-xs text-slate-500">{item.partner_phone || '—'}</div>
              </div>,
              <div key={`signals-${item.commission_id}`} className="space-y-1">
                {(item.signals || []).map((signal) => <Badge key={`${item.commission_id}-${signal}`} value={signal} />)}
              </div>,
              item.reward_mode === 'cash' ? money(item.commission_amount_kopecks) : `${item.points || 0} баллов`,
              item.glm_amount ? `${item.glm_amount} GLM · ${item.glm_status || '—'}${item.auto_apply_eligible ? ' · auto' : ''}` : '—',
              item.order_id ? `order ${item.order_status || '—'}` : item.purchase_id ? `purchase ${item.purchase_total_amount ?? '—'}` : '—',
              <button key={`refund-${item.commission_id}`} disabled={saving} onClick={() => void cancelReferralCommission(item.commission_id, item.member_id)} className="rounded border border-red-200 px-3 py-2 text-xs font-medium text-red-700 disabled:opacity-50">Отменить GLM</button>,
            ])}
          />
          {!glmRefundCandidates.length ? <div className="mt-3 text-sm text-slate-500">Кандидатов на возврат GLM сейчас нет</div> : null}
        </div>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">Bonus expiry</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">CRM: сгорающие баллы {'->'} GLM</div>
          </div>
          <div className="grid gap-2 sm:grid-cols-[0.8fr_auto_auto_auto]">
            <select value={bonusExpiryDays} onChange={(event) => setBonusExpiryDays(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="7">7 дней</option>
              <option value="30">30 дней</option>
              <option value="60">60 дней</option>
              <option value="90">90 дней</option>
            </select>
            <button onClick={() => void loadBonusExpiryAudience()} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Обновить</button>
            <a href={`/api/referrals/admin/bonus-expiry-audience.csv?days=${bonusExpiryDays}&limit=1000`} className="inline-flex items-center justify-center rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700">CSV</a>
            <button onClick={() => void createBonusExpiryDrafts()} disabled={saving || !bonusExpiryAudience.length} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">Создать drafts</button>
          </div>
        </div>
        {bonusExpiryDraftResult ? <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{bonusExpiryDraftResult}</div> : null}
        <div className="mt-4">
          <DataTable
            headers={['Клиент', 'Баланс 1С', 'Сгорает', 'Ближайшая дата', 'Текст points_to_glm']}
            rows={bonusExpiryAudience.map((item) => [
              <div key={`client-${item.user_id}`}>
                <div className="font-medium text-slate-900">{item.full_name || 'Клиент GLAME'}</div>
                <div className="mt-1 text-xs text-slate-500">{item.phone || item.email || '—'}</div>
              </div>,
              `${item.loyalty_points || 0} баллов`,
              <div key={`exp-${item.user_id}`} className="text-sm text-slate-700">
                <div>{item.expiring_points || 0} баллов</div>
                <div className="mt-1 text-xs text-slate-500">{item.lots_count || 0} начислений</div>
              </div>,
              dateRu(item.nearest_expiry),
              <div key={`msg-${item.user_id}`} className="max-w-[360px] text-xs leading-5 text-slate-600">{item.campaign_message}</div>,
            ])}
          />
        </div>
      </section>

      <section id="ton-readiness" className="rounded-md border border-slate-200 bg-white p-5 shadow-sm scroll-mt-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">TON Testnet Readiness</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Готовность GLM treasury transfer workflow</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => void runGlmTonAutoTransfer()} disabled={saving || !glmTonReadiness?.auto_transfer?.ready} className="rounded-md border border-emerald-200 px-4 py-2 text-sm font-medium text-emerald-700 disabled:opacity-50">Запустить auto-transfer</button>
            <button onClick={() => void setGlmTonAutoTransferOverride(false)} disabled={saving || glmTonReadiness?.auto_transfer?.override?.enabled === false} className="rounded-md border border-rose-200 px-4 py-2 text-sm font-medium text-rose-700 disabled:opacity-50">Пауза auto-transfer</button>
            <button onClick={() => void setGlmTonAutoTransferOverride(true)} disabled={saving || glmTonReadiness?.auto_transfer?.override?.enabled === true} className="rounded-md border border-blue-200 px-4 py-2 text-sm font-medium text-blue-700 disabled:opacity-50">Включить auto-transfer</button>
            <button onClick={() => void loadGlmTonReadiness()} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Проверить</button>
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-12">
          <Metric title="Status" value={label(glmTonReadiness?.status)} />
          <Metric title="Network" value={String(glmTonReadiness?.policy?.network || 'testnet')} />
          <Metric title="Jetton" value={label(glmTonReadiness?.artifact?.deployment_status || glmTonReadiness?.policy?.status || 'missing')} />
          <Metric title="Hot-wallet GLM" value={`${glmHotWalletBalance?.glm_balance ?? '—'}`} hint={`need ${glmHotWalletBalance?.required_glm ?? '—'} · ${label(glmHotWalletBalance?.status)}`} />
          <Metric title="Hot-wallet TON gas" value={`${glmHotWalletBalance?.ton_balance ?? '—'}`} hint={`need ${glmHotWalletBalance?.required_ton ?? '—'} · ${label(glmHotWalletBalance?.status)}`} />
          <Metric title="Hot safe GLM" value={`${glmHotWalletBalance?.safe_transfer_capacity_glm ?? '—'}`} hint={`threshold ${glmHotWalletBalance?.refill_threshold_glm ?? '—'}`} />
          <Metric title="Hot refill target" value={`${glmHotWalletBalance?.refill_target_glm ?? '—'} GLM`} hint={`${glmHotWalletBalance?.refill_target_ton ?? '—'} TON gas`} />
          <Metric title="Treasury GLM" value={`${glmTreasuryBalance?.glm_balance ?? '—'}`} hint={`need ${glmTreasuryBalance?.required_glm ?? '—'} · ${label(glmTreasuryBalance?.status)}`} />
          <Metric title="Treasury TON gas" value={`${glmTreasuryBalance?.ton_balance ?? '—'}`} hint={`need ${glmTreasuryBalance?.required_ton ?? '—'} · ${label(glmTreasuryBalance?.status)}`} />
          <Metric title="Баллы→GLM" value={`${glmTonReadiness?.pending_claims?.count || 0}`} hint={`${glmTonReadiness?.pending_claims?.amount_glm || 0} GLM`} />
          <Metric title="Б→GLM не начато" value={`${glmTonReadiness?.pending_claims?.auto_transfer_status_counts?.not_started || 0}`} />
          <Metric title="Б→GLM ждут TON" value={`${glmTonReadiness?.pending_claims?.auto_transfer_status_counts?.sent_waiting_settlement || 0}`} />
          <Metric title="Б→GLM блок" value={`${sumStatusCounts(glmTonReadiness?.pending_claims?.auto_transfer_status_counts, (status) => status.startsWith('blocked_'))}`} />
          <Metric title="Б→GLM health" value={glmTonReadiness?.pending_claims?.auto_transfer_health?.needs_attention ? 'Attention' : 'OK'} hint={`${glmTonReadiness?.pending_claims?.auto_transfer_health?.oldest_pending_age_minutes || 0} мин`} />
          <Metric title="Б→GLM нет GLM" value={`${glmTonReadiness?.pending_claims?.auto_transfer_health?.blocked_amount_glm || 0}`} hint={`${glmTonReadiness?.pending_claims?.auto_transfer_health?.waiting_settlement_amount_glm || 0} ждут TON`} />
          <Metric title="GLM→баллы" value={`${glmTonReadiness?.pending_glm_to_points?.count || 0}`} hint={`${glmTonReadiness?.pending_glm_to_points?.amount_glm || 0} GLM`} />
          <Metric title="GLM→Б ждут TON" value={`${(glmTonReadiness?.pending_glm_to_points?.deposit_status_counts?.waiting_for_deposit || 0) + (glmTonReadiness?.pending_glm_to_points?.deposit_status_counts?.not_started || 0) + (glmTonReadiness?.pending_glm_to_points?.deposit_status_counts?.wallet_request_prepared || 0)}`} />
          <Metric title="GLM→Б TON найден" value={`${glmTonReadiness?.pending_glm_to_points?.deposit_status_counts?.tx_hash_present || 0}`} />
          <Metric title="GLM→Б health" value={glmTonReadiness?.pending_glm_to_points?.health?.needs_attention ? 'Attention' : 'OK'} hint={`${glmTonReadiness?.pending_glm_to_points?.health?.oldest_pending_age_minutes || 0} мин`} />
          <Metric title="GLM→Б 1C issue" value={`${glmTonReadiness?.pending_glm_to_points?.health?.onec_issue_count || 0}`} hint={`${glmTonReadiness?.pending_glm_to_points?.health?.tx_found_amount_glm || 0} GLM tx`} />
          <Metric title="Операции" value={`${glmTonReadiness?.bridge_operations?.count || 0}`} hint={`${glmTonReadiness?.bridge_operations?.amount_glm || 0} GLM`} />
          <Metric title="Нет операции" value={`${glmTonReadiness?.bridge_operations?.missing_domain_count || 0}`} />
          <Metric title="Сверка health" value={glmTonReadiness?.bridge_operations?.health?.needs_attention ? 'Attention' : 'OK'} hint={`${glmTonReadiness?.bridge_operations?.health?.oldest_pending_age_minutes || 0} мин`} />
          <Metric title="TON/1C проблемы" value={`${glmTonReadiness?.bridge_operations?.health?.ton_waiting_count || 0}/${glmTonReadiness?.bridge_operations?.health?.onec_issue_count || 0}`} hint="TON / 1C" />
          <Metric title="Blockers" value={`${glmTonReadiness?.blockers?.length || 0}`} />
          <Metric title="Auto-transfer" value={label(glmTonReadiness?.schedulers?.ton_auto_transfer?.status || '—')} hint={glmTonReadiness?.schedulers?.ton_auto_transfer?.enabled ? 'enabled' : 'disabled'} />
          <Metric title="Settlement" value={label(glmTonReadiness?.schedulers?.ton_settlement?.status || '—')} hint={glmTonReadiness?.schedulers?.ton_settlement?.enabled ? 'enabled' : 'disabled'} />
          <Metric title="1C retry" value={label(glmTonReadiness?.schedulers?.onec_bridge_retry?.status || '—')} hint={glmTonReadiness?.schedulers?.onec_bridge_retry?.enabled ? 'включен' : 'выключен'} />
          <Metric title="Security" value={glmTonReadiness?.security?.mainnet_ready ? 'Mainnet ready' : 'Pilot only'} hint={`${(glmTonReadiness?.security?.warnings || []).length + (glmTonReadiness?.security?.mainnet_blockers || []).length} notes`} />
          <Metric title="Prod wallet" value={glmTonReadiness?.security?.production_candidate_ready ? 'Candidate' : 'Missing'} hint={label(glmTonReadiness?.security?.production_signer_mode || 'not configured')} />
          <Metric title="Prod approvals" value={glmTonReadiness?.security?.production_approvals_ready ? 'Ready' : 'Pending'} hint={`${[
            glmTonReadiness?.security?.production_legal_approved ? 'legal' : null,
            glmTonReadiness?.security?.production_security_approved ? 'security' : null,
            glmTonReadiness?.security?.production_treasury_approved ? 'treasury' : null,
          ].filter(Boolean).length}/3`} />
          <Metric title="Batch" value={`${glmTonReadiness?.schedulers?.ton_auto_transfer?.batch_limit || 0}`} hint={`${glmTonReadiness?.schedulers?.ton_auto_transfer?.interval_minutes || 0} мин`} />
          <Metric title="Mainnet" value={glmTonReadiness?.policy?.mainnet_enabled ? 'Enabled' : 'Blocked'} />
        </div>
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Hot-wallet limits</div>
              <div className="mt-1 text-sm text-slate-600">
                Сейчас доступно безопасно: {glmHotWalletBalance?.safe_transfer_capacity_glm ?? '—'} GLM · {glmHotWalletBalance?.safe_transfer_capacity_ton ?? '—'} TON gas
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => void checkTreasuryBalances()} disabled={saving} className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 disabled:opacity-60">Проверить балансы</button>
              <button onClick={() => void saveHotWalletLimits()} disabled={saving} className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 disabled:opacity-60">Сохранить лимиты</button>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              GLM минимум
              <input
                value={hotWalletLimitForm.hot_wallet_refill_glm_threshold}
                onChange={(event) => setHotWalletLimitForm((prev) => ({ ...prev, hot_wallet_refill_glm_threshold: event.target.value }))}
                className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold normal-case tracking-normal text-slate-900"
                inputMode="decimal"
              />
            </label>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              TON gas минимум
              <input
                value={hotWalletLimitForm.hot_wallet_refill_ton_threshold}
                onChange={(event) => setHotWalletLimitForm((prev) => ({ ...prev, hot_wallet_refill_ton_threshold: event.target.value }))}
                className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold normal-case tracking-normal text-slate-900"
                inputMode="decimal"
              />
            </label>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              GLM цель
              <input
                value={hotWalletLimitForm.hot_wallet_refill_glm_target}
                onChange={(event) => setHotWalletLimitForm((prev) => ({ ...prev, hot_wallet_refill_glm_target: event.target.value }))}
                className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold normal-case tracking-normal text-slate-900"
                inputMode="decimal"
              />
            </label>
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              TON gas цель
              <input
                value={hotWalletLimitForm.hot_wallet_refill_ton_target}
                onChange={(event) => setHotWalletLimitForm((prev) => ({ ...prev, hot_wallet_refill_ton_target: event.target.value }))}
                className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold normal-case tracking-normal text-slate-900"
                inputMode="decimal"
              />
            </label>
          </div>
          <div className="mt-4 rounded-md border border-slate-200 bg-white p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Операционный план пополнения</div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <span className="text-lg font-semibold text-slate-900">{label(hotWalletRefillPlan?.status || '—')}</span>
                  <Badge value={hotWalletRefillPlan?.reason || '—'} />
                </div>
                <div className="mt-1 text-sm text-slate-600">
                  {hotWalletRefillPlan?.required
                    ? `Hot-wallet ниже целевого остатка. Нужно долить: ${hotWalletRefillPlan.refill_glm_amount || 0} GLM · ${hotWalletRefillPlan.refill_ton_amount || 0} TON gas`
                    : 'Пополнение не требуется по текущим лимитам.'}
                </div>
                <div className="mt-2 text-xs leading-5 text-slate-500">
                  {hotWalletRefillPlan?.status === 'blocked'
                    ? 'Сначала пополните treasury или уменьшите целевой refill. Hot-wallet нельзя довести до цели из текущего treasury-баланса.'
                    : hotWalletRefillPlan?.status === 'ready'
                      ? 'Следующий шаг: долить указанное количество GLM/TON из treasury на hot-wallet и нажать “Проверить балансы”. Это не очередь пользовательских заявок.'
                      : 'Следующий шаг не требуется: hot-wallet выше заданных лимитов.'}
                </div>
                {hotWalletLatestAlert?.last_sent_at ? (
                  <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                    Последний Telegram alert: {dateRu(hotWalletLatestAlert.last_sent_at)} · {hotWalletLatestAlert.message || 'low-balance alert'}
                  </div>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <TonConnectButton />
                <button onClick={() => void confirmHotWalletRefillInWallet()} disabled={saving || hotWalletRefillPlan?.status !== 'ready'} className="rounded-md border border-emerald-300 px-4 py-2 text-sm font-medium text-emerald-700 disabled:opacity-60">Пополнить через TON Connect</button>
                <button onClick={() => void copyHotWalletRefillPlan()} disabled={saving || !hotWalletRefillPlan} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Скопировать план</button>
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <Metric title="Долить GLM в hot-wallet" value={`${hotWalletRefillPlan?.refill_glm_amount ?? '—'}`} hint={`целевой остаток ${hotWalletRefillPlan?.target_glm ?? '—'}`} />
              <Metric title="Долить TON gas" value={`${hotWalletRefillPlan?.refill_ton_amount ?? '—'}`} hint={`целевой остаток ${hotWalletRefillPlan?.target_ton ?? '—'}`} />
              <Metric title="Treasury GLM" value={`${hotWalletRefillPlan?.treasury_glm_balance ?? '—'}`} hint={(hotWalletRefillPlan?.errors || []).includes('treasury_glm_insufficient') ? 'недостаточно' : 'доступно'} />
              <Metric title="Treasury TON" value={`${hotWalletRefillPlan?.treasury_ton_balance ?? '—'}`} hint={(hotWalletRefillPlan?.errors || []).includes('treasury_ton_insufficient') ? 'недостаточно' : 'доступно'} />
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <div className="rounded-md border border-slate-200 p-3 text-sm text-slate-700">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Откуда отправлять</div>
                <div className="mt-2 break-all font-mono text-xs">{hotWalletRefillPlan?.source_address || '—'}</div>
                <div className="mt-2 text-xs text-slate-500">Treasury/deposit wallet GLAME</div>
                {hotWalletRefillPlan?.source_address ? (
                  <button onClick={() => void navigator.clipboard.writeText(hotWalletRefillPlan.source_address || '')} className="mt-2 rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700">Скопировать адрес</button>
                ) : null}
              </div>
              <div className="rounded-md border border-slate-200 p-3 text-sm text-slate-700">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Куда пополнить</div>
                <div className="mt-2 break-all font-mono text-xs">{hotWalletRefillPlan?.destination_address || '—'}</div>
                <div className="mt-2 text-xs text-slate-500">Hot-wallet для автоматических Баллы → GLM переводов</div>
                {hotWalletRefillPlan?.destination_address ? (
                  <button onClick={() => void navigator.clipboard.writeText(hotWalletRefillPlan.destination_address || '')} className="mt-2 rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700">Скопировать адрес</button>
                ) : null}
              </div>
            </div>
            <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs leading-5 text-slate-600">
              <div className="font-semibold text-slate-800">После перевода</div>
              <div>1. Дождаться появления TON-транзакции в кошельке.</div>
              <div>2. Нажать “Проверить балансы”.</div>
              <div>3. Если статус стал OK/готово, auto-transfer продолжит отправлять Баллы → GLM заявки автоматически.</div>
            </div>
            <div className="mt-4 rounded-md border border-slate-200 bg-white p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Записать ручное пополнение</div>
              <div className="mt-3 grid gap-2 lg:grid-cols-[0.7fr_0.7fr_1.1fr_1.3fr_auto]">
                <input
                  value={hotWalletRefillForm.manual_glm_amount}
                  onChange={(event) => setHotWalletRefillForm((prev) => ({ ...prev, manual_glm_amount: event.target.value.replace(/[^\d.]/g, '') }))}
                  placeholder="GLM отправлено"
                  inputMode="decimal"
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
                <input
                  value={hotWalletRefillForm.manual_ton_amount}
                  onChange={(event) => setHotWalletRefillForm((prev) => ({ ...prev, manual_ton_amount: event.target.value.replace(/[^\d.]/g, '') }))}
                  placeholder="TON отправлено"
                  inputMode="decimal"
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
                <input
                  value={hotWalletRefillForm.ton_tx_hash}
                  onChange={(event) => setHotWalletRefillForm((prev) => ({ ...prev, ton_tx_hash: event.target.value }))}
                  placeholder="TON tx hash"
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
                <input
                  value={hotWalletRefillForm.comment}
                  onChange={(event) => setHotWalletRefillForm((prev) => ({ ...prev, comment: event.target.value }))}
                  placeholder="Комментарий"
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
                <button onClick={() => void recordHotWalletRefill()} disabled={saving || (!hotWalletRefillForm.manual_glm_amount && !hotWalletRefillForm.manual_ton_amount && !hotWalletRefillForm.ton_tx_hash.trim())} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Записать</button>
              </div>
            </div>
            {(hotWalletRefillPlan?.errors || []).length > 0 ? (
              <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                {(hotWalletRefillPlan?.errors || []).map((item) => label(item)).join(', ')}
              </div>
            ) : null}
          </div>
          {hotWalletRefillResult && <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{hotWalletRefillResult}</div>}
          {hotWalletRefillTonResult && <div className="mt-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-800">{hotWalletRefillTonResult}</div>}
          {hotWalletLimitResult && <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{hotWalletLimitResult}</div>}
          {(glmTonReadiness?.treasury_balances?.alerts || []).length > 0 && (
            <div className="mt-3 space-y-2">
              {(glmTonReadiness?.treasury_balances?.alerts || []).map((alert) => (
                <div key={`${alert.code}-${alert.message}`} className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  <span className="font-semibold">{label(alert.code)}</span>: {alert.message}
                </div>
              ))}
            </div>
          )}
          {hotWalletRefillChecks.length > 0 ? (
            <div className="mt-4 rounded-md border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Журнал hot-wallet</div>
                  <div className="mt-1 text-sm text-slate-600">Последние проверки баланса и ручные пополнения.</div>
                </div>
                <button onClick={() => void loadHotWalletRefillChecks()} disabled={saving} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-60">Обновить</button>
              </div>
              <div className="mt-3">
                <DataTable
                  headers={['Дата', 'Тип', 'Статус', 'План', 'Факт', 'Балансы', 'Tx / комментарий']}
                  rows={hotWalletRefillChecks.slice(0, 10).map((item) => [
                    dateRu(item.created_at),
                    label(item.event_type),
                    <div key={`refill-status-${item.id}`} className="max-w-[180px]">
                      <Badge value={item.status} />
                      <div className="mt-1 text-xs text-slate-500">{label(item.reason)}</div>
                    </div>,
                    <div key={`refill-plan-${item.id}`} className="text-xs leading-5 text-slate-600">
                      <div>{item.refill_glm_amount ?? 0} GLM</div>
                      <div>{item.refill_ton_amount ?? 0} TON</div>
                    </div>,
                    <div key={`refill-manual-${item.id}`} className="text-xs leading-5 text-slate-600">
                      <div>{item.manual_glm_amount ?? 0} GLM</div>
                      <div>{item.manual_ton_amount ?? 0} TON</div>
                    </div>,
                    <div key={`refill-balances-${item.id}`} className="text-xs leading-5 text-slate-600">
                      <div>hot: {item.hot_wallet_glm_balance ?? '—'} GLM / {item.hot_wallet_ton_balance ?? '—'} TON</div>
                      <div>treasury: {item.treasury_glm_balance ?? '—'} GLM / {item.treasury_ton_balance ?? '—'} TON</div>
                    </div>,
                    <div key={`refill-comment-${item.id}`} className="max-w-[300px] break-all text-xs leading-5 text-slate-600">
                      <div>{item.ton_tx_hash || '—'}</div>
                      <div className="mt-1 text-slate-500">{item.comment || (item.errors || []).map((entry) => label(entry)).join(', ') || '—'}</div>
                    </div>,
                  ])}
                />
              </div>
            </div>
          ) : null}
        </div>
        <div className="mt-4 grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Deployment artifact</div>
            <div className="mt-3 space-y-2 text-xs text-slate-600">
              <div className="break-all">master: {glmTonReadiness?.artifact?.jetton_master_address || glmTonReadiness?.policy?.jetton_master_address || '—'}</div>
              <div className="break-all">treasury: {glmTonReadiness?.artifact?.treasury_address || glmTonReadiness?.policy?.treasury_address || '—'}</div>
              <div className="break-all">deploy tx: {glmTonReadiness?.artifact?.deploy_tx_hash || '—'}</div>
              <div className="border-t border-slate-200 pt-2">
                <div className="uppercase tracking-wide text-slate-500">Reference</div>
                <div className="mt-1 break-all">repo: {glmTonReadiness?.reference?.repo || '—'}</div>
                <div className="break-all">commit: {glmTonReadiness?.reference?.actual_commit || glmTonReadiness?.reference?.expected_commit || '—'}</div>
                <div>vendor: {glmTonReadiness?.reference?.vendor_exists ? 'ready' : 'missing'} · {glmTonReadiness?.reference?.matches_lock ? 'matches lock' : 'not verified'}</div>
              </div>
              {glmTonReadiness?.policy?.metadata_url ? <a href={glmTonReadiness.policy.metadata_url} target="_blank" rel="noreferrer" className="inline-block text-blue-700">Jetton metadata</a> : null}
            </div>
            <div className="mt-5 border-t border-slate-200 pt-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Next steps</div>
              <div className="mt-3 space-y-2 text-xs leading-5 text-slate-600">
                {(glmTonReadiness?.next_steps || []).map((step, index) => (
                  <div key={`ton-step-${index}`}>{index + 1}. {step}</div>
                ))}
                {!(glmTonReadiness?.next_steps || []).length ? <div>Нет активных шагов</div> : null}
              </div>
            </div>
            <div className="mt-5 border-t border-slate-200 pt-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Commands</div>
              <div className="mt-3 space-y-2 text-xs text-slate-600">
                {Object.entries(glmTonReadiness?.commands || {}).map(([key, command]) => (
                  <div key={key}>
                    <div className="uppercase tracking-wide text-slate-500">{key}</div>
                    <div className="mt-1 break-all rounded border border-slate-200 bg-white p-2 font-mono">{command}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DataTable
            headers={['Check', 'Status', 'Message']}
            rows={(glmTonReadiness?.checks || []).map((item) => [
              item.code,
              <Badge key={`ton-check-${item.code}`} value={item.ok ? 'processed' : 'pending'} />,
              <div key={`ton-message-${item.code}`} className="max-w-[420px] text-xs leading-5 text-slate-600">{item.message}</div>,
            ])}
          />
        </div>
        {(glmTonReadiness?.alerts || []).length ? (
          <div className="mt-4">
            <DataTable
              headers={['Alert', 'Status', 'Message']}
              rows={(glmTonReadiness?.alerts || []).map((item) => [
                item.code,
                <Badge key={`readiness-alert-${item.code}`} value={item.severity === 'critical' ? 'failed' : item.severity === 'warning' ? 'pending' : 'processed'} />,
                <div key={`readiness-alert-message-${item.code}`} className="max-w-[680px] text-xs leading-5 text-slate-600">{item.message}</div>,
              ])}
            />
          </div>
        ) : null}
        {((glmTonReadiness?.security?.warnings || []).length || (glmTonReadiness?.security?.mainnet_blockers || []).length) ? (
          <div className="mt-4">
            <DataTable
              headers={['Security', 'Status', 'Message']}
              rows={[
                ...(glmTonReadiness?.security?.warnings || []).map((item) => [
                  item.code,
                  <Badge key={`security-warning-${item.code}`} value={item.severity === 'blocker' ? 'failed' : 'pending'} />,
                  <div key={`security-warning-message-${item.code}`} className="max-w-[680px] text-xs leading-5 text-slate-600">{item.message}</div>,
                ]),
                ...(glmTonReadiness?.security?.mainnet_blockers || []).map((item) => [
                  item.code,
                  <Badge key={`security-blocker-${item.code}`} value="failed" />,
                  <div key={`security-blocker-message-${item.code}`} className="max-w-[680px] text-xs leading-5 text-slate-600">{item.message}</div>,
                ]),
              ]}
            />
          </div>
        ) : null}
        {(glmTonReadiness?.pending_claims?.sample || []).length ? (
          <div className="mt-4">
            <DataTable
              headers={['Заявка Баллы→GLM', 'GLM', '1С', 'TON', 'Tx hash']}
              rows={(glmTonReadiness?.pending_claims?.sample || []).map((item) => [
                <div key={`claim-${item.id}`} className="max-w-[220px] break-all text-xs">{item.id}</div>,
                `${item.amount_glm || 0}`,
                label(item.onec_spend_sync_status),
                label(item.auto_transfer_status),
                item.tx_hash ? <div key={`hash-${item.id}`} className="max-w-[260px] break-all text-xs">{item.tx_hash}</div> : '—',
              ])}
            />
          </div>
        ) : null}
        {(glmTonReadiness?.pending_glm_to_points?.sample || []).length ? (
          <div className="mt-4">
            <DataTable
              headers={['Заявка GLM→баллы', 'GLM', 'Баллы', 'TON', '1C']}
              rows={(glmTonReadiness?.pending_glm_to_points?.sample || []).map((item) => [
                <div key={`bridge-${item.id}`} className="max-w-[220px] break-all text-xs">{item.id}</div>,
                `${item.amount_glm || 0}`,
                `${item.target_points || item.amount_glm || 0}`,
                <div key={`deposit-${item.id}`} className="max-w-[260px] break-all text-xs">
                  <div>{label(item.ton_deposit_status || item.last_lookup_status)}</div>
                  {item.deposit_tx_hash ? <div className="mt-1 text-slate-500">{item.deposit_tx_hash}</div> : null}
                </div>,
                label(item.onec_sync_status),
              ])}
            />
          </div>
        ) : null}
      </section>

      <section id="glm-claims" className="rounded-md border border-slate-200 bg-white p-5 shadow-sm scroll-mt-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">CryptoGLAME</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Очередь Баллы → GLM в TON</div>
          </div>
          <div className="grid gap-2 sm:grid-cols-[0.7fr_1fr_1fr_auto_auto]">
            <select value={glmClaimStatus} onChange={(event) => setGlmClaimStatus(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="pending">Ожидают</option>
              <option value="processed">Обработаны</option>
              <option value="failed">Ошибка</option>
              <option value="canceled">Отменены</option>
            </select>
            <input value={glmClaimTxHash} onChange={(event) => setGlmClaimTxHash(event.target.value)} placeholder="TON tx hash" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input value={glmClaimComment} onChange={(event) => setGlmClaimComment(event.target.value)} placeholder="Комментарий" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <a href={`/api/referrals/admin/glm-claims/ton-operator.csv?status=${glmClaimStatus || 'pending'}&limit=1000`} className="inline-flex items-center justify-center rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700">TON CSV</a>
            <button onClick={() => void loadGlmClaims()} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Обновить</button>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500">Баллы уже списаны в 1С, дальше GLM отправляются из hot-wallet в подтвержденный TON-кошелек партнера.</p>
        <div className="mt-4">
          <DataTable
            headers={['Партнер', 'Сумма', 'Кошелек', 'Статус', 'Создана', 'Tx hash', 'Действия']}
            rows={glmClaims.map((claim) => {
              const stage = pointsToGlmStage(claim);
              return [
                <div key={`partner-${claim.id}`}>
                  <div className="font-medium text-slate-900">{claim.partner_name || 'Партнер GLAME'}</div>
                  <div className="mt-1 text-xs text-slate-500">{claim.partner_phone || '—'} · {claim.wallet_app || 'TON wallet'}</div>
                </div>,
                `${claim.amount} GLM`,
                <div key={`wallet-${claim.id}`} className="max-w-[260px] break-all text-xs">{claim.wallet_address || '—'}</div>,
                <div key={`status-${claim.id}`} className="max-w-[220px]">
                  <Badge value={stage.value} />
                  <div className="mt-1 text-xs text-slate-500">{stage.label}</div>
                  <div className="mt-1 text-xs text-slate-400">{stage.detail}</div>
                </div>,
                dateRu(claim.created_at),
                claim.tx_hash ? <div key={`tx-${claim.id}`} className="max-w-[220px] break-all text-xs">{claim.tx_hash}</div> : '—',
                <div key={`actions-${claim.id}`} className="flex flex-wrap gap-2">
                  <button disabled={saving || claim.status !== 'pending' || !glmClaimTxHash.trim()} onClick={() => void updateGlmClaim(claim.id, 'processed', claim.bridge_operation_id)} className="rounded border border-emerald-200 px-3 py-2 text-xs font-medium text-emerald-700 disabled:opacity-50">Подтвердить TON</button>
                  <button disabled={saving || claim.status !== 'pending'} onClick={() => void updateGlmClaim(claim.id, 'failed', claim.bridge_operation_id)} className="rounded border border-red-200 px-3 py-2 text-xs font-medium text-red-700 disabled:opacity-50">Ошибка</button>
                  <button disabled={saving || claim.status !== 'pending'} onClick={() => void updateGlmClaim(claim.id, 'canceled', claim.bridge_operation_id)} className="rounded border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-50">Отменить</button>
                </div>,
              ];
            })}
          />
        </div>
      </section>

      <section id="glm-to-points" className="rounded-md border border-slate-200 bg-white p-5 shadow-sm scroll-mt-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">CryptoGLAME</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Очередь GLM -&gt; баллы 1С</div>
          </div>
          <div className="grid gap-2 sm:grid-cols-[0.75fr_0.75fr_1fr_1fr_auto]">
            <select value={glmToPointsStatus} onChange={(event) => setGlmToPointsStatus(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="pending">Ожидают</option>
              <option value="processed">Обработаны</option>
              <option value="failed">Ошибка</option>
              <option value="canceled">Отменены</option>
            </select>
            <input value={glmToPointsValue} onChange={(event) => setGlmToPointsValue(event.target.value.replace(/[^\d]/g, ''))} placeholder="Баллы" inputMode="numeric" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input value={glmToPointsDocument} onChange={(event) => setGlmToPointsDocument(event.target.value)} placeholder="Документ 1С" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input value={glmToPointsComment} onChange={(event) => setGlmToPointsComment(event.target.value)} placeholder="Комментарий" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <button onClick={() => { void loadGlmToPointsBridges(); void loadGlmBridgeReconciliation(); }} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Обновить</button>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Партнер отправляет GLM из подтвержденного TON-кошелька в GLAME. После проверки TON-перевода платформа начисляет баллы в 1С.
        </p>
        <div className="mt-4">
          <DataTable
            headers={['Партнер', 'GLM', 'Баллы', 'TON-перевод', 'Статус', 'Документ / комментарий', 'Действия']}
            rows={glmToPointsBridges.map((item) => {
              const stage = glmToPointsStage(item);
              return [
                <div key={`partner-${item.id}`}>
                  <div className="font-medium text-slate-900">{item.partner_name || 'Партнер GLAME'}</div>
                  <div className="mt-1 text-xs text-slate-500">{item.partner_phone || '—'}</div>
                </div>,
                `${Math.abs(item.amount || 0)} GLM`,
                <div key={`points-${item.id}`} className="text-sm text-slate-700">
                  <div>{item.processed_points || item.target_points || Math.abs(item.amount || 0)} баллов</div>
                  <div className="mt-1 text-xs text-slate-500">{label(item.reason)}</div>
                  {item.refunded_glm ? <div className="mt-1 text-xs text-slate-500">возврат {item.refunded_glm} GLM</div> : null}
                </div>,
                <div key={`deposit-${item.id}`} className="max-w-[300px] text-xs leading-5 text-slate-600">
                  <div className="break-all">от: {item.expected_ton_sender_address || '—'}</div>
                  <div className="break-all">GLAME: {item.treasury_address || '—'}</div>
                  {item.deposit_tx_hash ? <div className="break-all text-emerald-700">TON tx: {item.deposit_tx_hash}</div> : null}
                  {item.ton_deposit_verification?.verified ? <div className="text-emerald-700">TON проверен</div> : null}
                </div>,
                <div key={`status-${item.id}`} className="max-w-[220px]">
                  <Badge value={stage.value} />
                  <div className="mt-1 text-xs text-slate-500">{stage.label}</div>
                  <div className="mt-1 text-xs text-slate-400">{stage.detail}</div>
                </div>,
                <div key={`doc-${item.id}`} className="max-w-[260px]">
                  <div className="text-xs text-slate-500">создана: {dateRu(item.created_at)}</div>
                  <div className="break-all text-xs text-slate-600">{item.onec_document_id || item.source_id || '—'}</div>
                  <div className="mt-1 text-xs text-slate-500">{item.admin_comment || item.description || '—'}</div>
                  {item.onec_sync_status ? <div className="mt-1 text-xs text-slate-500">1С: {label(item.onec_sync_status)}</div> : null}
                  {item.onec_sync_error ? <div className="mt-1 text-xs text-red-600">{item.onec_sync_error}</div> : null}
                  {item.loyalty_points_expires_at ? <div className="mt-1 text-xs text-slate-500">баллы до {dateRu(item.loyalty_points_expires_at)}</div> : null}
                </div>,
                <div key={`actions-${item.id}`} className="flex max-w-[260px] flex-wrap gap-2">
                  <input
                    value={glmToPointsDepositHashes[item.id] || ''}
                    onChange={(event) => setGlmToPointsDepositHashes((current) => ({ ...current, [item.id]: event.target.value }))}
                    placeholder="TON tx hash"
                    className="w-full rounded border border-slate-300 px-3 py-2 text-xs"
                  />
                  <button disabled={saving || item.status !== 'pending' || !(glmToPointsDepositHashes[item.id] || '').trim()} onClick={() => void settleGlmToPointsBridgeDeposit(item.id, item.bridge_operation_id)} className="rounded border border-emerald-200 px-3 py-2 text-xs font-medium text-emerald-700 disabled:opacity-50">Проверить TON</button>
                  <button disabled={saving || item.status !== 'pending'} onClick={() => void updateGlmToPointsBridge(item.id, 'processed', item.bridge_operation_id)} className="rounded border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-50">Начислено</button>
                  <button disabled={saving || item.status !== 'pending'} onClick={() => void updateGlmToPointsBridge(item.id, 'failed', item.bridge_operation_id)} className="rounded border border-red-200 px-3 py-2 text-xs font-medium text-red-700 disabled:opacity-50">Ошибка</button>
                  <button disabled={saving || item.status !== 'pending'} onClick={() => void updateGlmToPointsBridge(item.id, 'canceled', item.bridge_operation_id)} className="rounded border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-50">Отменить</button>
                  <button disabled={saving || item.status !== 'processed'} onClick={() => void repairGlmBridge(item.id, 'retry_onec', item.bridge_operation_id)} className="rounded border border-blue-200 px-3 py-2 text-xs font-medium text-blue-700 disabled:opacity-50">Повторить 1С</button>
                  <button disabled={saving || item.status !== 'processed' || !glmToPointsDocument.trim()} onClick={() => void repairGlmBridge(item.id, 'record_manual_document', item.bridge_operation_id)} className="rounded border border-amber-200 px-3 py-2 text-xs font-medium text-amber-700 disabled:opacity-50">Внести документ</button>
                </div>,
              ];
            })}
          />
        </div>
      </section>

      <section id="glm-bridge-reconciliation" className="rounded-md border border-slate-200 bg-white p-5 shadow-sm scroll-mt-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">CryptoGLAME</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Сверка TON-переводов и 1С</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href="/api/referrals/admin/glm-bridge/reconciliation.csv?stale_hours=48&limit=500" className="inline-flex items-center justify-center rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700">CSV</a>
            <button onClick={() => { void loadGlmBridgeOperations(); void loadGlmBridgeReconciliation(); void loadGlmLoyaltyReconciliation(); }} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Пересчитать</button>
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-12">
          <Metric title="Проверено операций" value={`${glmBridgeReconciliation?.checked_bridge_operations ?? 0}`} hint={`${glmBridgeReconciliation?.bridge_operations_total ?? 0} всего`} />
          <Metric title="Нет записи операции" value={`${glmBridgeReconciliation?.bridge_operations_missing_domain_count ?? 0}`} hint={label(glmBridgeReconciliation?.bridge_operations_source || 'internal')} />
          <Metric title="Проблемы операций" value={`${glmBridgeReconciliation?.bridge_operations_consistency_issue_count ?? 0}`} hint={`${glmBridgeReconciliation?.bridge_operations_stale_pending_count || 0} зависли`} />
          <Metric title="Проверено ledger" value={`${glmBridgeReconciliation?.checked_total_transactions ?? glmBridgeReconciliation?.checked_bridge_transactions ?? 0}`} hint={`${glmBridgeReconciliation?.checked_points_to_glm_transactions || 0} Баллы→GLM`} />
          <Metric title="GLM→баллы ждут" value={`${glmBridgeReconciliation?.pending_count || 0}`} hint={`${glmBridgeReconciliation?.pending_reserved_glm || 0} GLM`} />
          <Metric title="GLM→баллы готово" value={`${glmBridgeReconciliation?.processed_count || 0}`} hint={`${glmBridgeReconciliation?.processed_points || 0} баллов`} />
          <Metric title="Баллы→GLM ждут" value={`${glmBridgeReconciliation?.points_to_glm_pending_count || 0}`} />
          <Metric title="Баллы→GLM готово" value={`${glmBridgeReconciliation?.points_to_glm_processed_count || 0}`} />
          <Metric title="Баллы→GLM отменено" value={`${glmBridgeReconciliation?.points_to_glm_canceled_count || 0}`} />
          <Metric title="Ждет TON" value={`${glmBridgeReconciliation?.ton_sent_waiting_count || 0}`} />
          <Metric title="Проблемы 1С" value={`${(glmBridgeReconciliation?.onec_failed_count || 0) + (glmBridgeReconciliation?.onec_spend_failed_count || 0) + (glmBridgeReconciliation?.onec_cancel_spend_failed_count || 0)}`} />
          <Metric title="Нет TON tx" value={`${glmBridgeReconciliation?.ton_processed_without_tx_count || 0}`} />
          <Metric title="Всего проблем" value={`${glmBridgeReconciliation?.issues_count || 0}`} hint={glmBridgeReconciliation?.generated_at ? dateRu(glmBridgeReconciliation.generated_at) : undefined} />
        </div>
        <div className="mt-6 rounded-md border border-slate-200 p-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">1С bonus reconciliation</div>
              <div className="mt-1 text-sm text-slate-600">
                Платформа vs 1С к списанию vs начисленные лоты формы карты.
              </div>
            </div>
            <div className="grid gap-2 text-xs text-slate-500 sm:grid-cols-3">
              <div>Проверено: <span className="font-semibold text-slate-900">{glmLoyaltyReconciliation?.checked ?? 0}</span></div>
              <div>Строк: <span className="font-semibold text-slate-900">{glmLoyaltyReconciliation?.count ?? 0}</span></div>
              <div>Проблем: <span className="font-semibold text-slate-900">{glmLoyaltyReconciliation?.issues_count ?? 0}</span></div>
            </div>
          </div>
          <div className="mt-4">
            <DataTable
              headers={['Статус', 'Партнер', 'Платформа', '1С к списанию', '1С лоты', 'Δ платформа/1С', 'Δ к списанию/лоты', 'Комментарий']}
              rows={(glmLoyaltyReconciliation?.items || []).slice(0, 20).map((item) => [
                <Badge key={`loyalty-status-${item.member_id}`} value={item.status === 'ok' ? 'processed' : item.status === 'warning' ? 'pending' : 'failed'} />,
                <div key={`loyalty-partner-${item.member_id}`}>
                  <div className="font-medium text-slate-900">{item.partner_name || 'Партнер GLAME'}</div>
                  <div className="mt-1 text-xs text-slate-500">{item.partner_phone || item.discount_card_number || '—'}</div>
                </div>,
                `${item.platform_points ?? 0}`,
                item.onec_working_balance ?? '—',
                item.onec_lots_balance ?? '—',
                item.platform_vs_working_delta ?? '—',
                item.working_vs_lots_delta ?? '—',
                <div key={`loyalty-note-${item.member_id}`} className="max-w-[360px] text-xs leading-5 text-slate-600">
                  {item.errors?.length ? item.errors.join('; ') : item.status === 'ok' ? 'Остатки совпадают' : item.status === 'warning' ? 'Диагностика: лоты 1С отличаются от рабочего остатка, repair отключен' : 'Платформа отличается от 1С'}
                </div>,
              ])}
            />
          </div>
        </div>
        <div className="mt-4">
          <DataTable
            headers={['Направление', 'Этап', 'Партнер', 'GLM', 'Баллы', 'TON', '1С', 'Операция']}
            rows={(glmBridgeOperations || []).slice(0, 20).map((item) => {
              const stage = item.direction === 'glm_to_points' ? glmToPointsStage(item) : pointsToGlmStage(item);
              return [
                bridgeDirectionLabel(item.direction),
                <div key={`bridge-op-status-${item.id}`} className="max-w-[220px]">
                  <Badge value={stage.value} />
                  <div className="mt-1 text-xs text-slate-500">{stage.label}</div>
                  <div className="mt-1 text-xs text-slate-400">{stage.detail}</div>
                </div>,
                <div key={`bridge-op-partner-${item.id}`}>
                  <div className="font-medium text-slate-900">{item.partner_name || 'Партнер GLAME'}</div>
                  <div className="mt-1 text-xs text-slate-500">{item.partner_phone || '—'}</div>
                </div>,
                `${item.glm_amount || 0}`,
                `${item.points_amount || 0}`,
                <div key={`bridge-op-ton-${item.id}`} className="max-w-[260px] break-all text-xs">
                  <div>{label(item.ton_status)}</div>
                  {item.ton_tx_hash ? <div className="mt-1 text-slate-500">{item.ton_tx_hash}</div> : null}
                </div>,
                <div key={`bridge-op-onec-${item.id}`} className="max-w-[220px] break-all text-xs">
                  <div>{label(item.onec_status)}</div>
                  {item.onec_document_id ? <div className="mt-1 text-slate-500">{item.onec_document_id}</div> : null}
                </div>,
                <div key={`bridge-op-id-${item.id}`} className="max-w-[220px] break-all text-xs">
                  <div>{item.id}</div>
                  <div className="mt-1 text-slate-500">{dateRu(item.updated_at || item.created_at)}</div>
                </div>,
              ];
            })}
          />
        </div>
        <div className="mt-4">
          <DataTable
            headers={['Важность', 'Операция', 'Проблема', 'ID операции', 'Транзакция', 'Документ 1С', 'TON', 'Сообщение', 'Действие']}
            rows={(glmBridgeReconciliation?.issues || []).map((item, index) => [
              <Badge key={`severity-${index}`} value={item.severity === 'error' ? 'failed' : item.severity === 'warn' ? 'pending' : 'processed'} />,
              bridgeDirectionLabel(item.operation),
              label(item.code),
              item.bridge_operation_id ? <div key={`op-${index}`} className="max-w-[180px] break-all text-xs">{item.bridge_operation_id}</div> : '—',
              item.transaction_id ? <div key={`tx-${index}`} className="max-w-[220px] break-all text-xs">{item.transaction_id}</div> : '—',
              item.onec_document_id ? <div key={`onec-${index}`} className="max-w-[180px] break-all text-xs">{item.onec_document_id}</div> : '—',
              <div key={`ton-${index}`} className="max-w-[220px] break-all text-xs">
                <div>{label(item.ton_status)}</div>
                {item.ton_tx_hash ? <div className="mt-1 text-slate-500">{item.ton_tx_hash}</div> : null}
              </div>,
              <div key={`msg-${index}`} className="max-w-[420px] text-xs leading-5 text-slate-600">{item.message}</div>,
              item.transaction_id ? (
                <div key={`action-${index}`} className="flex max-w-[300px] flex-wrap gap-2">
                  {item.code === 'ton_sent_waiting_settlement' ? (
                    <button
                      disabled={saving}
                      onClick={() => void runGlmBridgeIssueAction(item.transaction_id!, 'settle_ton_transfer', item.code, item.bridge_operation_id)}
                      className="rounded border border-emerald-200 px-3 py-2 text-xs font-medium text-emerald-700 disabled:opacity-50"
                    >
                      Проверить TON
                    </button>
                  ) : null}
                  {item.code === 'closed_points_to_glm_without_1c_spend_unpost' ? (
                    <button
                      disabled={saving}
                      onClick={() => void runGlmBridgeIssueAction(item.transaction_id!, 'cancel_onec_spend', item.code, item.bridge_operation_id)}
                      className="rounded border border-red-200 px-3 py-2 text-xs font-medium text-red-700 disabled:opacity-50"
                    >
                      Отменить списание 1С
                    </button>
                  ) : null}
                  {item.code === 'processed_points_to_glm_without_1c_spend' ? (
                    <button
                      disabled={saving}
                      onClick={() => void runGlmBridgeIssueAction(item.transaction_id!, 'mark_legacy_manual', item.code, item.bridge_operation_id)}
                      className="rounded border border-amber-200 px-3 py-2 text-xs font-medium text-amber-700 disabled:opacity-50"
                    >
                      Закрыть как проверенное
                    </button>
                  ) : null}
                  {item.code.startsWith('onec_spend_') ? (
                    <>
                      <button
                        disabled={saving}
                        onClick={() => void repairPointsToGlmSpend(item.transaction_id!, 'retry_onec_spend', item.bridge_operation_id)}
                        className="rounded border border-blue-200 px-3 py-2 text-xs font-medium text-blue-700 disabled:opacity-50"
                      >
                        Повторить 1С
                      </button>
                      <button
                        disabled={saving || !glmToPointsDocument.trim()}
                        onClick={() => void repairPointsToGlmSpend(item.transaction_id!, 'record_manual_spend_document', item.bridge_operation_id)}
                        className="rounded border border-amber-200 px-3 py-2 text-xs font-medium text-amber-700 disabled:opacity-50"
                      >
                        Внести списание 1С
                      </button>
                    </>
                  ) : null}
                  <button
                    disabled={saving}
                    onClick={() => void runGlmBridgeIssueAction(item.transaction_id!, 'mark_reviewed', item.code, item.bridge_operation_id)}
                    className="rounded border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-50"
                  >
                    Проверено
                  </button>
                </div>
              ) : '—',
            ])}
          />
        </div>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">GLM Audit Hash</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Ежедневный hash GLM ledger</div>
          </div>
          <div className="grid gap-2 sm:grid-cols-[0.8fr_auto_auto_auto]">
            <input type="date" value={glmAuditDate} onChange={(event) => setGlmAuditDate(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <button onClick={() => void generateGlmAuditHash()} disabled={saving || !glmAuditDate} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">Сформировать</button>
            <button onClick={() => void publishGlmAuditHash()} disabled={saving || !glmAuditDate} className="rounded-md border border-emerald-300 px-4 py-2 text-sm font-medium text-emerald-700 disabled:opacity-60">Опубликовать</button>
            <button onClick={() => void loadGlmAuditHashes()} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Обновить</button>
          </div>
        </div>
        {glmAuditResult ? <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{glmAuditResult}</div> : null}
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <a href="/api/referrals/glm-audit-hashes/public" target="_blank" rel="noreferrer" className="rounded border border-slate-300 px-3 py-2 text-slate-700">Public API</a>
          <a href="/static/glm_audit_journal/index.json" target="_blank" rel="noreferrer" className="rounded border border-slate-300 px-3 py-2 text-slate-700">Journal JSON</a>
          <a href="/static/glm_audit_journal/glame-audit-hashes.jsonl" target="_blank" rel="noreferrer" className="rounded border border-slate-300 px-3 py-2 text-slate-700">Journal JSONL</a>
        </div>
        <div className="mt-4">
          <DataTable
            headers={['Дата', 'Root hash', 'Previous', 'Tx', 'Accounts', 'Totals', 'Статус', 'Public']}
            rows={glmAuditHashes.map((item) => [
              dateRu(item.audit_date),
              <div key={`root-${item.id}`} className="max-w-[280px] break-all font-mono text-xs">{item.root_hash}</div>,
              item.previous_root_hash ? <div key={`prev-${item.id}`} className="max-w-[180px] break-all font-mono text-xs">{item.previous_root_hash}</div> : '—',
              item.transactions_count,
              item.accounts_count,
              <div key={`totals-${item.id}`} className="text-xs leading-5 text-slate-600">
                <div>balance: {item.balance_total} GLM</div>
                <div>hold: {item.hold_total} GLM</div>
                <div>earned: {item.lifetime_earned_total} GLM</div>
                <div>burned: {item.lifetime_burned_total} GLM</div>
              </div>,
              <Badge key={`status-${item.id}`} value={item.public_status} />,
              item.public_reference ? <a key={`public-${item.id}`} href={item.public_reference} target="_blank" rel="noreferrer" className="text-xs font-medium text-blue-700">Открыть</a> : '—',
            ])}
          />
        </div>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">GLM Store</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Очередь выдачи товаров и сервисов</div>
          </div>
          <div className="grid gap-2 sm:grid-cols-[0.8fr_1fr_auto]">
            <select value={glmRedemptionStatus} onChange={(event) => setGlmRedemptionStatus(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="pending_ton_payment">Ждет TON-оплату</option>
              <option value="pending_fulfillment">На сборке</option>
              <option value="fulfilled">Выдано</option>
              <option value="failed">Ошибка</option>
              <option value="canceled">Отменено</option>
            </select>
            <input value={glmFulfillmentComment} onChange={(event) => setGlmFulfillmentComment(event.target.value)} placeholder="Комментарий выдачи" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <button onClick={() => void loadGlmRedemptions()} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Обновить</button>
          </div>
        </div>
        <div className="mt-4">
          <DataTable
            headers={['Партнер', 'Товар', 'Сумма', 'Статус', 'Создан', 'Комментарий', 'Действия']}
            rows={glmRedemptions.map((item) => [
              <div key={`partner-${item.id}`}>
                <div className="font-medium text-slate-900">{item.partner_name || 'Партнер GLAME'}</div>
                <div className="mt-1 text-xs text-slate-500">{item.partner_phone || '—'}</div>
              </div>,
              <div key={`item-${item.id}`}>
                <div className="font-medium text-slate-900">{item.item_title || item.sku || 'GLM Store item'}</div>
                <div className="mt-1 break-all text-xs text-slate-500">{item.sku || '—'}</div>
              </div>,
              item.payment_method === 'loyalty_points'
                ? `${item.price_points || 0} баллов`
                : `${Math.abs(item.amount || item.price_glm || 0)} GLM`,
              <Badge key={`status-${item.id}`} value={item.status} />,
              dateRu(item.created_at),
              item.ton_refund_required
                ? 'Нужен ручной TON refund из treasury'
                : item.admin_comment || item.delivery_note || item.ton_deposit_status || item.onec_spend_sync_error || item.onec_spend_sync_status || '—',
              <div key={`actions-${item.id}`} className="flex flex-wrap gap-2">
                <button disabled={saving || item.status !== 'pending_fulfillment'} onClick={() => void updateGlmRedemption(item.id, 'fulfilled')} className="rounded border border-emerald-200 px-3 py-2 text-xs font-medium text-emerald-700 disabled:opacity-50">Исполнено</button>
                <button disabled={saving || item.status !== 'pending_fulfillment'} onClick={() => void updateGlmRedemption(item.id, 'canceled')} className="rounded border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-50">{item.payment_method === 'ton_glm' ? 'Отмена' : 'Отмена + возврат'}</button>
                <button disabled={saving || item.status !== 'pending_fulfillment'} onClick={() => void updateGlmRedemption(item.id, 'failed')} className="rounded border border-red-200 px-3 py-2 text-xs font-medium text-red-700 disabled:opacity-50">{item.payment_method === 'ton_glm' ? 'Ошибка' : 'Ошибка + возврат'}</button>
              </div>,
            ])}
          />
        </div>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">GLM AI segments</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Готовые аудитории для CRM-кампаний</div>
          </div>
          <button onClick={() => void loadGlmSegments()} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Обновить</button>
        </div>
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          {glmSegments.map((segment) => (
            <div key={segment.code} className="rounded-md border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slate-900">{segment.title}</div>
                  <div className="mt-1 text-xs leading-5 text-slate-500">{segment.description}</div>
                </div>
                <div className="rounded border border-slate-200 bg-white px-3 py-1 text-sm font-semibold text-slate-700">{segment.count}</div>
              </div>
              <div className="mt-3 space-y-2">
                {(segment.items || []).slice(0, 5).map((item) => (
                  <div key={`${segment.code}-${item.member_id}`} className="rounded border border-slate-200 bg-white p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-slate-900">{item.partner_name || 'Партнер GLAME'}</div>
                        <div className="mt-1 text-xs text-slate-500">{item.partner_phone || '—'}</div>
                      </div>
                      <div className="text-right text-xs text-slate-600">
                        <div>{item.balance} GLM</div>
                        <div className="mt-1 text-slate-400">{item.tier || 'GLM Start'}{item.to_next ? ` · ${item.to_next} до next` : ''}</div>
                      </div>
                    </div>
                  </div>
                ))}
                {!(segment.items || []).length ? <div className="text-sm text-slate-500">Аудитория пока пустая</div> : null}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">Reward Store</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Товары за бонусы и GLM</div>
            <div className="mt-1 text-sm text-slate-500">Добавление, цена в баллах/GLM, статус витрины и архив.</div>
          </div>
          <button onClick={resetRewardStoreForm} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Новый товар</button>
        </div>

        <div className="mt-4 grid gap-3 xl:grid-cols-12">
          <input value={rewardStoreForm.sku} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, sku: event.target.value }))} placeholder="SKU" className="rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-2" />
          <input value={rewardStoreForm.title} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, title: event.target.value }))} placeholder="Название" className="rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-3" />
          <select value={rewardStoreForm.category} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, category: event.target.value }))} className="rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-2">
            <option value="branded_goods">Товар</option>
            <option value="limited_goods">Лимитка</option>
            <option value="service">Сервис</option>
            <option value="access_pass">Доступ</option>
            <option value="other">Другое</option>
          </select>
          <select value={rewardStoreForm.status} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, status: event.target.value, is_active: event.target.value !== 'archived' }))} className="rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-2">
            <option value="available">Доступен</option>
            <option value="limited">Лимитирован</option>
            <option value="draft">Черновик</option>
            <option value="sold_out">Нет в наличии</option>
            <option value="archived">Архив</option>
          </select>
          <input value={rewardStoreForm.price_glm} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, price_glm: event.target.value.replace(/\D/g, '') }))} placeholder="Цена GLM" className="rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-1" />
          <input value={rewardStoreForm.price_points} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, price_points: event.target.value.replace(/\D/g, '') }))} placeholder="Баллы" className="rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-1" />
          <input value={rewardStoreForm.quantity_available} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, quantity_available: event.target.value.replace(/\D/g, '') }))} placeholder="Остаток, шт." className="rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-1" />
          <input value={rewardStoreForm.sort_order} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, sort_order: event.target.value.replace(/\D/g, '') }))} placeholder="Сорт." className="rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-1" />
          <textarea value={rewardStoreForm.description} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, description: event.target.value }))} placeholder="Описание" className="min-h-20 rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-7" />
          <input value={rewardStoreForm.inventory_status} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, inventory_status: event.target.value }))} placeholder="Метка: pilot_batch / limited / service" className="rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-2" />
          <label className="flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 xl:col-span-1">
            <input type="checkbox" checked={rewardStoreForm.is_active} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, is_active: event.target.checked }))} />
            Активен
          </label>
          <button onClick={() => void saveRewardStoreItem()} disabled={saving || !rewardStoreForm.sku.trim() || !rewardStoreForm.title.trim()} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60 xl:col-span-1">
            {rewardStoreEditingId ? 'Сохранить' : 'Добавить'}
          </button>
          <input value={rewardStoreForm.image_url} onChange={(event) => setRewardStoreForm((prev) => ({ ...prev, image_url: event.target.value }))} placeholder="URL фото" className="rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-5" />
          <input id="reward-store-image-file" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setRewardStoreImageFile(event.target.files?.[0] || null)} className="rounded-md border border-slate-300 px-3 py-2 text-sm xl:col-span-4" />
          <button onClick={() => void uploadRewardStoreImage()} disabled={saving || !rewardStoreImageFile} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60 xl:col-span-2">
            Загрузить фото
          </button>
          {rewardStoreForm.image_url ? (
            <div className="flex items-center gap-3 rounded-md border border-slate-200 bg-slate-50 p-2 xl:col-span-1">
              <img src={rewardStoreForm.image_url} alt="" className="h-12 w-12 rounded object-cover" />
            </div>
          ) : null}
        </div>
        {rewardStoreResult ? <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{rewardStoreResult}</div> : null}

        <div className="mt-4">
          <DataTable
            headers={['Товар', 'SKU', 'Цена', 'Категория', 'Остаток', 'Статус', 'Сорт.', 'Действия']}
            rows={rewardStoreItems.map((item) => [
              <div key={`title-${item.id}`} className="max-w-[320px]">
                <div className="flex items-start gap-3">
                  {item.image_url ? <img src={item.image_url} alt="" className="h-14 w-14 rounded border border-slate-200 object-cover" /> : null}
                  <div>
                    <div className="font-medium text-slate-900">{item.title}</div>
                    <div className="mt-1 line-clamp-2 text-xs text-slate-500">{item.description || '—'}</div>
                  </div>
                </div>
              </div>,
              item.sku,
              <div key={`price-${item.id}`} className="text-sm">
                <div>{item.price_glm ? `${item.price_glm} GLM` : 'GLM —'}</div>
                <div className="mt-1 text-xs text-slate-500">{item.price_points ? `${item.price_points} баллов` : 'Баллы —'}</div>
              </div>,
              <div key={`cat-${item.id}`} className="text-sm">
                <div>{item.category}</div>
                <div className="mt-1 text-xs text-slate-500">{item.inventory_status}</div>
              </div>,
              item.quantity_available === null || item.quantity_available === undefined ? '—' : `${item.quantity_available} шт.`,
              <Badge key={`status-${item.id}`} value={item.is_active ? item.status : 'archived'} />,
              item.sort_order,
              <div key={`actions-${item.id}`} className="flex flex-wrap gap-2">
                <button onClick={() => editRewardStoreItem(item)} disabled={saving} className="rounded border border-slate-300 px-3 py-1 text-xs text-slate-700 disabled:opacity-60">Изменить</button>
                {item.is_active ? (
                  <button onClick={() => void setRewardStoreItemArchived(item, true)} disabled={saving} className="rounded border border-amber-300 px-3 py-1 text-xs text-amber-700 disabled:opacity-60">Архив</button>
                ) : (
                  <button onClick={() => void setRewardStoreItemArchived(item, false)} disabled={saving} className="rounded border border-emerald-300 px-3 py-1 text-xs text-emerald-700 disabled:opacity-60">Вернуть</button>
                )}
              </div>,
            ])}
          />
        </div>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-slate-500">GLM Ledger</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">Журнал и выпуск истекшего hold</div>
          </div>
          <div className="grid gap-2 sm:grid-cols-[0.8fr_0.8fr_auto_auto]">
            <select value={glmTxType} onChange={(event) => setGlmTxType(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="">Все типы</option>
              <option value="earn">Начисления</option>
              <option value="release">Доступно после холда</option>
              <option value="claim">Баллы → GLM</option>
              <option value="adjustment">Корректировки</option>
              <option value="redemption">GLM Store</option>
              <option value="conversion">Баллы → GLM</option>
              <option value="reversal">Возвраты GLM</option>
            </select>
            <select value={glmTxStatus} onChange={(event) => setGlmTxStatus(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="">Все статусы</option>
              <option value="hold">Холд</option>
              <option value="available">Доступно</option>
              <option value="pending">На проверке</option>
              <option value="processed">Обработано</option>
              <option value="pending_ton_payment">Ждет TON-оплату</option>
              <option value="pending_fulfillment">На сборке</option>
              <option value="fulfilled">Выдано</option>
              <option value="failed">Ошибка</option>
              <option value="canceled">Отменено</option>
            </select>
            <button onClick={() => void releaseDueGlmHolds()} disabled={saving} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">Выпустить hold</button>
            <button onClick={() => { void loadGlmTransactions(); void loadGlmDashboard(); void loadGlmEffectiveness(); void loadGlmSegments(); void loadGlmRefundCandidates(); void loadGlmToPointsBridges(); }} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60">Обновить</button>
          </div>
        </div>
        {glmReleaseResult ? <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{glmReleaseResult}</div> : null}
        <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-10">
          <Metric title="GLM accounts" value={`${glmDashboard?.accounts_total || 0}`} />
          <Metric title="Balance" value={`${glmDashboard?.balance_total || 0} GLM`} />
          <Metric title="Hold" value={`${glmDashboard?.hold_total || 0} GLM`} hint={`${glmDashboard?.due_hold_total || 0} GLM due`} />
          <Metric title="Earn month" value={`${glmDashboard?.monthly_earn_total || 0} GLM`} />
          <Metric title="Emission cap" value={`${glmDashboard?.monthly_referral_emission_percent || 0}%`} hint={`${glmDashboard?.monthly_referral_emission_remaining || 0} GLM left`} />
          <Metric title="Campaign" value={glmDashboard?.referral_campaign?.active ? `x${glmDashboard.referral_campaign.multiplier}` : 'Base'} hint={glmDashboard?.referral_campaign?.active ? glmDashboard.referral_campaign.name : '1 GLM / 1 ₽'} />
          <Metric title="Real-backed" value={`${glmDashboard?.real_turnover_backed_percent || 0}%`} hint={`${glmDashboard?.real_turnover_backed_total || 0} GLM referral`} />
          <Metric title="Points→GLM" value={`${glmDashboard?.conversion_total || 0} GLM`} hint="из бонусных баллов" />
          <Metric title="Store burn" value={`${glmDashboard?.redemption_total || 0} GLM`} hint={`${glmDashboard?.burned_total || 0} GLM burned`} />
          <Metric title="Ждет отправки в TON" value={`${glmDashboard?.pending_claim_total || 0} GLM`} hint={`${glmDashboard?.pending_claim_count || 0} заявок`} />
        </div>
        <div className="mt-4 grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Топ партнеров по GLM</div>
            <div className="mt-3 space-y-2">
              {(glmDashboard?.top_partners || []).slice(0, 6).map((item) => (
                <div key={item.member_id} className="rounded border border-slate-200 bg-white p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-slate-900">{item.partner_name || 'Партнер GLAME'}</div>
                      <div className="mt-1 text-xs text-slate-500">{item.partner_phone || '—'}</div>
                    </div>
                    <div className="text-right text-xs text-slate-600">
                      <div>{item.balance} GLM</div>
                      <div className="mt-1 text-slate-400">hold {item.hold_balance}</div>
                    </div>
                  </div>
                </div>
              ))}
              {!(glmDashboard?.top_partners || []).length ? <div className="text-sm text-slate-500">GLM-аккаунтов пока нет</div> : null}
            </div>
          </div>
          <div>
            <DataTable
              headers={['Дата', 'Партнер', 'Тип', 'Статус', 'Сумма', 'Баланс', 'Причина']}
              rows={glmTransactions.map((tx) => [
                dateRu(tx.created_at),
                <div key={`partner-${tx.id}`}>
                  <div className="font-medium text-slate-900">{tx.partner_name || 'Партнер GLAME'}</div>
                  <div className="mt-1 text-xs text-slate-500">{tx.partner_phone || '—'}</div>
                </div>,
                <Badge key={`type-${tx.id}`} value={tx.type} />,
                <Badge key={`status-${tx.id}`} value={tx.status} />,
                `${tx.amount} GLM`,
                <div key={`balance-${tx.id}`} className="text-xs text-slate-600">balance {tx.balance_after} · hold {tx.hold_balance_after}</div>,
                <div key={`reason-${tx.id}`} className="max-w-[260px]">
                  <div className="text-sm text-slate-700">{tx.reason || tx.source || '—'}</div>
                  <div className="mt-1 break-all text-xs text-slate-500">{tx.tx_hash || tx.source_id || tx.description || '—'}</div>
                </div>,
              ])}
            />
          </div>
        </div>
      </section>

      <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.25fr)]">
        <section className="min-w-0 rounded-md border border-slate-200 bg-white p-4 shadow-sm">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Поиск: ФИО, телефон, код, ИНН" className="rounded-md border border-slate-300 px-3 py-2 text-sm md:col-span-1" />
            <select value={status} onChange={(event) => setStatus(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="">Все статусы</option>
              <option value="active">Активные</option>
              <option value="blocked">Заблокированные</option>
              <option value="paused">Пауза</option>
            </select>
            <select value={rewardMode} onChange={(event) => setRewardMode(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="">Все режимы</option>
              <option value="points">Баллы</option>
              <option value="cash">Деньги</option>
            </select>
            <select value={tonStatus} onChange={(event) => setTonStatus(event.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="">Все TON</option>
              <option value="verified">TON подтвержден</option>
              <option value="linked">Ручная привязка</option>
              <option value="claim_enabled">GLM в TON разрешен</option>
              <option value="missing">Без кошелька</option>
            </select>
          </div>

          <div className="mt-4 max-h-[720px] space-y-2 overflow-auto pr-1">
            {loading ? <div className="p-6 text-center text-sm text-slate-500">Загрузка...</div> : null}
            {!loading && !partners.length ? <div className="p-6 text-center text-sm text-slate-500">Партнеры не найдены</div> : null}
            {partners.map((partner) => {
              const active = selected?.member.id === partner.member.id;
              const wallet = partner.member.crypto_wallet;
              const tonVerified = wallet?.status === 'verified';
              return (
                <button key={partner.member.id} onClick={() => void loadPartner(partner.member.id)} className={`w-full rounded-md border p-4 text-left transition ${active ? 'border-slate-900 bg-slate-50' : 'border-slate-200 hover:border-slate-400'}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-slate-900">{partner.profile.full_name || 'Партнер GLAME'}</div>
                      <div className="mt-1 text-sm text-slate-500">{partner.profile.phone || '—'} · {partner.referral_code?.code || 'без кода'}</div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <Badge value={partner.member.status} />
                      <span className={`inline-flex rounded border px-2 py-1 text-xs font-medium ${tonVerified ? 'border-sky-200 bg-sky-50 text-sky-700' : wallet?.status ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-slate-200 bg-slate-50 text-slate-500'}`}>
                        {tonVerified ? 'TON подтвержден' : wallet?.status === 'linked' ? 'TON вручную' : 'Нет TON'}
                      </span>
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-slate-600">
                    <div><span className="block text-slate-400">Режим</span>{partner.member.reward_mode === 'cash' ? 'Деньги' : 'Баллы'}</div>
                    <div><span className="block text-slate-400">Оборот</span>{money(partner.summary.referral_revenue)}</div>
                    <div><span className="block text-slate-400">GLM в TON</span>{wallet?.glm_claim_enabled ? 'Разрешен' : 'Нет'}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="min-w-0 space-y-4">
          {!selected ? (
            <div className="rounded-md border border-slate-200 bg-white p-8 text-center text-slate-500">Выберите партнера</div>
          ) : (
            <>
              <div className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <h2 className="text-2xl font-semibold text-slate-900">{selected.profile.full_name || 'Партнер GLAME'}</h2>
                    <div className="mt-2 flex flex-wrap gap-2 text-sm text-slate-600">
                      <span>{selected.profile.phone || '—'}</span>
                      <span>{selected.profile.email || '—'}</span>
                      <span>{selected.referral_code?.code || 'без кода'}</span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge value={selected.member.status} />
                    <Badge value={selected.member.cash_status} />
                    <Badge value={selected.member.onec_sync_status} />
                  </div>
                </div>

                <div className="mt-5 grid gap-3 md:grid-cols-4">
                  <Metric title="Регистрации" value={`${selectedSummary.registrations}`} />
                  <Metric title="Покупки" value={`${selectedSummary.purchases}`} />
                  <Metric title="Оборот" value={money(selectedSummary.referral_revenue)} />
                  <Metric title={selected.member.reward_mode === 'cash' ? 'Комиссия' : 'Баллы'} value={selected.member.reward_mode === 'cash' ? money(selectedSummary.approved_commission + selectedSummary.accrued_in_1c) : `${selectedSummary.posted_points}`} />
                </div>
              </div>

              <div className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-slate-900">TON-кошелек / GLM в TON</h3>
                    <p className="mt-1 text-sm text-slate-500">Перевод GLM в TON включается только для кошельков, подтвержденных через TON Connect ton_proof.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge value={selectedWallet?.status || 'missing'} />
                    <Badge value={selectedWallet?.glm_claim_enabled ? 'claim_enabled' : 'pending'} />
                  </div>
                </div>
                <div className="mt-4 grid gap-3 text-sm md:grid-cols-2">
                  <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                    <div className="text-xs uppercase tracking-wide text-slate-500">GLM balance</div>
                    <div className="mt-1 text-slate-900">{selected.token?.balance || 0} GLM · hold {selected.token?.hold_balance || 0} GLM</div>
                  </div>
                  <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                    <div className="text-xs uppercase tracking-wide text-slate-500">Ждет отправки в TON</div>
                    <div className="mt-1 text-slate-900">{selected.token?.pending_claim ? `${selected.token?.pending_claim_amount || 0} GLM` : 'Нет'}</div>
                  </div>
                  <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                    <div className="text-xs uppercase tracking-wide text-slate-500">Адрес</div>
                    <div className="mt-1 break-all text-slate-900">{selectedWallet?.address || '—'}</div>
                  </div>
                  <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                    <div className="text-xs uppercase tracking-wide text-slate-500">Wallet app</div>
                    <div className="mt-1 text-slate-900">{selectedWallet?.wallet_app || selectedWallet?.label || '—'}</div>
                  </div>
                  <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                    <div className="text-xs uppercase tracking-wide text-slate-500">Proof</div>
                    <div className="mt-1 text-slate-900">{selectedWallet?.verification || '—'} · {dateRu(selectedWallet?.verified_at)}</div>
                  </div>
                  <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                    <div className="text-xs uppercase tracking-wide text-slate-500">GLM в TON</div>
                    <div className="mt-1 text-slate-900">{selectedWallet?.glm_claim_enabled ? `Разрешен · ${dateRu(selectedWallet?.glm_claim_updated_at)}` : 'Не разрешен'}</div>
                  </div>
                </div>
                {selectedWallet?.glm_claim_comment ? <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">{selectedWallet.glm_claim_comment}</div> : null}
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    disabled={saving || selectedWallet?.status !== 'verified' || !!selectedWallet?.glm_claim_enabled}
                    onClick={() => void setGlmClaimAccess(true)}
                    className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  >
                    Разрешить GLM в TON
                  </button>
                  <button
                    disabled={saving || !selectedWallet?.glm_claim_enabled}
                    onClick={() => void setGlmClaimAccess(false)}
                    className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
                  >
                    Отключить GLM в TON
                  </button>
                  <button
                    disabled={saving || !selected.token?.hold_balance}
                    onClick={() => void releaseGlmHold()}
                    className="rounded-md border border-emerald-200 px-4 py-2 text-sm font-medium text-emerald-700 disabled:opacity-50"
                  >
                    Перевести hold в balance
                  </button>
                </div>
                <div className="mt-5 rounded-md border border-slate-200 bg-slate-50 p-4">
                  <div className="text-sm font-semibold text-slate-900">Ручная корректировка GLM balance</div>
                  <div className="mt-3 grid gap-3 lg:grid-cols-[0.7fr_0.7fr_1fr]">
                    <select value={glmAdjustDirection} onChange={(event) => setGlmAdjustDirection(event.target.value as 'credit' | 'debit')} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
                      <option value="credit">Начислить</option>
                      <option value="debit">Списать</option>
                    </select>
                    <input value={glmAdjustAmount} onChange={(event) => setGlmAdjustAmount(event.target.value)} placeholder="Сумма GLM" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
                    <input value={glmAdjustReason} onChange={(event) => setGlmAdjustReason(event.target.value)} placeholder="Причина, обязательно" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
                  </div>
                  <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_auto]">
                    <input value={glmAdjustComment} onChange={(event) => setGlmAdjustComment(event.target.value)} placeholder="Комментарий для audit trail" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
                    <button disabled={saving} onClick={() => void adjustGlmBalance()} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">Сохранить корректировку</button>
                  </div>
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
                  <h3 className="font-semibold text-slate-900">Управление программой</h3>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <label className="text-sm text-slate-600">Статус
                      <select value={selected.member.status} onChange={(event) => void updatePartner({ status: event.target.value })} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2">
                        <option value="active">Активен</option>
                        <option value="paused">Пауза</option>
                        <option value="blocked">Заблокирован</option>
                      </select>
                    </label>
                    <label className="text-sm text-slate-600">Режим
                      <select value={selected.member.reward_mode} onChange={(event) => void updatePartner({ reward_mode: event.target.value })} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2">
                        <option value="points">Баллы</option>
                        <option value="cash">Деньги</option>
                      </select>
                    </label>
                    <label className="text-sm text-slate-600">Уровень
                      <input defaultValue={selected.member.program_level} onBlur={(event) => void updatePartner({ program_level: event.target.value })} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" />
                    </label>
                    <label className="text-sm text-slate-600">Договор 1С
                      <input value={contractId} onChange={(event) => setContractId(event.target.value)} onBlur={(event) => void updatePartner({ onec_agency_contract_id: event.target.value })} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" />
                    </label>
                  </div>
                  <button disabled={saving} onClick={() => void updatePartner({ status: 'blocked', block_reason: 'Отключено администратором' })} className="mt-4 rounded-md border border-red-200 px-4 py-2 text-sm font-medium text-red-700 disabled:opacity-60">Заблокировать партнера</button>
                </div>

                <div className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
                  <h3 className="font-semibold text-slate-900">Данные 1С и договора</h3>
                  <div className="mt-4 grid gap-3 text-sm">
                    <div><span className="text-slate-500">Контрагент/покупатель 1С: </span>{selected.member.onec_counterparty_id || selected.profile.customer_id_1c || '—'}</div>
                    <div><span className="text-slate-500">Карта/телефон 1С: </span>{selected.profile.discount_card_number || '—'}</div>
                    <div><span className="text-slate-500">ИНН: </span>{selected.profile.inn || '—'}</div>
                    <div><span className="text-slate-500">Правовой статус: </span>{selected.profile.legal_status === 'ip' ? 'ИП' : selected.profile.legal_status === 'self_employed' ? 'Самозанятый' : '—'}</div>
                  </div>
                </div>
              </div>

              <div className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
                <h3 className="font-semibold text-slate-900">Заявки на денежное вознаграждение</h3>
                <div className="mt-4 space-y-3">
                  {(selected.cash_requests || []).length ? selected.cash_requests?.map((request) => (
                    <div key={request.id} className="rounded-md border border-slate-200 p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                        <div>
                          <div className="font-medium text-slate-900">{request.legal_status === 'ip' ? 'ИП' : 'Самозанятый'} · ИНН {request.inn}</div>
                          <div className="mt-1 text-sm text-slate-500">Создана {dateRu(request.created_at)}</div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Badge value={request.status} />
                          <button disabled={saving || request.status !== 'pending'} onClick={() => void reviewCashRequest(request.id, 'approved')} className="rounded-md border border-emerald-200 px-3 py-2 text-sm text-emerald-700 disabled:opacity-50">Одобрить</button>
                          <button disabled={saving || request.status !== 'pending'} onClick={() => void reviewCashRequest(request.id, 'rejected')} className="rounded-md border border-red-200 px-3 py-2 text-sm text-red-700 disabled:opacity-50">Отклонить</button>
                        </div>
                      </div>
                    </div>
                  )) : <div className="text-sm text-slate-500">Заявок нет</div>}
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
                  <h3 className="font-semibold text-slate-900">Паспортные данные</h3>
                  <div className="mt-4"><JsonBlock value={selected.profile.passport_data} /></div>
                </div>
                <div className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
                  <h3 className="font-semibold text-slate-900">Реквизиты для выплат</h3>
                  <div className="mt-4"><JsonBlock value={selected.profile.payout_details} /></div>
                </div>
              </div>

              <div className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                  <div>
                    <h3 className="font-semibold text-slate-900">Выплаты</h3>
                    <p className="mt-1 text-sm text-slate-500">Создание и фиксация статусов выплат по агентскому договору.</p>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <input value={payoutAmount} onChange={(event) => setPayoutAmount(event.target.value)} placeholder="Сумма, ₽" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
                    <input value={payoutDocument} onChange={(event) => setPayoutDocument(event.target.value)} placeholder="Документ 1С" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
                    <button disabled={saving} onClick={() => void createPayout()} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">Создать выплату</button>
                  </div>
                </div>
                <textarea value={payoutComment} onChange={(event) => setPayoutComment(event.target.value)} placeholder="Комментарий к выплате" className="mt-3 min-h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
                <div className="mt-4">
                  <DataTable
                    headers={['Период', 'Сумма', 'Статус', 'Документ 1С', 'Действия']}
                    rows={(selected.payouts || []).map((item) => [
                      item.period_start || item.period_end ? `${dateRu(item.period_start)} - ${dateRu(item.period_end)}` : dateRu(item.requested_at),
                      money(item.amount),
                      <Badge key={`status-${item.id}`} value={item.status} />,
                      item.onec_payment_document_id || '—',
                      <div key={`actions-${item.id}`} className="flex flex-wrap gap-2">
                        <button disabled={saving} onClick={() => void updatePayout(item.id, 'approved')} className="rounded border border-slate-300 px-2 py-1 text-xs">Одобрить</button>
                        <button disabled={saving} onClick={() => void updatePayout(item.id, 'paid')} className="rounded border border-slate-300 px-2 py-1 text-xs">Оплачено</button>
                        <button disabled={saving} onClick={() => void updatePayout(item.id, 'canceled')} className="rounded border border-red-200 px-2 py-1 text-xs text-red-700">Отмена</button>
                      </div>,
                    ])}
                  />
                </div>
              </div>

              <div className="grid gap-4">
                <div>
                  <h3 className="mb-3 font-semibold text-slate-900">Рефералы</h3>
                  <DataTable headers={['Имя', 'Телефон', 'Источник', 'Статус', 'Покупки', 'Сумма', 'Вознаграждение']} rows={(selected.referrals || []).map((item) => [item.name || '—', item.phone || '—', item.source || '—', <Badge key={item.id} value={item.status} />, item.purchases || 0, money(item.spent), selected.member.reward_mode === 'cash' ? money(item.reward_amount) : `${item.reward_points || 0} баллов`])} />
                </div>
                <div>
                  <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                    <h3 className="font-semibold text-slate-900">Начисления</h3>
                    <input value={commissionCancelComment} onChange={(event) => setCommissionCancelComment(event.target.value)} placeholder="Комментарий к отмене/возврату" className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
                  </div>
                  <DataTable
                    headers={['Дата', 'База', 'Ставка', 'Вознаграждение', 'Статус', 'GLM', '1С', 'Действия']}
                    rows={(selected.commissions || []).map((item) => [
                      dateRu(item.date),
                      money(item.base),
                      `${item.rate || 0}%`,
                      item.reward_mode === 'cash' ? money(item.amount) : `${item.points || 0} баллов`,
                      <Badge key={`status-${item.id}`} value={item.status} />,
                      item.glm?.amount ? `${item.glm.amount} GLM · ${item.glm.status || '—'}` : '—',
                      item.onec_document_id || item.onec_sync_status || '—',
                      <button key={`cancel-${item.id}`} disabled={saving || item.status === 'canceled'} onClick={() => void cancelReferralCommission(item.id)} className="rounded border border-red-200 px-2 py-1 text-xs text-red-700 disabled:opacity-50">Отменить</button>,
                    ])}
                  />
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
