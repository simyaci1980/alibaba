
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
	resim = models.ImageField(upload_to='urun_resimleri/', blank=True, null=True)  # Tek resim desteği devam etsin

	def __str__(self):
		return self.isim


# Çoklu resim desteği
class UrunResim(models.Model):
	urun = models.ForeignKey(Urun, on_delete=models.CASCADE, related_name='resimler')
	resim = models.ImageField(upload_to='urun_resimleri/')
	sira = models.PositiveIntegerField(default=0, help_text="Resim sırası (isteğe bağlı)")

	def __str__(self):
		return f"{self.urun.isim} - Resim {self.id}"


class Fiyat(models.Model):
	urun = models.ForeignKey(Urun, on_delete=models.CASCADE, related_name='fiyatlar')
	magaza = models.ForeignKey(Magaza, on_delete=models.CASCADE)
	fiyat = models.DecimalField(max_digits=10, decimal_places=2)
	affiliate_link = models.URLField()

	def __str__(self):
		return f"{self.urun.isim} - {self.magaza.isim}"

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
	link_type = models.CharField(max_length=20)  # 'amazon' veya 'aliexpress'
	timestamp = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.link_type} - {self.timestamp}"
