"""
Django Management Command: import_aliexpress_products
Fetches products from AliExpress Portals API and saves to database
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from urunler.aliexpress_api import AliExpressAPIConnector
from urunler.models import Urun, Magaza, Fiyat, UrunResim
from decimal import Decimal
import logging
import json
import re
import random
import string
import importlib
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import products from AliExpress Portals API'

    def add_arguments(self, parser):
        parser.add_argument(
            'search_query',
            type=str,
            help='Search keywords (e.g., "laptop" or "wireless headphones")'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=25,
            help='Number of products to fetch from API (default: 25, max: 50). Higher values recommended as TR check filters results.'
        )
        parser.add_argument(
            '--tracking-id',
            type=str,
            default=getattr(settings, 'ALIEXPRESS_TRACKING_ID', 'kolaybulexpres'),
            help='Your tracking/sub ID for affiliate links'
        )
        parser.add_argument(
            '--min-price',
            type=float,
            default=None,
            help='Minimum price filter (USD)'
        )
        parser.add_argument(
            '--max-price',
            type=float,
            default=None,
            help='Maximum price filter (USD)'
        )
        parser.add_argument(
            '--translate-tr',
            action='store_true',
            help='Translate title/category/details to Turkish when possible'
        )
        parser.add_argument(
            '--ship-to-turkey',
            action='store_true',
            help='Only show products that ship to Turkey'
        )
        parser.add_argument(
            '--ship-to-country',
            type=str,
            default=None,
            help='Ship-to country code filter (e.g., TR, BR, DE) - DEPRECATED: unreliable API filter, use Playwright verification instead'
        )
        parser.add_argument(
            '--ship-from-turkey',
            action='store_true',
            help='Only products shipped FROM Turkey warehouse (Türkiye Deposu)'
        )
        parser.add_argument(
            '--only-buyable-tr',
            action='store_true',
            default=True,
            help='DEFAULT: Verify with browser and import only products buyable from Turkey (TR). Use --skip-tr-check to disable.'
        )
        parser.add_argument(
            '--skip-tr-check',
            action='store_true',
            help='Skip browser TR buyability verification (faster but may import unavailable products)'
        )
        parser.add_argument(
            '--headful',
            action='store_true',
            help='Show browser window during verification (for debugging)'
        )
        parser.add_argument(
            '--tr-check-retries',
            type=int,
            default=4,
            help='Retry count per product when CAPTCHA/network page appears during TR verification (default: 4)'
        )
        parser.add_argument(
            '--preview-only',
            action='store_true',
            help='Do not import into DB. Only list candidate links for manual TR testing.'
        )
        parser.add_argument(
            '--snapshot-out',
            type=str,
            default=None,
            help='Write candidate product list to JSON file for later import (e.g. snapshots/candidates.json)'
        )
        parser.add_argument(
            '--from-snapshot',
            type=str,
            default=None,
            help='Load candidate products from a JSON snapshot file instead of calling API search'
        )
        parser.add_argument(
            '--shop-id',
            type=str,
            default=None,
            help='Only import products from this AliExpress shop ID (e.g. 1105265650)'
        )
        parser.add_argument(
            '--max-pages',
            type=int,
            default=8,
            help='How many API pages to scan when searching products (default: 8)'
        )

    def generate_unique_code(self, length=5):
        """Generate unique 5-digit product code"""
        while True:
            code = ''.join(random.choices(string.digits, k=length))
            if not Urun.objects.filter(urun_kodu=code).exists():
                return code

    def clean_html(self, raw_text: str) -> str:
        """Remove HTML tags from text"""
        if not raw_text:
            return ''
        cleaned = re.sub(r'<[^>]+>', ' ', raw_text)
        return re.sub(r'\s+', ' ', cleaned).strip()

    def extract_product_id(self, product_data: dict) -> str:
        """Extract stable AliExpress product id from payload/urls"""
        raw_product_id = str(product_data.get('product_id') or '').strip()
        if raw_product_id.isdigit():
            return raw_product_id

        candidate_urls = [
            product_data.get('product_url'),
            product_data.get('product_detail_url'),
        ]

        for candidate_url in candidate_urls:
            if not candidate_url:
                continue
            match = re.search(r'/item/(\d+)\.html', candidate_url)
            if match:
                return match.group(1)

        return ''

    def canonicalize_source_url(self, product_data: dict) -> str:
        """Create canonical source_url to avoid duplicates across URL variants"""
        product_id = self.extract_product_id(product_data)
        if product_id:
            return f'https://www.aliexpress.com/item/{product_id}.html'

        source_url = product_data.get('product_url') or product_data.get('product_detail_url')
        if not source_url:
            return ''

        parts = urlsplit(source_url.strip())
        scheme = parts.scheme or 'https'
        netloc = (parts.netloc or 'www.aliexpress.com').lower()
        path = parts.path or ''

        if 'aliexpress.com' in netloc:
            netloc = 'www.aliexpress.com'

        return urlunsplit((scheme, netloc, path.rstrip('/'), '', ''))

    def handle(self, *args, **options):
        search_query = options['search_query']
        limit = min(options['limit'], 50)  # Max 50 per request
        tracking_id = options['tracking_id']
        min_price = options['min_price']
        max_price = options['max_price']
        translate_tr = options['translate_tr']
        ship_to_turkey = options['ship_to_turkey']
        ship_to_country = options['ship_to_country']
        ship_from_turkey = options['ship_from_turkey']
        skip_tr_check = options['skip_tr_check']
        headful = options.get('headful', False)
        tr_check_retries = max(1, int(options.get('tr_check_retries', 4)))
        only_buyable_tr = options['only_buyable_tr'] and not skip_tr_check
        preview_only = options.get('preview_only', False)
        snapshot_out = options.get('snapshot_out')
        from_snapshot = options.get('from_snapshot')
        shop_id_filter = (options.get('shop_id') or '').strip()
        max_pages = max(1, int(options.get('max_pages', 8)))

        if ship_to_country:
            ship_to_country = ship_to_country.strip().upper()
        elif ship_to_turkey:
            ship_to_country = 'TR'

        def build_ship_to_url(url: str, country: str) -> str:
            parts = urlsplit(url)
            query = dict(parse_qsl(parts.query, keep_blank_values=True))
            query['shipToCountry'] = country
            return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

        def is_buyable_for_country(source_url: str, page, country: str = 'TR') -> tuple[bool, str]:
            """Check if product is buyable from given country.
            Strategy (hybrid):
            1) If known blocked phrase exists -> not buyable
            2) If buy/cart signal exists -> buyable
            3) If no blocked phrase exists -> likely buyable (dynamic UI tolerance)
            """
            if not source_url or not page:
                return (False, 'playwright_not_ready')

            buy_selectors = [
                "button:has-text('Buy now')",
                "button:has-text('Buy Now')",
                "button:has-text('Satın Al')",
                "button:has-text('Şimdi satın al')",
                "button:has-text('Şimdi Satın Al')",
                "button:has-text('satın al')",
                "button:has-text('Comprar agora')",
                "button:has-text('Comprar')",
                "[role='button']:has-text('Buy now')",
                "[role='button']:has-text('Satın Al')",
                "[role='button']:has-text('Şimdi satın al')",
                "[role='button']:has-text('satın al')",
                # Try more generic - any button with action-like text
                "button[class*='add']",
                "button[class*='buy']",
                "button[class*='cart']",
            ]

            cart_selectors = [
                "button:has-text('Add to cart')",
                "button:has-text('Sepete Ekle')",
                "button:has-text('Sepete ekle')",
                "button:has-text('sepete ekle')",
                "button:has-text('Adicionar ao carrinho')",
                "[role='button']:has-text('Add to cart')",
                "[role='button']:has-text('Sepete Ekle')",
                "[role='button']:has-text('Sepete ekle')",
                "[role='button']:has-text('sepete ekle')",
                "button[class*='add-to-cart']",
                "button[class*='addCart']",
            ]

            blocked_phrases = [
                'üzgünüz, bu ürün şu anda bulunduğunuz bölgede mevcut değil',
                'üzgünüz, bu ürün şu anda konumunuzda kullanılamıyor',
                'bu ürün henüz konumunuzda mevcut değil',
                'bu ürün geçici olarak tedarik edilemiyor',
                "can't be shipped",
                'cannot be shipped',
                'not available in your location',
                'temporarily unavailable',
                'item is unavailable',
                'no longer available',
            ]

            try:
                # Navigate to product page
                last_error = ''
                loaded = False
                test_url = build_ship_to_url(source_url, country)
                for nav_timeout in (25000, 40000):
                    try:
                        page.goto(test_url, wait_until='networkidle', timeout=nav_timeout)
                        # Shorter wait - let's see if 1500ms is enough
                        page.wait_for_timeout(1500)
                        loaded = True
                        break
                    except Exception as nav_exc:
                        last_error = str(nav_exc)
                        continue

                if not loaded:
                    return (False, f'load_error:{last_error[:50]}')

                # Recover from AliExpress interstitial: "Network error, click to reload"
                try:
                    for _ in range(3):
                        html = page.content().lower()
                        if 'network error, click to reload' not in html:
                            break
                        try:
                            page.get_by_text('click to reload', exact=False).first.click(timeout=1500)
                        except Exception:
                            page.reload(wait_until='domcontentloaded', timeout=25000)
                        page.wait_for_timeout(2500)

                    if 'network error, click to reload' in page.content().lower():
                        return (False, 'network_error_page')
                except Exception:
                    pass

                # CAPTCHA/interstitial detection for BOTH headless and headful runs
                try:
                    challenge_html = page.content().lower()
                    if (
                        'captcha' in challenge_html
                        or 'i am not a robot' in challenge_html
                        or 'ben robot değilim' in challenge_html
                        or 'verify' in challenge_html
                        or 'security check' in challenge_html
                    ):
                        return (False, 'captcha_page_detected')
                except Exception:
                    pass

                if headful:
                    try:
                        challenge_text = page.content().lower()
                        if (
                            'robot' in challenge_text
                            or 'verify' in challenge_text
                            or 'captcha' in challenge_text
                            or 'i am not a robot' in challenge_text
                        ):
                            self.stdout.write(self.style.WARNING('  ~ CAPTCHA detected. Solve it in browser, waiting up to 90s...'))
                            for _ in range(30):
                                page.wait_for_timeout(3000)
                                try:
                                    current_html = page.content().lower()
                                except Exception:
                                    current_html = ''
                                if not (
                                    'robot' in current_html
                                    or 'verify' in current_html
                                    or 'captcha' in current_html
                                    or 'i am not a robot' in current_html
                                ):
                                    break
                            else:
                                return (False, 'captcha_not_solved')
                    except Exception:
                        pass

                # Step-1: hard blocked phrase check (most decisive)
                page_html = ''
                try:
                    page_html = page.content().lower()
                except Exception:
                    page_html = ''

                for phrase in blocked_phrases:
                    if phrase in page_html:
                        return (False, f'blocked_in_html:{phrase[:36]}')

                # Check for buy button (MOST RELIABLE method) - extended timeout
                buy_visible = False
                for selector in buy_selectors:
                    try:
                        element = page.locator(selector).first
                        if element.is_visible(timeout=2000):
                            buy_visible = True
                            break
                    except Exception:
                        continue

                if buy_visible:
                    return (True, 'buy_button_visible')

                # Generic text checks (button may not use <button> tag)
                generic_buy_texts = [
                    'Buy now', 'Satın Al', 'satın al', 'Şimdi satın al', 'Şimdi Satın Al'
                ]
                for buy_text in generic_buy_texts:
                    try:
                        if page.get_by_text(buy_text, exact=False).first.is_visible(timeout=1200):
                            return (True, f'buy_text_visible:{buy_text}')
                    except Exception:
                        continue

                # Check for cart button
                cart_visible = False
                for selector in cart_selectors:
                    try:
                        element = page.locator(selector).first
                        if element.is_visible(timeout=2000):
                            cart_visible = True
                            break
                    except Exception:
                        continue

                if cart_visible:
                    return (True, 'cart_button_visible')

                generic_cart_texts = ['Add to cart', 'Sepete Ekle', 'Sepete ekle', 'sepete ekle']
                for cart_text in generic_cart_texts:
                    try:
                        if page.get_by_text(cart_text, exact=False).first.is_visible(timeout=1200):
                            return (True, f'cart_text_visible:{cart_text}')
                    except Exception:
                        continue

                # Debug: capture visible button labels for diagnosis
                try:
                    button_texts = page.eval_on_selector_all(
                        'button, [role="button"]',
                        'els => els.map(e => (e.innerText || "").trim()).filter(Boolean).slice(0, 12)'
                    )
                    if button_texts:
                        self.stdout.write(self.style.WARNING(f"  ~ Debug visible buttons: {button_texts}"))
                except Exception:
                    pass

                # Step-3: if no blocked phrase detected, keep product (UI may be dynamic)
                if page_html:
                    return (True, 'no_block_phrase_detected')

                return (False, 'no_purchase_button_visible')
            except Exception as exc:
                return (False, f'check_error:{str(exc)[:50]}')

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

        # Get credentials from settings
        app_key = getattr(settings, 'ALIEXPRESS_APP_KEY', None)
        app_secret = getattr(settings, 'ALIEXPRESS_APP_SECRET', None)

        if not app_key or not app_secret:
            raise CommandError(
                'AliExpress credentials not configured. '
                'Set ALIEXPRESS_APP_KEY and ALIEXPRESS_APP_SECRET in settings.py'
            )

        self.stdout.write(self.style.SUCCESS('✓ Using AliExpress Portals API'))

        # Initialize API connector
        connector = AliExpressAPIConnector(
            app_key=app_key,
            app_secret=app_secret
        )

        self.stdout.write(f'Searching for: "{search_query}" (limit: {limit})')
        if shop_id_filter:
            self.stdout.write(self.style.SUCCESS(f'✓ Shop filter: {shop_id_filter} (max_pages={max_pages})'))
        if tracking_id:
            self.stdout.write(f'Using tracking_id: {tracking_id}')
        if ship_to_country:
            self.stdout.write(self.style.SUCCESS(f'✓ Filtering: ship to {ship_to_country}'))
        if only_buyable_tr:
            self.stdout.write(self.style.SUCCESS('✓ TR buyability check: ENABLED (browser verification)'))
        else:
            self.stdout.write(self.style.WARNING('⚠ TR buyability check: DISABLED (may import unavailable products)'))

        products = []
        if from_snapshot:
            try:
                with open(from_snapshot, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                if not isinstance(loaded, list):
                    raise ValueError('Snapshot must contain a JSON array of products')
                products = loaded
                if shop_id_filter:
                    products = [p for p in products if str(p.get('shop_id') or '') == shop_id_filter]
                self.stdout.write(self.style.SUCCESS(f'✓ Loaded {len(products)} product(s) from snapshot: {from_snapshot}'))
            except Exception as exc:
                raise CommandError(f'Failed to read snapshot file: {exc}') from exc
        else:
            # Search products across multiple pages
            base_params = {
                'keywords': search_query,
                'page_size': limit,
            }

            if min_price is not None:
                base_params['min_price'] = min_price
            if max_price is not None:
                base_params['max_price'] = max_price
            if tracking_id:
                base_params['tracking_id'] = tracking_id
            if ship_to_country:
                self.stdout.write(self.style.WARNING(
                    f'⚠ WARNING: AliExpress API may not reliably support ship_to_country={ship_to_country}.\n'
                    '  Results may include products that do not ship to selected country.\n'
                    '  Please verify shipping on product page before purchase.'
                ))
                base_params['ship_to_country'] = ship_to_country

            if ship_from_turkey:
                self.stdout.write(self.style.ERROR(
                    '❌ ERROR: AliExpress API does not support ship_from_country filter.\n'
                    '   This parameter is not available in the current API version.\n'
                    '   Please manually verify shipping country on AliExpress product pages.\n'
                    '   Proceeding with regular search...'
                ))

            products = []
            for page_no in range(1, max_pages + 1):
                page_params = dict(base_params)
                page_params['page_no'] = page_no

                response = connector.search_products(**page_params)
                if not response:
                    if page_no == 1:
                        raise CommandError('Failed to fetch products from AliExpress')
                    self.stdout.write(self.style.WARNING(f'~ API response empty on page {page_no}, stopping scan'))
                    break

                page_products = connector.parse_search_results(response)

                if not page_products and tracking_id:
                    self.stdout.write(self.style.WARNING(f'~ No products with tracking_id on page {page_no}, retrying without tracking_id...'))
                    retry_params = dict(page_params)
                    retry_params.pop('tracking_id', None)
                    retry_response = connector.search_products(**retry_params)
                    if retry_response:
                        page_products = connector.parse_search_results(retry_response)

                if shop_id_filter:
                    page_products = [p for p in page_products if str(p.get('shop_id') or '') == shop_id_filter]

                if not page_products and page_no > 1 and not shop_id_filter:
                    break

                products.extend(page_products)

                if len(products) >= limit:
                    products = products[:limit]
                    break

            if shop_id_filter and len(products) > limit:
                products = products[:limit]

        if not products:
            self.stdout.write(self.style.WARNING('⚠ No products found in search results'))
            return

        if snapshot_out:
            try:
                snapshot_path = Path(snapshot_out)
                if snapshot_path.parent and str(snapshot_path.parent) not in ('', '.'):
                    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                with open(snapshot_path, 'w', encoding='utf-8') as f:
                    json.dump(products, f, ensure_ascii=False, indent=2)
                self.stdout.write(self.style.SUCCESS(f'✓ Snapshot saved: {snapshot_path} ({len(products)} ürün)'))
            except Exception as exc:
                raise CommandError(f'Failed to write snapshot file: {exc}') from exc

        precheck_skipped = 0
        if only_buyable_tr:
            try:
                from playwright.sync_api import sync_playwright
            except Exception as exc:
                raise CommandError(
                    'Playwright not installed. Run: pip install playwright && python -m playwright install chromium'
                ) from exc

            self.stdout.write('Pre-checking TR buyability before import...')
            filtered_products = []

            with sync_playwright() as p:
                launch_kwargs = {
                    'headless': not headful,
                    'args': [
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                    ]
                }
                browser = p.chromium.launch(**launch_kwargs)

                if headful:
                    context = browser.new_context(locale='tr-TR', timezone_id='Europe/Istanbul')
                else:
                    context = browser.new_context(
                        locale='tr-TR',
                        extra_http_headers={'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8'},
                        timezone_id='Europe/Istanbul',
                    )
                page = context.new_page()
                page.set_default_timeout(30000)

                # Warm-up navigation to establish cookies/session before product checks
                try:
                    page.goto('https://www.aliexpress.com/', wait_until='domcontentloaded', timeout=30000)
                    page.wait_for_timeout(2500)
                except Exception:
                    pass

                if not headful:
                    page.route(
                        '**/*',
                        lambda route, request: route.abort()
                        if request.resource_type in {'image', 'media', 'font'}
                        else route.continue_()
                    )

                for product_data in products:
                    title = product_data.get('title') or 'AliExpress Ürünü'
                    source_url = self.canonicalize_source_url(product_data)
                    if not source_url:
                        self.stdout.write(self.style.WARNING(f'  ~ Skipped (invalid source_url): {title[:50]}...'))
                        precheck_skipped += 1
                        continue

                    is_buyable = False
                    reason = 'unknown'
                    for attempt in range(1, tr_check_retries + 1):
                        is_buyable, reason = is_buyable_for_country(source_url, page, 'TR')
                        if is_buyable:
                            break

                        if reason in {'captcha_not_solved', 'captcha_page_detected', 'network_error_page', 'load_error'}:
                            self.stdout.write(self.style.WARNING(
                                f"  ~ Retry {attempt}/{tr_check_retries} ({reason}) for: {title[:45]}..."
                            ))
                            try:
                                page.goto('https://www.aliexpress.com/', wait_until='domcontentloaded', timeout=30000)
                                page.wait_for_timeout(2500)
                            except Exception:
                                pass
                            continue

                        break

                    if is_buyable:
                        filtered_products.append(product_data)
                    else:
                        self.stdout.write(self.style.WARNING(f'  ~ Skipped (TR not buyable: {reason}): {title[:50]}...'))
                        precheck_skipped += 1

                    if headful:
                        try:
                            page.wait_for_timeout(1000)
                        except Exception:
                            break

                context.close()
                browser.close()

            products = filtered_products
            self.stdout.write(self.style.SUCCESS(f'✓ TR buyability pre-check kept {len(products)} product(s)'))

            if not products:
                self.stdout.write(self.style.WARNING('\n=== IMPORT SUMMARY ==='))
                self.stdout.write(self.style.SUCCESS('✓ Successfully imported: 0'))
                self.stdout.write(self.style.WARNING(f'~ Skipped: {precheck_skipped}'))
                self.stdout.write(self.style.SUCCESS(f'Total processed: {precheck_skipped}'))
                return

        if preview_only:
            self.stdout.write(self.style.SUCCESS(f'\n=== PREVIEW ({len(products)} ürün) ==='))
            for idx, product_data in enumerate(products, start=1):
                source_url = self.canonicalize_source_url(product_data)
                if ship_to_country and source_url:
                    source_url = build_ship_to_url(source_url, ship_to_country)
                self.stdout.write(
                    f"{idx}. product_id={self.extract_product_id(product_data)} | "
                    f"{(product_data.get('title') or 'AliExpress Ürünü')[:70]}"
                )
                self.stdout.write(f"   url: {source_url}")

            self.stdout.write(self.style.SUCCESS('\n✓ Preview tamam. Ürünler DB\'ye eklenmedi.'))
            self.stdout.write('Manuel kontrol sonrası import için:')
            self.stdout.write('  1) Snapshot aldıysanız dosyada istemediklerinizi silin')
            self.stdout.write(f'  2) python manage.py import_aliexpress_products "{search_query}" --from-snapshot="{snapshot_out or "<snapshot.json>"}" --skip-tr-check')
            return

        self.stdout.write(f'✓ Found {len(products)} products')
        self.stdout.write('Processing...')

        # Get or create AliExpress API store (CSV kanalından ayır)
        aliexpress_store, created = Magaza.objects.get_or_create(
            isim='AliExpress (API)',
            defaults={'web_adresi': 'https://www.aliexpress.com/'}
        )
        if created:
            self.stdout.write(self.style.SUCCESS('✓ Created AliExpress (API) store'))

        # Import products
        imported_count = 0
        skipped_count = precheck_skipped
        
        # Extract search keywords for relevance check (minimum 3 chars)
        search_keywords = set(word.lower() for word in re.split(r'\W+', search_query) if len(word) >= 3)

        for product_data in products:
            try:
                    title = product_data.get('title') or 'AliExpress Ürünü'

                    # Relevance check: Product title must contain at least ONE search keyword
                    title_words = set(word.lower() for word in re.split(r'\W+', title) if len(word) >= 3)
                    common_words = search_keywords.intersection(title_words)

                    # If no keywords match, skip this product
                    if not common_words and len(search_keywords) > 0 and not shop_id_filter:
                        self.stdout.write(self.style.WARNING(f'  ~ Skipped (irrelevant): {title[:60]}...'))
                        skipped_count += 1
                        continue

                    # TURKEY WAREHOUSE DOĞRULAMA
                    if ship_from_turkey:
                        # API response'da gönderim menşeini kontrol et
                        ship_from = product_data.get('ship_from_country') or ''
                        delivery_days = int(product_data.get('delivery_days', 0))

                        if ship_from and 'TR' not in ship_from.upper():
                            self.stdout.write(
                                self.style.WARNING(
                                    f'  ~ Skipped (not from Turkey): {title[:50]}... (from: {ship_from})'
                                )
                            )
                            skipped_count += 1
                            continue

                        # Delivery time kontrol (Türkiye'den çok hızlı olmalı)
                        if delivery_days > 14:
                            self.stdout.write(
                                self.style.WARNING(
                                    f'  ~ Skipped (slow delivery: {delivery_days} days): {title[:50]}...'
                                )
                            )
                            skipped_count += 1
                            continue

                    title_tr = tr_text(title)
                    category = product_data.get('category_name') or 'Belirtilmedi'
                    category_tr = tr_text(category)

                    # Build subtitle
                    discount = product_data.get('discount', '0').replace('%', '')
                    commission = product_data.get('commission_rate', '0').replace('%', '')

                    subtitle = f"{category_tr}"
                    if discount and float(discount) > 0:
                        subtitle += f" • %{discount} İndirim"

                    # Build features
                    ozellikler_lines = [
                        f"Kategori: {category_tr}",
                        f"Ürün ID: {product_data.get('product_id')}",
                        f"İndirim Oranı: %{discount}",
                        f"Komisyon Oranı: %{commission}",
                        f"Satış Sayısı: {product_data.get('orders', 0)}",
                        f"Değerlendirme: {product_data.get('rating', '0')}",
                        f"Gönderim: Çin'den",
                    ]

                    # Build tags
                    etiket_set = [category_tr]
                    title_words = [w for w in re.split(r'\W+', title_tr.lower()) if len(w) > 2]
                    etiket_set.extend(title_words[:8])
                    etiketler = ', '.join(dict.fromkeys([x for x in etiket_set if x]))[:500]

                    aciklama = f"{title_tr}\n\nKategori: {category_tr}"

                    # Canonical product URL (tekillik için stabil URL)
                    source_url = self.canonicalize_source_url(product_data)
                    if not source_url:
                        raise ValueError('source_url boş geldi, ürün atlandı')

                    product_id = self.extract_product_id(product_data)

                    # Affiliate link (komisyon için s.click / promotion link)
                    promotion_link = product_data.get('promotion_link')

                    # API promotion link dönmezse üretmeyi dene
                    if not promotion_link:
                        promotion_link = connector.generate_affiliate_link(
                            source_url,
                            tracking_id=tracking_id
                        ) or source_url

                    product = Urun.objects.filter(source_url=source_url).first()
                    created = False

                    # Eski kayıtlarda URL varyantları varsa product_id ile yakala
                    if not product and product_id:
                        product = Urun.objects.filter(source_url__icontains=f'/item/{product_id}').first()

                    if not product:
                        product = Urun.objects.create(
                            source_url=source_url,
                            isim=title_tr[:200],
                            aciklama=aciklama[:1000],
                            ana_baslik=title_tr,
                            alt_baslik=subtitle,
                            etiketler=etiketler,
                            ozellikler='\n'.join(ozellikler_lines)[:5000],
                            resim_url=product_data.get('image_url'),
                            urun_kodu=self.generate_unique_code(),
                        )
                        created = True

                    if created:
                        self.stdout.write(f'  ✓ Created: {title_tr[:50]}...')
                    else:
                        self.stdout.write(f'  ~ Existing: {title_tr[:50]}...')
                        # Update key fields
                        product.source_url = source_url
                        product.isim = title_tr[:200]
                        product.aciklama = aciklama[:1000]
                        product.ana_baslik = title_tr
                        product.alt_baslik = subtitle
                        product.etiketler = etiketler
                        product.ozellikler = '\n'.join(ozellikler_lines)[:5000]
                        if product_data.get('image_url'):
                            product.resim_url = product_data['image_url']
                        product.save()

                    # Add/update price
                    price, price_created = Fiyat.objects.get_or_create(
                        urun=product,
                        magaza=aliexpress_store,
                        defaults={
                            'fiyat': Decimal(str(product_data['price'])),
                            'para_birimi': product_data['currency'],
                            'affiliate_link': promotion_link,
                            'gonderim_ucreti': Decimal('0'),  # Usually free or not specified
                            'gonderim_yerinden': 'Çin',
                            'gonderim_durumu': True,
                        }
                    )

                    if not price_created:
                        # Update existing price
                        price.fiyat = Decimal(str(product_data['price']))
                        price.affiliate_link = promotion_link
                        price.save()

                    # Add product image if available
                    if product_data.get('image_url') and not product.resimler.exists():
                        UrunResim.objects.get_or_create(
                            urun=product,
                            resim_url=product_data['image_url'],
                            defaults={'sira': 0}
                        )

                    imported_count += 1

            except Exception as e:
                logger.error(f"Error importing product {product_data.get('title', 'Unknown')}: {str(e)}")
                skipped_count += 1
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Error: {str(e)[:100]}')
                )

        # Summary
        self.stdout.write(self.style.SUCCESS(f'\n=== IMPORT SUMMARY ==='))
        self.stdout.write(self.style.SUCCESS(f'✓ Successfully imported: {imported_count}'))
        if skipped_count > 0:
            self.stdout.write(self.style.WARNING(f'~ Skipped: {skipped_count}'))
        self.stdout.write(self.style.SUCCESS(f'Total processed: {imported_count + skipped_count}'))
