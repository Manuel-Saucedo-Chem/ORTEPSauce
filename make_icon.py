"""Draws ortepsauce.ico (an ORTEP-style ellipsoid with bonds) for the .exe."""
from PIL import Image, ImageDraw

S = 256
im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=48, fill=(31, 106, 165, 255))
for x0, y0, x1, y1 in ((60, 190, 128, 128), (128, 128, 205, 70), (128, 128, 200, 195)):
    d.line([x0, y0, x1, y1], fill=(15, 15, 15, 255), width=14)
for cx, cy, r, col in ((60, 190, 26, (80, 80, 80)), (205, 70, 24, (0, 93, 255)), (200, 195, 22, (220, 30, 30))):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (255,), outline=(10, 10, 10, 255), width=4)
d.ellipse([78, 92, 178, 164], fill=(206, 40, 206, 255), outline=(10, 10, 10, 255), width=5)   # metal ellipsoid
d.arc([78, 92, 178, 164], 0, 360, fill=(255, 255, 255, 255), width=3)
d.line([128, 94, 128, 162], fill=(255, 255, 255, 255), width=4)                             # principal axes
d.line([80, 128, 176, 128], fill=(255, 255, 255, 255), width=4)
im.save('ortepsauce.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print('ortepsauce.ico written')
