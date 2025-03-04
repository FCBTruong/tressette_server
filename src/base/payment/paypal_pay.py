from datetime import datetime, timedelta
import httpx
import asyncio
import time

from sqlalchemy import func, select  # Used for token expiration tracking

from src.config.settings import settings
from src.postgres.orm import PsqlOrm
from src.postgres.sql_models import PayPalOrder
from src.base.payment import payment_mgr  # Import once

# PayPal API Credentials
PAYPAL_CLIENT_ID = "Addl0J3coQd3ET8opHfWZt6hPmZDexasIgPRjCJTb2HwlZh9TMhM4zzgY4OOG5XELUmFSKbcAkIcJEgA"
PAYPAL_CLIENT_SECRET = "EIk-kYZ5-sjHPj-iBLPXK0c9YsE4poVN3_ZIL5XhV-TEE2AcC6Yge85zU2HXQRteLd2ZJk3JlfZ6NGa9"
PAYPAL_API_URL = "https://api-m.sandbox.paypal.com"  # Use "https://api-m.paypal.com" for live

# In-memory cache for PayPal access token
paypal_access_token = None
paypal_token_expires_at = 0  # Timestamp of expiration

if not settings.ENABLE_CHEAT:
    PAYPAL_API_URL = "https://api-m.paypal.com"
    PAYPAL_CLIENT_ID = 'AYTpfl5u55R8KCKvQ0dTVmN0hbcvMbPf1NT4LRMGIERqZkh3VDzkeTF2zh4ojx35QR6H1cZuG_zvt5dR'
    PAYPAL_CLIENT_SECRET = 'ECQStY6ooJgS2SbN2YWzCDrKq4la_L1j5sFCvEm_1P02UO8iHRo--AMB9viAzQXUlOcNnaIOHGc_wOR6'

async def get_paypal_access_token():
    """Obtain a PayPal access token and cache it."""
    global paypal_access_token, paypal_token_expires_at

    # If token is still valid, return it
    if paypal_access_token and time.time() < paypal_token_expires_at:
        return paypal_access_token

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PAYPAL_API_URL}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            headers={"Accept": "application/json", "Accept-Language": "en_US"}
        )
        response.raise_for_status()
        data = response.json()

        paypal_access_token = data.get("access_token")
        expires_in = data.get("expires_in", 32000)  # Default to ~9 hours
        paypal_token_expires_at = time.time() + expires_in - 60  # Subtract 60s for buffer

        return paypal_access_token


async def create_paypal_order(uid: int, amount: float, pack_id: int, currency="EUR"):
    # to prevent spamming, we should check if user already has a pending order
    async with PsqlOrm.get().session() as session:
        existing_order = await session.scalar(
            select(PayPalOrder).where(
                (PayPalOrder.user_id == uid) &
                (PayPalOrder.pack_id == pack_id) &
                (PayPalOrder.status == "CREATED") &
                (PayPalOrder.created_at >= func.now() - timedelta(hours=24))
            )
        )


        if existing_order:
            print("User already has a pending order with this pack.", pack_id, existing_order.order_id)
            return existing_order.order_url
        else:
            print("No pending order found, proceed with creating a new one.")
    """Create a PayPal order and get the payment link."""
    access_token = await get_paypal_access_token()

    order_data = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {
                "currency_code": currency,
                "value": str(amount)
            }
        }],
        "application_context": {
            "return_url": settings.SERVER_URL + "/paypal/success",
            "cancel_url": settings.SERVER_URL + "/paypal/cancel"
        }
    }

    async with httpx.AsyncClient() as client, PsqlOrm.get().session() as session:
        response = await client.post(
            f"{PAYPAL_API_URL}/v2/checkout/orders",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            },
            json=order_data
        )
        response.raise_for_status()
        order = response.json()

        order_url = None
        for link in order.get("links", []):
            if link.get("rel") == "approve":
                order_url = link.get("href")
                break
    
        new_order = PayPalOrder(
            order_id=order["id"],
            user_id=uid,
            pack_id=pack_id,
            amount=amount,
            currency=currency,
            status=order.get("status"),
            order_url=order_url
        )
        session.add(new_order)
        await session.commit()

    return order_url


async def capture_paypal_order(order_id: str):
    """Capture a PayPal order after user approves it."""
    access_token = await get_paypal_access_token()

    async with httpx.AsyncClient() as client, PsqlOrm.get().session() as session:
        response = await client.post(
            f"{PAYPAL_API_URL}/v2/checkout/orders/{order_id}/capture",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            }
        )
        response.raise_for_status()
        capture_info = response.json()
        print("Capture info:", capture_info)

        status = capture_info.get("status", "FAILED")
        payer_id = capture_info.get("payer", {}).get("payer_id", None)

        order = await session.get(PayPalOrder, order_id)
        if order:
            order.status = status
            order.payer_id = payer_id
            await session.commit()

    return status


async def handle_paypal_success(token: str, payer_id: str):
    # check if order is exist in db
    async with PsqlOrm.get().session() as session:
        order = await session.get(PayPalOrder, token)
        if not order:
            return "FAILED"
        
        user_id, pack_id = order.user_id, order.pack_id 
        
    access_token = await get_paypal_access_token()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PAYPAL_API_URL}/v2/checkout/orders/{token}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        order_info = response.json()
        print("Order info:", order_info)

        if order_info.get("status") != "APPROVED":
            return "FAILED"

        status = await capture_paypal_order(token)
        if status == "COMPLETED":
            await payment_mgr._purchase_success(user_id, pack_id, "paypal")

        return status
