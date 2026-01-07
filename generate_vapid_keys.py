import base64
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

def generate_vapid_keys():
    # 1. Generate the Private Key (P-256 Curve)
    private_key = ec.generate_private_key(ec.SECP256R1())

    # 2. Derive the Public Key
    public_key = private_key.public_key()

    # 3. Serialize Private Key to an Integer to get the raw bytes (32 bytes)
    private_val = private_key.private_numbers().private_value
    private_bytes = private_val.to_bytes(32, byteorder='big')

    # 4. Serialize Public Key to Uncompressed format (65 bytes: 0x04 + x + y)
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )

    # 5. Encode both to URL-Safe Base64 (VAPID format)
    # Remove padding '=' for VAPID standard
    private_b64 = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')
    public_b64 = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip('=')

    print("-" * 40)
    print("VAPID KEYS GENERATED SUCCESSFULLY")
    print("-" * 40)
    print(f"\n[PRIVATE KEY] (Keep this secret! Paste into notification_routes.py):\n{private_b64}")
    print(f"\n[PUBLIC KEY] (Save this! You will need it for the Frontend later):\n{public_b64}")
    print("-" * 40)

if __name__ == "__main__":
    generate_vapid_keys()