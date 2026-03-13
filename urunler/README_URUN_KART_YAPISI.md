# Ürün Kartı Yapısı (product card structure)

Bu projede anasayfadaki ürün kartlarının HTML yapısı aşağıdaki gibidir:

product -row-scrollable 

- **product-link** (kartın tamamı)
  - Kartı saran ana div. Her bir ürün için bir adet bulunur.
  - **product-body** (kartın üst kısmı)

    - Kartın üst bölümünü kapsar. İçinde resim ve metin alanları bulunur.
    - **product-media product-image-slider** (resim ve slider)

      - Ürün görselinin ve slider'ın bulunduğu alan.
      - **img** (ürün resmi)

        - Ürüne ait ana görsel.
      - **slider-dots** (slider noktaları)

        - Eğer birden fazla resim varsa, hangi resmin gösterildiğini belirten noktalar.
    - **product-text-scrollable** (başlık, alt başlık, açıklama)

      - Ürün başlığı, alt başlık ve açıklama metinlerinin bulunduğu kaydırılabilir alan.
  - **stores** (mağaza/fiyat kutuları, kartın alt kısmı)

    - Ürünün farklı mağazalardaki fiyat ve kargo bilgilerinin bulunduğu bölüm. Kartın alt kısmında yer alır.

---

Her bölüm, stil ve fonksiyonellik açısından ayrı ayrı özelleştirilebilir. Değişiklik yapmak için yukarıdaki hiyerarşiye göre ilgili div veya class'ı düzenleyebilirsiniz.
