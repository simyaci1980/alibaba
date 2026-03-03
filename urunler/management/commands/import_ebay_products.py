"""
Django Management Command: import_ebay_products
Fetches products from eBay Browse API and saves to database
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from urunler.ebay_api import EbayAPIConnector
from urunler.models import Urun, Magaza, Fiyat, UrunResim
from decimal import Decimal
import logging
import re
import importlib
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


def build_epn_rover_url(item_url: str, campaign_id: str, custom_id: int | None = None) -> str:
    if not item_url:
        return ''

    if 'rover.ebay.com' in item_url:
        return item_url

    if not campaign_id:
        return item_url

    params = {
        'campid': str(campaign_id),
        'toolid': '10001',
        'mpre': item_url,
    }
    if custom_id is not None:
        params['customid'] = str(custom_id)

    return f"https://rover.ebay.com/rover/1/711-53200-19255-0/1?{urlencode(params)}"


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

    def handle(self, *args, **options):
        search_query = options['search_query']
        limit = min(options['limit'], 200)  # Max 200
        use_sandbox = options['sandbox']
        campaign_id = options['campaign_id']
        translate_tr = options['translate_tr']

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

        def clean_html(raw_text: str) -> str:
            if not raw_text:
                return ''
            cleaned = re.sub(r'<[^>]+>', ' ', raw_text)
            return re.sub(r'\s+', ' ', cleaned).strip()

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
            sandbox=use_sandbox
        )

        self.stdout.write(f'Searching for: "{search_query}" (limit: {limit})')

        # Get OAuth token
        if not connector.get_oauth_token():
            raise CommandError('Failed to get OAuth token from eBay')

        self.stdout.write(self.style.SUCCESS('✓ OAuth token obtained'))

        # Search products
        response = connector.search_items(q=search_query, limit=limit)
        if not response:
            raise CommandError('Failed to fetch products from eBay')

        total_results = response.get('total', 0)
        self.stdout.write(f'Found {total_results} total results')

        # Parse results
        items = connector.parse_search_results(response)
        if not items:
            self.stdout.write(self.style.WARNING('No items found in search results'))
            return

        self.stdout.write(f'Processing {len(items)} items...')

        # Get or create eBay store
        ebay_store, created = Magaza.objects.get_or_create(
            isim='eBay',
            defaults={'web_adresi': 'https://www.ebay.com/'}
        )
        if created:
            self.stdout.write(self.style.SUCCESS('✓ Created eBay store'))

        # Import products
        imported_count = 0
        skipped_count = 0

        for item in items:
            try:
                details = None
                if item.get('item_id'):
                    details = connector.get_item_details(item['item_id'])

                title = item.get('title') or 'eBay Ürünü'
                title_tr = tr_text(title)
                category = item.get('category') or 'Belirtilmedi'
                category_tr = tr_text(category)
                condition = item.get('condition') or 'Unknown'
                condition_tr = tr_text(condition)

                subtitle = ''
                if details:
                    subtitle = clean_html(details.get('shortDescription') or details.get('subtitle') or '')
                subtitle = subtitle or f"Durum: {condition_tr}"
                subtitle_tr = tr_text(subtitle)

                ozellikler_lines = []
                if details and details.get('localizedAspects'):
                    for aspect in details.get('localizedAspects', []):
                        key = tr_text(aspect.get('name') or '')
                        values = aspect.get('value') or []
                        if isinstance(values, list):
                            value_text = ', '.join([tr_text(v) for v in values if v])
                        else:
                            value_text = tr_text(str(values))
                        if key and value_text:
                            ozellikler_lines.append(f"{key}: {value_text}")

                ozellikler_lines.append(f"Kategori: {category_tr}")
                ozellikler_lines.append(f"Gönderim Yeri: {item.get('shipping_origin', 'Belirtilmedi')}")
                ozellikler_lines.append(
                    f"Kargo: {'Ücretsiz' if float(item.get('shipping_cost', 0) or 0) == 0 else str(item.get('shipping_cost')) + ' ' + item.get('currency', 'USD')}"
                )

                etiket_set = [
                    category_tr,
                    condition_tr,
                    item.get('shipping_origin', 'Belirtilmedi'),
                    tr_text('ücretsiz kargo') if float(item.get('shipping_cost', 0) or 0) == 0 else tr_text('ücretli kargo')
                ]
                title_words = [w for w in re.split(r'\W+', title_tr.lower()) if len(w) > 2]
                etiket_set.extend(title_words[:6])
                etiketler = ', '.join(dict.fromkeys([x for x in etiket_set if x]))[:500]

                aciklama = f"Kategori: {category_tr}"

                # Check if product already exists (by source URL)
                source_url = item['affiliate_url'] or item['item_web_url']
                
                product, created = Urun.objects.get_or_create(
                    source_url=source_url,
                    defaults={
                        'isim': title_tr[:200],
                        'aciklama': aciklama,
                        'ana_baslik': title_tr[:200],
                        'alt_baslik': subtitle_tr[:200],
                        'etiketler': etiketler,
                        'ozellikler': '\n'.join(ozellikler_lines)[:5000],
                        'resim_url': item['image_url'],
                    }
                )

                if created:
                    self.stdout.write(f'✓ Created product: {title_tr[:50]}...')
                else:
                    self.stdout.write(f'~ Found existing: {title_tr[:50]}...')
                    # Keep card fields fresh for existing products too
                    product.isim = title_tr[:200]
                    product.aciklama = aciklama
                    product.ana_baslik = title_tr[:200]
                    product.alt_baslik = subtitle_tr[:200]
                    product.etiketler = etiketler
                    product.ozellikler = '\n'.join(ozellikler_lines)[:5000]
                    if item['image_url']:
                        product.resim_url = item['image_url']
                    product.save()

                # Add/update price entry
                base_item_url = item['item_web_url'] or item['affiliate_url']
                affiliate_url = build_epn_rover_url(base_item_url, campaign_id, product.id)

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
                    }
                )

                if not price_created:
                    # Update existing price
                    price.fiyat = Decimal(str(item['price']))
                    price.affiliate_link = affiliate_url
                    price.gonderim_ucreti = Decimal(str(item['shipping_cost']))
                    price.gonderim_yerinden = item['shipping_origin']
                    price.gonderim_durumu = item['shipping_available']
                    price.save()

                # Add product image if URL available
                if item['image_url'] and not product.resimler.exists():
                    UrunResim.objects.get_or_create(
                        urun=product,
                        resim_url=item['image_url'],
                        defaults={'sira': 0}
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
