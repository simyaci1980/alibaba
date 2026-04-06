from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q, Case, When, IntegerField, Prefetch
from django.conf import settings
from django.core.paginator import Paginator
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
import json
import re
from .models import Urun, UrunResim, Fiyat, ClickLog, Yorum
from .forms import YorumForm
from django.http import HttpResponse
from django.utils.safestring import mark_safe


def _build_breadcrumb_schema(items: list) -> dict:
	"""
	Breadcrumb Schema JSON-LD oluştur.
	items = [{'position': 1, 'name': 'Ana Sayfa', 'url': '/'}, ...]
	"""
	return {
		'@context': 'https://schema.org',
		'@type': 'BreadcrumbList',
		'itemListElement': items,
	}


def _build_organization_schema() -> dict:
	"""Site-wide Organization Schema"""
	base_url = getattr(settings, 'SITE_BASE_URL', '').rstrip('/')
	logo_url = _to_absolute_url('/static/urunler/kolaybulexpres_logo.svg')
	
	return {
		'@context': 'https://schema.org',
		'@type': 'Organization',
		'name': 'Kolay Bul Ekspres',
		'url': base_url or 'https://www.kolaybulexpres.com',
		'logo': logo_url,
		'description': 'Curated retro handheld consoles and gaming devices. Fast shipping, safe shopping, no sign-up required.',,
		'sameAs': [
			'https://www.facebook.com/kolaybulexpres',
			'https://www.instagram.com/kolaybulexpres',
		],
	}


def _translate_detail_label(label: str) -> str:
	label_map = {
		'mensei ulke': 'Menşei Ülke',
		'mensei ulkesi': 'Menşei Ülke',
		'brand': 'Marka',
		'marka': 'Marka',
		'style': 'Stil',
		'stil': 'Stil',
		'tip': 'Tip',
		'type': 'Tip',
		'bolge kodu': 'Bölge Kodu',
		'region code': 'Bölge Kodu',
		'platformu': 'Platform',
		'platform': 'Platform',
		'color': 'Renk',
		'renk': 'Renk',
		'model': 'Model',
		'modeli': 'Model',
		'connectivity': 'Bağlantı',
		'gonderim yeri': 'Gönderim Yeri',
		'gonderim yerinden': 'Gönderim Yeri',
		'ship from': 'Gönderim Yeri',
		'ships from': 'Gönderim Yeri',
		'year manufactured': 'Üretim Yılı',
		'features': 'Özellikler',
		'unit quantity': 'Adet',
		'country/region of manufacture': 'Üretim Yeri',
	}
	normalized = re.sub(r'\s+', ' ', (label or '').strip().lower())
	translated = label_map.get(normalized)
	if translated:
		return translated
	if not normalized:
		return 'Bilgi'
	return (label or '').strip()


def _normalize_description_text(text: str) -> str:
	"""Açıklama metnini gürültüden arındırıp okunabilir hale getirir."""
	if not text:
		return ''
	cleaned = str(text)
	cleaned = re.sub(r'(?is)<script[^>]*>.*?</script>', ' ', cleaned)
	cleaned = re.sub(r'(?is)<style[^>]*>.*?</style>', ' ', cleaned)
	cleaned = re.sub(r'(?is)<[^>]+>', ' ', cleaned)
	cleaned = re.sub(r'\s+', ' ', cleaned).strip()
	return cleaned


