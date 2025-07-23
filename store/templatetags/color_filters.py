from django import template

register = template.Library()

def hex_to_rgb(value):
    value = value.lstrip('#')
    lv = len(value)
    return tuple(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))

@register.filter
def contrast_text(hex_color):
    try:
        rgb = hex_to_rgb(hex_color)
        luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2])
        return '#fff' if luminance < 128 else '#111'
    except Exception:
        return '#111'