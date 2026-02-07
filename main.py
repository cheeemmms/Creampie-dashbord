#!/usr/bin/env python3
"""
FrameBuffer Display Controller - 优化版
主控制程序，负责协调各模块渲染和屏幕刷新
"""

import os
import time
import importlib
import sys
import signal
import hashlib
import logging
import subprocess
import json
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional, List, Any
from PIL import Image
import numpy as np
from collections import deque

# ==============================================
# 配置类 (可扩展为从文件加载)
# ==============================================

@dataclass
class DisplayConfig:
    """显示配置类"""
    fb_device: str = "/dev/fb1"
    screen_size: Tuple[int, int] = (480, 320)
    frame_size: int = 307200  # 480*320*2 bytes for RGB565
    refresh_interval: float = 0.5  # 基础刷新间隔(秒)
    ntp_server: str = "ntp.ntsc.ac.cn"
    ntp_sync_interval: int = 21600  # NTP同步间隔(6小时)
    modules_dir: str = "modules"
    
    # 布局配置 (x, y, width, height)
    layout: Dict[str, Tuple[int, int, int, int]] = field(default_factory=lambda: {
        "clock": (0, 0, 180, 80),
        "weather": (180, 0, 300, 80),
        "stocks": (0, 80, 480, 240)
    })
    
    @classmethod
    def from_file(cls, config_path: str = "config.json"):
        """从JSON文件加载配置"""
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                # 转换元组格式
                for key, value in data.get('layout', {}).items():
                    if isinstance(value, list):
                        data['layout'][key] = tuple(value)
                return cls(**data)
            except Exception as e:
                logging.warning(f"Failed to load config from {config_path}: {e}")
        return cls()


# ==============================================
# 模块管理类
# ==============================================

class ModuleManager:
    """模块管理器"""
    
    def __init__(self, modules_dir: str = "modules"):
        self.modules_dir = modules_dir
        self.modules: Dict[str, Any] = {}
        self.failed_modules: set = set()
        self.last_reload_check: float = 0
        self.reload_check_interval: int = 60  # 检查模块重载的间隔(秒)
    
    def load_module(self, name: str) -> bool:
        """加载单个模块"""
        try:
            module = importlib.import_module(f"{self.modules_dir}.{name}")
            # 验证模块接口
            if hasattr(module, 'get_surface'):
                self.modules[name] = module
                if name in self.failed_modules:
                    self.failed_modules.remove(name)
                logging.info(f"Module '{name}' loaded successfully")
                return True
            else:
                logging.error(f"Module '{name}' missing 'get_surface' method")
        except Exception as e:
            logging.error(f"Failed to load module '{name}': {e}")
        
        self.failed_modules.add(name)
        return False
    
    def load_all(self, module_names: List[str]) -> int:
        """加载所有模块"""
        success_count = 0
        for name in module_names:
            if self.load_module(name):
                success_count += 1
        return success_count
    
    def check_and_reload_failed(self) -> int:
        """检查并重试加载失败的模块"""
        if not self.failed_modules:
            return 0
        
        reloaded = 0
        current_time = time.time()
        if current_time - self.last_reload_check > self.reload_check_interval:
            for name in list(self.failed_modules):
                if self.load_module(name):
                    reloaded += 1
            self.last_reload_check = current_time
        
        return reloaded
    
    def get_module(self, name: str) -> Optional[Any]:
        """获取模块实例"""
        return self.modules.get(name)
    
    def list_loaded_modules(self) -> List[str]:
        """获取已加载的模块列表"""
        return list(self.modules.keys())


# ==============================================
# 时间同步类
# ==============================================

