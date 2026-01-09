from django.core.management.base import BaseCommand
from urunler.models import Urun, Magaza, Fiyat, UrunResim
from urunler.utils.deeplink import build_admitad_deeplink
from decouple import config
import random


class Command(BaseCommand):
    help = 'Fetch and add AliExpress products to database (demo with sample data)'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=10, help='Number of products to add (default: 10)')
        parser.add_argument('--category', type=str, default='electronics', help='Product category (for demo purposes)')

    def handle(self, *args, **options):
        limit = options['limit']
        category = options['category']
        base_link = config('ADMITAD_BASE_LINK', default='')

        if not base_link:
            self.stdout.write(self.style.ERROR('❌ ADMITAD_BASE_LINK is missing in .env'))
            self.stdout.write('Add it to .env file first')
            return

        # Get or create AliExpress store
        aliexpress, created = Magaza.objects.get_or_create(
            isim='AliExpress',
            defaults={'web_adresi': 'https://www.aliexpress.com'}
        )
        if created:
            self.stdout.write(self.style.SUCCESS('✓ Created AliExpress store'))

        self.stdout.write(self.style.SUCCESS(f'\n🔄 Fetching {limit} products from category: {category}...\n'))

        # Sample product data (Admitad doesn't provide direct product API)
        # In production, you would scrape or use AliExpress API directly
        sample_products = [
            {
                'name': 'Wireless Bluetooth Headphones',
                'description': 'High-quality wireless headphones with noise cancellation and 30-hour battery life.',
                'price': 299.99,
                'url': 'https://www.aliexpress.com/item/1005003842156789.html',
                'image': 'https://ae01.alicdn.com/kf/S8e5a8b5c5b5e4c5d8f5e5a5b5c5d5e5fM.jpg'
            },
            {
                'name': 'Smart Watch Pro',
                'description': 'Fitness tracker with heart rate monitor, GPS, and water resistance.',
                'price': 599.90,
                'url': 'https://www.aliexpress.com/item/1005004123456789.html'
            },
            {
                'name': 'USB-C Fast Charger 65W',
                'description': 'Compact fast charger with multiple ports for laptops and phones.',
                'price': 149.50,
                'url': 'https://www.aliexpress.com/item/1005004987654321.html'
            },
            {
                'name': 'Mechanical Gaming Keyboard RGB',
                'description': 'RGB backlit mechanical keyboard with customizable keys.',
                'price': 450.00,
                'url': 'https://www.aliexpress.com/item/1005003111222333.html'
            },
            {
                'name': 'Wireless Mouse Ergonomic',
                'description': 'Ergonomic wireless mouse with adjustable DPI and silent clicks.',
                'price': 89.99,
                'url': 'https://www.aliexpress.com/item/1005004444555666.html'
            },
            {
                'name': '4K Action Camera Waterproof',
                'description': 'Action camera with 4K recording, waterproof case, and accessories.',
                'price': 799.00,
                'url': 'https://www.aliexpress.com/item/1005003777888999.html'
            },
            {
                'name': 'Portable SSD 1TB External Drive',
                'description': 'Ultra-fast portable SSD with USB 3.2 Gen 2 for quick data transfer.',
                'price': 549.90,
                'url': 'https://www.aliexpress.com/item/1005004321098765.html'
            },
            {
                'name': 'LED Ring Light for Photography',
                'description': 'Professional ring light with adjustable brightness and tripod stand.',
                'price': 199.00,
                'url': 'https://www.aliexpress.com/item/1005003654321987.html'
            },
            {
                'name': 'Power Bank 20000mAh Fast Charge',
                'description': 'High-capacity power bank with dual USB ports and LED display.',
                'price': 179.50,
                'url': 'https://www.aliexpress.com/item/1005004789123456.html'
            },
            {
                'name': 'Smartphone Gimbal Stabilizer',
                'description': '3-axis gimbal for smartphones with face tracking and long battery.',
                'price': 399.00,
                'url': 'https://www.aliexpress.com/item/1005003147258369.html'
            },
            {
                'name': 'Laptop Stand Adjustable Aluminum',
                'description': 'Ergonomic laptop stand made of premium aluminum with cooling design.',
                'price': 129.99,
                'url': 'https://www.aliexpress.com/item/1005004951753468.html'
            },
            {
                'name': 'Mini Projector 1080P Portable',
                'description': 'Compact portable projector with WiFi, Bluetooth, and 1080P support.',
                'price': 899.00,
                'url': 'https://www.aliexpress.com/item/1005003258147963.html'
            },
            {
                'name': 'Graphics Drawing Tablet',
                'description': 'Professional drawing tablet with pressure sensitivity and stylus.',
                'price': 649.00,
                'url': 'https://www.aliexpress.com/item/1005004369852147.html'
            },
            {
                'name': 'Webcam 1080P HD with Microphone',
                'description': 'Full HD webcam with built-in microphone for video calls and streaming.',
                'price': 219.90,
                'url': 'https://www.aliexpress.com/item/1005003741852963.html'
            },
            {
                'name': 'Cable Organizer Kit 50 Pieces',
                'description': 'Complete cable management kit with clips, ties, and holders.',
                'price': 59.90,
                'url': 'https://www.aliexpress.com/item/1005004852963741.html'
            },
        ]

        added_count = 0
        for i, product_data in enumerate(sample_products[:limit]):
            try:
                # Check if product already exists
                if Urun.objects.filter(isim=product_data['name']).exists():
                    self.stdout.write(self.style.WARNING(f'⚠ Skipping: {product_data["name"]} (already exists)'))
                    continue

                # Create product
                urun = Urun.objects.create(
                    isim=product_data['name'],
                    aciklama=product_data['description'],
                )

                # Add product image if available
                if 'image' in product_data and product_data['image']:
                    # For now, we'll use a placeholder image service
                    image_url = f"https://via.placeholder.com/300x200/6366f1/ffffff?text={product_data['name'][:20]}"
                    # Note: In production, you would download and save actual images
                    # For now we just reference the URL in description or skip images

                # Create affiliate deeplink
                try:
                    affiliate_link = build_admitad_deeplink(
                        base_link=base_link,
                        product_url=product_data['url'],
                        subid=f'auto_{i}'
                    )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'✗ Failed to create deeplink: {e}'))
                    affiliate_link = product_data['url']  # Fallback to original URL

                # Add price with affiliate link
                Fiyat.objects.create(
                    urun=urun,
                    magaza=aliexpress,
                    fiyat=product_data['price'],
                    affiliate_link=affiliate_link
                )

                added_count += 1
                self.stdout.write(self.style.SUCCESS(f'✓ Added: {product_data["name"]} - ₺{product_data["price"]}'))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Failed to add {product_data["name"]}: {str(e)}'))

        self.stdout.write(self.style.SUCCESS(f'\n✅ Successfully added {added_count} products!'))
        self.stdout.write(f'Visit http://127.0.0.1:8000/ to see them.')
