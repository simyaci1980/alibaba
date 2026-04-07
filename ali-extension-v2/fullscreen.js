// Global değişkenler
let allResults = [];
let selectedResults = [];
let currentIndex = 0;
let editedValues = {}; // Değiştirilen değerleri sakla

const RETRO_SPECS_ORDER = [
  { key: "marka", label: "Marka" },
  { key: "model", label: "Model" },
  { key: "ekran_boyutu", label: "Ekran Boyutu" },
  { key: "cozunurluk", label: "Cozunurluk" },
  { key: "ram", label: "RAM" },
  { key: "depolama", label: "Depolama" },
  { key: "batarya", label: "Batarya" },
  { key: "cpu", label: "Islemci" },
  { key: "baglanti", label: "Baglanti" },
  { key: "wifi", label: "Wi-Fi" },
  { key: "bluetooth", label: "Bluetooth" },
  { key: "usb_c", label: "USB-C" },
  { key: "isletim_sistemi", label: "Isletim Sistemi" },
  { key: "hdmi_cikisi", label: "HDMI Cikisi" },
  { key: "gonderim_yeri", label: "Gonderim Yeri" }
];

const SPEC_FIELD_KEYS = [
  "marka",
  "model",
  "ekran_boyutu",
  "cozunurluk",
  "cpu",
  "ram",
  "depolama",
  "batarya",
  "baglanti",
  "wifi",
  "bluetooth",
  "usb_c",
  "isletim_sistemi",
  "hdmi_cikisi",
  "gonderim_yeri"
];

function normalizeCurrencyCode(code) {
  const raw = String(code || "").trim().toUpperCase();
  if (!raw) return "USD";
  if (["US$", "$", "USD"].includes(raw)) return "USD";
  if (["TL", "TRY", "₺"].includes(raw)) return "TRY";
  if (["€", "EUR"].includes(raw)) return "EUR";
  if (["£", "GBP"].includes(raw)) return "GBP";
  return raw;
}

