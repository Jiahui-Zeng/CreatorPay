import http.client
import json
import uuid

import time

import base64
import codecs
# Installed by `pip install pycryptodome`
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256

# Define the subscription fee and renewal period (e.g., 30 days)
subscription_fee = "0.01"  
renewal_period_seconds = 60 # 30 * 24 * 60 * 60  30 days in seconds

# Define your API key and encryption functions
APIKEY = "YOUR_API_KEY"  # Replace with your actual API key
SECRET = "SECRET_KEY"
PUBLIC_KEY = "PUBLICKEY_KEY"

headers = {
        'Content-Type': "application/json",
        'Authorization': f"Bearer {APIKEY}"
    }

# Encrypt the Entity Secret to entitySecretCiphertext
def encrypt_secret():

    entity_secret = bytes.fromhex(SECRET)

    if len(entity_secret) != 32:
        print("invalid entity secret")
        exit(1)

    public_key = RSA.importKey(PUBLIC_KEY)

    # encrypt data by the public key
    cipher_rsa = PKCS1_OAEP.new(key=public_key, hashAlgo=SHA256)
    encrypted_data = cipher_rsa.encrypt(entity_secret)

    # encode to base64
    encrypted_data_base64 = base64.b64encode(encrypted_data)

    secret_ciphertext = encrypted_data_base64.decode()
    return secret_ciphertext

# Check wallet balance
def check_wallet_balance(wallet_id):
    conn = http.client.HTTPSConnection("api.circle.com") 
    conn.request("GET", f"/v1/w3s/developer/wallets/{wallet_id}/balances", headers=headers)
    res = conn.getresponse()
    data = json.loads(res.read())
    return data['data']['tokenBalances']['amount'] # double check

# Transfer transaction
def transfer_tokens(token_id, sender_wallet_id, receiver_wallet_addr, amount):
    conn = http.client.HTTPSConnection("api.circle.com")

    payload = {
        "idempotencyKey": str(uuid.uuid4()),
        "entitySecretCipherText": encrypt_secret(),
        "amounts": [amount],
        "feeLevel": "MEDIUM",
        "tokenId": token_id,
        "walletId": sender_wallet_id,
        "destinationAddress": receiver_wallet_addr
    }
    conn.request("POST", "/v1/w3s/developer/transactions/transfer", json.dumps(payload), headers=headers)
    res = conn.getresponse()
    data = json.loads(res.read())
    # return data

# Create a wallet set for the creator
def create_wallet_set(creator_name):
    conn = http.client.HTTPSConnection("api.circle.com")
    payload = {
        "idempotencyKey": str(uuid.uuid4()),
        "entitySecretCipherText": encrypt_secret(),
        "name": creator_name
    }

    conn.request("POST", "/v1/w3s/developer/walletSets", json.dumps(payload), headers=headers)
    res = conn.getresponse()
    data = json.loads(res.read())
    return data['data']['walletSet']['id']

# Create wallets under a wallet set
def create_wallets(walletset_id, blockchain, count):
    conn = http.client.HTTPSConnection("api.circle.com")
    payload = {
        "idempotencyKey": str(uuid.uuid4()),
        "entitySecretCipherText": encrypt_secret(),
        "blockchains": [blockchain],
        "count": count,
        "walletSetId": walletset_id
    }

    conn.request("POST", "/v1/w3s/developer/wallets", json.dumps(payload), headers=headers)
    res = conn.getresponse()
    data = json.loads(res.read())
    return data['data']['wallets'][0]['id'], data['data']['wallets'][0]['address']

# Initiate scheduled token transfer for subscription renewal
def subscription_payment(token_id, user_wallet_id, creator_wallet_addr, amount):
    while True:
        # Check if user's wallet balance is sufficient for the subscription fee
        user_balance = check_wallet_balance(user_wallet_id)
        if float(user_balance) >= float(amount):
            # Transfer the subscription fee to the creator
            transfer_tokens(token_id, sender_wallet_id=user_wallet_id, receiver_wallet_addr=creator_wallet_addr, amount=amount)
            print("Subscription payment successful.")
        else:
            # Set subscription status to inactive or notify the user to top up
            print("Insufficient balance for subscription. Please top up your wallet.")
            break
        
        # Sleep for the renewal period
        time.sleep(renewal_period_seconds)

if __name__ == "__main__":
   
    # Adjust as needed
    transfer_blockchain = "ETH-GOERLI"
    token_id = "0x15aad21e7c1c400b71bc628c681e9e079b4bb966" # goerli_id
    start_amount = "0.25"
    transfer_amount = "0.001"  
    user_own_wallet_id = "8f73b36e-69b0-5f12-a20b-52248f7b9cd1"
    user_own_wallet_addr = "0xbf26ee4e44096cfd2a1929aa26b92ccb830e1b0a"

    # Creator creates a wallet set
    creator_walletset_id = create_wallet_set("CreatorPay")
    creator_wallet_id, creator_wallet_addr = create_wallets(creator_walletset_id, transfer_blockchain, 1)

    # User creates a wallet under the service provider's wallet set
    user_wallet_id, user_wallet_addr = create_wallets(creator_walletset_id, transfer_blockchain, 1)

    # User transfers tokens to their wallet   
    transfer_tokens(token_id=token_id, sender_wallet_id=user_own_wallet_id, receiver_wallet_addr=user_own_wallet_addr, amount=start_amount)

    # Start the subscription renewal process in the background
    subscription_payment(token_id=token_id, user_wallet_id=user_wallet_id, creator_wallet_addr=creator_wallet_addr, amount=subscription_fee)

    # User cancels the subscription and requests a refund
    if check_wallet_balance(user_wallet_id) > 0:
        # Refund remaining balance to the user's private wallet
        transfer_tokens(token_id=token_id, sender_wallet_id=user_wallet_id, receiver_wallet_addr=user_own_wallet_addr, amount=str(check_wallet_balance(user_wallet_id)))
    