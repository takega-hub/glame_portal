import logging
import re
from uuid import UUID

from sqlalchemy import delete, update, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.session import Session
from app.models.purchase_history import PurchaseHistory
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.onec_user_sync_job import OneCUserSyncJob
from app.models.saved_look import SavedLook
from app.models.look import Look
from app.models.marketing_campaign import MarketingCampaign
from app.models.website_visit import WebsiteVisit
from app.models.analytics_event import AnalyticsEvent
from app.models.content_plan import ContentPlan
from app.models.customer_message import CustomerMessage
from app.models.user_segment import UserSegment
from app.models.agent_system_prompt import AgentSystemPrompt, AgentPromptVersionHistory, AgentPromptGenerationRequest


logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("8"):
        return "7" + digits[1:]
    if len(digits) == 10:
        return "7" + digits
    return digits


class UserDeletionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def delete_user_by_phone(self, phone: str) -> bool:
        phone_norm = normalize_phone(phone)
        if not phone_norm:
            return False
        result = await self.db.execute(select(User).where(User.phone == phone_norm))
        user = result.scalar_one_or_none()
        if not user:
            return False
        await self.delete_user_by_id(user.id)
        return True

    async def delete_user_by_id(self, user_id: UUID) -> None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return

        if getattr(user, "email", None) == "portal@internal":
            return

        await self.db.execute(update(AgentSystemPrompt).where(AgentSystemPrompt.created_by == user_id).values(created_by=None))
        await self.db.execute(update(AgentSystemPrompt).where(AgentSystemPrompt.approved_by == user_id).values(approved_by=None))
        await self.db.execute(update(AgentPromptVersionHistory).where(AgentPromptVersionHistory.changed_by == user_id).values(changed_by=None))
        await self.db.execute(update(AgentPromptGenerationRequest).where(AgentPromptGenerationRequest.created_by == user_id).values(created_by=None))

        await self.db.execute(delete(LoyaltyTransaction).where(LoyaltyTransaction.user_id == user_id))
        await self.db.execute(delete(LoyaltyTransaction).where(LoyaltyTransaction.created_by == user_id))

        await self.db.execute(delete(PurchaseHistory).where(PurchaseHistory.user_id == user_id))
        await self.db.execute(delete(Session).where(Session.user_id == user_id))
        await self.db.execute(delete(OneCUserSyncJob).where(OneCUserSyncJob.user_id == user_id))
        await self.db.execute(delete(SavedLook).where(SavedLook.user_id == user_id))
        await self.db.execute(delete(Look).where(Look.user_id == user_id))
        await self.db.execute(delete(UserSegment).where(UserSegment.user_id == user_id))
        await self.db.execute(delete(CustomerMessage).where(CustomerMessage.user_id == user_id))
        await self.db.execute(delete(ContentPlan).where(ContentPlan.user_id == user_id))
        await self.db.execute(delete(MarketingCampaign).where(MarketingCampaign.user_id == user_id))
        await self.db.execute(delete(WebsiteVisit).where(WebsiteVisit.user_id == user_id))
        await self.db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.user_id == user_id))

        await self.db.execute(delete(User).where(User.id == user_id))
        await self.db.commit()

