import csv
import io
import re
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

# === SETTINGS ===
CSV_FILE = "links.csv"        # your CSV file (change this to your actual filename)
OUTPUT_FOLDER = "downloads"   # where images will be saved
MAX_WORKERS = 10              # number of parallel downloads (try 10-20)
TIMEOUT = 30                  # request timeout in seconds
JPEG_QUALITY = 90             # quality for the converted JPG (1-100)
TARGET_SIZE = (1080, 1080)    # final canvas size (width, height) in pixels
BG_COLOR = (255, 255, 255)    # padding/background color (white)

# Create downloads folder
out_dir = Path(OUTPUT_FOLDER)
out_dir.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str) -> str:
    """Make sure filenames are safe for Windows."""
    return re.sub(r'[\/:*?"<>|]', "_", name.strip()) or "unnamed"


def detect_columns(fieldnames):
    """
    Find all 'serial'-style columns and all 'link/image'-style columns,
    in the order they appear in the CSV header.
    """
    serial_cols, link_cols = [], []
    for col in fieldnames:
        if not col:
            continue
        key = col.strip().lower().replace(" ", "")
        if "serial" in key:
            serial_cols.append(col)
        elif "link" in key or "image" in key:
            link_cols.append(col)
    return serial_cols, link_cols


def load_tasks(csv_file):
    """
    Build a flat list of (row_index, name, url) download tasks.

    Supports two layouts:
      1) Simple: one 'serial' column + one 'links' column (old format).
      2) Grouped: a base serial column + several sub-serial columns
         (serial 1, serial 2, serial 3, ...) and several link columns
         (Image Link 1, Image Link 2, ...). The first serial column is
         treated as the row's base id and is NOT downloaded on its own;
         each link column is paired, in left-to-right order, with the
         next sub-serial column to form the saved filename.
         e.g. serial 1=1, serial 2=1.1, serial 3=1.2 ... + Image Link 1, Image Link 2 ...
              -> saved as 1.1.jpg, 1.2.jpg, ...
    """
    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t"])
        except csv.Error:
            dialect = csv.excel  # fall back to comma-separated

        reader = csv.DictReader(f, dialect=dialect)
        print("\nDetected columns:", reader.fieldnames)

        serial_cols, link_cols = detect_columns(reader.fieldnames)
        if not serial_cols or not link_cols:
            print("\nERROR: Could not find serial/link-style columns.")
            print("Make sure your CSV has columns with 'serial' and 'link' (or 'image') in their names.")
            raise SystemExit(1)

        print(f"Serial columns: {serial_cols}")
        print(f"Link columns:   {link_cols}\n")

        # If there's more than one serial column, the first is the row's
        # base id and the rest are the per-image sub-ids.
        sub_serial_cols = serial_cols[1:] if len(serial_cols) > 1 else serial_cols

        tasks = []
        skipped = 0
        for row_index, row in enumerate(reader, start=1):
            for i, link_col in enumerate(link_cols):
                url = (row.get(link_col) or "").strip()
                if not url:
                    continue  # empty cell, nothing to download

                if i >= len(sub_serial_cols):
                    print(f"[Row {row_index}] No serial column available for '{link_col}' - skipping.")
                    skipped += 1
                    continue

                name = (row.get(sub_serial_cols[i]) or "").strip()
                if not name:
                    print(f"[Row {row_index}] Empty serial for '{link_col}' - skipping.")
                    skipped += 1
                    continue

                tasks.append((row_index, name, url))

        print(f"Total images to download: {len(tasks)} (skipped {skipped})\n")
        return tasks


def download_one(item):
    """Download a single image, convert it to a real JPG, and fit it onto a
    TARGET_SIZE white canvas without stretching (aspect ratio preserved,
    extra space padded with BG_COLOR)."""
    row_index, name, url = item
    filename = sanitize_filename(name)
    filepath = out_dir / f"{filename}.jpg"

    # Skip if already exists (good for resume / retries)
    if filepath.exists():
        return f"[Row {row_index}] {name} already exists, skipping."

    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()

        img = Image.open(io.BytesIO(resp.content))

        # Flatten any transparency onto a white background before saving as JPG
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
            background = Image.new("RGB", img.size, BG_COLOR)
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Scale to fit inside TARGET_SIZE while keeping the original aspect
        # ratio (no stretching/distortion), then center it on a fixed-size
        # canvas so every output file is exactly TARGET_SIZE.
        target_w, target_h = TARGET_SIZE
        scale = min(target_w / img.width, target_h / img.height)
        new_w, new_h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
        resized = img.resize((new_w, new_h), Image.LANCZOS)

        canvas = Image.new("RGB", TARGET_SIZE, BG_COLOR)
        paste_x = (target_w - new_w) // 2
        paste_y = (target_h - new_h) // 2
        canvas.paste(resized, (paste_x, paste_y))
        img = canvas

        img.save(filepath, "JPEG", quality=JPEG_QUALITY)

        return f"[Row {row_index}] Downloaded {name} -> {filepath}"
    except Exception as e:
        return f"[Row {row_index}] ERROR for {name} ({url}): {e}"


def main():
    tasks = load_tasks(CSV_FILE)
    if not tasks:
        print("No valid rows found. Nothing to download.")
        return

    print(f"Starting parallel downloads with {MAX_WORKERS} workers...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_one, item): item for item in tasks}
        for future in as_completed(futures):
            print(future.result())

    print("\nAll done!")


if __name__ == "__main__":
    main()