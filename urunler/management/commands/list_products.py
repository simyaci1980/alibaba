"""
Django Management Command: list_products
List recent products with URLs for manual checking
"""

from django.core.management.base import BaseCommand
from urunler.models import Urun


class Command(BaseCommand):
    help = 'List recent products with clickable URLs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Number of products to show (default: 20)'
        )
        parser.add_argument(
            '--start-id',
            type=int,
            default=None,
            help='Start from this ID'
        )
        parser.add_argument(
            '--with-tr-param',
            action='store_true',
            help='Add ?shipToCountry=TR to URLs for easy checking'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        start_id = options['start_id']
        with_tr = options['with_tr_param']
        
        # Get products
        queryset = Urun.objects.filter(source_url__icontains='aliexpress.com')
        
        if start_id:
            queryset = queryset.filter(id__gte=start_id)
        
        products = queryset.order_by('-id')[:limit]
        
        if not products:
            self.stdout.write('No products found.')
            return
        
        self.stdout.write(self.style.SUCCESS(f'\nShowing {products.count()} product(s):\n'))
        self.stdout.write('='*100)
        
        for p in products:
            url = p.source_url
            if with_tr and url:
                # Add shipToCountry=TR parameter
                separator = '&' if '?' in url else '?'
                url = f"{url}{separator}shipToCountry=TR"
            
            self.stdout.write(f'\nID: {p.id}')
            self.stdout.write(f'Name: {p.isim}')
            self.stdout.write(f'URL: {url}')
            self.stdout.write('-'*100)
        
        # Show quick delete command
        ids = ','.join(str(p.id) for p in products)
        self.stdout.write(self.style.WARNING(
            f'\n💡 To delete blocked products, use:\n'
            f'   python manage.py delete_products [ID1] [ID2] [ID3]\n'
        ))
        
        if with_tr:
            self.stdout.write(self.style.SUCCESS(
                f'\n✓ URLs include shipToCountry=TR parameter\n'
                f'  Open them in your browser to check TR availability\n'
                f'  If you see "Üzgünüz" message, the product cannot ship to Turkey'
            ))
