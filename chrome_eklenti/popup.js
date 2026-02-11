    // Tümünü Temizle butonu
    document.getElementById('clear-all').onclick = function() {
        if (!confirm('Tüm ürünleri silmek istediğinize emin misiniz?')) return;
        chrome.storage.local.remove('urunler', function() {
            document.getElementById('ekle-bilgi').innerText = 'Tüm ürünler silindi!';
            setTimeout(()=>{document.getElementById('ekle-bilgi').innerText = ''}, 2000);
        });
    };
let currentProduct = null;

document.addEventListener('DOMContentLoaded', function() {
    // Ürün bilgilerini çek
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
        chrome.scripting.executeScript({
            target: { tabId: tabs[0].id },
            func: function() {
                let name = document.querySelector('h1, .product-title, [itemprop="name"]')?.innerText || '';
                let price = document.querySelector('.price, [itemprop="price"], .product-price')?.innerText || '';
                // Resim URL çekme mantığı (önce meta, sonra img)
                let image = '';
                let metaOgImage = document.querySelector('meta[property="og:image"]');
                if (metaOgImage && metaOgImage.content) {
                    image = metaOgImage.content;
                } else {
                    let img1 = document.querySelector('img.magnifier-image');
                    if (img1 && img1.src) image = img1.src;
                    else {
                        let img2 = document.querySelector('.images-view-item img');
                        if (img2 && img2.src) image = img2.src;
                        else {
                            let img3 = document.querySelector('img, .product-image img, [itemprop="image"]');
                            if (img3 && img3.src) image = img3.src;
                        }
                    }
                }
                let url = window.location.href;
                // Sadece https://tr.aliexpress.com/item/ID.html kısmını al
                let urlMatch = url.match(/https:\/\/tr\.aliexpress\.com\/item\/\d+\.html/);
                if (urlMatch) url = urlMatch[0];
                return { name, price, image, url };
            }
        }, (results) => {
            if (results && results[0] && results[0].result) {
                currentProduct = results[0].result;
                let html = '';
                if (currentProduct.image) {
                    html += `<img src="${currentProduct.image}" alt="Ürün Resmi" style="max-width:80px; max-height:80px; display:block; margin-bottom:8px;"/>`;
                    html += `<div><b>Resim URL:</b> <a href="${currentProduct.image}" target="_blank" style="word-break:break-all;">${currentProduct.image}</a></div>`;
                }
                if (currentProduct.name) html += `<div><b>Ad:</b> ${currentProduct.name}</div>`;
                if (currentProduct.price) html += `<div><b>Fiyat:</b> ${currentProduct.price}</div>`;
                html += `<div><b>Sayfa URL:</b> <a href="${currentProduct.url}" target="_blank" style="word-break:break-all;">${currentProduct.url}</a></div>`;
                document.getElementById('product-info').innerHTML = html;
            } else {
                document.getElementById('product-info').innerText = 'Ürün bilgisi bulunamadı.';
            }
        });
    });

    // Ürünü ekle butonu
    document.getElementById('add-product').onclick = function() {
        if (!currentProduct) {
            document.getElementById('ekle-bilgi').innerText = 'Ürün bilgisi alınamadı!';
            setTimeout(()=>{document.getElementById('ekle-bilgi').innerText = ''}, 1500);
            return;
        }
        // Manuel fiyat kontrolü
        const manualPrice = document.getElementById('manual-price').value;
        let productToSave = { ...currentProduct };
        if (manualPrice && !isNaN(manualPrice)) {
            productToSave.price = manualPrice;
        }
        chrome.storage.local.get({urunler: []}, function(result) {
            const urunler = result.urunler;
            urunler.push(productToSave);
            chrome.storage.local.set({urunler: urunler}, function() {
                document.getElementById('ekle-bilgi').innerText = 'Ürün eklendi! (Toplam: ' + urunler.length + ')';
                setTimeout(()=>{document.getElementById('ekle-bilgi').innerText = ''}, 1500);
            });
        });
    };

    // CSV olarak indir butonu
    document.getElementById('download-csv').onclick = function() {
        chrome.storage.local.get({urunler: []}, function(result) {
            const urunler = result.urunler;
            if (!urunler.length) {
                document.getElementById('ekle-bilgi').innerText = 'Henüz eklenmiş ürün yok!';
                setTimeout(()=>{document.getElementById('ekle-bilgi').innerText = ''}, 1500);
                return;
            }
            let csv = 'Ad,Fiyat,Resim,URL\n';
            // Sadece ürün adı tırnaklanacak, diğer alanlar sade kalacak
            let escape = v => `"${String(v).replace(/"/g, '""')}"`;
            csv += urunler.map(u => [
                escape(u.name),
                u.price,
                u.image,
                u.url
            ].join(',')).join('\n');
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'urunler.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            document.getElementById('ekle-bilgi').innerText = 'CSV indirildi!';
            setTimeout(()=>{document.getElementById('ekle-bilgi').innerText = ''}, 1500);
        });
    };
});
