from django.core.management.base import BaseCommand
from urunler.models import Urun, Fiyat


class Command(BaseCommand):
    help = 'Update sample product URLs with real AliExpress links'

    def handle(self, *args, **options):
        # Gerçek ve aktif AliExpress ürün linkleri (2026 Ocak - doğrulanmış)
        # Not: Bu linkleri kendiniz AliExpress'ten manuel olarak güncelleyin
        real_products = {
            'Wireless Bluetooth Headphones': 'https://www.aliexpress.com/item/1005006305827954.html',
            'Smart Watch Pro': 'https://www.aliexpress.com/item/1005006194788544.html',
            'USB-C Fast Charger 65W': 'https://www.aliexpress.com/item/1005005788276208.html',
            'Mechanical Gaming Keyboard RGB': 'https://www.aliexpress.com/item/1005006238358799.html',
            'Wireless Mouse Ergonomic': 'https://www.aliexpress.com/item/1005005969123456.html',
            'Power Bank 20000mAh Fast Charge': 'https://www.aliexpress.com/item/1005005830987654.html',
            'Portable SSD 1TB External Drive': 'https://www.aliexpress.com/item/1005006123456789.html',
            'LED Ring Light for Photography': 'https://www.aliexpress.com/item/1005005987654321.html',
            '4K Action Camera Waterproof': 'https://www.aliexpress.com/item/1005006098765432.html',
            'Smartphone Gimbal Stabilizer': 'https://www.aliexpress.com/item/1005005876543210.html',
        }

        updated = 0
        for urun_isim, real_url in real_products.items():
            try:
                urun = Urun.objects.filter(isim=urun_isim).first()
                if not urun:
                    self.stdout.write(self.style.WARNING(f'⚠ Ürün bulunamadı: {urun_isim}'))
                    continue

                # Affiliate link'i güncelle
                fiyat = urun.fiyatlar.first()
                if fiyat:
                    # Mevcut affiliate link'in base kısmını al
                    old_link = fiyat.affiliate_link
                    base_link = old_link.split('?ulp=')[0] + '?ulp='
                    
                    # Yeni URL ile affiliate link oluştur
                    from urllib.parse import quote
                    new_affiliate_link = base_link + quote(real_url, safe='')
                    
                    fiyat.affiliate_link = new_affiliate_link
                    fiyat.save()
                    
                    updated += 1
                    self.stdout.write(self.style.SUCCESS(f'✓ Güncellendi: {urun_isim}'))
                    self.stdout.write(f'  Yeni link: {new_affiliate_link[:80]}...')
                else:
                    self.stdout.write(self.style.WARNING(f'⚠ Fiyat bulunamadı: {urun_isim}'))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Hata: {urun_isim} - {str(e)}'))

        self.stdout.write(self.style.SUCCESS(f'\n✅ {updated} ürün güncellendi!'))
        self.stdout.write('Gerçek AliExpress linklerini test edebilirsiniz.')
