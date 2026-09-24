from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CrmCustomerSummary(BaseModel):
    id: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    birth_date: Optional[date] = None
    preferred_store_name: Optional[str] = None
    secondary_store_name: Optional[str] = None
    total_purchases: int = 0
    total_spent: int = 0
    average_check: Optional[int] = None
    last_purchase_date: Optional[datetime] = None
    customer_segment: Optional[str] = None
    loyalty_points: int = 0
    questionnaire: Dict[str, Any] = Field(default_factory=dict)
    contact_instruction: Optional[str] = None


class CrmTaskEventDto(BaseModel):
    id: str
    event_type: str
    actor_user_id: Optional[str] = None
    actor_name: Optional[str] = None
    previous_status: Optional[str] = None
    next_status: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class CrmTaskDto(BaseModel):
    id: str
    customer_id: str
    customer: Optional[CrmCustomerSummary] = None
    assigned_seller_user_id: Optional[str] = None
    assigned_seller_external_id: Optional[str] = None
    assigned_seller_name: Optional[str] = None
    store_id: Optional[str] = None
    store_name: Optional[str] = None
    work_date: date
    due_date: Optional[datetime] = None
    priority: int = 3
    crm_group: str
    reason: Optional[str] = None
    seller_action: Optional[str] = None
    script_key: Optional[str] = None
    script_text: Optional[str] = None
    status: str
    seller_outcome: Optional[str] = None
    seller_comment: Optional[str] = None
    next_action_date: Optional[date] = None
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    source: str = "manual"
    source_row_id: Optional[str] = None
    source_idempotency_key: Optional[str] = None
    source_payload: Dict[str, Any] = Field(default_factory=dict)
    last_contacted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    attributed_purchase_count: int = 0
    attributed_revenue_kopecks: int = 0
    attributed_purchase_ids: List[str] = Field(default_factory=list)
    attributed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    events: List[CrmTaskEventDto] = Field(default_factory=list)
    recent_messages: List[Dict[str, Any]] = Field(default_factory=list)


class CrmTaskListResponse(BaseModel):
    items: List[CrmTaskDto]
    total: int
    limit: int
    offset: int


class CrmTaskResultRequest(BaseModel):
    seller_outcome: str
    seller_comment: str
    next_action_date: Optional[date] = None


class CrmTaskPostponeRequest(BaseModel):
    next_action_date: date
    seller_comment: str


class CrmTaskAssignRequest(BaseModel):
    assigned_seller_user_id: Optional[UUID] = None
    assigned_seller_external_id: Optional[str] = None
    assigned_seller_name: Optional[str] = None
    store_id: Optional[str] = None
    store_name: Optional[str] = None


class CrmTaskImportRow(BaseModel):
    phone: str
    customer_name: Optional[str] = None
    seller_name: Optional[str] = None
    seller_external_id: Optional[str] = None
    store_id: Optional[str] = None
    store_name: Optional[str] = None
    work_date: date
    due_date: Optional[datetime] = None
    crm_group: str
    priority: int = 3
    reason: Optional[str] = None
    seller_action: Optional[str] = None
    script_key: Optional[str] = None
    script_text: Optional[str] = None
    source_row_id: Optional[str] = None
    status: Optional[str] = None
    seller_outcome: Optional[str] = None
    seller_comment: Optional[str] = None
    next_action_date: Optional[date] = None
    source_payload: Dict[str, Any] = Field(default_factory=dict)


class CrmTaskImportRequest(BaseModel):
    source: str = "google_sheets"
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    rows: List[CrmTaskImportRow]


