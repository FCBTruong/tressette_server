import json
import requests

from src.config.settings import settings

# Apple verification URLs
SANDBOX_URL = "https://sandbox.itunes.apple.com/verifyReceipt"
PRODUCTION_URL = "https://buy.itunes.apple.com/verifyReceipt"

def verify_apple_receipt(receipt_data):
    if settings.ENABLE_CHEAT:
        url = SANDBOX_URL
    else:
        url = PRODUCTION_URL 
    
    payload = {
        "receipt-data": receipt_data,  # The base64-encoded receipt
        "password": "YOUR_SHARED_SECRET",  # Only required for subscriptions
        "exclude-old-transactions": True  # Optional, reduces response size
    }
    
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    result = response.json()
    
    return result  # Apple's response

# Example Usage
receipt_data = "BASE64_ENCODED_RECEIPT_HERE"  # Get this from the iOS app
response = verify_apple_receipt(receipt_data)

print(response)
