
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

function setRunStatus(message, tone = "info") {
  const el = document.getElementById("runStatus");
  if (!el) return;
  el.textContent = `Durum: ${message}`;
  if (tone === "ok") {
    el.style.background = "#dcfce7";
    el.style.color = "#166534";
    el.style.borderColor = "#86efac";
  } else if (tone === "warn") {
    el.style.background = "#fef3c7";
    el.style.color = "#92400e";
    el.style.borderColor = "#fcd34d";
  } else if (tone === "error") {
    el.style.background = "#fee2e2";
    el.style.color = "#991b1b";
    el.style.borderColor = "#fca5a5";
  } else {
    el.style.background = "#eef2f7";
    el.style.color = "#334155";
    el.style.borderColor = "#dbe3ec";
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function getPageProductCount(maxAttempts = 8, delayMs = 450) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return null;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const result = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        // AliExpress kart yapisi: div.nl_nm (sayfa basi maksimum 60)
        const cards = document.querySelectorAll("div.nl_nm");
        return { count: Math.min(cards.length, 60), source: "div.nl_nm" };
      }
    });

    const payload = result && result[0] ? result[0].result : null;
    const count = payload && typeof payload.count === "number" ? payload.count : 0;
    if (count > 0) {
      return count;
    }

    if (attempt < maxAttempts) {
      await sleep(delayMs);
    }
  }

  return 0;
}

addLog("[Popup.js] Yüklendi!");