def _is_garbage_description(text: str) -> bool:
	"""CSS/HTML artığı veya anlamsız içerik benzeri metni tespit eder."""
	normalized = str(text or '').strip()
	if not normalized:
		return True

	lower_text = normalized.lower()

	# İngilizce CSS anahtar kelimeleri
	css_hits = len(re.findall(
		r'font-size|line-height|cursor:|appearance:|input\[type=|button\{|-webkit|@media|position:|display:|vertical-align',
		lower_text,
	))
	if css_hits >= 3:
		return True

	# CSS süslü parantez blokları — Türkçeye çevrilmiş CSS de olsa `{` kalır
	brace_count = normalized.count('{') + normalized.count('}')
	if brace_count >= 4:
		return True

	# CSS noktalı sınıf seçicileri (.aplus-v2, .container-with-background-image vb.)
	css_selector_hits = len(re.findall(r'\.[a-z][a-z0-9_-]{2,}', lower_text))
	if css_selector_hits >= 5:
		return True

	# Dilden bağımsız CSS değer desenleri (px, rem, %; width: height: margin: vb.)
	css_unit_hits = len(re.findall(
		r'\d+px\b|\d+rem\b|\d+em\b|width:|height:|margin:|padding:|border:|background:|overflow:',
		lower_text,
	))
	if css_unit_hits >= 3:
		return True

	punc_count = len(re.findall(r'[{};]', normalized))
	punc_ratio = punc_count / max(len(normalized), 1)
	if len(normalized) > 240 and punc_ratio > 0.06:
		return True

	word_tokens = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]{2,}", normalized)
	if len(normalized) > 180 and len(word_tokens) < 20:
		return True

	return False


def _build_canonical_url(path: str, query_string: str = '') -> str:
	base_url = getattr(settings, 'SITE_BASE_URL', '').rstrip('/')
	normalized_path = path if path.startswith('/') else f'/{path}'
	canonical_url = f'{base_url}{normalized_path}' if base_url else normalized_path
	if query_string:
		return f'{canonical_url}?{query_string}'
	return canonical_url


def _to_absolute_url(url: str) -> str:
	if not url:
		return ''
	normalized = str(url).strip()
	if normalized.startswith('//'):
		return f'https:{normalized}'
	if normalized.startswith('http://') or normalized.startswith('https://'):
		return normalized
	base_url = getattr(settings, 'SITE_BASE_URL', '').rstrip('/')
	if not base_url:
		return normalized
	return f"{base_url}/{normalized.lstrip('/')}"


def _default_og_image() -> str:
	return _to_absolute_url(getattr(settings, 'SITE_OG_IMAGE', '/static/urunler/android-icon-192x192.png'))


def _schema_currency_code(currency: str) -> str:
	code = str(currency or '').strip().upper()
	if code == 'TL':
		return 'TRY'
	return code or 'TRY'


def _extract_product_brand(urun) -> str:
	"""Try to infer product brand from structured details or feature lines."""
	detaylar = getattr(urun, 'detaylar', None) or {}
	for key in ('marka', 'brand'):
		value = str(detaylar.get(key, '') or '').strip()
		if value and value.lower() != 'belirtilmemiş':
			return value

	if urun.ozellikler:
		for raw_line in urun.ozellikler.splitlines():
			line = (raw_line or '').strip()
			if not line or ':' not in line:
				continue
			label_raw, value_raw = line.split(':', 1)
			translated = _translate_detail_label(label_raw)
			value = str(value_raw or '').strip()
			if translated == 'Marka' and value and value.lower() != 'belirtilmemiş':
				return value

	return ''


HOME_DETAIL_PRIORITY = [
	'Marka',
	'Model',
	'Gönderim Yeri',
]


HOME_DETAIL_KEY_ALIASES = {
	'Marka': ['marka', 'brand'],
	'Model': ['model', 'modeli'],
	'Stil': ['stil', 'style'],
	'Renk': ['renk', 'color'],
	'Tip': ['tip', 'type'],
	'Platform': ['platform'],
	'Bölge Kodu': ['bolge_kodu', 'region_code'],
	'Bağlantı': ['baglanti', 'connectivity'],
	'Ekran Boyutu': ['ekran_boyutu'],
	'Çözünürlük': ['cozunurluk'],
	'İşlemci': ['cpu', 'islemci', 'processor'],
	'RAM': ['ram', 'memory'],
	'Depolama': ['depolama', 'storage'],
	'Batarya': ['batarya', 'battery'],
	'İşletim Sistemi': ['isletim_sistemi', 'operating_system'],
	'HDMI Çıkışı': ['hdmi'],
	'Menşei Ülke': ['mensei_ulke', 'ulke', 'origin_country'],
	'Üretim Yeri': ['uretim_yeri', 'manufacture_country'],
	'Üretim Yılı': ['uretim_yili', 'year_manufactured'],
	'Özellikler': ['ozellikler', 'features'],
	'Adet': ['adet', 'unit_quantity'],
}


