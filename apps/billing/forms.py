from django import forms
from .models import Charge
from .services import quantize_amount


class ChargeCreationForm(forms.ModelForm):
    class Meta:
        model = Charge
        fields = "__all__"

    def clean_amount(self):
        try:
            amount = quantize_amount(self.cleaned_data["amount"])
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        if amount <= 0:
            raise forms.ValidationError(
                "Der Forderungsbetrag muss größer als null sein."
            )
        return amount

    def clean(self):
        data = super().clean()
        if (
            data.get("period_start")
            and data.get("period_end")
            and data["period_start"] > data["period_end"]
        ):
            self.add_error(
                "period_end", "Das Periodenende muss nach dem Beginn liegen."
            )
        return data
