chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "findAndHighlight") {
    console.log("[Content] Mesaj alındı");
    
    const cardList = document.getElementById("card-list");
    if (!cardList) {
      alert("card-list bulunamadı!");
      console.log("[Content] card-list bulunamadı");
      return;
    }

    const cards = cardList.querySelectorAll(":scope > div");
    console.log(`[Content] ${cards.length} kart bulundu`);
    
    cards.forEach((card, index) => {
      card.style.outline = "5px solid red";
      card.style.outlineOffset = "2px";
      card.style.backgroundColor = "rgba(255, 0, 0, 0.1)";
      console.log(`Kart ${index + 1} çerçevelendi:`, card);
    });

    alert(`${cards.length} ürün kırmızı çerçeveyle işaretlendi!`);
  }
});
