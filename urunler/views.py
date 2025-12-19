from django.shortcuts import render
from .models import Urun

def urun_listesi(request):
	urunler = Urun.objects.prefetch_related('fiyatlar__magaza').all()
	return render(request, 'urunler/urun_listesi.html', {'urunler': urunler})


def anasayfa(request):
	from .models import Urun
	urunler = Urun.objects.prefetch_related('fiyatlar__magaza').all()
	return render(request, 'urunler/anasayfa.html', {'urunler': urunler})
