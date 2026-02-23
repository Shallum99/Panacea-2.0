"""Test width mismatch: sum of word widths vs full line width."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
env_path = os.path.join(os.path.dirname(__file__), ".env")
for line in open(env_path):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import fitz
from app.services.pdf_format_preserver import _CMapManager, _WidthCalculator

PDF = "uploads/resumes/2d425a7058c54b2aad6c8e29bc22ef81_Shallum Maryapanor - Full Stack Software Developer-1 (1).pdf"
doc = fitz.open(PDF)

cmap_mgr = _CMapManager(doc)
width_calc = _WidthCalculator(doc)

# Find a bullet font - use the first font found
print("Available fonts:")
for tag, name in sorted(cmap_mgr.font_names.items()):
    n_fwd = len(cmap_mgr.font_cmaps.get(tag, {}).get("fwd", {}))
    n_widths = len(width_calc.font_widths.get(tag, {}))
    dw = width_calc._default_widths.get(tag, "N/A")
    print(f"  {tag}: {name} ({n_fwd} mappings, {n_widths} widths, default_w={dw})")

# Use largest font (most mappings = body text font)
bullet_font = max(cmap_mgr.font_cmaps.keys(),
                  key=lambda t: len(cmap_mgr.font_cmaps[t].get("fwd", {})))
print(f"\nUsing font: {bullet_font} ({cmap_mgr.font_names.get(bullet_font)})")

font_data = cmap_mgr.font_cmaps.get(bullet_font, {})
byte_width = font_data.get("byte_width", 2)
hex_per_char = byte_width * 2
widths_map = width_calc.font_widths.get(bullet_font, {})
default_w = width_calc._default_widths.get(bullet_font, 1000.0)

def calc_hex_width(hex_str):
    total = 0.0
    for ci in range(0, len(hex_str), hex_per_char):
        if ci + hex_per_char > len(hex_str):
            break
        cid = int(hex_str[ci:ci + hex_per_char], 16)
        total += widths_map.get(cid, default_w)
    return total

# Test text
test_line = "pricing, waivers, and proration logic; integrated COGS calculations and gross margin analysis to provide end-to-end financial visibility across all fee structures"
words = test_line.split()

# Space
space_hex, space_miss = cmap_mgr.encode_text(bullet_font, " ")
space_w = calc_hex_width(space_hex) if space_hex else default_w
print(f"\nSpace: hex='{space_hex}', missing={space_miss}, width={space_w}")

# Per-word sum
sum_w = 0.0
word_details = []
for i, word in enumerate(words):
    w_hex, w_miss = cmap_mgr.encode_text(bullet_font, word)
    w_w = calc_hex_width(w_hex) if w_hex else default_w * len(word)
    if i > 0:
        sum_w += space_w
    sum_w += w_w
    word_details.append((word, w_w, len(w_hex)//hex_per_char if w_hex else 0, len(word), w_miss))

# Full line
full_hex, full_miss = cmap_mgr.encode_text(bullet_font, test_line)
full_w = calc_hex_width(full_hex) if full_hex else 0

# Concat per-word hex
concat_hex = ""
for i, word in enumerate(words):
    if i > 0:
        concat_hex += space_hex
    w_hex, _ = cmap_mgr.encode_text(bullet_font, word)
    concat_hex += w_hex
concat_w = calc_hex_width(concat_hex)

print(f"\n{'='*60}")
print(f"Per-word sum (greedy method):  {sum_w:.0f}")
print(f"Concat hex width:             {concat_w:.0f}")
print(f"Full line encoding width:     {full_w:.0f}")
print(f"DIFF (full - sum):            {full_w - sum_w:.0f} ({(full_w/max(sum_w,1) - 1)*100:.1f}%)")
print(f"DIFF (full - concat):         {full_w - concat_w:.0f}")
print(f"{'='*60}")
print(f"Full hex len:   {len(full_hex)} ({len(full_hex)//hex_per_char} chars)")
print(f"Concat hex len: {len(concat_hex)} ({len(concat_hex)//hex_per_char} chars)")
print(f"Text char count: {len(test_line)}")
print(f"Full missing: {full_miss}")

if len(full_hex) != len(concat_hex):
    extra = (len(full_hex) - len(concat_hex)) // hex_per_char
    print(f"\n*** EXTRA CHARS in full encoding: {extra}")
    print(f"    These are likely spaces that got separate CID encodings")
    # Check: are the extra chars all spaces?
    # full_hex encodes all chars including spaces between words
    # concat_hex encodes words separately then joins with space_hex
    # They should be identical IF encode_text is character-by-character

doc.close()