function formatMoney(amount, currencyCode, fallback = "-") {
  const numeric = Number.parseFloat(amount);
  if (Number.isNaN(numeric)) return fallback;
  return `${numeric.toFixed(2)} ${normalizeCurrencyCode(currencyCode)}`;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function getSpecValue(specs, key, fallback = "Belirtilmemis") {
  const value = specs && specs[key] ? String(specs[key]).trim() : "";
  return value || fallback;
}

function renderSpecs(product) {
  const specsList = document.getElementById("specsList");
  if (!specsList) return;

  const specs = product.detailSpecs || {};
  specsList.innerHTML = RETRO_SPECS_ORDER.map((item) => {
    const value = getSpecValue(specs, item.key);
    return `
      <div class="specs-row">
        <div class="specs-label">${item.label}</div>
        <div class="specs-value">${escapeHtml(value)}</div>
      </div>
    `;
  }).join("");
}

function renderRawSpecs(product) {
  const rawList = document.getElementById("rawSpecsList");
  if (!rawList) return;

  const rows = Array.isArray(product.specPairs) ? product.specPairs : [];
  if (!rows.length) {
    rawList.innerHTML = "<div style='padding:6px 2px; color:#64748b;'>Ham ozellik verisi bulunamadi.</div>";
    return;
  }

  rawList.innerHTML = rows.map((row) => {
    const key = escapeHtml(row.key || "");
    const value = escapeHtml(row.value || "");
    return `<div style="padding:6px 2px; border-bottom:1px solid #e2e8f0;"><strong>${key}:</strong> ${value}</div>`;
  }).join("");
}

function renderTableSpecs(product) {
  const tbody = document.getElementById("specTableBody");
  if (!tbody) return;

  const rows = Array.isArray(product.specTable) ? product.specTable : [];
  
  // Eger specTable bosssa, overviewContent > navDescContent > tl1Content sirasiyla dene
  if (!rows.length) {
    const content = product.overviewContent || product.navDescContent || product.tl1Content || product.description || "";
    if (!content) {
      tbody.innerHTML = `<tr><td colspan="2" style="padding:10px; text-align:center; color:#64748b;">Ozellikler tablosu verisi bulunamadi.</td></tr>`;
      return;
    }
    const lines = content.split("\n");
    tbody.innerHTML = lines.map((line, idx) => {
      const bgColor = idx % 2 === 0 ? "#f9fafb" : "#ffffff";
      const textContent = escapeHtml(line.trim());
      if (!textContent) return "";
      return `
        <tr style="background: ${bgColor}; border-bottom: 1px solid #e2e8f0;">
          <td colspan="2" style="padding: 8px 6px; color: #484d4d; line-height: 1.5;">${textContent}</td>
        </tr>
      `;
    }).filter(html => html).join("");
    return;
  }

  tbody.innerHTML = rows.map((row, idx) => {
    const bgColor = idx % 2 === 0 ? "#f9fafb" : "#ffffff";
    const key = escapeHtml(row.key || "");
    const value = escapeHtml(row.value || "");
    return `
      <tr style="background: ${bgColor}; border-bottom: 1px solid #e2e8f0;">
        <td style="padding: 8px 6px; font-weight: 600; color: #374151; width: 45%;">${key}</td>
        <td style="padding: 8px 6px; color: #484d4d;">${value}</td>
      </tr>
    `;
  }).join("");
}

function fillSpecEditor(product) {
  const specs = product.detailSpecs || {};
  SPEC_FIELD_KEYS.forEach((key) => {
    const el = document.getElementById(`spec_${key}`);
    if (!el) return;
    if (key === "gonderim_yeri") {
      el.value = specs[key] || product.shippingFrom || "";
      return;
    }
    el.value = specs[key] || "";
  });
}

function collectSpecEditorValues() {
  const next = {};
  SPEC_FIELD_KEYS.forEach((key) => {
    const el = document.getElementById(`spec_${key}`);
    if (!el) return;
    const val = (el.value || "").trim();
    if (val) {
      next[key] = val;
    }
  });
  return next;
}

function renderImageGallery(product) {
  const imgElement   = document.getElementById("productImage");
  const imgUrlElement = document.getElementById("imageUrl");
  const thumbsEl      = document.getElementById("imageThumbs");
  const prevBtn       = document.getElementById("galleryPrev");
  const nextBtn       = document.getElementById("galleryNext");
  const counterEl     = document.getElementById("galleryCounter");
  if (!imgElement || !imgUrlElement || !thumbsEl) return;

  const images = Array.isArray(product.imageUrls) && product.imageUrls.length
    ? product.imageUrls
    : (product.imageUrl ? [product.imageUrl] : []);

  if (!images.length) {
    imgElement.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Crect fill='%23ccc' width='200' height='200'/%3E%3Ctext x='50%' y='50%' text-anchor='middle' dy='.3em' fill='%23999' font-size='14'%3EGorsel yok%3C/text%3E%3C/svg%3E";
    imgUrlElement.textContent = "(Gorsel Bulunamadi)";
    thumbsEl.innerHTML = "";
    if (counterEl) counterEl.textContent = "0 / 0";
    return;
  }

  let activeIndex = 0;

  function setActive(index) {
    activeIndex = ((index % images.length) + images.length) % images.length;
    imgElement.src = images[activeIndex];
    imgUrlElement.textContent = images[activeIndex];
    if (counterEl) counterEl.textContent = `${activeIndex + 1} / ${images.length}`;
    thumbsEl.querySelectorAll(".thumb-btn").forEach((btn, i) => {
      btn.classList.toggle("active", i === activeIndex);
      if (i === activeIndex) btn.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
    });
  }

  thumbsEl.innerHTML = images.map((url, idx) => `
    <button type="button" class="thumb-btn ${idx === 0 ? "active" : ""}" data-index="${idx}" title="Gorsel ${idx + 1}">
      <img src="${escapeHtml(url)}" alt="Gorsel ${idx + 1}" loading="lazy" />
    </button>
  `).join("");

  thumbsEl.querySelectorAll(".thumb-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const index = Number(btn.dataset.index || 0);
      if (!Number.isNaN(index)) setActive(index);
    });
  });

  if (prevBtn) { prevBtn.onclick = () => setActive(activeIndex - 1); }
  if (nextBtn) { nextBtn.onclick = () => setActive(activeIndex + 1); }

  // Klavye yön tuslari (sadece galeri odakta)
  document.addEventListener("keydown", (e) => {
    if (e.target && e.target.tagName === "INPUT") return; // form alanlari yazarken çalısmasın
    if (e.key === "ArrowLeft")  { e.preventDefault(); setActive(activeIndex - 1); }
    if (e.key === "ArrowRight") { e.preventDefault(); setActive(activeIndex + 1); }
  });

  setActive(0);
}

