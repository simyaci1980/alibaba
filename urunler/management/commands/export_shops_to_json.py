"""
Export AliExpress shops to JSON with TR verification URLs
User can manually check which shops have products available for Turkey
"""

import json
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from urunler.aliexpress_api import AliExpressAPIConnector


class Command(BaseCommand):
    help = 'Export AliExpress shops to JSON with commission rates and TR verification URLs'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='shops_list.json',
            help='Output JSON file name (default: shops_list.json)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Maximum number of unique shops to fetch (default: 100)'
        )
        parser.add_argument(
            '--keywords',
            type=str,
            default='kitchen storage,bathroom storage,bedroom organization,home decor,office supplies',
            help='Comma-separated keywords to search for shops',
        )
    
    def handle(self, *args, **options):
        app_key = getattr(settings, 'ALIEXPRESS_APP_KEY', None)
        app_secret = getattr(settings, 'ALIEXPRESS_APP_SECRET', None)
        
        if not app_key or not app_secret:
            self.stdout.write(self.style.ERROR('❌ API keys not configured. Set ALIEXPRESS_APP_KEY and ALIEXPRESS_APP_SECRET'))
            return
        
        api = AliExpressAPIConnector(app_key, app_secret)
        
        # Parse keywords
        keywords = [k.strip() for k in options['keywords'].split(',')]
        
        shops = {}  # shop_id -> shop data
        self.stdout.write(self.style.SUCCESS('🛍️  Fetching products to extract shops...'))
        
        for keyword in keywords:
            try:
                self.stdout.write(f'  📌 Searching: "{keyword}"')
                response = api.search_products(keyword, page_size=50)
                
                if response:
                    # Parse response properly
                    items = api.parse_search_results(response)
                    self.stdout.write(f'     ✓ Found {len(items)} products')
                    
                    for item in items:
                        shop_id = item.get('shop_id')
                        if not shop_id:
                            continue
                        
                        # Get shop_name from _raw_data (API provides it there)
                        raw_data = item.get('_raw_data', {})
                        shop_name = raw_data.get('shop_name', 'Unknown')
                        
                        # Commission rate from API (could be "7.0%" or float)
                        commission = item.get('commission_rate', '')
                        
                        if shop_id not in shops:
                            shops[shop_id] = {
                                'shop_id': shop_id,
                                'shop_name': shop_name,
                                'shop_url': item.get('shop_url', ''),
                                'shop_rating': item.get('rating', 'N/A'),
                                'commission_rate': commission,
                                'commission_rates': [commission] if commission else [],
                                'product_count': 1,
                                'tr_available': None,  # User will fill this manually
                                'shop_url_tr': ''
                            }
                        else:
                            # Track multiple commission rates from same shop
                            if commission and commission not in shops[shop_id]['commission_rates']:
                                shops[shop_id]['commission_rates'].append(commission)
                            shops[shop_id]['product_count'] += 1
                else:
                    self.stdout.write(f'     ⚠️  No response for "{keyword}"')
                    
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'     ⚠️  Error searching "{keyword}": {str(e)}'))
                continue
        
        if not shops:
            self.stdout.write(self.style.ERROR('❌ No shops found. Please check API keys and keywords.'))
            return
        
        # Prepare final shop list
        shops_list = list(shops.values())
        
        # Calculate average commission rate if multiple rates exist
        for shop in shops_list:
            rates = []
            for rate_str in shop['commission_rates']:
                try:
                    # Remove '%' if present and convert to float
                    rate_val = float(str(rate_str).replace('%', ''))
                    rates.append(rate_val)
                except (ValueError, TypeError):
                    pass
            
            if rates:
                avg_rate = sum(rates) / len(rates)
                shop['commission_rate_avg'] = f"{avg_rate:.1f}%"
            else:
                shop['commission_rate_avg'] = 'N/A'
        
        # Sort by product count (most products first)
        shops_list.sort(key=lambda x: x['product_count'], reverse=True)
        
        # Add TR verification URLs
        for shop in shops_list:
            if shop['shop_url']:
                shop['shop_url_tr'] = f"{shop['shop_url']}?shipToCountry=TR"
            else:
                shop['shop_url_tr'] = 'N/A'
        
        # Limit to specified count
        shops_list = shops_list[:options['limit']]
        
        # Clean up temporary commission_rates list before saving
        for shop in shops_list:
            del shop['commission_rates']
        
        # Save to JSON
        output_file = options['output']
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(shops_list, f, ensure_ascii=False, indent=2)
            
            self.stdout.write(self.style.SUCCESS(f'✅ Exported {len(shops_list)} shops to {output_file}'))
            self.stdout.write(self.style.SUCCESS(f'\n📋 Shop Summary:'))
            self.stdout.write(f'   Top 3 shops by product count:')
            for i, shop in enumerate(shops_list[:3], 1):
                self.stdout.write(
                    f'   {i}. {shop["shop_name"]} '
                    f'(ID: {shop["shop_id"]}, Products: {shop["product_count"]}, '
                    f'Avg Commission: {shop["commission_rate_avg"]}, '
                    f'Rating: {shop["shop_rating"]})'
                )
            
            self.stdout.write(f'\n📝 Next Steps:')
            self.stdout.write(f'   1. Open {output_file} in text editor')
            self.stdout.write(f'   2. For each shop, open the "shop_url_tr" link in your browser (includes ?shipToCountry=TR)')
            self.stdout.write(f'   3. Check if products are available (should see "Satın Al" button if TR shipping works)')
            self.stdout.write(f'   4. Update "tr_available": true/false for each shop')
            self.stdout.write(f'   5. Run: python manage.py import_from_shops --from-shops={output_file} --only-tr-available')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error writing to {output_file}: {str(e)}'))
