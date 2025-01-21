import json
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SERVICE_ACCOUNT_FILE = "secrets/gg_play_console.json"
PACKAGE_NAME = "com.clareentertainment.tressette"
SCOPES = ['https://www.googleapis.com/auth/androidpublisher']

# Create credentials from service account file
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)


async def verify_purchase(purchase_token, product_id):
    """Verifies a purchase token with the Google Play Developer API."""
    try:
        service = build('androidpublisher', 'v3', credentials=credentials)
        request = service.purchases().products().get(
            packageName=PACKAGE_NAME,
            productId=product_id,  # IMPORTANT: Provide the product ID
            token=purchase_token
        )
        response = request.execute()

        return response
    except Exception as e:
        print(f"Error verifying purchase: {e}")
        return False

# For subscriptions
async def acknowledge_purchase(purchase_token, product_id) -> bool:  
    """Acknowledges a purchase. This is usually what you want for non-consumables."""
    try:
        service = build('androidpublisher', 'v3', credentials=credentials)
        request = service.purchases().products().acknowledge(
            packageName=PACKAGE_NAME,
            productId=product_id,  # Specify the product ID here
            token=purchase_token,
            body={}  # Empty body for acknowledge
        )
        response = request.execute()
        print(f"Purchase acknowledged: {response}")

        return True

    except Exception as e:
        print(f"Error acknowledging purchase: {e}")
        return False

# For consumables
async def consume_purchase(purchase_token: str, product_id: str) -> bool:
    """Consumes a consumable purchase. This is necessary for consumable items."""
    try:
        service = build('androidpublisher', 'v3', credentials=credentials)
        request = service.purchases().products().consume(
            packageName=PACKAGE_NAME,
            productId=product_id,  # Provide the product ID
            token=purchase_token
        )
        response = request.execute()
        print(f"Purchase consumed: {response}")
        return True
    except Exception as e:
        print(f"Error consuming purchase: {e}")
        return False


