"""登录界面：使用 SQLite AuthDAO 验证账号并返回登录会话。"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
import secrets
import string

from database import AuthDAO


def _center_window(window: tk.Toplevel, parent: tk.Misc | None = None) -> None:
    window.update_idletasks()
    width, height = window.winfo_width(), window.winfo_height()
    if parent and parent.winfo_exists() and parent.winfo_viewable():
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
    else:
        x = max(0, (window.winfo_screenwidth() - width) // 2)
        y = max(0, (window.winfo_screenheight() - height) // 2 - 30)
    window.geometry(f"{width}x{height}+{x}+{y}")


class LoginDialog:
    def __init__(self, parent: tk.Tk):
        self.parent = parent
        self.result: dict | None = None
        self.dao = AuthDAO()

        self.window = tk.Toplevel(parent)
        self.window.title("校园运动系统 · 安全登录")
        self.window.geometry("520x650")
        self.window.minsize(520, 650)
        self.window.resizable(False, True)
        self.window.configure(bg="#EEF3FA")
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)

        self.account = tk.StringVar(value="20250101")
        self.password = tk.StringVar(value="123456")
        self.show_password = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="")
        self._build()
        self.window.bind("<Return>", lambda _event: self._submit())
        self.window.after(20, self._center)

    def _build(self) -> None:
        card = tk.Frame(
            self.window, bg="white", highlightbackground="#CBD5E1", highlightthickness=1
        )
        card.pack(fill="both", expand=True, padx=42, pady=36)

        tk.Label(card, text="校园运动健康平台", bg="white", fg="#0F172A",
                 font=("Microsoft YaHei UI", 23, "bold")).pack(pady=(32, 4))
        tk.Label(card, text="SQLite 数据库 · 角色权限 · 本地隐私保护", bg="white",
                 fg="#64748B", font=("Microsoft YaHei UI", 10)).pack(pady=(0, 28))

        form = tk.Frame(card, bg="white")
        form.pack(fill="x", padx=34)
        tk.Label(form, text="账号", bg="white", fg="#334155",
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        self.account_entry = ttk.Entry(form, textvariable=self.account, font=("Microsoft YaHei UI", 12))
        self.account_entry.pack(fill="x", pady=(7, 18), ipady=7)

        tk.Label(form, text="密码", bg="white", fg="#334155",
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        self.password_entry = ttk.Entry(
            form, textvariable=self.password, show="•", font=("Microsoft YaHei UI", 12)
        )
        self.password_entry.pack(fill="x", pady=(7, 8), ipady=7)
        ttk.Checkbutton(form, text="显示密码", variable=self.show_password,
                        command=self._toggle_password).pack(anchor="w")

        tk.Label(form, textvariable=self.status, bg="white", fg="#DC2626",
                 font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(8, 0))
        tk.Button(form, text="登 录", command=self._submit, bg="#2563EB", fg="white",
                  activebackground="#1D4ED8", activeforeground="white", relief="flat",
                  cursor="hand2", font=("Microsoft YaHei UI", 12, "bold"), pady=10).pack(
                      fill="x", pady=(12, 18)
                  )

        tk.Label(card, text="演示账号：学生 20250101 / 教师 T001 / 管理员 A001",
                 bg="white", fg="#64748B", font=("Microsoft YaHei UI", 9)).pack()

    def _center(self) -> None:
        _center_window(self.window)
        self.window.lift()
        self.account_entry.focus_set()

    def _toggle_password(self) -> None:
        self.password_entry.configure(show="" if self.show_password.get() else "•")

    def _submit(self) -> None:
        account = self.account.get().strip()
        password = self.password.get()
        if not account or not password:
            self.status.set("请输入账号和密码")
            return
        user = self.dao.authenticate(account, password)
        if not user:
            self.status.set("账号或密码错误，请重新输入")
            self.password_entry.focus_set()
            self.password_entry.selection_range(0, tk.END)
            return
        self.result = user
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()

    def show(self) -> dict | None:
        self.window.grab_set()
        self.parent.wait_window(self.window)
        return self.result


class PasswordChangeDialog:
    """初始密码强制修改和主界面通用修改密码窗口。"""

    def __init__(self, parent: tk.Misc, user: dict, force: bool = False):
        self.parent = parent
        self.user = user
        self.force = force
        self.result = False
        self.dao = AuthDAO()
        self.window = tk.Toplevel(parent)
        self.window.title("首次登录安全设置" if force else "修改密码")
        self.window.geometry("500x560" if force else "500x640")
        self.window.minsize(500, 560 if force else 640)
        self.window.resizable(False, True)
        self.window.configure(bg="#F5F8FF")
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.current = tk.StringVar()
        self.new = tk.StringVar()
        self.confirm = tk.StringVar()
        self.status = tk.StringVar(value="初始密码必须修改后才能进入系统" if force else "")
        self._build()
        self.window.after(20, lambda: _center_window(self.window, parent))

    def _build(self) -> None:
        card = tk.Frame(self.window, bg="white", highlightbackground="#D8E2F2", highlightthickness=1)
        card.pack(fill="both", expand=True, padx=32, pady=28)
        tk.Label(card, text="🔐  设置新密码", bg="white", fg="#17233D",
                 font=("Microsoft YaHei UI", 20, "bold")).pack(pady=(26, 6))
        tk.Label(card, text=f"账号：{self.user['student_id']}  ·  密码至少 6 位",
                 bg="white", fg="#86909C", font=("Microsoft YaHei UI", 10)).pack(pady=(0, 20))
        form = tk.Frame(card, bg="white")
        form.pack(fill="x", padx=30)
        if not self.force:
            self._password_field(form, "当前密码", self.current)
        self._password_field(form, "新密码", self.new)
        self._password_field(form, "确认新密码", self.confirm)
        tk.Label(form, textvariable=self.status, bg="white", fg="#F53F3F",
                 font=("Microsoft YaHei UI", 10), wraplength=330).pack(anchor="w", pady=(2, 8))
        tk.Button(form, text="确认修改", command=self._submit, bg="#165DFF", fg="white",
                  activebackground="#0E42D2", activeforeground="white", relief="flat",
                  font=("Microsoft YaHei UI", 11, "bold"), pady=9).pack(fill="x", pady=(4, 18))

    @staticmethod
    def _password_field(parent: tk.Frame, text: str, variable: tk.StringVar) -> None:
        tk.Label(parent, text=text, bg="white", fg="#4E5969",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        ttk.Entry(parent, textvariable=variable, show="•",
                  font=("Microsoft YaHei UI", 11)).pack(fill="x", pady=(5, 13), ipady=6)

    def _submit(self) -> None:
        if len(self.new.get()) < 6:
            self.status.set("新密码长度不能少于 6 位")
            return
        if self.new.get() != self.confirm.get():
            self.status.set("两次输入的新密码不一致")
            return
        if not self.force and self.current.get() == self.new.get():
            self.status.set("新密码不能与当前密码相同")
            return
        try:
            self.dao.change_password(
                str(self.user["student_id"]), self.new.get(),
                None if self.force else self.current.get(),
            )
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.result = True
        self.window.destroy()

    def _cancel(self) -> None:
        if self.force:
            if not messagebox.askyesno("退出系统", "未修改初始密码将无法进入系统，确定退出吗？", parent=self.window):
                return
        self.window.destroy()

    def show(self) -> bool:
        # 首次登录时主窗口仍处于 withdraw 状态，不能把弹窗 transient 到隐藏父窗，
        # 否则 Windows 上可能看不到强制改密窗口。
        if self.parent.winfo_viewable():
            self.window.transient(self.parent)
        self.window.deiconify()
        self.window.lift()
        self.window.attributes("-topmost", True)
        self.window.after(600, lambda: self.window.attributes("-topmost", False))
        self.window.focus_force()
        self.window.grab_set()
        self.parent.wait_window(self.window)
        return self.result


class VerificationDialog:
    """切换账号前的本地图形验证码，不依赖短信/邮件服务。"""

    def __init__(self, parent: tk.Misc):
        self.parent = parent
        self.result = False
        self.code = ""
        self.input_code = tk.StringVar()
        self.status = tk.StringVar(value="请输入图中的验证码")
        self.window = tk.Toplevel(parent)
        self.window.title("切换账号 · 人机验证")
        self.window.geometry("420x330")
        self.window.resizable(False, False)
        self.window.configure(bg="#F5F8FF")
        self._build()
        self._refresh_code()
        self.window.after(20, lambda: _center_window(self.window, parent))

    def _build(self) -> None:
        card = tk.Frame(self.window, bg="white", highlightbackground="#D8E2F2", highlightthickness=1)
        card.pack(fill="both", expand=True, padx=28, pady=24)
        tk.Label(card, text="切换账号安全验证", bg="white", fg="#17233D",
                 font=("Microsoft YaHei UI", 17, "bold")).pack(pady=(18, 4))
        tk.Label(card, text="防止自动化程序频繁切换账号", bg="white", fg="#86909C",
                 font=("Microsoft YaHei UI", 9)).pack(pady=(0, 12))
        self.canvas = tk.Canvas(card, width=210, height=64, bg="#E8F3FF", highlightthickness=0)
        self.canvas.pack()
        ttk.Button(card, text="看不清，换一张", command=self._refresh_code).pack(pady=(5, 8))
        ttk.Entry(card, textvariable=self.input_code, justify="center",
                  font=("Consolas", 14)).pack(ipady=5, padx=60, fill="x")
        tk.Label(card, textvariable=self.status, bg="white", fg="#F53F3F",
                 font=("Microsoft YaHei UI", 9)).pack(pady=(5, 4))
        ttk.Button(card, text="验证并切换", command=self._submit).pack(pady=(0, 12))

    def _refresh_code(self) -> None:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        self.code = "".join(secrets.choice(alphabet) for _ in range(5))
        self.input_code.set("")
        self.canvas.delete("all")
        for _ in range(8):
            x1, y1 = secrets.randbelow(210), secrets.randbelow(64)
            x2, y2 = secrets.randbelow(210), secrets.randbelow(64)
            self.canvas.create_line(x1, y1, x2, y2, fill="#94BFFF", width=1)
        for index, char in enumerate(self.code):
            self.canvas.create_text(38 + index * 34, 32 + secrets.randbelow(9) - 4,
                                    text=char, fill="#165DFF", font=("Consolas", 22, "bold"))

    def _submit(self) -> None:
        if self.input_code.get().strip().upper() != self.code:
            self.status.set("验证码不正确，请重新输入")
            self._refresh_code()
            return
        self.result = True
        self.window.destroy()

    def show(self) -> bool:
        self.window.transient(self.parent)
        self.window.grab_set()
        self.parent.wait_window(self.window)
        return self.result
