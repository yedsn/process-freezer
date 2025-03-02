import sys
import os
import json
import logging
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import psutil
import win32gui
import win32process
import win32con
import win32api
import pystray
from PIL import Image, ImageDraw, ImageFont
import tkinter.colorchooser
import keyboard  # 添加到文件顶部的导入部分
import traceback
from datetime import datetime

# 修改日志配置部分
def setup_logging():
    """配置日志记录器"""
    # 创建logs目录（如果不存在）
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 清理旧日志文件
    def cleanup_old_logs():
        try:
            # 检查上次清理时间
            last_cleanup_file = os.path.join(log_dir, ".last_cleanup")
            current_time = datetime.now()
            
            # 检查是否需要清理
            should_cleanup = True
            if os.path.exists(last_cleanup_file):
                try:
                    with open(last_cleanup_file, 'r') as f:
                        last_cleanup_str = f.read().strip()
                        last_cleanup = datetime.fromisoformat(last_cleanup_str)
                        # 如果距离上次清理不足24小时，则跳过
                        if (current_time - last_cleanup).total_seconds() < 24 * 3600:
                            should_cleanup = False
                except Exception:
                    # 如果读取失败，执行清理
                    pass
            
            if should_cleanup:
                # 遍历日志目录
                for filename in os.listdir(log_dir):
                    if filename.startswith('process_freezer_') and filename.endswith('.log'):
                        file_path = os.path.join(log_dir, filename)
                        # 获取文件最后修改时间
                        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        # 如果文件超过7天，则删除
                        if (current_time - file_time).days > 7:
                            try:
                                os.remove(file_path)
                                print(f"Removed old log file: {filename}")
                            except Exception as e:
                                print(f"Failed to remove old log file {filename}: {str(e)}")
                
                # 更新最后清理时间
                try:
                    with open(last_cleanup_file, 'w') as f:
                        f.write(current_time.isoformat())
                except Exception as e:
                    print(f"Failed to update last cleanup time: {str(e)}")
                    
        except Exception as e:
            print(f"Error during log cleanup: {str(e)}")
    
    # 执行日志清理
    cleanup_old_logs()
    
    # 生成日志文件名（包含日期）
    date_str = datetime.now().strftime("%Y%m%d")
    general_log = os.path.join(log_dir, f'process_freezer_{date_str}.log')
    error_log = os.path.join(log_dir, f'process_freezer_error_{date_str}.log')
    
    # 配置根日志记录器
    logging.getLogger().setLevel(logging.DEBUG)
    
    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s'
    )
    
    # 配置一般日志处理器
    file_handler = logging.FileHandler(general_log, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # 配置错误日志处理器
    error_handler = logging.FileHandler(error_log, encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    
    # 配置控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    
    # 添加处理器到根日志记录器
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().addHandler(error_handler)
    logging.getLogger().addHandler(console_handler)

# 在文件开头调用setup_logging
setup_logging()

class ProcessManager:
    def __init__(self, settings):  # 修改：接收 settings 参数
        self.config_file = "processes.json"
        self.processes = {}
        self.settings = settings  # 使用传入的 settings 实例
        self.window_hider = WindowHider()  
        self.load_processes()

    def load_processes(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    loaded_processes = json.load(f)
                    # 确保所有进程都有name字段
                    for proc_id, data in loaded_processes.items():
                        if "name" not in data:
                            data["name"] = proc_id  # 如果没有名称，使用进程ID作为默认名称
                    self.processes = loaded_processes
            except Exception as e:
                logging.error(f"加载进程配置文件失败: {str(e)}")
                self.processes = {}

    def save_processes(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.processes, f)

    def add_process(self, identifier, name="", is_frozen=False):
        self.processes[identifier] = {
            "name": name,
            "is_frozen": is_frozen
        }
        self.save_processes()

    def remove_process(self, identifier):
        if identifier in self.processes:
            del self.processes[identifier]
            self.save_processes()

    def toggle_freeze(self, identifier):
        if identifier in self.processes:
            current_state = self.processes[identifier]["is_frozen"]
            new_state = not current_state
            
            logging.info(f"Toggle freeze for process: {identifier}")
            logging.info(f"Current state: {current_state}")
            logging.info(f"New state: {new_state}")
            
            try:
                if new_state:  # Freeze
                    logging.info(f"Attempting to freeze process: {identifier}")
                    # 如果启用了窗口隐藏功能，先隐藏窗口
                    if self.settings.hide_window:
                        self.window_hider.hide_window_by_name(identifier)
                        
                    result = subprocess.run(['pssuspend64.exe', identifier], 
                                     check=True, 
                                     capture_output=True,
                                     text=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode == 0:
                        self.processes[identifier]["is_frozen"] = True
                        logging.info(f"Successfully froze process: {identifier}")
                    else:
                        # 如果冻结失败，恢复隐藏的窗口
                        if self.settings.hide_window:
                            self.window_hider.show_windows_by_name(identifier)
                        logging.error(f"Failed to freeze process: {result.stderr}")
                        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
                else:  # Resume
                    logging.info(f"Attempting to resume process: {identifier}")
                    result = subprocess.run(['pssuspend64.exe', '-r', identifier], 
                                     check=True,
                                     capture_output=True,
                                     text=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode == 0:
                        self.processes[identifier]["is_frozen"] = False
                        # 如果启用了窗口隐藏功能，在解冻后恢复窗口
                        if self.settings.hide_window:
                            self.window_hider.show_windows_by_name(identifier)
                        logging.info(f"Successfully resumed process: {identifier}")
                    else:
                        logging.error(f"Failed to resume process: {result.stderr}")
                        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
                
                self.save_processes()
                return True
                
            except subprocess.CalledProcessError as e:
                logging.error(f"Error executing pssuspend64: {str(e)}")
                messagebox.showerror("错误", f"执行进程{identifier}操作失败: {str(e)}")
                return False
            except Exception as e:
                logging.error(f"Unexpected error: {str(e)}")
                messagebox.showerror("错误", f"未知错误: {str(e)}")
                return False
        return False

class WindowHider:
    def __init__(self):
        self.hidden_windows = {}  # 存储被隐藏的窗口信息，格式：{进程ID: {hwnd: 窗口信息}}
    
    def get_window_title(self, hwnd):
        """获取窗口标题"""
        return win32gui.GetWindowText(hwnd)
    
    def get_window_process_id(self, hwnd):
        """获取窗口对应的进程ID"""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return pid
        except:
            return None
    
    def get_process_id_by_name(self, process_name):
        """通过进程名称获取进程ID列表"""
        logging.info(f"Attempting to get process ID for process: {process_name}")
        pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'].lower() == process_name.lower():
                    pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        logging.info(f"Successfully got process ID for process: {process_name} as {pids}")
        return pids
    
    def hide_window_by_name(self, process_name):
        """根据进程名称隐藏窗口"""
        pids = self.get_process_id_by_name(process_name)
        for pid in pids:
            self.hide_window_by_pid(pid)
    
    def show_windows_by_name(self, process_name):
        """根据进程名称显示窗口"""
        logging.info(f"Attempting to show windows by process name: {process_name}")
        pids = self.get_process_id_by_name(process_name)
        for pid in pids:
            self.show_windows_by_pid(pid)
        logging.info(f"Successfully showed windows by process name: {process_name}")
    
    def hide_window_by_pid(self, target_pid):
        """根据进程ID隐藏窗口"""
        logging.info(f"Attempting to hide windows by pid: {target_pid}")
        def enum_window(hwnd, target_pid):
            if win32gui.IsWindowVisible(hwnd):
                pid = self.get_window_process_id(hwnd)
                if pid == target_pid:
                    # 保存窗口状态
                    if target_pid not in self.hidden_windows:
                        self.hidden_windows[target_pid] = {}
                    self.hidden_windows[target_pid][hwnd] = {
                        'title': self.get_window_title(hwnd),
                        'is_foreground': hwnd == win32gui.GetForegroundWindow()
                    }
                    # 隐藏窗口
                    win32gui.SetWindowPos(
                        hwnd, 
                        0, 
                        0, 0, 0, 0,
                        win32con.SWP_NOMOVE | 
                        win32con.SWP_NOSIZE | 
                        win32con.SWP_NOZORDER |
                        win32con.SWP_HIDEWINDOW
                    )
        
        win32gui.EnumWindows(lambda hwnd, pid: enum_window(hwnd, pid), target_pid)
        logging.info(f"Successfully hide windows by pid: {target_pid}")
    
    def show_windows_by_pid(self, target_pid):
        """根据进程ID显示窗口"""
        if target_pid in self.hidden_windows:
            for hwnd, info in list(self.hidden_windows[target_pid].items()):
                # 显示窗口
                win32gui.SetWindowPos(
                    hwnd, 
                    0, 
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | 
                    win32con.SWP_NOSIZE | 
                    win32con.SWP_NOZORDER |
                    win32con.SWP_SHOWWINDOW
                )
                
                # 如果之前是前台窗口，恢复其状态
                if info['is_foreground']:
                    win32gui.SetForegroundWindow(hwnd)
            
            # 清除该进程的所有隐藏窗口记录
            del self.hidden_windows[target_pid]

class Settings:
    def __init__(self):
        self.config_file = "settings.json"
        self.show_icon_count = True
        self.icon_number_color = '#ffffff'  # white
        self.icon_shadow_color = '#007bff'  # blue
        self.hide_window = False  # 在冻结时隐藏窗口
        self.always_on_top = False
        self.toggle_hotkey = 'ctrl+alt+f'  # 新增：默认快捷键
        self.load_settings()

    def load_settings(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.show_icon_count = data.get('show_icon_count', True)
                    self.icon_number_color = data.get('icon_number_color', '#ffffff')
                    self.icon_shadow_color = data.get('icon_shadow_color', '#007bff')
                    self.hide_window = data.get('hide_window', False)
                    self.always_on_top = data.get('always_on_top', False)
                    self.toggle_hotkey = data.get('toggle_hotkey', 'ctrl+alt+f')  # 新增：加载快捷键设置
        except Exception as e:
            logging.error(f"Failed to load settings: {e}")

    def save_settings(self):
        try:
            data = {
                'show_icon_count': self.show_icon_count,
                'icon_number_color': self.icon_number_color,
                'icon_shadow_color': self.icon_shadow_color,
                'hide_window': self.hide_window,
                'always_on_top': self.always_on_top,
                'toggle_hotkey': self.toggle_hotkey  # 新增：保存快捷键设置
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save settings: {e}")

class DragHandle:
    def __init__(self, parent, callback):
        self.parent = parent
        self.callback = callback
        self.dragging = False
        
        # 创建手柄按钮
        self.handle = tk.Label(parent, 
                             text="⊕", 
                             font=('Microsoft YaHei UI', 16),
                             fg='#007bff',
                             bg='white',
                             cursor="hand2")
        
        # 绑定事件
        self.handle.bind('<Button-1>', self.start_drag)
        self.handle.bind('<B1-Motion>', self.dragging)
        self.handle.bind('<ButtonRelease-1>', self.stop_drag)
        self.handle.bind('<Enter>', self.on_enter)
        self.handle.bind('<Leave>', self.on_leave)
    
    def start_drag(self, event):
        self.dragging = True
        self.handle.configure(fg='#0056b3')  # 深蓝色
    
    def dragging(self, event):
        if self.dragging:
            # 获取鼠标位置
            x, y = win32gui.GetCursorPos()
            # 获取窗口句柄
            hwnd = win32gui.WindowFromPoint((x, y))
            if hwnd:
                # 获取进程ID
                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                # 更新手柄显示
                self.handle.configure(text="⊕")
    
    def stop_drag(self, event):
        if self.dragging:
            self.dragging = False
            self.handle.configure(fg='#007bff', text="⊕")  # 恢复原始颜色
            
            # 获取鼠标位置下的窗口信息
            x, y = win32gui.GetCursorPos()
            hwnd = win32gui.WindowFromPoint((x, y))
            
            if hwnd:
                # 获取进程ID和窗口标题
                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                window_title = win32gui.GetWindowText(hwnd)
                
                try:
                    # 使用psutil获取进程信息
                    process = psutil.Process(process_id)
                    process_name = process.name()  # 获取进程的可执行文件名称
                    
                    # 调用回调函数，传递进程名称而不是ID
                    if self.callback:
                        self.callback(process_name, window_title)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    messagebox.showerror("错误", "无法获取进程信息")
    
    def on_enter(self, event):
        if not self.dragging:
            self.handle.configure(fg='#0056b3')  # 深蓝色
    
    def on_leave(self, event):
        if not self.dragging:
            self.handle.configure(fg='#007bff')  # 恢复原始颜色
    
    def pack(self, **kwargs):
        self.handle.pack(**kwargs)

class ProcessListWindow:
    def __init__(self, process_manager):
        self.settings = Settings()
        self.process_manager = process_manager
        self.process_manager.settings = self.settings  # 确保 ProcessManager 使用相同的 settings 实例
        self.window = tk.Tk()
        self.window.title("进程冻结器")
        self.window.geometry("800x450")
        self.window.configure(bg='white')  # 设置窗口背景色
        
        # 用于控制快捷键检查的标志
        self.running = True
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
        if os.path.exists(icon_path):
            self.window.iconbitmap(icon_path)
        
        # 绑定窗口事件
        self.window.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        self.window.bind("<Unmap>", lambda e: self.handle_minimize(e))
        
        # 设置统一的字体
        self.default_font = ('Microsoft YaHei UI', 10)
        self.title_font = ('Microsoft YaHei UI', 12, 'bold')
        
        # 创建托盘图标
        self.create_tray_icon()
        
        # 创建主框架
        main_frame = tk.Frame(self.window, bg='white')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 创建顶部框架（包含标题和设置按钮）
        top_frame = tk.Frame(main_frame, bg='white')
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 添加进程按钮（使用现代风格）
        add_button = tk.Button(top_frame,
                             text="添加进程",
                             command=self.add_process,
                             font=self.default_font,
                             bg='#007bff',
                             fg='white',
                             relief=tk.FLAT,
                             padx=15)
        add_button.pack(side=tk.LEFT)
        
        # 设置按钮（使用⚙符号）
        settings_btn = tk.Label(top_frame,
                              text="⚙",
                              font=('Microsoft YaHei UI', 16),
                              bg='white',
                              fg='#666666',
                              cursor="hand2")
        settings_btn.pack(side=tk.RIGHT)
        
        # 绑定鼠标事件
        settings_btn.bind('<Button-1>', lambda e: self.show_settings_menu(e))
        settings_btn.bind('<Enter>', lambda e: settings_btn.configure(fg='#007bff'))
        settings_btn.bind('<Leave>', lambda e: settings_btn.configure(fg='#666666'))
        
        # 绑定鼠标悬停事件
        add_button.bind('<Enter>', lambda e, b=add_button: self.on_hover(e, b))
        add_button.bind('<Leave>', lambda e, b=add_button: self.on_leave(e, b))
        
        # 创建进程列表框架（带滚动条）
        list_container = tk.Frame(main_frame, bg='#f0f0f0')
        list_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建标题行（固定在顶部）
        header_frame = tk.Frame(list_container, bg='white')
        header_frame.pack(fill=tk.X)
        
        # 添加标题列
        tk.Label(header_frame, 
                text="进程名称", 
                width=30, 
                anchor='w', 
                bg='white', 
                font=('Microsoft YaHei UI', 10, 'bold'),
                pady=8).pack(side=tk.LEFT, padx=5)  # 减少垂直内边距
                
        tk.Label(header_frame, 
                text="进程ID", 
                width=20, 
                anchor='w', 
                bg='white', 
                font=('Microsoft YaHei UI', 10, 'bold'),
                pady=8).pack(side=tk.LEFT, padx=5)
                
        tk.Label(header_frame, 
                text="状态", 
                width=10, 
                anchor='w', 
                bg='white', 
                font=('Microsoft YaHei UI', 10, 'bold'),
                pady=8).pack(side=tk.LEFT, padx=5)
                
        tk.Label(header_frame, 
                text="操作", 
                width=20, 
                anchor='w', 
                bg='white', 
                font=('Microsoft YaHei UI', 10, 'bold'),
                pady=8).pack(side=tk.LEFT, padx=5)
        
        # 添加Canvas和滚动条
        self.canvas = tk.Canvas(list_container, bg='white', height=200)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(list_container, command=self.canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 配置Canvas
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        # 进程列表框架
        self.list_frame = tk.Frame(self.canvas, bg='white')
        self.canvas.create_window((0, 0), window=self.list_frame, anchor='nw', width=self.canvas.winfo_reqwidth())
        
        # 绑定调整大小事件
        self.list_frame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig(self.canvas.find_withtag('all')[0], width=e.width))
        
        # 绑定鼠标滚轮事件
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # 设置窗口置顶状态
        self.set_window_on_top(self.settings.always_on_top)

        # 更新进程列表显示
        self.update_process_list()

        # 添加快捷键状态标志
        self.hotkey_registered = False
        self.hotkey_retry_count = 0
        self.MAX_RETRY_COUNT = 3
        
        # 在初始化结束时注册快捷键
        self.window.after(1000, self.ensure_hotkey_registered)  # 延迟1秒注册

    def on_hover(self, event, button):
        """鼠标悬停效果"""
        if button['text'] == "添加进程":
            button.configure(bg='#0056b3')  # 深蓝色
        elif button['text'] == "最小化":
            button.configure(bg='#5a6268')  # 深灰色
        elif button['text'] == "冻结":
            button.configure(bg='#c82333')  # 深红色
        elif button['text'] == "解冻":
            button.configure(bg='#218838')  # 深绿色
        elif button['text'] == "删除":
            button.configure(bg='#5a6268')  # 深灰色
        else:  # 退出按钮
            button.configure(bg='#c82333')  # 深红色
    
    def on_leave(self, event, button):
        """鼠标离开效果"""
        if button['text'] == "添加进程":
            button.configure(bg='#007bff')  # 恢复蓝色
        elif button['text'] == "最小化":
            button.configure(bg='#6c757d')  # 恢复灰色
        elif button['text'] == "冻结":
            button.configure(bg='#dc3545')  # 恢复红色
        elif button['text'] == "解冻":
            button.configure(bg='#28a745')  # 恢复绿色
        elif button['text'] == "删除":
            button.configure(bg='#6c757d')  # 恢复灰色
        else:  # 退出按钮
            button.configure(bg='#dc3545')  # 恢复红色

    def update_process_list(self):
        # 清除现有项目
        for widget in self.list_frame.winfo_children():
            widget.destroy()
            
        # 添加新项目
        for proc_id, data in self.process_manager.processes.items():
            # 创建项目容器
            item_frame = tk.Frame(self.list_frame, bg='white')
            item_frame.pack(fill=tk.X, padx=10, pady=2)
            
            # 进程名称标签
            process_name = data.get("name", proc_id)
            name_label = tk.Label(item_frame,
                                text=process_name,
                                font=self.default_font,
                                bg='white',
                                fg='#666666',
                                width=30)
            name_label.pack(side=tk.LEFT, padx=5)
            
            # 进程ID标签
            id_label = tk.Label(item_frame,
                              text=proc_id,
                              font=self.default_font,
                              bg='white',
                              fg='#333333',
                              width=20)
            id_label.pack(side=tk.LEFT, padx=5)
            
            # 状态标签
            status_text = "已冻结" if data.get("is_frozen", False) else "未冻结"
            status_color = "#dc3545" if data.get("is_frozen", False) else "#28a745"
            status_label = tk.Label(item_frame,
                                  text=status_text,
                                  font=self.default_font,
                                  bg='white',
                                  fg=status_color,
                                  width=10)
            status_label.pack(side=tk.LEFT, padx=5)
            
            # 按钮框架（居中对齐）
            button_frame = tk.Frame(item_frame, bg='white')
            button_frame.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            
            # 创建一个内部框架来包含按钮，实现居中对齐
            inner_button_frame = tk.Frame(button_frame, bg='white')
            inner_button_frame.pack(expand=True)
            
            # 冻结/解冻按钮
            freeze_text = "解冻" if data.get("is_frozen", False) else "冻结"
            freeze_color = "#28a745" if data.get("is_frozen", False) else "#dc3545"
            freeze_btn = tk.Button(inner_button_frame,
                                text=freeze_text,
                                command=lambda pid=proc_id: self.toggle_freeze_with_button(pid),
                                font=self.default_font,
                                bg=freeze_color,
                                fg='white',
                                relief=tk.FLAT,
                                width=6)
            freeze_btn.pack(side=tk.LEFT, padx=(0, 5))
            
            # 删除按钮
            delete_btn = tk.Button(inner_button_frame,
                                text="删除",
                                command=lambda pid=proc_id: self.remove_process(pid),
                                font=self.default_font,
                                bg='#6c757d',
                                fg='white',
                                relief=tk.FLAT,
                                width=6)
            delete_btn.pack(side=tk.LEFT, padx=5)
            
            # 绑定鼠标悬停事件
            for btn in [freeze_btn, delete_btn]:
                btn.bind('<Enter>', lambda e, b=btn: self.on_hover(e, b))
                btn.bind('<Leave>', lambda e, b=btn: self.on_leave(e, b))

    def toggle_freeze_with_button(self, process_id):
        # 切换冻结状态
        if process_id in self.process_manager.processes:
            self.process_manager.toggle_freeze(process_id)
            # 更新列表显示
            self.update_process_list()
            self.update_tray_icon()

    def minimize_to_tray(self):
        """最小化到托盘"""
        try:
            if self.window.winfo_exists():  # 确保窗口还存在
                self.window.withdraw()  # 隐藏窗口
                logging.info("Window minimized to tray successfully")
        except Exception as e:
            error_msg = f"Failed to minimize window to tray: {str(e)}"
            logging.error(error_msg)
            logging.error(f"Traceback:\n{traceback.format_exc()}")
    
    def quit_app(self, from_tray=False):
        """退出应用程序"""
        try:
            # 如果是从托盘退出，或者用户确认退出
            if from_tray or messagebox.askokcancel("确认退出", "确定要退出程序吗？"):
                logging.info("User confirmed application exit")
                
                # 停止快捷键检查
                self.running = False
                logging.info("Hotkey check stopped")
                
                # 确保在退出前清理所有快捷键
                try:
                    keyboard.unhook_all()
                    self.hotkey_registered = False
                    logging.info("All keyboard hooks cleared")
                except Exception as e:
                    logging.error(f"Error clearing keyboard hooks: {str(e)}")
                
                # 停止托盘图标
                try:
                    if hasattr(self, 'tray_icon'):
                        self.tray_icon.stop()
                        logging.info("Tray icon stopped")
                except Exception as e:
                    logging.error(f"Error stopping tray icon: {str(e)}")
                
                # 销毁窗口
                try:
                    self.window.quit()
                    self.window.destroy()
                    logging.info("Main window destroyed")
                except Exception as e:
                    logging.error(f"Error destroying window: {str(e)}")
                
                logging.info("Application exit successful")
                sys.exit(0)  # 使用sys.exit代替os._exit以允许清理
        except Exception as e:
            error_msg = f"Critical error during application exit: {str(e)}"
            logging.error(error_msg)
            logging.error(f"Traceback:\n{traceback.format_exc()}")
            sys.exit(1)  # 使用sys.exit代替os._exit以允许清理

    def add_process(self):
        dialog = AddProcessDialog(self.window)
        self.window.wait_window(dialog.dialog)
        if dialog.result:
            self.process_manager.add_process(dialog.result[0], dialog.result[1])
            self.update_process_list()
            self.update_tray_icon()
            
    def remove_process(self, process_id):
        # 获取进程名称
        process_name = self.process_manager.processes[process_id].get("name", process_id)
        # 显示确认对话框
        if messagebox.askokcancel("确认删除", f"确定要删除进程 {process_name} 吗？"):
            self.process_manager.remove_process(process_id)
            self.update_process_list()
            self.update_tray_icon()
        
    def toggle_freeze(self, process_id, var):
        success = self.process_manager.toggle_freeze(process_id)
        if not success:
            messagebox.showerror("错误", f"无法切换进程 {process_id} 的状态")
            # Reset checkbox state
            var.set(not var.get())
        self.update_process_list()
        self.update_tray_icon()
        
    def run(self):
        self.window.mainloop()

    def create_icon_image(self):
        """创建托盘图标图像"""
        frozen_count = len([p for p in self.process_manager.processes.values() if p['is_frozen']])
        
        # 根据是否有冻结进程选择图标
        if frozen_count > 0:
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
        else:
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon_inactive.ico")

        if os.path.exists(icon_path):
            image = Image.open(icon_path)
            image = image.convert('RGBA')
        else:
            # 如果图标文件不存在，创建默认的圆形图标
            image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            dc = ImageDraw.Draw(image)
            icon_color = '#007bff' if frozen_count > 0 else '#6c757d'
            dc.ellipse([4, 4, 60, 60], fill=icon_color)
        
        # 如果设置为显示数字且有冻结进程，则绘制数字
        if self.settings.show_icon_count and frozen_count > 0:
           # 创建一个新的图层用于绘制数字
            txt_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
            dc = ImageDraw.Draw(txt_layer)
            
            # 计算文本大小和位置
            text = str(frozen_count)
            font_size = int(image.width * 0.7)  # 增大字体大小为图标宽度的70%
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                font = None
                
            # 获取文本大小
            if font:
                text_bbox = dc.textbbox((0, 0), text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
            else:
                text_width = font_size
                text_height = font_size
            
            # 为阴影创建稍大的粗体字体
            shadow_font_size = int(font_size * 1.5)  # 阴影字体大1.5倍
            shadow_font = None
            try:
                # 尝试使用Arial Bold字体
                shadow_font = ImageFont.truetype("arialbd.ttf", shadow_font_size)
            except:
                try:
                    # 备选：使用Arial Bold的另一种写法
                    shadow_font = ImageFont.truetype("arial bold", shadow_font_size)
                except:
                    shadow_font = font

            # 获取阴影文本的大小
            if shadow_font:
                shadow_bbox = dc.textbbox((0, 0), text, font=shadow_font)
                shadow_width = shadow_bbox[2] - shadow_bbox[0]
                shadow_height = shadow_bbox[3] - shadow_bbox[1]
            else:
                shadow_width = shadow_font_size
                shadow_height = shadow_font_size

            # 计算阴影和主文本的中心点位置
            center_x = image.width // 2
            center_y = image.height // 2

            # 计算阴影文本位置（使其居中）
            shadow_x = center_x - shadow_width // 2
            shadow_y = center_y - shadow_height // 1.4

            # 计算主文本位置（使其居中）
            main_x = center_x - text_width // 2
            main_y = center_y - text_height // 1.5

            # 绘制较大的阴影文本
            dc.text((shadow_x, shadow_y), text, fill=self.settings.icon_shadow_color, font=shadow_font)
            # 绘制主文本
            dc.text((main_x, main_y), text, fill=self.settings.icon_number_color, font=font)
            
            # 将文本图层合并到主图像
            image = Image.alpha_composite(image, txt_layer)
        
        return image

    def create_tray_icon(self):
        """创建系统托盘图标"""
        def toggle_process(process_id):
            """切换进程状态的包装函数"""
            return lambda: self.toggle_from_tray(process_id)
            
        def quit_from_tray(icon):
            """从托盘退出的包装函数"""
            self.quit_app(from_tray=True)
        
        def get_menu():
            """获取最新的菜单项"""
            processes = self.process_manager.processes
            menu_items = []
            
            # 添加所有已添加的进程到菜单
            for proc_id, data in processes.items():
                display_name = data.get("name", proc_id)
                is_frozen = data.get("is_frozen", False)
                # 为已冻结的进程添加雪花图标
                prefix = "❄ " if is_frozen else "  "
                text = f"{prefix}{'解冻' if is_frozen else '冻结'} {display_name}"
                menu_items.append(
                    pystray.MenuItem(
                        text,
                        toggle_process(proc_id)
                    )
                )
            
            # 添加分隔线
            if menu_items:
                menu_items.append(pystray.Menu.SEPARATOR)
            
            # 添加显示窗口和退出选项
            menu_items.extend([
                pystray.MenuItem(
                    "显示主窗口",
                    self.show_window,
                    default=True  # 设置为默认动作（双击时执行）
                ),
                pystray.MenuItem(
                    "退出",
                    quit_from_tray  # 使用包装函数
                )
            ])
            
            return pystray.Menu(*menu_items)
        
        # 保存get_menu函数以供后续更新使用
        self.get_tray_menu = get_menu

        # 创建托盘图标
        self.tray_icon = pystray.Icon(
            "process_freezer",
            self.create_icon_image(),  # 使用新的方法创建图标
            "进程冻结器",
            menu=get_menu()
        )
        
        # 在单独的线程中启动托盘图标
        self.tray_icon.run_detached()

    def update_tray_icon(self):
        """更新托盘图标"""
        if hasattr(self, 'tray_icon'):
            self.tray_icon.icon = self.create_icon_image()
            self.tray_icon.menu = self.get_tray_menu()

    def toggle_from_tray(self, process_id):
        """从托盘菜单切换进程状态"""
        success = self.process_manager.toggle_freeze(process_id)
        if not success:
            # 在托盘图标显示通知
            self.tray_icon.notify(
                "错误",
                f"无法切换进程 {process_id} 的状态"
            )
        else:
            # 更新托盘图标和菜单
            self.update_tray_icon()
            # 如果主窗口可见，更新显示
            if self.window.winfo_viewable():
                self.update_process_list()

    def show_window(self):
        """显示主窗口"""
        try:
            self.window.deiconify()  # 显示窗口
            self.window.state('normal')  # 确保窗口不是最小化状态
            self.window.lift()  # 将窗口提升到顶层
            self.window.focus_force()  # 强制获取焦点
            
            # 添加短暂延迟后再设置置顶状态
            self.window.after(100, lambda: self.set_window_on_top(self.settings.always_on_top))
            
            # 更新进程列表
            self.update_process_list()
            logging.info("Window shown successfully")
        except Exception as e:
            error_msg = f"Failed to show window: {str(e)}"
            logging.error(error_msg)
            logging.error(f"Traceback:\n{traceback.format_exc()}")

    def handle_minimize(self, event):
        """处理最小化事件"""
        # 如果是最小化操作，则隐藏到托盘
        if self.window.state() == 'iconic':
            self.minimize_to_tray()

    def show_settings_menu(self, event):
        """显示设置菜单"""
        # 创建设置菜单
        settings_menu = tk.Menu(self.window, tearoff=0)
        
        # 添加分组标题（不可点击）
        settings_menu.add_command(label="托盘图标", state="disabled")
        settings_menu.add_separator()
        
        # 显示图标数字选项
        self.show_count_var = tk.BooleanVar(value=self.settings.show_icon_count)
        settings_menu.add_checkbutton(label="    显示冻结数量", 
                                variable=self.show_count_var,
                                command=self.toggle_icon_count)
        
        # 颜色选择按钮
        settings_menu.add_command(label="    设置数字颜色", command=self.set_number_color)
        settings_menu.add_command(label="    设置阴影颜色", command=self.set_shadow_color)
        
        # 添加进程冻结设置分组
        settings_menu.add_separator()
        settings_menu.add_command(label="进程冻结", state="disabled")
        settings_menu.add_separator()
        
        # 添加隐藏窗口选项
        self.hide_window_var = tk.BooleanVar(value=self.settings.hide_window)
        settings_menu.add_checkbutton(label="    冻结时隐藏窗口", 
                                    variable=self.hide_window_var,
                                    command=self.toggle_hide_window)
        
        # 添加窗口设置分组
        settings_menu.add_separator()
        settings_menu.add_command(label="窗口设置", state="disabled")
        settings_menu.add_separator()
        
        # 添加窗口置顶选项
        self.always_on_top_var = tk.BooleanVar(value=self.settings.always_on_top)
        settings_menu.add_checkbutton(label="    窗口置顶", 
                                    variable=self.always_on_top_var,
                                    command=self.toggle_window_on_top)
        
        # 添加快捷键设置分组
        settings_menu.add_separator()
        settings_menu.add_command(label="快捷键设置", state="disabled")
        settings_menu.add_separator()
        
        # 添加修改快捷键选项
        settings_menu.add_command(label="    修改显示/隐藏快捷键", 
                                command=self.set_toggle_hotkey)

        # 添加程序操作分组
        settings_menu.add_separator()
        settings_menu.add_command(label="程序操作", state="disabled")
        settings_menu.add_separator()
        settings_menu.add_command(label="    最小化到托盘", 
                                command=self.minimize_to_tray)
        settings_menu.add_command(label="    退出程序", 
                                command=self.quit_app,
                                foreground='#dc3545')  # 使用红色突出显示退出选项
        
        # 显示菜单
        settings_menu.post(event.x_root, event.y_root)

    def toggle_icon_count(self):
        """切换是否显示图标数字"""
        self.settings.show_icon_count = self.show_count_var.get()
        self.settings.save_settings()
        self.update_tray_icon()

    def toggle_hide_window(self):
        """切换是否在冻结时隐藏窗口"""
        self.settings.hide_window = self.hide_window_var.get()
        self.settings.save_settings()

    def set_number_color(self):
        """设置数字颜色"""
        color = tk.colorchooser.askcolor(color=self.settings.icon_number_color,
                                       title="选择数字颜色")
        if color and color[1]:  # color[1] 是十六进制颜色值
            self.settings.icon_number_color = color[1]
            self.settings.save_settings()
            self.update_tray_icon()

    def set_shadow_color(self):
        """设置阴影颜色"""
        color = tk.colorchooser.askcolor(color=self.settings.icon_shadow_color,
                                       title="选择阴影颜色")
        if color and color[1]:  # color[1] 是十六进制颜色值
            self.settings.icon_shadow_color = color[1]
            self.settings.save_settings()
            self.update_tray_icon()

    def set_window_on_top(self, on_top):
        """设置窗口置顶状态"""
        self.window.attributes('-topmost', on_top)
        self.settings.always_on_top = on_top
        self.settings.save_settings()

    def toggle_window_on_top(self):
        """切换窗口置顶状态"""
        on_top = self.always_on_top_var.get()
        self.set_window_on_top(on_top)

    def ensure_hotkey_registered(self):
        """确保快捷键被正确注册"""
        if not self.running:
            return
            
        try:
            if not self.hotkey_registered:
                logging.warning("Hotkey not registered, attempting to register")
                self.register_hotkey()
            else:
                # 测试快捷键是否仍然有效
                try:
                    hotkeys = keyboard._listener.handlers.get(self.settings.toggle_hotkey, [])
                    if not hotkeys:
                        logging.warning("Hotkey handler not found, re-registering")
                        self.register_hotkey()
                except Exception as e:
                    logging.error(f"Error checking hotkey status: {str(e)}")
                    logging.error(f"Traceback:\n{traceback.format_exc()}")
                    self.register_hotkey()
            
            # 只有在程序仍在运行时才继续检查
            if self.running:
                self.window.after(10000, self.ensure_hotkey_registered)  # 每10秒检查一次
        except Exception as e:
            logging.error(f"Error in ensure_hotkey_registered: {str(e)}")
            logging.error(f"Traceback:\n{traceback.format_exc()}")
            # 发生错误时，尝试重新注册
            if self.running:
                self.register_hotkey()

    def register_hotkey(self):
        """注册全局快捷键"""
        try:
            # 先清除已有的快捷键绑定
            keyboard.unhook_all()
            logging.info("Previous hotkeys cleared")
            
            def hotkey_callback():
                try:
                    if not self.window.winfo_exists():
                        logging.warning("Window does not exist, skipping hotkey action")
                        return
                        
                    # 将窗口操作放入主线程队列
                    self.window.after(0, self._handle_hotkey_action)
                except Exception as e:
                    logging.error(f"Error in hotkey callback: {str(e)}")
                    logging.error(f"Traceback:\n{traceback.format_exc()}")
                    self.retry_register_hotkey()

            # 注册新的快捷键
            keyboard.add_hotkey(
                self.settings.toggle_hotkey,
                hotkey_callback,
                suppress=True,
                trigger_on_release=True
            )
            
            self.hotkey_registered = True
            self.hotkey_retry_count = 0
            logging.info(f"Global hotkey registered successfully: {self.settings.toggle_hotkey}")
            
        except Exception as e:
            error_msg = f"Failed to register hotkey: {str(e)}"
            logging.error(error_msg)
            logging.error(f"Traceback:\n{traceback.format_exc()}")
            self.retry_register_hotkey()

    def retry_register_hotkey(self):
        """重试注册快捷键"""
        MAX_RETRY_COUNT = 5  # 最大重试次数
        try:
            if self.hotkey_retry_count < MAX_RETRY_COUNT:
                self.hotkey_retry_count += 1
                retry_delay = min(1000 * (2 ** self.hotkey_retry_count), 30000)  # 指数退避，最大30秒
                logging.info(f"Retrying hotkey registration (attempt {self.hotkey_retry_count}) after {retry_delay}ms")
                self.window.after(retry_delay, self.register_hotkey)
            else:
                logging.error("Max retry attempts reached for hotkey registration")
                self.hotkey_retry_count = 0  # 重置重试计数
                messagebox.showerror("错误", "快捷键注册失败，请尝试重启应用")
        except Exception as e:
            logging.error(f"Error in retry_register_hotkey: {str(e)}")
            logging.error(f"Traceback:\n{traceback.format_exc()}")

    def _handle_hotkey_action(self):
        """处理快捷键动作"""
        try:
            current_state = self.window.state()
            is_visible = self.window.winfo_viewable()
            logging.debug(f"Window state: {current_state}, Visible: {is_visible}")
            
            if current_state == 'withdrawn' or not is_visible:
                logging.info("Hotkey pressed: Showing window")
                self.show_window()
            else:
                logging.info("Hotkey pressed: Minimizing window")
                self.minimize_to_tray()
        except Exception as e:
            logging.error(f"Error handling hotkey action: {str(e)}")

    def set_toggle_hotkey(self):
        """设置显示/隐藏快捷键"""
        dialog = HotkeyDialog(self.window, self.settings.toggle_hotkey)
        self.window.wait_window(dialog.dialog)
        if dialog.result:
            try:
                # 更新快捷键设置
                self.settings.toggle_hotkey = dialog.result
                self.settings.save_settings()
                
                # 重置状态并重新注册快捷键
                self.hotkey_registered = False
                self.hotkey_retry_count = 0
                self.register_hotkey()
                
                messagebox.showinfo("成功", f"快捷键已更新为: {dialog.result}")
            except Exception as e:
                logging.error(f"Error setting hotkey: {str(e)}")
                messagebox.showerror("错误", f"设置快捷键失败: {str(e)}")

    def _on_mousewheel(self, event):
        # 检查鼠标是否在canvas区域内
        canvas_x = self.canvas.winfo_rootx()
        canvas_y = self.canvas.winfo_rooty()
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        mouse_x = self.window.winfo_pointerx()
        mouse_y = self.window.winfo_pointery()
        
        if (canvas_x <= mouse_x <= canvas_x + canvas_width and
            canvas_y <= mouse_y <= canvas_y + canvas_height):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

class AddProcessDialog:
    def __init__(self, parent):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("添加进程")
        self.dialog.geometry("400x400")
        self.dialog.configure(bg='#f0f0f0')
        self.dialog.resizable(False, False)
        
        # 设置字体
        self.default_font = ('Microsoft YaHei UI', 10)
        self.title_font = ('Microsoft YaHei UI', 12, 'bold')
        
        # 主框架
        main_frame = tk.Frame(self.dialog, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 标题
        title_label = tk.Label(main_frame,
                             text="添加进程",
                             font=self.title_font,
                             bg='#f0f0f0',
                             fg='#333333')
        title_label.pack(pady=(0, 20))

        # 拖动手柄框架
        handle_frame = tk.Frame(main_frame, bg='#f0f0f0')
        handle_frame.pack(fill=tk.X, pady=(0, 20))
        
        handle_label = tk.Label(handle_frame,
                              text="拖动句柄到目标窗口获取进程标识：",
                              font=self.default_font,
                              bg='#f0f0f0',
                              fg='#333333')
        handle_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # 创建拖动手柄
        self.drag_handle = DragHandle(handle_frame, self.on_process_identified)
        self.drag_handle.pack(side=tk.LEFT)
        
        # 进程ID输入框架
        id_frame = tk.Frame(main_frame, bg='#f0f0f0')
        id_frame.pack(fill=tk.X, pady=(0, 10))
        
        id_label = tk.Label(id_frame,
                          text="进程标识符：",
                          font=self.default_font,
                          bg='#f0f0f0',
                          fg='#333333')
        id_label.pack(side=tk.LEFT)
        
        self.id_entry = tk.Entry(id_frame,
                               font=self.default_font,
                               width=30)
        self.id_entry.pack(side=tk.LEFT, padx=(10, 0))
        
        # 进程名称输入框架
        name_frame = tk.Frame(main_frame, bg='#f0f0f0')
        name_frame.pack(fill=tk.X, pady=(0, 20))
        
        name_label = tk.Label(name_frame,
                            text="进程名称：",
                            font=self.default_font,
                            bg='#f0f0f0',
                            fg='#333333')
        name_label.pack(side=tk.LEFT)
        
        self.name_entry = tk.Entry(name_frame,
                                 font=self.default_font,
                                 width=30)
        self.name_entry.pack(side=tk.LEFT, padx=(10, 0))
        
        # 按钮框架
        button_frame = tk.Frame(main_frame, bg='#f0f0f0')
        button_frame.pack(pady=10)
        
        # 确定按钮
        self.ok_button = tk.Button(button_frame,
                                 text="确定",
                                 command=self.ok,
                                 font=self.default_font,
                                 bg='#007bff',
                                 fg='white',
                                 relief=tk.FLAT,
                                 width=10)
        self.ok_button.pack(side=tk.LEFT, padx=5)
        
        # 取消按钮
        self.cancel_button = tk.Button(button_frame,
                                     text="取消",
                                     command=self.cancel,
                                     font=self.default_font,
                                     bg='#6c757d',
                                     fg='white',
                                     relief=tk.FLAT,
                                     width=10)
        self.cancel_button.pack(side=tk.LEFT, padx=5)
        
        # 绑定鼠标悬停事件
        for btn in [self.ok_button, self.cancel_button]:
            btn.bind('<Enter>', lambda e, b=btn: self.on_hover(e, b))
            btn.bind('<Leave>', lambda e, b=btn: self.on_leave(e, b))

        self.result = None
        
        # 设置对话框为模态
        self.dialog.transient(parent)
        self.dialog.grab_set()
    
    def on_process_identified(self, process_name, window_title):
        """当通过拖动识别到进程时调用"""
        self.id_entry.delete(0, tk.END)
        self.id_entry.insert(0, process_name)
        
        # 如果名称框为空，则使用窗口标题作为默认名称
        if not self.name_entry.get() and window_title:
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, window_title)
    
    def on_hover(self, event, button):
        """鼠标悬停效果"""
        if button == self.ok_button:
            button.configure(bg='#0056b3')  # 深蓝色
        else:
            button.configure(bg='#5a6268')  # 深灰色
    
    def on_leave(self, event, button):
        """鼠标离开效果"""
        if button == self.ok_button:
            button.configure(bg='#007bff')  # 恢复蓝色
        else:
            button.configure(bg='#6c757d')  # 恢复灰色
    
    def ok(self):
        """确定按钮回调"""
        process_id = self.id_entry.get().strip()
        process_name = self.name_entry.get().strip()
        
        if not process_id:
            messagebox.showerror("错误", "请输入进程标识符")
            return
        
        self.result = (process_id, process_name)
        self.dialog.destroy()
    
    def cancel(self):
        """取消按钮回调"""
        self.dialog.destroy()

# 新增：快捷键设置对话框
class HotkeyDialog:
    def __init__(self, parent, current_hotkey):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("设置快捷键")
        self.dialog.geometry("400x200")
        self.dialog.configure(bg='#f0f0f0')
        self.dialog.resizable(False, False)
        
        self.default_font = ('Microsoft YaHei UI', 10)
        self.result = None
        
        # 主框架
        main_frame = tk.Frame(self.dialog, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 说明标签
        instruction = tk.Label(main_frame,
                             text="请按下新的快捷键组合\n当前快捷键: " + current_hotkey,
                             font=self.default_font,
                             bg='#f0f0f0',
                             fg='#333333')
        instruction.pack(pady=20)
        
        # 快捷键显示框
        self.hotkey_var = tk.StringVar(value="按下快捷键...")
        self.hotkey_label = tk.Label(main_frame,
                                   textvariable=self.hotkey_var,
                                   font=('Microsoft YaHei UI', 12, 'bold'),
                                   bg='white',
                                   fg='#007bff',
                                   relief=tk.SUNKEN,
                                   padx=10,
                                   pady=5)
        self.hotkey_label.pack(pady=20)
        
        # 按钮框架
        button_frame = tk.Frame(main_frame, bg='#f0f0f0')
        button_frame.pack(pady=10)
        
        # 确定按钮
        self.ok_button = tk.Button(button_frame,
                                 text="确定",
                                 command=self.ok,
                                 font=self.default_font,
                                 bg='#007bff',
                                 fg='white',
                                 relief=tk.FLAT,
                                 width=10,
                                 state=tk.DISABLED)
        self.ok_button.pack(side=tk.LEFT, padx=5)
        
        # 取消按钮
        self.cancel_button = tk.Button(button_frame,
                                     text="取消",
                                     command=self.cancel,
                                     font=self.default_font,
                                     bg='#6c757d',
                                     fg='white',
                                     relief=tk.FLAT,
                                     width=10)
        self.cancel_button.pack(side=tk.LEFT, padx=5)
        
        # 开始监听按键
        self.current_keys = set()
        keyboard.hook(self.on_key_event)
        
        # 设置对话框为模态
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
    def on_key_event(self, event):
        """处理按键事件"""
        try:
            if not self.dialog.winfo_exists():  # 检查对话框是否还存在
                return
                
            if event.event_type == 'down':
                self.current_keys.add(event.name)
            elif event.event_type == 'up':
                if event.name in self.current_keys:
                    self.current_keys.remove(event.name)
                
                if not self.current_keys:  # 当所有键都释放时
                    if len(set(event.name) | self.current_keys) > 1:  # 确保不是单个按键
                        hotkey = '+'.join(sorted(set(event.name) | self.current_keys))
                        self.hotkey_var.set(hotkey)
                        if self.ok_button.winfo_exists():  # 检查按钮是否还存在
                            self.ok_button.configure(state=tk.NORMAL)
        except Exception as e:
            logging.error(f"Error in hotkey dialog: {str(e)}")
            keyboard.unhook_all()  # 出错时清理键盘钩子
    
    def ok(self):
        """确定按钮回调"""
        try:
            self.result = self.hotkey_var.get()
        finally:
            keyboard.unhook_all()  # 确保在任何情况下都清理键盘钩子
            self.dialog.destroy()
    
    def cancel(self):
        """取消按钮回调"""
        try:
            keyboard.unhook_all()  # 清理键盘钩子
        finally:
            self.dialog.destroy()

if __name__ == '__main__':
    settings = Settings()  # 新增：创建 Settings 实例
    process_manager = ProcessManager(settings)  # 传入 settings 实例
    app = ProcessListWindow(process_manager)
    app.run()
