"""Canonical GLAME AI agent operating contracts.

This module is the single lightweight source of truth for business-facing
marketing agent IDs, aliases and inter-agent message metadata. It intentionally
contains no database imports so it can be reused by API endpoints, workers,
frontend schema generators and tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentId(str, Enum):
    DIRECTOR = "director-agent"
    PERSONAL_MEDIA = "personal-media-agent"
    BRAND_MEDIA = "brand-media-agent"
    CRM = "crm-agent"
    PR_PARTNERSHIPS = "pr-partnerships-agent"
    TRAFFIC_GROWTH = "traffic-growth-agent"
    ANALYTICS = "analytics-agent"
    ASSORTMENT = "assortment-agent"


class CommunicationType(str, Enum):
    TASK_ASSIGNMENT = "task_assignment"
    APPROVAL_REQUEST = "approval_request"
    ESCALATION = "escalation"
    ANALYTICS_SUMMARY = "analytics_summary"
    CAMPAIGN_UPDATE = "campaign_update"
    CRM_RECOMMENDATION = "crm_recommendation"
    PERFORMANCE_RECOMMENDATION = "performance_recommendation"
    AGENT_REPORT = "agent_report"
    REVISION_REQUEST = "revision_request"
    HANDOFF = "handoff"


class BusinessStage(str, Enum):
    IDEA = "Idea"
    BRIEFED = "Briefed"
    PLANNED = "Planned"
    IN_PRODUCTION = "In Production"
    NEEDS_APPROVAL = "Needs Approval"
    APPROVED = "Approved"
    SCHEDULED = "Scheduled"
    PUBLISHED = "Published"
    SENT = "Sent"
    LAUNCHED = "Launched"
    MEASURED = "Measured"
    DONE = "Done"
    BLOCKED = "Blocked"


class ApprovalCategory(str, Enum):
    STRATEGY_CHANGE = "strategy_change"
    SENSITIVE_CAMPAIGN = "sensitive_campaign"
    NEW_OFFER = "new_offer"
    DISCOUNT = "discount"
    MAJOR_CRM_SEND = "major_crm_send"
    PUBLIC_POSITIONING = "public_positioning"
    RISKY_COLLABORATION = "risky_collaboration"
    APP_PUSH_CAMPAIGN = "app_push_campaign"


class AgentPriority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


PRIORITY_TO_NUMERIC: Dict[str, int] = {
    AgentPriority.P0.value: 1,
    AgentPriority.P1.value: 2,
    AgentPriority.P2.value: 3,
    AgentPriority.P3.value: 4,
}

NUMERIC_TO_PRIORITY: Dict[int, str] = {value: key for key, value in PRIORITY_TO_NUMERIC.items()}

MARKETING_AGENT_REGISTRY: List[Dict[str, Any]] = [
    {
        "id": AgentId.DIRECTOR.value,
        "name": "AI Marketing Director",
        "board": "Command Board",
        "role": "Центральный управляющий агент маркетинговой операционной системы GLAME.",
        "receives": [
            "стратегия, приоритеты и ограничения от Елены",
            "Omegacount / посещения магазинов",
            "1C: продажи, чеки, возвраты, loyalty, товары",
            "CRM-сегменты и retention",
            "соцмедиа, сайт / Yandex Metrika, будущие app-события",
            "отчеты всех AI-агентов",
        ],
        "outputs": [
            "monthly strategy",
            "weekly focus",
            "daily plan",
            "cross-agent task assignments",
            "campaign priorities",
            "risk alerts",
            "recommendations and approval requests",
        ],
        "tools": ["director chat", "knowledge base", "task orchestration", "all data tools"],
        "aliases": ["marketing-director", "marketing-director-agent", "ai-marketing-director", "ai-marketer", "director", "command", "marketing"],
    },
    {
        "id": AgentId.PERSONAL_MEDIA.value,
        "name": "AI Personal Media",
        "board": "Personal Media Board",
        "role": "Личный медиа-слой Елены: внимание, авторитет, вкус и доверие.",
        "receives": ["priorities from Director", "AI Analytics", "AI Brand Media", "approved personal topics"],
        "outputs": ["personal blog calendar", "Reels ideas", "hooks", "storylines", "soft bridges into GLAME"],
        "tools": ["content planner", "performance reports", "knowledge base", "media task board"],
        "aliases": ["personal-media", "personal", "elena-media"],
    },
    {
        "id": AgentId.BRAND_MEDIA.value,
        "name": "AI Brand Media",
        "board": "Content Board",
        "role": "GLAME brand media: перевод внимания в желание, доверие, визиты, saves/app/site и покупки.",
        "receives": ["weekly focus", "AI Assortment", "AI Analytics", "AI Traffic & Growth", "AI CRM"],
        "outputs": ["content plan", "Reels scenarios", "Stories plan", "hooks", "CTA", "shooting briefs"],
        "tools": ["content generator", "content board", "campaign context", "assortment/product focus"],
        "aliases": ["brand-media", "content-agent", "content", "brand-media-content", "content_board"],
    },
    {
        "id": AgentId.CRM.value,
        "name": "AI CRM",
        "board": "CRM Board",
        "role": "CRM, retention, customer return and loyalty communication.",
        "receives": ["customer segments", "purchase history", "loyalty", "AI Assortment", "AI Analytics", "AI Brand Media"],
        "outputs": ["CRM plans", "segment logic", "SMS/WhatsApp/email drafts", "VIP scenarios", "return flows"],
        "tools": ["CRM data", "segmentation", "communications", "loyalty", "message drafts"],
        "aliases": ["crm", "communication-agent", "communication", "crm-board", "mailing", "segment"],
    },
    {
        "id": AgentId.PR_PARTNERSHIPS.value,
        "name": "AI PR & Partnerships",
        "board": "Partnership Board",
        "role": "Партнерства, коллаборации, local influence and external warm traffic.",
        "receives": ["campaign focus", "city focus", "local events", "partner database", "AI Brand Media", "AI Analytics"],
        "outputs": ["partnership strategy", "collab ideas", "outreach briefs", "partner prioritization", "event proposals"],
        "tools": ["partnership board", "partner database", "campaign briefs", "analytics reports"],
        "aliases": ["pr-partnerships", "partnership", "pr", "partnership-agent", "partner", "influencer", "collab"],
    },
    {
        "id": AgentId.TRAFFIC_GROWTH.value,
        "name": "AI Traffic & Growth",
        "board": "Traffic/Growth Board",
        "role": "Growth layer: amplify proven content, campaigns, CRM flows and store/app return logic.",
        "receives": ["content performance", "campaign focus", "website/app data", "CRM segments", "AI Analytics", "AI Assortment"],
        "outputs": ["traffic recommendations", "Yandex briefs", "geo recommendations", "retarget recommendations", "budget logic"],
        "tools": ["Yandex/Metrika", "geo traffic", "retargeting briefs", "campaign tracking"],
        "aliases": ["traffic-growth", "traffic", "growth", "traffic-agent", "retarget", "ads"],
    },
    {
        "id": AgentId.ANALYTICS.value,
        "name": "AI Analytics",
        "board": "Analytics Board",
        "role": "Unified business intelligence across content, CRM, traffic, app, website, Omegacount, 1C and partnerships.",
        "receives": ["all agents", "data systems", "1C", "Omegacount", "CRM", "website analytics", "Flutter app behavior", "Instagram analytics"],
        "outputs": ["daily pulse", "weekly report", "monthly report", "anomaly alerts", "correlation insights", "recommendations"],
        "tools": ["sales records", "store visits", "CRM analytics", "website analytics", "mobile app behavior", "Instagram analytics", "agent reports"],
        "aliases": ["analytics", "report", "analysis"],
    },
    {
        "id": AgentId.ASSORTMENT.value,
        "name": "AI Assortment",
        "board": "Product Focus Board",
        "role": "Связь маркетинга с реальным продуктом, остатками, продажами и styling logic.",
        "receives": ["1C sales", "inventory", "arrivals", "returns", "product categories", "CRM behaviour", "content needs"],
        "outputs": ["product focus", "arrivals focus", "slow mover recommendations", "styling combinations", "content product briefs"],
        "tools": ["1C sales", "inventory/stock", "product analytics", "marketing-inventory link"],
        "aliases": ["assortment", "marketing-inventory-agent", "inventory-control-agent", "inventory", "product", "stock"],
    },
]

CANONICAL_AGENT_IDS: List[str] = [agent["id"] for agent in MARKETING_AGENT_REGISTRY]

CANONICAL_AGENT_EXECUTION_ALIASES: Dict[str, str] = {
    "brand-media-agent": "content-agent",
    "personal-media-agent": "content-agent",
    "crm-agent": "communication-agent",
    "assortment-agent": "marketing-inventory-agent",
}

CANONICAL_AGENT_PROMPT_ALIASES: Dict[str, str] = {
    "ai-marketer": AgentId.DIRECTOR.value,
    "marketing-director": AgentId.DIRECTOR.value,
    "marketing-director-agent": AgentId.DIRECTOR.value,
    "content-agent": AgentId.BRAND_MEDIA.value,
    "content_board": AgentId.BRAND_MEDIA.value,
    "personal-media": AgentId.PERSONAL_MEDIA.value,
    "communication-agent": AgentId.CRM.value,
    "pr-partnerships": AgentId.PR_PARTNERSHIPS.value,
    "traffic-growth": AgentId.TRAFFIC_GROWTH.value,
    "marketing-inventory-agent": AgentId.ASSORTMENT.value,
}

DOC_PROMPT_TITLE_TO_AGENT_ID: Dict[str, str] = {
    "AI MARKETING DIRECTOR": AgentId.DIRECTOR.value,
    "AI PERSONAL MEDIA": AgentId.PERSONAL_MEDIA.value,
    "AI BRAND MEDIA": AgentId.BRAND_MEDIA.value,
    "AI CRM": AgentId.CRM.value,
    "AI PR & PARTNERSHIPS": AgentId.PR_PARTNERSHIPS.value,
    "AI TRAFFIC & GROWTH": AgentId.TRAFFIC_GROWTH.value,
    "AI ANALYTICS": AgentId.ANALYTICS.value,
    "AI ASSORTMENT": AgentId.ASSORTMENT.value,
}

BOARD_ALIASES: Dict[str, List[str]] = {
    "command": [AgentId.DIRECTOR.value, "marketing-director", "marketing"],
    "content": [AgentId.BRAND_MEDIA.value, "content", "content-agent", "brand-media", "publication"],
    "personal-media": [AgentId.PERSONAL_MEDIA.value, "personal-media", "personal", "elena"],
    "crm": [AgentId.CRM.value, "crm", "communication", "communication-agent", "mailing", "segment"],
    "partnership": [AgentId.PR_PARTNERSHIPS.value, "partnership", "partner", "pr-partnerships", "influencer", "collab"],
    "traffic": [AgentId.TRAFFIC_GROWTH.value, "traffic", "growth", "retarget", "ads"],
    "product": [AgentId.ASSORTMENT.value, "product", "assortment", "inventory", "stock", "marketing-inventory-agent"],
    "analytics": [AgentId.ANALYTICS.value, "analytics", "report", "analysis"],
}

APPROVAL_REQUIRED_CATEGORIES: List[str] = [category.value for category in ApprovalCategory]

TECHNICAL_STATUS_TO_BUSINESS_STAGE: Dict[str, str] = {
    "pending": BusinessStage.IDEA.value,
    "validating": BusinessStage.BRIEFED.value,
    "validated": BusinessStage.NEEDS_APPROVAL.value,
    "pending_approval": BusinessStage.NEEDS_APPROVAL.value,
    "approved": BusinessStage.APPROVED.value,
    "queued": BusinessStage.SCHEDULED.value,
    "processing": BusinessStage.IN_PRODUCTION.value,
    "completed": BusinessStage.DONE.value,
    "failed": BusinessStage.BLOCKED.value,
    "rejected": BusinessStage.BLOCKED.value,
    "cancelled": BusinessStage.BLOCKED.value,
}


def canonical_agent_id(value: str) -> str:
    normalized = (value or "").strip().lower()
    for agent in MARKETING_AGENT_REGISTRY:
        if normalized == agent["id"] or normalized in agent.get("aliases", []):
            return agent["id"]
    return normalized


def execution_agent_id(agent_id: str) -> str:
    return CANONICAL_AGENT_EXECUTION_ALIASES.get(canonical_agent_id(agent_id), agent_id)


def prompt_agent_id(agent_id: str) -> str:
    canonical = canonical_agent_id(agent_id)
    return CANONICAL_AGENT_PROMPT_ALIASES.get(agent_id, CANONICAL_AGENT_PROMPT_ALIASES.get(canonical, canonical))


def board_aliases(board_id: str) -> List[str]:
    return BOARD_ALIASES.get(board_id, [board_id])


@dataclass
class ApprovalPolicy:
    required: bool = False
    categories: List[ApprovalCategory] = field(default_factory=list)
    approver_role: str = "elena"
    risk_level: str = "low"
    blocking: bool = True
    reason: Optional[str] = None


@dataclass
class AgentCommunicationEnvelope:
    from_agent: str
    to_agent: str
    type: CommunicationType
    task: str
    priority: AgentPriority = AgentPriority.P2
    context: Dict[str, Any] = field(default_factory=dict)
    deadline: Optional[str] = None
    expected_output: Optional[str] = None
    status: BusinessStage = BusinessStage.BRIEFED
    approval_policy: ApprovalPolicy = field(default_factory=ApprovalPolicy)
    dependencies: List[str] = field(default_factory=list)
    handoff_payload: Dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "AgentCommunicationEnvelope":
        return AgentCommunicationEnvelope(
            from_agent=canonical_agent_id(self.from_agent),
            to_agent=canonical_agent_id(self.to_agent),
            type=self.type,
            task=self.task,
            priority=self.priority,
            context=dict(self.context),
            deadline=self.deadline,
            expected_output=self.expected_output,
            status=self.status,
            approval_policy=self.approval_policy,
            dependencies=list(self.dependencies),
            handoff_payload=dict(self.handoff_payload),
        )
