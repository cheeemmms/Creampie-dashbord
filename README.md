Pi-Dashboard
基于 Framebuffer 的嵌入式 Linux 仪表盘这是一个轻量级的、基于 Python 的嵌入式信息显示系统。它通过直接操作 Linux 帧缓冲设备（Framebuffer），在无需安装 X11 或 Wayland 等重型图形界面的情况下，为 3.5 寸 LCD 屏提供丝滑的信息展示体验。
🌟 核心特性高性能渲染：利用 numpy 进行高效的 RGB565 颜色空间转换，适配大多数嵌入式 LCD 驱动。智能帧同步：引入 MD5 帧哈希校验 机制，仅在画面像素发生变化时才执行写入操作，显著降低系统 IO 和 CPU 负载。模块化架构：系统由主调度中心和独立的插件模块（时钟、天气、股票）组成，结构清晰，极易扩展。数据可视化：内置支持从新浪财经抓取数据并动态绘制 K 线蜡烛图。高可靠性：所有网络请求（天气、股票、NTP 对时）均具备超时保护与独立缓存，确保 UI 线程不会因网络波动而卡顿。
📂 项目结构文件描述main.py核心引擎：管理全局布局、执行帧检测、处理 RGB565 转换及设备写入。modules/clock.py时钟模块：渲染高清晰度的系统时间、日期及星期。modules/weather.py天气模块：通过 wttr.in 获取实时气温与天气描述，并根据气象逻辑自动切换配色。modules/stocks.py股票模块：实时抓取沪深 300 数据，并自动计算坐标缩放绘制 K 线图。🛠️ 技术规格硬件接口: /dev/fb1默认分辨率: $480 \times 320$刷新采样率: 0.5 秒 (可精准捕捉秒钟跳动)更新策略:股票: 每 15 分钟更新一次 K 线天气: 每 30 分钟同步一次气象信息时间: 每小时自动执行一次 NTP 强制同步
🚀 快速开始
1. 准备环境确保你的系统中已安装中文字体（如文泉驿微米黑），这是渲染中文模块的必要条件：Bashsudo apt-get install ttf-wqy-microhei
2. 安装 Python 依赖Bashpip install pillow numpy requests pandas
3. 配置权限运行程序需要对帧缓冲设备有读写权限：Bashsudo chmod 666 /dev/fb1
4. 运行Bashpython3 main.py
📊 布局自定义你可以通过修改 main.py 中的 LAYOUT 字典来重新排布各个模块的位置：PythonLAYOUT = {
    "clock":   (0, 0, 180, 80),    # (x, y, width, height)
    "weather": (180, 0, 300, 80),
    "stocks":  (0, 80, 480, 240)
}
