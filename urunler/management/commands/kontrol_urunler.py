"""
Veritabanındaki ürünlerin AliExpress sayfalarından bilgi çeken Django command
- Satın Al butonu kontrolü (Türkiye'ye gönderim)
- Gönderim yeri
- Kargo ücreti
- Ürün fiyatı
- Toplam fiyat
"""
from django.core.management.base import BaseCommand
from urunler.models import Urun, Fiyat
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import re

class Command(BaseCommand):
    help = 'AliExpress ürün bilgilerini günceller'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=5,
            help='Kontrol edilecek maksimum ürün sayısı'
        )

    def setup_driver(self):
        """Selenium driver ayarla"""
        chrome_options = Options()
        # chrome_options.add_argument('--headless')  # TEST: Tarayıcıyı göster
        chrome_options.add_argument('--start-maximized')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        driver = webdriver.Chrome(options=chrome_options)
        return driver

    def extract_price(self, text):
        """Fiyat metninden sayı çıkar (Türk ve Amerikan formatı destekler)"""
        try:
            # "86.618,79TL" veya "$70.24" veya "70636,24 ₺" gibi
            # Sadece sayıları ve ayraçları al
            numbers = re.findall(r'[\d,\.]+', text)
            if numbers:
                price_str = numbers[0]
                
                # Türk formatı mı? (86.618,79)
                if ',' in price_str and '.' in price_str:
                    # Nokta binlik ayracı, virgül ondalık
                    price_str = price_str.replace('.', '').replace(',', '.')
                elif ',' in price_str:
                    # Sadece virgül var, ondalık ayracı
                    price_str = price_str.replace(',', '.')
                # Sadece nokta varsa zaten Amerikan formatı
                
                return float(price_str)
        except Exception as e:
            self.stdout.write(f"  ⚠️  Fiyat parse hatası: {text} -> {e}")
            pass
        return None

    def check_product(self, driver, urun):
        """Tek bir ürünü kontrol et"""
        try:
            # İlk fiyat kaydını al
            fiyat = urun.fiyatlar.first()
            if not fiyat or not fiyat.affiliate_link:
                self.stdout.write(f"⏭️  {urun.isim[:40]}... - Affiliate link yok")
                return False
            
            # Sayfaya git
            driver.get(fiyat.affiliate_link)
            time.sleep(5)  # Admitad redirect + sayfa yüklenmesini bekle
            
            # Sayfanın tamamen yüklenmesini bekle
            try:
                wait = WebDriverWait(driver, 10)
                wait.until(EC.presence_of_element_located((By.ID, "root")))
            except:
                pass
            
            result = {
                'satin_al_var': False,
                'gonderim_yeri': None,
                'kargo_ucreti': 0,
                'urun_fiyati': None,
                'toplam_fiyat': None
            }
            
            # Satın Al butonu kontrolü (kullanıcı buldu)
            try:
                buy_button = driver.find_element(By.XPATH, 
                    "//*[@id='root']/div/div[1]/div/div[2]/div/div/div[6]/button[1]/span")
                result['satin_al_var'] = True
                self.stdout.write("  🔍 Satın Al butonu bulundu (yeni XPath)")
            except:
                # Fallback: eski yöntem
                try:
                    buy_button = driver.find_element(By.XPATH, 
                        "//button[contains(text(), 'Satın al') or contains(text(), 'Buy Now')]")
                    result['satin_al_var'] = True
                    self.stdout.write("  🔍 Satın Al butonu bulundu (fallback)")
                except:
                    result['satin_al_var'] = False
                    self.stdout.write("  ❌ Satın Al butonu BULUNAMADI")
            
            # Gönderim bilgisi container (kullanıcı buldu)
            try:
                shipping_container = driver.find_element(By.XPATH, 
                    "//*[@id='root']/div/div[1]/div/div[2]/div/div/div[3]/div[1]/div/div/div[1]")
                result['gonderim_yeri'] = shipping_container.text
                self.stdout.write(f"  🔍 Gönderim container: '{shipping_container.text[:50]}'")
            except:
                # Fallback
                try:
                    shipping_elem = driver.find_element(By.XPATH, 
                        "//*[contains(text(), 'gönderi') or contains(text(), 'Gönderim') or contains(text(), 'Teslimat')]")
                    result['gonderim_yeri'] = shipping_elem.text
                    self.stdout.write(f"  🔍 Gönderim fallback: '{shipping_elem.text[:50]}'")
                except:
                    self.stdout.write("  ❌ Gönderim bilgisi BULUNAMADI")
                    pass
            
            # Kargo ücreti/detay fiyat (kullanıcı buldu)
            try:
                shipping_fee_elem = driver.find_element(By.XPATH, 
                    "//*[@id='root']/div/div[1]/div/div[2]/div/div/div[3]/div[1]/div/div/div[1]/span[1]/span/strong")
                fee_text = shipping_fee_elem.text
                self.stdout.write(f"  🔍 Kargo elementi: '{fee_text}'")
                extracted_fee = self.extract_price(fee_text)
                if extracted_fee:
                    result['kargo_ucreti'] = extracted_fee
            except Exception as e:
                self.stdout.write(f"  ❌ Kargo elementi BULUNAMADI: {str(e)[:30]}")
                pass
            
            # Ürün fiyatı (kullanıcı buldu)
            try:
                price_elem = driver.find_element(By.XPATH, 
                    "//*[@id='root']/div/div[1]/div/div[1]/div[1]/div[2]/div[3]/div/span")
                price_text = price_elem.text
                self.stdout.write(f"  🔍 Fiyat elementi: '{price_text}'")
                extracted_price = self.extract_price(price_text)
                if extracted_price:
                    result['urun_fiyati'] = extracted_price
            except Exception as e:
                self.stdout.write(f"  ❌ Fiyat elementi BULUNAMADI: {str(e)[:30]}")
                # Fallback: eski yöntem
                try:
                    price_elem = driver.find_element(By.XPATH, 
                        "//*[contains(@class, 'price') or contains(@class, 'product-price')]")
                    price_text = price_elem.text
                    extracted_price = self.extract_price(price_text)
                    if extracted_price:
                        result['urun_fiyati'] = extracted_price
                        self.stdout.write(f"  🔍 Fiyat fallback: '{price_text}'")
                except:
                    pass
            
            # Veritabanını güncelle
            if result['satin_al_var']:
                fiyat.gonderim_durumu = True
                if result['gonderim_yeri']:
                    # "Fransa Teslimat'den gönderiyor" -> "Fransa"
                    yeri = result['gonderim_yeri'].split()[0]
                    fiyat.gonderim_yerinden = yeri
                if result['kargo_ucreti'] is not None:
                    fiyat.gonderim_ucreti = result['kargo_ucreti']
                if result['urun_fiyati'] is not None:
                    fiyat.fiyat = result['urun_fiyati']
                fiyat.save()
                
                status = "✅" if result['satin_al_var'] else "❌"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{status} {urun.isim[:35]}... | "
                        f"Gönderim: {result['gonderim_yeri'] or 'Bilinmiyor'} | "
                        f"Kargo: {result['kargo_ucreti']} | "
                        f"Fiyat: {result['urun_fiyati'] or 'N/A'}"
                    )
                )
                return True
            else:
                self.stdout.write(f"❌ {urun.isim[:40]}... - Satın alınamıyor/Türkiye'ye gönderim yok")
                return False
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Hata: {e}"))
            return False

    def handle(self, *args, **options):
        limit = options['limit']
        
        # Affiliate linki olan ürünleri al
        urunler = Urun.objects.filter(
            fiyatlar__affiliate_link__isnull=False
        ).distinct()[:limit]
        
        total = urunler.count()
        self.stdout.write(f"🚀 {total} ürün kontrol edilecek\n")
        
        driver = self.setup_driver()
        
        try:
            success_count = 0
            for i, urun in enumerate(urunler, 1):
                self.stdout.write(f"\n[{i}/{total}] Kontrol ediliyor...")
                if self.check_product(driver, urun):
                    success_count += 1
                time.sleep(2)  # Rate limit
            
            self.stdout.write("\n" + "="*50)
            self.stdout.write(self.style.SUCCESS(f"\n✅ Başarılı: {success_count}/{total}"))
            
        finally:
            driver.quit()
