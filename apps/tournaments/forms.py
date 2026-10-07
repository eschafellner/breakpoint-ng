from django import forms


class DrawCompetitionForm(forms.Form):
    snapshot = forms.CharField(widget=forms.HiddenInput)
    confirm = forms.BooleanField(
        label="Ich habe die Teilnehmer geprüft. Die Auslosung schließt die Anmeldung für das gesamte Turnier.",
    )
