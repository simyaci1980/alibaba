
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

// Bildirim göster
function showNotification(message) {
  const notif = document.getElementById("notification");
  if (!notif) return;
  
  notif.textContent = message;
  notif.style.display = "block";
  
  // 3 saniye sonra gizle
  setTimeout(() => {
    notif.style.display = "none";
  }, 3000);
}

addLog("[Popup.js] Yüklendi!");

document.getElementById("findBtn").addEventListener("click", async () => {
  addLog("[Popup] Buton tıklandı");
  
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  addLog(`[Popup] Aktif tab: ${tab?.id ?? "?"}`);

  const rangeStartInput = document.getElementById("rangeStart");
  const rangeEndInput = document.getElementById("rangeEnd");
  const rangeStart = rangeStartInput && rangeStartInput.value ? parseInt(rangeStartInput.value, 10) : null;
  const rangeEnd = rangeEndInput && rangeEndInput.value ? parseInt(rangeEndInput.value, 10) : null;
  
  try {
    // 1. Kartları çerçevele ve ilk kartın linkini al
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
        
        // Kartları çerçevele
        cards.forEach((card, index) => {
          card.style.outline = "5px solid red";
          card.style.backgroundColor = "rgba(255, 0, 0, 0.1)";
          console.log(`[Content] Kart ${index + 1} çerçevelendi`);
        });
        
        // Kartların linklerini ve görselini al
        const cardLinks = [];
        const cardImages = [];
        for (let i = 0; i < cards.length; i++) {
          const card = cards[i];
          
          // Farklı selector'lar dene
          let link = card.querySelector("a");
          if (!link) {
            link = card.querySelector("[href]");
          }
          if (!link) {
            // Kart yapısını debug et
            console.log(`[Content] Kart ${i + 1} HTML:`, card.innerHTML.substring(0, 200));
          }
          
          if (link && link.href) {
            cardLinks.push(link.href);
            console.log(`[Content] Kart ${i + 1} link: ${link.href.substring(0, 80)}`);
          }

          // Görseli bul
          let img = card.querySelector("img");
          let imgUrl = "";
          if (img) {
            imgUrl = img.getAttribute("src") || img.getAttribute("data-src") || img.getAttribute("data-img") || "";
            // Protokol ekle (// ile başlıyorsa)
            if (imgUrl.startsWith("//")) {
              imgUrl = "https:" + imgUrl;
            }
          }
          cardImages.push(imgUrl);
        }
        
        console.log("[Content] Toplam link sayısı:", cardLinks.length);
        
        return { cardCount: cards.length, cardLinks, cardImages };
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
    
    if (!data.cardLinks || data.cardLinks.length === 0) {
      alert("Link bulunamadı! Ürün kartlarının yapısı farklı olabilir.");
      addLog("[Popup] Hata: cardLinks boş");
      return;
    }
    
    // Ara sayfayı gizle, işleniyor mesajı göster
    document.getElementById("searchSection").style.display = "none";
    document.getElementById("resultsSection").style.display = "block";
    const progressMsg = document.getElementById("progressMsg");
    if (progressMsg) {
      progressMsg.style.display = "block";
      progressMsg.textContent = "Ürünler kontrol ediliyor...";
    }
    
    addLog("[Popup] Kontrol başladı");
    
    // 2. Aralık belirle
    let startIndex = rangeStart ? Math.max(1, rangeStart) : 1;
    let endIndex = rangeEnd ? Math.max(startIndex, rangeEnd) : Math.min(20, data.cardLinks.length);
    startIndex = Math.min(startIndex, data.cardLinks.length);
    endIndex = Math.min(endIndex, data.cardLinks.length);

    addLog(`[Popup] Aralık: ${startIndex}-${endIndex}`);

    const results = [];
    
    for (let i = startIndex - 1; i < endIndex; i++) {
      const productLink = data.cardLinks[i];
      const imageUrl = (data.cardImages && data.cardImages[i]) ? data.cardImages[i] : "";
      addLog(`[Popup] Ürün ${i + 1} işleniyor`);
      
      const newTab = await chrome.tabs.create({ url: productLink, active: false });
      
      // Her tab için bekle ve veri çek
      await new Promise((resolve) => {
        chrome.tabs.onUpdated.addListener(function listener(tabId, info) {
          if (tabId === newTab.id && info.status === 'complete') {
            chrome.tabs.onUpdated.removeListener(listener);
            
            setTimeout(async () => {
              try {
                const priceResult = await chrome.scripting.executeScript({
                  target: { tabId: newTab.id },
                  func: () => {
                    // Fiyatı çek
                    const priceSpan = document.querySelector('span[class*="price-default--current"]');
                    let price = 'Bulunamadı';
                    
                    if (priceSpan) {
                      const priceText = priceSpan.textContent.trim();
                      const cleanPrice = priceText.replace('TL', '').trim();
                      const formattedPrice = cleanPrice.replace(/\./g, '').replace(',', '.');
                      price = formattedPrice;
                    }
                    
                    // Gönderim durumunu kontrol et
                    const deliveryText = document.body.textContent;
                    const cannotDeliver = deliveryText.includes('Bu ürün adresinize gönderilemiyor');
                    
                    // Gönderim ücretini çek
                    let shippingFee = 0;
                    let shippingFrom = 'Çin';
                    
                    if (!cannotDeliver) {
                      // "Gönderim: X TL" pattern'ini ara
                      const shippingMatch = deliveryText.match(/Gönderim:\s*([\d.,]+)\s*TL/);
                      if (shippingMatch) {
                        const shippingText = shippingMatch[1];
                        const cleanShipping = shippingText.replace(/\./g, '').replace(',', '.');
                        shippingFee = parseFloat(cleanShipping) || 0;
                      }
                      
                      // "Gönderildiği yer X" pattern'ini ara
                      const originMatch = deliveryText.match(/Gönderildiği yer\s+([A-Za-z\s]+)/);
                      if (originMatch) {
                        shippingFrom = originMatch[1].trim();
                      }
                    }
                    
                    // Başlık ve açıklama çek
                    const titleEl = document.querySelector("h1") || document.querySelector('[data-pl="product-title"]') || document.querySelector('meta[property="og:title"]');
                    const title = titleEl ? (titleEl.content || titleEl.textContent || "").trim() : "";

                    const descMeta = document.querySelector('meta[name="description"]') || document.querySelector('meta[property="og:description"]');
                    const descEl = document.querySelector(".detail-desc" ) || document.querySelector(".description" );
                    const description = descMeta ? (descMeta.content || "").trim() : (descEl ? descEl.textContent.trim() : "");

                    // Toplam fiyat hesapla
                    const priceNum = parseFloat(price) || 0;
                    const totalPrice = priceNum + shippingFee;
                    
                    console.log("[Price] Fiyat:", price, "Gönderim:", shippingFee, "Toplam:", totalPrice, "Nereden:", shippingFrom);
                    
                    return { 
                      price: price, 
                      shippingFee: shippingFee.toFixed(2),
                      totalPrice: totalPrice.toFixed(2),
                      shippingFrom: shippingFrom,
                      cannotDeliver,
                      title,
                      description
                    };
                  }
                });
                
                const result = priceResult[0].result;
                results.push({
                  index: i + 1,
                  price: result.price,
                  shippingFee: result.shippingFee,
                  totalPrice: result.totalPrice,
                  shippingFrom: result.shippingFrom,
                  status: result.cannotDeliver ? 'Gönderilemiyor ❌' : 'Gönderilebiliyor ✅',
                  imageUrl: imageUrl,
                  title: result.title || "",
                  description: result.description || "",
                  productLink: productLink
                });
                
                chrome.tabs.remove(newTab.id);
                addLog(`[Popup] Ürün ${i + 1} tamamlandı`);
                resolve();
                
              } catch (error) {
                console.error(`[Popup] Ürün ${i + 1} hatası:`, error);
                chrome.tabs.remove(newTab.id);
                resolve();
              }
            }, 3000);
          }
        });
      });
    }
    
    addLog(`[Popup] Tüm ürünler tamamlandı. Toplam: ${results.length}`);
    
    // 3. Sonuçları popup'ın kendisinde göster
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
  const lines = [headers.join(",")];
  rows.forEach((r) => {
    const values = [
      r.index,
      r.title,
      r.description,
      r.price,
      r.shippingFee,
      r.totalPrice,
      r.shippingFrom,
      r.status,
      r.imageUrl,
      r.productLink
    ].map(toCsvValue);
    lines.push(values.join(","));
  });
  return lines.join("\n");
}

function downloadCsv(content) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "aliexpress-secimler.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function addCurrentToCsv() {
  if (!allResults || allResults.length === 0) {
    addLog("[CSV] Eklenebilecek ürün yok");
    return;
  }
  const current = allResults[currentIndex];
  if (!current) {
    addLog("[CSV] Ürün bulunamadı");
    return;
  }
  const exists = selectedResults.some((r) => r.index === current.index && r.productLink === current.productLink);
  if (exists) {
    addLog(`[CSV] Ürün zaten eklendi: ${current.index}`);
    showNotification("⚠️ Bu ürün zaten eklendi!");
    return;
  }
  selectedResults.push(current);
  addLog(`[CSV] Ürün eklendi: ${current.index} (Toplam: ${selectedResults.length})`);
  
  // İndir butonunu göster
  const downloadBtn = document.getElementById("downloadBtn");
  if (downloadBtn) {
    downloadBtn.style.display = "block";
  }
  
  showNotification(`✅ Ürün eklendi! (Toplam: ${selectedResults.length})`);
}

function showResults(results, tab, cardCount) {
  addLog(`[showResults] Çağrıldı. Results: ${results.length}`);
  
  allResults = results;
  currentTab = tab;
  currentCardCount = cardCount;
  currentIndex = 0;
  
  // Ara sayfayı gizle, sonuç sayfasını göster
  document.getElementById("searchSection").style.display = "none";
  document.getElementById("resultsSection").style.display = "block";
  const progressMsg = document.getElementById("progressMsg");
  if (progressMsg) {
    progressMsg.style.display = "none";
  }
  
  addLog("[showResults] Sayfalar değiştirildi");
  
  // Hemen ilk ürünü göster
  displayResult(0);
  
  // Çerçeveleri renklendir (arka planda)
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (results) => {
      const cardList = document.querySelector("#card-list");
      if (!cardList) return;
      
      const cards = cardList.querySelectorAll(":scope > div");
      
      results.forEach(result => {
        const card = cards[result.index - 1];
        if (!card) return;
        
        const cannotDeliver = result.status.includes('❌');
        if (cannotDeliver) {
          card.style.outline = "5px solid gold";
          card.style.backgroundColor = "rgba(255, 215, 0, 0.2)";
        } else {
          card.style.outline = "5px solid green";
          card.style.backgroundColor = "rgba(0, 128, 0, 0.1)";
        }
      });
    },
    args: [results]
  });
}

