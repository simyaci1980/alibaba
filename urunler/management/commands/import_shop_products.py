"""
Django Management Command: import_shop_products
Scrapes products directly from an AliExpress shop page
No API limitations - gets all products from the shop
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from urunler.aliexpress_api import AliExpressAPIConnector
from urunler.models import Urun, Magaza, Fiyat, UrunResim
from decimal import Decimal
import logging
import json
import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import products from AliExpress shop by scraping shop page'

    def add_arguments(self, parser):
        parser.add_argument(
            'shop_id',
            type=str,
            help='Shop ID (e.g., 5251272 or 1105265650)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Maximum number of products to import (default: 20)'
        )
        parser.add_argument(
            '--tracking-id',
            type=str,
            default=getattr(settings, 'ALIEXPRESS_TRACKING_ID', 'kolaybulexpres'),
            help='Your tracking/sub ID for affiliate links'
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Skip products that already exist in database'
        )
        parser.add_argument(
            '--translate-tr',
            action='store_true',
            help='Translate product descriptions to Turkish'
        )
        parser.add_argument(
            '--headful',
            action='store_true',
            help='Show browser window (for debugging)'
        )

    def handle(self, *args, **options):
        shop_id = options['shop_id']
        limit = options['limit']
        tracking_id = options['tracking_id']
        skip_existing = options['skip_existing']
        translate_tr = options['translate_tr']
        headful = options.get('headful', False)

        self.stdout.write(f"🔍 Scraping products from shop {shop_id}")
        self.stdout.write(f"📊 Limit: {limit} products")
        
        # Initialize API connector for affiliate links
        app_key = getattr(settings, 'ALIEXPRESS_APP_KEY', None)
        app_secret = getattr(settings, 'ALIEXPRESS_APP_SECRET', None)
        
        if not app_key or not app_secret:
            raise CommandError("AliExpress API credentials not found in settings")
        
        api_connector = AliExpressAPIConnector(app_key, app_secret)
        
        # Scrape shop page for product links
        product_links = self._scrape_shop_page(shop_id, limit, headful)
        
        if not product_links:
            self.stdout.write(self.style.WARNING("⚠ No products found in shop"))
            return
        
        self.stdout.write(self.style.SUCCESS(f"✓ Found {len(product_links)} products"))
        
        # Process each product
        imported_count = 0
        skipped_count = 0
        
        for idx, product_url in enumerate(product_links, 1):
            self.stdout.write(f"\n[{idx}/{len(product_links)}] Processing: {product_url}")
            
            # Extract product ID from URL
            product_id = self._extract_product_id(product_url)
            if not product_id:
                self.stdout.write(self.style.WARNING("  ⚠ Could not extract product ID"))
                continue
            
            # Check if product already exists
            if skip_existing:
                existing = Urun.objects.filter(urun_kodu=product_id).first()
                if existing:
                    self.stdout.write(self.style.WARNING(f"  ⏭ Already exists: {existing.isim[:50]}"))
                    skipped_count += 1
                    continue
            
            # Get product details from API
            try:
                product_data = api_connector.get_product_details(
                    product_id=product_id,
                    tracking_id=tracking_id
                )
                
                if not product_data:
                    self.stdout.write(self.style.WARNING("  ⚠ API returned no data"))
                    continue
                
                # Extract product info from API response
                resp_result = product_data.get('aliexpress_affiliate_productdetail_get_response', {}).get('resp_result', {})
                if isinstance(resp_result, str):
                    resp_result = json.loads(resp_result)
                
                result = resp_result.get('result', {})
                if not result:
                    self.stdout.write(self.style.WARNING("  ⚠ Empty result from API"))
                    continue
                
                # Save product to database
                saved = self._save_product(result, tracking_id, translate_tr)
                if saved:
                    imported_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Imported: {saved.isim[:50]}"))
                else:
                    self.stdout.write(self.style.WARNING("  ⚠ Failed to save product"))
                
                # Rate limiting
                time.sleep(1)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
                continue
        
        # Summary
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS(f"✓ Import complete"))
        self.stdout.write(f"  • Imported: {imported_count}")
        self.stdout.write(f"  • Skipped: {skipped_count}")
        self.stdout.write(f"  • Total processed: {len(product_links)}")

    def _scrape_shop_page(self, shop_id, limit, headful=False):
        """Scrape product links from shop page using Playwright"""
        shop_url = f"https://www.aliexpress.com/store/{shop_id}"
        product_links = []
        
        try:
            with sync_playwright() as p:
                self.stdout.write(f"🌐 Opening shop page: {shop_url}")
                browser = p.chromium.launch(headless=not headful)
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = context.new_page()
                
                # Navigate to shop
                page.goto(shop_url, timeout=60000, wait_until='networkidle')
                self.stdout.write("  ⏳ Waiting for page to load...")
                time.sleep(8)  # Wait for dynamic content
                
                # Check if we need to handle any popups/cookies
                try:
                    close_button = page.query_selector('button[class*="close"], .close-btn, [aria-label="Close"]')
                    if close_button:
                        close_button.click()
                        time.sleep(1)
                except:
                    pass
                
                # Scroll to load more products
                self.stdout.write("  📜 Scrolling to load more products...")
                for i in range(5):
                    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    time.sleep(2)
                
                # Try multiple selectors for product links
                self.stdout.write("  🔍 Looking for product links...")
                
                # Selector 1: Standard product links
                links = page.query_selector_all('a[href*="/item/"]')
                self.stdout.write(f"  • Found {len(links)} links with /item/ pattern")
                
                # Selector 2: Product cards
                if not links:
                    links = page.query_selector_all('.product-card a, .product-item a')
                    self.stdout.write(f"  • Found {len(links)} product card links")
                
                # Selector 3: Any link to aliexpress item
                if not links:
                    links = page.query_selector_all('a[href*="aliexpress.com/item"]')
                    self.stdout.write(f"  • Found {len(links)} aliexpress item links")
                
                # Debug: Print page content structure
                if not links and headful:
                    self.stdout.write("  📄 Page HTML preview:")
                    html_preview = page.content()[:500]
                    self.stdout.write(f"  {html_preview}")

                
                seen_ids = set()
                for link in links:
                    href = link.get_attribute('href')
                    if not href:
                        continue
                    
                    # Make absolute URL
                    if href.startswith('//'):
                        href = 'https:' + href
                    elif href.startswith('/'):
                        href = 'https://www.aliexpress.com' + href
                    
                    # Extract product ID to deduplicate
                    product_id = self._extract_product_id(href)
                    if product_id and product_id not in seen_ids:
                        product_links.append(href)
                        seen_ids.add(product_id)
                        
                        if len(product_links) >= limit:
                            break
                
                browser.close()
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Scraping error: {str(e)}"))
        
        return product_links[:limit]

    def _extract_product_id(self, url):
        """Extract product ID from AliExpress URL"""
        # Pattern: /item/{product_id}.html
        match = re.search(r'/item/(\d+)\.html', url)
        if match:
            return match.group(1)
        
        # Alternative pattern: /item/{product_id}
        match = re.search(r'/item/(\d+)', url)
        if match:
            return match.group(1)
        
        return None

    def _save_product(self, product_data, tracking_id, translate_tr):
        """Save product to database (similar to import_aliexpress_products)"""
        try:
            product_id = str(product_data.get('product_id', ''))
            product_title = product_data.get('product_title', '')
            
            if not product_id or not product_title:
                return None
            
            # Get or create shop
            shop_id = product_data.get('shop_id')
            shop_url = product_data.get('shop_url', '')
            
            magaza = None
            if shop_id:
                magaza, _ = Magaza.objects.get_or_create(
                    magaza_id=str(shop_id),
                    defaults={
                        'isim': f"Shop {shop_id}",
                        'url': shop_url or f"https://www.aliexpress.com/store/{shop_id}"
                    }
                )
            
            # Get product URL
            product_url = product_data.get('product_detail_url', '')
            if not product_url:
                product_url = f"https://www.aliexpress.com/item/{product_id}.html"
            
            # Clean URL (remove tracking params)
            product_url = self._clean_url(product_url)
            
            # Check if product already exists
            urun, created = Urun.objects.get_or_create(
                urun_kodu=product_id,
                defaults={
                    'isim': product_title,
                    'source_url': product_url,
                }
            )
            
            if not created:
                # Update existing product
                urun.isim = product_title
                urun.source_url = product_url
            
            # Generate titles and description
            if translate_tr:
                # Use translation function if available
                try:
                    from urunler.utils.translate import tr_text
                    urun.ana_baslik = tr_text(product_title)
                    urun.alt_baslik = tr_text(f"High quality {product_title.lower()}")
                    urun.aciklama = tr_text(product_data.get('product_description', product_title))
                except:
                    urun.ana_baslik = product_title
                    urun.alt_baslik = f"Quality {product_title}"
                    urun.aciklama = product_data.get('product_description', product_title)
            else:
                urun.ana_baslik = product_title
                urun.alt_baslik = f"Quality {product_title}"
                urun.aciklama = product_data.get('product_description', product_title)
            
            urun.save()
            
            # Save price
            target_sale_price = product_data.get('target_sale_price')
            promotion_link = product_data.get('promotion_link', '')
            
            if target_sale_price:
                fiyat, _ = Fiyat.objects.get_or_create(
                    urun=urun,
                    magaza=magaza,
                    defaults={
                        'fiyat': Decimal(str(target_sale_price)),
                        'para_birimi': 'USD',
                        'affiliate_link': promotion_link
                    }
                )
                
                # Update if exists
                fiyat.fiyat = Decimal(str(target_sale_price))
                fiyat.affiliate_link = promotion_link
                fiyat.save()
            
            # Save product images
            product_main_image_url = product_data.get('product_main_image_url', '')
            product_video_url = product_data.get('product_video_url', '')
            
            if product_main_image_url:
                UrunResim.objects.get_or_create(
                    urun=urun,
                    resim_url=product_main_image_url,
                    defaults={'sira': 1}
                )
            
            return urun
            
        except Exception as e:
            logger.error(f"Error saving product: {str(e)}")
            return None

    def _clean_url(self, url):
        """Remove tracking parameters from URL"""
        if not url:
            return url
        
        # Remove common tracking params
        parsed = list(urlsplit(url))
        query_params = dict(parse_qsl(parsed[3]))
        
        # Remove tracking params
        tracking_params = ['aff_fcid', 'aff_fsk', 'aff_platform', 'sk', 'aff_trace_key', 
                          'terminal_id', 'afSmartRedirect', 'gatewayAdapt', 'spm']
        for param in tracking_params:
            query_params.pop(param, None)
        
        parsed[3] = urlencode(query_params)
        return urlunsplit(parsed)