class TimeSynchronizer:
    """时间同步管理器"""
    
    def __init__(self, ntp_server: str, sync_interval: int = 21600):
        self.ntp_server = ntp_server
        self.sync_interval = sync_interval  # 同步间隔(秒)
        self.last_sync_time: float = 0
        self.failed_attempts: int = 0
        self.max_failures: int = 3
        self.sync_in_progress: bool = False
    
    def should_sync(self) -> bool:
        """检查是否需要同步时间"""
        current_time = time.time()
        time_since_sync = current_time - self.last_sync_time
        
        # 每天凌晨3点强制同步一次
        local_time = time.localtime(current_time)
        should_force_sync = (
            local_time.tm_hour == 3 and 
            local_time.tm_min < 5 and  # 3:00-3:05期间
            time_since_sync > 300  # 至少5分钟前同步过
        )
        
        return (
            (time_since_sync > self.sync_interval or should_force_sync) 
            and self.failed_attempts < self.max_failures
            and not self.sync_in_progress
        )
    
    def sync_time(self) -> bool:
        """执行时间同步"""
        self.sync_in_progress = True
        success = False
        
        try:
            logging.info(f"Syncing time with {self.ntp_server}...")
            
            # 使用subprocess替代os.system，提供更好的控制和错误处理
            result = subprocess.run(
                ["sudo", "ntpdate", "-u", self.ntp_server],
                timeout=30,  # 30秒超时
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.last_sync_time = time.time()
                self.failed_attempts = 0
                success = True
                logging.info(f"Time sync successful: {result.stdout.strip()}")
            else:
                self.failed_attempts += 1
                logging.error(f"Time sync failed: {result.stderr.strip()}")
                
        except subprocess.TimeoutExpired:
            self.failed_attempts += 1
            logging.error("Time sync timeout")
        except FileNotFoundError:
            logging.error("ntpdate command not found")
        except Exception as e:
            self.failed_attempts += 1
            logging.error(f"Time sync error: {e}")
        finally:
            self.sync_in_progress = False
        
        return success


# ==============================================
# 帧缓冲写入器
# ==============================================

class FrameBufferWriter:
    """帧缓冲写入器"""
    
    def __init__(self, fb_device: str, frame_size: int):
        self.fb_device = fb_device
        self.frame_size = frame_size
        self.fb_handle = None
        self.last_frame_hash = None
        self.write_count = 0
        self.total_bytes_written = 0
    
    def __enter__(self):
        """上下文管理器入口"""
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
    
    def open(self):
        """打开帧缓冲设备"""
        try:
            # 设置设备权限
            subprocess.run(["sudo", "chmod", "666", self.fb_device], 
                          capture_output=True)
            
            # 打开设备文件
            self.fb_handle = open(self.fb_device, "r+b")
            logging.info(f"Frame buffer {self.fb_device} opened")
            
        except Exception as e:
            logging.error(f"Failed to open frame buffer: {e}")
            raise
    
    def close(self):
        """关闭帧缓冲设备"""
        if self.fb_handle:
            self.fb_handle.close()
            self.fb_handle = None
            logging.info("Frame buffer closed")
    
    def convert_to_rgb565(self, img: Image.Image) -> bytes:
        """转换图像为RGB565格式"""
        img_array = np.array(img.convert('RGB'))
        r = img_array[:, :, 0].astype(np.uint16)
        g = img_array[:, :, 1].astype(np.uint16)
        b = img_array[:, :, 2].astype(np.uint16)
        
        # RGB565转换公式
        rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        return rgb565.tobytes()
    
    def write_frame(self, frame_data: bytes, force: bool = False) -> bool:
        """写入帧到缓冲区（仅当内容变化时）"""
        if self.fb_handle is None:
            logging.error("Frame buffer not opened")
            return False
        
        try:
            # 计算当前帧的哈希值
            current_hash = hashlib.md5(frame_data).hexdigest()
            
            # 检查是否需要写入（内容变化或强制写入）
            if force or current_hash != self.last_frame_hash:
                self.fb_handle.seek(0)
                self.fb_handle.write(frame_data[:self.frame_size])
                self.fb_handle.flush()
                
                self.last_frame_hash = current_hash
                self.write_count += 1
                self.total_bytes_written += self.frame_size
                
                return True
            return False
            
        except Exception as e:
            logging.error(f"Frame buffer write error: {e}")
            return False


# ==============================================
# 性能监控器
# ==============================================

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, history_size: int = 100):
        self.frame_times: deque = deque(maxlen=history_size)
        self.render_times: deque = deque(maxlen=history_size)
        self.start_time: float = time.time()
        self.frame_count: int = 0
        self.last_report_time: float = self.start_time
        self.report_interval: int = 60  # 性能报告间隔(秒)
    
    def record_frame(self, render_time: float, total_time: float):
        """记录帧性能数据"""
        self.frame_times.append(total_time)
        self.render_times.append(render_time)
        self.frame_count += 1
        
        # 定期报告性能
        current_time = time.time()
        if current_time - self.last_report_time > self.report_interval:
            self.report_performance()
            self.last_report_time = current_time
    
    def report_performance(self):
        """报告性能统计数据"""
        if not self.frame_times:
            return
        
        avg_frame_time = sum(self.frame_times) / len(self.frame_times)
        avg_render_time = sum(self.render_times) / len(self.render_times)
        fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
        
        uptime = time.time() - self.start_time
        
        logging.info(
            f"Performance: FPS={fps:.1f}, "
            f"Frame={avg_frame_time*1000:.1f}ms, "
            f"Render={avg_render_time*1000:.1f}ms, "
            f"Frames={self.frame_count}, "
            f"Uptime={uptime//3600:.0f}h{(uptime%3600)//60:.0f}m"
        )
    
    def get_fps(self) -> float:
        """获取当前FPS"""
        if not self.frame_times:
            return 0.0
        avg_time = sum(self.frame_times) / len(self.frame_times)
        return 1.0 / avg_time if avg_time > 0 else 0.0


