
from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
import re

class Magaza(models.Model):
	isim = models.CharField(max_length=100)
	web_adresi = models.URLField(blank=True)

	def __str__(self):
		return self.isim


class KategoriSema(models.Model):
	slug = models.SlugField(max_length=80, unique=True, help_text='Kategori URL kimligi (or. retro-handheld)')
	isim = models.CharField(max_length=120)
	alanlar = models.JSONField(default=list, blank=True, help_text='Kategoriye ozel alan semasi')
	aktif = models.BooleanField(default=True)

	class Meta:
		verbose_name = 'Kategori Semasi'
		verbose_name_plural = 'Kategori Semalari'

	def __str__(self):
		return self.isim


class Urun(models.Model):
	isim = models.CharField(max_length=200)
	aciklama = models.TextField(blank=True)
	ana_baslik = models.CharField(max_length=500, blank=True, verbose_name="Ana Başlık")
	alt_baslik = models.CharField(max_length=500, blank=True, verbose_name="Alt Başlık")
	etiketler = models.CharField(max_length=500, blank=True, verbose_name="Etiketler")
	ozellikler = models.TextField(blank=True, verbose_name="Özellikler")
	kategori = models.ForeignKey(KategoriSema, on_delete=models.SET_NULL, blank=True, null=True, related_name='urunler')
	detaylar = models.JSONField(default=dict, blank=True, help_text='Kategori semasina gore yapisal urun alanlari')
	slug = models.SlugField(max_length=255, unique=True, blank=True, null=True, db_index=True)
	durum = models.CharField(max_length=100, blank=True, null=True, verbose_name="Durum")
	resim = models.ImageField(upload_to='urun_resimleri/', blank=True, null=True)  # Dosya yükleme için
	resim_url = models.URLField(max_length=500, blank=True, null=True, help_text='Resim URL (yer kaplamaz)')  # URL için
	source_url = models.URLField(max_length=1000, blank=True, null=True, unique=True, help_text='Ürünün kaynak URL adresi (tekrarları önler)')
	urun_kodu = models.CharField(max_length=12, unique=True, blank=True, null=True, help_text='Kısa arama kodu (otomatik)')
	item_id = models.CharField(max_length=50, unique=True, blank=True, null=True, help_text='eBay ürün ID')
	sira = models.PositiveIntegerField(default=0, blank=True, null=True, help_text="Ürün sırası (küçükten büyüğe önde)")

	SLUG_STALE_PATTERN = re.compile(
		r'\b(el-tipi|oyun-konsolu|elde-tasinabilir|yeni|ucretsiz|ekran|cozunurluk|isletim-sistemi|baglanti|gonderim|kargo|abd)\b',
		re.IGNORECASE,
	)

	def _slug_source_text(self):
		return self.ana_baslik or self.isim or self.urun_kodu or 'urun'

	def _build_unique_slug(self, source_text=None):
		base_text = source_text or self._slug_source_text()
		base_slug = slugify(base_text)[:230] or f"urun-{self.urun_kodu or 'x'}"
		candidate = base_slug
		i = 2
		while Urun.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
			candidate = f"{base_slug[:220]}-{i}"
			i += 1
		return candidate

	def _should_refresh_slug(self):
		current_slug = str(self.slug or '').strip()
		if not current_slug:
			return True
		fresh_slug = self._build_unique_slug()
		if fresh_slug == current_slug:
			return False
		# Only auto-refresh slugs that still reflect stale Turkish wording.
		return bool(self.SLUG_STALE_PATTERN.search(current_slug))

	def save(self, *args, **kwargs):
		if self._should_refresh_slug():
			self.slug = self._build_unique_slug()
		super().save(*args, **kwargs)

	def __str__(self):
		return f"{self.isim} ({self.urun_kodu})" if self.urun_kodu else self.isim


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
	affiliate_link = models.URLField(max_length=1000)
	
	# Gönderim bilgileri
	gonderim_ucreti = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Kargo ücreti')
	gonderim_yerinden = models.CharField(max_length=100, default='Çin', help_text='Hangi ülkeden gönderiliyor')
	gonderim_durumu = models.BooleanField(default=True, help_text='Gönderilebiliyor mu?')
	ucretsiz_kargo = models.BooleanField(default=False, help_text='Ücretsiz kargo bilgisi eBay/API tarafından doğrulandı mı?')

	def __str__(self):
		sembol = '₺' if self.para_birimi == 'TL' else '$'
		return f"{self.urun.isim} - {self.magaza.isim} ({self.fiyat} {sembol})"
	
	@property
	def toplam_fiyat(self):
		"""Ürün fiyatı + Gönderim ücreti"""
		return self.fiyat + self.gonderim_ucreti

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
	subid = models.CharField(max_length=100, blank=True, null=True, help_text="Alt kimlik (ör: otomatik_0, admin, vs.)")
	gclid = models.CharField(max_length=120, blank=True, null=True, db_index=True)
	utm_source = models.CharField(max_length=150, blank=True, null=True)
	utm_medium = models.CharField(max_length=150, blank=True, null=True)
	utm_campaign = models.CharField(max_length=200, blank=True, null=True)
	utm_term = models.CharField(max_length=200, blank=True, null=True)
	utm_content = models.CharField(max_length=200, blank=True, null=True)
	landing_path = models.CharField(max_length=500, blank=True, null=True)
	referrer = models.CharField(max_length=1000, blank=True, null=True)
	client_ip = models.CharField(max_length=64, blank=True, null=True)
	user_agent = models.CharField(max_length=255, blank=True, null=True)
	timestamp = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.link_type} - {self.urun} - {self.timestamp}"
