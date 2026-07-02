import csv
import re
import requests
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

# === SETTINGS ===
CSV_FILE = "links.csv"        # your CSV file (serial,links)
OUTPUT_FOLDER = "downloads"   # where images will be saved
MAX_WORKERS = 10              # parallel downloads (try 10–20)
TIMEOUT = 30                  # request timeout in seconds
JPEG_QUALITY = 95             # 1–100, higher = better (95 is visually lossless)

out_dir = Path(OUTPUT_FOLDER)
out_dir.mkdir(parents=True, exist_ok=True)

def sanitize_filename(name: str) -> str:
    """Strip characters that are illegal in Windows filenames."""
    return re.sub(r'[\/:*?"<>|]', "_", name.strip()) or "unnamed"

def clean_url(raw: str) -> str | None:
    """
    Strip trailing junk (CSS inline styles, query noise) from a URL and
    return a clean https:// URL, or None if the URL looks invalid.
    """
    # Cut off anything that looks like inline CSS appended to the URL
    # e.g. "https://…/foo.jpg style=width:…" or "https://…/foo.jpgstyle=…"
    raw = re.split(r'\s*style\s*=', raw, maxsplit=1)[0].strip()

    # Must start with http
    if not raw.lower().startswith("http"):
        return None

    parsed = urlparse(raw)
    # Must have a real host
    if not parsed.netloc:
        return None

    # Rebuild cleanly (drop query string & fragment — CDN images don't need them)
    clean = parsed._replace(query="", fragment="").geturl()
    return clean

def filename_from_url(url: str, row_index: int) -> str:
    """
    Extract the image stem from the URL path.
    e.g. https://cdn.example.com/p/e65e7dfb8b91e8fc44ece84a6ca1d6aa.jpg
         → e65e7dfb8b91e8fc44ece84a6ca1d6aa
    Falls back to image_row<N> if nothing useful is found.
    """
    try:
        path = unquote(urlparse(url).path)
        stem = Path(path).stem
        if stem:
            return sanitize_filename(stem)
    except Exception:
        pass
    return f"image_row{row_index}"

def load_rows(csv_file):
    """Read CSV and return list of (row_index, url, save_stem)."""
    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t"])
        reader = csv.DictReader(f, dialect=dialect)

        # Find the links column (any column whose name contains "link" or "url")
        url_col = None
        for col in (reader.fieldnames or []):
            if col and re.search(r'link|url', col.strip(), re.IGNORECASE):
                url_col = col
                break

        if not url_col:
            print("ERROR: Could not find a column named 'links' or 'url' in your CSV.")
            raise SystemExit(1)

        print(f"Using URL column: '{url_col}'\n")

        rows = []
        skipped = 0
        for i, row in enumerate(reader, start=2):   # start=2 because row 1 is header
            raw_url = str(row.get(url_col, "")).strip()
            url = clean_url(raw_url)
            if not url:
                print(f"[Row {i}] Skipping invalid URL: {raw_url[:80]}")
                skipped += 1
                continue
            stem = filename_from_url(url, i)
            rows.append((i, url, stem))

        print(f"Valid rows: {len(rows)}   Skipped: {skipped}\n")
        return rows

# ── image helper ──────────────────────────────────────────────────────────────

def to_rgb(img: Image.Image) -> Image.Image:
    """Convert to RGB (required for JPEG). Transparency → white background."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")

# ── download worker ────────────────────────────────────────────────────────────

def download_one(item):
    row_index, url, stem = item
    filepath = out_dir / f"{stem}.jpg"

    if filepath.exists():
        return f"[Row {row_index}] '{stem}' already exists — skipped."

    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()

        img = Image.open(BytesIO(resp.content))
        img.load()

        # Convert to JPG without changing size or cropping
        img = to_rgb(img)
        img.save(filepath, "JPEG", quality=JPEG_QUALITY, subsampling=0, optimize=True)

        return f"[Row {row_index}] ✓  {stem}.jpg  ({img.width}×{img.height})"
    except Exception as e:
        return f"[Row {row_index}] ERROR ({stem}): {e}"

# ── main ───────────────────────────────────────────────────────────────────────

def main():
    rows = load_rows(CSV_FILE)
    if not rows:
        print("No valid URLs found. Nothing to download.")
        return

    print(f"Starting downloads ({MAX_WORKERS} workers)…\n")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_one, item): item for item in rows}
        for future in as_completed(futures):
            print(future.result())

    print("\nAll done!")

if __name__ == "__main__":
    main()
