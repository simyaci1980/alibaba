import cairosvg
from PIL import Image

# SVG'den PNG'ye dönüştür
cairosvg.svg2png(url='kolaybulexpres_logo_1x1_focus.svg', write_to='kolaybulexpres_logo_1x1_focus.png')

# PNG'den JPG'ye dönüştür
png_image = Image.open('kolaybulexpres_logo_1x1_focus.png')
rgb_image = png_image.convert('RGB')
rgb_image.save('kolaybulexpres_logo_1x1_focus.jpg', quality=95)

print('PNG ve JPG dosyaları oluşturuldu.')
