from django.core.management.base import BaseCommand

from urunler.models import Urun


class Command(BaseCommand):
    help = "Refresh stale product slugs from current titles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ids",
            type=str,
            default="",
            help="Comma-separated product IDs to process",
        )
        parser.add_argument(
            "--source",
            type=str,
            default="",
            help="Optional source filter: ebay or aliexpress",
        )

    def handle(self, *args, **options):
        ids_raw = str(options.get("ids") or "").strip()
        source = str(options.get("source") or "").strip().lower()

        queryset = Urun.objects.order_by("id")

        if ids_raw:
            ids = [int(chunk.strip()) for chunk in ids_raw.split(",") if chunk.strip().isdigit()]
            queryset = queryset.filter(id__in=ids)

        if source == "ebay":
            queryset = queryset.filter(source_url__icontains="ebay")
        elif source == "aliexpress":
            queryset = queryset.filter(source_url__icontains="aliexpress")

        updated = 0
        for urun in queryset:
            old_slug = urun.slug
            if not urun._should_refresh_slug():
                continue
            urun.slug = urun._build_unique_slug()
            urun.save(update_fields=["slug"])
            updated += 1
            self.stdout.write(f"[{urun.id}] {old_slug} -> {urun.slug}")

        self.stdout.write(self.style.SUCCESS(f"Updated slug count: {updated}"))