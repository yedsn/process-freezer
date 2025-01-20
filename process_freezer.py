import sys
import os
import json
import logging
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import psutil

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
                                         text=True)
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
                                         text=True)
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

class ProcessListWindow:
    def __init__(self, process_manager):
        self.window = tk.Tk()
        self.window.title("进程冻结器")
        self.window.geometry("700x400")
        self.window.configure(bg='#f0f0f0')  # 设置窗口背景色
        self.window.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

        # 设置统一的字体
        self.default_font = ('Microsoft YaHei UI', 10)
        self.title_font = ('Microsoft YaHei UI', 12, 'bold')
        
        self.process_manager = process_manager
        
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
        self.window.iconify()  # 最小化窗口到任务栏
    
    def quit_app(self):
        if messagebox.askokcancel("确认", "确定要退出程序吗？"):
            self.window.quit()
    
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
                             text="添加新进程",
                             font=self.title_font,
                             bg='#f0f0f0',
                             fg='#333333')
        title_label.pack(pady=(0, 20))
        
        # 进程名称输入框
        tk.Label(main_frame,
                text="进程名称:",
                font=self.default_font,
                bg='#f0f0f0',
                fg='#333333').pack()
        self.name_input = tk.Entry(main_frame,
                                 font=self.default_font,
                                 width=30)
        self.name_input.pack(pady=(0, 20))
        
        # 进程标识符输入框
        tk.Label(main_frame,
                text="进程标识符:",
                font=self.default_font,
                bg='#f0f0f0',
                fg='#333333').pack()
        self.process_input = tk.Entry(main_frame,
                                    font=self.default_font,
                                    width=30)
        self.process_input.pack(pady=(0, 20))
        
        # 提示文本
        tip_text = "提示：进程标识符通常是进程的可执行文件名，例如：notepad.exe"
        tip_label = tk.Label(main_frame,
                           text=tip_text,
                           font=(self.default_font[0], 9),
                           bg='#f0f0f0',
                           fg='#666666',
                           wraplength=300)  # 设置文本自动换行
        tip_label.pack(pady=(0, 20))
        
        # 按钮框架
        button_frame = tk.Frame(main_frame, bg='#f0f0f0')
        button_frame.pack()
        
        # 确定按钮
        ok_btn = tk.Button(button_frame,
                          text="确定",
                          command=self.accept,
                          font=self.default_font,
                          bg='#28a745',
                          fg='white',
                          relief=tk.FLAT,
                          padx=20)
        ok_btn.pack(side=tk.LEFT, padx=5)
        
        # 取消按钮
        cancel_btn = tk.Button(button_frame,
                             text="取消",
                             command=self.cancel,
                             font=self.default_font,
                             bg='#6c757d',
                             fg='white',
                             relief=tk.FLAT,
                             padx=20)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # 绑定鼠标悬停事件
        for btn in [ok_btn, cancel_btn]:
            btn.bind('<Enter>', lambda e, b=btn: self.on_hover(e, b))
            btn.bind('<Leave>', lambda e, b=btn: self.on_leave(e, b))
        
        self.result = None
        
    def on_hover(self, event, button):
        if button['text'] == "确定":
            button.configure(bg='#218838')
        else:  # 取消按钮
            button.configure(bg='#5a6268')

    def on_leave(self, event, button):
        if button['text'] == "确定":
            button.configure(bg='#28a745')
        else:  # 取消按钮
            button.configure(bg='#6c757d')
            
    def accept(self):
        self.result = (self.process_input.get().strip(), self.name_input.get().strip())
        self.dialog.destroy()
        
    def cancel(self):
        self.dialog.destroy()

if __name__ == '__main__':
    process_manager = ProcessManager()
    app = ProcessListWindow(process_manager)
    app.run()
