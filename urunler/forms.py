from django import forms
from .models import Yorum

class YorumForm(forms.ModelForm):
    class Meta:
        model = Yorum
        fields = ['isim', 'yorum', 'email', 'telefon']
        widgets = {
            'isim': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Adınız'}),
            'yorum': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Yorumunuz', 'rows': 3}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'E-posta (isteğe bağlı)'}),
            'telefon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Telefon (isteğe bağlı)'}),
        }