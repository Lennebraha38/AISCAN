"""Demo icin 10 farkli patoloji goruntusu uretir (deterministik v2).

Her dosya motorun ozel cikarimlarinda (asimetri/opasite/kenar/mediasten/
periferik karanlik) FARKLI bir profil uretecek sekilde cizilir.

Kullanim: .venv/bin/python scripts/gen_demo_images.py [cikti_dizini]
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 512


def _noise(a, amp=5):
    rng = np.random.default_rng(7)
    return np.clip(a.astype(np.float32) + rng.normal(0, amp, a.shape), 0, 255)


def _smooth(a, r=2):
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(r)
    )
    return np.asarray(im, dtype=np.float32)


def chest(shift=0.0, body_base=40):
    """Govde tam cerceveyi dolduran temel PA grafisi."""
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    a = np.full((SIZE, SIZE), 10, dtype=np.float32)
    # govde (kenarlarda ince koyu rim kalir)
    body = ((xx - SIZE / 2) / (SIZE / 2 - 8)) ** 2 + ((yy - 270) / 245) ** 2 < 1
    a[body] = body_base
    cx = SIZE // 2 + shift * 34
    for side in (-1, 1):
        lx = cx + side * 122
        lung = (((xx - lx) / 104) ** 2 + ((yy - 255) / 172) ** 2) < 1
        a[lung] = 86 + 14 * np.sin(yy[lung] / 33) * np.cos(xx[lung] / 27)
        rib = (np.sin((yy + xx * side * 0.22) / 24) > 0.88) & lung
        a[rib] += 14
    # mediyasten (0.62 esiginin ALTINDA kalmali)
    medi = (np.abs(xx - cx) < 52) & (yy > 110) & (yy < 440)
    a[medi] = 148
    spined = (np.abs(xx - cx) < 13) & (yy > 60)
    a[spined] = 165
    # diafragma
    for side in (-1, 1):
        dx = cx + side * 122
        dm = (yy > 408 - 34 * np.exp(-(((xx - dx) / 135) ** 2))) & (
            np.abs(xx - dx) < 140
        )
        a[dm] = np.maximum(a[dm], 142)
    return _smooth(_noise(a), 1.5)


def add_blob(a, x, y, r, val, blur=8):
    m = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(m).ellipse([x - r, y - r, x + r, y + r], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(blur))
    overlay = Image.new("L", (SIZE, SIZE), int(val))
    base = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return np.asarray(Image.composite(overlay, base, m), dtype=np.float32)


def region_max(a, mask_fn, val, blur=6):
    m = Image.new("L", (SIZE, SIZE), 0)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    sel = mask_fn(xx, yy)
    marr = np.zeros((SIZE, SIZE), dtype=np.uint8)
    marr[sel] = 255
    m = Image.fromarray(marr).filter(ImageFilter.GaussianBlur(blur))
    overlay = Image.new("L", (SIZE, SIZE), int(val))
    base = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return np.asarray(Image.composite(overlay, base, m), dtype=np.float32)


def save(a, name, outdir):
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(
        os.path.join(outdir, name)
    )
    print("uretildi:", name)


def gen_normal(d):
    save(chest(), "cxr-normal.png", d)


def _hard_blob(a, x, y, r, val):
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    ImageDraw.Draw(im).ellipse([x - r, y - r, x + r, y + r], fill=int(val))
    return np.asarray(im, dtype=np.float32)


def _sharpen(a):
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(
        ImageFilter.UnsharpMask(radius=2, percent=170)
    )
    return np.asarray(im, dtype=np.float32)


def gen_nodule(d):
    a = chest()
    a = _hard_blob(a, 350, 250, 74, 26)    # koyu hale
    a = _hard_blob(a, 350, 250, 58, 252)   # ana kutle
    a = _hard_blob(a, 356, 240, 22, 255)   # cekirdek
    a = _hard_blob(a, 284, 330, 26, 30)    # uydu 1 halesi
    a = _hard_blob(a, 284, 330, 17, 248)
    a = _hard_blob(a, 402, 180, 14, 30)    # uydu 2 halesi
    a = _hard_blob(a, 402, 180, 10, 246)
    save(_sharpen(a), "cxr-nodule.png", d)


def gen_metastatic(d):
    a = chest()
    pts = [(178, 205), (205, 305), (248, 250), (352, 215), (322, 330), (382, 285),
           (150, 260), (230, 180)]
    for x, y, r in [(x, y, 22 if i % 2 else 26) for i, (x, y) in enumerate(pts)]:
        a = _hard_blob(a, x, y, r + 12, 28)   # koyu hale
        a = _hard_blob(a, x, y, r, 247)
    save(_sharpen(a), "cxr-metastatic.png", d)


def gen_effusion(d):
    a = chest()
    a = region_max(a, lambda x, y: (x < 250) & (y > 325 - 0.30 * (250 - x)) & (y < 480),
                   186, blur=7)
    save(a, "cxr-effusion.png", d)


def gen_pneumonia(d):
    a = chest()
    yy0, xx0 = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    right_lung = (xx0 > 268) & (xx0 < 470) & (yy0 > 212) & (yy0 < 428)
    a[right_lung] = np.maximum(a[right_lung], 162)
    a = add_blob(a, 185, 360, 40, 158, blur=14)   # sol bazal odak
    a = add_blob(a, 165, 250, 30, 156, blur=13)   # sol ust odak
    save(a, "cxr-pneumonia.png", d)


def _air_zone(a, xmin, shift_line_x, line_val=118, width=4, ymax=470):
    a[:ymax, xmin:] = 5
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)
    dr.line([(shift_line_x, 55), (shift_line_x + 4, 470)], fill=line_val, width=width)
    return np.asarray(im.filter(ImageFilter.GaussianBlur(1)), dtype=np.float32)


def gen_pneumothorax(d):
    a = chest()
    a = _air_zone(a, 392, 390, ymax=372)
    save(a, "cxr-pneumothorax.png", d)


def gen_tension(d):
    a = chest(shift=-0.85)
    a = _air_zone(a, 305, 303, line_val=100, width=6)
    save(a, "cxr-tension.png", d)


def gen_cardiomegaly(d):
    a = chest()
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    # cok genis ve uzun kalp golgesi (kol ortalamalarini esige tasiyacak)
    hm = ((xx - 228) / 172) ** 2 + ((yy - 295) / 205) ** 2 < 1
    a[hm] = 156
    wide = (xx > 96) & (xx < 366) & (yy > 90) & (yy < 480)
    a[wide] = np.maximum(a[wide] * 0.55, 138)
    a = add_blob(a, 150, 418, 54, 172, blur=11)
    a = add_blob(a, 382, 422, 50, 170, blur=11)
    im = _smooth(a, 4)
    save(np.asarray(im, dtype=np.float32), "cxr-cardiomegaly.png", d)


def gen_atelectasis(d):
    a = chest(shift=-0.35)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    m = (xx < 258) & (yy > 300) & (yy < 455)
    a[m] = np.maximum(a[m], 170)
    band = (np.abs(xx - 185 + 0.30 * (yy - 300)) < 30) & (yy > 290) & (yy < 440)
    a[band] = 188
    save(np.asarray(_smooth(a, 4), dtype=np.float32), "cxr-atelectasis.png", d)


def gen_ct_head(d):
    a = np.full((SIZE, SIZE), 8, dtype=np.float32)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    r2 = (xx - 256) ** 2 + (yy - 256) ** 2
    a[(r2 < 216 ** 2) & (r2 > 194 ** 2)] = 212
    brain = r2 < 194 ** 2
    a[brain] = 112 + 10 * np.sin(xx[brain] / 42) * np.cos(yy[brain] / 38)
    vent = (((xx - 256) / 24) ** 2 + ((yy - 240) / 58) ** 2) < 1
    a[vent] = 46
    # sag hemisferde buyuk hiperdens kanama + odem (asimetri)
    a[((xx - 318) ** 2 + (yy - 280) ** 2) < 46 ** 2] = 208
    a[((xx - 318) ** 2 + (yy - 280) ** 2) < 78 ** 2] += 14
    a[((xx - 318) ** 2 + (yy - 280) ** 2) < 78 ** 2] = np.minimum(
        a[((xx - 318) ** 2 + (yy - 280) ** 2) < 78 ** 2], 190
    )
    im = Image.fromarray(np.clip(_noise(a, 4), 0, 255).astype(np.uint8))
    im.save(os.path.join(d, "ct-head.png"))
    print("uretildi: ct-head.png")


GENS = {
    "normal": gen_normal,
    "nodule": gen_nodule,
    "metastatic": gen_metastatic,
    "effusion": gen_effusion,
    "pneumonia": gen_pneumonia,
    "pneumothorax": gen_pneumothorax,
    "tension": gen_tension,
    "cardiomegaly": gen_cardiomegaly,
    "atelectasis": gen_atelectasis,
    "ct_head": gen_ct_head,
}

if __name__ == "__main__":
    outdir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/testdata"
    os.makedirs(outdir, exist_ok=True)
    for name, fn in GENS.items():
        fn(outdir)
