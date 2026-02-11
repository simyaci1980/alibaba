// Log mesajlarını ekrana yazdır
function addLog(message) {
  console.log(message);
  const logsDiv = document.getElementById("logs");
  const logsSection = document.getElementById("logsSection");
  
  if (logsDiv && logsSection) {
    logsSection.style.display = "block";
    const logEntry = document.createElement("div");
    logEntry.textContent = message;
    logsDiv.appendChild(logEntry);
    logsDiv.scrollTop = logsDiv.scrollHeight;
  }
}
addLog("[Popup.js] Fetch versiyonu yüklendi!");

// Sayfa yüklendiğinde toplam ürün sayısını göster
document.addEventListener("DOMContentLoaded", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  
  try {
    const result = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const cardList = document.querySelector("#card-list");
        if (!cardList) return null;
        const cards = cardList.querySelectorAll(":scope > div");
        return cards.length;
      }
    });
    
    const count = result[0]?.result;
    const totalCountEl = document.getElementById("totalCount");
    if (totalCountEl) {
      totalCountEl.textContent = `Sayfadaki ürün sayısı: ${count ?? "-"}`;
    }
  } catch (e) {
    console.log("Ürün sayısı alınamadı:", e.message);
  }
});

document.getElementById("findBtn").addEventListener("click", async () => {
  addLog("[Popup] Buton tıklandı");
  
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  addLog(`[Popup] Aktif tab: ${tab?.id ?? "?"}`);

  const rangeStartInput = document.getElementById("rangeStart");
  const rangeEndInput = document.getElementById("rangeEnd");
  const rangeStart = rangeStartInput && rangeStartInput.value ? parseInt(rangeStartInput.value, 10) : null;
  const rangeEnd = rangeEndInput && rangeEndInput.value ? parseInt(rangeEndInput.value, 10) : null;
  
  try {
    // 1. Kartları çerçevele ve linkleri al
    const result = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        console.log("[Content] Script yüklendi");
        
        const cardList = document.querySelector("#card-list");
        console.log("[Content] #card-list bulundu:", cardList);
        
        if (!cardList) {
          return { error: "#card-list bulunamadı! AliExpress arama sayfasında mısınız?" };
        }
        
        const cards = cardList.querySelectorAll(":scope > div");
        console.log("[Content] Bulunan kart sayısı:", cards.length);
        
        if (cards.length === 0) {
          return { error: "Hiç ürün kartı bulunamadı!" };
        }
        
        // Kartları çerçevele ve tüm bilgileri topla
        const cardData = [];
        
        for (let i = 0; i < cards.length; i++) {
          const card = cards[i];
          
          // Çerçevele
          card.style.outline = "5px solid red";
          card.style.backgroundColor = "rgba(255, 0, 0, 0.1)";
          console.log(`[Content] Kart ${i + 1} çerçevelendi`);
          
          // Link
          let link = card.querySelector("a");
          if (!link) {
            link = card.querySelector("[href]");
          }
          const productLink = link && link.href ? link.href : "";
          
          // Görsel
          let img = card.querySelector("img");
          let imgUrl = "";
          if (img) {
            imgUrl = img.getAttribute("src") || img.getAttribute("data-src") || img.getAttribute("data-img") || "";
            if (imgUrl.startsWith("//")) {
              imgUrl = "https:" + imgUrl;
            }
          }
          
          // Fiyat - karttan direkt çek
          let price = "Bulunamadı";
          const priceSpan = card.querySelector('span[class*="price"]') || card.querySelector('.price');
          if (priceSpan) {
            const priceText = priceSpan.textContent.trim();
            const cleanPrice = priceText.replace('TL', '').replace('₺', '').trim();
            const formattedPrice = cleanPrice.replace(/\./g, '').replace(',', '.');
            price = formattedPrice;
          }
          
          // Başlık - karttan çek
          let title = "";
          const titleEl = card.querySelector("h1") || card.querySelector("h2") || card.querySelector("h3") || card.querySelector('[class*="title"]');
          if (titleEl) {
            title = titleEl.textContent.trim();
          }
          
          cardData.push({
            productLink,
            imageUrl: imgUrl,
            price,
            title
          });
        }
        
        console.log("[Content] Toplam kart verisi:", cardData.length);
        
        return { cardCount: cards.length, cardData };
      }
    });
    
    const data = result[0].result;
    addLog("[Popup] Sonuç alındı");
    
    if (data.error) {
      alert(data.error);
      return;
    }

    const totalCountEl = document.getElementById("totalCount");
    if (totalCountEl) {
      totalCountEl.textContent = `Sayfadaki ürün sayısı: ${data.cardCount}`;
    }
    
    if (!data.cardData || data.cardData.length === 0) {
      alert("Ürün verisi bulunamadı! Ürün kartlarının yapısı farklı olabilir.");
      addLog("[Popup] Hata: cardData boş");
      return;
    }
    
    // Ara sayfayı gizle, işleniyor mesajı göster
    document.getElementById("searchSection").style.display = "none";
    document.getElementById("resultsSection").style.display = "block";
    const progressMsg = document.getElementById("progressMsg");
    if (progressMsg) {
      progressMsg.style.display = "block";
      progressMsg.textContent = "Ürünler ana sayfadan çekiliyor... ⚡";
    }
    
    addLog("[Popup] Ana sayfa verisi işleniyor");
    
    // 2. Aralık belirle
    let startIndex = rangeStart ? Math.max(1, rangeStart) : 1;
    let endIndex = rangeEnd ? Math.max(startIndex, rangeEnd) : Math.min(20, data.cardData.length);
    startIndex = Math.min(startIndex, data.cardData.length);
    endIndex = Math.min(endIndex, data.cardData.length);

    addLog(`[Popup] Aralık: ${startIndex}-${endIndex}`);

    const results = [];
    
    // 3. Ana sayfadan çekilen verilerle sonuçları oluştur (çok hızlı!)
    for (let i = startIndex - 1; i < endIndex; i++) {
      const cardInfo = data.cardData[i];
      addLog(`[Popup] Ürün ${i + 1} işleniyor (ana sayfadan)`);
      
      const priceNum = parseFloat(cardInfo.price) || 0;
      
      results.push({
        index: i + 1,
        price: cardInfo.price,
        shippingFee: "0.00", // Ana sayfada yok, varsayılan
        totalPrice: priceNum.toFixed(2),
        shippingFrom: "Çin", // Ana sayfada yok, varsayılan
        status: 'Gönderilebiliyor ✅', // Ana sayfada yok, varsayılan
        imageUrl: cardInfo.imageUrl,
        title: cardInfo.title || "",
        description: "", // Ana sayfada yok
        productLink: cardInfo.productLink
      });
      
      // Progress güncelle
      if (progressMsg) {
        progressMsg.textContent = `İşleniyor: ${i + 1 - startIndex + 1}/${endIndex - startIndex + 1} ⚡`;
      }
      
      addLog(`[Popup] Ürün ${i + 1} tamamlandı (${cardInfo.price} TL)`);
    }
    
    addLog(`[Popup] Tüm ürünler tamamlandı. Toplam: ${results.length}`);
    
    // 4. Sonuçları göster
    showResults(results, tab, data.cardCount);
    
  } catch (error) {
    console.error("[Popup] Hata:", error);
    alert("Hata: " + error.message);
    document.getElementById("searchSection").style.display = "block";
    document.getElementById("resultsSection").style.display = "none";
  }
});