document.getElementById("findBtn").addEventListener("click", async () => {
  addLog("[Popup] Buton tıklandı");
  setRunStatus("Islem baslatildi", "info");
  
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  addLog(`[Popup] Aktif tab: ${tab?.id ?? "?"}`);

  const rangeStartInput = document.getElementById("rangeStart");
  const rangeEndInput = document.getElementById("rangeEnd");
  const rangeWarning = document.getElementById("rangeWarning");
  const rangeStart = rangeStartInput && rangeStartInput.value ? parseInt(rangeStartInput.value, 10) : null;
  const rangeEnd = rangeEndInput && rangeEndInput.value ? parseInt(rangeEndInput.value, 10) : null;

  if (rangeWarning) {
    rangeWarning.style.display = "none";
  }

  if (!rangeStart || !rangeEnd) {
    if (rangeWarning) {
      rangeWarning.style.display = "block";
    }
    alert("Lutfen baslangic ve bitis araligini giriniz! Ornek: 1-20");
    addLog("[Popup] Hata: Aralik girilmedi");
    setRunStatus("Aralik bekleniyor", "warn");
    return;
  }
  
  try {
    // 1. Kartları çerçevele ve ilk kartın linkini al
    const result = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        console.log("[Content] Script yüklendi");
        
        function findProductCards() {
          const containerSelectors = [
            "#card-list",
            ".search-card-list",
            "[class*='search-card']",
            "[class*='list--gallery']",
            "[data-spm*='search']"
          ];

          for (const selector of containerSelectors) {
            const container = document.querySelector(selector);
            if (!container) continue;
            const items = container.querySelectorAll(":scope > div, :scope > li, [data-product-id], [class*='search-card-item']");
            if (items && items.length > 0) {
              return Array.from(items);
            }
          }

          const fallback = document.querySelectorAll("a[href*='/item/']");
          const cards = [];
          fallback.forEach((a) => {
            const card = a.closest("div, li");
            if (card) cards.push(card);
          });
          return cards;
        }

        const cards = findProductCards();
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
        
        // Kartlarin linklerini ve gorsellerini ayni kayitta tut
        const cardItems = [];
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
            const item = { link: link.href, imageUrl: "" };
            console.log(`[Content] Kart ${i + 1} link: ${link.href.substring(0, 80)}`);

            // Ayni karttaki ana gorseli bul
            let img = card.querySelector("img");
            let imgUrl = "";
            if (img) {
              imgUrl = img.getAttribute("src") || img.getAttribute("data-src") || img.getAttribute("data-img") || "";
              if (imgUrl.startsWith("//")) {
                imgUrl = "https:" + imgUrl;
              }
            }
            item.imageUrl = imgUrl;
            cardItems.push(item);
          }
        }
        
        console.log("[Content] Toplam islenebilir kart sayisi:", cardItems.length);
        
        return { cardCount: cards.length, cardItems };
      }
    });
    
    const data = result[0].result;
    addLog("[Popup] Sonuç alındı");
    
    if (data.error) {
      alert(data.error);
      setRunStatus("Urun listesi bulunamadi", "error");
      return;
    }

    const totalCountEl = document.getElementById("totalCount");
    if (totalCountEl) {
      totalCountEl.textContent = `Sayfadaki ürün sayısı: ${data.cardCount}`;
    }
    
    if (!data.cardItems || data.cardItems.length === 0) {
      alert("Link bulunamadı! Ürün kartlarının yapısı farklı olabilir.");
      addLog("[Popup] Hata: cardItems bos");
      setRunStatus("Link bulunamadi", "error");
      return;
    }
    
    // Ara sayfayı gizle, işleniyor mesajı göster
    document.getElementById("searchSection").style.display = "none";
    document.getElementById("resultsSection").style.display = "block";
    
    addLog("[Popup] Kontrol başladı");
    setRunStatus("Urunler taraniyor...", "info");
    
    // Aralığı valide et
    let startIndex = Math.max(1, rangeStart);
    let endIndex = Math.max(startIndex, rangeEnd);
    startIndex = Math.min(startIndex, data.cardItems.length);
    endIndex = Math.min(endIndex, data.cardItems.length);

    addLog(`[Popup] Aralık: ${startIndex}-${endIndex}`);
    
    // progressMsg'i güncelle
    const progressMsg = document.getElementById("progressMsg");
    if (progressMsg) {
      progressMsg.style.display = "block";
      progressMsg.textContent = `Ürünler kontrol ediliyor (${startIndex}-${endIndex})...`;
    }

    const results = [];
    
    for (let i = startIndex - 1; i < endIndex; i++) {
      const visualIndex = i + 1;
      const doneCount = i - (startIndex - 1);
      const cardItem = data.cardItems[i] || {};
      const productLink = cardItem.link;
      const imageUrl = cardItem.imageUrl || "";
      addLog(`[Popup] Ürün ${i + 1} işleniyor`);
      setRunStatus(`Urun ${visualIndex} isleniyor (${doneCount}/${endIndex - startIndex + 1} tamamlandi)`, "info");
      if (progressMsg) {
        progressMsg.textContent = `Isleniyor: urun ${visualIndex} (${doneCount}/${endIndex - startIndex + 1} tamamlandi)`;
      }
      
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
                    let description = descMeta ? (descMeta.content || "").trim() : (descEl ? descEl.textContent.trim() : "");

                    // #tl_1 metinlerini (urun aciklamasi) description'a ekle ve ayri tut
                    let tl1Content = "";
                    const tl1El = document.getElementById("tl_1");
                    if (tl1El) {
                      const tl1Text = (tl1El.textContent || "").trim();
                      if (tl1Text) {
                        tl1Content = tl1Text;
                        if (!description.includes(tl1Text)) {
                          description = description ? `${description}\n\n${tl1Text}` : tl1Text;
                        }
                      }
                    }

                    // Urun aciklama metnini birden fazla bilinen selector'dan cek, en uzun icerigi sec
                    let navDescContent = "";
                    const SKIP_LINES = new Set([
                      "daha fazla görüntüle", "daha fazla gör", "show more", "show less",
                      "daha az görüntüle", "see more", "see less", "load more", "devamını gör",
                      "tümünü gör", "see all", "view more"
                    ]);

                    function extractTextFromEl(el) {
                      if (!el) return "";
                      const lines = [];
                      const walker = document.createTreeWalker(
                        el,
                        NodeFilter.SHOW_TEXT,
                        {
                          acceptNode(node) {
                            const parent = node.parentElement;
                            if (!parent) return NodeFilter.FILTER_REJECT;
                            const tag = parent.tagName.toLowerCase();
                            if (["img", "script", "style", "noscript"].includes(tag)) return NodeFilter.FILTER_REJECT;
                            const text = node.textContent.trim();
                            const lower = text.toLowerCase();
                            // buton metinlerini atla
                            if (SKIP_LINES.has(lower)) return NodeFilter.FILTER_REJECT;
                            return text ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
                          }
                        }
                      );
                      let node;
                      while ((node = walker.nextNode())) {
                        const line = node.textContent.trim();
                        if (line) lines.push(line);
                      }
                      return lines.join("\n");
                    }

                    // Bilinen AliExpress description selector'lari (en uzun icerigi sececegiz)
                    const DESC_SELECTORS = [
                      "#product-description .detail-desc-decorate-richtext",
                      "#product-description .description-origin-content",
                      "#product-description .product-description-content",
                      "#product-description .html-content",
                      "#product-description .description-content",
                      "#product-description > div > div > div",
                      "#product-description > div > div",
                      "#nav-description .detail-desc-decorate-richtext",
                      "#nav-description .description-origin-content",
                      "#nav-description > div:nth-child(2) > div",
                      "#nav-description > div:nth-child(2)",
                      ".product-description-richtext",
                      ".description-wrap",
                    ];

                    let bestText = "";
                    for (const sel of DESC_SELECTORS) {
                      const el = document.querySelector(sel);
                      if (!el) continue;
                      const text = extractTextFromEl(el);
                      if (text.length > bestText.length) bestText = text;
                    }
                    navDescContent = bestText;

                    // Genel Bakis (Overview) bolumunden metin cek
                    let overviewContent = "";
                    const OVERVIEW_SELECTORS = [
                      "#nav-overview .tab-page-section",
                      "#nav-overview > div",
                      "#nav-overview",
                      ".product-overview-content",
                      ".pdp-overview",
                      "[data-pl='product-overview']",
                      ".overview-wrap",
                      ".product-highlights",
                      ".product-keypoints",
                      ".key-feature-list",
                    ];
                    let bestOverview = "";
                    for (const sel of OVERVIEW_SELECTORS) {
                      const el = document.querySelector(sel);
                      if (!el) continue;
                      const text = extractTextFromEl(el);
                      if (text.length > bestOverview.length) bestOverview = text;
                    }
                    overviewContent = bestOverview;

                    // Urun galeri resimleri: sadece belirli DOM yolundan cek
                    // XPath: //*[@id="root"]/div/div[1]/div/div[1]/div[1]/div[1]/div/div/div[1]/div/div/div[N]/div/img
                    function getProductImages() {
                      function norm(url) {
                        if (!url) return "";
                        let u = String(url).trim();
                        if (!u || u.startsWith("data:")) return "";
                        if (u.startsWith("//")) u = "https:" + u;
                        return u;
                      }

                      // CSS karsiligi: #root > div > div:first-child > div > div:first-child > div:first-child > div:first-child > div > div > div:first-child
                      const root = document.getElementById("root");
                      if (!root) return [];

                      try {
                        const container =
                          root
                            .children[0]
                            ?.children[0]
                            ?.children[0]
                            ?.children[0]
                            ?.children[0]
                            ?.children[0]
                            ?.children[0]
                            ?.children[0]
                            ?.children[0];

                        if (!container) return [];

                        // container > div > div > div[N] > div > img
                        const innerWrap = container.children[0]?.children[0];
                        if (!innerWrap) return [];

                        const seen = new Set();
                        const urls = [];
                        Array.from(innerWrap.children).forEach((slot) => {
                          const img = slot.querySelector("div > img") || slot.querySelector("img");
                          if (!img) return;
                          const src = norm(img.getAttribute("src") || img.getAttribute("data-src") || "");
                          if (!src) return;
                          // Thumbnail suffix'ini kaldir ve tekrari engelle
                          const canonical = src.replace(/(\.(?:jpg|jpeg|png|webp))_[^/?#]+$/i, "$1").split("?")[0];
                          if (seen.has(canonical)) return;
                          seen.add(canonical);
                          urls.push(canonical);
                        });
                        return urls;
                      } catch (e) {
                        return [];
                      }
                    }

                    const imageUrls = getProductImages().slice(0, 20);

                    // Ozellikler tablosu çek (button tıkla ve açılan tabloyu oku)
                    function getSpecificationTable() {
                      const tableRows = [];
                      try {
                        const navSpec = document.getElementById("nav-specification");
                        if (!navSpec) return tableRows;

                        // Button'a tıkla ("Daha Fazla Göster" gibi)
                        const btn = navSpec.querySelector("button span")?.parentElement;
                        if (btn) {
                          btn.click();
                          // DOM güncellenmesi için kısa bekle
                          const wait = new Promise((r) => setTimeout(r, 300));
                          // Ama bu senkron değil, bu yüzden direkt devam et
                        }

                        // Tablo satırlarını oku (yapı: tr > td çiftleri)
                        const table = navSpec.querySelector("table");
                        if (!table) return tableRows;

                        const rows = table.querySelectorAll("tbody > tr");
                        rows.forEach((tr) => {
                          const tds = tr.querySelectorAll("td");
                          if (tds.length >= 2) {
                            const key = (tds[0]?.textContent || "").trim();
                            const value = (tds[1]?.textContent || "").trim();
                            if (key) {
                              tableRows.push({ key, value });
                            }
                          }
                        });
                      } catch (e) {
                        // Tablo çikabilme başarısız
                      }
                      return tableRows;
                    }

                    const specTable = getSpecificationTable();

                    // Teknik alanları metinden + nav-specification listesinden çıkar
                    const fullText = `${title}\n${description}\n${deliveryText}`;

                    function pick(regex) {
                      const m = fullText.match(regex);
                      return m ? m[0].trim() : "";
                    }

                    function normalizeSpecKey(key) {
                      return String(key || "")
                        .toLowerCase()
                        .normalize("NFD")
                        .replace(/[\u0300-\u036f]/g, "")
                        .replace(/[^a-z0-9]+/g, " ")
                        .trim();
                    }

                    function parseSpecificationPairs() {
                      const root = document.querySelector("#nav-specification ul");
                      if (!root) return [];

                      const pairs = [];
                      const seen = new Set();
                      const rows = root.querySelectorAll("li");

                      function cleanText(s) {
                        return String(s || "").replace(/\s+/g, " ").trim();
                      }

                      function addPair(key, value) {
                        if (!key || !value) return;
                        const dedupeKey = `${normalizeSpecKey(key)}::${String(value).toLowerCase()}`;
                        if (!seen.has(dedupeKey)) {
                          seen.add(dedupeKey);
                          pairs.push({ key, value });
                        }
                      }

                      rows.forEach((li) => {
                        // Her li icinde birden fazla div blogu olabilir.
                        // div:nth-child(1) > div:nth-child(1)=baslik, div:nth-child(2)=deger
                        // div:nth-child(2) > div:nth-child(1)=baslik, div:nth-child(2)=deger  ... vs.
                        const blocks = li.querySelectorAll(":scope > div");
                        let parsedFromBlocks = false;

                        blocks.forEach((block) => {
                          const k = cleanText(block.querySelector(":scope > div:nth-child(1)")?.textContent || "");
                          const v = cleanText(block.querySelector(":scope > div:nth-child(2)")?.textContent || "");
                          if (k && v) {
                            addPair(k, v);
                            parsedFromBlocks = true;
                          }
                        });

                        if (parsedFromBlocks) return;

                        // Fallback 1: class tabanli seciciler.
                        {
                          const keyNode   = li.querySelector('.attr-name, .spec-item-name, [class*="name"]');
                          const valueNode = li.querySelector('.attr-value, .spec-item-value, [class*="value"]');
                          const k = cleanText(keyNode?.textContent   || "");
                          const v = cleanText(valueNode?.textContent || "");
                          if (k && v) { addPair(k, v); return; }
                        }

                        // Fallback 2: span siralamasindan key/value.
                        {
                          const spans = Array.from(li.querySelectorAll("span"))
                            .map((el) => cleanText(el.textContent || ""))
                            .filter(Boolean);
                          if (spans.length >= 2) { addPair(spans[0], spans.slice(1).join(" ")); return; }
                        }

                        // Son fallback: ':' ile ayrilan satir metni.
                        {
                          const raw = cleanText(li.textContent || "");
                          const firstColon = raw.indexOf(":");
                          if (firstColon > 0) {
                            addPair(cleanText(raw.slice(0, firstColon)), cleanText(raw.slice(firstColon + 1)));
                          }
                        }
                      });

                      return pairs;
                    }

                    function findSpecValue(specPairs, keySynonyms) {
                      const normalizedSynonyms = keySynonyms.map((k) => normalizeSpecKey(k));
                      for (const pair of specPairs) {
                        const k = normalizeSpecKey(pair.key);
                        if (normalizedSynonyms.some((syn) => k === syn || k.includes(syn) || syn.includes(k))) {
                          return String(pair.value || "").trim();
                        }
                      }
                      return "";
                    }

                    const specPairs = parseSpecificationPairs();

                    const brandCandidates = ['AYANEO', 'ANBERNIC', 'POWKIDDY', 'RETROID', 'MIYOO', 'TRIMUI'];
                    let brand = '';
                    for (const b of brandCandidates) {
                      if (fullText.toUpperCase().includes(b)) {
                        brand = b;
                        break;
                      }
                    }

                    let model = '';
                    if (brand) {
                      const modelRegex = new RegExp(`${brand}\\s+([A-Za-z0-9\\-+ ]{2,40})`, 'i');
                      const mm = title.match(modelRegex);
                      if (mm && mm[1]) model = mm[1].trim();
                    }

                    const specMarka = findSpecValue(specPairs, ["Marka adı", "Brand Name", "Marka"]);
                    const specModel = findSpecValue(specPairs, ["Model"]);
                    const specEkranBoyutu = findSpecValue(specPairs, ["Ekran Boyutu", "Screen Size"]);
                    const specCozunurluk = findSpecValue(specPairs, ["Ekran Çözünürlüğü", "Ekran Cozunurlugu", "Screen Resolution", "Çözünürlük", "Cozunurluk"]);
                    const specRam = findSpecValue(specPairs, ["RAM"]);
                    const specDepolama = findSpecValue(specPairs, ["Veri depolama kapasitesi", "Data Storage Capacity", "Genişletilebilir depolama", "Expandable storage", "Depolama"]);
                    const specBatarya = findSpecValue(specPairs, ["Pil Kapasitesi[mAh]", "Battery Capacity[mAh]", "Batarya", "Pil"]);
                    const specCpu = findSpecValue(specPairs, ["CPU", "İşlemci", "Islemci", "SoC", "Chipset"]);
                    const specBaglanti = findSpecValue(specPairs, ["Harici Denetleyici Arayüzü", "External Controller Interface", "Bağlantı", "Baglanti", "Şarj arayüzü türü", "Sarj arayuzu turu"]);
                    const specIsletimSistemi = findSpecValue(specPairs, ["İşletim sistemi", "Isletim sistemi", "Operating System"]);
                    const specHdmi = findSpecValue(specPairs, ["HDMI", "HDMI Çıkışı", "HDMI Cikisi"]);

                    const detailSpecs = {
                      marka: specMarka || brand || '',
                      model: specModel || model || '',
                      ekran_boyutu: specEkranBoyutu || pick(/\b\d{1,2}(?:[.,]\d{1,2})?\s*(?:inc|inch|\")\b/i),
                      cozunurluk: specCozunurluk || pick(/\b\d{3,4}\s*[xX]\s*\d{3,4}\b|\b\d{3,4}p\b/i),
                      ram: specRam || pick(/\b\d{1,2}\s*GB\s*RAM\b|\bRAM\s*\d{1,2}\s*GB\b/i),
                      depolama: specDepolama || pick(/\b\d{2,4}\s*(?:GB|TB)\s*(?:ROM|Storage|Depolama)?\b/i),
                      batarya: specBatarya || pick(/\b\d{3,5}\s*mAh\b/i),
                      cpu: specCpu || pick(/\b(?:MTK|Snapdragon|Unisoc|Allwinner|RK\d{3,4}|Helio\s*[A-Z0-9]+)\b/i),
                      baglanti: specBaglanti || '',
                      isletim_sistemi: specIsletimSistemi || '',
                      hdmi_cikisi: specHdmi || '',
                      gonderim_yeri: shippingFrom || ''
                    };

                    const featureFromSpecs = Object.entries(detailSpecs)
                      .filter(([, value]) => value)
                      .map(([key, value]) => `${key}=${value}`);
                    const featureFromPairs = specPairs.map((p) => `${p.key}=${p.value}`);
                    const features = Array.from(new Set([...featureFromSpecs, ...featureFromPairs])).join(', ');

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
                      description,
                      imageUrls,
                      detailSpecs,
                      specPairs,
                      specTable,
                      tl1Content,
                      navDescContent,
                      overviewContent,
                      features
                    };
                  }
                });
                
                const result = priceResult[0].result;
                // Oncelik urun detay sayfasindan cekilen gorsellerde olsun.
                const detailImages = Array.isArray(result.imageUrls) ? result.imageUrls : [];
                const mergedImageUrls = Array.from(new Set([
                  ...detailImages,
                  imageUrl
                ].filter(Boolean)));

                results.push({
                  index: i + 1,
                  price: result.price,
                  shippingFee: result.shippingFee,
                  totalPrice: result.totalPrice,
                  shippingFrom: result.shippingFrom,
                  status: result.cannotDeliver ? 'Gönderilemiyor âŒ' : 'Gönderilebiliyor âœ…',
                  imageUrl: mergedImageUrls[0] || imageUrl,
                  imageUrls: mergedImageUrls,
                  title: result.title || "",
                  description: result.description || "",
                  tl1Content: result.tl1Content || "",
                  navDescContent: result.navDescContent || "",
                  overviewContent: result.overviewContent || "",
                  specPairs: result.specPairs || [],
                  specTable: result.specTable || [],
                  features: result.features || "",
                  detailSpecs: result.detailSpecs || {},
                  productLink: productLink
                });
                
                chrome.tabs.remove(newTab.id);
                addLog(`[Popup] Ürün ${i + 1} tamamlandı`);
                if (progressMsg) {
                  const nowDone = doneCount + 1;
                  progressMsg.textContent = `Tamamlandi: urun ${visualIndex} (${nowDone}/${endIndex - startIndex + 1})`;
                }
                resolve();
                
              } catch (error) {
                console.error(`[Popup] Ürün ${i + 1} hatası:`, error);
                chrome.tabs.remove(newTab.id);
                if (progressMsg) {
                  const nowDone = doneCount + 1;
                  progressMsg.textContent = `Hata gecildi: urun ${visualIndex} (${nowDone}/${endIndex - startIndex + 1})`;
                }
                resolve();
              }
            }, 3000);
          }
        });
      });
    }
    
    addLog(`[Popup] Tüm ürünler tamamlandı. Toplam: ${results.length}`);
    setRunStatus(`Tamamlandi (${results.length} urun)`, "ok");
    
    // 3. Sonuçları popup'ın kendisinde göster
    showResults(results, tab, data.cardCount);
    
  } catch (error) {
    console.error("[Popup] Hata:", error);
    alert("Hata: " + error.message);
    document.getElementById("searchSection").style.display = "block";
    document.getElementById("resultsSection").style.display = "none";
    setRunStatus("Islem hatasi", "error");
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
    "Index",
    "Başlık",
    "Ana Başlık",
    "Alt Başlık",
    "Etiketler",
    "Özellikler",
    "Açıklama",
    "Genel Bakış",
    "Ürün Açıklama Metni",
    "TL1 İçerik",
    "Marka",
    "Model",
    "Ekran Boyutu",
    "Çözünürlük",
    "CPU",
    "RAM",
    "Depolama",
    "Batarya",
    "Bağlantı",
    "İşletim Sistemi",
    "HDMI Çıkışı",
    "Gönderim Yeri",
    "Fiyat",
    "Gönderim Ücreti",
    "Toplam Fiyat",
    "Durum",
    "Resim URL",
    "Tüm Resim URL'leri",
    "Detay Specs JSON",
    "Spec Pairs JSON",
    "Spec Table JSON",
    "Link"
  ];
  const lines = [headers.join(",")];
  rows.forEach((r) => {
    const specs = r.detailSpecs || {};
    const rawSpecsText = (r.specPairs || [])
      .map((item) => `${item?.key || ""}: ${item?.value || ""}`.trim())
      .filter((item) => item && item !== ":")
      .join(" | ");
    const values = [
      r.index,
      r.title,
      r.anaTitle || r.title || "",
      r.subTitle || "",
      r.tags || "",
        r.features,
        r.description,
      r.overviewContent || "",
      r.navDescContent || "",
      r.tl1Content || "",
      specs.marka || "",
      specs.model || "",
      specs.ekran_boyutu || "",
      specs.cozunurluk || "",
      specs.cpu || "",
      specs.ram || "",
      specs.depolama || "",
      specs.batarya || "",
      specs.baglanti || "",
      specs.isletim_sistemi || "",
      specs.hdmi_cikisi || "",
      specs.gonderim_yeri || r.shippingFrom || "",
      r.price,
      r.shippingFee,
      r.totalPrice,
      r.status || "",
      r.imageUrl,
      (r.imageUrls || []).join(' | '),
      rawSpecsText,
      JSON.stringify(specs),
      JSON.stringify(r.specPairs || []),
      JSON.stringify(r.specTable || []),
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
    showNotification("âš ï¸ Bu ürün zaten eklendi!");
    return;
  }
  selectedResults.push(current);
  addLog(`[CSV] Ürün eklendi: ${current.index} (Toplam: ${selectedResults.length})`);
  
  // Seçili sayısını güncelle
  const selectedCountDiv = document.getElementById("selectedCount");
  const selectedNum = document.getElementById("selectedNum");
  if (selectedCountDiv && selectedNum) {
    selectedNum.textContent = selectedResults.length;
    selectedCountDiv.style.display = "block";
  }
  
  // İndir butonunu göster
  const downloadBtn = document.getElementById("downloadBtn");
  if (downloadBtn) {
    downloadBtn.style.display = "block";
    downloadBtn.classList.remove("hidden"); // Eğer hidden class varsa kaldır
    addLog("[UI] İndir butonu gösterildi");
    
    // Butona otomatik scroll
    setTimeout(() => {
      downloadBtn.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 100);
  }
  
  // Daha belirgin bildirim
  showNotification(`âœ… Eklendi! (${selectedResults.length}/${allResults.length})`);
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
      function findProductCards() {
        const containerSelectors = ["#card-list", ".search-card-list", "[class*='search-card']", "[class*='list--gallery']"];
        for (const selector of containerSelectors) {
          const container = document.querySelector(selector);
          if (!container) continue;
          const items = container.querySelectorAll(":scope > div, :scope > li, [data-product-id], [class*='search-card-item']");
          if (items && items.length > 0) return Array.from(items);
        }
        const fallback = document.querySelectorAll("a[href*='/item/']");
        const cards = [];
        fallback.forEach((a) => {
          const card = a.closest("div, li");
          if (card) cards.push(card);
        });
        return cards;
      }

      const cards = findProductCards();
      if (!cards.length) return;
      
      results.forEach(result => {
        const card = cards[result.index - 1];
        if (!card) return;
        
        const cannotDeliver = result.status.includes('âŒ');
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
  
  const isError = result.status.includes('âŒ');
  
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
  const expandBtn = document.getElementById("expandBtn");
  const backBtn = document.getElementById("backBtn");
  const totalCountEl = document.getElementById("totalCount");
  const openDetailBtn = document.getElementById("openDetailBtn");

  // Son oturumdan veriyi geri yükle (detay görünüm butonu için)
  try {
    const cachedResults = JSON.parse(localStorage.getItem("aliExtensionResults") || "[]");
    if (Array.isArray(cachedResults) && cachedResults.length > 0) {
      allResults = cachedResults;
      setRunStatus(`Hazir (${cachedResults.length} urun onbellekte)`, "ok");
    }
  } catch (e) {
  }

  if (openDetailBtn) {
    openDetailBtn.addEventListener("click", () => {
      if (!allResults || allResults.length === 0) {
        alert("Detayli gorunum icin once urunleri bulmaniz gerekiyor.");
        setRunStatus("Detay gorunum icin urun bekleniyor", "warn");
        return;
      }

      localStorage.setItem("aliExtensionResults", JSON.stringify(allResults));
      localStorage.setItem("aliExtensionSelected", JSON.stringify(selectedResults));
      localStorage.setItem("aliExtensionIndex", currentIndex);

      chrome.tabs.create({
        url: chrome.runtime.getURL("fullscreen.html")
      });
    });
  }
  
  // Detaylı Görünüm butonu
  if (expandBtn) {
    expandBtn.addEventListener("click", () => {
      if (!allResults || allResults.length === 0) {
        alert("âŒ Henüz ürün bulunamadı! Lütfen önce 'Ürünleri Bul' düğmesini tıklayın.");
        return;
      }
      
      addLog("[EXPAND] Detaylı görünüm açılıyor...");
      
      // Verileri localStorage'a kaydet
      localStorage.setItem("aliExtensionResults", JSON.stringify(allResults));
      localStorage.setItem("aliExtensionSelected", JSON.stringify(selectedResults));
      localStorage.setItem("aliExtensionIndex", currentIndex);
      
      // fullscreen.html'i yeni tab'da aç
      chrome.tabs.create({
        url: chrome.runtime.getURL("fullscreen.html")
      });
    });
  }

  // Popup açıldığında ürün sayısını göster
  (async () => {
    try {
      if (!totalCountEl) return;
      totalCountEl.textContent = "Sayfadaki urun sayisi: yukleniyor...";
      const count = await getPageProductCount();
      totalCountEl.textContent = `Sayfadaki urun sayisi: ${count}`;
      if (count > 0) {
        setRunStatus(`Hazir (${count} urun bulundu)`, "ok");
      } else {
        setRunStatus("Urun listesi bulunamadi (sayfayi yenileyin)", "warn");
      }
    } catch (error) {
      if (totalCountEl) {
        totalCountEl.textContent = "Sayfadaki urun sayisi: 0";
      }
      setRunStatus("Urun sayisi alinamadi", "warn");
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
      addLog("[USER] Ekle butonguna tıklandı");
      addCurrentToCsv();
      addLog("[USER] addCurrentToCsv() tamamlandı");
    });
  }
  
  const downloadBtn = document.getElementById("downloadBtn");
  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      if (selectedResults.length === 0) {
        showNotification("âš ï¸ Henüz hiçbir ürün eklemedin!");
        return;
      }
      const csv = buildCsv(selectedResults);
      downloadCsv(csv);
      showNotification(`âœ… CSV indirildi! (${selectedResults.length} ürün)`);
      
      // İndirme sonrası reset et
      selectedResults = [];
      const selectedCountDiv = document.getElementById("selectedCount");
      const selectedNum = document.getElementById("selectedNum");
      if (selectedCountDiv && selectedNum) {
        selectedNum.textContent = "0";
        selectedCountDiv.style.display = "none";
      }
      downloadBtn.style.display = "none";
    });
  }
  
  if (backBtn) {
    backBtn.addEventListener("click", () => {
      currentIndex = 0;
      allResults = [];
      selectedResults = [];
      
      // Seçilen sayısını gizle
      const selectedCountDiv = document.getElementById("selectedCount");
      if (selectedCountDiv) {
        selectedCountDiv.style.display = "none";
      }
      
      // İndir butonunu gizle
      const downloadBtn = document.getElementById("downloadBtn");
      if (downloadBtn) {
        downloadBtn.style.display = "none";
      }
      
      document.getElementById("searchSection").style.display = "block";
      document.getElementById("resultsSection").style.display = "none";
      setRunStatus("Hazir", "info");
    });
  }
});



