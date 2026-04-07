from django.conf import settings
from django.contrib import admin
from django.core.management.base import BaseCommand

from urunler.admin import UrunAdmin
from urunler.ebay_api import EbayAPIConnector
from urunler.models import Urun


class Command(BaseCommand):
    help = "Fill missing technical specs from eBay API, page content, and product images (OCR)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max product count to process (0 = all)",
        )
        parser.add_argument(
            "--ids",
            type=str,
            default="",
            help="Comma-separated product IDs to process (example: 1,2,3)",
        )
        parser.add_argument(
            "--no-ocr",
            action="store_true",
            help="Disable OCR-based extraction from images",
        )

    def handle(self, *args, **options):
        limit = max(0, int(options.get("limit") or 0))
        ids_raw = str(options.get("ids") or "").strip()
        no_ocr = bool(options.get("no_ocr"))

        queryset = Urun.objects.select_related("kategori").prefetch_related("resimler").order_by("id")
        queryset = queryset.filter(source_url__icontains="ebay")

        if ids_raw:
            id_values = []
            for chunk in ids_raw.split(","):
                chunk = chunk.strip()
                if chunk.isdigit():
                    id_values.append(int(chunk))
            if not id_values:
                self.stdout.write(self.style.ERROR("No valid IDs in --ids"))
                return
            queryset = queryset.filter(id__in=id_values)

        if limit > 0:
            queryset = queryset[:limit]

        products = list(queryset)
        if not products:
            self.stdout.write(self.style.WARNING("No eBay products found to process."))
            return

        admin_helper = UrunAdmin(Urun, admin.site)

        connector = None
        client_id = getattr(settings, "EBAY_PRODUCTION_CLIENT_ID", None)
        client_secret = getattr(settings, "EBAY_PRODUCTION_CLIENT_SECRET", None)
        if client_id and client_secret:
            connector = EbayAPIConnector(
                client_id=client_id,
                client_secret=client_secret,
                sandbox=False,
                ship_to_country="US",
            )
            if not connector.get_oauth_token():
                connector = None
                self.stdout.write(self.style.WARNING("eBay API token could not be obtained; API step skipped."))
        else:
            self.stdout.write(self.style.WARNING("eBay API credentials missing; API step skipped."))

        processed = 0
        skipped = 0
        updated_products = 0
        updated_fields_total = 0
        key_fill_counts = {
            "model": 0,
            "ekran_boyutu": 0,
            "cozunurluk": 0,
            "cpu": 0,
            "ram": 0,
            "depolama": 0,
            "batarya": 0,
            "baglanti": 0,
            "wifi": 0,
            "bluetooth": 0,
            "usb_c": 0,
            "isletim_sistemi": 0,
            "hdmi": 0,
            "gonderim_yeri": 0,
        }

        for urun in products:
            processed += 1
            missing_keys = admin_helper._get_missing_schema_keys(urun)
            if not missing_keys:
                skipped += 1
                self.stdout.write(f"[{urun.id}] Skipped (no missing schema keys)")
                continue

            merged = {}

            def merge_payload(incoming):
                for key, value in (incoming or {}).items():
                    clean_val = str(value or "").strip()
                    if not clean_val:
                        continue
                    if key not in merged:
                        merged[key] = clean_val

            # 1) eBay API aspects
            if connector:
                item_id = str(getattr(urun, "item_id", "") or "").strip() or admin_helper._extract_ebay_item_id(urun.source_url)
                if item_id:
                    try:
                        details = connector.get_item_details(item_id)
                        api_mapped = admin_helper._map_aspects_to_detaylar((details or {}).get("localizedAspects") or [])
                        merge_payload(api_mapped)
                    except Exception:
                        pass

            # 2) Source page HTML + seller description
            html_text = admin_helper._fetch_html(urun.source_url)
            if html_text:
                html_mapped = admin_helper._map_html_specs_to_detaylar(html_text)
                merge_payload(html_mapped)

                desc_assets = admin_helper._extract_seller_description_assets(html_text, urun.source_url)
                desc_text = desc_assets.get("text", "")
                if desc_text:
                    text_mapped = admin_helper._map_ocr_text_to_detaylar(desc_text, target_keys=missing_keys)
                    merge_payload(text_mapped)

                if not no_ocr:
                    desc_images = desc_assets.get("image_urls", [])
                    if desc_images:
                        desc_img_mapped, _desc_img_meta = admin_helper._map_ocr_from_known_urls(
                            desc_images,
                            urun.source_url,
                            target_keys=missing_keys,
                        )
                        merge_payload(desc_img_mapped)

                    page_ocr_mapped, _page_ocr_meta = admin_helper._map_ocr_images_to_detaylar(
                        html_text,
                        urun.source_url,
                        target_keys=missing_keys,
                    )
                    merge_payload(page_ocr_mapped)

            # 3) Saved description text + known product images
            saved_desc = str(getattr(urun, "aciklama", "") or "").strip()
            if saved_desc:
                saved_text_mapped = admin_helper._map_ocr_text_to_detaylar(saved_desc, target_keys=missing_keys)
                merge_payload(saved_text_mapped)

            if not no_ocr:
                known_image_urls = admin_helper._collect_product_image_urls(urun)
                if known_image_urls:
                    known_img_mapped, _known_img_meta = admin_helper._map_ocr_from_known_urls(
                        known_image_urls,
                        urun.source_url,
                        target_keys=missing_keys,
                    )
                    merge_payload(known_img_mapped)

            details = dict(urun.detaylar or {})
            product_updates = []
            for key in missing_keys:
                current_val = str(details.get(key, "") or "").strip()
                if current_val and current_val.lower() != "belirtilmemiş":
                    continue
                incoming_val = str(merged.get(key, "") or "").strip()
                if not incoming_val:
                    continue
                details[key] = incoming_val
                product_updates.append((key, incoming_val))

            if product_updates:
                urun.detaylar = details
                urun.save(update_fields=["detaylar"])
                updated_products += 1
                updated_fields_total += len(product_updates)
                for key, _ in product_updates:
                    if key in key_fill_counts:
                        key_fill_counts[key] += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[{urun.id}] Updated {len(product_updates)} fields: "
                        + ", ".join([f"{k}={v}" for k, v in product_updates[:5]])
                    )
                )
            else:
                self.stdout.write(f"[{urun.id}] No new values found")

        self.stdout.write("\n=== FILL SUMMARY ===")
        self.stdout.write(f"Processed: {processed}")
        self.stdout.write(f"Skipped (already full): {skipped}")
        self.stdout.write(self.style.SUCCESS(f"Updated products: {updated_products}"))
        self.stdout.write(self.style.SUCCESS(f"Updated fields total: {updated_fields_total}"))
        self.stdout.write("Filled by key:")
        for key, count in key_fill_counts.items():
            self.stdout.write(f"  {key}: {count}")
