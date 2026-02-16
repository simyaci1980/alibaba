"""
CSV dosyasındaki ürün isimlerini Türkçeye çeviren script
"""
import csv
import time
from deep_translator import GoogleTranslator

def translate_csv(input_file, output_file, max_rows=100):
    """
    CSV dosyasındaki 'name' sütununu Türkçeye çevir
    
    Args:
        input_file: Kaynak CSV dosyası
        output_file: Hedef CSV dosyası
        max_rows: Maksimum çevrilecek satır sayısı (test için)
    """
    translator = GoogleTranslator(source='en', target='tr')
    
    with open(input_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8', newline='') as outfile:
        
        reader = csv.DictReader(infile, delimiter=';')
        fieldnames = reader.fieldnames
        writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=';', quoting=csv.QUOTE_ALL)
        writer.writeheader()
        
        count = 0
        for row in reader:
            if count >= max_rows:
                print(f"\n✓ {max_rows} satır çevrildi. Durduruldu.")
                break
            
            try:
                # Ürün adını çevir
                original_name = row['name']
                if original_name and len(original_name.strip()) > 0:
                    # Uzun metinleri parçalara böl (Google limit: 5000 karakter)
                    if len(original_name) > 500:
                        original_name = original_name[:500]
                    
                    translated = translator.translate(original_name)
                    row['name'] = translated
                    print(f"{count+1}. {original_name[:40]}... → {translated[:40]}...")
                
                writer.writerow(row)
                count += 1
                
                # Rate limit için bekleme (her 10 satırda)
                if count % 10 == 0:
                    time.sleep(0.5)
                    
            except Exception as e:
                print(f"Hata (satır {count+1}): {e}")
                writer.writerow(row)  # Hatalı satırı olduğu gibi yaz
                count += 1
                time.sleep(2)

if __name__ == "__main__":
    input_file = r"c:\Users\ab111777\Desktop\alibaba\Aliexpress-sample.csv"
    output_file = r"c:\Users\ab111777\Desktop\alibaba\Aliexpress-TURKCE.csv"
    
    print("🚀 Çeviri başlıyor...")
    print(f"📥 Kaynak: {input_file}")
    print(f"📤 Hedef: {output_file}")
    print(f"⚠️  İlk 100 satır çevrilecek (test)\n")
    
    translate_csv(input_file, output_file, max_rows=100)
    
    print(f"\n✅ Tamamlandı! Türkçe CSV: {output_file}")