def _set_home_detail_candidate(candidates: dict, label: str, value: str):
	translated_label = _translate_detail_label(label)
	clean_value = str(value or '').strip()
	if not translated_label or not clean_value or clean_value.lower() == 'belirtilmemiş':
		return
	candidates.setdefault(translated_label.casefold(), {'label': translated_label, 'value': clean_value})


def _get_home_shipping_origin(urun) -> str:
	best_origin = ''
	best_total = None
	for fiyat in urun.fiyatlar.all():
		origin = str(getattr(fiyat, 'gonderim_yerinden', '') or '').strip()
		if not origin:
			continue
		total = getattr(fiyat, 'toplam_fiyat', None)
		if best_total is None or (total is not None and total < best_total):
			best_total = total
			best_origin = origin
	return best_origin


def _build_home_detail_rows(urun) -> list[dict]:
	candidates = {}

	if urun.ozellikler:
		for raw_line in urun.ozellikler.splitlines():
			line = (raw_line or '').strip()
			if not line or ':' not in line:
				continue
			label_raw, value_raw = line.split(':', 1)
			_set_home_detail_candidate(candidates, label_raw, value_raw)

	if getattr(urun, 'detaylar', None):
		detaylar = urun.detaylar or {}
		for label, aliases in HOME_DETAIL_KEY_ALIASES.items():
			for key in aliases:
				value = detaylar.get(key, '')
				if str(value or '').strip() and str(value).strip() != 'Belirtilmemiş':
					_set_home_detail_candidate(candidates, label, value)
					break

	shipping_origin = _get_home_shipping_origin(urun)
	if shipping_origin:
		_set_home_detail_candidate(candidates, 'Gönderim Yeri', shipping_origin)

	rows = []
	seen_labels = set()
	priority_keys = {label.casefold() for label in HOME_DETAIL_PRIORITY}

	for label in HOME_DETAIL_PRIORITY:
		payload = candidates.get(label.casefold())
		if not payload:
			continue
		rows.append(payload)
		seen_labels.add(label.casefold())
		if len(rows) >= 8:
			return rows

	remaining_rows = sorted(
		[payload for key, payload in candidates.items() if key not in priority_keys and key not in seen_labels],
		key=lambda item: item['label'].casefold(),
	)
	for payload in remaining_rows:
		rows.append(payload)
		if len(rows) >= 8:
			break

	return rows

