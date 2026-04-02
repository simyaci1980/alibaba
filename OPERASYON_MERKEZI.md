# OPERASYON MERKEZI (TEK KAYNAK)

Bu dosya, gunluk operasyon ve sistem akisi icin ana referanstir.

## 1) GUNLUK STANDART AKIS

1. Kod degisikligini localde yap.
2. Sadece gerekli dosyalari commit et.
3. GitHub'a push et.
4. PythonAnywhere'de repo klasorunde pull et.
5. Web panelden Reload yap.
6. Kisa saglik kontrolu calistir.

## 2) CANLIYA AKTARIM KOMUTLARI

### Local -> GitHub

```bash
git add <dosyalar>
git commit -m "Mesaj"
git push
```

### PythonAnywhere -> Canli

```bash
cd ~/alibaba
git pull --ff-only
```

Sonra PythonAnywhere Web panelinden Reload.

## 3) VERITABANI KURALI (SQLITE)

- Canli sqlite dosyasi repo disinda tutulur.
- Pull islemi DB'yi ezmez.
- Hizli kontrol:

```bash
cd ~/alibaba
python manage.py shell -c "from urunler.models import Urun; print(Urun.objects.count())"
```

## 4) URUN IMPORT KOMUTLARI

### eBay import (kategori secimli)

```bash
python manage.py import_ebay_products "retro handheld console" --limit 30 --translate-tr --category-slug retro-handheld --category-name "Retro El Konsolu"
```

### AliExpress (Admitad CSV) import (kategori secimli)

```bash
python manage.py import_csv_products Aliexpress_WW_Basic_sample_100.csv --category-slug retro-handheld --category-name "Retro El Konsolu"
```

Not:
- category-slug teknik kimliktir.
- category-name gorunen addir.
- Slug yoksa otomatik olusturulur.

## 5) SEO HIZLI KONTROL

### Sitemap

https://www.kolaybulexpres.com/sitemap.xml

### Ilk 5 loc kontrolu

```bash
curl -s "https://www.kolaybulexpres.com/sitemap.xml" | grep -Eo '<loc>[^<]*</loc>' | head -5
```

Beklenen: Tum satirlar https://www.kolaybulexpres.com ile baslamali.

### Product JSON-LD brand kontrolu

```bash
curl -s "https://www.kolaybulexpres.com/urun/SLUG/" | tr -d '\n' | grep -Eo '"brand"[[:space:]]*:[[:space:]]*\{[^}]*\}'
```

## 6) DOKUMAN TAKIP KURALI

- Bu dosya: Ana operasyon kaynagi.
- README.md: Proje giris dokumani.
- Diger md dosyalari: Arsiv veya konu-bazli not.

Kural:
- Yeni operasyon bilgisi once bu dosyaya eklenir.
- Diger md dosyalarina sadece konuya ozel detay yazilir.

## 7) KISA HAFTALIK KONTROL

1. Search Console: tiklama, gosterim, CTR, konum
2. Index durumu: kritik URL'ler
3. Yeni urun sayisi
4. Import hata sayisi
5. Canli DB sayim kontrolu

---
Son guncelleme: 2026-04-02
