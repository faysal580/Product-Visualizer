import os
import win32com.client

# =====================================
# 🔧 CHANGE THESE VALUES ANYTIME
# =====================================
TARGET_WIDTH  = 1080     # target box width (px)
TARGET_HEIGHT = 826      # target box height (px)
TARGET_X      = 0        # target box left (px)
TARGET_Y      = 254        # target box top (px)
# =====================================

# === Setup paths ===
input_folder   = os.path.abspath("input")
output_folder  = os.path.abspath("output")
template_path  = os.path.abspath("May campaign.psd")

os.makedirs(output_folder, exist_ok=True)

# === Start Photoshop ===
psApp = win32com.client.Dispatch("Photoshop.Application")
psApp.DisplayDialogs = 3
psApp.Preferences.RulerUnits = 1  # pixels

def process_image(psApp, input_path, template_path, output_folder):
    try:
        if not os.path.exists(input_path):
            print(f"❌ File not found: {input_path}")
            return False

        # Open template PSD
        doc = psApp.Open(template_path)

        # Remove old image layer (if exists)
        for layer in doc.Layers:
            if layer.Name.lower() == "image":
                layer.Delete()
                break

        # Open input image and duplicate into PSD
        placed_file = psApp.Open(input_path)
        placed_layer = placed_file.ActiveLayer.Duplicate(doc, 2)  # 2 = place at beginning-ish
        placed_file.Close(2)  # 2 = don't save
        placed_layer.Name = "image"

        # Ensure "image" is selected before JS runs (extra safety)
        doc.ActiveLayer = placed_layer

        # FIT (no stretch) + CENTER inside target box
        psApp.DoJavaScript(f"""
        #target photoshop
        var doc = app.activeDocument;

        function findLayerByName(nameLower) {{
            for (var i = 0; i < doc.layers.length; i++) {{
                if (doc.layers[i].name.toLowerCase() === nameLower) return doc.layers[i];
            }}
            return null;
        }}

        var layer = findLayerByName("image");
        if (!layer) throw new Error("Layer 'image' not found");

        // Current bounds
        var b = layer.bounds;
        var w = b[2].as("px") - b[0].as("px");
        var h = b[3].as("px") - b[1].as("px");

        // Uniform scale (NO STRETCH): FIT inside target box
        var scaleW = {TARGET_WIDTH} / w;
        var scaleH = {TARGET_HEIGHT} / h;
        var scale = Math.min(scaleW, scaleH) * 100;

        layer.resize(scale, scale, AnchorPosition.MIDDLECENTER);

        // Recalc bounds after resize
        b = layer.bounds;
        var newW = b[2].as("px") - b[0].as("px");
        var newH = b[3].as("px") - b[1].as("px");

        // Target center
        var targetCenterX = {TARGET_X} + ({TARGET_WIDTH} / 2);
        var targetCenterY = {TARGET_Y} + ({TARGET_HEIGHT} / 2);

        // Layer center
        var layerCenterX = b[0].as("px") + (newW / 2);
        var layerCenterY = b[1].as("px") + (newH / 2);

        // Move to center
        layer.translate(targetCenterX - layerCenterX, targetCenterY - layerCenterY);

        // Keep sticker on top (if exists)
        var sticker = findLayerByName("sticker");
        if (sticker) {{
            sticker.move(layer, ElementPlacement.PLACEBEFORE); // place above image
        }}
        """)

        # Save JPG
        base = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(output_folder, base + ".jpg")

        jpg_options = win32com.client.Dispatch("Photoshop.JPEGSaveOptions")
        jpg_options.Quality = 12

        doc.SaveAs(output_path, jpg_options, True)
        doc.Close(2)  # don't save PSD

        print(f"✔ Saved: {output_path}")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        try:
            doc.Close(2)
        except:
            pass
        return False


# === Process each file ===
success = 0
for filename in os.listdir(input_folder):
    if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
        if process_image(psApp, os.path.join(input_folder, filename), template_path, output_folder):
            success += 1

print(f"\n🎉 Completed! {success} images processed.")