def anasayfa(request):
	"""Ana sayfa - ürün listesi ve yorumlar"""
	search_query = request.GET.get('q', '').strip()
	resim_prefetch = Prefetch('resimler', queryset=UrunResim.objects.order_by('sira', 'id'), to_attr='sirali_resimler')
	base_queryset = Urun.objects.exclude(durum__iexact='Pasif').prefetch_related('fiyatlar__magaza', resim_prefetch)
	
	if search_query:
		# Arama yapılıyorsa - ürün ismine veya urun_kodu'na göre filtrele
		urunler = base_queryset.filter(
			Q(isim__icontains=search_query) |
			Q(aciklama__icontains=search_query) |
			Q(urun_kodu__iexact=search_query) |
			Q(urun_kodu__icontains=search_query)
		).annotate(
			# Tam eşleşme öncelikli sıralama
			relevance=Case(
				When(isim__iexact=search_query, then=1),
				When(isim__istartswith=search_query, then=2),
				When(isim__icontains=search_query, then=3),
				When(urun_kodu__iexact=search_query, then=0),
				default=4,
				output_field=IntegerField()
			)
		).order_by('relevance', 'isim')
	else:
		# Arama yoksa tüm ürünleri göster
		gonderim_yeri = request.GET.get('gonderim_yeri', '').strip()
		urunler = list(base_queryset.all())
		if gonderim_yeri:
			gonderim_yeri_lower = gonderim_yeri.strip().lower()
			urunler = [
				u for u in urunler
				if any(
					f.gonderim_yerinden and f.gonderim_yerinden.strip().lower() == gonderim_yeri_lower
					for f in u.fiyatlar.all()
				)
			]
		numarali = {u.sira: u for u in urunler if u.sira and u.sira > 0}
		sifirli = [u for u in urunler if not u.sira or u.sira == 0]
		sifirli_sorted = sorted(sifirli, key=lambda u: -u.id)
		max_sira = max(list(numarali.keys()) + [0])
		urunler_sirali = []
		sifirli_idx = 0
		for i in range(1, max_sira+1):
			if i in numarali:
				urunler_sirali.append(numarali[i])
			else:
				if sifirli_idx < len(sifirli_sorted):
					urunler_sirali.append(sifirli_sorted[sifirli_idx])
					sifirli_idx += 1
		urunler_sirali += sifirli_sorted[sifirli_idx:]
		urunler = urunler_sirali
	
	yorumlar = Yorum.objects.filter(onayli=True).order_by('-eklenme_tarihi')[:10]
	form = YorumForm(request.POST or None)
	if request.method == 'POST' and form.is_valid():
		form.save()
		form = YorumForm()

	# İlk açılışta 60 ürün göster, devamı sayfalansın.
	paginator = Paginator(urunler, 60)
	page_number = request.GET.get('page')
	page_obj = paginator.get_page(page_number)
	urunler = page_obj.object_list
	for urun in urunler:
		urun.home_detail_rows = _build_home_detail_rows(urun)

	query_params = request.GET.copy()
	query_params.pop('page', None)
	query_string = query_params.urlencode()
	canonical_url = _build_canonical_url(request.path, query_string)
	meta_title = 'Ana Sayfa | KOLAY BUL EKSPRES'
	meta_description = 'Kolay Bul Ekspres ile secilmis urunleri karsilastirin ve guvenli sekilde inceleyin.'
	organization_schema = _build_organization_schema()

	return render(request, 'urunler/anasayfa.html', {
		'urunler': urunler,
		'page_obj': page_obj,
		'query_string': query_string,
		'yorumlar': yorumlar,
		'form': form,
		'search_query': search_query,
		'canonical_url': canonical_url,
		'meta_title': meta_title,
		'meta_description': meta_description,
		'og_title': meta_title,
		'og_description': meta_description,
		'og_url': canonical_url,
		'og_image': _default_og_image(),
		'organization_schema_json': mark_safe(json.dumps(organization_schema, ensure_ascii=False)),
	})


def urun_listesi(request):
	"""Ürün listesi sayfası"""
	resim_prefetch = Prefetch('resimler', queryset=UrunResim.objects.order_by('sira', 'id'), to_attr='sirali_resimler')
	urunler = list(Urun.objects.exclude(durum__iexact='Pasif').prefetch_related('fiyatlar__magaza', resim_prefetch).all())
	numarali = {u.sira: u for u in urunler if u.sira and u.sira > 0}
	sifirli = [u for u in urunler if not u.sira or u.sira == 0]
	sifirli_sorted = sorted(sifirli, key=lambda u: -u.id)
	max_sira = max(list(numarali.keys()) + [0])
	urunler_sirali = []
	sifirli_idx = 0
	for i in range(1, max_sira+1):
		if i in numarali:
			urunler_sirali.append(numarali[i])
		else:
			if sifirli_idx < len(sifirli_sorted):
				urunler_sirali.append(sifirli_sorted[sifirli_idx])
				sifirli_idx += 1
	urunler_sirali += sifirli_sorted[sifirli_idx:]
	urunler = urunler_sirali
	canonical_url = _build_canonical_url(request.path)
	meta_title = 'Urun Listesi | Kolay Bul Ekspres'
	meta_description = 'Kategori ve fiyat bilgileriyle urunleri listeleyin, karsilastirin ve en uygun secenekleri bulun.'
	organization_schema = _build_organization_schema()
	return render(request, 'urunler/urun_listesi.html', {
		'urunler': urunler,
		'canonical_url': canonical_url,
		'meta_title': meta_title,
		'meta_description': meta_description,
		'og_title': meta_title,
		'og_description': meta_description,
		'og_url': canonical_url,
		'og_image': _default_og_image(),
		'organization_schema_json': mark_safe(json.dumps(organization_schema, ensure_ascii=False)),
	})


