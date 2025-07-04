from django import forms
from django.contrib.admin.helpers import ActionForm


class DuplicateProductForm(ActionForm):
    number_of_copies = forms.IntegerField(
        min_value=1,
        initial=1,
        required=False,
        widget=forms.NumberInput(attrs={"title": "How many copies?"}),
    )