// Sonuçları popup'ta göster
let currentIndex = 0;
let allResults = [];
let currentTab = null;
let currentCardCount = 0;
let selectedResults = [];

function toCsvValue(value) {
  const text = String(value ?? "").replace(/\r?\n/g, " ");
  return `"${text.replace(/"/g, '""')}"`;
}

function buildCsv(rows) {
  const headers = [
    "index",
    "title",
    "description",
    "price",
    "shippingFee",
    "totalPrice",
    "shippingFrom",
    "status",
    "imageUrl",
    "productLink"
  ];
  
  let csv = headers.join(",") + "\r\n";
  
  for (const row of rows) {
    const line = headers.map(h => toCsvValue(row[h])).join(",");
    csv += line + "\r\n";
  }
  
  return csv;
}

function downloadCsv(content) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  
  const a = document.createElement("a");
  a.href = url;
  a.download = `aliexpress_urunler_${Date.now()}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function showResults(results, tab, cardCount) {
  allResults = results;
  currentTab = tab;
  currentCardCount = cardCount;
  currentIndex = 0;
  
  const progressMsg = document.getElementById("progressMsg");
  if (progressMsg) {
    progressMsg.style.display = "none";
  }
  
  if (results.length === 0) {
    alert("Hiç sonuç bulunamadı!");
    document.getElementById("searchSection").style.display = "block";
    document.getElementById("resultsSection").style.display = "none";
    return;
  }
  
  displayResult(0);
}

function displayResult(index) {
  if (index < 0 || index >= allResults.length) {
    return;
  }
  
  currentIndex = index;
  const result = allResults[index];
  
  const resultsList = document.getElementById("resultsList");
  const canDeliver = !result.status.includes('❌');
  
  resultsList.innerHTML = `
    <div class="result-card ${canDeliver ? 'can-deliver' : 'cannot-deliver'}">
      <h3>Ürün ${result.index} / ${currentCardCount}</h3>
      ${result.imageUrl ? `<img src="${result.imageUrl}" alt="Ürün Resmi">` : ''}
      <p><strong>Başlık:</strong> ${result.title || '-'}</p>
      <p><strong>Açıklama:</strong> ${result.description || '-'}</p>
      <p><strong>Fiyat:</strong> ${result.price} TL</p>
      <p><strong>Gönderim Ücreti:</strong> ${result.shippingFee} TL</p>
      <p><strong>Toplam:</strong> ${result.totalPrice} TL</p>
      <p><strong>Nereden:</strong> ${result.shippingFrom}</p>
      <p><strong>Durum:</strong> ${result.status}</p>
      <p><strong>Link:</strong> <a href="${result.productLink}" target="_blank">Ürüne Git</a></p>
    </div>
  `;
  
  // Buton durumlarını güncelle
  document.getElementById("prevBtn").disabled = (currentIndex === 0);
  document.getElementById("nextBtn").disabled = (currentIndex === allResults.length - 1);
}

// Butonlar
document.getElementById("prevBtn").addEventListener("click", () => {
  if (currentIndex > 0) {
    displayResult(currentIndex - 1);
  }
});

document.getElementById("nextBtn").addEventListener("click", () => {
  if (currentIndex < allResults.length - 1) {
    displayResult(currentIndex + 1);
  }
});

document.getElementById("backBtn").addEventListener("click", () => {
  document.getElementById("searchSection").style.display = "block";
  document.getElementById("resultsSection").style.display = "none";
  allResults = [];
  currentIndex = 0;
});

document.getElementById("addBtn").addEventListener("click", () => {
  if (currentIndex >= 0 && currentIndex < allResults.length) {
    const current = allResults[currentIndex];
    selectedResults.push(current);
    
    const csv = buildCsv(selectedResults);
    downloadCsv(csv);
    
    addLog(`[CSV] Ürün ${current.index} eklendi. Toplam seçili: ${selectedResults.length}`);
    alert(`Ürün ${current.index} CSV'ye eklendi! (Toplam: ${selectedResults.length})`);
  }
});
