"""Signed, expiring tokens for email verification."""

from django.core import signing

VERIFY_SALT = 'healthwise.email.verify'
VERIFY_MAX_AGE = 60 * 60 * 24 * 3


def make_verification_token(user):
    return signing.dumps(
        {'uid': user.pk, 'email': user.email},
        salt=VERIFY_SALT,
        compress=True,
    )


def read_verification_token(token, max_age=VERIFY_MAX_AGE):
    try:
        return signing.loads(token, salt=VERIFY_SALT, max_age=max_age)
    except (signing.BadSignature, signing.SignatureExpired):
        return None
