def temiz_alisveris_linki(url):
	"""AliExpress linkinden tüm affiliate/utm/izleme parametrelerini temizle."""
	import urllib.parse
	parsed = urllib.parse.urlparse(url)
	# Sadece ana path ve zorunlu query parametreleri kalsın
	temiz_query = urllib.parse.parse_qs(parsed.query)
	# Tutulacak parametreler (hiçbiri, sadece path)
	allowed = set()
	temiz = {k: v for k, v in temiz_query.items() if k in allowed}
	new_query = urllib.parse.urlencode(temiz, doseq=True)
	# Sadece scheme, netloc, path
	return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', new_query, ''))
from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from decouple import config
import requests
import re
import json
from bs4 import BeautifulSoup
from .models import Magaza, Urun, Fiyat, UrunResim, Yorum, ClickLog
from .utils.deeplink import build_admitad_deeplink


class FiyatInline(admin.TabularInline):
	model = Fiyat
	extra = 1
	fields = ('magaza', 'fiyat', 'para_birimi', 'gonderim_ucreti', 'gonderim_yerinden', 'gonderim_durumu', 'affiliate_link')
	readonly_fields = ('toplam_fiyat_goster',)
	
	def toplam_fiyat_goster(self, obj):
		if obj.id:
			return f"{obj.toplam_fiyat:.2f} {obj.para_birimi}"
		return "-"
	toplam_fiyat_goster.short_description = "Toplam (Fiyat + Gönderim)"

class UrunResimInline(admin.TabularInline):
	model = UrunResim
	extra = 1


@admin.register(Yorum)
class YorumAdmin(admin.ModelAdmin):
	list_display = ("isim", "yorum", "eklenme_tarihi")


