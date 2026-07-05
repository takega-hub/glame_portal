import re
from typing import Optional, Dict, Any
from datetime import date
from pydantic import BaseModel, EmailStr, field_validator


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("8"):
        return "7" + digits[1:]
    if len(digits) == 10:
        return "7" + digits
    return digits


class OneCUserRegistrationPayload(BaseModel):
    phone: str
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    inn: Optional[str] = None
    birth_date: Optional[date] = None
    loyalty_program_key: Optional[str] = None
    source: Optional[str] = None
    customer_group_key: Optional[str] = None
    skip_welcome_bonus: bool = False
    welcome_bonus_points: Optional[int] = None
    welcome_bonus_comment: Optional[str] = None
    referral_code: Optional[str] = None
    referral_url: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        phone_norm = normalize_phone(v)
        if not phone_norm or len(phone_norm) < 10:
            raise ValueError("Некорректный телефон")
        return phone_norm

    @field_validator("inn")
    @classmethod
    def _validate_inn(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        digits = re.sub(r"\D", "", v)
        if not digits:
            return None
        if len(digits) not in (10, 12):
            raise ValueError("ИНН должен содержать 10 или 12 цифр")
        return digits

    def to_job_payload(self) -> Dict[str, Any]:
        return {
            "phone": self.phone,
            "full_name": self.full_name,
            "email": str(self.email).lower() if self.email else None,
            "inn": self.inn,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
            "loyalty_program_key": self.loyalty_program_key,
            "source": self.source,
            "customer_group_key": self.customer_group_key,
            "skip_welcome_bonus": self.skip_welcome_bonus,
            "welcome_bonus_points": self.welcome_bonus_points,
            "welcome_bonus_comment": self.welcome_bonus_comment,
            "referral_code": self.referral_code,
            "referral_url": self.referral_url,
        }
