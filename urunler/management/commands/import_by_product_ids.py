"""
Django Management Command: import_by_product_ids
Imports specific products by their AliExpress Product IDs
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from urunler.aliexpress_api import AliExpressAPIConnector
from urunler.models import Urun, Magaza, Fiyat, UrunResim
from decimal import Decimal
import logging
import json
import time

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import products by their AliExpress Product IDs'

    def add_arguments(self, parser):
        parser.add_argument(
            'product_ids',
            nargs='*',
            type=str,
            help='Product IDs to import (space-separated)'
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
            '--from-file',
            type=str,
            help='Read product IDs from JSON file (products with commission_rate 7%)'
        )

    def handle(self, *args, **options):
        tracking_id = options['tracking_id']
        skip_existing = options['skip_existing']
        
        # Get product IDs
        product_ids = options['product_ids']
        
        # If from-file specified, load from JSON
        products_data = {}
        if options['from_file']:
            try:
                with open(options['from_file'], 'r') as f:
                    data = json.load(f)
                    # Filter by commission rate 7%
                    filtered = [p for p in data if p.get('commission_rate') == '7.0%']
                    product_ids = [str(p['product_id']) for p in filtered]
                    # Store product data from JSON
                    for p in filtered:
                        products_data[str(p['product_id'])] = p
                    self.stdout.write(f"✓ Loaded {len(product_ids)} products from {options['from_file']}")
            except Exception as e:
                raise CommandError(f"Error reading file: {str(e)}")
        
        self.stdout.write(f"\n🔍 Importing {len(product_ids)} products by ID")
        
        # Initialize API connector (for generating affiliate links if needed)
        app_key = getattr(settings, 'ALIEXPRESS_APP_KEY', None)
        app_secret = getattr(settings, 'ALIEXPRESS_APP_SECRET', None)
        
        if not app_key or not app_secret:
            raise CommandError("AliExpress API credentials not found in settings")
        
        api_connector = AliExpressAPIConnector(app_key, app_secret)
        
        # Process each product
        imported_count = 0
        skipped_count = 0
        failed_count = 0
        
        for idx, product_id in enumerate(product_ids, 1):
            self.stdout.write(f"\n[{idx}/{len(product_ids)}] Product ID: {product_id}")
            
            # Check if already exists
            if skip_existing:
                existing = Urun.objects.filter(urun_kodu=product_id).first()
                if existing:
                    self.stdout.write(self.style.WARNING(f"  ⏭ Already exists: {existing.isim[:50]}"))
                    skipped_count += 1
                    continue
            
            try:
                # Get product data from JSON if available
                if product_id in products_data:
                    self.stdout.write(f"  📦 Using data from JSON file...")
                    saved = self._save_product_from_json(products_data[product_id], tracking_id)
                else:
                    # Fallback: try API
                    self.stdout.write(f"  📡 Fetching from API...")
                    product_data = api_connector.get_product_details(
                        product_id=product_id,
                        tracking_id=tracking_id
                    )
                    
                    if not product_data:
                        self.stdout.write(self.style.WARNING("  ⚠ API returned no data"))
                        failed_count += 1
                        continue
                    
                    # Extract product info from API response
                    resp_result = product_data.get('aliexpress_affiliate_productdetail_get_response', {}).get('resp_result', {})
                    if isinstance(resp_result, str):
                        resp_result = json.loads(resp_result)
                    
                    result = resp_result.get('result', {})
                    if not result:
                        self.stdout.write(self.style.WARNING("  ⚠ Empty result from API"))
                        failed_count += 1
                        continue
                    
                    saved = self._save_product(result, tracking_id)
                
                if saved:
                    imported_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Imported: {saved.isim[:50]}"))
                else:
                    self.stdout.write(self.style.WARNING("  ⚠ Failed to save product"))
                    failed_count += 1
                
                # Rate limiting
                time.sleep(1)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
                failed_count += 1
                continue
        
        # Summary
        self.stdout.write("\n" + "="*70)
        self.stdout.write(self.style.SUCCESS(f"✓ Import complete"))
        self.stdout.write(f"  • Imported: {imported_count}")
        self.stdout.write(f"  • Skipped: {skipped_count}")
        self.stdout.write(f"  • Failed: {failed_count}")
        self.stdout.write(f"  • Total: {len(product_ids)}")

    def _save_product(self, product_data, tracking_id):
        """Save product to database"""
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
                    isim=f"Shop {shop_id}",
                    defaults={
                        'web_adresi': shop_url or f"https://www.aliexpress.com/store/{shop_id}"
                    }
                )
            
            # Get product URL
            product_url = product_data.get('product_detail_url', '')
            if not product_url:
                product_url = f"https://www.aliexpress.com/item/{product_id}.html"
            
            # Check if product already exists
            urun, created = Urun.objects.get_or_create(
                urun_kodu=product_id,
                defaults={
                    'isim': product_title,
                    'source_url': product_url,
                }
            )
            
            if not created:
                # Update existing
                urun.isim = product_title
                urun.source_url = product_url
            
            # Set titles and description
            urun.ana_baslik = product_title
            urun.alt_baslik = f"High quality {product_title.lower()}"
            urun.aciklama = product_data.get('product_description', product_title)
            
            urun.save()
            
            # Save price with affiliate link
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

    def _save_product_from_json(self, product_json, tracking_id):
        """Save product from JSON data (candidates_bathroom.json format)"""
        try:
            product_id = str(product_json.get('product_id', ''))
            product_title = product_json.get('title', '')
            
            if not product_id or not product_title:
                return None
            
            # Extract shop info from URL
            shop_url = product_json.get('shop_url', '')
            shop_id = None
            if shop_url:
                # Extract shop_id from URL
                import re
                match = re.search(r'/store/(\d+)', shop_url)
                if match:
                    shop_id = match.group(1)
            
            magaza = None
            if shop_id:
                magaza, _ = Magaza.objects.get_or_create(
                    isim=f"Shop {shop_id}",
                    defaults={
                        'web_adresi': shop_url or f"https://www.aliexpress.com/store/{shop_id}"
                    }
                )
            
            # Get product URL - clean it
            product_url = product_json.get('product_url', '')
            if not product_url:
                product_url = f"https://www.aliexpress.com/item/{product_id}.html"
            
            # Clean URL parameters
            if '?' in product_url:
                product_url = product_url.split('?')[0]
            
            # Check if product already exists
            urun, created = Urun.objects.get_or_create(
                urun_kodu=product_id,
                defaults={
                    'isim': product_title,
                    'source_url': product_url,
                }
            )
            
            if not created:
                # Update existing
                urun.isim = product_title
                urun.source_url = product_url
            
            # Set titles
            urun.ana_baslik = product_title
            urun.alt_baslik = f"Quality {product_title.lower()}"
            urun.aciklama = f"Original AliExpress product - {product_title}"
            
            urun.save()
            
            # Save price with affiliate link
            price = float(product_json.get('price', 0))
            promotion_link = product_json.get('promotion_link', '')
            
            if price > 0:
                fiyat, _ = Fiyat.objects.get_or_create(
                    urun=urun,
                    magaza=magaza,
                    defaults={
                        'fiyat': Decimal(str(price)),
                        'para_birimi': product_json.get('currency', 'USD'),
                        'affiliate_link': promotion_link
                    }
                )
                
                # Update if exists
                fiyat.fiyat = Decimal(str(price))
                fiyat.affiliate_link = promotion_link
                fiyat.save()
            
            # Save product image
            image_url = product_json.get('image_url', '')
            if image_url:
                UrunResim.objects.get_or_create(
                    urun=urun,
                    resim_url=image_url,
                    defaults={'sira': 1}
                )
            
            return urun
            
        except Exception as e:
            logger.error(f"Error saving product from JSON: {str(e)}")
            return None
