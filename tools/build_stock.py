"""Build the stock art library (GD5): web sizes, stream size and manifest.json.

Input : design/keep.json  {"<id>": {"raw": "<repo path to PNG>", "tag": "...", "region": "...", "alt": "...", "prompt": "...", "seed": N, "host": "...", "date": "...", "judge_notes": "...", "corner_check": "..."}}
Output: assets/stock/web/<id>-{375,768,1440}.{avif,webp,jpg}, assets/stock/stream/<id>.webp (1920x1080), assets/stock/manifest.json
Rules : no text in images, label 'Illustration', licence 'generated in-house'.
"""
import json, os, subprocess, sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "stock")
WIDTHS = (375, 768, 1440)
LICENCE = "generated in-house, FLUX schnell, Apache 2.0"


def fit(im, w, h):
    """Crop to the w:h ratio from the centre, then resize."""
    r = w / h
    iw, ih = im.size
    if iw / ih > r:
        nw = round(ih * r); im = im.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = round(iw / r); im = im.crop((0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh))
    return im.resize((w, h), Image.LANCZOS)


def avif(src_png, dst, crf):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src_png, "-c:v", "libsvtav1", "-crf", str(crf), "-pix_fmt", "yuv420p", "-frames:v", "1", dst], check=True)


def build(keep):
    os.makedirs(os.path.join(OUT, "web"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "stream"), exist_ok=True)
    tmp = os.path.join(OUT, ".tmp.png")
    manifest = []
    for sid, k in sorted(keep.items()):
        im = Image.open(k["raw"]).convert("RGB")
        web = []
        for w in WIDTHS:
            h = round(w * 9 / 16)
            r = fit(im, w, h)
            base = os.path.join(OUT, "web", "%s-%d" % (sid, w))
            r.save(base + ".webp", "WEBP", quality=72, method=6)
            r.save(base + ".jpg", "JPEG", quality=70, optimize=True, progressive=True)
            r.save(tmp)
            avif(tmp, base + ".avif", 38)
            web += ["web/%s-%d.%s" % (sid, w, x) for x in ("avif", "webp", "jpg")]
        fit(im, 1920, 1080).save(os.path.join(OUT, "stream", sid + ".webp"), "WEBP", quality=82, method=6)
        manifest.append({"id": sid, "tag": k["tag"], "region": k.get("region", ""), "alt": k["alt"][:125], "prompt": k["prompt"], "model": "FLUX schnell",
                         "seed": k.get("seed"), "date": k.get("date", ""), "host": k.get("host", ""), "licence": LICENCE, "label": "Illustration",
                         "web": web, "stream": "stream/%s.webp" % sid, "judge_notes": k.get("judge_notes", ""), "corner_check": k.get("corner_check", "")})
    if os.path.exists(tmp):
        os.remove(tmp)
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": "in-house", "count": len(manifest), "items": manifest}, f, separators=(",", ":"))
    return manifest


if __name__ == "__main__":
    keep = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "design", "keep.json")))
    m = build(keep)
    print("built %d stills" % len(m))
