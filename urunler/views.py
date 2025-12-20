from django.shortcuts import render
from .models import Urun

def urun_listesi(request):
	urunler = Urun.objects.prefetch_related('fiyatlar__magaza').all()
	return render(request, 'urunler/urun_listesi.html', {'urunler': urunler})


from .models import Urun, Yorum
from .forms import YorumForm

def anasayfa(request):
	urunler = Urun.objects.prefetch_related('fiyatlar__magaza').all()
	yorumlar = Yorum.objects.filter(onayli=True).order_by('-eklenme_tarihi')[:10]
	form = YorumForm(request.POST or None)
	if request.method == 'POST' and form.is_valid():
		form.save()
		form = YorumForm()  # Formu temizle
	return render(request, 'urunler/anasayfa.html', {
		'urunler': urunler,
		'yorumlar': yorumlar,
		'form': form,
	})