def urun_detay(request, slug):
	"""SEO odakli urun detay sayfasi"""
	resim_prefetch = Prefetch('resimler', queryset=UrunResim.objects.order_by('sira', 'id'), to_attr='sirali_resimler')
	urun = get_object_or_404(
		Urun.objects.exclude(durum__iexact='Pasif').prefetch_related('fiyatlar__magaza', resim_prefetch),
		slug=slug
	)

	def normalize_image_url(url: str) -> str:
		if not url:
			return ''
		normalized = str(url).strip()
		if normalized.startswith('//'):
			normalized = f"https:{normalized}"
		normalized = re.sub(r'^https:///+', 'https://', normalized)
		normalized = re.sub(r'^http:///+', 'http://', normalized)
		return normalized

	fiyatlar = sorted(list(urun.fiyatlar.all()), key=lambda f: f.toplam_fiyat)
	en_dusuk_fiyat = fiyatlar[0] if fiyatlar else None

	image_candidates = []
	if urun.resim_url:
		image_candidates.append(normalize_image_url(urun.resim_url))
	elif urun.resim and urun.resim.name:
		image_candidates.append(urun.resim.url)

	for r in getattr(urun, 'sirali_resimler', []):
		if r.resim_url:
			image_candidates.append(normalize_image_url(r.resim_url))
		elif r.resim and r.resim.name:
			image_candidates.append(r.resim.url)

	image_urls = []
	seen = set()
	for img in image_candidates:
		if not img:
			continue
		if img in seen:
			continue
		seen.add(img)
		image_urls.append(img)

	primary_image_url = image_urls[0] if image_urls else ''
	gallery_image_urls = image_urls[1:9] if len(image_urls) > 1 else []

	if urun.ana_baslik:
		title_text = urun.ana_baslik
	else:
		title_text = urun.isim

	meta_description_source = (urun.alt_baslik or urun.aciklama or urun.ozellikler or urun.isim or '').strip()
	meta_description = ' '.join(meta_description_source.split())[:160]
	canonical_url = _build_canonical_url(request.path)
	meta_title = f"{title_text} | Kolay Bul Ekspres"

	product_schema = {
		'@context': 'https://schema.org',
		'@type': 'Product',
		'name': title_text,
		'description': meta_description,
		'sku': urun.urun_kodu or str(urun.id),
		'url': canonical_url,
	}

	brand_name = _extract_product_brand(urun)
	if brand_name:
		product_schema['brand'] = {
			'@type': 'Brand',
			'name': brand_name,
		}

	if image_urls:
		product_schema['image'] = image_urls[:6]

	if en_dusuk_fiyat:
		product_schema['offers'] = {
			'@type': 'Offer',
			'priceCurrency': _schema_currency_code(en_dusuk_fiyat.para_birimi),
			'price': str(en_dusuk_fiyat.fiyat),
			'availability': 'https://schema.org/InStock',
		}

	# Şemaya dayalı detaylar (template'de güzel label + badge gösterimi için)
	detaylar_schema = []
	excluded_keys = {'kontrolcu', 'oyun_sayisi', 'kutu_icerigi'}
	if urun.kategori and urun.kategori.alanlar:
		mevcut_detaylar = urun.detaylar or {}
		for _alan in urun.kategori.alanlar:
			_key = _alan.get('key', '')
			if not _key or _key == 'ocr_adayi':
				continue
			if _key in excluded_keys:
				continue
			_val_raw = mevcut_detaylar.get(_key, '')
			_val = str(_val_raw).strip() if _val_raw is not None else ''
			if not _val:
				_val = 'Belirtilmemiş'
			detaylar_schema.append({
				'key': _key,
				'label': _alan.get('label', _key.replace('_', ' ').title()),
				'value': _val,
				'kaynak': _alan.get('kaynak', 'description'),
				'zorunlu': _alan.get('zorunlu', False),
			})

	# Açıklama/not alanını satır satır görselleştirmek için ayrıştır
	ozellikler_satirlari = []
	if urun.ozellikler:
		for raw_line in urun.ozellikler.splitlines():
			line = (raw_line or '').strip()
			if not line:
				continue
			if line.startswith('---') and line.endswith('---'):
				heading = line.strip('- ').strip()
				if 'description cikarim' in heading.lower():
					continue
				ozellikler_satirlari.append({
					'tur': 'baslik',
					'icerik': heading,
				})
				continue

			if ':' in line:
				label_raw, value_raw = line.split(':', 1)
				label_raw = label_raw.strip()
				value_raw = value_raw.strip() or 'Belirtilmemiş'
				label = f"{label_raw[:1].upper()}{label_raw[1:]}" if label_raw else 'Bilgi'
				ozellikler_satirlari.append({
					'tur': 'satir',
					'label': label,
					'value': value_raw,
				})
			else:
				ozellikler_satirlari.append({
					'tur': 'metin',
					'icerik': line,
				})

	orijinal_aciklama = str(urun.aciklama or '').strip()
	temiz_aciklama = _normalize_description_text(orijinal_aciklama)

	orijinal_kotu = _is_garbage_description(orijinal_aciklama)
	temiz_kotu = _is_garbage_description(temiz_aciklama)

	gosterilecek_aciklama = ''
	aciklama_orijinal_goster = False
	show_description_card = False

	if temiz_aciklama and not temiz_kotu:
		gosterilecek_aciklama = temiz_aciklama
		show_description_card = True
		aciklama_orijinal_goster = (
			bool(orijinal_aciklama)
			and not orijinal_kotu
			and orijinal_aciklama != temiz_aciklama
		)

	show_notes_section = bool(ozellikler_satirlari or show_description_card)

	# Breadcrumb Schema
	breadcrumb_items = [
		{'position': 1, 'name': 'Ana Sayfa', 'url': _to_absolute_url('/')},
		{'position': 2, 'name': 'Ürün Listesi', 'url': _to_absolute_url('/urun-listesi/')},
		{'position': 3, 'name': title_text, 'url': canonical_url},
	]
	breadcrumb_schema = _build_breadcrumb_schema(breadcrumb_items)
	organization_schema = _build_organization_schema()

	context = {
		'urun': urun,
		'fiyatlar': fiyatlar,
		'en_dusuk_fiyat': en_dusuk_fiyat,
		'all_image_urls': image_urls,
		'primary_image_url': primary_image_url,
		'gallery_image_urls': gallery_image_urls,
		'detaylar_schema': detaylar_schema,
		'ozellikler_satirlari': ozellikler_satirlari,
		'show_notes_section': show_notes_section,
		'show_description_card': show_description_card,
		'aciklama_orijinal_goster': aciklama_orijinal_goster,
		'gosterilecek_aciklama': gosterilecek_aciklama,
		'meta_title': meta_title,
		'meta_description': meta_description,
		'canonical_url': canonical_url,
		'og_title': meta_title,
		'og_description': meta_description,
		'og_url': canonical_url,
		'og_image': _to_absolute_url(primary_image_url) or _default_og_image(),
		'og_type': 'product',
		'product_schema_json': mark_safe(json.dumps(product_schema, ensure_ascii=False)),
		'breadcrumb_schema_json': mark_safe(json.dumps(breadcrumb_schema, ensure_ascii=False)),
		'organization_schema_json': mark_safe(json.dumps(organization_schema, ensure_ascii=False)),
	}
	return render(request, 'urunler/urun_detay.html', context)


