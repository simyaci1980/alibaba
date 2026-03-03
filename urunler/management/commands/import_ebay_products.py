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

logger = logging.getLogger(__name__)


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

    def handle(self, *args, **options):
        search_query = options['search_query']
        limit = min(options['limit'], 200)  # Max 200
        use_sandbox = options['sandbox']
        campaign_id = options['campaign_id']

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
                # Check if product already exists (by source URL)
                source_url = item['affiliate_url'] or item['item_web_url']
                
                product, created = Urun.objects.get_or_create(
                    source_url=source_url,
                    defaults={
                        'isim': item['title'],
                        'aciklama': f"Kategori: {item['category'] or 'Belirtilmedi'}",
                        'ana_baslik': item['title'][:200],
                        'alt_baslik': f"Durum: {item['condition']}",
                        'etiketler': item['category'] or '',
                        'resim_url': item['image_url'],
                    }
                )

                if created:
                    self.stdout.write(f'✓ Created product: {item["title"][:50]}...')
                else:
                    self.stdout.write(f'~ Found existing: {item["title"][:50]}...')
                    # Keep text fields fresh for existing products too
                    product.aciklama = f"Kategori: {item['category'] or 'Belirtilmedi'}"
                    product.ana_baslik = item['title'][:200]
                    product.alt_baslik = f"Durum: {item['condition']}"
                    product.etiketler = item['category'] or ''
                    if item['image_url']:
                        product.resim_url = item['image_url']
                    product.save()

                # Add/update price entry
                affiliate_url = item['affiliate_url'] or item['item_web_url']
                
                # Add affiliate tracking if available
                if affiliate_url and campaign_id:
                    # Check if URL already has campaign ID
                    if 'campid=' not in affiliate_url:
                        separator = '&' if '?' in affiliate_url else '?'
                        affiliate_url += f"{separator}campid={campaign_id}&customid={product.id}"

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
