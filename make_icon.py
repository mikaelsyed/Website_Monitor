# Regenerates website_monitor.ico (run with ArcGIS Pro Python; needs Pillow).
from PIL import Image, ImageDraw

S = 1024  # draw big, scale down for smooth edges
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Background: rounded square with vertical gradient (navy -> blue)
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
for y in range(S):
    t = y / S
    gd.line([(0, y), (S, y)], fill=(int(18 + 20 * t), int(38 + 60 * t), int(78 + 90 * t), 255))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=200, fill=255)
img.paste(grad, (0, 0), mask)

# Faint globe behind
cx, cy, r = S // 2, S // 2, 330
ov = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
globe = (255, 255, 255, 60)
d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=globe, width=22)
d.ellipse([cx - r // 2, cy - r, cx + r // 2, cy + r], outline=globe, width=18)
d.line([cx - r, cy, cx + r, cy], fill=globe, width=18)
d.line([cx, cy - r, cx, cy + r], fill=globe, width=18)

img.alpha_composite(ov); d = ImageDraw.Draw(img)
# Green heartbeat / pulse line
pts = [(130, 540), (360, 540), (430, 400), (520, 720), (610, 300), (680, 540), (894, 540)]
d.line(pts, fill=(80, 230, 110, 255), width=64, joint="curve")
for p in (pts[0], pts[-1]):
    d.ellipse([p[0] - 32, p[1] - 32, p[0] + 32, p[1] + 32], fill=(80, 230, 110, 255))

import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "website_monitor.ico")
img.resize((256, 256), Image.LANCZOS).save(
    out, sizes=[(s, s) for s in (16, 20, 24, 30, 32, 36, 40, 48, 64, 72, 96, 128, 256)])
print("ok")