@admin.register(Urun)
class UrunAdmin(admin.ModelAdmin):
	list_display = ("isim", "resim_goster")
	inlines = [FiyatInline, UrunResimInline]
	readonly_fields = ("resim_goster",)

	def changelist_view(self, request, extra_context=None):
		from .models import Urun
		toplam_urun = Urun.objects.count()
		if extra_context is None:
			extra_context = {}
		extra_context['toplam_urun'] = toplam_urun
		return super().changelist_view(request, extra_context=extra_context)

	def resim_goster(self, obj):
		if obj.resim:
			return f'<img src="{obj.resim.url}" style="max-height:80px; max-width:120px;" />'
		return "-"
	resim_goster.allow_tags = True
	resim_goster.short_description = "Resim"
	
	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
			path('link-ekle/', self.admin_site.admin_view(self.link_ekle_view), name='urun_link_ekle'),
			path('amazon-link-ekle/', self.admin_site.admin_view(self.amazon_link_ekle_view), name='urun_amazon_link_ekle'),
		]
		return custom_urls + urls
	
	def link_ekle_view(self, request):
		"""AliExpress linkinden otomatik ürün ekleme"""
		if request.method == 'POST':
			url = request.POST.get('aliexpress_url', '').strip()
			# Linki temizle (sadece ana ürün linki kalsın)
			url = temiz_alisveris_linki(url)
			subid = request.POST.get('subid', 'admin').strip()
			manual_fiyat = request.POST.get('fiyat', '').strip()
			
			if not url:
				messages.error(request, 'Lütfen bir AliExpress linki girin!')
				return render(request, 'admin/urun_link_ekle.html', {
					'title': 'AliExpress Linkinden Ürün Ekle',
					'opts': self.model._meta,
				})
			
			try:
				# AliExpress kampanya ID'sini al
				from pathlib import Path
				campaign_file = Path(__file__).resolve().parent.parent / 'aliexpress_campaign_id.txt'
				campaign_id = 6115  # Varsayılan
				if campaign_file.exists():
					with open(campaign_file, 'r') as f:
						campaign_id = int(f.read().strip())
				
				# 1. Admitad API'den ürün bilgilerini çek
				from .admitad_client import AdmitadAPI
				api_client = AdmitadAPI()
				
				self.message_user(request, '🔄 Admitad API\'den ürün bilgileri çekiliyor...', messages.INFO)
				product_data = api_client.get_product_details(url, campaign_id)
				
				if product_data and product_data.get('price', 0) > 0:
					# API'den başarıyla veri geldi (şu an Admitad API ürün bilgisi yok)
					title = product_data['title']
					price = product_data['price']
					price_with_tax = price
					image_url = product_data['image_url']
					description = product_data['description']
					
					self.message_user(request, f'✓ API\'den fiyat çekildi: {price} TL', messages.SUCCESS)
				else:
					# API'den veri gelmedi, BeautifulSoup ile scrape et
					self.message_user(request, '⚠️ Admitad API ürün endpoint\'i desteklemiyor, sayfa parse ediliyor...', messages.WARNING)
					
					# Ürün bilgilerini çek (retry mekanizmasıyla)
					headers = {
						'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
					}
					
					# Retry: 3 deneme yap
					html_content = None
					soup = None
					for attempt in range(1, 4):
						try:
							response = requests.get(url, headers=headers, timeout=30)  # 30 saniye timeout
							response.raise_for_status()
							html_content = response.text
							soup = BeautifulSoup(response.content, 'html.parser')
							self.message_user(request, f'✓ Sayfa başarıyla indirildi (Deneme {attempt})', messages.SUCCESS)
							break
						except requests.exceptions.Timeout:
							if attempt < 3:
								self.message_user(request, f'⏱️ Timeout ({attempt}/3), tekrar deniyor...', messages.WARNING)
							else:
								self.message_user(request, f'❌ 3 denemede başarısız oldu. Lütfen daha sonra tekrar deneyin.', messages.ERROR)
								return render(request, 'admin/urun_link_ekle.html', {
									'title': 'AliExpress Linkinden Ürün Ekle',
									'opts': self.model._meta,
									'aliexpress_url': url,
								})
						except Exception as e:
							if attempt < 3:
								self.message_user(request, f'⚠️ Hata ({attempt}/3): {str(e)[:50]}, tekrar deniyor...', messages.WARNING)
							else:
								self.message_user(request, f'❌ Bağlantı hatası: {str(e)[:100]}', messages.ERROR)
								return render(request, 'admin/urun_link_ekle.html', {
									'title': 'AliExpress Linkinden Ürün Ekle',
									'opts': self.model._meta,
									'aliexpress_url': url,
								})
					
					if not html_content or not soup:
						self.message_user(request, '❌ Sayfa yüklenemedi', messages.ERROR)
						return render(request, 'admin/urun_link_ekle.html', {
							'title': 'AliExpress Linkinden Ürün Ekle',
							'opts': self.model._meta,
							'aliexpress_url': url,
						})
					
					# Başlık
					title = None
					h1 = soup.select_one('h1')
					if h1:
						title = h1.get_text(strip=True)[:200]
					if not title:
						meta_title = soup.select_one('meta[property="og:title"]')
						if meta_title:
							title = meta_title.get('content', '')[:200]
					if not title:
						match = re.search(r'/item/(\d+)\.html', url)
						title = f'AliExpress Ürün #{match.group(1)}' if match else 'AliExpress Ürün'
					
					# Fiyat - window.runParams'dan çek (JavaScript verisi)
					price = None
					price_with_tax = None
					para_birimi = 'TL'  # Varsayılan
					
					# Try 1: window.runParams JSON'ından fiyat çek
					run_params_match = re.search(r'window\.runParams\s*=\s*({.+?});', html_content, re.DOTALL)
					if run_params_match:
						try:
							import json
							run_params_str = run_params_match.group(1)
							# Tek tırnak kullanımı varsa düzelt
							run_params_str = re.sub(r"'", '"', run_params_str)
							run_params = json.loads(run_params_str)
							
							# data.priceModule içinden fiyat çek
							if 'data' in run_params:
								price_module = run_params['data'].get('priceModule', {})
								
								# minActivityAmount (indiriml fiyat)
								if 'minActivityAmount' in price_module:
									price_dict = price_module['minActivityAmount']
									if 'value' in price_dict:
										price = float(price_dict['value'])
								
								# minAmount (normal fiyat)
								if not price and 'minAmount' in price_module:
									price_dict = price_module['minAmount']
									if 'value' in price_dict:
										price = float(price_dict['value'])
								
								# formattedPrice (formatlanmış)
								if not price and 'formattedPrice' in price_module:
									formatted = price_module['formattedPrice']
									price_match = re.search(r'([\d,]+\.?\d*)', formatted)
									if price_match:
										price = float(price_match.group(1).replace(',', ''))
									
						except Exception as e:
							self.message_user(request, f'JSON parse hatası: {e}', messages.WARNING)
					
					# Try 2: Script taglerinden regex ile fiyat çek
					if not price:
						# HTML content'inde direkt fiyat ara (render edilen sayfada görünen)
						# Format: "37,90 ABD doları", "1.836,13 TL" vs.
						price_patterns = [
							# USD patterns - öncelik ver (AliExpress TR'de sık gösteriliyor)
							(r'(\d+[,]\d{2})\s+ABD doları', 'USD'),  # 27,90 ABD doları (EN YAYGINI)
							(r'(\d+[.,]\d{2})\s+(?:ABD|US)?\s*doları', 'USD'),  # Esnek USD
							(r'(\d+[.,]\d{2})\s*(?:USD|\$)', 'USD'),  # USD / $ sembolü
							
							# TL patterns
							(r'(\d{1,5}[.,]\d{2})\s*TL', 'TL'),  # Türk formatı: 1.836,13 TL
							(r'(\d{1,5}[.,]\d{2})\s*₺', 'TL'),   # Lira sembolü
							(r'[\D](\d{1,5}[.,]\d{2})[\s]*(?:TL|₺)', 'TL'),  # Başında sayı olmayan
						]
						
						for pattern, currency in price_patterns:
							matches = re.findall(pattern, html_content)
							if matches:
								try:
									# Fiyatlar desc sıraya göre ilk büyük rakam ana ürün fiyatı
									# En küçük olanı seç (indirimsiz)
									prices = [float(m.replace('.', '').replace(',', '.')) for m in matches]
									
									# Para birimine göre aralık belirle
									if currency == 'USD':
										price = min([p for p in prices if 5 < p < 1000])  # USD: 5-1000
									else:
										price = min([p for p in prices if 10 < p < 100000])  # TL: 10-100000
									
									para_birimi = currency
									
									# USD'yi TL'ye çevir (yaklaşık 33 TL/USD)
									if currency == 'USD':
										original_usd = price
										price = price * 33  # USD → TL çevirimi
										self.message_user(request, f'✓ USD fiyat çekildi: ${original_usd:.2f} → {price:.2f} TL', messages.SUCCESS)
									else:
										self.message_user(request, f'✓ TL fiyat çekildi: {price:.2f} TL', messages.SUCCESS)
									break
								except Exception as ex:
									continue
					
					# Varsayılan fiyat
					if not price or price == 0:
						if manual_fiyat:
							try:
								price = float(manual_fiyat)
								self.message_user(request, f'✓ Manuel fiyat kullanıldı: {price} TL', messages.SUCCESS)
							except:
								price = 199.99
								self.message_user(request, '⚠️ Manuel fiyat geçersiz, varsayılan: 199.99 TL', messages.WARNING)
						else:
							price = 199.99
							self.message_user(request, '⚠️ Fiyat otomatik çekilemedi, varsayılan: 199.99 TL', messages.WARNING)
					else:
						self.message_user(request, f'✓ Fiyat bulundu: {price} TL', messages.SUCCESS)
					
					# AliExpress'te gösterilen fiyata vergi/gümrük ekle (1.60 çarpanı)
					price_with_tax = round(price * 1.65, 2)
					self.message_user(request, f'💰 Vergi eklendi: {price} TL × 1.65 = {price_with_tax} TL', messages.INFO)
					
					# Resim URL
					image_url = ''
					og_image = soup.select_one('meta[property="og:image"]')
					if og_image:
						image_url = og_image.get('content', '')
					
					# Açıklama
					description = ''
					meta_desc = soup.select_one('meta[name="description"]')
					if meta_desc:
						description = meta_desc.get('content', '')[:300]
				
				# Mağaza
				magaza, _ = Magaza.objects.get_or_create(
					isim='AliExpress',
					defaults={'web_adresi': 'https://www.aliexpress.com'}
				)
				
				# Affiliate link oluştur
				base_link = config('ADMITAD_BASE_LINK', default='')
				if not base_link:
					messages.error(request, 'ADMITAD_BASE_LINK yapılandırılmamış!')
					return redirect('..')
				
				affiliate_link = build_admitad_deeplink(
					base_link=base_link,
					product_url=url,
					subid=subid
				)
				
				# Ürünü kaydet - AliExpress'te gösterilen gerçek fiyat
				urun = Urun.objects.create(
					isim=title,
					aciklama=description or 'AliExpress kaliteli ürün',
					resim_url=image_url if image_url else None
				)
				
				Fiyat.objects.create(
					urun=urun,
					magaza=magaza,
					fiyat=price_with_tax,  # Sayfada gösterilen fiyat
					para_birimi=para_birimi,  # Para birimi (TL veya USD)
					affiliate_link=affiliate_link
				)

				messages.success(request, f'✅ Ürün başarıyla eklendi: {title}')
				return redirect(f'/admin/urunler/urun/{urun.id}/change/')
			
			except Exception as e:
				messages.error(request, f'❌ Hata: {str(e)}')
				return render(request, 'admin/urun_link_ekle.html', {
					'title': 'AliExpress Linkinden Ürün Ekle',
					'opts': self.model._meta,
					'aliexpress_url': url,
				})
	
		return render(request, 'admin/urun_link_ekle.html', {
			'title': 'AliExpress Linkinden Ürün Ekle',
			'opts': self.model._meta,
		})
	
	def amazon_link_ekle_view(self, request):
		"""Amazon linki ile ürün ekle - 2 adımlı form."""
		from .utils.amazon_scraper import scrape_amazon_product, validate_amazon_url, extract_asin
		
		amazon_url = request.POST.get('amazon_url', '').strip() or request.GET.get('amazon_url', '').strip()
		manual_fiyat = request.POST.get('manual_fiyat', '').strip()
		product_data = None
		
		# URL'yi orijinal şekilde sakla (SiteStripe affiliate tag'ini korusun)
		affiliate_link = amazon_url
		
		# Step 2: Ürünü kaydet (fiyat bilgisi var)
		if request.method == 'POST' and manual_fiyat:
			if not amazon_url:
				return render(request, 'admin/urun_amazon_link_ekle.html', {
					'title': 'Amazon Linkinden Ürün Ekle',
					'opts': self.model._meta,
					'error': 'Lütfen bir Amazon URL\'si girin',
				})
			
			try:
				# Ürün bilgilerini tekrar çek (cache yok)
				product_data = scrape_amazon_product(amazon_url)
				
				if not product_data:
					raise Exception('Amazon sayfasından bilgi alınamadı. URL\'yi kontrol edin.')
				
				title = product_data.get('title', 'Amazon Ürünü')
				description = product_data.get('description', '')
				image_url = product_data.get('image_url', '')
				
				# Manuel fiyat al
				try:
					price_with_tax = float(manual_fiyat)
				except:
					raise Exception('Geçerli bir fiyat girin (sayı olmalı)')
				
				if price_with_tax < 10:
					raise Exception('Fiyat en az 10 TL olmalı')
				
				self.message_user(request, f'💰 Fiyat: {price_with_tax:.2f} TL', messages.INFO)
				
				# Mağaza
				magaza, _ = Magaza.objects.get_or_create(
					isim='Amazon',
					defaults={'web_adresi': 'https://www.amazon.com'}
				)
				
				# Ürünü kaydet
				urun = Urun.objects.create(
					isim=title,
					aciklama=description or 'Amazon kaliteli ürün',
					resim_url=image_url if image_url else None
				)
				
				# Fiyat kaydı (affiliate_link orijinal link - SiteStripe tag'ini korur)
				Fiyat.objects.create(
					urun=urun,
					magaza=magaza,
					fiyat=price_with_tax,
					para_birimi='TL',
					affiliate_link=affiliate_link  # Orijinal URL + SiteStripe tag'i
				)
				
				self.message_user(request, f'✅ Ürün başarıyla eklendi: {title}', messages.SUCCESS)
				return redirect(f'/admin/urunler/urun/{urun.id}/change/')
			
			except Exception as e:
				self.message_user(request, f'❌ Hata: {str(e)}', messages.ERROR)
				return render(request, 'admin/urun_amazon_link_ekle.html', {
					'title': 'Amazon Linkinden Ürün Ekle',
					'opts': self.model._meta,
					'amazon_url': amazon_url,
					'error': str(e),
				})
		
		# Step 1: Bilgileri çek
		if request.method == 'POST' and not manual_fiyat:  # Sadece URL, fiyat yok
			if not amazon_url:
				return render(request, 'admin/urun_amazon_link_ekle.html', {
					'title': 'Amazon Linkinden Ürün Ekle',
					'opts': self.model._meta,
					'error': 'Lütfen bir Amazon URL\'si girin',
				})
			
			# URL doğrula
			if not validate_amazon_url(amazon_url):
				return render(request, 'admin/urun_amazon_link_ekle.html', {
					'title': 'Amazon Linkinden Ürün Ekle',
					'opts': self.model._meta,
					'error': 'Geçerli bir Amazon URL\'si girin (amazon.com, amazon.co.uk, vb.)',
				})
			
			try:
				# Amazon'dan bilgi çek
				product_data = scrape_amazon_product(amazon_url)
				
				if not product_data:
					raise Exception('Amazon sayfasından bilgi alınamadı. URL\'yi kontrol edin.')
				
				# Başarı mesajı
				title_display = product_data.get("title", "N/A")
				self.message_user(request, f'✓ Ürün bilgileri çekildi: {title_display}', messages.SUCCESS)
				
				# Form 2'yi göster
				return render(request, 'admin/urun_amazon_link_ekle.html', {
					'title': 'Amazon Linkinden Ürün Ekle',
					'opts': self.model._meta,
					'amazon_url': amazon_url,
					'product_data': product_data,
				})
			
			except Exception as e:
				self.message_user(request, f'❌ Hata: {str(e)}', messages.ERROR)
				return render(request, 'admin/urun_amazon_link_ekle.html', {
					'title': 'Amazon Linkinden Ürün Ekle',
					'opts': self.model._meta,
					'amazon_url': amazon_url,
					'error': str(e),
				})
		
		# İlk form
		return render(request, 'admin/urun_amazon_link_ekle.html', {
			'title': 'Amazon Linkinden Ürün Ekle',
			'opts': self.model._meta,
		})


@admin.register(Magaza)
class MagazaAdmin(admin.ModelAdmin):
	list_display = ("isim", "web_adresi")


@admin.register(Fiyat)
class FiyatAdmin(admin.ModelAdmin):
	list_display = ("urun", "magaza", "fiyat_goster", "para_birimi", "affiliate_link")
	readonly_fields = ("affiliate_link",)

	def fiyat_goster(self, obj):
		sembol = '₺' if obj.para_birimi == 'TL' else '$'
		return f"{obj.fiyat} {sembol}"
	fiyat_goster.short_description = "Fiyat"


@admin.register(ClickLog)
class ClickLogAdmin(admin.ModelAdmin):
	list_display = ("id", "timestamp", "user", "link_type", "urun")

