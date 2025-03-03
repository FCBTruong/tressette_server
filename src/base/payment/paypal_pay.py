import httpx
import asyncio

# PayPal API Credentials
PAYPAL_CLIENT_ID = "Af6QXXBg_SbDASiFfnejhQsBIeDLYhGAeG-gY1Jqo1RsFupCppf6PR8kImjse1kzjUVhAsND7Ap3i6iO"
PAYPAL_CLIENT_SECRET = "EGImIaH5u0CbmuERGrvdDxnf6yaU7CCgFr99O9CNRHjeWd_nnESM7pYZ3UrqDrwmnZb0KrAkyU7CE7Fw"
PAYPAL_API_URL = "https://api-m.sandbox.paypal.com"  # Change to "https://api-m.paypal.com" for live

async def get_paypal_access_token():
    """Obtain an access token from PayPal."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PAYPAL_API_URL}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            headers={"Accept": "application/json", "Accept-Language": "en_US"}
        )
        response.raise_for_status()
        return response.json()["access_token"]

async def create_paypal_order(amount, pack_id):
    return_url="https://yourgame.com/success"
    cancel_url="https://yourgame.com/cancel"
    currency="USD"

    """Create a PayPal order and get the payment link."""
    access_token = await get_paypal_access_token()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PAYPAL_API_URL}/v2/checkout/orders",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            },
            json={
                "intent": "AUTHORIZE",
                "purchase_units": [{
                    "amount": {
                        "currency_code": currency,
                        "value": str(amount)
                    }
                }],
                "application_context": {
                    "return_url": return_url,
                    "cancel_url": cancel_url
                }
            }
        )
        response.raise_for_status()
        order = response.json()
    
    # Extract the approval link for user payment
    for link in order["links"]:
        if link["rel"] == "approve":
            return link["href"]
    
    return None




from fastapi import FastAPI, Request
app = FastAPI()

PAYPAL_WEBHOOK_ID = "YOUR_WEBHOOK_ID"  # Get this from PayPal
async def verify_webhook(request: Request):
    """Verify PayPal webhook signature."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PAYPAL_API_URL}/v1/notifications/verify-webhook-signature",
            headers=headers,
            json={
                "auth_algo": request.headers.get("PAYPAL-AUTH-ALGO"),
                "cert_url": request.headers.get("PAYPAL-CERT-URL"),
                "transmission_id": request.headers.get("PAYPAL-TRANSMISSION-ID"),
                "transmission_sig": request.headers.get("PAYPAL-TRANSMISSION-SIG"),
                "transmission_time": request.headers.get("PAYPAL-TRANSMISSION-TIME"),
                "webhook_id": PAYPAL_WEBHOOK_ID,
                "webhook_event": await request.json(),
            }
        )
        return response.json().get("verification_status") == "SUCCESS"

async def paypal_webhook(request: Request):
    print("PayPal webhook received")
    """Handle PayPal webhook events."""
    if not await verify_webhook(request):
        return {"status": "error", "message": "Invalid webhook"}

    data = await request.json()
    event_type = data.get("event_type")

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        order_id = data["resource"]["id"]
        payer_email = data["resource"]["payer"]["email_address"]
        amount = data["resource"]["amount"]["value"]

        # TODO: Mark order as paid in your database
        print(f"Payment received: {amount} from {payer_email} (Order ID: {order_id})")
    elif event_type in ["PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.REVERSED"]:
        order_id = data["resource"]["id"]
        print(f"Payment failed or reversed for order {order_id}")

    return {"status": "success"}
