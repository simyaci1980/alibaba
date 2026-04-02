import csv
import json
import random
import re
import string

from decouple import config
from django.core.management.base import BaseCommand

from urunler.models import Fiyat, KategoriSema, Magaza, Urun, UrunResim
from urunler.utils.deeplink import build_admitad_deeplink


RETRO_HANDHELD_SCHEMA = [
    {"key": "marka", "label": "Marka", "zorunlu": False, "kaynak": "csv"},
    {"key": "model", "label": "Model", "zorunlu": False, "kaynak": "csv"},
    {"key": "ekran_boyutu", "label": "Ekran Boyutu", "zorunlu": True, "kaynak": "csv"},
    {"key": "cozunurluk", "label": "Çözünürlük", "zorunlu": True, "kaynak": "csv"},
    {"key": "cpu", "label": "İşlemci", "zorunlu": False, "kaynak": "csv"},
    {"key": "ram", "label": "RAM", "zorunlu": False, "kaynak": "csv"},
    {"key": "depolama", "label": "Depolama", "zorunlu": False, "kaynak": "csv"},
    {"key": "batarya", "label": "Batarya", "zorunlu": False, "kaynak": "csv"},
    {"key": "baglanti", "label": "Bağlantı", "zorunlu": False, "kaynak": "csv"},
    {"key": "isletim_sistemi", "label": "İşletim Sistemi", "zorunlu": False, "kaynak": "csv"},
    {"key": "hdmi", "label": "HDMI Çıkışı", "zorunlu": False, "kaynak": "csv"},
    {"key": "gonderim_yeri", "label": "Gönderim Yeri", "zorunlu": False, "kaynak": "csv"},
]


DETAIL_COLUMN_MAP = {
    "Marka": "marka",
    "Model": "model",
    "Ekran Boyutu": "ekran_boyutu",
    "Çözünürlük": "cozunurluk",
    "CPU": "cpu",
    "RAM": "ram",
    "Depolama": "depolama",
    "Batarya": "batarya",
    "Bağlantı": "baglanti",
    "İşletim Sistemi": "isletim_sistemi",
    "HDMI Çıkışı": "hdmi",
    "Gönderim Yeri": "gonderim_yeri",
}


