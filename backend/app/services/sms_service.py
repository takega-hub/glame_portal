import httpx
import os
import time
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class SMSAeroService:
    BASE_URL = "https://gate.smsaero.ru/v2"

    def __init__(self, email: str, api_key: str):
        self.email = email
        self.api_key = api_key
        self.auth = (email, api_key)

    async def _request(self, method: str, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(method, url, params=params, auth=self.auth)
                response.raise_for_status()
                data = response.json()
                if not data.get("success"):
                    logger.error(f"SMS Aero API error: {data.get('message')}")
                    # Don't raise exception immediately, return data so caller can handle
                    # or raise here if we want strict behavior.
                    # SMS Aero returns 200 OK even for logical errors sometimes, but with success=False
                    if "message" in data:
                        raise Exception(data["message"])
                    raise Exception("Unknown error from SMS Aero")
                return data
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error SMS Aero: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Failed to request SMS Aero: {e}")
                raise

    async def check_auth(self) -> bool:
        """Check if authentication is valid."""
        try:
            await self._request("GET", "auth")
            return True
        except Exception:
            return False

    async def send_sms(self, number: str, text: str, sign: str = "GLAME", date_send: Optional[int] = None) -> Dict[str, Any]:
        """
        Send a single SMS message.
        :param number: Phone number.
        :param text: Message text.
        :param sign: Sender signature.
        :param date_send: Unix timestamp for scheduled sending.
        """
        params = {
            "number": number,
            "text": text,
            "sign": sign,
        }
        if date_send:
            params["dateSend"] = date_send
        
        return await self._request("GET", "sms/send", params=params)

    async def send_bulk_sms(self, numbers: List[str], text: str, sign: str = "GLAME", date_send: Optional[int] = None) -> Dict[str, Any]:
        """
        Send SMS to multiple numbers (bulk).
        :param numbers: List of phone numbers.
        :param text: Message text.
        :param sign: Sender signature.
        :param date_send: Unix timestamp for scheduled sending.
        """
        # SMS Aero supports array of numbers in `numbers[]` parameter
        # httpx handles list params by repeating the key if we pass a list of tuples or similar structure
        # but for query params, httpx supports list values directly for repeated keys.
        params = {
            "text": text,
            "sign": sign,
            "numbers[]": numbers 
        }
        
        if date_send:
            params["dateSend"] = date_send

        # Note: httpx query params with list: {"key": ["v1", "v2"]} results in key=v1&key=v2
        # SMS Aero expects numbers[]=v1&numbers[]=v2
        # So we need to be careful.
        # Let's verify httpx behavior or construct query string manually/carefully.
        
        # httpx way:
        query_params = []
        query_params.append(("text", text))
        query_params.append(("sign", sign))
        if date_send:
            query_params.append(("dateSend", str(date_send)))
        for num in numbers:
            query_params.append(("numbers[]", num))
            
        return await self._request("GET", "sms/send", params=query_params)

    async def check_status(self, sms_id: int) -> Dict[str, Any]:
        """
        Check status of a sent message.
        :param sms_id: ID of the message returned by send_sms.
        """
        return await self._request("GET", "sms/status", params={"id": sms_id})

# Singleton instance
# Initialize with environment variables or config
sms_service = None

def get_sms_service() -> Optional[SMSAeroService]:
    global sms_service
    if not sms_service:
        email = os.getenv("SMS_AERO_EMAIL")
        api_key = os.getenv("SMS_AERO_API_KEY")
        if email and api_key:
            sms_service = SMSAeroService(email, api_key)
    return sms_service
