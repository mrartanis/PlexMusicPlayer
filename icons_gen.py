import os
from PIL import Image, ImageDraw, ImageFont

icon_sizes = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024
}

iconset_dir = "MusicApp.iconset"
if not os.path.exists(iconset_dir):
    os.makedirs(iconset_dir)

for filename, size in icon_sizes.items():
    img = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    font_size = size // 2
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except IOError:
        font = ImageFont.load_default()
    text = "♪"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_x = (size - text_width) // 2
    text_y = (size - text_height) // 2
    note_color = (135, 206, 235, 255)
    draw.text((text_x, text_y), text, font=font, fill=note_color)
    img.save(os.path.join(iconset_dir, filename))

print("Icon set created in folder:", iconset_dir)
print("Run 'iconutil -c icns {}' to compile the .icns file.".format(iconset_dir))