class Command(BaseCommand):
    help = "CSV dosyasından AliExpress ürünlerini kategori/detay alanlarıyla içe aktarır"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="CSV dosyasının yolu")
        parser.add_argument("--subid", type=str, default="auto", help="Tracking için subid")
        parser.add_argument(
            "--category-slug",
            type=str,
            default="retro-handheld",
            help="Ürünlerin atanacağı kategori slug'ı (varsayılan: retro-handheld)",
        )
        parser.add_argument(
            "--category-name",
            type=str,
            default="Retro El Konsolu",
            help="Kategori yoksa oluşturulacak ad (varsayılan: Retro El Konsolu)",
        )

    def generate_unique_code(self, length=5):
        while True:
            code = "".join(random.choices(string.digits, k=length))
            if not Urun.objects.filter(urun_kodu=code).exists():
                return code

    def get_first(self, row, *keys, default=""):
        for key in keys:
            if key in row and row.get(key) not in (None, ""):
                return row.get(key)
        return default

    def parse_float(self, value, default=0.0):
        raw = str(value or "").strip()
        if not raw:
            return default
        raw = raw.replace("₺", "").replace("TL", "").strip()
        if "," in raw and "." in raw:
            if raw.rfind(",") > raw.rfind("."):
                raw = raw.replace(".", "").replace(",", ".")
            else:
                raw = raw.replace(",", "")
        elif "," in raw:
            raw = raw.replace(",", ".")
        match = re.search(r"-?\d+(?:\.\d+)?", raw)
        if not match:
            return default
        try:
            return float(match.group(0))
        except ValueError:
            return default

    def parse_json_value(self, value, fallback):
        raw = str(value or "").strip()
        if not raw:
            return fallback
        try:
            return json.loads(raw)
        except Exception:
            return fallback

    def normalize_url(self, url):
        normalized = str(url or "").strip()
        if not normalized:
            return ""
        if normalized.startswith("//"):
            normalized = f"https:{normalized}"
        normalized = re.sub(r"^https:///+", "https://", normalized)
        normalized = re.sub(r"^http:///+", "http://", normalized)
        return normalized

    def normalize_shipping_status(self, value):
        text = str(value or "").strip()
        lower_text = text.lower()
        if "gönderilemiyor" in lower_text or "gonderilemiyor" in lower_text:
            return "Gönderilemiyor ❌", False
        if "gönderilebiliyor" in lower_text or "gonderilebiliyor" in lower_text:
            return "Gönderilebiliyor ✅", True
        if "✅" in text:
            return "Gönderilebiliyor ✅", True
        if "❌" in text:
            return "Gönderilemiyor ❌", False
        return (text or "Gönderilebiliyor ✅"), True

    def is_low_value_text(self, text):
        normalized = str(text or "").strip()
        if not normalized:
            return True
        lower_text = normalized.lower()
        bad_markers = [
            "daha fazla görüntüle",
            "daha fazla göster",
            "show more",
            "show less",
            "see more",
            "aliexpress'den",
            "aliexpressden",
            "dünya çapında ücretsiz gönderimin keyfini çıkarın",
            "sınırlı süreli indirim",
            "kolay iade",
            "ürün bulun",
        ]
        if any(marker in lower_text for marker in bad_markers):
            return True
        if len(normalized) < 25:
            return True
        return False

    def ensure_target_kategori(self, slug, name):
        category_slug = str(slug or "retro-handheld").strip().lower() or "retro-handheld"
        category_name = str(name or "").strip() or category_slug.replace("-", " ").title()

        kategori = KategoriSema.objects.filter(slug=category_slug).first()
        if not kategori:
            return KategoriSema.objects.create(
                slug=category_slug,
                isim=category_name,
                alanlar=RETRO_HANDHELD_SCHEMA,
                aktif=True,
            )

        updated_fields = []
        if category_name and kategori.isim != category_name:
            kategori.isim = category_name
            updated_fields.append("isim")
        if not kategori.alanlar:
            kategori.alanlar = RETRO_HANDHELD_SCHEMA
            updated_fields.append("alanlar")
        if not kategori.aktif:
            kategori.aktif = True
            updated_fields.append("aktif")

        if updated_fields:
            kategori.save(update_fields=updated_fields)
        return kategori

    def build_detaylar(self, row, shipping_from):
        detaylar = {}

        detail_specs = self.parse_json_value(row.get("Detay Specs JSON"), {})
        if isinstance(detail_specs, dict):
            for key, value in detail_specs.items():
                if value in (None, ""):
                    continue
                detaylar[str(key).strip()] = str(value).strip()

        for csv_key, hedef_key in DETAIL_COLUMN_MAP.items():
            value = str(row.get(csv_key) or "").strip()
            if value:
                detaylar[hedef_key] = value

        if shipping_from and not detaylar.get("gonderim_yeri"):
            detaylar["gonderim_yeri"] = shipping_from

        if detaylar.get("hdmi_cikisi") and not detaylar.get("hdmi"):
            detaylar["hdmi"] = detaylar["hdmi_cikisi"]
        if detaylar.get("hdmi") and not detaylar.get("hdmi_cikisi"):
            detaylar["hdmi_cikisi"] = detaylar["hdmi"]

        spec_pairs = self.parse_json_value(row.get("Spec Pairs JSON"), [])
        if isinstance(spec_pairs, list) and spec_pairs:
            detaylar["spec_pairs"] = spec_pairs

        spec_table = self.parse_json_value(row.get("Spec Table JSON"), [])
        if isinstance(spec_table, list) and spec_table:
            detaylar["spec_table"] = spec_table

        for meta_key, csv_key in [
            ("ham_ozellikler", "Ham Özellikler"),
            ("genel_bakis", "Genel Bakış"),
            ("urun_aciklama_metni", "Ürün Açıklama Metni"),
            ("tl1_icerik", "TL1 İçerik"),
        ]:
            value = str(row.get(csv_key) or "").strip()
            if value:
                detaylar[meta_key] = value

        return detaylar

    def build_ozellikler(self, row, detaylar, shipping_from, shipping_fee, category_name="Retro El Konsolu"):
        lines = []
        seen = set()

        raw_specs = str(row.get("Ham Özellikler") or "").strip()
        if raw_specs:
            for piece in raw_specs.split("|"):
                line = piece.strip()
                if not line:
                    continue
                sig = line.lower()
                if sig in seen:
                    continue
                seen.add(sig)
                lines.append(line)

        if not lines:
            features = str(row.get("Özellikler") or "").strip()
            for piece in features.split(","):
                line = piece.strip()
                if not line:
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    line = f"{key.strip()}: {value.strip()}"
                sig = line.lower()
                if sig in seen:
                    continue
                seen.add(sig)
                lines.append(line)

        kategori_satiri = f"Kategori: {category_name}"
        if kategori_satiri.lower() not in seen:
            lines.append(kategori_satiri)

        if shipping_from:
            ship_line = f"Gönderim Yeri: {shipping_from}"
            if ship_line.lower() not in seen:
                lines.append(ship_line)

        cargo_line = "Kargo: Ücretsiz" if shipping_fee <= 0 else f"Kargo: {shipping_fee:.2f} TL"
        if cargo_line.lower() not in seen:
            lines.append(cargo_line)

        if not lines:
            for key in ["marka", "model", "ekran_boyutu", "cozunurluk", "cpu", "ram", "depolama", "batarya", "baglanti", "isletim_sistemi", "hdmi", "gonderim_yeri"]:
                value = str(detaylar.get(key) or "").strip()
                if value:
                    label = key.replace("_", " ").title()
                    lines.append(f"{label}: {value}")

        return "\n".join(lines)[:5000]

    def build_aciklama(self, row, category_name="Retro El Konsolu"):
        pieces = []
        for key in ["Ürün Açıklama Metni", "TL1 İçerik", "Açıklama"]:
            value = str(row.get(key) or "").strip()
            if value and not self.is_low_value_text(value) and value not in pieces:
                pieces.append(value)
        if pieces:
            return "\n\n".join(pieces)[:5000]
        return f"Kategori: {category_name}"

    def build_gallery_urls(self, row, primary_image_url):
        urls = []
        if primary_image_url:
            urls.append(primary_image_url)

        multi_urls = str(row.get("Tüm Resim URL'leri") or "").strip()
        if multi_urls:
            for part in multi_urls.split("|"):
                url = self.normalize_url(part)
                if url and url not in urls:
                    urls.append(url)
        return urls

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        subid = options["subid"]
        category_slug = options["category_slug"]
        category_name = options["category_name"]
        base_link = config("ADMITAD_BASE_LINK", default="")
        if not base_link:
            self.stdout.write(self.style.ERROR("❌ ADMITAD_BASE_LINK eksik"))
            return

        magaza, _ = Magaza.objects.get_or_create(
            isim="AliExpress",
            defaults={"web_adresi": "https://www.aliexpress.com"},
        )
        target_kategori = self.ensure_target_kategori(category_slug, category_name)

        with open(csv_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    name = str(self.get_first(row, "Başlık", "title", "Ad", default="")).strip()
                    if not name:
                        raise ValueError("Başlık boş")

                    description = self.build_aciklama(row, category_name=target_kategori.isim)
                    ana_baslik = str(self.get_first(row, "Ana Başlık", "ana_baslik", default=name)).strip() or name
                    alt_baslik = str(self.get_first(row, "Alt Başlık", "alt_baslik", default="")).strip()
                    etiketler = str(self.get_first(row, "Etiketler", "etiketler", default="")).strip()

                    shipping_from = str(self.get_first(row, "Gönderim Yeri", "shippingFrom", default="Çin")).strip() or "Çin"
                    detaylar = self.build_detaylar(row, shipping_from)
                    price_str = self.get_first(row, "Fiyat", "price", "Toplam Fiyat", "totalPrice", default="0")
                    price = self.parse_float(price_str, default=0.0)

                    shipping_fee_str = self.get_first(row, "Gönderim Ücreti", "shippingFee", default="0")
                    shipping_fee = self.parse_float(shipping_fee_str, default=0.0)

                    ozellikler = self.build_ozellikler(
                        row,
                        detaylar,
                        shipping_from,
                        shipping_fee,
                        category_name=target_kategori.isim,
                    )

                    shipping_status_raw = self.get_first(row, "Durum", "status", "Gönderim Durumu", default="Gönderilebiliyor ✅")
                    shipping_status, can_deliver = self.normalize_shipping_status(shipping_status_raw)

                    image_url = self.normalize_url(self.get_first(row, "Resim URL", "imageUrl", "Resim", default=""))
                    product_url = self.normalize_url(self.get_first(row, "Link", "productLink", "URL", default=""))
                    gallery_urls = self.build_gallery_urls(row, image_url)

                    urun = None
                    if product_url:
                        urun = Urun.objects.filter(source_url=product_url).first()

                    if not urun and name and image_url:
                        urun = Urun.objects.filter(isim__iexact=name, resim_url=image_url).first()

                    if not urun and name:
                        urun = Urun.objects.filter(isim__iexact=name).first()

                    mevcut_detaylar = dict(getattr(urun, "detaylar", {}) or {}) if urun else {}
                    birlesik_detaylar = {**mevcut_detaylar, **detaylar}

                    created = False
                    if urun:
                        if not urun.urun_kodu:
                            urun.urun_kodu = self.generate_unique_code()
                        urun.isim = name or urun.isim
                        urun.aciklama = description or urun.aciklama
                        urun.ana_baslik = ana_baslik or urun.ana_baslik
                        urun.alt_baslik = alt_baslik or urun.alt_baslik
                        urun.etiketler = etiketler or urun.etiketler
                        urun.ozellikler = ozellikler or urun.ozellikler
                        urun.kategori = target_kategori
                        urun.detaylar = birlesik_detaylar
                        urun.durum = shipping_status or urun.durum
                        urun.resim_url = image_url or urun.resim_url
                        if product_url:
                            urun.source_url = product_url
                        urun.save()
                    else:
                        urun = Urun.objects.create(
                            isim=name,
                            aciklama=description,
                            ana_baslik=ana_baslik,
                            alt_baslik=alt_baslik,
                            etiketler=etiketler,
                            ozellikler=ozellikler,
                            kategori=target_kategori,
                            detaylar=birlesik_detaylar,
                            durum=shipping_status or "Gönderilebiliyor ✅",
                            resim_url=image_url or None,
                            source_url=product_url or None,
                            urun_kodu=self.generate_unique_code(),
                        )
                        created = True

                    deeplink_subid = urun.urun_kodu if subid == "auto" else subid
                    affiliate_link = build_admitad_deeplink(
                        base_link=base_link,
                        product_url=product_url,
                        subid=deeplink_subid,
                    )

                    Fiyat.objects.update_or_create(
                        urun=urun,
                        magaza=magaza,
                        defaults={
                            "fiyat": round(price, 2),
                            "para_birimi": "TL",
                            "affiliate_link": affiliate_link,
                            "gonderim_ucreti": round(shipping_fee, 2),
                            "gonderim_yerinden": shipping_from,
                            "gonderim_durumu": can_deliver,
                            "ucretsiz_kargo": shipping_fee <= 0,
                        },
                    )

                    if gallery_urls:
                        for index, url in enumerate(gallery_urls):
                            UrunResim.objects.get_or_create(
                                urun=urun,
                                resim_url=url,
                                defaults={"sira": index},
                            )

                    toplam = price + shipping_fee
                    if created:
                        self.stdout.write(self.style.SUCCESS(
                            f"✓ {name[:50]} eklendi (Fiyat: {price:.2f} + Gönderim: {shipping_fee:.2f} = {toplam:.2f} TL, Kod: {urun.urun_kodu})"
                        ))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"⚠ {name[:50]} zaten vardı, güncellendi (Fiyat: {price:.2f} + Gönderim: {shipping_fee:.2f} = {toplam:.2f} TL, Kod: {urun.urun_kodu})"
                        ))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f"❌ Hata: {row.get('Başlık') or row.get('title') or row.get('Ad') or 'Bilinmiyor'} - {e}"
                    ))
