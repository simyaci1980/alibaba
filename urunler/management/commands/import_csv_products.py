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

                    # Ürünü tekilleştir: önce kaynak URL, yoksa isim+resim_url, en son isim
                    urun = None
                    if product_url:
                        urun = Urun.objects.filter(source_url=product_url).first()

                    if not urun and name and image_url:
                        urun = Urun.objects.filter(isim__iexact=name, resim_url=image_url).first()

                    if not urun and name:
                        urun = Urun.objects.filter(isim__iexact=name).first()

                    created = False
                    if urun:
                        if not urun.urun_kodu:
                            urun.urun_kodu = generate_unique_code()
                        urun.isim = name or urun.isim
                        urun.aciklama = description or urun.aciklama
                        urun.resim_url = image_url or urun.resim_url
                        if product_url and not urun.source_url:
                            urun.source_url = product_url
                        urun.save()
                    else:
                        urun_kodu = generate_unique_code()
                        urun = Urun.objects.create(
                            isim=name,
                            aciklama=description,
                            resim_url=image_url,
                            source_url=product_url or None,
                            urun_kodu=urun_kodu
                        )
                        created = True

                    # Affiliate link oluştur (subid olarak ürün kodu gönder)
                    affiliate_link = build_admitad_deeplink(
                        base_link=base_link,
                        product_url=product_url,
                        subid=urun.urun_kodu or 'auto'
                    )

                    Fiyat.objects.update_or_create(
                        urun=urun,
                        magaza=magaza,
                        defaults={
                            'fiyat': round(price, 2),
                            'para_birimi': 'TL',
                            'affiliate_link': affiliate_link,
                            'gonderim_ucreti': round(shipping_fee, 2),
                            'gonderim_yerinden': shipping_from,
                            'gonderim_durumu': can_deliver,
                        }
                    )
                    toplam = price + shipping_fee
                    if created:
                        self.stdout.write(self.style.SUCCESS(
                            f'✓ {name[:50]} eklendi (Fiyat: {price:.2f} + Gönderim: {shipping_fee:.2f} = {toplam:.2f} TL, Kod: {urun.urun_kodu})'
                        ))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f'⚠ {name[:50]} zaten vardı, güncellendi (Fiyat: {price:.2f} + Gönderim: {shipping_fee:.2f} = {toplam:.2f} TL, Kod: {urun.urun_kodu})'
                        ))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'❌ Hata: {row.get("title", row.get("Ad", "Bilinmiyor"))} - {e}'))
