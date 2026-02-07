import requests
import pandas as pd
import time, os
from PIL import Image, ImageDraw, ImageFont

# 屏蔽代理干扰
os.environ['no_proxy'] = '*' 

# 缓存配置
CACHE = {"data": None, "last_pull": 0, "status": "Ready"}
FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"

def get_surface(width, height):
    global CACHE
    now = time.time()
    
    # 每 15 分钟更新一次 K 线
    if now - CACHE["last_pull"] > 900:
        try:
            # 目标：沪深300 (sz399300) 的日K线
            # 新浪 API: 获取最近 60 个交易日数据
            url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
            params = {
                "symbol": "sz399300",
                "scale": "240",  # 240分钟=1日
                "datalen": "60"   # 获取60根K线
            }
            headers = {'Referer': 'http://finance.sina.com.cn'}
            
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    # 将 JSON 转换为 DataFrame (包含 day, open, high, low, close)
                    df = pd.DataFrame(data)
                    # 转换数值类型
                    cols = ['open', 'high', 'low', 'close']
                    df[cols] = df[cols].astype(float)
                    
                    CACHE["data"] = df
                    CACHE["status"] = "Sina-Live"
                    CACHE["last_pull"] = now
                else:
                    CACHE["status"] = "No-Data"
            else:
                CACHE["status"] = f"Error:{resp.status_code}"
                
        except Exception as e:
            CACHE["status"] = "Net-Retry"
            print(f"K-Line Pull Error: {e}")

    # --- 绘图管线 ---
    img = Image.new('RGB', (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        f_title = ImageFont.truetype(FONT_PATH, 16)
        f_price = ImageFont.truetype(FONT_PATH, 14)
    except:
        f_title = f_price = ImageFont.load_default()

    # 绘制背景装饰线
    for i in range(1, 4):
        y_grid = (height // 4) * i
        draw.line([(0, y_grid), (width, y_grid)], fill=(30, 30, 30))

    if CACHE["data"] is not None:
        df = CACHE["data"]
        # 1. 自动计算坐标轴缩放
        y_min, y_max = df['low'].min() * 0.99, df['high'].max() * 1.01
        y_range = y_max - y_min
        
        # 2. 绘制标题和最新价
        last_close = df.iloc[-1]['close']
        last_open = df.iloc[-1]['open']
        color_last = (255, 50, 50) if last_close >= last_open else (50, 255, 50)
        draw.text((10, 5), f"沪深300指数 | {CACHE['status']}", font=f_title, fill=(200, 200, 200))
        draw.text((width - 100, 5), f"{last_close:.1f}", font=f_price, fill=color_last)

        # 3. 循环绘制每根 K 线 (管线逻辑)
        k_count = len(df)
        k_w = width / k_count # 每根K线的宽度
        
        for i in range(k_count):
            def to_y(v): return int(height - (v - y_min) / y_range * (height - 40) - 10)
            
            x_center = i * k_w + k_w / 2
            o, c, h, l = df.iloc[i]['open'], df.iloc[i]['close'], df.iloc[i]['high'], df.iloc[i]['low']
            
            # 配色方案
            k_color = (255, 50, 50) if c >= o else (50, 255, 50)
            
            # 绘制上下影线
            draw.line([(x_center, to_y(h)), (x_center, to_y(l))], fill=k_color, width=1)
            # 绘制蜡烛实体
            rect_top = to_y(max(o, c))
            rect_bottom = to_y(min(o, c))
            # 确保即使平盘也能画出一条线
            if rect_top == rect_bottom: rect_bottom += 1
            draw.rectangle([i * k_w + 1, rect_top, (i+1) * k_w - 1, rect_bottom], fill=k_color)
    else:
        draw.text((width//2-40, height//2), "正在加载K线数据...", font=f_title, fill=(100, 100, 100))

    return img