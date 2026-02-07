import requests, time
from PIL import Image, ImageDraw, ImageFont

# 缓存与配置
cache = {"last": 0, "city": "重庆", "temp": "--", "desc": "同步中"}
FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"

def get_surface(width, height):
    global cache
    now = time.time()
    
    # 30 分钟同步一次数据
    if now - cache["last"] > 1800:
        try:
            # 强制中文 &lang=zh
            r = requests.get("https://wttr.in/Chongqing?format=%l|%C|%t&lang=zh", timeout=5)
            if r.status_code == 200:
                parts = r.text.split('|')
                cache["desc"] = parts[1].strip()
                # 提取数字，去掉 + 号和 °C
                temp_val = parts[2].strip().replace('+', '').replace('°C', '')
                cache["temp"] = temp_val
                cache["last"] = now
        except:
            cache["desc"] = "同步中"

    img = Image.new('RGB', (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        # --- 字体字号与时间板块严格统一 ---
        font_big = ImageFont.truetype(FONT_PATH, 55)   # 与时间板块 55px 统一
        font_small = ImageFont.truetype(FONT_PATH, 18) # 与时间板块 18px 统一
        font_desc = ImageFont.truetype(FONT_PATH, 24)  # 天气描述稍小，跟在数字后
    except:
        font_big = font_small = font_desc = ImageFont.load_default()

    # 右边距
    margin_right = 10

    # 1. 绘制“重庆”（上方，与日期高度一致）
    city_str = cache["city"]
    bbox_city = draw.textbbox((0, 0), city_str, font=font_small)
    city_w = bbox_city[2] - bbox_city[0]
    draw.text((width - city_w - margin_right, 5), city_str, font=font_small, fill=(160, 160, 160))

    # 2. 绘制“气温 + 天气描述”（下方，与时间高度一致）
    # 组合字符串，例如 "12° 阴"
    temp_full_str = f"{cache['temp']}°"
    desc_str = cache["desc"]
    
    # 计算总宽度以实现右对齐
    bbox_temp = draw.textbbox((0, 0), temp_full_str, font=font_big)
    bbox_desc = draw.textbbox((0, 0), desc_str, font=font_desc)
    
    total_w = (bbox_temp[2] - bbox_temp[0]) + (bbox_desc[2] - bbox_desc[0]) + 10 # 10px是间距
    start_x = width - total_w - margin_right

    # 绘制气温数字
    draw.text((start_x, 22), temp_full_str, font=font_big, fill=(255, 255, 255))
    
    # 绘制天气描述 (颜色根据天气调整)
    color_desc = (0, 200, 255) if "晴" not in desc_str else (255, 165, 0)
    # y 坐标 40 是为了让较小的天气字描述在中下部对齐，显得不突兀
    draw.text((start_x + (bbox_temp[2] - bbox_temp[0]) + 5, 42), desc_str, font=font_desc, fill=color_desc)

    # 底部蓝色装饰线
    draw.line([(0, height-1), (width, height-1)], fill=(0, 80, 150), width=2)
    return img