// Log mesajlarını göster
function addLog(message) {
  console.log(message);
  const logsDiv = document.getElementById("logs");
  if (logsDiv) {
    logsDiv.style.display = "block";
    logsDiv.innerHTML += message + "<br>";
    logsDiv.scrollTop = logsDiv.scrollHeight;
    
    // 5 saniye sonra gizle
    setTimeout(() => {
      logsDiv.style.display = "none";
      logsDiv.innerHTML = "";
    }, 5000);
  }
}

// Edit modunu başlat
function startEdit(fieldName) {
  const viewElement = document.getElementById(fieldName + "Detail");
  const editRow = document.getElementById(fieldName + "EditRow");
  const editField = document.getElementById(fieldName + "Edit");
  
  if (viewElement && editRow && editField) {
    viewElement.style.display = "none";
    editRow.style.display = "block";
    editField.value = viewElement.textContent;
    editField.focus();
    editField.select();
  }
}

// Edit kaydet
function saveEdit(fieldName) {
  const editRow = document.getElementById(fieldName + "EditRow");
  const editField = document.getElementById(fieldName + "Edit");
  const viewElement = document.getElementById(fieldName + "Detail");
  
  if (editField && viewElement && editRow) {
    const newValue = editField.value.trim();
    viewElement.textContent = newValue;
    editedValues[fieldName] = newValue; // Değişiklikleri sakla
    
    viewElement.style.display = "block";
    editRow.style.display = "none";
    
    addLog(`[EDIT] ${fieldName} güncellendi: ${newValue.substring(0, 50)}`);
  }
}

// Edit iptal
function cancelEdit(fieldName) {
  const editRow = document.getElementById(fieldName + "EditRow");
  const viewElement = document.getElementById(fieldName + "Detail");
  
  if (viewElement && editRow) {
    viewElement.style.display = "block";
    editRow.style.display = "none";
  }
}

// localStorage'dan verileri yükle
function loadData() {
  try {
    const resultsJson = localStorage.getItem("aliExtensionResults");
    const selectedJson = localStorage.getItem("aliExtensionSelected");
    const indexJson = localStorage.getItem("aliExtensionIndex");
    
    if (resultsJson) {
      allResults = JSON.parse(resultsJson);
      addLog(`[DATA] ${allResults.length} ürün yüklendi`);
    }
    
    if (selectedJson) {
      selectedResults = JSON.parse(selectedJson);
      addLog(`[DATA] ${selectedResults.length} seçili ürün yüklendi`);
    }
    
    if (indexJson) {
      currentIndex = parseInt(indexJson, 10);
      addLog(`[DATA] Index: ${currentIndex}`);
    }
    
    if (allResults.length === 0) {
      document.querySelector(".container").innerHTML = `
        <div style="grid-column: 1/-1; display: flex; align-items: center; justify-content: center;">
          <div style="text-align: center; padding: 40px;">
            <h1>❌ Veri Bulunamadı</h1>
            <p style="margin-top: 20px; color: #666;">Lütfen popup'tan ürünleri "Bul" düğmesini tıklayıp daha sonra "Genişletilmiş Görünüm"ü açın.</p>
            <button onclick="window.close();" style="margin-top: 20px; padding: 10px 20px; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">Kapat</button>
          </div>
        </div>
      `;
      return false;
    }
    
    return true;
  } catch (error) {
    addLog(`[ERROR] Veri yükleme hatası: ${error.message}`);
    return false;
  }
}

