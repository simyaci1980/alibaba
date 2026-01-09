from django import forms


class UrunEkleForm(forms.Form):
    """AliExpress linkinden otomatik ürün ekleme formu"""
    aliexpress_url = forms.URLField(
        label='AliExpress Ürün Linki',
        max_length=1000,
        widget=forms.URLInput(attrs={
            'placeholder': 'https://www.aliexpress.com/item/...',
            'class': 'form-control'
        }),
        help_text='AliExpress ürün linkini buraya yapıştırın'
    )
    
    subid = forms.CharField(
        label='Takip Kodu (İsteğe Bağlı)',
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'kulaklık, saat, vb.',
            'class': 'form-control'
        }),
        help_text='Admitad\'da bu ürünü takip etmek için kod (opsiyonel)'
    )
