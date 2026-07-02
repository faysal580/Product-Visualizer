import os
from PIL import Image

# Folders
input_folder = "input"
output_folder = "output"
os.makedirs(output_folder, exist_ok=True)

SIZE = (1080, 1080)   # final resolution
MAX_FILESIZE = 940 * 1024  # 940 KB in bytes
VALID_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"]

def save_with_max_size(img, output_path, max_filesize, min_quality=20):
    """
    Save image as JPG with highest quality possible under max_filesize.
    """
    quality = 95
    while quality >= min_quality:
        img.save(output_path, "JPEG", quality=quality, optimize=True)
        if os.path.getsize(output_path) <= max_filesize:
            return True
        quality -= 5
    return False

for filename in os.listdir(input_folder):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in VALID_EXTENSIONS:
        continue

    input_path = os.path.join(input_folder, filename)
    output_name = os.path.splitext(filename)[0] + ".jpg"
    output_path = os.path.join(output_folder, output_name)

    try:
        img = Image.open(input_path).convert("RGB")
        w, h = img.size

        # Step 1: Make image square with padding
        max_side = max(w, h)
        square_bg = Image.new("RGB", (max_side, max_side), (255, 255, 255))
        offset = ((max_side - w) // 2, (max_side - h) // 2)
        square_bg.paste(img, offset)

        # Step 2: Resize square to 1080x1080
        final_img = square_bg.resize(SIZE, Image.Resampling.LANCZOS)

        # Save with max size restriction
        if save_with_max_size(final_img, output_path, MAX_FILESIZE):
            print(f"✅ Saved {output_path} under 940KB")
        else:
            print(f"⚠️ Could not keep {output_path} under {MAX_FILESIZE/1024:.0f}KB (used min quality)")

    except Exception as e:
        print(f"❌ Error processing {filename}: {e}")
