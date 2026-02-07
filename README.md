Pi-Dashboard: 基于 Framebuffer 的嵌入式 Linux 仪表盘这是一个轻量级的、基于 Python 的嵌入式信息显示系统。它直接与 Linux 的帧缓冲设备（Framebuffer）交互，能够绕过复杂的图形桌面环境（如 X11 或 Wayland），在小型 LCD 屏幕上高效地渲染实时信息。🌟 核心特性高性能渲染：使用 numpy 实现高效的 RGB565 颜色空间转换。引入 帧哈希校验（MD5） 机制，只有当画面内容发生变化时才写入磁盘，大幅降低 CPU 和 IO 损耗。模块化架构：系统由主调度器和独立的功能插件组成，易于扩展。金融级数据可视化：内置支持抓取新浪财经 API 数据并绘制专业的日 K 线图。智能同步：集成 NTP 自动对时，确保离线或弱网环境下的时钟准确性。容错设计：所有网络请求均设有超时保护和异常缓存逻辑，确保 UI 线程永不卡死。📂 项目结构文件描述main.py系统大脑：负责模块布局管理、帧同步、RGB565 编码及硬件写入。modules/clock.py时钟插件：高字体清晰度显示当前时间、日期及星期。modules/weather.py天气插件：基于 wttr.in 获取实时气温与天气描述。modules/stocks.py股票插件：自动计算 K 线缩放比例，绘制沪深300 指数行情。🛠️ 技术规格硬件接口: /dev/fb1 (通常为 SPI 接口的 3.5寸屏)。屏幕分辨率: $480 \times 320$ (支持在 main.py 中自定义)。采样频率: $0.5s$ (动态检测秒级切换)。数据更新策略:股市数据：每 15 分钟更新一次。天气数据：每 30 分钟同步一次。🚀 快速开始1. 依赖安装系统需要 Python 3 环境及以下库：Bashsudo apt-get install ttf-wqy-microhei # 安装文泉驿中文字体
pip install pillow numpy requests pandas
2. 权限配置由于需要直接操作设备文件，需要确保当前用户有权访问 fb1：Bashsudo chmod 666 /dev/fb1
3. 运行项目Bashpython3 main.py
📊 布局自定义在 main.py 中，通过 LAYOUT 字典可以轻松调整显示区域：PythonLAYOUT = {
    "clock":   (0, 0, 180, 80),    # 时钟占据左上角
    "weather": (180, 0, 300, 80),  # 天气占据右上角
    "stocks":  (0, 80, 480, 240)   # 股票占据下半部全宽
}
