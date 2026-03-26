"""
Django Management Command: delete_products
Quickly delete products by ID list
"""

from django.core.management.base import BaseCommand
from urunler.models import Urun


class Command(BaseCommand):
    help = 'Delete products by ID list'

    def add_arguments(self, parser):
        parser.add_argument(
            'product_ids',
            nargs='+',
            type=int,
            help='Product IDs to delete (space-separated)'
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt'
        )

    def handle(self, *args, **options):
        product_ids = options['product_ids']
        confirm = options['confirm']
        
        # Get products
        products = Urun.objects.filter(id__in=product_ids)
        
        if not products.exists():
            self.stdout.write(self.style.WARNING('No products found with given IDs.'))
            return
        
        # Show products to delete
        self.stdout.write(self.style.WARNING(f'\nWill delete {products.count()} product(s):\n'))
        for p in products:
            self.stdout.write(f'  ID={p.id:3d} | {p.isim[:60]}')
        
        # Confirm deletion
        if not confirm:
            response = input('\nType "yes" to confirm deletion: ')
            if response.lower() != 'yes':
                self.stdout.write(self.style.ERROR('Deletion cancelled.'))
                return
        
        # Delete products
        count, details = products.delete()
        
        self.stdout.write(self.style.SUCCESS(f'\n✓ Deleted {count} objects:'))
        for model, num in details.items():
            self.stdout.write(f'  - {model}: {num}')
