"""
Django Management Command: import_ebay_products
Fetches products from eBay Browse API and saves to database
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from urunler.ebay_api import EbayAPIConnector
from urunler.models import Urun, Magaza, Fiyat, UrunResim, KategoriSema
from decimal import Decimal
import logging
import re
import importlib
import random
import string
import json
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

logger = logging.getLogger(__name__)


RETRO_HANDHELD_SCHEMA = [
    {"key": "model",          "label": "Model",              "zorunlu": False, "kaynak": "description"},
    {"key": "ekran_boyutu",   "label": "Ekran Boyutu",       "zorunlu": True,  "kaynak": "description"},
    {"key": "cozunurluk",     "label": "Çözünürlük",         "zorunlu": True,  "kaynak": "description"},
    {"key": "cpu",            "label": "İşlemci (CPU)",      "zorunlu": True,  "kaynak": "description"},
    {"key": "ram",            "label": "RAM",                "zorunlu": True,  "kaynak": "description"},
    {"key": "depolama",       "label": "Depolama",           "zorunlu": True,  "kaynak": "description"},
    {"key": "batarya",        "label": "Batarya",            "zorunlu": False, "kaynak": "description"},
    {"key": "baglanti",       "label": "Bağlantı",           "zorunlu": False, "kaynak": "description"},
    {"key": "wifi",           "label": "Wi-Fi",              "zorunlu": False, "kaynak": "description"},
    {"key": "bluetooth",      "label": "Bluetooth",          "zorunlu": False, "kaynak": "description"},
    {"key": "usb_c",          "label": "USB-C",              "zorunlu": False, "kaynak": "description"},
    {"key": "isletim_sistemi","label": "İşletim Sistemi",    "zorunlu": False, "kaynak": "description"},
    {"key": "hdmi",           "label": "HDMI Çıkışı",        "zorunlu": False, "kaynak": "description"},
    {"key": "gonderim_yeri",  "label": "Gönderim Yeri",      "zorunlu": False, "kaynak": "description"},
    {"key": "ocr_adayi",      "label": "OCR Adayı (Görsel)", "zorunlu": False, "kaynak": "pipeline"},
]


DETAIL_KEY_MAP = {
    'model': 'model',
    'ekran': 'ekran_boyutu',
    'öğe yüksekliği': 'ekran_boyutu',
    'oge yuksekligi': 'ekran_boyutu',
    'item height': 'ekran_boyutu',
    'cozunurluk': 'cozunurluk',
    'cpu': 'cpu',
    'ram': 'ram',
    'depolama': 'depolama',
    'batarya': 'batarya',
    'baglanti': 'baglanti',
    'wifi': 'wifi',
    'wi-fi': 'wifi',
    'bluetooth': 'bluetooth',
    'usb c': 'usb_c',
    'usb-c': 'usb_c',
    'type c': 'usb_c',
    'isletim sistemi': 'isletim_sistemi',
    'isletim_sistemi': 'isletim_sistemi',
    'cikis': 'hdmi',
    'gonderim yeri': 'gonderim_yeri',
    'ships from': 'gonderim_yeri',
    'kontrolcu': 'kontrolcu',
    'oyun': 'oyun_sayisi',
    'kutu icerigi': 'kutu_icerigi',
}


ASPECT_KEY_MAP = {
    'model': 'model',
    'anbernic model': 'model',
    'retroid pocket model': 'model',
    'screen size': 'ekran_boyutu',
    'display size': 'ekran_boyutu',
    'item height': 'ekran_boyutu',
    'resolution': 'cozunurluk',
    'processor': 'cpu',
    'cpu model': 'cpu',
    'ram size': 'ram',
    'memory': 'ram',
    'storage capacity': 'depolama',
    'hard drive capacity': 'depolama',
    'battery capacity': 'batarya',
    'operating system': 'isletim_sistemi',
    'os': 'isletim_sistemi',
    'connectivity': 'baglanti',
    'bluetooth': 'bluetooth',
    'bluetooth-compatible': 'bluetooth',
    'wifi': 'wifi',
    'wi-fi': 'wifi',
    'charging interface type': 'usb_c',
    'external controller interface': 'usb_c',
    'hdmi': 'hdmi',
    'ships from': 'gonderim_yeri',
    'controller': 'kontrolcu',
}


def build_epn_rover_url(item_url: str, campaign_id: str, custom_id: int | None = None) -> str:
    if not item_url:
        return ''

    if 'rover.ebay.com' in item_url:
        return item_url

    if not campaign_id:
        return item_url

    parsed = urlparse(item_url)

    clean_path = parsed.path
    if '/itm/' in clean_path:
        item_id = clean_path.split('/itm/', 1)[1].split('/', 1)[0]
        clean_path = f"/itm/{item_id}"

    # Keep URL short and stable: only required affiliate params + language hints.
    final_params = {
        'mkcid': '1',
        'mkrid': '711-53200-19255-0',
        'siteid': '0',
        'campid': str(campaign_id),
        'toolid': '10001',
        'mkevt': '1',
        '_lang': 'tr-TR',
        '_ul': 'TR',
    }
    if custom_id is not None:
        final_params['customid'] = str(custom_id)

    return urlunparse((
        parsed.scheme or 'https',
        parsed.netloc or 'www.ebay.com',
        clean_path,
        '',
        urlencode(final_params),
        ''
    ))


class Command(BaseCommand):
    help = 'Import products from eBay Browse API'

    def add_arguments(self, parser):
        parser.add_argument(
            'search_query',
            type=str,
            help='Search query (e.g., "drone" or "trimui smart pro")'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Number of products to import (default: 20, max: 200)'
        )
        parser.add_argument(
            '--offset',
            type=int,
            default=0,
            help='Kaçıncı üründen itibaren başlasın (varsayılan: 0)'
        )
        parser.add_argument(
            '--sandbox',
            action='store_true',
            help='Use sandbox environment (default: false = production)'
        )
        parser.add_argument(
            '--campaign-id',
            type=str,
            default='5339143578',
            help='eBay Partner Network campaign ID'
        )
        parser.add_argument(
            '--translate-tr',
            action='store_true',
            help='Translate title/category/details to Turkish when possible'
        )
        parser.add_argument(
            '--category-slug',
            type=str,
            default='retro-handheld',
            help='Ürünlerin atanacağı kategori slug\'ı (varsayılan: retro-handheld)'
        )
        parser.add_argument(
            '--category-name',
            type=str,
            default='Retro El Konsolu',
            help='Kategori yoksa oluşturulacak ad (varsayılan: Retro El Konsolu)'
        )
        parser.add_argument(
            '--ship-to',
            type=str,
            default='US',
            help='Kargo hedef ülke kodu (varsayılan: US)'
        )

    def handle(self, *args, **options):
        search_query = options['search_query']
        limit = min(options['limit'], 200)  # Max 200
        offset = max(options.get('offset', 0), 0)
        use_sandbox = options['sandbox']
        campaign_id = options['campaign_id']
        translate_tr = options['translate_tr']
        category_slug = options['category_slug']
        category_name = options['category_name']
        ship_to_country = options['ship_to'].upper()

        translator = None
        translation_cache = {}
        if translate_tr:
            GoogleTranslator = None
            try:
                deep_translator_module = importlib.import_module('deep_translator')
                GoogleTranslator = getattr(deep_translator_module, 'GoogleTranslator', None)
            except Exception:
                GoogleTranslator = None

            if GoogleTranslator is None:
                self.stdout.write(self.style.WARNING('~ deep_translator not installed, translation disabled'))
            else:
                translator = GoogleTranslator(source='auto', target='tr')

        def tr_text(text: str) -> str:
            if not text:
                return ''
            if not translator:
                return text
            if text in translation_cache:
                return translation_cache[text]
            try:
                translated = translator.translate(text)
                translation_cache[text] = translated
                return translated
            except Exception:
                return text

        def generate_unique_code(length=5):
            """Generate unique 5-digit product code (same as AliExpress imports)"""
            while True:
                code = ''.join(random.choices(string.digits, k=length))
                if not Urun.objects.filter(urun_kodu=code).exists():
                    return code

        def clean_html(raw_text: str) -> str:
            if not raw_text:
                return ''
            raw_text = raw_text.replace('&nbsp;', ' ')
            cleaned = re.sub(r'<[^>]+>', ' ', raw_text)
            return re.sub(r'\s+', ' ', cleaned).strip()

        def normalize_bool_text(value: str) -> str:
            normalized = str(value or '').strip().lower()
            if normalized in {'yes', 'y', 'true', '1', 'evet', 'var'}:
                return 'Yes'
            if normalized in {'no', 'n', 'false', '0', 'hayir', 'hayır', 'yok'}:
                return 'No'
            return ''

        def infer_model_from_text(text: str) -> str:
            normalized = str(text or '').replace('Ⅱ', '2').replace('III', '3')
            patterns = [
                r'\b(RG40XX\s*[HV])\b',
                r'\b(RG35XX)\b',
                r'\b(RG353V)\b',
                r'\b(R36S)\b',
                r'\b(R40S\s*PRO)\b',
                r'\b(R40)\b',
                r'\b(X55)\b',
                r'\b(X9)\b',
                r'\b(X6)\b',
                r'\b(K36)\b',
                r'\b(SF3500)\b',
                r'\b(RGB20SX)\b',
                r'\b(RGB10MAX3)\b',
                r'\b(Trimui\s+Smart\s+Pro)\b',
                r'\b(Miyoo\s+Mini\s+Plus)\b',
                r'\b(Miyoo\s+Mini\s+V?2)\b',
                r'\b(Retroid\s+Pocket\s+5)\b',
                r'\b(Retroid\s+Pocket\s+Flip2)\b',
            ]
            for pattern in patterns:
                match = re.search(pattern, normalized, re.IGNORECASE)
                if match:
                    return re.sub(r'\s+', ' ', match.group(1)).strip()
            return ''

        def enrich_connectivity_fields(detaylar: dict):
            source = ' '.join([
                str(detaylar.get('baglanti') or ''),
                str(detaylar.get('wifi') or ''),
                str(detaylar.get('bluetooth') or ''),
                str(detaylar.get('usb_c') or ''),
                str(detaylar.get('hdmi') or ''),
            ]).lower()

            wifi_value = normalize_bool_text(detaylar.get('wifi'))
            if not wifi_value:
                if 'wi-fi' in source or ' wifi' in f' {source}' or 'wlan' in source:
                    wifi_value = 'Yes'
                elif 'no wifi' in source:
                    wifi_value = 'No'
            if wifi_value:
                detaylar['wifi'] = wifi_value

            bluetooth_value = normalize_bool_text(detaylar.get('bluetooth'))
            if not bluetooth_value and 'bluetooth' in source:
                bluetooth_value = 'No' if 'no bluetooth' in source else 'Yes'
            if bluetooth_value:
                detaylar['bluetooth'] = bluetooth_value

            usb_c_value = normalize_bool_text(detaylar.get('usb_c'))
            if not usb_c_value:
                if 'type-c' in source or 'usb-c' in source:
                    usb_c_value = 'Yes'
                elif 'micro usb' in source or 'mini usb' in source:
                    usb_c_value = 'No'
            if usb_c_value:
                detaylar['usb_c'] = usb_c_value

            hdmi_value = normalize_bool_text(detaylar.get('hdmi'))
            if not hdmi_value and 'hdmi' in source:
                hdmi_value = 'Yes'
            if hdmi_value:
                detaylar['hdmi'] = hdmi_value

            parts = []
            if detaylar.get('wifi') == 'Yes':
                parts.append('Wi-Fi')
            if detaylar.get('bluetooth') == 'Yes':
                parts.append('Bluetooth')
            if detaylar.get('usb_c') == 'Yes':
                parts.append('USB-C')
            if detaylar.get('hdmi') == 'Yes':
                parts.append('HDMI')
            if parts:
                detaylar['baglanti'] = ', '.join(parts)
            elif normalize_bool_text(detaylar.get('baglanti')) == 'No':
                detaylar['baglanti'] = 'No'

        def parse_description_specs(description_html: str, already_seen: set[str]) -> tuple[list[str], bool]:
            """
            Extract comparison-friendly specs from HTML description text.
            Returns (spec_lines, is_ocr_candidate).
            """
            if not description_html:
                return [], False

            # Image-heavy listings usually have many <img> tags and little real text.
            img_count = len(re.findall(r'<img\b', description_html, flags=re.IGNORECASE))
            text = clean_html(description_html)
            lower = text.lower()
            ocr_candidate = img_count >= 3 and len(text) < 180

            lines: list[str] = []

            def add_line(key: str, value: str):
                k = key.strip()
                v = value.strip(' .;,:')
                if not k or not v:
                    return
                normalized = f"{k.lower()}:{v.lower()}"
                if normalized in already_seen:
                    return
                already_seen.add(normalized)
                lines.append(f"{k}: {v}")

            patterns = [
                ("Ekran", r'(\d+(?:[\.,]\d+)?)\s*(?:inch|inches|in\b|\")\s*(?:hd|ips|lcd|oled|rgb)?'),
                ("Cozunurluk", r'(\d{3,4}\s*[xX]\s*\d{3,4})'),
                ("CPU", r'cpu\s*[:\-]\s*([^\n\r\.;]{3,120})'),
                ("RAM", r'ram\s*[:\-]\s*([^\n\r\.;]{1,80})'),
                ("Depolama", r'(?:storage|storage capacity)\s*[:\-]\s*([^\n\r\.;]{1,80})'),
                ("Batarya", r'(?:battery)\s*[:\-]\s*([^\n\r\.;]{1,120})'),
                ("Baglanti", r'(?:connectivity|other function)\s*[:\-]\s*([^\n\r\.;]{3,180})'),
                ("Isletim Sistemi", r'(?:system|os)\s*[:\-]\s*([^\n\r\.;]{2,80})'),
            ]

            for key, pattern in patterns:
                m = re.search(pattern, lower, flags=re.IGNORECASE)
                if m:
                    add_line(key, m.group(1))

            # Useful implicit signals
            if 'hdmi' in lower:
                add_line('Cikis', 'HDMI')
            if 'type-c' in lower or 'usb-c' in lower:
                add_line('Baglanti', 'Type-C')
            if 'controller' in lower:
                m = re.search(r'(\d+)\s*(?:wired\s+)?controllers?', lower)
                if m:
                    add_line('Kontrolcu', f"{m.group(1)} adet")
                else:
                    add_line('Kontrolcu', 'Dahil')
            if 'preloaded games' in lower or 'games' in lower:
                m = re.search(r'(\d{1,3}(?:[\.,]\d{3}){1,2}\+?|\d{3,5}\+?)\s*(?:preloaded\s+)?games?', lower)
                if m:
                    game_count = m.group(1).replace('.', '').replace(',', '')
                    add_line('Oyun', game_count)
            if 'what’s in the box' in lower or "what's in the box" in lower:
                add_line('Kutu Icerigi', 'Mevcut')

            return lines, ocr_candidate

        def normalize_url(url):
            """URL'deki gereksiz parametreleri temizle, küçük harfe çevir"""
            if not url:
                return ''
            parsed = urlparse(url)
            # Sadece ana yol ve temel parametreler kalsın
            clean_path = parsed.path.lower()
            return urlunparse((parsed.scheme, parsed.netloc, clean_path, '', '', ''))

        def normalize_image_url(url: str) -> str:
            if not url:
                return ''
            normalized = str(url).strip()
            if normalized.startswith('//'):
                normalized = f"https:{normalized}"
            normalized = re.sub(r'^https:///+', 'https://', normalized)
            normalized = re.sub(r'^http:///+', 'http://', normalized)
            return normalized

        def ensure_target_kategori() -> KategoriSema:
            resolved_slug = str(category_slug or 'retro-handheld').strip().lower() or 'retro-handheld'
            resolved_name = str(category_name or '').strip() or resolved_slug.replace('-', ' ').title()

            kategori = KategoriSema.objects.filter(slug=resolved_slug).first()
            if not kategori:
                return KategoriSema.objects.create(
                    slug=resolved_slug,
                    isim=resolved_name,
                    alanlar=RETRO_HANDHELD_SCHEMA,
                    aktif=True,
                )

            updated_fields = []
            if resolved_name and kategori.isim != resolved_name:
                kategori.isim = resolved_name
                updated_fields.append('isim')
            if not kategori.alanlar:
                kategori.alanlar = RETRO_HANDHELD_SCHEMA
                updated_fields.append('alanlar')
            if not kategori.aktif:
                kategori.aktif = True
                updated_fields.append('aktif')

            if updated_fields:
                kategori.save(update_fields=updated_fields)
            return kategori

        def build_detaylar_from_specs(spec_lines: list[str], is_ocr_candidate: bool) -> dict:
            detaylar: dict[str, object] = {}
            for line in spec_lines:
                if ':' not in line:
                    continue
                key_part, value_part = line.split(':', 1)
                src_key = key_part.strip().lower()
                dst_key = DETAIL_KEY_MAP.get(src_key)
                if not dst_key:
                    continue
                value = value_part.strip()
                if value:
                    detaylar[dst_key] = value
            enrich_connectivity_fields(detaylar)
            if is_ocr_candidate:
                detaylar['ocr_adayi'] = True
            return detaylar

        def apply_aspect_to_detaylar(detaylar: dict, key: str, value: str):
            if not key or not value:
                return
            normalized_key = key.strip().lower()
            mapped = ASPECT_KEY_MAP.get(normalized_key)
            if mapped and mapped not in detaylar:
                clean_value = value.strip()
                if mapped in {'wifi', 'bluetooth', 'usb_c', 'hdmi'}:
                    normalized_bool = normalize_bool_text(clean_value)
                    if mapped == 'usb_c' and not normalized_bool:
                        lower_value = clean_value.lower()
                        if 'type-c' in lower_value or 'usb-c' in lower_value:
                            normalized_bool = 'Yes'
                        elif 'micro usb' in lower_value or 'mini usb' in lower_value:
                            normalized_bool = 'No'
                    detaylar[mapped] = normalized_bool or clean_value
                else:
                    detaylar[mapped] = clean_value
            enrich_connectivity_fields(detaylar)

        # Get credentials from settings or environment
        if use_sandbox:
            client_id = getattr(settings, 'EBAY_SANDBOX_CLIENT_ID', None)
            client_secret = getattr(settings, 'EBAY_SANDBOX_CLIENT_SECRET', None)
            self.stdout.write(self.style.WARNING('Using SANDBOX environment'))
        else:
            client_id = getattr(settings, 'EBAY_PRODUCTION_CLIENT_ID', None)
            client_secret = getattr(settings, 'EBAY_PRODUCTION_CLIENT_SECRET', None)
            self.stdout.write(self.style.SUCCESS('Using PRODUCTION environment'))

        if not client_id or not client_secret:
            raise CommandError(
                f'eBay credentials not configured. '
                f'Set EBAY_{"SANDBOX" if use_sandbox else "PRODUCTION"}_CLIENT_ID '
                f'and EBAY_{"SANDBOX" if use_sandbox else "PRODUCTION"}_CLIENT_SECRET in settings.py'
            )

        # Initialize API connector
        connector = EbayAPIConnector(
            client_id=client_id,
            client_secret=client_secret,
            sandbox=use_sandbox,
            ship_to_country=ship_to_country
        )

        self.stdout.write(f'Searching for: "{search_query}" (limit: {limit})')

        # Get OAuth token
        if not connector.get_oauth_token():
            raise CommandError('Failed to get OAuth token from eBay')

        self.stdout.write(self.style.SUCCESS('✓ OAuth token obtained'))

        # Search products
        response = connector.search_items(q=search_query, limit=limit, offset=offset)
        if not response:
            raise CommandError('Failed to fetch products from eBay')

        total_results = response.get('total', 0)
        self.stdout.write(f'Found {total_results} total results')

        # Parse results
        items = connector.parse_search_results(response)
        if not items:
            self.stdout.write(self.style.WARNING('No items found in search results'))
            return

        # Offset artık API seviyesinde uygulanıyor, burada gerek yok

        # Her ürün için detayları çek ve ekle
        for item in items:
            try:
                details = None
                if item.get('item_id'):
                    details = connector.get_item_details(item['item_id'])
                if details:
                    item['details'] = details
            except Exception as e:
                logger.error(f"Error fetching details for item {item.get('item_id', 'Unknown')}: {str(e)}")
                item['details'] = {'error': str(e)}

        # Tüm ürünleri detaylarıyla JSON'a kaydet (debug amaçlı)
        self.save_items_to_json(items, filename="ebay_import_temp.json")

        self.stdout.write(f'Processing {len(items)} items...')

        # Get or create eBay store
        ebay_store, created = Magaza.objects.get_or_create(
            isim='eBay',
            defaults={'web_adresi': 'https://www.ebay.com/'}
        )
        if created:
            self.stdout.write(self.style.SUCCESS('✓ Created eBay store'))

        # Import products
        target_kategori = ensure_target_kategori()
        imported_count = 0
        skipped_count = 0

        for item in items:
            try:
                details = item.get('details')
                title = item.get('title') or 'eBay Ürünü'
                title_tr = tr_text(title)
                category = item.get('category') or 'Belirtilmedi'
                category_tr = tr_text(category)
                condition = item.get('condition') or 'Unknown'
                condition_tr = tr_text(condition)
                shipping_cost = float(item.get('shipping_cost', 0) or 0)
                shipping_is_free = bool(item.get('shipping_is_free'))

                subtitle = ''
                if details:
                    subtitle = clean_html(details.get('shortDescription') or details.get('subtitle') or '')
                subtitle = subtitle or f"Durum: {condition_tr}"
                subtitle_tr = tr_text(subtitle)

                description_html = ''
                if details:
                    description_html = details.get('description') or ''
                description_text = clean_html(description_html)

                ozellikler_lines = []
                seen_specs = set()
                detaylar: dict[str, object] = {}
                if details and details.get('localizedAspects'):
                    for aspect in details.get('localizedAspects', []):
                        key = tr_text(aspect.get('name') or '')
                        raw_key = (aspect.get('name') or '').strip()
                        values = aspect.get('value') or []
                        if isinstance(values, list):
                            value_text = ', '.join([tr_text(v) for v in values if v])
                            raw_value_text = ', '.join([str(v) for v in values if v])
                        else:
                            value_text = tr_text(str(values))
                            raw_value_text = str(values)
                        if key and value_text:
                            line = f"{key}: {value_text}"
                            sig = f"{key.lower()}:{value_text.lower()}"
                            if sig not in seen_specs:
                                seen_specs.add(sig)
                                ozellikler_lines.append(line)
                            apply_aspect_to_detaylar(detaylar, raw_key, raw_value_text)

                extracted_specs, is_ocr_candidate = parse_description_specs(description_html, seen_specs)
                detaylar.update(build_detaylar_from_specs(extracted_specs, is_ocr_candidate))
                if item.get('shipping_origin') and not detaylar.get('gonderim_yeri'):
                    detaylar['gonderim_yeri'] = item.get('shipping_origin')
                if not detaylar.get('model'):
                    inferred_model = infer_model_from_text(title)
                    if inferred_model:
                        detaylar['model'] = inferred_model
                enrich_connectivity_fields(detaylar)
                if extracted_specs:
                    ozellikler_lines.append('--- Description Cikarimlari ---')
                    ozellikler_lines.extend([tr_text(x) for x in extracted_specs])
                if is_ocr_candidate:
                    ozellikler_lines.append('Not: OCR adayi (aciklama metni dusuk, gorsel agirlikli)')

                ozellikler_lines.append(f"Kategori: {target_kategori.isim}")
                ozellikler_lines.append(f"Gönderim Yeri: {item.get('shipping_origin', 'Belirtilmedi')}")
                if shipping_is_free:
                    shipping_label = 'Ücretsiz'
                    shipping_tag = tr_text('ücretsiz kargo')
                elif shipping_cost > 0:
                    shipping_label = f"{shipping_cost} {item.get('currency', 'USD')}"
                    shipping_tag = tr_text('ücretli kargo')
                elif item.get('shipping_available'):
                    shipping_label = 'Konuma göre hesaplanır'
                    shipping_tag = tr_text('kargo hesaplanıyor')
                else:
                    shipping_label = 'Bilgi yok'
                    shipping_tag = tr_text('kargo bilgisi yok')

                ozellikler_lines.append(f"Kargo: {shipping_label}")

                etiket_set = [
                    category_tr,
                    condition_tr,
                    item.get('shipping_origin', 'Belirtilmedi'),
                    shipping_tag,
                ]
                title_words = [w for w in re.split(r'\W+', title_tr.lower()) if len(w) > 2]
                etiket_set.extend(title_words[:6])
                etiketler = ', '.join(dict.fromkeys([x for x in etiket_set if x]))[:500]

                aciklama = description_text[:5000] if description_text else f"Kategori: {category_tr}"

                # Gelişmiş güncelleme: source_url ve item_id ile kontrol
                norm_aff_url = normalize_url(item.get('affiliate_url') or '')
                norm_web_url = normalize_url(item.get('item_web_url') or '')
                primary_image_url = normalize_image_url(item.get('image_url') or '')
                product = None
                created = False
                # Önce source_url (affiliate_url) ile dene
                if norm_aff_url:
                    product = Urun.objects.filter(source_url=norm_aff_url).first()
                # Sonra source_url (item_web_url) ile dene
                if not product and norm_web_url:
                    product = Urun.objects.filter(source_url=norm_web_url).first()
                # Son olarak item_id ile dene (modelde item_id alanı varsa, yoksa eklenmeli)
                if not product and item.get('item_id') and hasattr(Urun, 'item_id'):
                    product = Urun.objects.filter(item_id=item['item_id']).first()

                if not product:
                    # Yeni ürün oluştur
                    product = Urun.objects.create(
                        source_url=norm_aff_url or norm_web_url,
                        isim=title_tr[:200],
                        aciklama=aciklama,
                        ana_baslik=title_tr,
                        alt_baslik=subtitle_tr,
                        etiketler=etiketler,
                        ozellikler='\n'.join(ozellikler_lines)[:5000],
                        kategori=target_kategori,
                        detaylar=detaylar,
                        durum=condition_tr,
                        resim_url=primary_image_url,
                        urun_kodu=generate_unique_code(),
                        item_id=item.get('item_id') if hasattr(Urun, 'item_id') else None
                    )
                    created = True
                    self.stdout.write(f'✓ Created product: {title_tr[:50]}...')
                else:
                    self.stdout.write(f'~ Found existing: {title_tr[:50]}...')
                    # Tüm alanları güncelle
                    product.isim = title_tr[:200]
                    product.aciklama = aciklama
                    product.ana_baslik = title_tr
                    product.alt_baslik = subtitle_tr
                    product.etiketler = etiketler
                    product.ozellikler = '\n'.join(ozellikler_lines)[:5000]
                    product.kategori = target_kategori
                    product.detaylar = detaylar
                    product.durum = condition_tr
                    if primary_image_url:
                        product.resim_url = primary_image_url
                    if hasattr(product, 'item_id') and item.get('item_id'):
                        product.item_id = item['item_id']
                    product.save()

                # Add/update price entry
                base_item_url = item['item_web_url'] or item['affiliate_url']
                affiliate_url = build_epn_rover_url(base_item_url, campaign_id, product.urun_kodu)

                price, price_created = Fiyat.objects.get_or_create(
                    urun=product,
                    magaza=ebay_store,
                    defaults={
                        'fiyat': Decimal(str(item['price'])),
                        'para_birimi': item['currency'],
                        'affiliate_link': affiliate_url,
                        'gonderim_ucreti': Decimal(str(item['shipping_cost'])),
                        'gonderim_yerinden': item['shipping_origin'],
                        'gonderim_durumu': item['shipping_available'],
                        'ucretsiz_kargo': item.get('shipping_is_free', False),
                    }
                )

                if not price_created:
                    # Update existing price
                    price.fiyat = Decimal(str(item['price']))
                    price.affiliate_link = affiliate_url
                    price.gonderim_ucreti = Decimal(str(item['shipping_cost']))
                    price.gonderim_yerinden = item['shipping_origin']
                    price.gonderim_durumu = item['shipping_available']
                    price.ucretsiz_kargo = item.get('shipping_is_free', False)
                    price.save()

                # Tüm resimleri ekle (ana ve ek resimler)
                image_urls = []
                if item.get('image_url'):
                    image_urls.append(normalize_image_url(item['image_url']))
                if item.get('additional_images'):
                    image_urls.extend([normalize_image_url(url) for url in item['additional_images'] if url])
                for idx, img_url in enumerate(image_urls):
                    if not img_url:
                        continue
                    UrunResim.objects.get_or_create(
                        urun=product,
                        resim_url=img_url,
                        defaults={'sira': idx}
                    )

                imported_count += 1

            except Exception as e:
                logger.error(f"Error importing product {item.get('title', 'Unknown')}: {str(e)}")
                skipped_count += 1
                self.stdout.write(
                    self.style.ERROR(f'✗ Error: {str(e)[:100]}')
                )

        # Summary
        self.stdout.write(self.style.SUCCESS(f'\n=== IMPORT SUMMARY ==='))
        self.stdout.write(self.style.SUCCESS(f'✓ Successfully imported: {imported_count}'))
        self.stdout.write(self.style.WARNING(f'~ Skipped: {skipped_count}'))
        self.stdout.write(self.style.SUCCESS(f'Total: {imported_count + skipped_count}'))

    def save_items_to_json(self, items, filename="ebay_import_temp.json"):
        """Tüm çekilen ürünleri detaylarıyla JSON dosyasına kaydet (debug/test için)"""
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        self.stdout.write(self.style.SUCCESS(f"{len(items)} ürün {filename} dosyasına kaydedildi."))
