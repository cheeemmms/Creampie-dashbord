from PIL import Image, ImageDraw, ImageFont
import time

FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"

def get_surface(width, height):
    img = Image.new('RGB', (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font_time = ImageFont.truetype(FONT_PATH, 55) # 很大很清晰的时分
        font_date = ImageFont.truetype(FONT_PATH, 18)
    except:
        font_time = font_date = ImageFont.load_default()

    # 只保留时和分
    time_hm = time.strftime("%H:%M")
    week_map = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    date_str = time.strftime("%m月%d日 ") + week_map[time.localtime().tm_wday]

    draw.text((12, 5), date_str, font=font_date, fill=(160, 160, 160))
    draw.text((8, 22), time_hm, font=font_time, fill=(255, 255, 255))
    
    draw.line([(0, height-1), (width, height-1)], fill=(0, 80, 150), width=2)
    return img