class CrmTaskImportResponse(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    not_found_customers: int = 0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    tasks: List[CrmTaskDto] = Field(default_factory=list)


class CrmDashboardResponse(BaseModel):
    total: int = 0
    active: int = 0
    completed: int = 0
    overdue: int = 0
    without_comment: int = 0
    postponed: int = 0
    attributed_purchase_count: int = 0
    attributed_revenue_kopecks: int = 0
    by_status: Dict[str, int] = Field(default_factory=dict)
    by_seller: List[Dict[str, Any]] = Field(default_factory=list)
    by_group: Dict[str, int] = Field(default_factory=dict)


class CrmCampaignAnalyticsPurchase(BaseModel):
    task_id: str
    customer_id: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    store_name: Optional[str] = None
    seller_name: Optional[str] = None
    contact_date: Optional[datetime] = None
    purchase_count: int = 0
    revenue_kopecks: int = 0
    purchase_ids: List[str] = Field(default_factory=list)


class CrmCampaignAnalyticsChannel(BaseModel):
    channel: str
    label: str
    recipients: int = 0
    contacted: int = 0
    purchases: int = 0
    revenue_kopecks: int = 0
    conversion_rate: float = 0


class CrmCampaignAnalyticsItem(BaseModel):
    campaign_id: Optional[str] = None
    campaign_name: str
    source: str = "manual"
    recipients: int = 0
    contacted: int = 0
    completed: int = 0
    purchases: int = 0
    buyers: int = 0
    revenue_kopecks: int = 0
    conversion_rate: float = 0
    revenue_per_contact_kopecks: int = 0
    by_channel: List[CrmCampaignAnalyticsChannel] = Field(default_factory=list)
    purchases_list: List[CrmCampaignAnalyticsPurchase] = Field(default_factory=list)


class CrmCampaignAnalyticsResponse(BaseModel):
    window_days: int = 14
    total_campaigns: int = 0
    total_recipients: int = 0
    total_contacted: int = 0
    total_purchases: int = 0
    total_revenue_kopecks: int = 0
    campaigns: List[CrmCampaignAnalyticsItem] = Field(default_factory=list)


class CrmAttributionRequest(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    task_ids: Optional[List[UUID]] = None
    window_days: int = Field(default=14, ge=1, le=90)


class CrmAttributionResponse(BaseModel):
    updated: int = 0
    purchase_count: int = 0
    revenue_kopecks: int = 0


class CrmTouchpointGenerationRequest(BaseModel):
    work_date: Optional[date] = None
    warranty_days: int = Field(default=30, ge=14, le=1095)
    limit_documents_per_rule: int = Field(default=2000, ge=1, le=10000)


class CrmTouchpointGenerationResponse(BaseModel):
    work_date: str
    warranty_days: int
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    by_rule: Dict[str, Any] = Field(default_factory=dict)


class CrmBirthdayGenerationRequest(BaseModel):
    work_date: Optional[date] = None
    days_ahead: int = Field(default=3, ge=0, le=30)
    limit: int = Field(default=500, ge=1, le=5000)


class CrmBirthdayGenerationResponse(BaseModel):
    work_date: str
    days_ahead: int
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    by_tier: Dict[str, Any] = Field(default_factory=dict)


class CrmNewArrivalGenerationRequest(BaseModel):
    work_date: Optional[date] = None
    lookback_hours: int = Field(default=48, ge=1, le=24 * 14)
    limit_arrivals: int = Field(default=10, ge=1, le=100)
    limit_clients_per_arrival: int = Field(default=25, ge=1, le=300)
    use_polling_fallback: bool = False
    source: Literal["primary_receipt_only"] = "primary_receipt_only"
    batch_id: Optional[str] = None
    create_seller_tasks: bool = False
    prepare_push: bool = False
    send_push: bool = False
    dry_run: bool = True
    anatoliy_technical_approved: bool = False


class CrmNewArrivalGenerationResponse(BaseModel):
    work_date: str
    received_since: str
    created: int = 0
    updated: int = 0
    dry_run: bool = True
    tasks_previewed: int = 0
    skipped: int = 0
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    by_arrival: Dict[str, Any] = Field(default_factory=dict)
    receipt_sync: Dict[str, Any] = Field(default_factory=dict)
    transfer_sync: Dict[str, Any] = Field(default_factory=dict)
    push_drafts: List[Dict[str, Any]] = Field(default_factory=list)
    push_auto_send: bool = False
