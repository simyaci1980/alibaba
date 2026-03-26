"""
Django Management Command: cleanup_blocked_products
Batch check all products and remove those that don't ship to Turkey
"""

from django.core.management.base import BaseCommand
from urunler.models import Urun
from playwright.sync_api import sync_playwright
import time


class Command(BaseCommand):
    help = 'Check all products and remove those blocked in Turkey'

    def add_arguments(self, parser):
        parser.add_argument(
            '--auto-delete',
            action='store_true',
            help='Automatically delete blocked products without confirmation'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of products to check'
        )
        parser.add_argument(
            '--start-id',
            type=int,
            default=None,
            help='Start checking from this product ID'
        )
        parser.add_argument(
            '--headful',
            action='store_true',
            help='Show browser window (allows manual CAPTCHA solving)'
        )

    def handle(self, *args, **options):
        auto_delete = options['auto_delete']
        limit = options['limit']
        start_id = options['start_id']
        headful = options.get('headful', False)

        # Get products to check
        queryset = Urun.objects.filter(source_url__icontains='aliexpress.com')
        
        if start_id:
            queryset = queryset.filter(id__gte=start_id)
        
        queryset = queryset.order_by('-id')
        
        if limit:
            queryset = queryset[:limit]
        
        products = list(queryset)
        
        if not products:
            self.stdout.write('No products to check.')
            return
        
        self.stdout.write(f'Checking {len(products)} product(s)...\n')
        
        blocked_products = []
        unsure_products = []
        ok_products = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headful)
            context = browser.new_context(
                locale='tr-TR',
                extra_http_headers={'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8'},
                timezone_id='Europe/Istanbul',
            )
            page = context.new_page()
            page.set_default_timeout(30000)
            
            # Block unnecessary resources only in headless mode
            if not headful:
                page.route(
                    '**/*',
                    lambda route, request: route.abort()
                    if request.resource_type in {'image', 'media', 'font'}
                    else route.continue_()
                )
            
            for i, product in enumerate(products, 1):
                url = product.source_url
                if not url:
                    continue
                
                # Add shipToCountry parameter
                test_url = f"{url}{'&' if '?' in url else '?'}shipToCountry=TR"
                
                try:
                    page.goto(test_url, wait_until='domcontentloaded', timeout=30000)
                    page.wait_for_timeout(2000)
                    
                    html = page.content().lower()
                    
                    # Check for blocked phrases
                    blocked_phrases = [
                        'üzgünüz, bu ürün şu anda bulunduğunuz bölgede mevcut değil',
                        'üzgünüz, bu ürün şu anda konumunuzda kullanılamıyor',
                        'bu ürün henüz konumunuzda mevcut değil',
                        'bu ürün geçici olarak tedarik edilemiyor',
                        "can't be shipped",
                        'cannot be shipped',
                        'not available in your location',
                    ]
                    
                    captcha_phrases = ['captcha', 'robot', 'verify']
                    
                    # Check for CAPTCHA
                    is_captcha = any(phrase in html for phrase in captcha_phrases)
                    
                    # Check for blocked phrases
                    blocked_hits = [phrase for phrase in blocked_phrases if phrase in html]
                    
                    # Check for buy button
                    buy_selectors = [
                        "button:has-text('Satın Al')",
                        "button:has-text('Buy now')",
                        "[role='button']:has-text('Satın Al')",
                    ]
                    has_buy_button = False
                    for selector in buy_selectors:
                        try:
                            if page.locator(selector).count() > 0:
                                has_buy_button = True
                                break
                        except:
                            pass
                    
                    # Classify product
                    if is_captcha:
                        status = 'UNSURE (CAPTCHA)'
                        unsure_products.append(product)
                    elif blocked_hits:
                        status = f'BLOCKED: {blocked_hits[0][:40]}'
                        blocked_products.append(product)
                    elif has_buy_button:
                        status = 'OK (has buy button)'
                        ok_products.append(product)
                    else:
                        status = 'UNSURE (no button, no block)'
                        unsure_products.append(product)
                    
                    self.stdout.write(
                        f'[{i}/{len(products)}] ID={product.id:3d} | {status:30s} | {product.isim[:45]}'
                    )
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(
                            f'[{i}/{len(products)}] ID={product.id:3d} | ERROR: {str(e)[:50]} | {product.isim[:30]}'
                        )
                    )
                    unsure_products.append(product)
                
                # Small delay to avoid rate limiting
                time.sleep(0.5)
            
            context.close()
            browser.close()
        
        # Print summary
        self.stdout.write('\n' + '='*80)
        self.stdout.write(self.style.SUCCESS(f'✓ OK Products: {len(ok_products)}'))
        self.stdout.write(self.style.WARNING(f'⚠ Unsure Products: {len(unsure_products)}'))
        self.stdout.write(self.style.ERROR(f'❌ Blocked Products: {len(blocked_products)}'))
        
        if blocked_products:
            self.stdout.write('\nBlocked products:')
            for p in blocked_products:
                self.stdout.write(f'  ID={p.id:3d} | {p.isim[:60]}')
            
            if auto_delete:
                self.stdout.write(self.style.ERROR(f'\nDeleting {len(blocked_products)} blocked product(s)...'))
                for p in blocked_products:
                    p.delete()
                self.stdout.write(self.style.SUCCESS('✓ Deleted.'))
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'\nTo delete blocked products, run: '
                        f'python manage.py cleanup_blocked_products --auto-delete'
                    )
                )