// Ürünü göster
function displayProduct(index) {
  if (!allResults || index < 0 || index >= allResults.length) {
    addLog(`[ERROR] Geçersiz index: ${index}`);
    return;
  }
  

  // Önce eklenmiş/güncellenmiş ürün var mı kontrol et
  let product = allResults[index];
  const selectedIndex = selectedResults.findIndex(r => r.index === product.index && r.productLink === product.productLink);
  if (selectedIndex !== -1) {
    product = { ...product, ...selectedResults[selectedIndex] };
  }
  currentIndex = index;
  // editedValues artık resetlenmiyor; allResults'a kaydedilen degerler displayProduct'ta geri okunuyor

  // Görsel galerisi + teknik alan kartı
  renderImageGallery(product);
  renderSpecs(product);
  renderRawSpecs(product);
  renderTableSpecs(product);
  fillSpecEditor(product);

  // Başlığı ayarla
  document.getElementById("productIndex").textContent = `ürün #${product.index}`;
  document.getElementById("productTitle").textContent = product.title || "Başlık Yok";

  // Input field'leri doldur
  const titleInput = document.getElementById("titleInput");
  const descriptionInput = document.getElementById("descriptionInput");
  const shippingInput = document.getElementById("shippingInput");
  const anaTitleInput = document.getElementById("anaTitleInput");
  const subTitleInput = document.getElementById("subTitleInput");
  const tagsInput = document.getElementById("tagsInput");
  const featuresInput = document.getElementById("featuresInput");
  const specShippingInput = document.getElementById("spec_gonderim_yeri");

  titleInput.value = product.title || "";
  // Baslik metni varsayilan olarak Ana Baslik alanina da yazilsin.
  anaTitleInput.value = product.anaTitle || product.title || "";
  subTitleInput.value = product.subTitle || "";
  tagsInput.value = product.tags || "";
  featuresInput.value = product.features || "";

  // Açıklamayı ayarla
  const descriptionRow = document.getElementById("descriptionRow");
  if (product.description) {
    descriptionRow.style.display = "flex";
    descriptionInput.style.display = "block";
    descriptionInput.value = product.description;
    descriptionInput.placeholder = "Ürün açıklamasını düzenle...";
  } else {
    descriptionRow.style.display = "none";
    descriptionInput.style.display = "none";
  }

  shippingInput.value = product.shippingFrom || "";
  shippingInput.placeholder = "Gönderim yerini düzenle (örn: Çin, Fransa)...";
  if (specShippingInput && !specShippingInput.value) {
    specShippingInput.value = shippingInput.value || "";
  }
  
  // Durum
  const statusBadge = document.getElementById("statusBadge");
  const isError = product.status.includes('❌');
  statusBadge.textContent = product.status;
  statusBadge.className = isError ? "status-badge error" : "status-badge ok";
  
  // Fiyatlar ve gönderim (salt okunur)
  const currencyCode = normalizeCurrencyCode(product.currencyCode);
  document.getElementById("priceDetail").textContent = formatMoney(product.price, currencyCode, "-");
  
  if (product.shippingFee && parseFloat(product.shippingFee) > 0) {
    document.getElementById("shippingFeeDetail").textContent = formatMoney(product.shippingFee, currencyCode, "-");
    document.getElementById("totalPriceDetail").textContent = formatMoney(product.totalPrice, currencyCode, "-");
  } else {
    document.getElementById("shippingFeeDetail").textContent = "Ücretsiz";
    document.getElementById("totalPriceDetail").textContent = formatMoney(product.price, currencyCode, "-");
  }
  
  // Link
  if (product.productLink) {
    document.getElementById("linkRow").style.display = "flex";
    document.getElementById("productLink").href = product.productLink;
  }
  
  // Sayfa bilgisi
  document.getElementById("pageCounter").textContent = `${index + 1} / ${allResults.length}`;
  
  // Seçili sayısını güncelle
  const selectedCountDiv = document.getElementById("selectedCount");
  const selectedNum = document.getElementById("selectedNum");
  if (selectedCountDiv && selectedNum) {
    selectedNum.textContent = selectedResults.length;
    if (selectedResults.length > 0) {
      selectedCountDiv.style.display = "block";
    } else {
      selectedCountDiv.style.display = "none";
    }
  }
  
  addLog(`[DISPLAY] Ürün #${product.index} gösterildi`);
}

