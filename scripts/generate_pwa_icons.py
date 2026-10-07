import cairo
import math
from PIL import Image

def draw_tennis_icon(ctx, size=512, maskable=False):
    # Base canvas coordinate system: 512x512
    scale = size / 512.0
    ctx.scale(scale, scale)

    # 1. Background
    ctx.rectangle(0, 0, 512, 512)
    # Radial background gradient from court green to deep court green
    bg_pat = cairo.RadialGradient(256, 220, 40, 256, 256, 360)
    bg_pat.add_color_stop_rgb(0.0, 0.169, 0.318, 0.255)  # #2B5141
    bg_pat.add_color_stop_rgb(1.0, 0.118, 0.231, 0.184)  # #1E3B2F
    ctx.set_source(bg_pat)
    ctx.fill()

    # Content scaling for maskable icons (keep inside safe 80% circle)
    ctx.save()
    if maskable:
        # Scale to 72% and center
        ctx.translate(256, 256)
        ctx.scale(0.72, 0.72)
        ctx.translate(-256, -256)

    # 2. Court lines in background
    # Clay court accent arc (subtle warmth)
    ctx.save()
    ctx.arc(256, 512, 280, math.pi * 1.1, math.pi * 1.9)
    ctx.set_source_rgba(0.725, 0.306, 0.200, 0.35)  # #B94E33 with alpha
    ctx.set_line_width(24)
    ctx.stroke()
    ctx.restore()

    # Court baseline & center service line (white chalk)
    ctx.save()
    ctx.set_source_rgba(1.0, 1.0, 1.0, 0.25)
    ctx.set_line_width(8)
    # Horizontal baseline
    ctx.move_to(40, 390)
    ctx.line_to(472, 390)
    ctx.stroke()
    # Vertical center service line
    ctx.move_to(256, 120)
    ctx.line_to(256, 460)
    ctx.stroke()
    ctx.restore()

    # 3. Tennis Ball
    ball_cx = 256
    ball_cy = 240
    ball_r = 125

    # Ball shadow
    ctx.save()
    ctx.translate(ball_cx + 10, ball_cy + 18)
    ctx.scale(1.0, 0.45)
    ctx.arc(0, 220, ball_r * 0.9, 0, 2 * math.pi)
    shadow_pat = cairo.RadialGradient(0, 220, 10, 0, 220, ball_r * 0.9)
    shadow_pat.add_color_stop_rgba(0.0, 0.05, 0.1, 0.08, 0.5)
    shadow_pat.add_color_stop_rgba(1.0, 0.05, 0.1, 0.08, 0.0)
    ctx.set_source(shadow_pat)
    ctx.fill()
    ctx.restore()

    # Ball body with radial gradient (lit from top-left)
    ctx.save()
    ctx.arc(ball_cx, ball_cy, ball_r, 0, 2 * math.pi)
    ball_pat = cairo.RadialGradient(
        ball_cx - 45, ball_cy - 45, 15,
        ball_cx, ball_cy, ball_r
    )
    # #EDF67D -> #D7E64A -> #A8B826
    ball_pat.add_color_stop_rgb(0.0, 0.93, 0.965, 0.49)
    ball_pat.add_color_stop_rgb(0.55, 0.843, 0.902, 0.290)
    ball_pat.add_color_stop_rgb(1.0, 0.659, 0.722, 0.149)
    ctx.set_source(ball_pat)
    ctx.fill_preserve()

    # Clip to ball for the seam lines
    ctx.clip()

    # Tennis ball seams (white lines with depth)
    ctx.set_source_rgba(1.0, 1.0, 1.0, 0.95)
    ctx.set_line_width(12)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)

    # Seam 1 (left/top arc)
    ctx.move_to(ball_cx - ball_r - 10, ball_cy - 60)
    ctx.curve_to(
        ball_cx - 40, ball_cy - 85,
        ball_cx - 15, ball_cy + 40,
        ball_cx - 85, ball_cy + ball_r + 10
    )
    ctx.stroke()

    # Seam 2 (right/bottom arc)
    ctx.move_to(ball_cx + 85, ball_cy - ball_r - 10)
    ctx.curve_to(
        ball_cx + 15, ball_cy - 40,
        ball_cx + 40, ball_cy + 85,
        ball_cx + ball_r + 10, ball_cy + 60
    )
    ctx.stroke()

    # Inner seam shadow for realistic tennis ball groove
    ctx.set_source_rgba(0.55, 0.62, 0.12, 0.35)
    ctx.set_line_width(4)
    ctx.move_to(ball_cx - ball_r - 10, ball_cy - 60)
    ctx.curve_to(
        ball_cx - 40, ball_cy - 85,
        ball_cx - 15, ball_cy + 40,
        ball_cx - 85, ball_cy + ball_r + 10
    )
    ctx.stroke()

    ctx.move_to(ball_cx + 85, ball_cy - ball_r - 10)
    ctx.curve_to(
        ball_cx + 15, ball_cy - 40,
        ball_cx + 40, ball_cy + 85,
        ball_cx + ball_r + 10, ball_cy + 60
    )
    ctx.stroke()

    ctx.restore()  # End clip

    # 4. Stylized Breakpoint "Chevron / Energy Spark" at bottom right
    # Emphasizes "Breakpoint" precision
    ctx.save()
    ctx.move_to(320, 335)
    ctx.line_to(360, 365)
    ctx.line_to(342, 368)
    ctx.line_to(372, 405)
    ctx.line_to(338, 380)
    ctx.line_to(350, 376)
    ctx.close_path()
    spark_pat = cairo.LinearGradient(320, 335, 372, 405)
    spark_pat.add_color_stop_rgb(0.0, 0.843, 0.902, 0.290)  # #D7E64A
    spark_pat.add_color_stop_rgb(1.0, 0.725, 0.306, 0.200)  # #B94E33
    ctx.set_source(spark_pat)
    ctx.fill()
    ctx.restore()

    # 5. Clean "BREAKPOINT" or "BP" Lettering badge (minimalist at top or bottom)
    # Using simple geometry for high rendering crispness without font dependencies
    ctx.save()
    ctx.set_source_rgba(1.0, 1.0, 1.0, 0.90)
    # Subtle crisp underline at bottom
    ctx.set_line_width(3)
    ctx.move_to(196, 428)
    ctx.line_to(316, 428)
    ctx.stroke()
    ctx.restore()

    ctx.restore() # End maskable scale

