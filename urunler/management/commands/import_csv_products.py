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
    {"key": "wifi", "label": "Wi-Fi", "zorunlu": False, "kaynak": "csv"},
    {"key": "bluetooth", "label": "Bluetooth", "zorunlu": False, "kaynak": "csv"},
    {"key": "usb_c", "label": "USB-C", "zorunlu": False, "kaynak": "csv"},
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
    "Connectivity": "baglanti",
    "Wi-Fi": "wifi",
    "Bluetooth": "bluetooth",
    "USB-C": "usb_c",
    "İşletim Sistemi": "isletim_sistemi",
    "Operating System": "isletim_sistemi",
    "HDMI Çıkışı": "hdmi",
    "HDMI Output": "hdmi",
    "Gönderim Yeri": "gonderim_yeri",
    "Ships From": "gonderim_yeri",
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
        raw = raw.replace("₺", "").replace("TL", "").replace("TRY", "").replace("$", "").replace("USD", "").replace("€", "").replace("EUR", "").replace("£", "").replace("GBP", "").strip()
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
        if "cannot ship" in lower_text or "can't ship" in lower_text or "can not ship" in lower_text:
            return "Gönderilemiyor ❌", False
        if "gönderilebiliyor" in lower_text or "gonderilebiliyor" in lower_text:
            return "Gönderilebiliyor ✅", True
        if "can ship" in lower_text:
            return "Gönderilebiliyor ✅", True
        if "✅" in text:
            return "Gönderilebiliyor ✅", True
        if "❌" in text:
            return "Gönderilemiyor ❌", False
        return (text or "Gönderilebiliyor ✅"), True

    def normalize_currency(self, value, default="USD"):
        raw = str(value or "").strip().upper()
        if not raw:
            return default
        if raw in {"$", "US$", "USD"}:
            return "USD"
        if raw in {"₺", "TL", "TRY"}:
            return "TRY"
        if raw in {"€", "EUR"}:
            return "EUR"
        if raw in {"£", "GBP"}:
            return "GBP"
        return raw

    def collect_row_text(self, row, extra_parts=None):
        parts = [
            self.get_first(row, "Başlık", "title", default=""),
            self.get_first(row, "Ana Başlık", "anaTitle", default=""),
            self.get_first(row, "Özellikler", "features", default=""),
            self.get_first(row, "Açıklama", "description", default=""),
            self.get_first(row, "Genel Bakış", "overviewContent", default=""),
            self.get_first(row, "Ürün Açıklama Metni", "navDescContent", default=""),
            self.get_first(row, "TL1 İçerik", "tl1Content", default=""),
            self.get_first(row, "Ham Özellikler", default=""),
        ]
        if extra_parts:
            parts.extend(extra_parts)
        return "\n".join(str(part or "") for part in parts if str(part or "").strip())

    def first_spec_pair_value(self, spec_pairs, key_tokens):
        tokens = [str(token or "").strip().lower() for token in key_tokens]
        for pair in spec_pairs or []:
            if not isinstance(pair, dict):
                continue
            key = str(pair.get("key") or "").strip().lower()
            value = str(pair.get("value") or "").strip()
            if key and value and any(token in key for token in tokens):
                return value
        return ""

    def infer_model_from_text(self, text):
        normalized = str(text or "").replace("Ⅱ", "2").replace("III", "3")
        patterns = [
            r"\b(R36MAX\w*)\b",
            r"\b(R36S)\b",
            r"\b(X55)\b",
            r"\b(M26\s*Ultra)\b",
            r"\b(M27)\b",
            r"\b(M26)\b",
            r"\b(Trimui\s+Smart\s+Pro)\b",
            r"\b(Miyoo\s+Mini\s+Plus)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                return re.sub(r"\s+", " ", match.group(1)).strip()
        return ""

    def clean_product_title(self, value):
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return ""
        text = re.sub(r"^buy\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+at\s+aliexpress.*$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+for\s*\.?\s*find more.*$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*\|\s*AliExpress.*$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^AliExpress\s*[-:|]?\s*", "", text, flags=re.IGNORECASE)
        return text.strip(" -|")

    def is_generic_product_title(self, value):
        normalized = re.sub(r"\s+", " ", str(value or "")).strip().lower()
        return not normalized or normalized in {"aliexpress", "buy at aliexpress"} or len(normalized) < 8

    def infer_display_title(self, row, detaylar):
        title_candidates = [
            self.get_first(row, "Başlık", "title", "Ad", default=""),
            self.get_first(row, "Ana Başlık", "ana_baslik", "anaTitle", default=""),
            self.get_first(row, "Açıklama", "description", default=""),
            self.get_first(row, "Ürün Açıklama Metni", "navDescContent", default=""),
            self.get_first(row, "Genel Bakış", "overviewContent", default=""),
        ]
        for candidate in title_candidates:
            cleaned = self.clean_product_title(candidate)
            if cleaned and not self.is_generic_product_title(cleaned):
                return cleaned

        brand = str(detaylar.get("marka") or "").strip()
        model = str(detaylar.get("model") or "").strip()
        if brand and model:
            return f"{brand} {model}".strip()
        if model:
            return model
        if brand:
            return brand
        return ""

    def infer_ram_from_text(self, text, model=""):
        source = str(text or "")
        explicit = re.search(r"\b(\d+\s*(?:GB|MB)\s*(?:RAM|LPDDR\dX?|DDR\d))\b", source, re.IGNORECASE)
        if explicit:
            return re.sub(r"\s+", "", explicit.group(1).upper())

        memory_type = re.search(r"\b(LPDDR\dX?|DDR\d)\b", source, re.IGNORECASE)
        if memory_type:
            mem = memory_type.group(1).upper()
            model_norm = str(model or "").strip().lower()
            if model_norm == "x55":
                return f"1GB {mem}"
            return mem
        return ""

    def infer_cpu_from_text(self, text, model=""):
        source = str(text or "")
        patterns = [
            r"\b(RK\d{4})\b",
            r"\b(Allwinner\s*[A-Z0-9]+)\b",
            r"\b(Snapdragon\s*[A-Z0-9]+)\b",
            r"\b(Helio\s*[A-Z0-9]+)\b",
            r"\b(Unisoc\s*[A-Z0-9]+)\b",
            r"\b(Cortex-[A-Z0-9]+)\b",
            r"\b(A\d{3,4}P?)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, source, re.IGNORECASE)
            if match:
                return re.sub(r"\s+", " ", match.group(1)).strip()

        model_norm = str(model or "").strip().lower()
        known_fallbacks = {
            "x55": "RK3566",
        }
        return known_fallbacks.get(model_norm, "")

    def normalize_screen_size(self, value):
        text = str(value or "").strip()
        match = re.search(r"(\d+(?:[\.,]\d+)?)", text)
        if not match:
            return text
        return f'{match.group(1).replace(",", ".")}"'

    def normalize_resolution(self, value):
        text = str(value or "").strip().replace("*", "x").replace(" ", "")
        match = re.search(r"(\d{3,5}x\d{3,5})", text, re.IGNORECASE)
        return match.group(1).lower() if match else text

    def normalize_storage(self, value):
        text = str(value or "").strip()
        match = re.search(r"(\d{1,4})\s*(TB|GB|MB|G)\b", text, re.IGNORECASE)
        if not match:
            return text
        unit = match.group(2).upper()
        if unit == "G":
            unit = "GB"
        return f"{match.group(1)}{unit}"

    def normalize_battery(self, value):
        text = str(value or "").strip()
        match = re.search(r"(\d{3,6})\s*(mAh)?", text, re.IGNORECASE)
        if not match:
            return text
        return f"{match.group(1)}mAh"

    def normalize_os(self, value):
        text = str(value or "").strip()
        lower_text = text.lower()
        if "linux" in lower_text:
            return "Linux"
        if "android" in lower_text:
            return "Android"
        return text

    def detect_yes_no(self, values, keyword_pattern):
        text = " ".join(str(value or "") for value in values).lower()
        if not text.strip():
            return ""
        if re.search(keyword_pattern, text):
            return "Yes"
        if re.search(r"\b(no|false|hayir|hayır)\b", text):
            return "No"
        return ""

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
        else:
            existing_keys = {str(item.get("key") or "").strip() for item in kategori.alanlar if isinstance(item, dict)}
            missing_items = [item for item in RETRO_HANDHELD_SCHEMA if item["key"] not in existing_keys]
            if missing_items:
                kategori.alanlar = list(kategori.alanlar) + missing_items
                updated_fields.append("alanlar")
        if not kategori.aktif:
            kategori.aktif = True
            updated_fields.append("aktif")

        if updated_fields:
            kategori.save(update_fields=updated_fields)
        return kategori

    def build_detaylar(self, row, shipping_from):
        detaylar = {}

        def normalize_yes_no(value, positive_tokens, negative_tokens=None):
            text = str(value or "").strip()
            if not text:
                return ""
            norm = text.lower()
            negatives = set(negative_tokens or ["no", "hayir", "hayır", "yok", "none", "false"])
            if any(token in norm for token in negatives):
                return "No"
            if any(token in norm for token in positive_tokens):
                return "Yes"
            return ""

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

        bluetooth_candidate = detaylar.get("bluetooth") or detaylar.get("baglanti")
        bluetooth_normalized = normalize_yes_no(
            bluetooth_candidate,
            positive_tokens=["bluetooth", "bt", "yes", "evet", "true", "compatible"],
        )
        if bluetooth_normalized:
            detaylar["bluetooth"] = bluetooth_normalized

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

        inference_text = self.collect_row_text(row, extra_parts=[
            json.dumps(spec_pairs, ensure_ascii=False) if spec_pairs else "",
            json.dumps(spec_table, ensure_ascii=False) if spec_table else "",
        ])

        if not detaylar.get("model"):
            inferred_model = self.infer_model_from_text(inference_text)
            if inferred_model:
                detaylar["model"] = inferred_model

        if not detaylar.get("ram"):
            inferred_ram = self.infer_ram_from_text(inference_text, model=detaylar.get("model"))
            if inferred_ram:
                detaylar["ram"] = inferred_ram

        if not detaylar.get("cpu"):
            inferred_cpu = self.infer_cpu_from_text(inference_text, model=detaylar.get("model"))
            if inferred_cpu:
                detaylar["cpu"] = inferred_cpu

        if not detaylar.get("hdmi"):
            inferred_hdmi = self.first_spec_pair_value(spec_pairs, ["hdmi", "input/output"])
            if inferred_hdmi:
                detaylar["hdmi"] = inferred_hdmi

        wifi_values = [
            detaylar.get("wifi"),
            detaylar.get("baglanti"),
            self.first_spec_pair_value(spec_pairs, ["wifi", "wireless"]),
        ]
        bluetooth_values = [
            detaylar.get("bluetooth"),
            detaylar.get("baglanti"),
            self.first_spec_pair_value(spec_pairs, ["bluetooth", "communication"]),
        ]
        usb_values = [
            detaylar.get("usb_c"),
            detaylar.get("baglanti"),
            self.first_spec_pair_value(spec_pairs, ["usb", "type-c", "charging interface", "external controller interface"]),
        ]

        wifi_normalized = self.detect_yes_no(wifi_values, r"\b(wifi|wi-fi|802\.11|wireless|yes|true|evet)\b")
        bluetooth_normalized = self.detect_yes_no(bluetooth_values, r"\b(bluetooth|yes|true|evet|compatible)\b")
        usb_normalized = self.detect_yes_no(usb_values, r"\b(usb-c|type-c|usb c|type c|yes|true|evet)\b")

        if wifi_normalized:
            detaylar["wifi"] = wifi_normalized
        if bluetooth_normalized:
            detaylar["bluetooth"] = bluetooth_normalized
        if usb_normalized:
            detaylar["usb_c"] = usb_normalized

        normalized_baglanti = []
        if detaylar.get("wifi") == "Yes":
            normalized_baglanti.append("Wi-Fi")
        if detaylar.get("bluetooth") == "Yes":
            normalized_baglanti.append("Bluetooth")
        if detaylar.get("usb_c") == "Yes":
            normalized_baglanti.append("USB-C")
        if str(detaylar.get("hdmi") or detaylar.get("hdmi_cikisi") or "").strip():
            normalized_baglanti.append("HDMI")
        if normalized_baglanti:
            detaylar["baglanti"] = ", ".join(normalized_baglanti)

        detaylar["ekran_boyutu"] = self.normalize_screen_size(detaylar.get("ekran_boyutu"))
        detaylar["cozunurluk"] = self.normalize_resolution(detaylar.get("cozunurluk"))
        detaylar["depolama"] = self.normalize_storage(detaylar.get("depolama"))
        detaylar["batarya"] = self.normalize_battery(detaylar.get("batarya"))
        detaylar["isletim_sistemi"] = self.normalize_os(detaylar.get("isletim_sistemi"))

        if shipping_from and not detaylar.get("gonderim_yeri"):
            detaylar["gonderim_yeri"] = shipping_from

        if detaylar.get("hdmi_cikisi") and not detaylar.get("hdmi"):
            detaylar["hdmi"] = detaylar["hdmi_cikisi"]
        if detaylar.get("hdmi") and not detaylar.get("hdmi_cikisi"):
            detaylar["hdmi_cikisi"] = detaylar["hdmi"]

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
                    detaylar = self.build_detaylar(row, str(self.get_first(row, "Gönderim Yeri", "Ships From", "shippingFrom", default="China")).strip() or "China")
                    inferred_title = self.infer_display_title(row, detaylar)
                    if self.is_generic_product_title(name) and inferred_title:
                        name = inferred_title
                    ana_baslik = str(self.get_first(row, "Ana Başlık", "ana_baslik", default=name)).strip() or name
                    if self.is_generic_product_title(ana_baslik) and inferred_title:
                        ana_baslik = inferred_title
                    alt_baslik = str(self.get_first(row, "Alt Başlık", "alt_baslik", default="")).strip()
                    etiketler = str(self.get_first(row, "Etiketler", "etiketler", default="")).strip()

                    shipping_from = str(self.get_first(row, "Gönderim Yeri", "Ships From", "shippingFrom", default="China")).strip() or "China"
                    price_str = self.get_first(row, "Fiyat", "price", "Toplam Fiyat", "totalPrice", default="0")
                    price = self.parse_float(price_str, default=0.0)
                    currency = self.normalize_currency(self.get_first(row, "Para Birimi", "Currency", "currencyCode", default="USD"), default="USD")

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

                    generic_names = {
                        "aliexpress",
                        "product",
                        "item",
                    }
                    can_use_name_matching = bool(name) and name.strip().lower() not in generic_names

                    if not urun and can_use_name_matching and image_url:
                        urun = Urun.objects.filter(isim__iexact=name, resim_url=image_url).first()

                    # Sadece isimle eşleme, genel başlıklar (örn. "Aliexpress")
                    # çok sayıda ürünü tek kayda düşürdüğü için kaldırıldı.

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
                            "para_birimi": currency,
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
                            f"✓ {name[:50]} eklendi (Fiyat: {price:.2f} + Gönderim: {shipping_fee:.2f} = {toplam:.2f} {currency}, Kod: {urun.urun_kodu})"
                        ))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"⚠ {name[:50]} zaten vardı, güncellendi (Fiyat: {price:.2f} + Gönderim: {shipping_fee:.2f} = {toplam:.2f} {currency}, Kod: {urun.urun_kodu})"
                        ))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f"❌ Hata: {row.get('Başlık') or row.get('title') or row.get('Ad') or 'Bilinmiyor'} - {e}"
                    ))
