def aliexpress_redirect(request):
	ClickLog.objects.create(
		user=request.user if request.user.is_authenticated else None,
		link_type='aliexpress',
		timestamp=timezone.now()
	)
	return redirect('https://rzekl.com/g/1e8d114494454bdb5abc16525dc3e8/')
from django.shortcuts import render, redirect
from .models import Urun, ClickLog, Yorum
from django.utils import timezone

def urun_listesi(request):
	urunler = Urun.objects.prefetch_related('fiyatlar__magaza').all()
	return render(request, 'urunler/urun_listesi.html', {'urunler': urunler})


def amazon_redirect(request):
	ClickLog.objects.create(
		user=request.user if request.user.is_authenticated else None,
		link_type='amazon',
		timestamp=timezone.now()
	)
	return redirect('https://www.amazon.com/b?node=53629917011&linkCode=ll2&tag=kolaybulekspr-20&linkId=8150ea1ccd7fe92bfd1f94652a6d69e4&language=en_US&ref_=as_li_ss_tl')


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
