import os, time, importlib, sys, signal, hashlib
from PIL import Image
import numpy as np

# --- 配置中心 ---
FB_DEV = "/dev/fb1"
SCREEN_SIZE = (480, 320)
FRAME_SIZE = 307200
REFRESH_INTERVAL = 0.5  # 采样频率（秒）
running = True

LAYOUT = {
    "clock":   (0, 0, 180, 80),
    "weather": (180, 0, 300, 80),
    "stocks":  (0, 80, 480, 240)
}

# 预加载模块，避免在循环中重复 import
modules = {name: importlib.import_module(f"modules.{name}") for name in LAYOUT}

def convert_to_rgb565(img):
    img_array = np.array(img.convert('RGB'))
    r = img_array[:, :, 0].astype(np.uint16)
    g = img_array[:, :, 1].astype(np.uint16)
    b = img_array[:, :, 2].astype(np.uint16)
    # 标准 RGB565 转换公式
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return rgb565.tobytes()

def main():
    global running
    os.system(f"sudo chmod 666 {FB_DEV}")
    last_sync_hour = -1
    last_frame_hash = None 

    print(">>> 系统启动中...")

    while running:
        curr_struct = time.localtime()
        
        # 1. 整点同步时间
        if curr_struct.tm_hour != last_sync_hour:
            os.system("sudo ntpdate -u ntp.ntsc.ac.cn &")
            last_sync_hour = curr_struct.tm_hour

        # 2. 渲染画布
        canvas = Image.new('RGB', SCREEN_SIZE, (0, 0, 0))
        for mod_name, (x, y, w, h) in LAYOUT.items():
            try:
                # 仅在调试阶段使用 reload，生产环境直接调用
                sub_img = modules[mod_name].get_surface(w, h)
                canvas.paste(sub_img, (x, y))
            except Exception as e:
                print(f"Module {mod_name} Error: {e}")

        # 3. 智能刷新检测：计算当前帧的哈希值
        raw_bytes = convert_to_rgb565(canvas)
        current_hash = hashlib.md5(raw_bytes).hexdigest()

        if current_hash != last_frame_hash:
            try:
                with open(FB_DEV, "r+b") as f:
                    f.seek(0)
                    f.write(raw_bytes[:FRAME_SIZE])
                    f.flush()
                last_frame_hash = current_hash
            except Exception as e:
                print(f"FB Write Error: {e}")
        
        # 4. 动态休眠：秒数对齐
        # 0.5秒采样一次足以捕捉秒钟切换，且不会导致 CPU 飙升
        time.sleep(REFRESH_INTERVAL)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    main()