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
from django.utils.safestring import mark_safe
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from decouple import config
import requests
import re
import json
from io import BytesIO
from urllib.parse import urljoin
from bs4 import BeautifulSoup

try:
	from PIL import Image, ImageFilter, ImageOps
except ImportError:
	Image = None
	ImageFilter = None
	ImageOps = None

try:
	from rapidocr_onnxruntime import RapidOCR
except ImportError:
	RapidOCR = None

from .models import Magaza, Urun, Fiyat, UrunResim, Yorum, ClickLog, KategoriSema
from .utils.deeplink import build_admitad_deeplink
from .ebay_api import EbayAPIConnector


@admin.register(KategoriSema)
class KategoriSemaAdmin(admin.ModelAdmin):
	list_display = ('isim', 'slug', 'aktif')
	search_fields = ('isim', 'slug')


class FiyatInline(admin.TabularInline):
	model = Fiyat
	extra = 1
	fields = ('magaza', 'fiyat', 'para_birimi', 'gonderim_ucreti', 'ucretsiz_kargo', 'gonderim_yerinden', 'gonderim_durumu', 'affiliate_link')
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
	from django.utils.safestring import mark_safe
	_rapidocr_engine = None

	def admin_thumbnail(self, obj):
		if obj.resim:
			return mark_safe(f'<img src="{obj.resim.url}" style="height:40px; width:auto; border-radius:4px; box-shadow:0 1px 4px rgba(0,0,0,0.07);" />')
		elif obj.resim_url:
			return mark_safe(f'<img src="{obj.resim_url}" style="height:40px; width:auto; border-radius:4px; box-shadow:0 1px 4px rgba(0,0,0,0.07);" />')
		else:
			return "-"
	admin_thumbnail.short_description = "Resim"

	list_display = ("id", "isim", "kategori", "slug", "ana_baslik", "alt_baslik", "sira", "admin_thumbnail")
	list_editable = ("sira",)
	search_fields = ("id", "isim", "ana_baslik", "urun_kodu", "slug")
	fields = ("isim", "kategori", "slug", "detaylar_kart", "detaylar", "ana_baslik", "alt_baslik", "etiketler", "ozellikler", "aciklama", "resim", "resim_url", "source_url", "urun_kodu", "sira", "resim_goster")
	inlines = [FiyatInline, UrunResimInline]
	readonly_fields = ("slug", "resim_goster", "detaylar_kart",)

	def response_change(self, request, obj):
		"""KAYDET butonunda list sayfasına gitmek yerine aynı ekranda kal."""
		if "_save" in request.POST:
			self.message_user(request, "Değişiklikler kaydedildi.", level=messages.SUCCESS)
			return redirect(request.path)
		return super().response_change(request, obj)

	def detaylar_kart(self, obj):
		"""Kategori şemasına göre parametreleri yapısal HTML form ile gösterir; JS ile raw JSON textarea'ya senkronize eder."""
		excluded_keys = {'kontrolcu', 'oyun_sayisi', 'kutu_icerigi'}
		if not obj or not obj.pk:
			return mark_safe('<em style="color:#6b7280;">Ürünü kaydedin, ardından kategori seçip tekrar açın.</em>')
		if not obj.kategori:
			return mark_safe('<em style="color:#6b7280;">Yukarıdan bir <strong>Kategori</strong> seçin ve kaydedin — parametreler burada görünecek.</em>')
		alanlar = obj.kategori.alanlar or []
		if not alanlar:
			return mark_safe('<em style="color:#6b7280;">Seçili kategorinin şeması tanımlı değil.</em>')

		mevcut = obj.detaylar or {}
		rows_html = []
		for alan in alanlar:
			key = alan.get('key', '')
			if not key:
				continue
			if key in excluded_keys:
				continue
			label    = alan.get('label', key.replace('_', ' ').title())
			kaynak   = alan.get('kaynak', 'description')
			zorunlu  = alan.get('zorunlu', False)
			deger    = mevcut.get(key, '')

			if kaynak == 'pipeline':
				badge = ('<span style="background:#ea580c;color:#fff;border-radius:3px;'
				         'padding:1px 5px;font-size:0.72em;font-weight:700;margin-left:5px;">OCR / Manuel</span>')
			else:
				badge = ('<span style="background:#16a34a;color:#fff;border-radius:3px;'
				         'padding:1px 5px;font-size:0.72em;font-weight:700;margin-left:5px;">API</span>')

			star = '<span style="color:#dc2626;margin-left:3px;" title="Zorunlu alan">*</span>' if zorunlu else ''

			deger_text = str(deger).strip() if deger is not None else ''
			is_unspecified = (not deger_text) or (deger_text.lower() == 'belirtilmemiş')
			input_value = 'Belirtilmemiş' if is_unspecified else deger_text
			deger_safe = input_value.replace('"', '&quot;').replace("'", '&#39;')

			if is_unspecified:
				inp_style = ('width:100%;box-sizing:border-box;border:1.5px solid #fbbf24;'
				             'border-radius:5px;padding:5px 8px;font-size:0.9em;background:#f8fafc;'
				             'color:#0f172a !important;-webkit-text-fill-color:#0f172a !important;'
				             'caret-color:#0f172a;color-scheme:light;')
				if kaynak == 'pipeline':
					inp_style = inp_style.replace('#fbbf24', '#fb923c')
			else:
				inp_style = ('width:100%;box-sizing:border-box;border:1.5px solid #22c55e;'
				             'border-radius:5px;padding:5px 8px;font-size:0.9em;background:#f8fafc;'
				             'color:#0f172a !important;-webkit-text-fill-color:#0f172a !important;'
				             'caret-color:#0f172a;color-scheme:light;')

			rows_html.append(f'''
			<tr>
				<td style="padding:8px 12px;white-space:nowrap;vertical-align:middle;
				            background:#0f172a;border-bottom:1px solid #1f2937;width:210px;">
					<span style="font-weight:600;font-size:0.88em;color:#e5e7eb;">{label}</span>{badge}{star}
				</td>
				<td style="padding:8px 12px;border-bottom:1px solid #1f2937;background:#020617;">
					<input type="text"
					       class="detaylar-alan-inp"
					       data-dk="{key}"
					       data-kaynak="{kaynak}"
					       value="{deger_safe}"
					       placeholder="Belirtilmemiş"
					       style="{inp_style}" />
				</td>
			</tr>''')

		rows_str = '\n'.join(rows_html)

		js = '''
<script>
(function(){
	if (window._detaylarKartInit) return;
	window._detaylarKartInit = true;

	function syncToRaw() {
		var inputs = document.querySelectorAll('.detaylar-alan-inp');
		var data = {};
		inputs.forEach(function(inp) {
			var v = inp.value.trim();
			data[inp.dataset.dk] = v || 'Belirtilmemiş';
		});
		var raw = document.getElementById('id_detaylar');
		if (raw) raw.value = JSON.stringify(data, null, 2);
	}

	document.addEventListener('DOMContentLoaded', function(){
		if (!document.getElementById('detaylar-input-theme-style')) {
			var style = document.createElement('style');
			style.id = 'detaylar-input-theme-style';
			style.textContent = '' +
				'.detaylar-alan-inp::placeholder{color:#64748b!important;opacity:1;}' +
				'.detaylar-alan-inp:focus{outline:none;box-shadow:0 0 0 2px rgba(56,189,248,.25);}';
			document.head.appendChild(style);
		}

		var raw = document.getElementById('id_detaylar');
		if (raw) {
			raw.style.display = 'none';
			var wrap = raw.closest('.form-row') || raw.parentNode;
			var toggle = document.createElement('a');
			toggle.href = '#';
			toggle.textContent = '▸ Ham JSON göster / gizle';
			toggle.style.cssText = 'font-size:0.8em;color:#9ca3af;display:block;margin-top:6px;';
			toggle.addEventListener('click', function(e){
				e.preventDefault();
				raw.style.display = raw.style.display === 'none' ? 'block' : 'none';
			});
			wrap.appendChild(toggle);
		}

		document.querySelectorAll('.detaylar-alan-inp').forEach(function(inp){
			if (!inp.value || !inp.value.trim()) {
				inp.value = 'Belirtilmemiş';
			}
			inp.style.color = '#0f172a';
			inp.style.webkitTextFillColor = '#0f172a';
			inp.style.caretColor = '#0f172a';
			inp.style.background = '#f8fafc';
			inp.addEventListener('blur', function(){
				if (!inp.value || !inp.value.trim()) {
					inp.value = 'Belirtilmemiş';
				}
				syncToRaw();
			});
			inp.addEventListener('input', function(){
				syncToRaw();
				var normalized = (inp.value || '').trim().toLocaleLowerCase('tr-TR');
				var filled = normalized.length > 0 && normalized !== 'belirtilmemiş';
				var isOcr  = inp.dataset.kaynak === 'pipeline';
				inp.style.borderColor = filled ? '#22c55e' : (isOcr ? '#fb923c' : '#fbbf24');
				inp.style.color = '#0f172a';
				inp.style.webkitTextFillColor = '#0f172a';
				inp.style.caretColor = '#0f172a';
				inp.style.background = '#f8fafc';
			});
		});

		syncToRaw();

		document.querySelectorAll('form').forEach(function(f){
			f.addEventListener('submit', syncToRaw);
		});
	});
})();
</script>'''

		# ── Görsel galerisi (Tab 1: ürün görselleri, Tab 2: açıklama görselleri) ──────
		product_imgs = self._collect_product_image_urls(obj)
		source_images_ajax_url = f"/admin/urunler/urun/source-images/{obj.id}/"
		thumb_items_urun = ''
		first_preview_url = ''
		for i, img_url in enumerate(product_imgs):
			img_url_safe = img_url.replace('&', '&amp;').replace('"', '%22')
			border_col = '#38bdf8' if i == 0 else 'transparent'
			if i == 0:
				first_preview_url = img_url
			thumb_items_urun += (
				'<div data-gurl="' + img_url_safe + '" onclick="gSetPreview(this)" '
				'style="cursor:pointer;border-radius:4px;overflow:hidden;'
				'border:2px solid ' + border_col + ';aspect-ratio:1/1;background:#1e293b;">'
				'<img src="' + img_url_safe + '" '
				'style="width:100%;height:100%;object-fit:cover;" loading="lazy" '
				'onerror="this.parentNode.style.display=\'none\'"/></div>'
			)
		if not thumb_items_urun:
			thumb_items_urun = ('<p style="color:#94a3b8;grid-column:1/-1;text-align:center;'
			                    'padding:16px;font-size:0.82em;">Ürün görseli eklenmemiş.</p>')

		first_p_safe   = first_preview_url.replace('&', '&amp;').replace('"', '%22')
		p_img_display  = 'block'        if first_preview_url else 'none'
		p_ph_display   = 'none'         if first_preview_url else 'block'
		p_btn_display  = 'inline-block' if first_preview_url else 'none'
		prod_img_count = len(product_imgs)

		gallery_html = f"""<div style="width:520px;flex-shrink:0;background:#0f172a;border-radius:8px;border:1px solid #1f2937;overflow:hidden;"><div style="display:flex;background:#111827;border-bottom:1px solid #1f2937;">
<button type="button" id="gtab-urun" onclick="gGalerTab('urun')" style="flex:1;padding:8px 4px;color:#38bdf8;background:transparent;border:none;border-bottom:2px solid #38bdf8;font-weight:700;cursor:pointer;font-size:0.78em;">&#128247; Ürün Görselleri ({prod_img_count})</button>
<button type="button" id="gtab-aciklama" onclick="gGalerTab('aciklama')" style="flex:1;padding:8px 4px;color:#94a3b8;background:transparent;border:none;border-bottom:2px solid transparent;cursor:pointer;font-size:0.78em;">&#128444; Açıklama Görselleri</button></div>
<div style="position:relative;background:#020617;height:390px;overflow:hidden;display:flex;align-items:center;justify-content:center;">
<button type="button" onclick="gNavigate(-1);return false;" style="position:absolute;left:8px;top:50%;transform:translateY(-50%);width:32px;height:44px;border:1px solid #334155;border-radius:8px;background:rgba(2,6,23,0.72);color:#e2e8f0;cursor:pointer;z-index:2;font-size:1.05em;">&#10094;</button>
<img id="gorsel-preview-img" src="{first_p_safe}" style="max-height:390px;max-width:100%;object-fit:contain;display:{p_img_display};" /><span id="gorsel-preview-ph" style="color:#475569;font-size:0.88em;display:{p_ph_display};">Görsele tıklayarak önizleyin</span>
<button type="button" onclick="gNavigate(1);return false;" style="position:absolute;right:8px;top:50%;transform:translateY(-50%);width:32px;height:44px;border:1px solid #334155;border-radius:8px;background:rgba(2,6,23,0.72);color:#e2e8f0;cursor:pointer;z-index:2;font-size:1.05em;">&#10095;</button>
<a id="gorsel-buyut-btn" href="{first_p_safe}" target="_blank" style="position:absolute;top:6px;right:6px;background:rgba(0,0,0,0.6);color:#e2e8f0;border-radius:4px;padding:3px 8px;font-size:0.75em;text-decoration:none;display:{p_btn_display};">&#10530; Büyüt</a></div>
<div id="grid-urun" style="padding:9px;max-height:230px;overflow-y:auto;"><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:7px;">{thumb_items_urun}</div></div>
<div id="grid-aciklama" style="display:none;padding:9px;max-height:230px;overflow-y:auto;"><div id="aciklama-grid-inner" style="display:grid;grid-template-columns:repeat(3,1fr);gap:7px;"><p style="color:#94a3b8;grid-column:1/-1;text-align:center;padding:12px;font-size:0.82em;">Yüklemek için sekmeye tıklayın.</p></div></div></div>"""

		gallery_js = f"""<script>(function(){{
var _aYuklendi=false;
window.gGetVisibleThumbs=function(){{
	var gu=document.getElementById('grid-urun');
	var ga=document.getElementById('grid-aciklama');
	var activeGrid=(ga&&ga.style.display!=='none')?ga:gu;
	if(!activeGrid)return [];
	return Array.prototype.filter.call(activeGrid.querySelectorAll('[data-gurl]'), function(el){{
		return el.style.display!=='none';
	}});
}};
window.gSetPreview=function(el){{
  var url=el.getAttribute('data-gurl');if(!url)return;
  var img=document.getElementById('gorsel-preview-img');
  var ph=document.getElementById('gorsel-preview-ph');
  var btn=document.getElementById('gorsel-buyut-btn');
  img.src=url;img.style.display='block';
  ph.style.display='none';
  btn.href=url;btn.style.display='inline-block';
  document.querySelectorAll('[data-gurl]').forEach(function(t){{t.style.borderColor='transparent';}});
  el.style.borderColor='#38bdf8';
}};
window.gNavigate=function(step){{
	var thumbs=window.gGetVisibleThumbs();
	if(!thumbs.length)return;
	var current=(document.getElementById('gorsel-preview-img').getAttribute('src')||'').trim();
	var idx=0;
	for(var i=0;i<thumbs.length;i++){{
		if((thumbs[i].getAttribute('data-gurl')||'').trim()===current){{idx=i;break;}}
	}}
	var next=(idx+step+thumbs.length)%thumbs.length;
	window.gSetPreview(thumbs[next]);
	try{{thumbs[next].scrollIntoView({{block:'nearest',inline:'nearest'}});}}catch(_e){{}}
}};
window.gGalerTab=function(tab){{
  var tu=document.getElementById('gtab-urun');
  var ta=document.getElementById('gtab-aciklama');
  var gu=document.getElementById('grid-urun');
  var ga=document.getElementById('grid-aciklama');
  if(tab==='urun'){{
    tu.style.color='#38bdf8';tu.style.borderBottomColor='#38bdf8';
    ta.style.color='#94a3b8';ta.style.borderBottomColor='transparent';
    gu.style.display='block';ga.style.display='none';
  }}else{{
    ta.style.color='#38bdf8';ta.style.borderBottomColor='#38bdf8';
    tu.style.color='#94a3b8';tu.style.borderBottomColor='transparent';
    gu.style.display='none';ga.style.display='block';
    if(!_aYuklendi){{
      _aYuklendi=true;
      var inner=document.getElementById('aciklama-grid-inner');
      inner.innerHTML='<p style="color:#94a3b8;text-align:center;padding:12px;font-size:0.82em;">Yükleniyor...</p>';
      fetch('{source_images_ajax_url}')
        .then(function(r){{return r.json();}})
        .then(function(d){{
          var urls=(d&&d.image_urls)?d.image_urls:[];
          if(!urls.length){{inner.innerHTML='<p style="color:#94a3b8;text-align:center;padding:12px;font-size:0.82em;">Açıklama görseli yok.</p>';return;}}
          inner.innerHTML='';
          urls.forEach(function(url){{
            var w=document.createElement('div');
            w.setAttribute('data-gurl',url);
            w.style.cssText='cursor:pointer;border-radius:4px;overflow:hidden;border:2px solid transparent;aspect-ratio:1/1;background:#1e293b;';
            w.onclick=function(){{window.gSetPreview(w);}};
            var im=document.createElement('img');
            im.src=url;im.style.cssText='width:100%;height:100%;object-fit:cover;';
            im.loading='lazy';
            im.onerror=function(){{w.style.display='none';}};
            w.appendChild(im);inner.appendChild(w);
          }});
					var first=inner.querySelector('[data-gurl]');
					if(first){{window.gSetPreview(first);}}
        }})
        .catch(function(){{inner.innerHTML='<p style="color:#ef4444;text-align:center;padding:12px;font-size:0.82em;">Görsel yüklenemedi.</p>';}});
    }}
  }}
}};
}})();</script>"""

		header = (f'<b style="color:#e5e7eb;">{obj.kategori.isim}</b> — teknik parametreler &nbsp;&nbsp;'
		          f'<span style="color:#16a34a;font-weight:600;">● API (otomatik)</span> &nbsp;'
		          f'<span style="color:#ea580c;font-weight:600;">● OCR / Manuel (elle girin)</span> &nbsp;'
		          f'<span style="color:#dc2626;font-weight:600;">* zorunlu</span>')

		return mark_safe(f'''
		<div style="display:flex;gap:16px;align-items:flex-start;font-family:system-ui,sans-serif;margin-bottom:4px;">
			<div style="flex:1;min-width:0;border:1px solid #1f2937;border-radius:8px;overflow:hidden;background:#020617;">
				<div style="background:#111827;padding:8px 14px;border-bottom:1px solid #1f2937;font-size:0.83em;">{header}</div>
				<table style="width:100%;border-collapse:collapse;">{rows_str}</table>
				<div style="padding:10px 12px;border-top:1px solid #1f2937;background:#0b1220;display:flex;justify-content:flex-end;">
					<button type="submit" name="_save" value="1"
					        style="background:#2563eb;color:#fff;border:1px solid #1d4ed8;border-radius:6px;padding:7px 14px;font-size:0.86em;font-weight:700;cursor:pointer;">
						KAYDET
					</button>
				</div>
			</div>
			{gallery_html}
		</div>{js}{gallery_js}''')
	detaylar_kart.short_description = "Teknik Parametreler (Şemaya Göre)"


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
			path('fill-detaylar/<int:urun_id>/', self.admin_site.admin_view(self.fill_detaylar_view), name='urun_fill_detaylar'),
			path('source-images/<int:urun_id>/', self.admin_site.admin_view(self.source_images_view), name='urun_source_images'),
			path('link-ekle/', self.admin_site.admin_view(self.link_ekle_view), name='urun_link_ekle'),
			path('amazon-link-ekle/', self.admin_site.admin_view(self.amazon_link_ekle_view), name='urun_amazon_link_ekle'),
		]
		return custom_urls + urls

	def _extract_ebay_item_id(self, source_url: str) -> str:
		if not source_url:
			return ''
		url = source_url.strip()
		m = re.search(r'/itm/(?:[^/]+/)?(\d+)', url)
		if m:
			return m.group(1)
		m = re.search(r'item/(\d+)', url)
		if m:
			return m.group(1)
		return ''

	def _map_aspects_to_detaylar(self, aspects: list) -> dict:
		mapped = {}

		def normalize_bool_text(value: str) -> str:
			text = str(value or '').strip().lower()
			if text in {'yes', 'y', 'true', '1', 'evet', 'var'}:
				return 'Yes'
			if text in {'no', 'n', 'false', '0', 'hayir', 'hayır', 'yok'}:
				return 'No'
			return ''

		def enrich_connectivity_fields(payload: dict):
			source = ' '.join([
				str(payload.get('baglanti') or ''),
				str(payload.get('wifi') or ''),
				str(payload.get('bluetooth') or ''),
				str(payload.get('usb_c') or ''),
				str(payload.get('hdmi') or ''),
			]).lower()
			if not payload.get('wifi'):
				if 'wi-fi' in source or ' wifi' in f' {source}' or 'wlan' in source:
					payload['wifi'] = 'Yes'
				elif 'no wifi' in source:
					payload['wifi'] = 'No'
			if not payload.get('bluetooth') and 'bluetooth' in source:
				payload['bluetooth'] = 'No' if 'no bluetooth' in source else 'Yes'
			if not payload.get('usb_c'):
				if 'type-c' in source or 'usb-c' in source:
					payload['usb_c'] = 'Yes'
				elif 'micro usb' in source or 'mini usb' in source:
					payload['usb_c'] = 'No'
			if not payload.get('hdmi') and 'hdmi' in source:
				payload['hdmi'] = 'Yes'
			parts = []
			if payload.get('wifi') == 'Yes':
				parts.append('Wi-Fi')
			if payload.get('bluetooth') == 'Yes':
				parts.append('Bluetooth')
			if payload.get('usb_c') == 'Yes':
				parts.append('USB-C')
			if payload.get('hdmi') == 'Yes':
				parts.append('HDMI')
			if parts:
				payload['baglanti'] = ', '.join(parts)
		# eBay aspect adlarındaki varyasyonlar için basit eşleme tablosu
		aspect_key_map = {
			'model': 'model',
			'anbernic model': 'model',
			'retroid pocket model': 'model',
			'ekran': 'ekran_boyutu',
			'ekran boyutu': 'ekran_boyutu',
			'screen size': 'ekran_boyutu',
			'display size': 'ekran_boyutu',
			'display': 'ekran_boyutu',
			'çözünürlük': 'cozunurluk',
			'resolution': 'cozunurluk',
			'işlemci': 'cpu',
			'processor': 'cpu',
			'cpu': 'cpu',
			'chipset': 'cpu',
			'veri deposu': 'ram',
			'bellek': 'ram',
			'ram': 'ram',
			'ram size': 'ram',
			'memory': 'ram',
			'depolama kapasitesi': 'depolama',
			'depolama': 'depolama',
			'storage capacity': 'depolama',
			'hard drive capacity': 'depolama',
			'pil': 'batarya',
			'batarya': 'batarya',
			'battery capacity': 'batarya',
			'işletim sistemi': 'isletim_sistemi',
			'sistem': 'isletim_sistemi',
			'operating system': 'isletim_sistemi',
			'os': 'isletim_sistemi',
			'bağlantı': 'baglanti',
			'baglanti': 'baglanti',
			'connectivity': 'baglanti',
			'bluetooth': 'bluetooth',
			'bluetooth-compatible': 'bluetooth',
			'wifi': 'wifi',
			'wi-fi': 'wifi',
			'usb': 'usb_c',
			'usb-c': 'usb_c',
			'type-c': 'usb_c',
			'charging interface type': 'usb_c',
			'external controller interface': 'usb_c',
			'hdmi': 'hdmi',
			'ships from': 'gonderim_yeri',
		}

		for asp in aspects or []:
			name = (asp.get('name') or '').strip().lower()
			values = asp.get('value') or []
			if isinstance(values, list):
				value_text = ', '.join([str(v).strip() for v in values if str(v).strip()])
			else:
				value_text = str(values).strip()
			if not name or not value_text:
				continue
			dst = aspect_key_map.get(name)
			if dst:
				if dst in {'wifi', 'bluetooth', 'usb_c', 'hdmi'}:
					mapped[dst] = normalize_bool_text(value_text) or value_text
				else:
					mapped[dst] = value_text

		enrich_connectivity_fields(mapped)

		return mapped

	def _normalize_label(self, label: str) -> str:
		text = (label or '').strip().lower()
		replacements = {
			'ç': 'c', 'ğ': 'g', 'ı': 'i', 'İ': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u',
			'Ç': 'c', 'Ğ': 'g', 'Ö': 'o', 'Ş': 's', 'Ü': 'u',
		}
		for old, new in replacements.items():
			text = text.replace(old, new)
		text = re.sub(r'[^a-z0-9 ]+', ' ', text)
		text = re.sub(r'\s+', ' ', text).strip()
		return text

	def _map_html_specs_to_detaylar(self, html: str) -> dict:
		if not html:
			return {}
		soup = BeautifulSoup(html, 'html.parser')
		pairs = []

		for tr in soup.select('table tr'):
			th = tr.find('th')
			td = tr.find('td')
			if th and td:
				label = th.get_text(' ', strip=True)
				value = td.get_text(' ', strip=True)
				if label and value:
					pairs.append((label, value))

		for dl in soup.select('dl'):
			dts = dl.find_all('dt')
			dds = dl.find_all('dd')
			for dt, dd in zip(dts, dds):
				label = dt.get_text(' ', strip=True)
				value = dd.get_text(' ', strip=True)
				if label and value:
					pairs.append((label, value))

		for line in soup.get_text('\n', strip=True).splitlines():
			if ':' not in line:
				continue
			l, v = line.split(':', 1)
			l = l.strip()
			v = v.strip()
			if len(l) < 2 or not v:
				continue
			pairs.append((l, v))

		mapping_table = {
			'model': 'model',
			'anbernic model': 'model',
			'retroid pocket model': 'model',
			'ekran': 'ekran_boyutu',
			'ekran boyutu': 'ekran_boyutu',
			'screen size': 'ekran_boyutu',
			'display size': 'ekran_boyutu',
			'oge yuksekligi': 'ekran_boyutu',
			'item height': 'ekran_boyutu',
			'cozunurluk': 'cozunurluk',
			'resolution': 'cozunurluk',
			'islemci': 'cpu',
			'processor': 'cpu',
			'cpu': 'cpu',
			'ram': 'ram',
			'memory': 'ram',
			'veri deposu': 'ram',
			'depolama': 'depolama',
			'depolama kapasitesi': 'depolama',
			'storage': 'depolama',
			'pil': 'batarya',
			'batarya': 'batarya',
			'battery': 'batarya',
			'baglanti': 'baglanti',
			'connectivity': 'baglanti',
			'wifi': 'wifi',
			'wi fi': 'wifi',
			'bluetooth': 'bluetooth',
			'usb c': 'usb_c',
			'usb': 'usb_c',
			'type c': 'usb_c',
			'isletim sistemi': 'isletim_sistemi',
			'operating system': 'isletim_sistemi',
			'system': 'isletim_sistemi',
			'hdmi': 'hdmi',
			'ships from': 'gonderim_yeri',
		}

		mapped = {}
		for label, value in pairs:
			norm = self._normalize_label(label)
			dst = mapping_table.get(norm)
			if not dst:
				for cand, target in mapping_table.items():
					if cand in norm:
						dst = target
						break
			if not dst or not value:
				continue
			if dst not in mapped:
				mapped[dst] = value.strip()

		if mapped:
			source = ' '.join([
				str(mapped.get('baglanti') or ''),
				str(mapped.get('wifi') or ''),
				str(mapped.get('bluetooth') or ''),
				str(mapped.get('usb_c') or ''),
				str(mapped.get('hdmi') or ''),
			]).lower()
			parts = []
			if str(mapped.get('wifi') or '').strip().lower() in {'yes', 'wifi'} or 'wi-fi' in source or ' wifi' in f' {source}' or 'wlan' in source:
				mapped['wifi'] = 'Yes'
				parts.append('Wi-Fi')
			elif 'no wifi' in source:
				mapped['wifi'] = 'No'
			if str(mapped.get('bluetooth') or '').strip().lower() == 'yes' or 'bluetooth' in source:
				mapped['bluetooth'] = 'Yes'
				parts.append('Bluetooth')
			elif 'no bluetooth' in source:
				mapped['bluetooth'] = 'No'
			if 'type-c' in source or 'usb-c' in source:
				mapped['usb_c'] = 'Yes'
				parts.append('USB-C')
			elif 'micro usb' in source or 'mini usb' in source:
				mapped['usb_c'] = 'No'
			if 'hdmi' in source:
				mapped['hdmi'] = 'Yes'
				parts.append('HDMI')
			if parts:
				mapped['baglanti'] = ', '.join(dict.fromkeys(parts))

		return mapped

	def _get_missing_schema_keys(self, urun) -> set[str]:
		excluded_keys = {'kontrolcu', 'oyun_sayisi', 'kutu_icerigi', 'ocr_adayi'}
		missing = set()
		alanlar = getattr(getattr(urun, 'kategori', None), 'alanlar', None) or []
		mevcut = dict(urun.detaylar or {})
		for alan in alanlar:
			key = alan.get('key')
			if not key or key in excluded_keys:
				continue
			value = str(mevcut.get(key, '') or '').strip()
			if not value or value.lower() == 'belirtilmemiş':
				missing.add(key)
		return missing

	def _get_ocr_engine(self):
		if RapidOCR is None:
			return None
		if self._rapidocr_engine is None:
			self._rapidocr_engine = RapidOCR()
		return self._rapidocr_engine

	def _extract_candidate_image_urls(self, html: str, base_url: str) -> list[str]:
		if not html:
			return []
		soup = BeautifulSoup(html, 'html.parser')
		urls = []
		seen = set()
		skip_tokens = ('sprite', 'logo', 'icon', 'avatar', 'thumb', 'thumbnail', '1x1', 'spacer')
		for img in soup.select('img'):
			width = (img.get('width') or '').strip()
			height = (img.get('height') or '').strip()
			try:
				if width.isdigit() and height.isdigit() and int(width) < 180 and int(height) < 180:
					continue
			except Exception:
				pass

			for attr in ('src', 'data-src', 'data-zoom-src', 'data-lazy-src', 'data-image-url'):
				raw = (img.get(attr) or '').strip()
				if not raw or raw.startswith('data:'):
					continue
				full = urljoin(base_url, raw)
				full_lower = full.lower()
				if not full_lower.startswith(('http://', 'https://')):
					continue
				if any(token in full_lower for token in skip_tokens):
					continue
				if full in seen:
					continue
				seen.add(full)
				urls.append(full)
				break

		return urls[:12]

	def _extract_image_urls_from_soup(self, soup, base_url: str, limit: int = 16) -> list[str]:
		urls = []
		seen = set()
		skip_tokens = ('sprite', 'logo', 'icon', 'avatar', 'thumb', 'thumbnail', '1x1', 'spacer')
		for img in soup.select('img'):
			for attr in ('src', 'data-src', 'data-zoom-src', 'data-lazy-src', 'data-image-url', 'data-original'):
				raw = (img.get(attr) or '').strip()
				if not raw or raw.startswith('data:'):
					continue
				full = urljoin(base_url, raw)
				full_lower = full.lower()
				if not full_lower.startswith(('http://', 'https://')):
					continue
				if any(token in full_lower for token in skip_tokens):
					continue
				if full in seen:
					continue
				seen.add(full)
				urls.append(full)
				break
			if len(urls) >= limit:
				break
		return urls

	def _fetch_html(self, url: str, referer_url: str = '', timeout: int = 25) -> str:
		if not url:
			return ''
		try:
			headers = {
				'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
			}
			if referer_url:
				headers['Referer'] = referer_url
			resp = requests.get(url, headers=headers, timeout=timeout)
			if resp.status_code == 200:
				return resp.text
		except Exception:
			return ''
		return ''

	def _extract_seller_description_assets(self, html: str, base_url: str) -> dict:
		if not html:
			return {'text': '', 'image_urls': []}

		soup = BeautifulSoup(html, 'html.parser')
		desc_texts = []
		desc_images = []
		seen_text = set()
		seen_url = set()

		def push_text(raw_text: str):
			text = str(raw_text or '').strip()
			if not text:
				return
			if len(text) < 12:
				return
			if text in seen_text:
				return
			seen_text.add(text)
			desc_texts.append(text)

		def push_url(url: str):
			clean = str(url or '').strip()
			if not clean:
				return
			full = urljoin(base_url, clean)
			full = self._upgrade_image_url_for_preview(full)
			if not full.lower().startswith(('http://', 'https://')):
				return
			if full in seen_url:
				return
			seen_url.add(full)
			desc_images.append(full)

		description_selectors = [
			'#viTabs_0_is', '#vi-desc-maincntr', '#itemDescription', '#desc_div', '#desc_wrapper',
			'[data-testid="x-item-description"]', '[class*="description"]', '[id*="description"]',
		]
		for selector in description_selectors:
			for node in soup.select(selector):
				push_text(node.get_text('\n', strip=True))
				for img_url in self._extract_image_urls_from_soup(node, base_url, limit=24):
					push_url(img_url)

		for script in soup.select('script[type="application/ld+json"]'):
			try:
				payload = json.loads(script.get_text(strip=True) or '{}')
			except Exception:
				continue
			if isinstance(payload, dict):
				desc_val = payload.get('description')
				if isinstance(desc_val, str):
					push_text(desc_val)

		iframe_urls = []
		for iframe in soup.select('iframe'):
			src = (iframe.get('src') or '').strip()
			if not src:
				continue
			src_low = src.lower()
			if any(token in src_low for token in ('desc', 'description', 'vi_item_desc')):
				iframe_urls.append(urljoin(base_url, src))

		for regex in [
			r'"descriptionIframeUrl"\s*:\s*"([^"]+)"',
			r'"descIframe"\s*:\s*"([^"]+)"',
			r'"iframeUrl"\s*:\s*"([^"]*desc[^"]*)"',
		]:
			for match in re.findall(regex, html, re.IGNORECASE):
				iframe_urls.append(urljoin(base_url, match.replace('\\/', '/')))

		for iframe_url in iframe_urls[:3]:
			iframe_html = self._fetch_html(iframe_url, referer_url=base_url, timeout=25)
			if not iframe_html:
				continue
			iframe_soup = BeautifulSoup(iframe_html, 'html.parser')
			push_text(iframe_soup.get_text('\n', strip=True))
			for img_url in self._extract_image_urls_from_soup(iframe_soup, iframe_url, limit=24):
				push_url(img_url)

		joined_text = '\n'.join(desc_texts)
		return {
			'text': joined_text,
			'image_urls': desc_images[:24],
		}

	def _run_ocr_on_image_bytes(self, image_bytes: bytes) -> str:
		engine = self._get_ocr_engine()
		if not engine or not image_bytes:
			return ''

		def _collect_lines(payload: bytes) -> list[str]:
			try:
				result, _meta = engine(payload)
			except Exception:
				return []
			lines = []
			for row in result or []:
				if len(row) < 2:
					continue
				text = str(row[1]).strip()
				if not text:
					continue
				confidence = 1.0
				if len(row) > 2:
					try:
						confidence = float(row[2])
					except Exception:
						confidence = 1.0
				if confidence >= 0.35:
					lines.append(text)
			return lines

		all_lines = []
		seen_lines = set()
		for line in _collect_lines(image_bytes):
			if line not in seen_lines:
				seen_lines.add(line)
				all_lines.append(line)

		if Image is None:
			return '\n'.join(all_lines)

		try:
			base_image = Image.open(BytesIO(image_bytes)).convert('RGB')
		except Exception:
			return '\n'.join(all_lines)

		variants = []
		width, height = base_image.size
		if width and height:
			variants.append(ImageOps.grayscale(base_image))
			variants.append(ImageOps.autocontrast(ImageOps.grayscale(base_image)))
			upscaled = base_image.resize((max(width * 2, width), max(height * 2, height)))
			variants.append(ImageOps.autocontrast(ImageOps.grayscale(upscaled)))
			if ImageFilter is not None:
				variants.append(ImageOps.autocontrast(ImageOps.grayscale(upscaled.filter(ImageFilter.SHARPEN))))

		for variant in variants:
			try:
				buffer = BytesIO()
				variant.save(buffer, format='PNG')
				for line in _collect_lines(buffer.getvalue()):
					if line not in seen_lines:
						seen_lines.add(line)
						all_lines.append(line)
			except Exception:
				continue

		return '\n'.join(all_lines)

	def _extract_value_from_line(self, line: str) -> str:
		clean = (line or '').strip().strip('-').strip()
		if not clean:
			return ''
		for separator in (':', '-', '：'):
			if separator in clean:
				left, right = clean.split(separator, 1)
				right = right.strip()
				if right and len(right) <= 120:
					return right
		return clean if len(clean) <= 120 else ''

	def _map_ocr_text_to_detaylar(self, text: str, target_keys: set[str] | None = None) -> dict:
		if not text:
			return {}

		def wants(key: str) -> bool:
			return not target_keys or key in target_keys

		mapped = {}
		connectivity = []
		lines = [line.strip() for line in text.splitlines() if line.strip()]
		joined_text = ' '.join(lines)

		for line in lines:
			norm = self._normalize_label(line)
			value = self._extract_value_from_line(line)

			# Etiketsiz serbest satır: "3.5 inch screen", "3.5\" display" vb.
			if wants('ekran_boyutu') and 'ekran_boyutu' not in mapped:
				free_inch = re.search(r'(\d+(?:[\.,]\d+)?)\s*[-–]?\s*(?:inch|in\b|\"|inches|inç)\b', line, re.IGNORECASE)
				if free_inch:
					try:
						num_free = float(free_inch.group(1).replace(',', '.'))
					except Exception:
						num_free = 0.0
					if 1.5 <= num_free <= 12.5:
						mapped['ekran_boyutu'] = f"{num_free:g} inç"

			if wants('ekran_boyutu') and 'ekran_boyutu' not in mapped and any(token in norm for token in ('screen', 'display', 'ekran')):
				match = re.search(r'(\d+(?:[\.,]\d+)?)\s*[-–]?\s*(?:inch|in\b|"|inches)', line, re.IGNORECASE)
				if match:
					try:
						num = float(match.group(1).replace(',', '.'))
					except Exception:
						num = 0.0
					if 1.5 <= num <= 12.5:
						mapped['ekran_boyutu'] = f"{num:g} inç"
				elif value and re.search(r'(\d+(?:[\.,]\d+)?)\s*[-–]?\s*(?:inch|in\b|inç|cm|"|inches)', value, re.IGNORECASE):
					size_match = re.search(r'(\d+(?:[\.,]\d+)?)\s*[-–]?\s*(?:inch|in\b|inç|cm|"|inches)', value, re.IGNORECASE)
					if size_match:
						try:
							num = float(size_match.group(1).replace(',', '.'))
						except Exception:
							num = 0.0
						if 1.5 <= num <= 12.5:
							mapped['ekran_boyutu'] = value

			# Etiketsiz çözünürlük: "640*480", "1280x720" gibi serbest satır
			if wants('cozunurluk') and 'cozunurluk' not in mapped:
				free_res = re.search(r'\b(\d{3,5}\s*[xX*]\s*\d{3,5})\b', line)
				if free_res:
					mapped['cozunurluk'] = free_res.group(1).replace('*', 'x').replace(' ', '')

			if wants('cozunurluk') and 'cozunurluk' not in mapped and any(token in norm for token in ('resolution', 'cozunurluk')):
				match = re.search(r'(\d{3,5}\s*[xX*]\s*\d{3,5})', line)
				if match:
					mapped['cozunurluk'] = match.group(1).replace('*', 'x').replace(' ', '')
				elif value:
					mapped['cozunurluk'] = value

			if wants('ram') and 'ram' not in mapped and re.search(r'\b(ram|memory)\b', norm):
				match = re.search(r'(\d+(?:[\.,]\d+)?)\s*(GB|MB)', line, re.IGNORECASE)
				if match:
					mapped['ram'] = match.group(0).replace(' ', '')

			if wants('depolama') and 'depolama' not in mapped and any(token in norm for token in ('storage', 'rom', 'depolama', 'internal memory')):
				match = re.search(r'(\d+(?:[\.,]\d+)?)\s*(TB|GB|MB)', line, re.IGNORECASE)
				if match:
					mapped['depolama'] = match.group(0).replace(' ', '')

			if wants('batarya') and 'batarya' not in mapped and any(token in norm for token in ('battery', 'batarya', 'mah')):
				match = re.search(r'(\d{3,6}\s*mAh)', line, re.IGNORECASE)
				mapped['batarya'] = match.group(1).replace(' ', '') if match else value

			if wants('cpu') and 'cpu' not in mapped and any(token in norm for token in ('cpu', 'processor', 'chipset', 'islemci')) and value:
				if 2 <= len(value) <= 60:
					mapped['cpu'] = value

			if wants('isletim_sistemi') and 'isletim_sistemi' not in mapped:
				# 'Operating System: Linux' gibi açık etiket + değer formatı
				os_label_match = re.search(r'(?:operating system|işletim sistemi|isletim sistemi)\s*[:\-–]\s*([^\n\r\.;,]{1,50})', line, re.IGNORECASE)
				if os_label_match:
					os_val = os_label_match.group(1).strip()
					if any(token in os_val.lower() for token in ('android', 'linux', 'windows', 'batocera')):
						mapped['isletim_sistemi'] = os_val
				# value kısa ve net bir OS adıysa al
				elif value and len(value) <= 40 and any(token in value.lower() for token in ('android', 'linux', 'windows', 'batocera')):
					mapped['isletim_sistemi'] = value

			if wants('hdmi') and 'hdmi' not in mapped and 'hdmi' in norm:
				mapped['hdmi'] = 'Var'

			# "Quad core" / "Quad-core" işlemci etiketsiz gelirse yakala
			if wants('cpu') and 'cpu' not in mapped:
				cpu_free = re.search(r'\b((?:quad|dual|octa|hexa|single)[\s-]?core[^\n\r]{0,30})', line, re.IGNORECASE)
				if cpu_free:
					mapped['cpu'] = cpu_free.group(1).strip()

			# "OTG Transfer" → bağlantı
			if wants('baglanti') and re.search(r'\botg\b', norm):
				if 'OTG' not in connectivity:
					connectivity.append('OTG')

			if wants('baglanti') and any(token in norm for token in ('wifi', 'wi fi', 'bluetooth', 'usb', 'type c', 'hdmi')):
				for token in ('Wi-Fi', 'Bluetooth', 'USB', 'Type-C', 'HDMI'):
					if token.lower().replace('-', ' ') in norm and token not in connectivity:
						connectivity.append(token)

		if wants('ekran_boyutu') and 'ekran_boyutu' not in mapped:
			match = re.search(r'(\d+(?:[\.,]\d+)?)\s*[-–]?\s*(?:inch|in\b|"|inches)', joined_text, re.IGNORECASE)
			if match:
				try:
					num = float(match.group(1).replace(',', '.'))
				except Exception:
					num = 0.0
				if 1.5 <= num <= 12.5:
					mapped['ekran_boyutu'] = f"{num:g} inç"

		if wants('cozunurluk') and 'cozunurluk' not in mapped:
			match = re.search(r'(\d{3,5}\s*[xX*]\s*\d{3,5})', joined_text)
			if match:
				mapped['cozunurluk'] = match.group(1).replace('*', 'x').replace(' ', '')

		if wants('batarya') and 'batarya' not in mapped:
			match = re.search(r'(\d{3,6}\s*mAh)', joined_text, re.IGNORECASE)
			if match:
				mapped['batarya'] = match.group(1).replace(' ', '')

		# isletim_sistemi için tam metin taraması (etiket:değer formatı)
		if wants('isletim_sistemi') and 'isletim_sistemi' not in mapped:
			os_match = re.search(r'(?:operating system|işletim sistemi|isletim sistemi)\s*[:\-–]\s*([^\n\r\.;,]{1,50})', joined_text, re.IGNORECASE)
			if os_match:
				os_val = os_match.group(1).strip()
				if any(token in os_val.lower() for token in ('android', 'linux', 'windows', 'batocera')):
					mapped['isletim_sistemi'] = os_val

		if wants('baglanti') and connectivity and 'baglanti' not in mapped:
			mapped['baglanti'] = ', '.join(connectivity)

		return {key: value for key, value in mapped.items() if value}

	def _map_ocr_images_to_detaylar(self, html: str, base_url: str, target_keys: set[str] | None = None) -> tuple[dict, dict]:
		engine = self._get_ocr_engine()
		if not engine:
			return {}, {'ocr_enabled': False, 'image_count': 0, 'matched_keys': 0}

		image_urls = self._extract_candidate_image_urls(html, base_url)
		if not image_urls:
			return {}, {'ocr_enabled': True, 'image_count': 0, 'matched_keys': 0}

		headers = {
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
			'Referer': base_url,
		}
		mapped = {}
		scanned = 0
		for image_url in image_urls:
			if target_keys and target_keys.issubset(mapped.keys()):
				break
			try:
				resp = requests.get(image_url, headers=headers, timeout=20)
				if resp.status_code != 200:
					continue
				content_type = (resp.headers.get('Content-Type') or '').lower()
				if content_type and 'image' not in content_type:
					continue
				scanned += 1
				ocr_text = self._run_ocr_on_image_bytes(resp.content)
				ocr_mapped = self._map_ocr_text_to_detaylar(ocr_text, target_keys=target_keys)
				for key, value in ocr_mapped.items():
					mapped.setdefault(key, value)
			except Exception:
				continue

		return mapped, {'ocr_enabled': True, 'image_count': scanned, 'matched_keys': len(mapped)}

	def _collect_product_image_urls(self, urun) -> list[str]:
		urls = []
		seen = set()

		def push(url: str):
			clean = str(url or '').strip()
			if not clean:
				return
			if clean.startswith('//'):
				clean = f'https:{clean}'
			clean = self._upgrade_image_url_for_preview(clean)
			if not clean.lower().startswith(('http://', 'https://')):
				return
			if clean in seen:
				return
			seen.add(clean)
			urls.append(clean)

		push(getattr(urun, 'resim_url', None))
		for img in urun.resimler.all().order_by('sira', 'id')[:12]:
			push(getattr(img, 'resim_url', None))

		return urls

	def _upgrade_image_url_for_preview(self, url: str) -> str:
		"""Bazı kaynakların thumbnail URL'lerini daha net sürüme yükseltir."""
		clean = str(url or '').strip()
		if not clean:
			return ''
		low = clean.lower()
		if 'ebayimg.com' in low or 'ebaystatic.com' in low:
			# eBay'de s-l64/s-l300/s-l500 gibi URL'ler düşük çözünürlük olabilir.
			clean = re.sub(r'/s-l\d+(\.[a-z0-9]+)(\?.*)?$', r'/s-l1600\1\2', clean, flags=re.IGNORECASE)
		return clean

	def _map_ocr_from_known_urls(self, image_urls: list[str], referer_url: str, target_keys: set[str] | None = None) -> tuple[dict, dict]:
		engine = self._get_ocr_engine()
		if not engine or not image_urls:
			return {}, {'ocr_enabled': bool(engine), 'image_count': 0, 'matched_keys': 0}

		headers = {
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
			'Referer': referer_url,
		}
		mapped = {}
		scanned = 0
		for image_url in image_urls:
			if target_keys and target_keys.issubset(mapped.keys()):
				break
			try:
				resp = requests.get(image_url, headers=headers, timeout=20)
				if resp.status_code != 200:
					continue
				content_type = (resp.headers.get('Content-Type') or '').lower()
				if content_type and 'image' not in content_type:
					continue
				scanned += 1
				ocr_text = self._run_ocr_on_image_bytes(resp.content)
				ocr_mapped = self._map_ocr_text_to_detaylar(ocr_text, target_keys=target_keys)
				for key, value in ocr_mapped.items():
					mapped.setdefault(key, value)
			except Exception:
				continue

		return mapped, {'ocr_enabled': True, 'image_count': scanned, 'matched_keys': len(mapped)}

	def _merge_source_candidates(self, merged: dict, incoming: dict, source_label: str):
		for key, value in (incoming or {}).items():
			clean = str(value or '').strip()
			if not clean or key in merged:
				continue
			merged[key] = {'value': clean, 'source': source_label}

	def _build_fill_preview(self, urun, mapped: dict) -> list[dict]:
		excluded_keys = {'kontrolcu', 'oyun_sayisi', 'kutu_icerigi'}
		label_map = {}
		if urun.kategori and urun.kategori.alanlar:
			for alan in urun.kategori.alanlar:
				key = alan.get('key')
				if not key or key in excluded_keys or key == 'ocr_adayi':
					continue
				label_map[key] = alan.get('label', key.replace('_', ' ').title())

		preview = []
		mevcut = dict(urun.detaylar or {})
		for key, payload in mapped.items():
			if key in excluded_keys:
				continue
			if isinstance(payload, dict):
				new_val = payload.get('value', '')
				source_label = payload.get('source', '-')
			else:
				new_val = payload
				source_label = '-'
			old_val = str(mevcut.get(key, '') or '').strip() or 'Belirtilmemiş'
			is_missing = old_val.lower() == 'belirtilmemiş'
			preview.append({
				'key': key,
				'label': label_map.get(key, key.replace('_', ' ').title()),
				'old_value': old_val,
				'new_value': str(new_val).strip(),
				'source': source_label,
				'can_apply': is_missing,
			})
		preview.sort(key=lambda row: (not row['can_apply'], row['label']))
		return preview

	def fill_detaylar_view(self, request, urun_id):
		urun = self.get_object(request, urun_id)
		if not urun:
			messages.error(request, 'Ürün bulunamadı.')
			return redirect('../')

		if not urun.source_url:
			messages.error(request, 'Source URL boş. Önce ürün kaynak linkini girin.')
			return redirect(f'/admin/urunler/urun/{urun.id}/change/')

		if 'ebay.' not in urun.source_url.lower():
			messages.warning(request, 'Şimdilik sadece eBay source URL destekleniyor.')
			return redirect(f'/admin/urunler/urun/{urun.id}/change/')

		item_id = str(getattr(urun, 'item_id', '') or '').strip() or self._extract_ebay_item_id(urun.source_url)
		client_id = getattr(settings, 'EBAY_PRODUCTION_CLIENT_ID', None)
		client_secret = getattr(settings, 'EBAY_PRODUCTION_CLIENT_SECRET', None)
		merged = {}
		diagnostics = {
			'api_enabled': bool(client_id and client_secret and item_id),
			'api_matched': 0,
			'html_matched': 0,
			'desc_text_matched': 0,
			'saved_desc_text_matched': 0,
			'desc_image_count': 0,
			'desc_ocr_matched': 0,
			'ocr_enabled': bool(RapidOCR),
			'ocr_image_count': 0,
			'ocr_matched': 0,
			'ocr_known_image_count': 0,
		}

		if client_id and client_secret and item_id:
			connector = EbayAPIConnector(
				client_id=client_id,
				client_secret=client_secret,
				sandbox=False,
			)
			try:
				if connector.get_oauth_token():
					details = connector.get_item_details(item_id)
					api_mapped = self._map_aspects_to_detaylar((details or {}).get('localizedAspects') or [])
					self._merge_source_candidates(merged, api_mapped, 'API')
					diagnostics['api_matched'] = len(api_mapped)
				else:
					messages.warning(request, 'eBay API erişimi başarısız oldu; HTML ve OCR taraması denenecek.')
			except Exception:
				messages.warning(request, 'eBay API çağrısı hata verdi; HTML ve OCR taraması denenecek.')
		elif not item_id:
			messages.info(request, 'eBay item ID çözülemedi; yalnızca HTML ve OCR taraması denenecek.')
		else:
			messages.info(request, 'eBay API bilgileri eksik; yalnızca HTML ve OCR taraması denenecek.')

		html_text = ''
		try:
			headers = {
				'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
			}
			resp = requests.get(urun.source_url, headers=headers, timeout=25)
			if resp.status_code == 200:
				html_text = resp.text
		except Exception:
			html_text = ''

		if html_text:
			html_mapped = self._map_html_specs_to_detaylar(html_text)
			self._merge_source_candidates(merged, html_mapped, 'HTML')
			diagnostics['html_matched'] = len(html_mapped)

			desc_assets = self._extract_seller_description_assets(html_text, urun.source_url)
			desc_text = desc_assets.get('text', '')
			desc_images = desc_assets.get('image_urls', [])

			missing_keys = self._get_missing_schema_keys(urun)
			if desc_text and missing_keys:
				desc_text_mapped = self._map_ocr_text_to_detaylar(desc_text, target_keys=missing_keys)
				self._merge_source_candidates(merged, desc_text_mapped, 'Açıklama Metni')
				diagnostics['desc_text_matched'] = len(desc_text_mapped)

			missing_keys = self._get_missing_schema_keys(urun)
			if desc_images and missing_keys:
				desc_img_mapped, desc_img_meta = self._map_ocr_from_known_urls(desc_images, urun.source_url, target_keys=missing_keys)
				self._merge_source_candidates(merged, desc_img_mapped, 'Açıklama Görseli OCR')
				diagnostics['desc_image_count'] = desc_img_meta.get('image_count', 0)
				diagnostics['desc_ocr_matched'] = desc_img_meta.get('matched_keys', 0)

			missing_keys = self._get_missing_schema_keys(urun)
			if missing_keys:
				ocr_mapped, ocr_meta = self._map_ocr_images_to_detaylar(html_text, urun.source_url, target_keys=missing_keys)
				self._merge_source_candidates(merged, ocr_mapped, 'OCR')
				diagnostics['ocr_enabled'] = ocr_meta.get('ocr_enabled', diagnostics['ocr_enabled'])
				diagnostics['ocr_image_count'] = ocr_meta.get('image_count', 0)
				diagnostics['ocr_matched'] = ocr_meta.get('matched_keys', 0)

		missing_keys = self._get_missing_schema_keys(urun)
		saved_desc_text = str(getattr(urun, 'aciklama', '') or '').strip()
		if saved_desc_text and missing_keys:
			saved_desc_mapped = self._map_ocr_text_to_detaylar(saved_desc_text, target_keys=missing_keys)
			self._merge_source_candidates(merged, saved_desc_mapped, 'Kayıtlı Açıklama Metni')
			diagnostics['saved_desc_text_matched'] = len(saved_desc_mapped)

		missing_keys = self._get_missing_schema_keys(urun)
		known_image_urls = self._collect_product_image_urls(urun)
		if known_image_urls and missing_keys:
			ocr2_mapped, ocr2_meta = self._map_ocr_from_known_urls(known_image_urls, urun.source_url, target_keys=missing_keys)
			self._merge_source_candidates(merged, ocr2_mapped, 'OCR (Urun Gorselleri)')
			diagnostics['ocr_known_image_count'] = ocr2_meta.get('image_count', 0)
			diagnostics['ocr_matched'] += ocr2_meta.get('matched_keys', 0)

		if not merged:
			messages.warning(request, 'API, HTML ve OCR taramasında eşleşen teknik alan bulunamadı.')
			return redirect(f'/admin/urunler/urun/{urun.id}/change/')

		preview = self._build_fill_preview(urun, merged)
		if request.method == 'POST':
			selected_keys = request.POST.getlist('selected_keys')
			if not selected_keys:
				messages.info(request, 'Uygulanacak alan seçilmedi.')
				return redirect(f'/admin/urunler/urun/{urun.id}/change/')

			detaylar = dict(urun.detaylar or {})
			updated = []
			for row in preview:
				if row['key'] not in selected_keys:
					continue
				if not row['can_apply']:
					continue
				detaylar[row['key']] = row['new_value']
				updated.append(f"{row['label']}={row['new_value']}")

			if not updated:
				messages.info(request, 'Seçilen alanlarda uygulanabilir değişiklik bulunamadı.')
				return redirect(f'/admin/urunler/urun/{urun.id}/change/')

			urun.detaylar = detaylar
			urun.save(update_fields=['detaylar'])
			messages.success(request, f'{len(updated)} alan kaynaktan dolduruldu: ' + ', '.join(updated[:6]))
			return redirect(f'/admin/urunler/urun/{urun.id}/change/')

		context = {
			'title': 'Kaynaktan Doldur Onizleme',
			'opts': self.model._meta,
			'original': urun,
			'urun': urun,
			'preview_rows': preview,
			'source_url': urun.source_url,
			'diagnostics': diagnostics,
		}
		return render(request, 'admin/urunler/urun/fill_detaylar_preview.html', context)

	def source_images_view(self, request, urun_id):
		"""Açıklama görsellerini AJAX ile döner (galeri Tab 2 için)."""
		from django.http import JsonResponse
		urun = self.get_object(request, urun_id)
		if not urun:
			return JsonResponse({'image_urls': []}, status=404)
		if not urun.source_url:
			return JsonResponse({'image_urls': []})
		html = self._fetch_html(urun.source_url)
		if not html:
			return JsonResponse({'image_urls': []})
		assets = self._extract_seller_description_assets(html, urun.source_url)
		return JsonResponse({'image_urls': assets.get('image_urls', [])})

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
	list_filter = ("link_type", "timestamp")
	search_fields = ("urun__isim", "subid", "user__username")
	ordering = ("-timestamp",)
	date_hierarchy = "timestamp"