function displayResult(index) {
  addLog(`[displayResult] Çağrıldı. Index: ${index + 1}`);
  
  if (!allResults || allResults.length === 0) {
    console.error("[displayResult] allResults boş");
    return;
  }
  
  const result = allResults[index];
  const resultsList = document.getElementById("resultsList");
  
  if (!resultsList) {
    console.error("[displayResult] resultsList bulunamadı");
    return;
  }
  
  const isError = result.status.includes('❌');
  
  // Basit HTML oluştur
  let html = `
    <div style="padding: 15px; background: #f5f5f5; border-radius: 5px; margin: 10px 0; border: 2px solid #ddd;">
      <div style="font-weight: bold; font-size: 16px; margin-bottom: 10px;">
        #${result.index}. Ürün
      </div>
      ${result.title ? `
      <div style="margin: 6px 0; font-size: 13px;">
        <strong>Başlık:</strong> ${result.title}
      </div>
      ` : ''}
      ${result.description ? `
      <div style="margin: 6px 0; font-size: 12px; color: #555;">
        <strong>Açıklama:</strong> ${result.description}
      </div>
      ` : ''}
      ${result.imageUrl ? `
      <div style="text-align: center; margin-bottom: 10px;">
        <img src="${result.imageUrl}" alt="Ürün" style="max-width: 100%; max-height: 150px; object-fit: contain; border-radius: 4px;" />
        <div style="font-size: 11px; color: #666; word-break: break-all; margin-top: 4px;">${result.imageUrl}</div>
      </div>
      ` : ''}
      <div style="margin: 8px 0; font-size: 13px;">
        <strong>Fiyat:</strong> ${result.price} TL
      </div>
  `;
  
  if (parseFloat(result.shippingFee) > 0) {
    html += `
      <div style="margin: 8px 0; font-size: 13px;">
        <strong>Gönderim:</strong> ${result.shippingFee} TL (${result.shippingFrom})
      </div>
      <div style="margin: 8px 0; font-size: 13px;">
        <strong>Toplam:</strong> <span style="font-weight: bold; color: #dc3545;">${result.totalPrice} TL</span>
      </div>
    `;
  } else {
    html += `
      <div style="margin: 8px 0; font-size: 13px;">
        <strong>Gönderim:</strong> Ücretsiz (${result.shippingFrom})
      </div>
    `;
  }
  
  const statusColor = isError ? '#dc3545' : '#28a745';
  html += `
      <div style="margin: 8px 0; font-size: 13px;">
        <strong>Durum:</strong> <span style="color: ${statusColor};">${result.status}</span>
      </div>
    </div>
  `;
  
  resultsList.innerHTML = html;
  
  const pageInfo = document.getElementById("pageInfo");
  if (pageInfo) {
    pageInfo.textContent = `${index + 1} / ${allResults.length}`;
  }
  
  addLog(`[displayResult] Gösterildi. Ürün: ${result.index}`);
}

