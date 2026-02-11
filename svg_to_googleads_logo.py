import cairosvg
from PIL import Image
import io

# SVG dosya yolu
svg_path = 'kolaybulexpres-lo-1x1-focus.svg'
# PNG olarak kaydedilecek yol
png_path = 'static/urunler/kolaybulexpres-logo.png'

# SVG'den PNG'ye dönüştür (1200x1200 px)
cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=1200, output_height=1200)

# PNG'yi aç ve kenarlardaki boşlukları kırp (gerekirse)
img = Image.open(png_path)
img = img.convert('RGBA')

# Otomatik kırpma (gerekiyorsa)
# img = img.crop(img.getbbox())

# Yeniden 1200x1200'e ortala (boşlukları azaltmak için)
background = Image.new('RGBA', (1200, 1200), (255, 255, 255, 0))
img.thumbnail((960, 960), Image.LANCZOS)
# Ortalamak için
x = (1200 - img.width) // 2
y = (1200 - img.height) // 2
background.paste(img, (x, y), img)
background.save(png_path)

print('Logo Google Ads için hazırlandı: static/urunler/kolaybulexpres-logo.png')
