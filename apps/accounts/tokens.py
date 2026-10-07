from django.contrib.auth.tokens import PasswordResetTokenGenerator


class AccountAccessTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return (
            super()._make_hash_value(user, timestamp)
            + str(user.email_verified)
            + str(user.account_access_sent_at)
        )


account_access_token_generator = AccountAccessTokenGenerator()
