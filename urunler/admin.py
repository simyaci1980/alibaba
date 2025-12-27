from django.contrib import admin
from .models import Magaza, Urun, Fiyat, UrunResim, Yorum
from .models import ClickLog

# Yorum modelini admin paneline ekle
@admin.register(Yorum)
class YorumAdmin(admin.ModelAdmin):
	list_display = ("isim", "yorum", "eklenme_tarihi")


class FiyatInline(admin.TabularInline):
	model = Fiyat
	extra = 1

class UrunResimInline(admin.TabularInline):
	model = UrunResim
	extra = 1


@admin.register(Urun)
class UrunAdmin(admin.ModelAdmin):
	list_display = ("isim", "resim_goster")
	inlines = [FiyatInline, UrunResimInline]
	readonly_fields = ("resim_goster",)

	def resim_goster(self, obj):
		if obj.resim:
			return f'<img src="{obj.resim.url}" style="max-height:80px; max-width:120px;" />'
		return "-"
	resim_goster.allow_tags = True
	resim_goster.short_description = "Resim"

@admin.register(Magaza)
class MagazaAdmin(admin.ModelAdmin):
	list_display = ("isim", "web_adresi")

@admin.register(Fiyat)
class FiyatAdmin(admin.ModelAdmin):
	list_display = ("urun", "magaza", "fiyat", "affiliate_link")
@admin.register(ClickLog)
class ClickLogAdmin(admin.ModelAdmin):
	list_display = ("id", "timestamp", "user", "link_type", "urun")
