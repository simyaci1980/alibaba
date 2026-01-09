from django.core.management.base import BaseCommand
from urunler.admitad_client import AdmitadAPI


class Command(BaseCommand):
    help = 'List websites in Admitad account (ID, name, status)'

    def handle(self, *args, **options):
        api = AdmitadAPI()
        sites = api.get_websites()
        if not sites:
            self.stdout.write(self.style.WARNING('No websites found or token missing.'))
            return

        self.stdout.write(self.style.SUCCESS(f'Found {len(sites)} websites:\n'))
        for site in sites:
            self.stdout.write(f"- ID: {site.get('id')} | Name: {site.get('name')} | Status: {site.get('status')}")
