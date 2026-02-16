from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    priority = 1.0
    changefreq = 'daily'
    protocol = 'https'

    def items(self):
        return ['anasayfa', 'urun_listesi']

    def location(self, item):
        return reverse(item)
