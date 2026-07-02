import os
from io import BytesIO

import numpy as np
from PIL import Image
from rembg import remove, new_session
from scipy import ndimage

# ==========================================
# SETTINGS
# ==========================================

INPUT_DIR = "input"
OUTPUT_DIR = "output"

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1080

# Product fills about 92% of canvas
FIT_RATIO = 0.92

# Pure white background
BACKGROUND_COLOR = (255, 255, 255)

SUPPORTED_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff"
)

# ==========================================
# CREATE FOLDERS
# ==========================================

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# LOAD AI MODEL
# ==========================================

print("Loading AI model...")
session = new_session("isnet-general-use")
print("AI model loaded.")

# ==========================================
# PROCESS IMAGE
# ==========================================

def process_image(image_path):

    filename = os.path.basename(image_path)
    name = os.path.splitext(filename)[0]

    print(f"Processing: {filename}")

    # --------------------------------------
    # Read image
    # --------------------------------------

    with open(image_path, "rb") as f:
        input_bytes = f.read()

    # --------------------------------------
    # Remove background
    # --------------------------------------

    output_bytes = remove(
        input_bytes,
        session=session
    )

    subject = Image.open(
        BytesIO(output_bytes)
    ).convert("RGBA")

    # --------------------------------------
    # Remove weak shadow pixels
    # --------------------------------------

    alpha = np.array(
        subject.getchannel("A")
    )

    alpha[alpha < 30] = 0

    subject.putalpha(
        Image.fromarray(alpha)
    )

    # --------------------------------------
    # Remove small noise (connected components)
    # Components smaller than 0.5% of total
    # foreground are treated as noise —
    # larger detached parts (e.g. plug pins)
    # are intentionally kept.
    # --------------------------------------

    alpha = np.array(
        subject.getchannel("A")
    )

    binary = alpha > 15

    labeled, num_features = ndimage.label(binary)

    if num_features > 1:
        component_sizes = ndimage.sum(
            binary, labeled, range(1, num_features + 1)
        )
        total_fg = binary.sum()
        min_size = total_fg * 0.005  # 0.5% threshold

        for label_idx, size in enumerate(component_sizes, start=1):
            if size < min_size:
                alpha[labeled == label_idx] = 0

        subject.putalpha(
            Image.fromarray(alpha)
        )

    # --------------------------------------
    # Tight crop around subject
    # --------------------------------------

    alpha = np.array(
        subject.getchannel("A")
    )

    coords = np.argwhere(alpha > 15)

    if len(coords) == 0:
        print(f"Skipped: {filename}")
        return

    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)

    subject = subject.crop(
        (
            x_min,
            y_min,
            x_max + 1,
            y_max + 1
        )
    )

    # --------------------------------------
    # Resize while maintaining aspect ratio
    # --------------------------------------

    sw, sh = subject.size

    available_w = CANVAS_WIDTH * FIT_RATIO
    available_h = CANVAS_HEIGHT * FIT_RATIO

    scale = min(
        available_w / sw,
        available_h / sh
    )

    new_w = max(1, int(sw * scale))
    new_h = max(1, int(sh * scale))

    subject = subject.resize(
        (new_w, new_h),
        Image.LANCZOS
    )

    # --------------------------------------
    # Create white canvas
    # --------------------------------------

    canvas = Image.new(
        "RGB",
        (CANVAS_WIDTH, CANVAS_HEIGHT),
        BACKGROUND_COLOR
    )

    # --------------------------------------
    # Center subject
    # --------------------------------------

    x = (CANVAS_WIDTH - new_w) // 2
    y = (CANVAS_HEIGHT - new_h) // 2

    canvas.paste(
        subject,
        (x, y),
        subject
    )

    # --------------------------------------
    # Save as high quality JPG
    # --------------------------------------

    output_file = os.path.join(
        OUTPUT_DIR,
        f"{name}.jpg"
    )

    canvas.save(
        output_file,
        "JPEG",
        quality=100,
        subsampling=0,
        optimize=True
    )

    print(f"Saved: {output_file}")

# ==========================================
# MAIN
# ==========================================

def main():

    files = [
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(
            SUPPORTED_EXTENSIONS
        )
    ]

    if not files:
        print(
            f"No images found in '{INPUT_DIR}' folder."
        )
        print(
            f"Put images into '{INPUT_DIR}' and run again."
        )
        return

    print(f"Found {len(files)} image(s).")

    success = 0
    failed = 0

    for file in files:

        try:

            process_image(
                os.path.join(
                    INPUT_DIR,
                    file
                )
            )

            success += 1

        except Exception as e:

            failed += 1

            print(f"Error processing {file}")
            print(str(e))

    print("")
    print("================================")
    print("PROCESS COMPLETE")
    print("================================")
    print(f"Success : {success}")
    print(f"Failed  : {failed}")
    print(f"Output  : {OUTPUT_DIR}")
    print("================================")

if __name__ == "__main__":
    main()
