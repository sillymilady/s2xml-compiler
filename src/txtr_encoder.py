"""
txtr_encoder.py
Converts PNG/JPG images into Sims 2 TXTR (texture) and TXMT (material) resources.

TXTR format:
  uint32  version       0x08000000
  uint32  width
  uint32  height  
  uint32  mip_count     number of mipmap levels
  uint32  format        pixel format (see below)
  uint32  unknown       0x01
  for each mip level (largest first):
    uint32  data_size
    bytes   pixel_data

Pixel formats:
  0x01 = DXT1 (RGB, no alpha)  - 4 bits/pixel
  0x03 = DXT3 (RGBA)           - 8 bits/pixel  
  0x05 = DXT5 (RGBA smooth)    - 8 bits/pixel
  0x06 = 32-bit RGBA uncompressed

TXMT format:
  A text-based property list referencing the TXTR by name.
"""

import struct
import zlib
from pathlib import Path

TYPE_TXTR = 0x1C4A276C
TYPE_TXMT = 0x49596978

# DXT format codes
FMT_DXT1 = 0x01
FMT_DXT3 = 0x03  
FMT_DXT5 = 0x05
FMT_RAW  = 0x06


def _encode_dxt1(rgba_data: bytes, width: int, height: int) -> bytes:
    """
    Simple DXT1 encoder - converts RGBA pixels to DXT1 blocks.
    DXT1: 4x4 pixel blocks, 2 colors + 4-bit index per pixel = 8 bytes/block
    """
    out = bytearray()
    
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            # Gather 4x4 block of pixels
            block = []
            for py in range(4):
                for px in range(4):
                    x = min(bx + px, width - 1)
                    y = min(by + py, height - 1)
                    idx = (y * width + x) * 4
                    r, g, b, a = rgba_data[idx:idx+4]
                    block.append((r, g, b, a))
            
            # Find min/max colors in block
            r_vals = [p[0] for p in block]
            g_vals = [p[1] for p in block]
            b_vals = [p[2] for p in block]
            
            r0, r1 = max(r_vals), min(r_vals)
            g0, g1 = max(g_vals), min(g_vals)
            b0, b1 = max(b_vals), min(b_vals)
            
            # Pack as RGB565
            c0 = ((r0 >> 3) << 11) | ((g0 >> 2) << 5) | (b0 >> 3)
            c1 = ((r1 >> 3) << 11) | ((g1 >> 2) << 5) | (b1 >> 3)
            
            # Ensure c0 > c1 for DXT1 opaque mode
            if c0 < c1:
                c0, c1 = c1, c0
                r0, r1 = r1, r0
                g0, g1 = g1, g0
                b0, b1 = b1, b0
            
            # Build color lookup table
            if c0 != c1:
                colors = [
                    (r0, g0, b0),
                    (r1, g1, b1),
                    ((2*r0 + r1) // 3, (2*g0 + g1) // 3, (2*b0 + b1) // 3),
                    ((r0 + 2*r1) // 3, (g0 + 2*g1) // 3, (b0 + 2*b1) // 3),
                ]
            else:
                colors = [(r0, g0, b0), (r1, g1, b1), (0, 0, 0), (0, 0, 0)]
            
            # Find best color index for each pixel
            indices = 0
            for i, (r, g, b, a) in enumerate(block):
                best_idx = 0
                best_dist = float('inf')
                for ci, (cr, cg, cb) in enumerate(colors):
                    dist = (r-cr)**2 + (g-cg)**2 + (b-cb)**2
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = ci
                indices |= (best_idx << (i * 2))
            
            out += struct.pack("<HHI", c0, c1, indices)
    
    return bytes(out)


def _encode_raw_rgba(rgba_data: bytes, width: int, height: int) -> bytes:
    """Raw 32-bit RGBA - just return as-is (BGRA for DirectX)."""
    # Convert RGBA to BGRA
    out = bytearray(len(rgba_data))
    for i in range(0, len(rgba_data), 4):
        out[i]   = rgba_data[i+2]  # B
        out[i+1] = rgba_data[i+1]  # G
        out[i+2] = rgba_data[i]    # R
        out[i+3] = rgba_data[i+3]  # A
    return bytes(out)


def _make_mipmap(rgba_data: bytes, width: int, height: int, 
                 new_w: int, new_h: int) -> bytes:
    """Simple box-filter downscale."""
    out = bytearray(new_w * new_h * 4)
    x_ratio = width / new_w
    y_ratio = height / new_h
    
    for y in range(new_h):
        for x in range(new_w):
            # Sample 2x2 area
            r = g = b = a = 0
            count = 0
            for dy in range(2):
                for dx in range(2):
                    sx = min(int((x + dx * 0.5) * x_ratio), width - 1)
                    sy = min(int((y + dy * 0.5) * y_ratio), height - 1)
                    idx = (sy * width + sx) * 4
                    r += rgba_data[idx]
                    g += rgba_data[idx+1]
                    b += rgba_data[idx+2]
                    a += rgba_data[idx+3]
                    count += 1
            oi = (y * new_w + x) * 4
            out[oi]   = r // count
            out[oi+1] = g // count
            out[oi+2] = b // count
            out[oi+3] = a // count
    
    return bytes(out)


def image_to_txtr(image_path: str, fmt: str = "dxt1",
                  num_mipmaps: int = 4,
                  group_id: int = 0x1C0532FA,
                  instance_id: int = 0x00000001) -> tuple:
    """
    Convert a PNG/JPG to a TXTR resource.
    fmt: "dxt1" (no alpha), "raw" (full quality RGBA)
    Returns (type_id, group_id, instance_id, data_bytes)
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError(
            "Pillow is required for texture import.\n"
            "It should be installed automatically."
        )
    
    img = Image.open(image_path).convert("RGBA")
    
    # Resize to power of 2
    w, h = img.size
    pow2_w = 1
    while pow2_w < w: pow2_w <<= 1
    pow2_h = 1
    while pow2_h < h: pow2_h <<= 1
    
    if (pow2_w, pow2_h) != (w, h):
        img = img.resize((pow2_w, pow2_h), Image.LANCZOS)
        w, h = pow2_w, pow2_h
    
    fmt_code = FMT_DXT1 if fmt == "dxt1" else FMT_RAW
    
    # Generate mipmaps
    mip_levels = []
    cur_img = img
    cur_w, cur_h = w, h
    
    for mip in range(num_mipmaps):
        rgba = cur_img.tobytes()
        if fmt == "dxt1":
            encoded = _encode_dxt1(rgba, cur_w, cur_h)
        else:
            encoded = _encode_raw_rgba(rgba, cur_w, cur_h)
        mip_levels.append((cur_w, cur_h, encoded))
        
        # Halve for next mip
        next_w = max(1, cur_w // 2)
        next_h = max(1, cur_h // 2)
        if next_w < 4 or next_h < 4:
            break
        rgba_down = _make_mipmap(rgba, cur_w, cur_h, next_w, next_h)
        cur_img = Image.frombytes("RGBA", (next_w, next_h), rgba_down)
        cur_w, cur_h = next_w, next_h
    
    # Build TXTR binary
    header = struct.pack("<IIIIII",
        0x08000000,      # version
        w, h,
        len(mip_levels), # mip count
        fmt_code,
        0x01,            # unknown
    )
    
    mip_data = bytearray()
    for mw, mh, mdata in mip_levels:
        mip_data += struct.pack("<I", len(mdata))
        mip_data += mdata
    
    return (TYPE_TXTR, group_id, instance_id, header + bytes(mip_data))


def make_txmt(texture_name: str, material_name: str = "",
              group_id: int = 0x1C0532FA,
              instance_id: int = 0x00000002) -> tuple:
    """
    Generate a TXMT (material definition) resource that references a TXTR.
    texture_name: the name of the texture (without extension)
    Returns (type_id, group_id, instance_id, data_bytes)
    """
    if not material_name:
        material_name = texture_name
    
    # TXMT is a text-based property list
    txmt_text = f"""version {{
  0x00000003
}}
property {{
  name {{stdMatBaseTextureName}}
  value {{{texture_name}}}
}}
property {{
  name {{stdMatDiffCoef}}
  value {{0.5,0.5,0.5,1.0}}
}}
property {{
  name {{stdMatEmissiveCoef}}
  value {{0.0,0.0,0.0,1.0}}
}}
property {{
  name {{stdMatSpecCoef}}
  value {{1.0,1.0,1.0,1.0}}
}}
property {{
  name {{stdMatEnvCubeCoef}}
  value {{0.0,0.0,0.0,1.0}}
}}
property {{
  name {{stdMatAlphaMultiplier}}
  value {{1.0}}
}}
property {{
  name {{stdMatAlphaRefValue}}
  value {{0}}
}}
property {{
  name {{stdMatAlphaBlendMode}}
  value {{none}}
}}
property {{
  name {{stdMatCullMode}}
  value {{2}}
}}
property {{
  name {{stdMatWrapModeU}}
  value {{1}}
}}
property {{
  name {{stdMatWrapModeV}}
  value {{1}}
}}
property {{
  name {{stdMatShininess}}
  value {{5.0}}
}}
"""
    data = txmt_text.encode("latin-1")
    return (TYPE_TXMT, group_id, instance_id, data)