// CSV oluştur
function buildCsv(results) {
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
    "Wi-Fi",
    "Bluetooth",
    "USB-C",
    "İşletim Sistemi",
    "HDMI Çıkışı",
    "Gönderim Yeri",
    "Para Birimi",
    "Fiyat",
    "Gönderim Ücreti",
    "Toplam Fiyat",
    "Durum",
    "Resim URL",
    "Tüm Resim URL'leri",
    "Ham Özellikler",
    "Detay Specs JSON",
    "Spec Pairs JSON",
    "Spec Table JSON",
    "Link"
  ];
  const lines = [headers.join(",")];
  
  results.forEach((r) => {
    const toCsvValue = (v) => {
      if (v === null || v === undefined) return "";
      const str = v.toString();
      if (str.includes(",") || str.includes('"') || str.includes("\n")) {
        return '"' + str.replace(/"/g, '""') + '"';
      }
      return str;
    };
    
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
      specs.wifi || "",
      specs.bluetooth || "",
      specs.usb_c || "",
      specs.isletim_sistemi || "",
      specs.hdmi_cikisi || "",
      specs.gonderim_yeri || r.shippingFrom || "",
      r.currencyCode || "USD",
      r.price,
      r.shippingFee,
      r.totalPrice,
      r.status || "",
      r.imageUrl,
      (r.imageUrls || []).join(" | "),
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

// CSV İndir
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
  
  addLog(`[CSV] ${selectedResults.length} ürün indirildi`);
}

// Ürünü ekle
function saveCurrentEdits() {
  if (currentIndex < 0 || currentIndex >= allResults.length) return;

  const product = allResults[currentIndex];
  const titleInput        = document.getElementById("titleInput");
  const descriptionInput  = document.getElementById("descriptionInput");
  const shippingInput     = document.getElementById("shippingInput");
  const anaTitleInput     = document.getElementById("anaTitleInput");
  const subTitleInput     = document.getElementById("subTitleInput");
  const tagsInput         = document.getElementById("tagsInput");
  const featuresInput     = document.getElementById("featuresInput");

  const updated = { ...product };
  updated.title       = titleInput?.value       ?? product.title;
  updated.anaTitle    = anaTitleInput?.value    ?? product.anaTitle;
  updated.subTitle    = subTitleInput?.value    ?? product.subTitle;
  updated.tags        = tagsInput?.value        ?? product.tags;
  updated.features    = featuresInput?.value    ?? product.features;
  updated.description = descriptionInput?.value ?? product.description;
  updated.shippingFrom = shippingInput?.value   ?? product.shippingFrom;

  const editedSpecs = collectSpecEditorValues();
  updated.detailSpecs = { ...(product.detailSpecs || {}), ...editedSpecs };
  if (updated.detailSpecs.gonderim_yeri) {
    updated.shippingFrom = updated.detailSpecs.gonderim_yeri;
  }

  // allResults'a geri yaz
  allResults[currentIndex] = updated;

  // selectedResults'ta varsa onu da güncelle
  const selIdx = selectedResults.findIndex(r => r.index === product.index && r.productLink === product.productLink);
  if (selIdx !== -1) {
    selectedResults[selIdx] = { ...selectedResults[selIdx], ...updated };
  }
}

function addCurrentProduct() {
  if (currentIndex < 0 || currentIndex >= allResults.length) {
    addLog("[ERROR] Geçersiz ürün");
    return;
  }
  
  const product = allResults[currentIndex];
  
  // Zaten eklendi mi? (güncelleyeceğiz!)
  let existingIndex = selectedResults.findIndex((r) => r.index === product.index && r.productLink === product.productLink);
  
  // Input field'lerden değerleri oku
  const titleInput = document.getElementById("titleInput");
  const descriptionInput = document.getElementById("descriptionInput");
  const shippingInput = document.getElementById("shippingInput");
  const anaTitleInput = document.getElementById("anaTitleInput");
  const subTitleInput = document.getElementById("subTitleInput");
  const tagsInput = document.getElementById("tagsInput");
  const featuresInput = document.getElementById("featuresInput");
  
  // Düzenlenen değerleri uygula
  const productToAdd = { ...product };
  
  if (titleInput.value !== product.title) {
    productToAdd.title = titleInput.value;
    addLog(`[EDIT] Başlık güncellendi: ${titleInput.value.substring(0, 40)}`);
  }

  if (descriptionInput.value !== product.description) {
    productToAdd.description = descriptionInput.value;
    addLog(`[EDIT] Açıklama güncellendi: ${descriptionInput.value.substring(0, 40)}`);
  }

  if (shippingInput.value !== product.shippingFrom) {
    productToAdd.shippingFrom = shippingInput.value;
    addLog(`[EDIT] Gönderim yeri güncellendi: ${shippingInput.value}`);
  }

  // Ana baslik: Baslik alanini temel al (istenen akis)
  productToAdd.anaTitle = (titleInput.value || anaTitleInput.value || "").trim();
  // Alt baslik su an ayni sekilde manuel kalsin
  productToAdd.subTitle = subTitleInput.value;
  productToAdd.tags = tagsInput.value;
  productToAdd.features = featuresInput.value;
  const editedSpecs = collectSpecEditorValues();
  productToAdd.detailSpecs = { ...(product.detailSpecs || {}), ...editedSpecs };
  if (productToAdd.detailSpecs.gonderim_yeri) {
    productToAdd.shippingFrom = productToAdd.detailSpecs.gonderim_yeri;
  }
  productToAdd.imageUrls = product.imageUrls || (product.imageUrl ? [product.imageUrl] : []);
  
  if (existingIndex !== -1) {
    // Zaten var, güncelle
    selectedResults[existingIndex] = productToAdd;
    addLog(`[CSV] Ürün güncellendi: ${product.index} (Toplam: ${selectedResults.length})`);
    alert(`✅ Ürün güncellendi!\n(${selectedResults.length}/${allResults.length})`);
  } else {
    // Yeni ürün, ekle
    selectedResults.push(productToAdd);
    addLog(`[CSV] Ürün eklendi: ${product.index} (Toplam: ${selectedResults.length})`);
    alert(`✅ Ürün eklendi!\n(${selectedResults.length}/${allResults.length})`);
  }
  
  // UI güncelle
  const selectedCountDiv = document.getElementById("selectedCount");
  const selectedNum = document.getElementById("selectedNum");
  const downloadBtn = document.getElementById("downloadBtn");
  
  if (selectedCountDiv && selectedNum) {
    selectedNum.textContent = selectedResults.length;
    selectedCountDiv.style.display = "block";
  }
  
  if (downloadBtn) {
    downloadBtn.style.display = "block";
  }
  
  // localStorage'a kaydet
  localStorage.setItem("aliExtensionSelected", JSON.stringify(selectedResults));
  
  // Düzenleme verilerini sıfırla
  editedValues = {};
}

// Keyboard kısayolları
window.addEventListener("keydown", function(e) {
  const active = document.activeElement;
  // Eğer bir input veya textarea odakta ise yön tuşları ürün değiştirmesin
  if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) {
    // Sadece Enter tuşu inputlarda çalışsın, diğerleri engellensin
    if (e.key.toLowerCase() === 'a' || e.key === 'ArrowLeft' || e.key.toLowerCase() === 'd' || e.key === 'ArrowRight') {
      return;
    }
    // Eğer textarea odakta ve Enter'a basıldıysa ürün eklenmesin, sadece yeni satır eklensin
    if (active.tagName === "TEXTAREA" && e.key === "Enter") {
      return; // Sadece textarea'da yeni satır ekle
    }
    // Eğer input odakta ve Enter'a basıldıysa ürün ekle
    if (active.tagName === "INPUT" && e.key === "Enter") {
      document.getElementById("addBtn").click();
      return;
    }
  }
  // ...eski yön tuşu kodu...
  if (e.key.toLowerCase() === 'a' || e.key === 'ArrowLeft') {
    if (currentIndex > 0) {
      currentIndex--;
      displayProduct(currentIndex);
    }
  } else if (e.key.toLowerCase() === 'd' || e.key === 'ArrowRight') {
    if (currentIndex < allResults.length - 1) {
      currentIndex++;
      displayProduct(currentIndex);
    }
  } else if (e.key === 'Enter') {
    // Sadece input/textarea odakta değilse ürün ekle
    if (!active || (active.tagName !== "INPUT" && active.tagName !== "TEXTAREA")) {
      document.getElementById("addBtn").click();
    }
  }
});

// DOM Yüklendikten sonra
document.addEventListener("DOMContentLoaded", () => {
  addLog("[INIT] Sayfa yüklendi");

  const titleInput = document.getElementById("titleInput");
  const anaTitleInput = document.getElementById("anaTitleInput");
  if (titleInput && anaTitleInput) {
    titleInput.addEventListener("input", () => {
      anaTitleInput.value = titleInput.value;
    });
  }
  
  if (!loadData()) {
    return;
  }
  
  displayProduct(currentIndex);
  
  // Butonlar
  document.getElementById("prevBtn").addEventListener("click", () => {
    if (currentIndex > 0) {
      saveCurrentEdits();
      currentIndex--;
      displayProduct(currentIndex);
    }
  });

  document.getElementById("nextBtn").addEventListener("click", () => {
    if (currentIndex < allResults.length - 1) {
      saveCurrentEdits();
      currentIndex++;
      displayProduct(currentIndex);
    }
  });
  
  document.getElementById("addBtn").addEventListener("click", () => {
    addCurrentProduct();
    // Otomatik sonraki ürüne geçiş kaldırıldı. Kullanıcı isterse manuel geçiş yapacak.
  });
  
  document.getElementById("downloadBtn").addEventListener("click", () => {
    if (selectedResults.length === 0) {
      alert("⚠️ Henüz hiçbir ürün eklemedin!");
      return;
    }
    const csv = buildCsv(selectedResults);
    downloadCsv(csv);
    alert(`✅ CSV indirildi! (${selectedResults.length} ürün)`);
    
    // Reset
    selectedResults = [];
    localStorage.setItem("aliExtensionSelected", JSON.stringify(selectedResults));
    document.getElementById("downloadBtn").style.display = "none";
    document.getElementById("selectedCount").style.display = "none";
    displayProduct(currentIndex);
  });
});