# ==============================================
# 自适应休眠控制器
# ==============================================

class AdaptiveSleeper:
    """自适应休眠控制器"""
    
    def __init__(self, base_interval: float = 0.5):
        self.base_interval = base_interval
        self.last_sleep_time: float = 0
        self.adaptive_factor: float = 1.0
        self.min_interval: float = 0.05
        self.max_interval: float = 2.0
    
    def calculate_sleep_time(self, last_frame_time: float) -> float:
        """计算休眠时间"""
        # 基础休眠时间
        sleep_time = self.base_interval
        
        # 根据上一帧渲染时间调整
        if last_frame_time > self.base_interval * 0.8:
            # 渲染时间过长，增加休眠时间避免CPU过载
            sleep_time = min(sleep_time * 1.5, self.max_interval)
        elif last_frame_time < self.base_interval * 0.2:
            # 渲染时间很短，减少休眠时间提高响应性
            sleep_time = max(sleep_time * 0.8, self.min_interval)
        
        return sleep_time
    
    def sleep(self, last_frame_time: float):
        """执行自适应休眠"""
        sleep_time = self.calculate_sleep_time(last_frame_time)
        
        # 确保最小休眠时间
        elapsed = time.time() - self.last_sleep_time
        remaining = sleep_time - elapsed
        
        if remaining > 0:
            time.sleep(remaining)
        
        self.last_sleep_time = time.time()


# ==============================================
# 主显示控制器
# ==============================================

