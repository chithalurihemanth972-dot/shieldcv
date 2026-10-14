"""
Fetch the real-photo "checkpoint" demo corpus from Wikimedia Commons.

Run ONCE on a connected machine; everything after this is offline. Downloads
small thumbnails (256 px) of freely-licensed photos for four classes a
checkpoint camera would see, and records author/licence/source for every file
in ``attribution.csv`` so the corpus can be shown and credited.

    python demo/fetch_checkpoint_data.py [--per-class 180] [--out demo/data/checkpoint_raw]

Output layout::

    <out>/<class>/<pageid>.jpg
    <out>/attribution.csv

The raw pool is noisy (a category page also holds diagrams, scans and photos
where the object is incidental); ``demo/build_checkpoint_dataset.py`` filters
and curates it into the demo dataset.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = ("SHIELD-CV-demo/1.0 (offline integrity-assurance hackathon demo; "
              "https://github.com/chithalurihemanth972-dot/shieldcv.io)")

# Class -> Commons categories (files directly in them; no recursion).
CLASSES: Dict[str, List[str]] = {
    "bottle": ["Water_bottles", "Plastic_bottles", "PET_bottles", "Drinking_water_bottles"],
    "grenade": ["Hand_grenades", "Fragmentation_grenades", "Stick_grenades",
                "Hand_grenades_of_the_United_States", "Hand_grenades_of_Germany",
                "Hand_grenades_of_Switzerland", "Hand_grenades_of_Poland",
                "Hand_grenades_of_the_Soviet_Union", "Hand_grenades_in_Auckland_Museum",
                "Hand_grenades_in_the_National_World_War_I_Museum",
                "Hand_grenades_in_the_Musée_de_l'armée", "Hand_grenades_of_Italy",
                "Hand_grenades_of_Argentina", "HG_85", "Hand_grenades_of_China",
                "Hand_grenades_of_the_United_Kingdom", "Hand_grenades_of_Russia",
                "Hand_grenades_of_Israel", "Hand_grenades_of_Austria", "L109A2_Grenade",
                "Hand_grenades_of_Japan", "Hand_grenades_of_France",
                "Hand_grenades_of_Finland", "RG-4", "Hand_grenades_of_Spain",
                "Hand_grenades_of_Indonesia", "Hand_grenades_of_Denmark",
                "L109_HE_Grenade", "Hand_grenades_of_Ukraine"],
    "phone": ["Smartphones", "Mobile_phones", "Feature_phones"],
    "backpack": ["Backpacks", "Rucksacks", "School_bags"],
}
ALLOWED_LICENCES = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? [0-9.]+|cc by(-sa)?)", re.I)


def api(params: Dict[str, str]) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json"})
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        import json
        return json.loads(response.read().decode("utf-8"))


def category_files(category: str, limit: int = 500) -> List[str]:
    data = api({"action": "query", "list": "categorymembers", "cmtype": "file",
                "cmtitle": f"Category:{category}", "cmlimit": str(limit)})
    titles = [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
    return [t for t in titles if t.lower().endswith((".jpg", ".jpeg", ".png"))]


def chunks(items: List[str], size: int) -> Iterable[List[str]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def image_infos(titles: List[str]) -> List[dict]:
    out = []
    for batch in chunks(titles, 40):
        data = api({"action": "query", "titles": "|".join(batch), "prop": "imageinfo",
                    "iiprop": "url|extmetadata|mime", "iiurlwidth": "256"})
        for page in data.get("query", {}).get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            licence = strip_tags(meta.get("LicenseShortName", {}).get("value", ""))
            if not info.get("thumburl") or not ALLOWED_LICENCES.match(licence):
                continue
            out.append({
                "pageid": page.get("pageid"), "title": page.get("title", ""),
                "thumb": info["thumburl"], "source": info.get("descriptionurl", ""),
                "artist": strip_tags(meta.get("Artist", {}).get("value", ""))[:120],
                "licence": licence,
            })
        time.sleep(0.2)
    return out


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--per-class", type=int, default=180)
    parser.add_argument("--out", default="demo/data/checkpoint_raw")
    parser.add_argument("--classes", nargs="*", default=list(CLASSES),
                        help="subset of classes to fetch (attribution rows for the "
                             "others are preserved)")
    args = parser.parse_args()

    from PIL import Image

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    attribution = out / "attribution.csv"
    if attribution.exists():
        with open(attribution, newline="", encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r["class"] not in args.classes]
    for name, categories in CLASSES.items():
        if name not in args.classes:
            continue
        folder = out / name
        folder.mkdir(exist_ok=True)
        titles: List[str] = []
        for category in categories:
            try:
                titles += [t for t in category_files(category) if t not in titles]
            except Exception as exc:
                print(f"  ! {category}: {exc}")
        infos = image_infos(titles)
        print(f"{name}: {len(titles)} files listed, {len(infos)} with an open licence")
        kept = 0
        for info in infos:
            if kept >= args.per_class:
                break
            target = folder / f"{info['pageid']}.jpg"
            try:
                if not target.exists():
                    data = download(info["thumb"])
                    # Re-encode through PIL: guarantees a plain RGB JPEG and
                    # rejects anything that is not actually an image.
                    with Image.open(io.BytesIO(data)) as image:
                        image.convert("RGB").save(target, quality=92)
                    time.sleep(0.1)
                kept += 1
                rows.append({"class": name, "file": f"{name}/{target.name}", **info})
            except Exception as exc:
                print(f"  ! {info['title']}: {exc}")
        print(f"  saved {kept}")

    with open(out / "attribution.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["class", "file", "pageid", "title", "artist",
                                                "licence", "source", "thumb"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"done: {len(rows)} images -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