def urun_karsilastir(request):
	"""Seçilen ürünleri karşılaştır"""
	ids_str = request.GET.get('ids', '').strip()
	urun_ids = []
	
	if ids_str:
		try:
			urun_ids = [int(uid) for uid in ids_str.split(',') if uid.strip()]
			urun_ids = urun_ids[:5]  # Max 5
		except (ValueError, AttributeError):
			urun_ids = []
	
	if not urun_ids:
		messages.info(request, 'Lütfen karşılaştırmak için ürün seçin.')
		return redirect('anasayfa')
	
	# Ürünleri getir
	resim_prefetch = Prefetch('resimler', queryset=UrunResim.objects.order_by('sira', 'id'), to_attr='sirali_resimler')
	urunler = list(
		Urun.objects.exclude(durum__iexact='Pasif').prefetch_related('fiyatlar__magaza', resim_prefetch).filter(id__in=urun_ids)
	)
	
	if not urunler:
		messages.error(request, 'Seçilen ürünler bulunamadı.')
		return redirect('anasayfa')
	
	# Teknik özellik alanlarını topla (birleşim)
	all_keys = set()
	excluded_keys = {'kontrolcu', 'oyun_sayisi', 'kutu_icerigi'}
	
	for urun in urunler:
		if urun.kategori and urun.kategori.alanlar:
			for alan in urun.kategori.alanlar:
				key = alan.get('key', '')
				if key and key not in excluded_keys:
					all_keys.add(key)
	
	# Label map ve detaylar table
	label_map = {}
	for urun in urunler:
		if urun.kategori and urun.kategori.alanlar:
			for alan in urun.kategori.alanlar:
				key = alan.get('key', '')
				if key and key not in label_map:
					label_map[key] = alan.get('label', key.replace('_', ' ').title())
	
	# Karşılaştırma satırları (column-major format)
	karsilastirma_satir = []
	for key in sorted(all_keys):
		row = {
			'key': key,
			'label': label_map.get(key, key.replace('_', ' ').title()),
			'degerler': []
		}
		for urun in urunler:
			val = str(urun.detaylar.get(key, '') if urun.detaylar else '').strip() or 'Belirtilmemiş'
			row['degerler'].append(val)
		karsilastirma_satir.append(row)
	
	context = {
		'urunler': urunler,
		'karsilastirma_satir': karsilastirma_satir,
		'meta_title': 'Ürün Karşılaştırması | Kolay Bul Ekspres',
		'meta_description': 'Secilen urunlerin teknik ozelliklerini ayni ekranda karsilastirin.',
		'canonical_url': _build_canonical_url(request.path, request.GET.urlencode()),
		'og_title': 'Ürün Karşılaştırması | Kolay Bul Ekspres',
		'og_description': 'Secilen urunlerin teknik ozelliklerini ayni ekranda karsilastirin.',
		'og_url': _build_canonical_url(request.path, request.GET.urlencode()),
		'og_image': _default_og_image(),
	}
	
	return render(request, 'urunler/urun_karsilastir.html', context)


