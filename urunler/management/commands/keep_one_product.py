from django.core.management.base import BaseCommand
from urunler.models import Urun


class Command(BaseCommand):
    help = 'Keep only the first product and delete all others'

    def handle(self, *args, **options):
        # İlk ürünü al (gerçek linkli olan)
        first_urun = Urun.objects.first()
        
        if not first_urun:
            self.stdout.write(self.style.WARNING('Hiç ürün yok!'))
            return
        
        # Diğer tüm ürünleri sil
        diger_urunler = Urun.objects.exclude(id=first_urun.id)
        silinen_sayi = diger_urunler.count()
        
        if silinen_sayi == 0:
            self.stdout.write(self.style.WARNING('Silinecek başka ürün yok.'))
            self.stdout.write(f'Mevcut tek ürün: {first_urun.isim}')
            return
        
        diger_urunler.delete()
        
        self.stdout.write(self.style.SUCCESS(f'\n✓ {silinen_sayi} ürün silindi'))
        self.stdout.write(self.style.SUCCESS(f'✓ Kalan tek ürün: {first_urun.isim}'))
        
        # Fiyat bilgisini göster
        fiyat = first_urun.fiyatlar.first()
        if fiyat:
            self.stdout.write(f'\nFiyat: {fiyat.fiyat} TL')
            self.stdout.write(f'Mağaza: {fiyat.magaza.isim}')
            self.stdout.write(f'Link: {fiyat.affiliate_link[:80]}...')
