from django.core.management.base import BaseCommand
from urunler.models import Urun, Magaza, Fiyat
from urunler.utils.deeplink import build_admitad_deeplink
from decouple import config
import requests
from bs4 import BeautifulSoup
import re
import json


class Command(BaseCommand):
    help = 'Otomatik AliExpress ürün ekle - link verdiğinizde ürün bilgilerini çekip ekler'

    def add_arguments(self, parser):
        parser.add_argument('url', type=str, help='AliExpress ürün URL\'si')
        parser.add_argument('--subid', type=str, default='auto', help='Tracking için subid')

    def handle(self, *args, **options):
        url = options['url']
        subid = options['subid']
        base_link = config('ADMITAD_BASE_LINK', default='')

        if not base_link:
            self.stdout.write(self.style.ERROR('❌ ADMITAD_BASE_LINK eksik'))
            return

        self.stdout.write(self.style.SUCCESS(f'\n🔄 Ürün bilgileri çekiliyor...\n'))
        self.stdout.write(f'URL: {url[:80]}...\n')

        try:
            # AliExpress sayfasını çek
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Ürün bilgilerini çek
            product_data = self.extract_product_info(soup, url)
            
            if not product_data['title']:
                self.stdout.write(self.style.ERROR('❌ Ürün bilgileri çekilemedi'))
                return
            
            self.stdout.write(self.style.SUCCESS(f'✓ Başlık: {product_data["title"]}'))
            self.stdout.write(self.style.SUCCESS(f'✓ Fiyat: {product_data["price"]} TL'))
            if product_data['description']:
                self.stdout.write(self.style.SUCCESS(f'✓ Açıklama: {product_data["description"][:50]}...'))
            
            # Mağaza kontrolü
            magaza, created = Magaza.objects.get_or_create(
                isim='AliExpress',
                defaults={'web_adresi': 'https://www.aliexpress.com'}
            )
            
            # Aynı isimde ürün var mı kontrol et
            if Urun.objects.filter(isim=product_data['title']).exists():
                self.stdout.write(self.style.WARNING(f'\n⚠ Bu isimde ürün zaten var: {product_data["title"]}'))
                overwrite = input('Yine de eklemek ister misiniz? (y/n): ')
                if overwrite.lower() != 'y':
                    return
            
            # Affiliate link oluştur
            self.stdout.write('\n🔗 Affiliate link oluşturuluyor...')
            try:
                affiliate_link = build_admitad_deeplink(
                    base_link=base_link,
                    product_url=url,
                    subid=subid
                )
                self.stdout.write(self.style.SUCCESS(f'✓ Affiliate link: {affiliate_link[:60]}...'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Affiliate link hatası: {e}'))
                return
            
            # Ürünü ekle
            urun = Urun.objects.create(
                isim=product_data['title'],
                aciklama=product_data['description'] or 'AliExpress kaliteli ürün',
                resim_url=product_data['image'] if product_data['image'] else None  # URL olarak kaydet (yer kaplamaz)
            )
            
            # Fiyat ekle
            Fiyat.objects.create(
                urun=urun,
                magaza=magaza,
                fiyat=product_data['price'],
                affiliate_link=affiliate_link
            )
            
            self.stdout.write(self.style.SUCCESS(f'\n✅ Ürün başarıyla eklendi!'))
            self.stdout.write(f'ID: {urun.id}')
            self.stdout.write(f'İsim: {urun.isim}')
            self.stdout.write(f'Fiyat: {product_data["price"]} TL')
            self.stdout.write(f'\nSiteye gidin: http://127.0.0.1:8000/')
            
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Bağlantı hatası: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Hata: {e}'))
            import traceback
            traceback.print_exc()

    def extract_product_info(self, soup, url):
        """AliExpress sayfasından ürün bilgilerini çek - geliştirilmiş versiyon"""
        data = {
            'title': '',
            'price': 0.0,
            'description': '',
            'image': ''
        }
        
        try:
            # 1. Script içindeki JSON verilerini bul
            scripts = soup.find_all('script')
            json_data = None
            
            for script in scripts:
                if script.string:
                    script_text = script.string
                    
                    # window.runParams veya data objesi ara
                    if 'window.runParams' in script_text or 'data:' in script_text:
                        # JSON benzeri veriyi çıkar
                        try:
                            # runParams içindeki data objesini bul
                            match = re.search(r'data:\s*({.+?})\s*[,}]', script_text, re.DOTALL)
                            if match:
                                json_str = match.group(1)
                                # Basit JSON parse dene
                                json_data = json.loads(json_str)
                                break
                        except:
                            pass
            
            # 2. Başlık çekme
            title_methods = [
                lambda: soup.select_one('h1').get_text(strip=True) if soup.select_one('h1') else None,
                lambda: soup.select_one('meta[property="og:title"]').get('content') if soup.select_one('meta[property="og:title"]') else None,
                lambda: soup.select_one('.product-title').get_text(strip=True) if soup.select_one('.product-title') else None,
            ]
            
            for method in title_methods:
                try:
                    title = method()
                    if title:
                        data['title'] = title[:200]  # Max 200 karakter
                        break
                except:
                    continue
            
            # 3. Fiyat çekme - çoklu strateji
            # Strateji A: Script içinden regex ile
            for script in scripts:
                if script.string:
                    script_text = script.string
                    
                    # Türkçe fiyat formatı (TRY, TL) - genişletilmiş patternler
                    patterns = [
                        # Standard JSON formatları
                        r'"price"["\s]*[\s:]+["\s]*(\d+[.,]\d+)"',
                        r'"salePrice"["\s]*[\s:]+["\s]*(\d+[.,]\d+)"',
                        r'"minAmount"["\s]*[\s:]+[{}\s]*"value"["\s]*[\s:]+["\s]*(\d+[.,]\d+)"',
                        r'"maxPrice"["\s]*[\s:]+["\s]*(\d+[.,]\d+)"',
                        r'"minPrice"["\s]*[\s:]+["\s]*(\d+[.,]\d+)"',
                        
                        # Currency specific
                        r'TRY["\s]*[\s:]+["\s]*(\d+[.,]\d+)',
                        r'"currency"["\s]*[\s:]+["\s]*TRY["\s]*.*?"price"["\s]*[\s:]+["\s]*(\d+[.,]\d+)',
                        
                        # ActivityPrice formatları
                        r'"activityPrice"["\s]*[\s:]+[{}\s]*"value"["\s]*[\s:]+["\s]*(\d+[.,]\d+)',
                        r'formattedPrice["\s]*[\s:]+["\']\s*[\₺TL]*\s*(\d+[.,]\d+)',
                        
                        # discountPrice formatları
                        r'"discountPrice"["\s]*[\s:]+["\s]*(\d+[.,]\d+)',
                        
                        # Basit sayısal format (3000-4000 gibi gerçekçi fiyatlar)
                        r'(\d{3,5}[.,]\d{2})["\s]*TL',
                        r'TL["\s:]*(\d{3,5}[.,]\d{2})',
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, script_text, re.IGNORECASE)
                        if matches:
                            try:
                                # Virgüllü format varsa noktaya çevir
                                price_str = matches[0].replace(',', '.')
                                price = float(price_str)
                                if 10 < price < 100000:  # Makul fiyat aralığı
                                    data['price'] = price
                                    self.stdout.write(self.style.SUCCESS(f'✓ Fiyat bulundu (pattern: {pattern[:40]}...): {price} TL'))
                                    break
                            except:
                                continue
                    
                    if data['price'] > 0:
                        break
            
            # Strateji B: Meta taglerden
            if data['price'] == 0:
                price_meta = soup.select_one('meta[property="product:price:amount"]')
                if price_meta:
                    try:
                        data['price'] = float(price_meta.get('content', '0').replace(',', '.'))
                    except:
                        pass
            
            # 4. Resim URL çekme
            image_methods = [
                lambda: soup.select_one('meta[property="og:image"]').get('content') if soup.select_one('meta[property="og:image"]') else None,
                lambda: soup.select_one('img.magnifier-image').get('src') if soup.select_one('img.magnifier-image') else None,
                lambda: soup.select_one('.images-view-item img').get('src') if soup.select_one('.images-view-item img') else None,
            ]
            
            for method in image_methods:
                try:
                    image_url = method()
                    if image_url and image_url.startswith('http'):
                        data['image'] = image_url
                        break
                except:
                    continue
            
            # 5. Açıklama çekme
            desc_methods = [
                lambda: soup.select_one('meta[name="description"]').get('content') if soup.select_one('meta[name="description"]') else None,
                lambda: soup.select_one('meta[property="og:description"]').get('content') if soup.select_one('meta[property="og:description"]') else None,
            ]
            
            for method in desc_methods:
                try:
                    desc = method()
                    if desc:
                        data['description'] = desc[:300]  # Max 300 karakter
                        break
                except:
                    continue
            
            # Fallback değerler
            if not data['title']:
                match = re.search(r'/item/(\d+)\.html', url)
                data['title'] = f'AliExpress Ürün #{match.group(1)}' if match else 'AliExpress Ürün'
            
            if data['price'] == 0:
                self.stdout.write(self.style.WARNING('⚠ Fiyat otomatik çekilemedi, varsayılan: 199.99 TL'))
                data['price'] = 199.99
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'⚠ Parse hatası: {e}'))
        
        return data