def amazon_redirect(request):
	"""Amazon affiliate redirect with logging"""
	ClickLog.objects.create(
		user=request.user if request.user.is_authenticated else None,
		link_type='amazon',
		subid='navbar',
		timestamp=timezone.now()
	)
	return redirect('https://www.amazon.com/b?node=53629917011&linkCode=ll2&tag=kolaybulekspr-20&linkId=8150ea1ccd7fe92bfd1f94652a6d69e4&language=en_US&ref_=as_li_ss_tl')


def aliexpress_redirect(request):
	"""AliExpress affiliate redirect with logging"""
	ClickLog.objects.create(
		user=request.user if request.user.is_authenticated else None,
		link_type='aliexpress',
		subid='navbar',
		timestamp=timezone.now()
	)
	return redirect('https://rzekl.com/g/1e8d11449462ceef436f16525dc3e8/')


def urun_affiliate_redirect(request, urun_id):
	"""Ürün affiliate redirect - her ürün için kendi linki"""
	urun = get_object_or_404(Urun, id=urun_id)
	# İlk fiyatın affiliate linkini al
	fiyat = urun.fiyatlar.first()
	if not fiyat:
		return redirect('/')  # Fiyat yoksa ana sayfaya yönlendir
	
	click = ClickLog.objects.create(
		user=request.user if request.user.is_authenticated else None,
		link_type='urun_affiliate',
		urun=urun,
		subid=f"u{urun.id}_c"
	)

	target_link = fiyat.affiliate_link
	if target_link and 'ebay.com' in target_link and 'campid=' in target_link:
		parsed = urlparse(target_link)
		params = dict(parse_qsl(parsed.query, keep_blank_values=True))
		params['customid'] = urun.urun_kodu or str(urun.id)
		target_link = urlunparse((
			parsed.scheme,
			parsed.netloc,
			parsed.path,
			parsed.params,
			urlencode(params),
			parsed.fragment,
		))

	if click.subid != (urun.urun_kodu or str(urun.id)):
		click.subid = urun.urun_kodu or str(urun.id)
		click.save(update_fields=['subid'])

	return redirect(target_link)


