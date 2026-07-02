import csv
import requests
import re
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

# === SETTINGS ===
CSV_FILE = "links.csv"        # your CSV file
OUTPUT_FOLDER = "downloads"   # where images will be saved
MAX_WORKERS = 10              # number of parallel downloads (try 10–20)
TIMEOUT = 30                  # request timeout in seconds
CANVAS_SIZE = 1080            # final square canvas size in pixels
JPEG_QUALITY = 95             # 1-100, higher = better quality (95 is visually lossless)

# Create downloads folder
out_dir = Path(OUTPUT_FOLDER)
out_dir.mkdir(parents=True, exist_ok=True)

def sanitize_filename(name: str) -> str:
    """Make sure filenames are safe for Windows."""
    return re.sub(r'[\/:*?"<>|]', "_", name.strip()) or "unnamed"

def find_column(fieldnames, keyword):
    """Find column containing keyword (case-insensitive, ignores spaces)."""
    keyword = keyword.lower()
    for col in fieldnames:
        if col and keyword in col.strip().lower().replace(" ", ""):
            return col
    return None

def load_rows(csv_file):
    """Read CSV and return list of (row_index, serial, url)."""
    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)

        # auto-detect delimiter (comma, semicolon, tab)
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t"])
        reader = csv.DictReader(f, dialect=dialect)

        print("\nDetected columns:", reader.fieldnames)

        serial_col = find_column(reader.fieldnames, "serial")
        url_col = find_column(reader.fieldnames, "link")

        if not serial_col or not url_col:
            print("\nERROR: Could not find columns for SERIAL or LINKS.")
            print("Make sure your CSV has something like:")
            print("serial,links")
            raise SystemExit(1)

        print(f"Using serial column: {serial_col}")
        print(f"Using links column:  {url_col}\n")

        rows = []
        for i, row in enumerate(reader, start=1):
            serial = str(row.get(serial_col, "")).strip()
            url = str(row.get(url_col, "")).strip()
            if not serial or not url:
                print(f"[Row {i}] Missing serial or link — skipping.")
                continue
            rows.append((i, serial, url))

        print(f"Total valid rows to download: {len(rows)}\n")
        return rows

def flatten_to_white(img: Image.Image) -> Image.Image:
    """Convert any image mode to RGB. If it has transparency, composite it onto a white background instead of just dropping the alpha channel."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")

def fit_on_square_canvas(img: Image.Image, size: int) -> Image.Image:
    """
    Resize image to fit fully inside a size x size box, keeping its original
    aspect ratio (no stretching/cropping), then center it on a white
    size x size canvas. Small images are upscaled too, so every output
    file ends up exactly size x size.
    """
    img = flatten_to_white(img)
    w, h = img.size
    scale = size / max(w, h)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))

    # LANCZOS gives the sharpest result for both downscaling and upscaling
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    offset = ((size - new_w) // 2, (size - new_h) // 2)
    canvas.paste(resized, offset)
    return canvas

def download_one(item):
    """Download a single image, fit it onto a white square canvas, save as high-quality JPG."""
    row_index, serial, url = item
    filename = sanitize_filename(serial)
    filepath = out_dir / f"{filename}.jpg"

    # Skip if already exists (good for resume / retries)
    if filepath.exists():
        return f"[Row {row_index}] {serial} already exists, skipping."

    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()

        img = Image.open(BytesIO(resp.content))
        img.load()  # force decode now, so corrupt/truncated files error out here

        final_img = fit_on_square_canvas(img, CANVAS_SIZE)

        # quality=95 + subsampling=0 keeps full color detail (no visible quality loss)
        final_img.save(filepath, "JPEG", quality=JPEG_QUALITY, subsampling=0, optimize=True)

        return f"[Row {row_index}] Downloaded {serial} -> {filepath}"
    except Exception as e:
        return f"[Row {row_index}] ERROR for {serial}: {e}"

def main():
    rows = load_rows(CSV_FILE)
    if not rows:
        print("No valid rows found. Nothing to download.")
        return

    print(f"Starting parallel downloads with {MAX_WORKERS} workers...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_one, item): item for item in rows}
        for future in as_completed(futures):
            msg = future.result()
            print(msg)

    print("\nAll done!")

if __name__ == "__main__":
    main()
