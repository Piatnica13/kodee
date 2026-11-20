"""Version of the account consent rendered by the site and recorded on signup."""
from datetime import datetime, timezone
import hmac

from flask import current_app

CONSENT_VERSION = '2026-11-21.1'


def record_consent(user, accepted_at=None):
    user.privacy_consent_version = CONSENT_VERSION
    user.privacy_consented_at = accepted_at or datetime.now(timezone.utc)


def google_subject_marker(subject):
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode()
    return hmac.digest(key, b'google-signup:' + subject.encode(), 'sha256').hex()