def fiyat_affiliate_redirect(request, fiyat_id):
	"""Fiyat (mağaza teklifi) bazlı affiliate redirect - her buton kendi linkine gider"""
	fiyat = get_object_or_404(Fiyat.objects.select_related('urun', 'magaza'), id=fiyat_id)
	urun = fiyat.urun

	click = ClickLog.objects.create(
		user=request.user if request.user.is_authenticated else None,
		link_type='urun_affiliate',
		urun=urun,
		subid=f"u{urun.id}_f{fiyat.id}"
	)

	target_link = fiyat.affiliate_link
	if target_link and 'ebay.com' in target_link and 'campid=' in target_link:
		parsed = urlparse(target_link)
		params = dict(parse_qsl(parsed.query, keep_blank_values=True))
		params['customid'] = urun.urun_kodu or str(urun.id)
		target_link = urlunparse((
			parsed.scheme,
			parsed.netloc,
			parsed.path,
			parsed.params,
			urlencode(params),
			parsed.fragment,
		))

	if click.subid != (urun.urun_kodu or str(urun.id)):
		click.subid = urun.urun_kodu or str(urun.id)
		click.save(update_fields=['subid'])

	return redirect(target_link)

def aliexpress_callback_view(request):
    import json
    from pathlib import Path
    from django.conf import settings

    error = request.GET.get('error')
    code  = request.GET.get('code')
    state = request.GET.get('state')

    if error:
        return HttpResponse(
            f"❌ AliExpress yetkilendirme hatası: {error}",
            content_type='text/plain; charset=utf-8',
            status=400,
        )

    if not code:
        return HttpResponse(
            "❌ Yetkilendirme kodu alınamadı.",
            content_type='text/plain; charset=utf-8',
            status=400,
        )

    app_key    = getattr(settings, 'ALIEXPRESS_APP_KEY', '')
    app_secret = getattr(settings, 'ALIEXPRESS_APP_SECRET', '')

    if not app_key or not app_secret:
        return HttpResponse(
            "❌ ALIEXPRESS_APP_KEY veya ALIEXPRESS_APP_SECRET .env dosyasında tanımlı değil.",
            content_type='text/plain; charset=utf-8',
            status=500,
        )

    from urunler.aliexpress_api import AliExpressAPIConnector
    connector    = AliExpressAPIConnector(app_key=app_key, app_secret=app_secret)
    redirect_uri = request.build_absolute_uri('/aliexpress/callback')
    token_data   = connector.exchange_code_for_token(code=code, redirect_uri=redirect_uri)

    if not token_data:
        return HttpResponse(
            f"⚠️  Code alındı: {code}\n\n"
            f"Ancak token exchange başarısız oldu.\n"
            f"Bu kodu manuel kaydetmek için terminalde şunu çalıştırın:\n\n"
            f"  python manage.py save_aliexpress_token {code}\n",
            content_type='text/plain; charset=utf-8',
        )

    # Token dosyaya kaydet (admitad_token.json ile aynı yapı)
    token_file = Path(settings.BASE_DIR) / 'aliexpress_token.json'
    with open(token_file, 'w', encoding='utf-8') as f:
        json.dump(token_data, f, indent=2, ensure_ascii=False)

    access_token = token_data.get('access_token', '')
    expires_in   = token_data.get('expires_in', 'Bilinmiyor')

    return HttpResponse(
        f"✅ AliExpress OAuth başarılı!\n\n"
        f"Access Token : {access_token[:20]}...\n"
        f"Expires In   : {expires_in} saniye\n\n"
        f"Token '{token_file}' dosyasına kaydedildi.\n"
        f"Artık Advanced API kullanılabilir:\n"
        f"  python test_advanced_api.py\n",
        content_type='text/plain; charset=utf-8',
    )
