
from django.db import models
from django.contrib.auth.models import User

class Magaza(models.Model):
	isim = models.CharField(max_length=100)
	web_adresi = models.URLField(blank=True)

	def __str__(self):
		return self.isim


class Urun(models.Model):
	isim = models.CharField(max_length=200)
	aciklama = models.TextField(blank=True)
	resim = models.ImageField(upload_to='urun_resimleri/', blank=True, null=True)  # Dosya yükleme için
	resim_url = models.URLField(max_length=500, blank=True, null=True, help_text='Resim URL (yer kaplamaz)')  # URL için

	def __str__(self):
		return self.isim


# Çoklu resim desteği
class UrunResim(models.Model):
	urun = models.ForeignKey(Urun, on_delete=models.CASCADE, related_name='resimler')
	resim = models.ImageField(upload_to='urun_resimleri/', blank=True, null=True)  # Dosya yükleme için
	resim_url = models.URLField(max_length=500, blank=True, null=True, help_text='Resim URL (yer kaplamaz)')  # URL için
	sira = models.PositiveIntegerField(default=0, help_text="Resim sırası (isteğe bağlı)")

	def __str__(self):
		return f"{self.urun.isim} - Resim {self.id}"


class Fiyat(models.Model):
	PARA_BIRIMI_CHOICES = [
		('TL', 'Türk Lirası (₺)'),
		('USD', 'ABD Doları ($)'),
	]
	
	urun = models.ForeignKey(Urun, on_delete=models.CASCADE, related_name='fiyatlar')
	magaza = models.ForeignKey(Magaza, on_delete=models.CASCADE)
	fiyat = models.DecimalField(max_digits=10, decimal_places=2)
	para_birimi = models.CharField(max_length=3, choices=PARA_BIRIMI_CHOICES, default='TL', help_text='Fiyat hangi para biriminde')
	affiliate_link = models.URLField()

	def __str__(self):
		sembol = '₺' if self.para_birimi == 'TL' else '$'
		return f"{self.urun.isim} - {self.magaza.isim} ({self.fiyat} {sembol})"

# Kullanıcı yorumları için model
class Yorum(models.Model):
	isim = models.CharField(max_length=100)
	yorum = models.TextField()
	eklenme_tarihi = models.DateTimeField(auto_now_add=True)
	onayli = models.BooleanField(default=False, verbose_name="Onaylı mı?")
	email = models.EmailField(blank=True, null=True, verbose_name="E-posta (isteğe bağlı)")
	telefon = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telefon (isteğe bağlı)")

	def __str__(self):
		return f"{self.isim} - {self.eklenme_tarihi:%Y-%m-%d}" 
    
class ClickLog(models.Model):
	user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
	link_type = models.CharField(max_length=20)  # 'amazon', 'aliexpress', 'urun_affiliate' vb.
	urun = models.ForeignKey(Urun, null=True, blank=True, on_delete=models.SET_NULL)
	timestamp = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.link_type} - {self.urun} - {self.timestamp}"
