#!/usr/bin/env python3
"""V2b fixes: book quad top up; P2 layout un-collided (type up, art inset,
mini bottom band so the phone timer stays visible)."""
import py_compile

p = 'assets/marketing/night-before-hook/build_v2.py'
src = open(p, encoding='utf-8').read()

# 1. book face starts higher than estimated
old_q = "BOOK_Q = [(0.078, 0.358), (0.535, 0.372), (0.528, 0.725), (0.072, 0.712)]"
assert old_q in src, 'BOOK_Q not found'
src = src.replace(old_q, "BOOK_Q = [(0.080, 0.330), (0.533, 0.344), (0.528, 0.725), (0.072, 0.712)]")

# 2a. P2 headline block: smaller + higher
old_t = '''    pill(d, (72, 96), "INSIDE THE PDF", F("archivo", 30, "Bold"), CREAM, CHAR)
    d.text((72, 180), "OPEN IT.", font=F("anton", 120), fill=CHAR)
    d.text((72, 300), "USE IT TONIGHT.", font=F("anton", 120), fill=TERRA)'''
assert old_t in src, 'P2 headline not found'
src = src.replace(old_t, '''    pill(d, (72, 64), "INSIDE THE PDF", F("archivo", 28, "Bold"), CREAM, CHAR)
    d.text((72, 140), "OPEN IT.", font=F("anton", 92), fill=CHAR)
    d.text((72, 232), "USE IT TONIGHT.", font=F("anton", 92), fill=TERRA)''')

# 2b. P2 book art: deeper inset so it sits inside the face
old_b = "    img = place_art(img, COVER, rq(FLAT_BOOK_Q), inset=0.07)"
assert old_b in src, 'P2 book place not found'
src = src.replace(old_b, "    img = place_art(img, COVER, rq(FLAT_BOOK_Q), inset=0.16)")

# 2c. P2 bottom: mini band so phone timer (ends ~1757) stays visible
old_band = '''    # bottom inventory on dark band for contrast
    band_y = 1330
    d.rectangle([0, band_y, W, H], fill=CHAR)
    d.rectangle([0, band_y, W, band_y + 8], fill=TERRA)
    y = band_y + 48
    d.text((72, y), "H \\u00b7 O \\u00b7 O \\u00b7 K \\u2014 the 4-move ritual, timed to 10:00",
           font=F("archivo", 36, "Bold"), fill=TERRA_LT)
    y += 70
    y = para(d, (72, y), "10 chapters \\u00b7 copy-paste if-then library \\u00b7 friction audit \\u00b7 3 worked nights \\u00b7 14-night log \\u00b7 one-page card",
             F("archivo", 36, "Regular"), CREAM, W - 144, 52) + 30
    pill(d, (72, y), "GET IT ON GUMROAD  \\u2192", F("archivo", 38, "Bold"), (20, 14, 8), TERRA_LT)'''
assert old_band in src, 'P2 band not found'
src = src.replace(old_band, '''    # bottom mini-band: inventory only, phone timer stays visible above it
    band_y = 1660
    d.rectangle([0, band_y, W, H], fill=CHAR)
    d.rectangle([0, band_y, W, band_y + 6], fill=TERRA)
    para(d, (72, band_y + 30), "H \\u00b7 O \\u00b7 O \\u00b7 K \\u2014 the 4-move ritual \\u00b7 10 chapters \\u00b7 if-then library \\u00b7 friction audit \\u00b7 14-night log \\u00b7 one-page card",
         F("archivo", 32, "Regular"), CREAM, W - 144, 46)''')

open(p, 'w', encoding='utf-8').write(src)
py_compile.compile(p, doraise=True)
print('v2b patched + compiles')