def main():
    import os
    out_dir = "static/icons"
    os.makedirs(out_dir, exist_ok=True)

    # 1. Render SVG
    svg_path = os.path.join(out_dir, "icon.svg")
    svg_surface = cairo.SVGSurface(svg_path, 512, 512)
    svg_ctx = cairo.Context(svg_surface)
    draw_tennis_icon(svg_ctx, 512, maskable=False)
    svg_surface.finish()
    print(f"Generated {svg_path}")

    # 2. Render 512x512 PNG
    p512_path = os.path.join(out_dir, "icon-512x512.png")
    surface512 = cairo.ImageSurface(cairo.FORMAT_ARGB32, 512, 512)
    ctx512 = cairo.Context(surface512)
    draw_tennis_icon(ctx512, 512, maskable=False)
    surface512.write_to_png(p512_path)
    print(f"Generated {p512_path}")

    # 3. Render 192x192 PNG
    p192_path = os.path.join(out_dir, "icon-192x192.png")
    surface192 = cairo.ImageSurface(cairo.FORMAT_ARGB32, 192, 192)
    ctx192 = cairo.Context(surface192)
    draw_tennis_icon(ctx192, 192, maskable=False)
    surface192.write_to_png(p192_path)
    print(f"Generated {p192_path}")

    # 4. Render Apple Touch Icon (180x180)
    p180_path = os.path.join(out_dir, "apple-touch-icon.png")
    surface180 = cairo.ImageSurface(cairo.FORMAT_ARGB32, 180, 180)
    ctx180 = cairo.Context(surface180)
    draw_tennis_icon(ctx180, 180, maskable=False)
    surface180.write_to_png(p180_path)
    print(f"Generated {p180_path}")

    # 5. Render Maskable 512x512 PNG
    mask_path = os.path.join(out_dir, "icon-maskable-512x512.png")
    surface_mask = cairo.ImageSurface(cairo.FORMAT_ARGB32, 512, 512)
    ctx_mask = cairo.Context(surface_mask)
    draw_tennis_icon(ctx_mask, 512, maskable=True)
    surface_mask.write_to_png(mask_path)
    print(f"Generated {mask_path}")

    # 6. Render favicon (32x32 & 16x16 ico)
    p32_path = os.path.join(out_dir, "favicon-32x32.png")
    surface32 = cairo.ImageSurface(cairo.FORMAT_ARGB32, 32, 32)
    ctx32 = cairo.Context(surface32)
    draw_tennis_icon(ctx32, 32, maskable=False)
    surface32.write_to_png(p32_path)

    img = Image.open(p512_path)
    ico_path = os.path.join(out_dir, "favicon.ico")
    img.resize((32, 32), Image.Resampling.LANCZOS).save(ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"Generated {ico_path}")

if __name__ == "__main__":
    main()