// Navigation butonları
document.addEventListener("DOMContentLoaded", () => {
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");
  const addBtn = document.getElementById("addBtn");
  const backBtn = document.getElementById("backBtn");
  const totalCountEl = document.getElementById("totalCount");

  // Popup açıldığında ürün sayısını göster
  (async () => {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !totalCountEl) return;
      const result = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          const cardList = document.querySelector("#card-list");
          if (!cardList) return null;
          return cardList.querySelectorAll(":scope > div").length;
        }
      });
      const count = result && result[0] ? result[0].result : null;
      totalCountEl.textContent = `Sayfadaki ürün sayısı: ${count ?? "-"}`;
    } catch (error) {
      if (totalCountEl) {
        totalCountEl.textContent = "Sayfadaki ürün sayısı: -";
      }
    }
  })();
  
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (currentIndex > 0) {
        currentIndex--;
        displayResult(currentIndex);
      }
    });
  }
  
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      if (currentIndex < allResults.length - 1) {
        currentIndex++;
        displayResult(currentIndex);
      }
    });
  }
  
  if (addBtn) {
    addBtn.addEventListener("click", () => {
      addCurrentToCsv();
    });
  }
  
  const downloadBtn = document.getElementById("downloadBtn");
  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      if (selectedResults.length === 0) {
        showNotification("⚠️ Henüz hiçbir ürün eklemedin!");
        return;
      }
      const csv = buildCsv(selectedResults);
      downloadCsv(csv);
      showNotification(`✅ CSV indirildi! (${selectedResults.length} ürün)`);
    });
  }
  
  if (backBtn) {
    backBtn.addEventListener("click", () => {
      currentIndex = 0;
      allResults = [];
      selectedResults = [];
      
      // İndir butonunu gizle
      const downloadBtn = document.getElementById("downloadBtn");
      if (downloadBtn) {
        downloadBtn.style.display = "none";
      }
      
      document.getElementById("searchSection").style.display = "block";
      document.getElementById("resultsSection").style.display = "none";
    });
  }
});

