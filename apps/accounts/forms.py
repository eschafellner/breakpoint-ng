from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .models import User


class AdminAccountCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name", "account_type")


class AdminAccountChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


class LoginForm(forms.Form):
    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

    email = forms.EmailField(
        label=_("E-Mail-Adresse"),
        widget=forms.EmailInput(
            attrs={"class": "input", "placeholder": "name@example.com"}
        ),
    )
    password = forms.CharField(
        label=_("Passwort"),
        widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "••••••••"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if email and password:
            user = authenticate(
                self.request, username=email, password=password
            )
            if not user:
                raise forms.ValidationError(
                    _("E-Mail oder Passwort ist nicht korrekt.")
                )
            self.user = user
        return cleaned_data


class AccountRecoveryForm(forms.Form):
    email = forms.EmailField(
        label=_("E-Mail-Adresse"),
        widget=forms.EmailInput(attrs={"class": "input", "autocomplete": "email"}),
    )


class RegistrationForm(forms.Form):
    REG_CHOICES = (
        ("GUEST", _("Als Gast registrieren (sofort buchen nach E-Mail-Bestätigung)")),
        ("MEMBER", _("Mitgliedschaft beantragen (nach Freischaltung volles Mitglied)")),
    )

    account_type = forms.ChoiceField(
        label=_("Registrierungsart"),
        choices=REG_CHOICES,
        widget=forms.RadioSelect,
        initial="GUEST",
    )
    email = forms.EmailField(
        label=_("E-Mail-Adresse"),
        widget=forms.EmailInput(
            attrs={"class": "input", "placeholder": "name@example.com"}
        ),
    )
    first_name = forms.CharField(label=_("Vorname"), max_length=50)
    last_name = forms.CharField(label=_("Nachname"), max_length=50)
    phone = forms.CharField(label=_("Telefonnummer"), max_length=50, required=False)
    birth_date = forms.DateField(
        label=_("Geburtsdatum"),
        widget=forms.DateInput(attrs={"type": "date"}),
        required=False,
    )
    address_street = forms.CharField(
        label=_("Straße & Hausnr."), max_length=150, required=False
    )
    address_zip = forms.CharField(label=_("PLZ"), max_length=20, required=False)
    address_city = forms.CharField(label=_("Ort"), max_length=100, required=False)

    password = forms.CharField(
        label=_("Passwort (mind. 8 Zeichen)"),
        widget=forms.PasswordInput(attrs={"class": "input"}),
        min_length=8,
    )
    password_confirm = forms.CharField(
        label=_("Passwort wiederholen"),
        widget=forms.PasswordInput(attrs={"class": "input"}),
    )

    membership_type = forms.ChoiceField(
        label=_("Gewünschte Mitgliedschaftsart"),
        required=False,
    )
    sepa_iban = forms.CharField(
        label=_("SEPA IBAN (optional)"),
        max_length=34,
        required=False,
    )

    consent_privacy = forms.BooleanField(
        label=_("Ich stimme der Datenschutzerklärung und der Vereinssatzung zu."),
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate membership types dynamically
        try:
            from apps.members.models import MembershipType

            types = MembershipType.objects.filter(is_active=True)
            self.fields["membership_type"].choices = [("", _("– Bitte wählen –"))] + [
                (
                    t.id,
                    f"{t.name} ({t.fee_amount} € / {t.get_billing_interval_display()})",
                )
                for t in types
            ]
        except Exception:
            self.fields["membership_type"].choices = [("", _("Standard"))]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                _("Diese E-Mail-Adresse ist bereits registriert.")
            )
        return email

    def clean_birth_date(self):
        value = self.cleaned_data.get("birth_date")
        if value and value > timezone.localdate():
            raise forms.ValidationError(
                _("Das Geburtsdatum darf nicht in der Zukunft liegen.")
            )
        return value

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error(
                "password_confirm", _("Die Passwörter stimmen nicht überein.")
            )
        if p1:
            candidate = User(
                email=cleaned_data.get("email", ""),
                first_name=cleaned_data.get("first_name", ""),
                last_name=cleaned_data.get("last_name", ""),
            )
            try:
                validate_password(p1, user=candidate)
            except forms.ValidationError as exc:
                self.add_error("password", exc)

        acct = cleaned_data.get("account_type")
        mem_type = cleaned_data.get("membership_type")
        if acct == "MEMBER" and not mem_type:
            self.add_error(
                "membership_type", _("Bitte wähle eine Mitgliedschaftsart aus.")
            )
        if acct == "GUEST" and mem_type:
            self.add_error(
                "membership_type",
                _("Bitte wähle die Registrierung als Mitgliedschaftsantrag."),
            )

        return cleaned_data


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone",
            "birth_date",
            "address_street",
            "address_zip",
            "address_city",
            "avatar",
            "allow_partner_search",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
        }