class DisplayController:
    """主显示控制器"""
    
    def __init__(self, config_path: Optional[str] = None):
        # 加载配置
        self.config = DisplayConfig.from_file(config_path)
        
        # 初始化组件
        self.module_manager = ModuleManager(self.config.modules_dir)
        self.time_sync = TimeSynchronizer(
            self.config.ntp_server, 
            self.config.ntp_sync_interval
        )
        self.fb_writer = FrameBufferWriter(
            self.config.fb_device, 
            self.config.frame_size
        )
        self.performance_monitor = PerformanceMonitor()
        self.adaptive_sleeper = AdaptiveSleeper(self.config.refresh_interval)
        
        # 状态变量
        self.running = False
        self.last_health_check = 0
        self.health_check_interval = 300  # 健康检查间隔(秒)
    
    def setup(self) -> bool:
        """初始化系统"""
        logging.info("Setting up display controller...")
        
        try:
            # 打开帧缓冲
            self.fb_writer.open()
            
            # 加载模块
            loaded = self.module_manager.load_all(self.config.layout.keys())
            if loaded == 0:
                logging.error("No modules loaded successfully")
                return False
            
            logging.info(f"Loaded {loaded}/{len(self.config.layout)} modules")
            
            # 初始时间同步
            if self.time_sync.should_sync():
                self.time_sync.sync_time()
            
            return True
            
        except Exception as e:
            logging.error(f"Setup failed: {e}")
            return False
    
    def render_frame(self) -> Tuple[Optional[bytes], float, bool]:
        """渲染一帧"""
        render_start = time.time()
        frame_updated = False
        
        try:
            # 创建画布
            canvas = Image.new('RGB', self.config.screen_size, (0, 0, 0))
            
            # 渲染各个模块
            for mod_name, (x, y, w, h) in self.config.layout.items():
                module = self.module_manager.get_module(mod_name)
                if module:
                    try:
                        sub_img = module.get_surface(w, h)
                        canvas.paste(sub_img, (x, y))
                    except Exception as e:
                        logging.error(f"Module '{mod_name}' render error: {e}")
                else:
                    # 绘制模块加载失败的占位符
                    self._draw_module_placeholder(canvas, x, y, w, h, mod_name)
            
            # 转换为RGB565格式
            frame_data = self.fb_writer.convert_to_rgb565(canvas)
            
            render_time = time.time() - render_start
            return frame_data, render_time, True
            
        except Exception as e:
            logging.error(f"Render error: {e}")
            render_time = time.time() - render_start
            return None, render_time, False
    
    def _draw_module_placeholder(self, canvas, x, y, w, h, mod_name):
        """绘制模块加载失败的占位符"""
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(canvas)
        
        # 绘制红色边框
        draw.rectangle([x, y, x+w-1, y+h-1], outline=(255, 50, 50), width=2)
        
        # 绘制错误文本
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 14
            )
        except:
            font = ImageFont.load_default()
        
        text = f"{mod_name} Error"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        text_x = x + (w - text_w) // 2
        text_y = y + (h - text_h) // 2
        
        draw.text((text_x, text_y), text, font=font, fill=(255, 50, 50))
    
    def health_check(self):
        """系统健康检查"""
        current_time = time.time()
        
        if current_time - self.last_health_check > self.health_check_interval:
            # 检查并重载失败模块
            reloaded = self.module_manager.check_and_reload_failed()
            if reloaded > 0:
                logging.info(f"Reloaded {reloaded} failed modules")
            
            # 报告性能
            self.performance_monitor.report_performance()
            
            # 检查系统资源（示例）
            try:
                # 获取CPU温度（树莓派）
                if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
                    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                        temp = int(f.read()) / 1000
                    if temp > 70:
                        logging.warning(f"High CPU temperature: {temp}°C")
            except:
                pass
            
            self.last_health_check = current_time
    
    def run(self):
        """主运行循环"""
        logging.info("Starting display controller...")
        
        if not self.setup():
            logging.error("Initialization failed, exiting...")
            return
        
        self.running = True
        frame_start_time = time.time()
        
        try:
            while self.running:
                cycle_start = time.time()
                
                # 时间同步
                if self.time_sync.should_sync():
                    self.time_sync.sync_time()
                
                # 渲染帧
                frame_data, render_time, render_ok = self.render_frame()
                
                # 写入帧缓冲
                write_ok = False
                if render_ok and frame_data is not None:
                    write_ok = self.fb_writer.write_frame(frame_data)
                
                # 记录性能
                cycle_time = time.time() - cycle_start
                self.performance_monitor.record_frame(render_time, cycle_time)
                
                # 健康检查
                self.health_check()
                
                # 自适应休眠
                self.adaptive_sleeper.sleep(cycle_time)
                
        except KeyboardInterrupt:
            logging.info("Shutdown requested by user")
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """清理资源"""
        logging.info("Cleaning up resources...")
        self.running = False
        self.fb_writer.close()
        logging.info("Display controller stopped")


# ==============================================
# 信号处理与主入口
# ==============================================

def setup_signal_handlers(controller: DisplayController):
    """设置信号处理器"""
    
    def signal_handler(signum, frame):
        logging.info(f"Received signal {signum}, shutting down...")
        controller.running = False
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 系统终止信号
    signal.signal(signal.SIGHUP, signal_handler)   # 终端挂起
    signal.signal(signal.SIGQUIT, signal_handler)  # Ctrl+\


def setup_logging(log_level=logging.INFO, log_file=None):
    """设置日志系统"""
    
    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 配置根日志记录器
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（可选）
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logging.warning(f"Failed to setup file logging: {e}")


def main():
    """主函数"""
    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser(description="FrameBuffer Display Controller")
    parser.add_argument("--config", type=str, help="Configuration file path")
    parser.add_argument("--log", type=str, help="Log file path")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()
    
    # 设置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level, args.log)
    
    # 创建显示控制器
    controller = DisplayController(args.config)
    
    # 设置信号处理器
    setup_signal_handlers(controller)
    
    # 运行主循环
    controller.run()


if __name__ == "__main__":
    main()
