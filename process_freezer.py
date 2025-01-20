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
from PIL import Image, ImageDraw

# 设置日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('process_freezer.log'),
        logging.StreamHandler()
    ]
)

class ProcessManager:
    def __init__(self):
        self.processes = {}
        self.config_file = "processes.json"
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
                    result = subprocess.run(['pssuspend64.exe', identifier], 
                                         check=True, 
                                         capture_output=True,
                                         text=True,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode == 0:
                        self.processes[identifier]["is_frozen"] = True
                        logging.info(f"Successfully froze process: {identifier}")
                    else:
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
        self.window = tk.Tk()
        self.window.title("进程冻结器")
        self.window.geometry("700x400")
        self.window.configure(bg='#f0f0f0')  # 设置窗口背景色
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(__file__), "icon.ico")
        if os.path.exists(icon_path):
            self.window.iconbitmap(icon_path)
        
        # 绑定窗口事件
        self.window.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        self.window.bind("<Unmap>", lambda e: self.handle_minimize(e))
        
        # 设置统一的字体
        self.default_font = ('Microsoft YaHei UI', 10)
        self.title_font = ('Microsoft YaHei UI', 12, 'bold')
        
        self.process_manager = process_manager
        
        # 创建托盘图标
        self.create_tray_icon()
        
        # 创建主框架
        main_frame = tk.Frame(self.window, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 标题
        title_label = tk.Label(main_frame, 
                             text="进程管理器", 
                             font=self.title_font,
                             bg='#f0f0f0',
                             fg='#333333')
        title_label.pack(pady=(0, 10))
        
        # 添加进程按钮（使用现代风格）
        add_button = tk.Button(main_frame,
                             text="添加进程",
                             command=self.add_process,
                             font=self.default_font,
                             bg='#007bff',
                             fg='white',
                             relief=tk.FLAT,
                             padx=15)
        add_button.pack(pady=(0, 10))
        
        # 创建进程列表框架（带滚动条）
        list_container = tk.Frame(main_frame, bg='#f0f0f0')
        list_container.pack(fill=tk.BOTH, expand=True)
        
        # 添加滚动条
        scrollbar = tk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 进程列表框架
        self.list_frame = tk.Frame(list_container, bg='white')
        self.list_frame.pack(fill=tk.BOTH, expand=True)
        
        # 底部按钮框架
        button_frame = tk.Frame(main_frame, bg='#f0f0f0')
        button_frame.pack(pady=10)
        
        # 最小化按钮
        minimize_btn = tk.Button(button_frame,
                               text="最小化",
                               command=self.minimize_to_tray,
                               font=self.default_font,
                               bg='#6c757d',
                               fg='white',
                               relief=tk.FLAT,
                               padx=15)
        minimize_btn.pack(side=tk.LEFT, padx=5)
        
        # 退出按钮
        quit_btn = tk.Button(button_frame,
                           text="退出",
                           command=self.quit_app,
                           font=self.default_font,
                           bg='#dc3545',
                           fg='white',
                           relief=tk.FLAT,
                           padx=15)
        quit_btn.pack(side=tk.LEFT, padx=5)
        
        self.update_process_list()
        
        # 绑定鼠标悬停事件
        for btn in [add_button, minimize_btn, quit_btn]:
            btn.bind('<Enter>', lambda e, b=btn: self.on_hover(e, b))
            btn.bind('<Leave>', lambda e, b=btn: self.on_leave(e, b))

    def on_hover(self, event, button):
        # 鼠标悬停时改变按钮颜色
        if button['text'] == "添加进程":
            button.configure(bg='#0056b3')
        elif button['text'] == "最小化":
            button.configure(bg='#5a6268')
        elif button['text'] == "冻结":
            button.configure(bg='#c82333')
        elif button['text'] == "解冻":
            button.configure(bg='#218838')
        elif button['text'] == "删除":
            button.configure(bg='#5a6268')
        else:  # 退出按钮
            button.configure(bg='#c82333')

    def on_leave(self, event, button):
        # 鼠标离开时恢复按钮颜色
        if button['text'] == "添加进程":
            button.configure(bg='#007bff')
        elif button['text'] == "最小化":
            button.configure(bg='#6c757d')
        elif button['text'] == "冻结":
            button.configure(bg='#dc3545')
        elif button['text'] == "解冻":
            button.configure(bg='#28a745')
        elif button['text'] == "删除":
            button.configure(bg='#6c757d')
        else:  # 退出按钮
            button.configure(bg='#dc3545')

    def update_process_list(self):
        # 清除现有项目
        for widget in self.list_frame.winfo_children():
            widget.destroy()
            
        # 添加表头
        header_frame = tk.Frame(self.list_frame, bg='#f8f9fa')
        header_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        # 表头标签
        headers = [
            ("进程名称", 200),
            ("进程标识符", 200),
            ("状态", 100),
            ("操作", 180)
        ]
        
        for text, width in headers:
            header_label = tk.Label(header_frame,
                                  text=text,
                                  font=(self.default_font[0], self.default_font[1], 'bold'),
                                  bg='#f8f9fa',
                                  fg='#495057',
                                  width=width // 10)  # 转换为大约的字符宽度
            header_label.pack(side=tk.LEFT, padx=10, pady=5)
            
        # 添加分隔线
        separator = tk.Frame(self.list_frame, height=2, bg='#dee2e6')
        separator.pack(fill=tk.X, padx=10, pady=(0, 5))
            
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
                                width=20)
            name_label.pack(side=tk.LEFT, padx=10, pady=5)
            
            # 进程ID标签
            id_label = tk.Label(item_frame,
                              text=proc_id,
                              font=self.default_font,
                              bg='white',
                              fg='#333333',
                              width=20)
            id_label.pack(side=tk.LEFT, padx=10)
            
            # 状态标签
            status_text = "已冻结" if data.get("is_frozen", False) else "未冻结"
            status_color = "#dc3545" if data.get("is_frozen", False) else "#28a745"
            status_label = tk.Label(item_frame,
                                  text=status_text,
                                  font=self.default_font,
                                  bg='white',
                                  fg=status_color,
                                  width=10)
            status_label.pack(side=tk.LEFT, padx=10)
            
            # 按钮框架（居中对齐）
            button_frame = tk.Frame(item_frame, bg='white')
            button_frame.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
            
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

    def minimize_to_tray(self):
        """最小化到托盘"""
        self.window.withdraw()  # 隐藏窗口
    
    def quit_app(self):
        if messagebox.askokcancel("确认", "确定要退出程序吗？"):
            # 先停止托盘图标
            if hasattr(self, 'tray_icon'):
                self.tray_icon.stop()
            # 销毁主窗口
            self.window.quit()
            # 退出程序
            sys.exit(0)
    
    def quit_from_tray(self):
        """从托盘菜单退出程序"""
        # 先停止托盘图标
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
        # 销毁主窗口
        self.window.quit()
        # 退出程序
        sys.exit(0)

    def add_process(self):
        dialog = AddProcessDialog(self.window)
        self.window.wait_window(dialog.dialog)
        if dialog.result:
            self.process_manager.add_process(dialog.result[0], dialog.result[1])
            self.update_process_list()
            
    def remove_process(self, process_id):
        self.process_manager.remove_process(process_id)
        self.update_process_list()
        
    def toggle_freeze(self, process_id, var):
        success = self.process_manager.toggle_freeze(process_id)
        if not success:
            messagebox.showerror("错误", f"无法切换进程 {process_id} 的状态")
            # Reset checkbox state
            var.set(not var.get())
        self.update_process_list()
        
    def run(self):
        self.window.mainloop()

    def create_tray_icon(self):
        """创建系统托盘图标"""
        # 使用ico文件作为托盘图标
        icon_path = os.path.join(os.path.dirname(__file__), "icon.ico")
        if os.path.exists(icon_path):
            image = Image.open(icon_path)
        else:
            # 如果找不到图标文件，使用默认的圆形图标
            icon_size = 64
            image = Image.new('RGBA', (icon_size, icon_size), (0, 0, 0, 0))
            dc = ImageDraw.Draw(image)
            margin = 4
            dc.ellipse(
                [margin, margin, icon_size - margin, icon_size - margin],
                fill='#007bff'
            )
        
        def toggle_process(process_id):
            """切换进程状态的包装函数"""
            return lambda: self.toggle_from_tray(process_id)
        
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
                    self.quit_from_tray  # 使用专门的托盘退出函数
                )
            ])
            
            return pystray.Menu(*menu_items)
        
        # 保存get_menu函数以供后续更新使用
        self.get_tray_menu = get_menu

        # 创建托盘图标
        self.tray_icon = pystray.Icon(
            "process_freezer",
            image,
            "进程冻结器",
            menu=get_menu()
        )
        
        # 在单独的线程中启动托盘图标
        self.tray_icon.run_detached()
    
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
            # 更新托盘菜单
            self.tray_icon.menu = self.get_tray_menu()
            # 如果主窗口可见，更新显示
            if self.window.winfo_viewable():
                self.update_process_list()
    
    def show_window(self):
        """显示主窗口"""
        self.window.deiconify()  # 显示窗口
        self.window.state('normal')  # 确保窗口不是最小化状态
        self.window.lift()  # 将窗口提升到顶层
        self.window.focus_force()  # 强制获取焦点
    
    def quit_app(self):
        """退出应用程序"""
        # 先停止托盘图标
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
        # 销毁主窗口
        self.window.quit()
        # 退出程序
        sys.exit(0)

    def handle_minimize(self, event):
        """处理最小化事件"""
        # 如果是最小化操作，则隐藏到托盘
        if self.window.state() == 'iconic':
            self.minimize_to_tray()

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

if __name__ == '__main__':
    process_manager = ProcessManager()
    app = ProcessListWindow(process_manager)
    app.run()
