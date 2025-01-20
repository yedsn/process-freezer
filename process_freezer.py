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
        self.window.geometry("400x300")
        self.window.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        
        self.process_manager = process_manager
        
        # Add process button
        tk.Button(self.window, text="添加进程", command=self.add_process).pack(pady=5)
        
        # Process list (using a frame with scrollbar)
        self.list_frame = tk.Frame(self.window)
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add a minimize button
        tk.Button(self.window, text="最小化到托盘", command=self.minimize_to_tray).pack(pady=5)
        
        self.update_process_list()
        
    def minimize_to_tray(self):
        self.window.withdraw()  # 隐藏窗口
        
        # 创建系统托盘菜单
        if not hasattr(self, 'tray_menu'):
            self.tray_menu = tk.Menu(self.window, tearoff=0)
            self.tray_menu.add_command(label="显示", command=self.show_window)
            self.tray_menu.add_separator()
            self.tray_menu.add_command(label="退出", command=self.quit_app)
            
            # 绑定右键菜单
            self.window.bind('<Button-3>', self.show_menu)
            
    def show_menu(self, event):
        try:
            self.tray_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tray_menu.grab_release()
            
    def show_window(self):
        self.window.deiconify()  # 显示窗口
        self.window.lift()  # 将窗口提到前台
        
    def quit_app(self):
        self.window.quit()
        
    def update_process_list(self):
        # Clear existing items
        for widget in self.list_frame.winfo_children():
            widget.destroy()
            
        # Add new items
        for proc_id, data in self.process_manager.processes.items():
            item_frame = tk.Frame(self.list_frame)
            item_frame.pack(fill=tk.X, padx=5, pady=2)
            
            # Process identifier label
            tk.Label(item_frame, text=proc_id).pack(side=tk.LEFT, padx=5)
            
            # Process name label (with error handling)
            process_name = data.get("name", proc_id)  # 如果没有name，使用proc_id
            tk.Label(item_frame, text=process_name).pack(side=tk.LEFT, padx=5)
            
            # Freeze checkbox
            var = tk.BooleanVar(value=data.get("is_frozen", False))
            cb = tk.Checkbutton(item_frame, text="冻结", 
                              variable=var, 
                              command=lambda pid=proc_id, v=var: self.toggle_freeze(pid, v))
            cb.pack(side=tk.LEFT, padx=5)
            
            # Remove button
            tk.Button(item_frame, text="删除", 
                     command=lambda pid=proc_id: self.remove_process(pid)).pack(side=tk.RIGHT, padx=5)
            
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
        self.dialog.geometry("300x150")
        self.dialog.resizable(False, False)
        
        # Process identifier input
        tk.Label(self.dialog, text="进程标识符:").pack(pady=5)
        self.process_input = tk.Entry(self.dialog)
        self.process_input.pack(pady=5)
        
        # Process name input
        tk.Label(self.dialog, text="进程名称:").pack(pady=5)
        self.name_input = tk.Entry(self.dialog)
        self.name_input.pack(pady=5)
        
        # Buttons
        button_frame = tk.Frame(self.dialog)
        button_frame.pack(pady=10)
        
        tk.Button(button_frame, text="确定", command=self.accept).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="取消", command=self.cancel).pack(side=tk.LEFT, padx=5)
        
        self.result = None
        
    def accept(self):
        self.result = (self.process_input.get().strip(), self.name_input.get().strip())
        self.dialog.destroy()
        
    def cancel(self):
        self.dialog.destroy()

if __name__ == '__main__':
    process_manager = ProcessManager()
    app = ProcessListWindow(process_manager)
    app.run()
