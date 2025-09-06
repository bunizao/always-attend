import pyotp


def gen_totp(secret: str) -> str:
    """Generate a TOTP code from a shared secret."""
    return pyotp.TOTP(secret).now()

