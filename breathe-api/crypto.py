"""Field-level encryption for sensitive data (CE Broker credentials, etc.)."""
import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def get_cipher() -> Fernet | None:
    """Get Fernet cipher from env var. Returns None if key not set."""
    key = os.environ.get("BREATHE_ENCRYPTION_KEY")
    if not key:
        logger.warning("BREATHE_ENCRYPTION_KEY not set — CE Broker sync disabled")
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.error(f"Invalid encryption key: {e}")
        return None


def encrypt_field(plaintext: str) -> str | None:
    """Encrypt a string. Returns None if encryption key not available."""
    cipher = get_cipher()
    if not cipher or not plaintext:
        return None
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt_field(ciphertext: str) -> str | None:
    """Decrypt a string. Returns None if decryption fails."""
    cipher = get_cipher()
    if not cipher or not ciphertext:
        return None
    try:
        return cipher.decrypt(ciphertext.encode()).decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return None


def is_encryption_available() -> bool:
    """Check if encryption is configured."""
    return get_cipher() is not None