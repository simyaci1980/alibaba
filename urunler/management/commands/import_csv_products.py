import csv
from django.core.management.base import BaseCommand
from urunler.models import Urun, Magaza, Fiyat
from urunler.utils.deeplink import build_admitad_deeplink
from decouple import config

class Command(BaseCommand):
    help = 'CSV dosyasından ürünleri otomatik ekler (fiyatı 1.65 ile çarpar, affiliate link oluşturur)'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str, help='CSV dosyasının yolu')
        parser.add_argument('--subid', type=str, default='auto', help='Tracking için subid')

    def handle(self, *args, **options):
        csv_path = options['csv_path']
        subid = options['subid']
        base_link = config('ADMITAD_BASE_LINK', default='')
        if not base_link:
            self.stdout.write(self.style.ERROR('❌ ADMITAD_BASE_LINK eksik'))
            return

        magaza, _ = Magaza.objects.get_or_create(
            isim='AliExpress',
            defaults={'web_adresi': 'https://www.aliexpress.com'}
        )

        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    name = row['Ad']
                    price = float(row['Fiyat'].replace(',', '.')) * 1.65 if row['Fiyat'] else 199.99
                    image_url = row['Resim']
                    product_url = row['URL']

                    # Affiliate link oluştur
                    affiliate_link = build_admitad_deeplink(
                        base_link=base_link,
                        product_url=product_url,
                        subid=subid
                    )

                    urun = Urun.objects.create(
                        isim=name,
                        aciklama='CSV ile eklendi',
                        resim_url=image_url
                    )
                    Fiyat.objects.create(
                        urun=urun,
                        magaza=magaza,
                        fiyat=round(price, 2),
                        para_birimi='TL',
                        affiliate_link=affiliate_link
                    )
                    self.stdout.write(self.style.SUCCESS(f'✓ {name} eklendi (Fiyat: {round(price,2)} TL)'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'❌ Hata: {row.get("Ad", "Bilinmiyor")} - {e}'))
