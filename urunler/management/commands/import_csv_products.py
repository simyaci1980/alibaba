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
        import random, string
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

        def generate_unique_code(length=5):
            while True:
                code = ''.join(random.choices(string.digits, k=length))
                if not Urun.objects.filter(urun_kodu=code).exists():
                    return code

        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    name = row.get('title', row.get('Ad', ''))
                    description = row.get('description', 'CSV ile eklendi')
                    price_str = row.get('totalPrice', row.get('Fiyat', '0'))
                    price = float(price_str.replace(',', '.')) if price_str else 0
                    
                    # Gönderim bilgileri
                    shipping_fee_str = row.get('shippingFee', '0')
                    shipping_fee = float(shipping_fee_str.replace(',', '.')) if shipping_fee_str else 0
                    shipping_from = row.get('shippingFrom', 'Çin')
                    shipping_status = row.get('status', 'Gönderilebiliyor ✅')
                    can_deliver = '✅' in shipping_status or 'Gönderilebiliyor' in shipping_status
                    
                    image_url = row.get('imageUrl', row.get('Resim', ''))
                    product_url = row.get('productLink', row.get('URL', ''))

                    urun_kodu = generate_unique_code()
                    # Affiliate link oluştur (subid olarak ürün kodu gönder)
                    affiliate_link = build_admitad_deeplink(
                        base_link=base_link,
                        product_url=product_url,
                        subid=urun_kodu
                    )

                    urun = Urun.objects.create(
                        isim=name,
                        aciklama=description,
                        resim_url=image_url,
                        urun_kodu=urun_kodu
                    )
                    Fiyat.objects.create(
                        urun=urun,
                        magaza=magaza,
                        fiyat=round(price, 2),
                        para_birimi='TL',
                        affiliate_link=affiliate_link,
                        gonderim_ucreti=round(shipping_fee, 2),
                        gonderim_yerinden=shipping_from,
                        gonderim_durumu=can_deliver
                    )
                    toplam = price + shipping_fee
                    self.stdout.write(self.style.SUCCESS(
                        f'✓ {name[:50]} eklendi (Fiyat: {price:.2f} + Gönderim: {shipping_fee:.2f} = {toplam:.2f} TL, Kod: {urun_kodu})'
                    ))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'❌ Hata: {row.get("title", row.get("Ad", "Bilinmiyor"))} - {e}'))
