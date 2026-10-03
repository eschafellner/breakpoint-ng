"""Encrypted values remain plaintext only in application memory."""

import base64
import hashlib

from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from django.conf import settings
from django.db import models
from django.core.validators import MaxLengthValidator


class EncryptedCharField(models.CharField):
    prefix = "fernet:"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("validators", [MaxLengthValidator(34)])
        super().__init__(*args, **kwargs)

    def cipher(self):
        secrets = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
        return MultiFernet(
            [
                Fernet(
                    base64.urlsafe_b64encode(
                        hashlib.sha256(
                            ("breakpoint-ng:sepa:" + secret).encode()
                        ).digest()
                    )
                )
                for secret in secrets
            ]
        )

    def from_db_value(self, value, expression, connection):
        if value and value.startswith(self.prefix):
            try:
                return (
                    self.cipher().decrypt(value[len(self.prefix) :].encode()).decode()
                )
            except InvalidToken as exc:
                raise ValueError(
                    "SEPA-Daten können mit den konfigurierten Schlüsseln nicht entschlüsselt werden."
                ) from exc
        # Legacy values are encrypted by the accompanying data migration.
        return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value:
            return self.prefix + self.cipher().encrypt(value.encode()).decode()
        return value
