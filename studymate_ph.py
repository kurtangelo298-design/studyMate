"""
StudyMate PH - Plan. Study. Achieve.
Fully functional desktop study app (Python + CustomTkinter)
Flow: Loading Screen -> Login -> Full Dashboard (all features with default data)
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import datetime
import json
import os
import csv
import random
import math
from PIL import Image, ImageDraw, ImageTk

# ============================================================
# APP PATHS & DATA
# ============================================================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(APP_DIR, "studymate_data.json")

# Color palette - dark theme matching the design
C_BG = "#0F0F1A"
C_SIDEBAR = "#13131F"
C_CARD = "#1E1E30"
C_CARD_HOVER = "#262640"
C_ACCENT = "#7C3AED"
C_ACCENT2 = "#3B82F6"
C_ACCENT_GRAD = "#6366F1"
C_TEXT = "#FFFFFF"
C_TEXT_DIM = "#9CA3AF"
C_SUCCESS = "#10B981"
C_WARNING = "#F59E0B"
C_DANGER = "#EF4444"
C_PURPLE = "#A78BFA"
C_BLUE = "#60A5FA"
C_TEAL = "#2DD4BF"
C_PINK = "#F472B6"
C_YELLOW = "#FBBF24"

DEFAULT_DATA = {
    "user": {"name": "Kath", "course": "BSIT Student", "username": "kath", "password": "1234"},
    "schedule": [
        {"time": "7:00 - 8:30 AM", "subject": "Mathematics", "room": "Room 201", "color": C_PURPLE},
        {"time": "9:00 - 10:30 AM", "subject": "Programming", "room": "Room 305", "color": C_BLUE},
        {"time": "1:00 - 2:30 PM", "subject": "Networking", "room": "Room 102", "color": C_TEAL},
    ],
    "deadlines": [
        {"title": "Programming Assignment", "due": "Apr 30, 2025", "days_left": 2, "color": C_PINK},
        {"title": "Group Project (Final Report)", "due": "May 2, 2025", "days_left": 4, "color": C_PURPLE},
        {"title": "Math Quiz", "due": "May 5, 2025", "days_left": 7, "color": C_YELLOW},
    ],
    "tasks": [
        {"id": 1, "title": "Programming Assignment", "due": "Apr 30, 2025", "category": "Schoolwork", "done": False, "overdue": False},
        {"id": 2, "title": "Group Project (Final Report)", "due": "May 2, 2025", "category": "Project", "done": False, "overdue": False},
        {"id": 3, "title": "Math Quiz Review", "due": "May 5, 2025", "category": "Review", "done": False, "overdue": False},
        {"id": 4, "title": "Networking Lab Report", "due": "Apr 25, 2025", "category": "Schoolwork", "done": True, "overdue": False},
        {"id": 5, "title": "Essay in English", "due": "Apr 20, 2025", "category": "Schoolwork", "done": True, "overdue": False},
        {"id": 6, "title": "PE Activity Output", "due": "Apr 15, 2025", "category": "Requirement", "done": True, "overdue": False},
        {"id": 7, "title": "Research Paper Draft", "due": "Apr 10, 2025", "category": "Project", "done": True, "overdue": True},
        {"id": 8, "title": "Science Experiment Log", "due": "Apr 8, 2025", "category": "Requirement", "done": False, "overdue": True},
    ],
    "grades": [
        {"subject": "Mathematics", "units": 3, "grade": 1.75},
        {"subject": "Programming", "units": 3, "grade": 1.50},
        {"subject": "Networking", "units": 3, "grade": 2.00},
        {"subject": "English", "units": 3, "grade": 1.25},
        {"subject": "Physical Education", "units": 2, "grade": 1.00},
        {"subject": "Science", "units": 3, "grade": 2.25},
    ],
    "budget": {"balance": 1250.00, "income": 5000.00, "expenses": 3750.00,
               "transactions": [
                   {"type": "Income", "desc": "Allowance", "amount": 5000.00, "date": "Apr 1, 2025"},
                   {"type": "Expense", "desc": "School Supplies", "amount": 450.00, "date": "Apr 5, 2025"},
                   {"type": "Expense", "desc": "Food", "amount": 1800.00, "date": "Apr 10, 2025"},
                   {"type": "Expense", "desc": "Transportation", "amount": 800.00, "date": "Apr 15, 2025"},
                   {"type": "Expense", "desc": "Project Materials", "amount": 700.00, "date": "Apr 20, 2025"},
               ]},
    "notes": [
        {"title": "Programming Notes", "content": "OOP concepts: Encapsulation, Inheritance, Polymorphism, Abstraction.\n\n- Class = blueprint\n- Object = instance of class\n- Use __init__ as constructor in Python"},
        {"title": "Math Formulas", "content": "Quadratic: x = (-b ± sqrt(b²-4ac)) / 2a\nSlope: m = (y2-y1)/(x2-x1)\nArea of circle: A = πr²"},
    ],
    "projects": [
        {"name": "Capstone Project", "members": "Kath, John, Mae", "progress": 65, "deadline": "May 15, 2025"},
        {"name": "Research Paper", "members": "Kath, Luis", "progress": 40, "deadline": "May 30, 2025"},
        {"name": "System Integration", "members": "Kath, John, Mae, Luis", "progress": 80, "deadline": "May 10, 2025"},
    ],
    "exams": [
        {"subject": "Mathematics", "date": "2025-05-10"},
        {"subject": "Programming", "date": "2025-05-12"},
        {"subject": "Networking", "date": "2025-05-15"},
    ],
    "calendar_events": {
        "2025-04-29": ["Mathematics 7AM", "Programming 9AM", "Networking 1PM"],
        "2025-04-30": ["Programming Assignment Due"],
        "2025-05-02": ["Group Project Final Report Due"],
        "2025-05-05": ["Math Quiz"],
    },
}


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_DATA))


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ============================================================
# GRADUATION CAP LOGO (drawn with PIL)
# ============================================================
def make_grad_cap_image(size=120):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size
    # Cap top (diamond/trapezoid)
    cap_top = [(int(s*0.15), int(s*0.42)), (int(s*0.5), int(s*0.22)), (int(s*0.85), int(s*0.42)), (int(s*0.5), int(s*0.62))]
    draw.polygon(cap_top, fill=(30, 30, 40, 255))
    # Cap base (rectangle below)
    draw.rectangle([int(s*0.32), int(s*0.55), int(s*0.68), int(s*0.78)], fill=(30, 30, 40, 255))
    draw.rectangle([int(s*0.28), int(s*0.74), int(s*0.72), int(s*0.80)], fill=(50, 50, 65, 255))
    # Tassel button on top
    draw.ellipse([int(s*0.45), int(s*0.36), int(s*0.55), int(s*0.46)], fill=(245, 158, 11, 255))
    # Tassel string + head
    draw.line([(int(s*0.5), int(s*0.41)), (int(s*0.78), int(s*0.50))], fill=(245, 158, 11, 255), width=3)
    draw.ellipse([int(s*0.75), int(s*0.48), int(s*0.84), int(s*0.60)], fill=(245, 158, 11, 255))
    return img


# ============================================================
# LOADING SCREEN
# ============================================================
class LoadingScreen(ctk.CTkFrame):
    def __init__(self, master, on_complete):
        super().__init__(master, fg_color=C_BG)
        self.on_complete = on_complete
        self.pack(fill="both", expand=True)

        # Center container
        container = ctk.CTkFrame(self, fg_color="transparent", width=400, height=400)
        container.place(relx=0.5, rely=0.5, anchor="center")

        # Canvas for animated ring + cap
        self.canvas = tk.Canvas(container, width=300, height=300, bg=C_BG, highlightthickness=0)
        self.canvas.pack(pady=20)

        # Grad cap image in center (fallback to emoji)
        self.cap_tk = None
        try:
            cap_img = make_grad_cap_image(110)
            self.cap_tk = ImageTk.PhotoImage(cap_img)
            self.canvas.create_image(150, 150, image=self.cap_tk)
        except Exception:
            self.canvas.create_text(150, 150, text="🎓", font=("Arial", 60))

        # Loading text
        self.label = ctk.CTkLabel(self, text="StudyMate PH", font=ctk.CTkFont(size=24, weight="bold"), text_color=C_TEXT)
        self.label.place(relx=0.5, rely=0.72, anchor="center")
        self.sub = ctk.CTkLabel(self, text="Plan · Study · Achieve", font=ctk.CTkFont(size=13), text_color=C_TEXT_DIM)
        self.sub.place(relx=0.5, rely=0.77, anchor="center")
        self.status = ctk.CTkLabel(self, text="Loading...", font=ctk.CTkFont(size=11), text_color=C_ACCENT2)
        self.status.place(relx=0.5, rely=0.85, anchor="center")

        self.angle = 0
        self.progress = 0
        self.animate()

    def draw_ring(self):
        self.canvas.delete("ring")
        cx, cy, r = 150, 150, 115
        # Three colored segments: green, blue, orange (like the design)
        colors = [C_SUCCESS, C_ACCENT2, C_PINK]
        seg_len = 90  # degrees each
        gap = 15
        start = self.angle
        for i, col in enumerate(colors):
            s = start + i * (seg_len + gap)
            self.canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=s, extent=seg_len,
                                   style="arc", outline=col, width=8, tags="ring")
        # Faint full circle background
        self.canvas.create_arc(cx-r, cy-r, cx+r, cy+r, start=0, extent=359,
                               style="arc", outline="#2A2A40", width=8, tags="ring_bg")
        self.canvas.tag_lower("ring_bg")

    def animate(self):
        self.angle = (self.angle + 6) % 360
        self.progress += 1
        self.draw_ring()
        msgs = ["Loading...", "Preparing your workspace...", "Almost there...", "Welcome!"]
        idx = min(self.progress // 25, len(msgs)-1)
        self.status.configure(text=msgs[idx])
        if self.progress < 100:
            self.after(30, self.animate)
        else:
            self.after(300, self.on_complete)


# ============================================================
# LOGIN SCREEN
# ============================================================
class LoginScreen(ctk.CTkFrame):
    def __init__(self, master, data, on_login):
        super().__init__(master, fg_color=C_BG)
        self.data = data
        self.on_login = on_login
        self.pack(fill="both", expand=True)
        self.show_pw = False

        # Card
        card = ctk.CTkFrame(self, fg_color=C_CARD, corner_radius=20, width=380, height=480)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        # Logo
        self.cap_tk = None
        try:
            cap_img = make_grad_cap_image(80)
            self.cap_tk = ctk.CTkImage(light_image=cap_img, dark_image=cap_img, size=(80, 80))
            ctk.CTkLabel(card, image=self.cap_tk, text="").pack(pady=(30, 8))
        except Exception:
            ctk.CTkLabel(card, text="🎓", font=ctk.CTkFont(size=54)).pack(pady=(30, 8))
        ctk.CTkLabel(card, text="StudyMate PH", font=ctk.CTkFont(size=22, weight="bold"), text_color=C_TEXT).pack()
        ctk.CTkLabel(card, text="Plan · Study · Achieve", font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM).pack(pady=(0, 20))

        # Form
        form = ctk.CTkFrame(card, fg_color="transparent")
        form.pack(fill="x", padx=30)

        ctk.CTkLabel(form, text="Username", font=ctk.CTkFont(size=12, weight="bold"), text_color=C_TEXT_DIM, anchor="w").pack(fill="x", pady=(0, 4))
        self.user_entry = ctk.CTkEntry(form, placeholder_text="Enter username", height=40, corner_radius=10, fg_color=C_BG, border_color=C_ACCENT)
        self.user_entry.insert(0, self.data["user"]["username"])
        self.user_entry.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(form, text="Password", font=ctk.CTkFont(size=12, weight="bold"), text_color=C_TEXT_DIM, anchor="w").pack(fill="x", pady=(0, 4))
        pw_frame = ctk.CTkFrame(form, fg_color="transparent")
        pw_frame.pack(fill="x", pady=(0, 16))
        self.pw_entry = ctk.CTkEntry(pw_frame, placeholder_text="Enter password", height=40, corner_radius=10, fg_color=C_BG, border_color=C_ACCENT, show="•")
        self.pw_entry.insert(0, self.data["user"]["password"])
        self.pw_entry.pack(side="left", fill="x", expand=True)
        self.eye_btn = ctk.CTkButton(pw_frame, text="👁", width=40, height=40, fg_color=C_BG, hover_color=C_CARD_HOVER, command=self.toggle_pw)
        self.eye_btn.pack(side="left", padx=(6, 0))

        self.login_btn = ctk.CTkButton(form, text="Log In", height=42, corner_radius=10,
                                       fg_color=C_ACCENT, hover_color="#6D28D9",
                                       font=ctk.CTkFont(size=14, weight="bold"), command=self.do_login)
        self.login_btn.pack(fill="x", pady=(4, 8))

        self.hint = ctk.CTkLabel(form, text=f"Default: {self.data['user']['username']} / {self.data['user']['password']}",
                                 font=ctk.CTkFont(size=10), text_color=C_TEXT_DIM)
        self.hint.pack()

        self.error_lbl = ctk.CTkLabel(form, text="", font=ctk.CTkFont(size=11), text_color=C_DANGER)
        self.error_lbl.pack(pady=(6, 0))

    def toggle_pw(self):
        self.show_pw = not self.show_pw
        self.pw_entry.configure(show="" if self.show_pw else "•")

    def do_login(self):
        u = self.user_entry.get().strip()
        p = self.pw_entry.get().strip()
        if u == self.data["user"]["username"] and p == self.data["user"]["password"]:
            self.on_login()
        else:
            self.error_lbl.configure(text="❌ Invalid username or password!")


# ============================================================
# MAIN APP
# ============================================================
class StudyMateApp(ctk.CTkFrame):
    def __init__(self, master, data):
        super().__init__(master, fg_color=C_BG)
        self.data = data
        self.pack(fill="both", expand=True)

        # Grad cap icon for window (skip if PIL/tk incompatible)
        try:
            cap = make_grad_cap_image(64)
            self._icon_ref = ImageTk.PhotoImage(cap)
            self.master.iconphoto(False, self._icon_ref)
        except Exception:
            pass

        # Main layout: sidebar + content
        self.main = ctk.CTkFrame(self, fg_color=C_BG)
        self.main.pack(fill="both", expand=True)

        self.sidebar = ctk.CTkFrame(self.main, fg_color=C_SIDEBAR, width=260, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.content = ctk.CTkFrame(self.main, fg_color=C_BG)
        self.content.pack(side="left", fill="both", expand=True)

        self.current_page = None
        self.nav_buttons = {}
        self.build_sidebar()
        self.show_page("Home")

    # ---------------- SIDEBAR ----------------
    def build_sidebar(self):
        # Logo
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=16, pady=(20, 10))
        self.logo_img = None
        try:
            cap_img = make_grad_cap_image(44)
            self.logo_img = ctk.CTkImage(light_image=cap_img, dark_image=cap_img, size=(44, 44))
            ctk.CTkLabel(logo_frame, image=self.logo_img, text="").pack(side="left")
        except Exception:
            ctk.CTkLabel(logo_frame, text="🎓", font=ctk.CTkFont(size=30), width=44, height=44).pack(side="left")
        txt = ctk.CTkFrame(logo_frame, fg_color="transparent")
        txt.pack(side="left", padx=(10, 0), fill="x", expand=True)
        ctk.CTkLabel(txt, text="StudyMate PH", font=ctk.CTkFont(size=17, weight="bold"), text_color=C_TEXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(txt, text="Plan · Study · Achieve", font=ctk.CTkFont(size=10), text_color=C_TEXT_DIM, anchor="w").pack(fill="x")

        # Profile card
        prof = ctk.CTkFrame(self.sidebar, fg_color=C_CARD, corner_radius=12)
        prof.pack(fill="x", padx=14, pady=(8, 14))
        inner = ctk.CTkFrame(prof, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=10)
        avatar = ctk.CTkLabel(inner, text="👩‍🎓", font=ctk.CTkFont(size=26), width=40, height=40, fg_color=C_ACCENT, corner_radius=20)
        avatar.pack(side="left")
        pt = ctk.CTkFrame(inner, fg_color="transparent")
        pt.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.name_lbl = ctk.CTkLabel(pt, text=self.data["user"]["name"], font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w")
        self.name_lbl.pack(fill="x")
        self.course_lbl = ctk.CTkLabel(pt, text=self.data["user"]["course"], font=ctk.CTkFont(size=10), text_color=C_TEXT_DIM, anchor="w")
        self.course_lbl.pack(fill="x")

        # Nav scrollable
        self.nav_scroll = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent", scrollbar_button_color=C_ACCENT)
        self.nav_scroll.pack(fill="both", expand=True, padx=8)

        main_menu = [
            ("🏠", "Home"), ("✅", "My Tasks"), ("📅", "Calendar"), ("📚", "Study Space"),
            ("👥", "Group Projects"), ("📝", "Notes & Files"), ("🎓", "Grades"),
            ("🎯", "Study Planner"), ("💰", "Budget Tracker"), ("⚙️", "Settings"),
        ]
        for icon, name in main_menu:
            self.add_nav_button(icon, name)

        # More Features section
        ctk.CTkLabel(self.nav_scroll, text="✨ More Features", font=ctk.CTkFont(size=11, weight="bold"), text_color=C_TEXT_DIM, anchor="w").pack(fill="x", padx=12, pady=(14, 4))
        more = [
            ("🔔", "Deadline Reminder"), ("♻️", "Missed Task Recovery"), ("📤", "Export Reports"),
            ("⏱️", "Time Estimator"), ("🤖", "AI Study Assistant"), ("📆", "Exam Countdown"),
            ("🌙", "Focus Mode"), ("💸", "Student Budget Tracker"),
        ]
        for icon, name in more:
            self.add_nav_button(icon, name, small=True)

        # Motivational quote
        quote = ctk.CTkFrame(self.sidebar, fg_color=C_CARD, corner_radius=12)
        quote.pack(fill="x", padx=14, pady=(8, 6))
        ctk.CTkLabel(quote, text="🌱 Small steps every day\nlead to big results.",
                     font=ctk.CTkFont(size=10), text_color=C_TEXT_DIM, justify="left").pack(padx=12, pady=10, anchor="w")

        # Logout
        ctk.CTkButton(self.sidebar, text="↪ Log Out", fg_color="transparent", hover_color="#3B1414",
                      text_color=C_DANGER, font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
                      command=self.logout).pack(fill="x", padx=14, pady=(4, 14))

    def add_nav_button(self, icon, name, small=False):
        btn = ctk.CTkButton(self.nav_scroll, text=f"  {icon}  {name}", anchor="w",
                            fg_color="transparent", hover_color=C_CARD_HOVER,
                            text_color=C_TEXT, font=ctk.CTkFont(size=12 if not small else 11),
                            height=34 if not small else 30, corner_radius=10,
                            command=lambda n=name: self.show_page(n))
        btn.pack(fill="x", pady=1, padx=4)
        self.nav_buttons[name] = btn

    def highlight_nav(self, name):
        for n, btn in self.nav_buttons.items():
            if n == name:
                btn.configure(fg_color=C_ACCENT, text_color=C_TEXT)
            else:
                btn.configure(fg_color="transparent", text_color=C_TEXT)

    def logout(self):
        if messagebox.askyesno("Log Out", "Are you sure you want to log out?"):
            save_data(self.data)
            self.master.destroy()

    # ---------------- PAGE ROUTER ----------------
    def show_page(self, name):
        if self.current_page:
            self.current_page.destroy()
        self.highlight_nav(name)
        page_map = {
            "Home": HomePage, "My Tasks": TasksPage, "Calendar": CalendarPage,
            "Study Space": StudySpacePage, "Group Projects": GroupProjectsPage,
            "Notes & Files": NotesPage, "Grades": GradesPage, "Study Planner": StudyPlannerPage,
            "Budget Tracker": BudgetPage, "Settings": SettingsPage,
            "Deadline Reminder": DeadlineReminderPage, "Missed Task Recovery": MissedTaskPage,
            "Export Reports": ExportReportsPage, "Time Estimator": TimeEstimatorPage,
            "AI Study Assistant": AIAssistantPage, "Exam Countdown": ExamCountdownPage,
            "Focus Mode": FocusModePage, "Student Budget Tracker": BudgetPage,
        }
        cls = page_map.get(name, HomePage)
        self.current_page = cls(self.content, self.data, self.show_page, self)
        self.current_page.pack(fill="both", expand=True, padx=16, pady=14)


# ============================================================
# BASE PAGE
# ============================================================
class BasePage(ctk.CTkScrollableFrame):
    def __init__(self, master, data, navigate, app=None):
        super().__init__(master, fg_color=C_BG, scrollbar_button_color=C_ACCENT)
        self.data = data
        self.navigate = navigate
        self.app = app

    def header(self, title, subtitle=""):
        h = ctk.CTkFrame(self, fg_color="transparent")
        h.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(h, text=title, font=ctk.CTkFont(size=22, weight="bold"), text_color=C_TEXT, anchor="w").pack(side="left")
        if subtitle:
            ctk.CTkLabel(h, text=subtitle, font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w").pack(side="left", padx=(12, 0))
        return h

    def card(self, parent=None, **kw):
        p = parent or self
        return ctk.CTkFrame(p, fg_color=C_CARD, corner_radius=14, **kw)


# ============================================================
# HOME PAGE
# ============================================================
class HomePage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        user = data["user"]

        # Top bar: greeting + bell + avatar
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 10))
        greet = ctk.CTkFrame(top, fg_color="transparent")
        greet.pack(side="left", fill="x", expand=True)
        hour = datetime.datetime.now().hour
        gr = "Good Morning" if hour < 12 else ("Good Afternoon" if hour < 18 else "Good Evening")
        ctk.CTkLabel(greet, text=f"{gr},\n{user['name']} ☀️", font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=C_TEXT, justify="left", anchor="w").pack(anchor="w")
        ctk.CTkLabel(greet, text="Keep going! Your future self will thank you.",
                     font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w", pady=(4, 0))
        ctk.CTkButton(top, text="🔔", width=44, height=44, fg_color=C_CARD, hover_color=C_CARD_HOVER, corner_radius=22,
                      command=lambda: self.navigate("Deadline Reminder")).pack(side="right", padx=(6, 0))
        ctk.CTkLabel(top, text="👩‍🎓", font=ctk.CTkFont(size=22), width=44, height=44, fg_color=C_ACCENT, corner_radius=22).pack(side="right")

        # Hero illustration card
        hero = self.card()
        hero.pack(fill="x", pady=(0, 14))
        hb = ctk.CTkFrame(hero, fg_color="transparent")
        hb.pack(fill="x", padx=18, pady=14)
        ctk.CTkLabel(hb, text="💻📚🎓", font=ctk.CTkFont(size=46)).pack(side="right", padx=(10, 0))
        ctk.CTkLabel(hb, text="Ready to ace this semester? 🚀", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=C_TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(hb, text=f"{len([t for t in data['tasks'] if not t['done']])} tasks pending · {len(data['deadlines'])} deadlines coming up",
                     font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w", pady=(4, 0))

        # Two columns: schedule + (deadlines & stats)
        cols = ctk.CTkFrame(self, fg_color="transparent")
        cols.pack(fill="x")
        left_col = ctk.CTkFrame(cols, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right_col = ctk.CTkFrame(cols, fg_color="transparent")
        right_col.pack(side="left", fill="both", expand=True, padx=(8, 0))

        # Today's Schedule
        sch = self.card(left_col)
        sch.pack(fill="x")
        sh = ctk.CTkFrame(sch, fg_color="transparent")
        sh.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(sh, text="📅 Today's Schedule", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(side="left")
        ctk.CTkButton(sh, text="View Calendar →", fg_color="transparent", hover_color=C_CARD_HOVER, text_color=C_ACCENT2,
                      font=ctk.CTkFont(size=11), command=lambda: self.navigate("Calendar")).pack(side="right")
        ctk.CTkLabel(sch, text="Tue, Apr 29, 2025", font=ctk.CTkFont(size=11), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w", padx=16)
        for s in data["schedule"]:
            row = ctk.CTkFrame(sch, fg_color=C_BG, corner_radius=10)
            row.pack(fill="x", padx=16, pady=5)
            ri = ctk.CTkFrame(row, fg_color="transparent")
            ri.pack(fill="x", padx=12, pady=10)
            dot = ctk.CTkLabel(ri, text="●", text_color=s["color"], font=ctk.CTkFont(size=14)).pack(side="left")
            info = ctk.CTkFrame(ri, fg_color="transparent")
            info.pack(side="left", padx=(10, 0), fill="x", expand=True)
            ctk.CTkLabel(info, text=s["time"], font=ctk.CTkFont(size=10), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=s["subject"], font=ctk.CTkFont(size=13, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w")
            ctk.CTkLabel(ri, text=f"📍 {s['room']}", font=ctk.CTkFont(size=10), text_color=C_TEXT_DIM).pack(side="right")

        # Upcoming Deadlines
        dl = self.card(right_col)
        dl.pack(fill="x", pady=(0, 8))
        dh = ctk.CTkFrame(dl, fg_color="transparent")
        dh.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(dh, text="⏰ Upcoming Deadlines", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(side="left")
        ctk.CTkButton(dh, text="View All →", fg_color="transparent", hover_color=C_CARD_HOVER, text_color=C_ACCENT2,
                      font=ctk.CTkFont(size=11), command=lambda: self.navigate("My Tasks")).pack(side="right")
        for d in data["deadlines"]:
            row = ctk.CTkFrame(dl, fg_color=C_BG, corner_radius=10)
            row.pack(fill="x", padx=16, pady=4)
            ri = ctk.CTkFrame(row, fg_color="transparent")
            ri.pack(fill="x", padx=12, pady=9)
            ctk.CTkLabel(ri, text="📄", font=ctk.CTkFont(size=18), fg_color=d["color"], corner_radius=8, width=34, height=34).pack(side="left")
            info = ctk.CTkFrame(ri, fg_color="transparent")
            info.pack(side="left", padx=(10, 0), fill="x", expand=True)
            ctk.CTkLabel(info, text=d["title"], font=ctk.CTkFont(size=12, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=f"Due {d['due']}", font=ctk.CTkFont(size=10), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w")
            ctk.CTkLabel(ri, text=f"{d['days_left']} days left", font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_WARNING, fg_color="#3B2F10", corner_radius=8).pack(side="right", padx=(6, 0))

        # Quick Stats with donut
        st = self.card(right_col)
        st.pack(fill="x")
        ctk.CTkLabel(st, text="📊 Quick Stats", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 4))
        stats_row = ctk.CTkFrame(st, fg_color="transparent")
        stats_row.pack(fill="x", padx=16, pady=(0, 12))
        total = len(data["tasks"])
        done = len([t for t in data["tasks"] if t["done"]])
        pending = len([t for t in data["tasks"] if not t["done"] and not t["overdue"]])
        overdue = len([t for t in data["tasks"] if t["overdue"] and not t["done"]])
        pct = int(done / total * 100) if total else 0
        # Donut canvas
        self.donut = tk.Canvas(stats_row, width=110, height=110, bg=C_CARD, highlightthickness=0)
        self.donut.pack(side="left", padx=(0, 14))
        self.draw_donut(pct)
        legend = ctk.CTkFrame(stats_row, fg_color="transparent")
        legend.pack(side="left", fill="both", expand=True)
        for label, val, col in [("Completed", done, C_SUCCESS), ("Pending", pending, C_WARNING), ("Overdue", overdue, C_DANGER)]:
            lr = ctk.CTkFrame(legend, fg_color="transparent")
            lr.pack(fill="x", pady=2)
            ctk.CTkLabel(lr, text="●", text_color=col, font=ctk.CTkFont(size=12)).pack(side="left")
            ctk.CTkLabel(lr, text=label, font=ctk.CTkFont(size=11), text_color=C_TEXT_DIM).pack(side="left", padx=(4, 0))
            ctk.CTkLabel(lr, text=str(val), font=ctk.CTkFont(size=12, weight="bold"), text_color=C_TEXT).pack(side="right")

        # Quick Actions grid
        ctk.CTkLabel(self, text="⚡ Quick Actions", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", pady=(16, 8))
        actions = [
            ("➕", "Add Task", C_ACCENT, "My Tasks"), ("📅", "View Schedule", C_ACCENT2, "Calendar"),
            ("🎯", "Study Planner", C_PURPLE, "Study Planner"), ("⏱️", "Focus Mode", C_TEAL, "Focus Mode"),
            ("🤖", "AI Assistant", C_PINK, "AI Study Assistant"), ("🔔", "Deadline Reminder", C_WARNING, "Deadline Reminder"),
            ("♻️", "Missed Task Recovery", C_SUCCESS, "Missed Task Recovery"), ("📤", "Export Reports", C_BLUE, "Export Reports"),
        ]
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x")
        for i, (icon, label, col, target) in enumerate(actions):
            if i % 4 == 0:
                row_f = ctk.CTkFrame(grid, fg_color="transparent")
                row_f.pack(fill="x", pady=4)
            b = ctk.CTkButton(row_f, text=f"{icon}\n{label}", fg_color=C_CARD, hover_color=col,
                              font=ctk.CTkFont(size=11, weight="bold"), text_color=C_TEXT,
                              height=70, corner_radius=14, command=lambda t=target: self.navigate(t))
            b.pack(side="left", fill="x", expand=True, padx=4)

        # Motivational banner
        banner = ctk.CTkFrame(self, fg_color="#1E1B4B", corner_radius=14)
        banner.pack(fill="x", pady=(16, 10))
        bb = ctk.CTkFrame(banner, fg_color="transparent")
        bb.pack(fill="x", padx=18, pady=14)
        ctk.CTkLabel(bb, text="🏔️🌙", font=ctk.CTkFont(size=30)).pack(side="right")
        ctk.CTkLabel(bb, text="Progress, not perfection.", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=C_TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(bb, text="You're doing great! 💪", font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w")

        # Bottom nav bar
        self.bottom_nav()

    def draw_donut(self, pct):
        self.donut.delete("all")
        cx, cy, r = 55, 55, 42
        self.donut.create_arc(cx-r, cy-r, cx+r, cy+r, start=90, extent=359, style="arc", outline="#2A2A40", width=12)
        extent = int(360 * pct / 100)
        if extent > 0:
            self.donut.create_arc(cx-r, cy-r, cx+r, cy+r, start=90, extent=-extent, style="arc", outline=C_SUCCESS, width=12)
        self.donut.create_text(cx, cy-6, text=f"{pct}%", fill=C_TEXT, font=("Arial", 16, "bold"))
        self.donut.create_text(cx, cy+14, text="Tasks Completed", fill=C_TEXT_DIM, font=("Arial", 7))

    def bottom_nav(self):
        nav = ctk.CTkFrame(self, fg_color=C_CARD, corner_radius=16, height=56)
        nav.pack(fill="x", pady=(6, 4))
        nav.pack_propagate(False)
        items = [("🏠", "Home"), ("✅", "Tasks"), ("📅", "Calendar"), ("👤", "Profile")]
        for icon, name in items:
            target = "Settings" if name == "Profile" else ("My Tasks" if name == "Tasks" else name)
            ctk.CTkButton(nav, text=f"{icon} {name}", fg_color="transparent", hover_color=C_CARD_HOVER,
                          text_color=C_TEXT_DIM, font=ctk.CTkFont(size=12, weight="bold"),
                          command=lambda t=target: self.navigate(t)).pack(side="left", fill="both", expand=True)
        ctk.CTkButton(nav, text="➕", width=48, height=48, fg_color=C_ACCENT, hover_color="#6D28D9",
                      corner_radius=24, font=ctk.CTkFont(size=20), command=lambda: self.navigate("My Tasks")).place(relx=0.5, rely=0.5, anchor="center")


# ============================================================
# MY TASKS PAGE
# ============================================================
class TasksPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.filter_var = ctk.StringVar(value="All")
        self.header("✅ My Tasks", "Manage all your school tasks")
        self.build_add_form()
        self.build_filters()
        self.build_task_list()

    def build_add_form(self):
        form = self.card()
        form.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(form, text="➕ Add New Task", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 8))
        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 12))
        self.title_e = ctk.CTkEntry(row, placeholder_text="Task title...", height=38, fg_color=C_BG, border_color=C_ACCENT)
        self.title_e.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.due_e = ctk.CTkEntry(row, placeholder_text="Due date (e.g. May 10, 2025)", width=200, height=38, fg_color=C_BG, border_color=C_ACCENT)
        self.due_e.pack(side="left", padx=6)
        self.cat_e = ctk.CTkComboBox(row, values=["Schoolwork", "Project", "Review", "Requirement"], height=38, fg_color=C_BG, button_color=C_ACCENT)
        self.cat_e.pack(side="left", padx=6)
        ctk.CTkButton(row, text="Add", width=80, height=38, fg_color=C_ACCENT, hover_color="#6D28D9", command=self.add_task).pack(side="left", padx=(6, 0))

    def build_filters(self):
        fr = ctk.CTkFrame(self, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 10))
        for f in ["All", "Pending", "Completed", "Overdue"]:
            ctk.CTkButton(fr, text=f, width=90, height=32, corner_radius=16,
                          fg_color=C_ACCENT if self.filter_var.get() == f else C_CARD,
                          hover_color=C_CARD_HOVER, text_color=C_TEXT, font=ctk.CTkFont(size=11, weight="bold"),
                          command=lambda x=f: self.set_filter(x)).pack(side="left", padx=3)

    def set_filter(self, f):
        self.filter_var.set(f)
        # rebuild list
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.build_task_list_items()

    def build_task_list(self):
        self.list_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.list_frame.pack(fill="x")
        self.build_task_list_items()

    def build_task_list_items(self):
        f = self.filter_var.get()
        tasks = self.data["tasks"]
        if f == "Pending":
            tasks = [t for t in tasks if not t["done"] and not t["overdue"]]
        elif f == "Completed":
            tasks = [t for t in tasks if t["done"]]
        elif f == "Overdue":
            tasks = [t for t in tasks if t["overdue"] and not t["done"]]

        if not tasks:
            ctk.CTkLabel(self.list_frame, text="🎉 No tasks here! Great job!", font=ctk.CTkFont(size=14), text_color=C_TEXT_DIM).pack(pady=30)
            return

        for t in tasks:
            row = self.card(self.list_frame)
            row.pack(fill="x", pady=4)
            ri = ctk.CTkFrame(row, fg_color="transparent")
            ri.pack(fill="x", padx=14, pady=10)
            status = "✅" if t["done"] else ("🔴" if t["overdue"] else "⭕")
            cb = ctk.CTkCheckBox(ri, text=status, width=24, fg_color=C_SUCCESS, hover_color=C_CARD_HOVER,
                                 command=lambda tid=t["id"]: self.toggle_task(tid))
            if t["done"]:
                cb.select()
            cb.pack(side="left")
            info = ctk.CTkFrame(ri, fg_color="transparent")
            info.pack(side="left", padx=(12, 0), fill="x", expand=True)
            style = "overstrike" if t["done"] else "normal"
            ctk.CTkLabel(info, text=t["title"], font=ctk.CTkFont(size=13, weight="bold", slant="roman"),
                         text_color=C_TEXT_DIM if t["done"] else C_TEXT, anchor="w").pack(anchor="w")
            tag_color = C_DANGER if t["overdue"] and not t["done"] else C_ACCENT2
            ctk.CTkLabel(info, text=f"📅 {t['due']} · 🏷️ {t['category']}", font=ctk.CTkFont(size=10),
                         text_color=tag_color, anchor="w").pack(anchor="w")
            ctk.CTkButton(ri, text="🗑", width=36, height=36, fg_color="transparent", hover_color="#3B1414",
                          text_color=C_DANGER, command=lambda tid=t["id"]: self.delete_task(tid)).pack(side="right")

    def add_task(self):
        title = self.title_e.get().strip()
        if not title:
            messagebox.showwarning("Warning", "Please enter a task title!")
            return
        new_id = max([t["id"] for t in self.data["tasks"]] + [0]) + 1
        self.data["tasks"].append({
            "id": new_id, "title": title,
            "due": self.due_e.get().strip() or "No date",
            "category": self.cat_e.get(), "done": False, "overdue": False,
        })
        save_data(self.data)
        self.title_e.delete(0, "end")
        self.due_e.delete(0, "end")
        self.set_filter(self.filter_var.get())

    def toggle_task(self, tid):
        for t in self.data["tasks"]:
            if t["id"] == tid:
                t["done"] = not t["done"]
                if t["done"]:
                    t["overdue"] = False
        save_data(self.data)
        self.set_filter(self.filter_var.get())

    def delete_task(self, tid):
        if messagebox.askyesno("Delete", "Delete this task?"):
            self.data["tasks"] = [t for t in self.data["tasks"] if t["id"] != tid]
            save_data(self.data)
            self.set_filter(self.filter_var.get())


# ============================================================
# CALENDAR PAGE
# ============================================================
class CalendarPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.today = datetime.date(2025, 4, 29)
        self.cur = self.today
        self.header("📅 Calendar", "View and manage your schedule")
        self.build_calendar()

    def build_calendar(self):
        card = self.card()
        card.pack(fill="x", pady=(0, 12))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(top, text="◀", width=40, height=36, fg_color=C_BG, hover_color=C_CARD_HOVER,
                      command=self.prev_month).pack(side="left")
        self.month_lbl = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=16, weight="bold"), text_color=C_TEXT)
        self.month_lbl.pack(side="left", expand=True)
        ctk.CTkButton(top, text="▶", width=40, height=36, fg_color=C_BG, hover_color=C_CARD_HOVER,
                      command=self.next_month).pack(side="left")
        self.grid_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.grid_frame.pack(fill="x", padx=16, pady=(0, 16))
        self.render_month()
        self.events_card = self.card()
        self.events_card.pack(fill="x")
        self.show_events(self.today)

    def render_month(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.month_lbl.configure(text=self.cur.strftime("%B %Y"))
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        hdr = ctk.CTkFrame(self.grid_frame, fg_color="transparent")
        hdr.pack(fill="x")
        for d in days:
            ctk.CTkLabel(hdr, text=d, font=ctk.CTkFont(size=11, weight="bold"), text_color=C_TEXT_DIM, width=40).pack(side="left", expand=True, fill="x")
        year, month = self.cur.year, self.cur.month
        first = datetime.date(year, month, 1)
        start_wd = first.weekday()
        import calendar as cal
        days_in_month = cal.monthrange(year, month)[1]
        day = 1
        for week in range(6):
            wr = ctk.CTkFrame(self.grid_frame, fg_color="transparent")
            wr.pack(fill="x", pady=2)
            for col in range(7):
                if week == 0 and col < start_wd:
                    ctk.CTkLabel(wr, text="", width=40, height=36).pack(side="left", expand=True, fill="x")
                elif day <= days_in_month:
                    ddate = datetime.date(year, month, day)
                    key = ddate.strftime("%Y-%m-%d")
                    has_event = key in self.data["calendar_events"]
                    is_today = ddate == self.today
                    fg = C_ACCENT if is_today else (C_CARD_HOVER if has_event else C_BG)
                    btn = ctk.CTkButton(wr, text=str(day), width=40, height=36, fg_color=fg, hover_color=C_ACCENT2,
                                        text_color=C_TEXT, font=ctk.CTkFont(size=12, weight="bold" if is_today else "normal"),
                                        corner_radius=10, command=lambda d=ddate: self.show_events(d))
                    btn.pack(side="left", expand=True, fill="x", padx=1)
                    day += 1
                else:
                    ctk.CTkLabel(wr, text="", width=40, height=36).pack(side="left", expand=True, fill="x")

    def prev_month(self):
        self.cur = (self.cur.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
        self.render_month()

    def next_month(self):
        self.cur = (self.cur.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        self.render_month()

    def show_events(self, date):
        for w in self.events_card.winfo_children():
            w.destroy()
        key = date.strftime("%Y-%m-%d")
        ctk.CTkLabel(self.events_card, text=f"📌 Events for {date.strftime('%B %d, %Y')}",
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 6))
        events = self.data["calendar_events"].get(key, [])
        if events:
            for e in events:
                ctk.CTkLabel(self.events_card, text=f"  • {e}", font=ctk.CTkFont(size=12),
                             text_color=C_TEXT_DIM, anchor="w").pack(anchor="w", padx=20, pady=2)
        else:
            ctk.CTkLabel(self.events_card, text="  No events for this day. Enjoy! 🌿", font=ctk.CTkFont(size=12),
                         text_color=C_TEXT_DIM, anchor="w").pack(anchor="w", padx=20, pady=(0, 12))
        # Add event
        add_f = ctk.CTkFrame(self.events_card, fg_color="transparent")
        add_f.pack(fill="x", padx=16, pady=(8, 12))
        self.ev_entry = ctk.CTkEntry(add_f, placeholder_text="Add event...", height=36, fg_color=C_BG, border_color=C_ACCENT)
        self.ev_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(add_f, text="Add", width=70, height=36, fg_color=C_ACCENT, hover_color="#6D28D9",
                      command=lambda: self.add_event(key)).pack(side="left")

    def add_event(self, key):
        ev = self.ev_entry.get().strip()
        if ev:
            self.data["calendar_events"].setdefault(key, []).append(ev)
            save_data(self.data)
            self.render_month()
            self.show_events(datetime.datetime.strptime(key, "%Y-%m-%d").date())


# ============================================================
# STUDY SPACE PAGE
# ============================================================
class StudySpacePage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("📚 Study Space", "Flashcards & study materials")
        self.flashcards = [
            ("OOP", "Object-Oriented Programming - uses objects and classes"),
            ("CPU", "Central Processing Unit - the brain of the computer"),
            ("LAN", "Local Area Network - connects computers in a small area"),
            ("Algorithm", "Step-by-step procedure to solve a problem"),
        ]
        self.fc_idx = 0
        self.fc_flipped = False
        card = self.card()
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text="🃏 Flashcards", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 8))
        self.fc_lbl = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=18, weight="bold"), text_color=C_TEXT,
                                   fg_color=C_BG, corner_radius=12, height=140, wraplength=500, justify="center")
        self.fc_lbl.pack(fill="x", padx=16, pady=(0, 12))
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(pady=(0, 16))
        ctk.CTkButton(btns, text="◀ Prev", width=100, height=38, fg_color=C_BG, hover_color=C_CARD_HOVER, command=self.prev_fc).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="🔄 Flip", width=100, height=38, fg_color=C_ACCENT, hover_color="#6D28D9", command=self.flip_fc).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Next ▶", width=100, height=38, fg_color=C_BG, hover_color=C_CARD_HOVER, command=self.next_fc).pack(side="left", padx=4)
        self.show_fc()

        tips = self.card()
        tips.pack(fill="x")
        ctk.CTkLabel(tips, text="💡 Study Tips", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 6))
        for t in ["Use Pomodoro: 25 min study, 5 min break", "Review notes within 24 hours of class", "Teach what you learn to someone else", "Sleep well before exams! 😴"]:
            ctk.CTkLabel(tips, text=f"  ✨ {t}", font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w", padx=20, pady=3)
        ctk.CTkLabel(tips, text="", height=8).pack()

    def show_fc(self):
        q, a = self.flashcards[self.fc_idx]
        self.fc_lbl.configure(text=f"Q: {q}" if not self.fc_flipped else f"A: {a}")

    def flip_fc(self):
        self.fc_flipped = not self.fc_flipped
        self.show_fc()

    def next_fc(self):
        self.fc_idx = (self.fc_idx + 1) % len(self.flashcards)
        self.fc_flipped = False
        self.show_fc()

    def prev_fc(self):
        self.fc_idx = (self.fc_idx - 1) % len(self.flashcards)
        self.fc_flipped = False
        self.show_fc()


# ============================================================
# GROUP PROJECTS PAGE
# ============================================================
class GroupProjectsPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("👥 Group Projects", "Track your collaborative work")
        for p in data["projects"]:
            card = self.card()
            card.pack(fill="x", pady=6)
            ri = ctk.CTkFrame(card, fg_color="transparent")
            ri.pack(fill="x", padx=16, pady=14)
            info = ctk.CTkFrame(ri, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(info, text=p["name"], font=ctk.CTkFont(size=15, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=f"👥 {p['members']}", font=ctk.CTkFont(size=11), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w", pady=(2, 0))
            ctk.CTkLabel(info, text=f"📅 Deadline: {p['deadline']}", font=ctk.CTkFont(size=11), text_color=C_WARNING, anchor="w").pack(anchor="w", pady=(2, 6))
            pb = ctk.CTkProgressBar(info, progress_color=C_ACCENT, fg_color=C_BG, height=10)
            pb.pack(fill="x")
            pb.set(p["progress"] / 100)
            ctk.CTkLabel(info, text=f"{p['progress']}% complete", font=ctk.CTkFont(size=10), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w", pady=(4, 0))
            ctk.CTkButton(ri, text="📂 Open", width=90, height=38, fg_color=C_ACCENT, hover_color="#6D28D9",
                          command=lambda n=p["name"]: messagebox.showinfo(n, f"Opening project: {n}\n\n(Default placeholder - files go here)")).pack(side="right", padx=(10, 0))


# ============================================================
# NOTES & FILES PAGE
# ============================================================
class NotesPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("📝 Notes & Files", "Your saved notes")
        self.selected = 0
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="both", expand=True)
        # Notes list
        self.list_card = self.card(row)
        self.list_card.pack(side="left", fill="y", padx=(0, 8))
        self.list_card.configure(width=200)
        self.list_card.pack_propagate(False)
        ctk.CTkLabel(self.list_card, text="📒 My Notes", font=ctk.CTkFont(size=13, weight="bold"), text_color=C_TEXT).pack(pady=(12, 6))
        self.notes_btns = []
        self.render_notes_list()
        ctk.CTkButton(self.list_card, text="➕ New Note", fg_color=C_ACCENT, hover_color="#6D28D9",
                      command=self.new_note).pack(fill="x", padx=12, pady=(8, 12))
        # Editor
        self.edit_card = self.card(row)
        self.edit_card.pack(side="left", fill="both", expand=True)
        self.title_entry = ctk.CTkEntry(self.edit_card, height=40, font=ctk.CTkFont(size=15, weight="bold"),
                                        fg_color=C_BG, border_color=C_ACCENT)
        self.title_entry.pack(fill="x", padx=14, pady=(14, 8))
        self.text_box = ctk.CTkTextbox(self.edit_card, fg_color=C_BG, font=ctk.CTkFont(size=13), corner_radius=10)
        self.text_box.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        btn_f = ctk.CTkFrame(self.edit_card, fg_color="transparent")
        btn_f.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkButton(btn_f, text="💾 Save", fg_color=C_SUCCESS, hover_color="#059669", command=self.save_note).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_f, text="🗑 Delete", fg_color=C_DANGER, hover_color="#B91C1C", command=self.delete_note).pack(side="left")
        self.load_note(0)

    def render_notes_list(self):
        for b in self.notes_btns:
            b.destroy()
        self.notes_btns = []
        for i, n in enumerate(self.data["notes"]):
            b = ctk.CTkButton(self.list_card, text=f"📄 {n['title'][:22]}", anchor="w",
                              fg_color=C_ACCENT if i == self.selected else C_BG, hover_color=C_CARD_HOVER,
                              text_color=C_TEXT, font=ctk.CTkFont(size=11), height=34, corner_radius=8,
                              command=lambda idx=i: self.load_note(idx))
            b.pack(fill="x", padx=10, pady=2)
            self.notes_btns.append(b)

    def load_note(self, idx):
        self.selected = idx
        n = self.data["notes"][idx]
        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, n["title"])
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", n["content"])
        self.render_notes_list()

    def save_note(self):
        n = self.data["notes"][self.selected]
        n["title"] = self.title_entry.get().strip() or "Untitled"
        n["content"] = self.text_box.get("1.0", "end").strip()
        save_data(self.data)
        self.render_notes_list()
        messagebox.showinfo("Saved", "Note saved successfully! ✅")

    def new_note(self):
        self.data["notes"].append({"title": "New Note", "content": ""})
        save_data(self.data)
        self.selected = len(self.data["notes"]) - 1
        self.render_notes_list()
        self.load_note(self.selected)

    def delete_note(self):
        if len(self.data["notes"]) <= 1:
            messagebox.showwarning("Warning", "Cannot delete the last note!")
            return
        if messagebox.askyesno("Delete", "Delete this note?"):
            del self.data["notes"][self.selected]
            save_data(self.data)
            self.selected = 0
            self.render_notes_list()
            self.load_note(0)


# ============================================================
# GRADES PAGE
# ============================================================
class GradesPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("🎓 Grades", "Your academic record & GPA")
        self.build_table()
        self.build_gpa()

    def build_table(self):
        card = self.card()
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text="📋 Grade Report", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 8))
        hdr = ctk.CTkFrame(card, fg_color=C_BG, corner_radius=8)
        hdr.pack(fill="x", padx=16, pady=(0, 4))
        for label, w in [("Subject", 0.4), ("Units", 0.2), ("Grade", 0.2), ("", 0.2)]:
            ctk.CTkLabel(hdr, text=label, font=ctk.CTkFont(size=12, weight="bold"), text_color=C_TEXT_DIM, anchor="w").pack(side="left", fill="x", expand=w, padx=10, pady=8)
        self.rows_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.rows_frame.pack(fill="x", padx=16, pady=(0, 12))
        self.render_rows()
        add = ctk.CTkFrame(card, fg_color="transparent")
        add.pack(fill="x", padx=16, pady=(0, 14))
        self.g_subj = ctk.CTkEntry(add, placeholder_text="Subject", height=36, fg_color=C_BG, border_color=C_ACCENT)
        self.g_subj.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.g_units = ctk.CTkEntry(add, placeholder_text="Units", width=70, height=36, fg_color=C_BG, border_color=C_ACCENT)
        self.g_units.pack(side="left", padx=4)
        self.g_grade = ctk.CTkEntry(add, placeholder_text="Grade", width=80, height=36, fg_color=C_BG, border_color=C_ACCENT)
        self.g_grade.pack(side="left", padx=4)
        ctk.CTkButton(add, text="➕ Add", width=80, height=36, fg_color=C_ACCENT, hover_color="#6D28D9", command=self.add_grade).pack(side="left", padx=(4, 0))

    def render_rows(self):
        for w in self.rows_frame.winfo_children():
            w.destroy()
        for i, g in enumerate(self.data["grades"]):
            row = ctk.CTkFrame(self.rows_frame, fg_color=C_BG, corner_radius=8)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=g["subject"], font=ctk.CTkFont(size=12), text_color=C_TEXT, anchor="w").pack(side="left", fill="x", expand=True, padx=10, pady=8)
            ctk.CTkLabel(row, text=str(g["units"]), font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w", width=5).pack(side="left", padx=10)
            color = C_SUCCESS if g["grade"] <= 2.0 else (C_WARNING if g["grade"] <= 3.0 else C_DANGER)
            ctk.CTkLabel(row, text=f"{g['grade']:.2f}", font=ctk.CTkFont(size=12, weight="bold"), text_color=color, anchor="w", width=6).pack(side="left", padx=10)
            ctk.CTkButton(row, text="🗑", width=30, height=28, fg_color="transparent", hover_color="#3B1414", text_color=C_DANGER,
                          command=lambda idx=i: self.del_grade(idx)).pack(side="right", padx=8)

    def add_grade(self):
        try:
            subj = self.g_subj.get().strip()
            units = int(self.g_units.get().strip())
            grade = float(self.g_grade.get().strip())
            if not subj:
                raise ValueError
            self.data["grades"].append({"subject": subj, "units": units, "grade": grade})
            save_data(self.data)
            self.render_rows()
            self.build_gpa()
            self.g_subj.delete(0, "end"); self.g_units.delete(0, "end"); self.g_grade.delete(0, "end")
        except Exception:
            messagebox.showwarning("Warning", "Invalid input! Check subject, units (number), and grade (number).")

    def del_grade(self, idx):
        if messagebox.askyesno("Delete", "Remove this grade?"):
            del self.data["grades"][idx]
            save_data(self.data)
            self.render_rows()
            self.build_gpa()

    def build_gpa(self):
        if hasattr(self, "gpa_card"):
            self.gpa_card.destroy()
        self.gpa_card = self.card()
        self.gpa_card.pack(fill="x")
        total_units = sum(g["units"] for g in self.data["grades"])
        weighted = sum(g["units"] * g["grade"] for g in self.data["grades"])
        gpa = weighted / total_units if total_units else 0
        rem = "Excellent! 🌟" if gpa <= 1.5 else ("Good! 👍" if gpa <= 2.0 else ("Keep pushing! 💪" if gpa <= 2.5 else "Study harder! 📚"))
        color = C_SUCCESS if gpa <= 2.0 else (C_WARNING if gpa <= 3.0 else C_DANGER)
        gf = ctk.CTkFrame(self.gpa_card, fg_color="transparent")
        gf.pack(fill="x", padx=16, pady=16)
        ctk.CTkLabel(gf, text="🏆 General Weighted Average (GWA)", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(gf, text=f"{gpa:.2f}", font=ctk.CTkFont(size=40, weight="bold"), text_color=color, anchor="w").pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(gf, text=f"{rem} · {total_units} units total", font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w")


# ============================================================
# STUDY PLANNER (POMODORO) PAGE
# ============================================================
class StudyPlannerPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("🎯 Study Planner", "Pomodoro timer for focused study")
        self.mode = "Focus"  # Focus / Break
        self.time_left = 25 * 60
        self.running = False
        self.timer_job = None
        card = self.card()
        card.pack(fill="x", pady=(0, 12))
        self.mode_lbl = ctk.CTkLabel(card, text="🍅 Focus Time (25 min)", font=ctk.CTkFont(size=16, weight="bold"), text_color=C_ACCENT2)
        self.mode_lbl.pack(pady=(20, 8))
        self.time_lbl = ctk.CTkLabel(card, text="25:00", font=ctk.CTkFont(size=60, weight="bold"), text_color=C_TEXT)
        self.time_lbl.pack(pady=(0, 16))
        self.progress = ctk.CTkProgressBar(card, progress_color=C_ACCENT, fg_color=C_BG, height=12)
        self.progress.pack(fill="x", padx=40, pady=(0, 20))
        self.progress.set(1.0)
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(pady=(0, 20))
        self.start_btn = ctk.CTkButton(btns, text="▶ Start", width=110, height=42, fg_color=C_SUCCESS, hover_color="#059669",
                                       font=ctk.CTkFont(size=13, weight="bold"), command=self.toggle_timer)
        self.start_btn.pack(side="left", padx=4)
        ctk.CTkButton(btns, text="⏹ Reset", width=110, height=42, fg_color=C_DANGER, hover_color="#B91C1C",
                      font=ctk.CTkFont(size=13, weight="bold"), command=self.reset_timer).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="☕ Switch to Break", width=140, height=42, fg_color=C_ACCENT, hover_color="#6D28D9",
                      font=ctk.CTkFont(size=13, weight="bold"), command=self.switch_mode).pack(side="left", padx=4)
        # Session stats
        stats = self.card()
        stats.pack(fill="x")
        ctk.CTkLabel(stats, text="📈 Today's Sessions", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 6))
        ctk.CTkLabel(stats, text="🍅 Focus sessions completed: 3\n☕ Breaks taken: 2\n⏱ Total focus time: 75 minutes",
                     font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w", justify="left").pack(anchor="w", padx=20, pady=(0, 14))

    def toggle_timer(self):
        if self.running:
            self.running = False
            self.start_btn.configure(text="▶ Resume", fg_color=C_SUCCESS)
            if self.timer_job:
                self.after_cancel(self.timer_job)
        else:
            self.running = True
            self.start_btn.configure(text="⏸ Pause", fg_color=C_WARNING)
            self.tick()

    def tick(self):
        if not self.running:
            return
        if self.time_left > 0:
            self.time_left -= 1
            self.update_display()
            self.timer_job = self.after(1000, self.tick)
        else:
            self.running = False
            self.start_btn.configure(text="▶ Start", fg_color=C_SUCCESS)
            messagebox.showinfo("Time's Up!", f"{'Great focus! Take a break. ☕' if self.mode == 'Focus' else 'Break over! Back to study! 📚'}")
            self.switch_mode()

    def update_display(self):
        m, s = divmod(self.time_left, 60)
        self.time_lbl.configure(text=f"{m:02d}:{s:02d}")
        total = 25 * 60 if self.mode == "Focus" else 5 * 60
        self.progress.set(self.time_left / total)

    def reset_timer(self):
        self.running = False
        if self.timer_job:
            self.after_cancel(self.timer_job)
        self.time_left = 25 * 60 if self.mode == "Focus" else 5 * 60
        self.start_btn.configure(text="▶ Start", fg_color=C_SUCCESS)
        self.update_display()

    def switch_mode(self):
        self.running = False
        if self.timer_job:
            self.after_cancel(self.timer_job)
        if self.mode == "Focus":
            self.mode = "Break"
            self.time_left = 5 * 60
            self.mode_lbl.configure(text="☕ Short Break (5 min)", text_color=C_SUCCESS)
        else:
            self.mode = "Focus"
            self.time_left = 25 * 60
            self.mode_lbl.configure(text="🍅 Focus Time (25 min)", text_color=C_ACCENT2)
        self.start_btn.configure(text="▶ Start", fg_color=C_SUCCESS)
        self.update_display()


# ============================================================
# BUDGET TRACKER PAGE
# ============================================================
class BudgetPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("💰 Budget Tracker", "Track your allowance & expenses")
        self.build_summary()
        self.build_add_form()
        self.build_transactions()

    def build_summary(self):
        b = self.data["budget"]
        card = self.card()
        card.pack(fill="x", pady=(0, 12))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=16)
        for label, val, col in [("💵 Balance", f"₱{b['balance']:.2f}", C_SUCCESS),
                                ("📥 Income", f"₱{b['income']:.2f}", C_ACCENT2),
                                ("📤 Expenses", f"₱{b['expenses']:.2f}", C_DANGER)]:
            box = ctk.CTkFrame(row, fg_color=C_BG, corner_radius=12)
            box.pack(side="left", fill="x", expand=True, padx=4)
            ctk.CTkLabel(box, text=label, font=ctk.CTkFont(size=11), text_color=C_TEXT_DIM).pack(pady=(10, 2))
            ctk.CTkLabel(box, text=val, font=ctk.CTkFont(size=18, weight="bold"), text_color=col).pack(pady=(0, 10))

    def build_add_form(self):
        card = self.card()
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text="➕ Add Transaction", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 8))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))
        self.t_type = ctk.CTkComboBox(row, values=["Income", "Expense"], height=38, fg_color=C_BG, button_color=C_ACCENT)
        self.t_type.set("Expense")
        self.t_type.pack(side="left", padx=(0, 6))
        self.t_desc = ctk.CTkEntry(row, placeholder_text="Description", height=38, fg_color=C_BG, border_color=C_ACCENT)
        self.t_desc.pack(side="left", fill="x", expand=True, padx=6)
        self.t_amt = ctk.CTkEntry(row, placeholder_text="Amount (₱)", width=140, height=38, fg_color=C_BG, border_color=C_ACCENT)
        self.t_amt.pack(side="left", padx=6)
        ctk.CTkButton(row, text="Add", width=80, height=38, fg_color=C_ACCENT, hover_color="#6D28D9", command=self.add_trans).pack(side="left", padx=(6, 0))

    def build_transactions(self):
        card = self.card()
        card.pack(fill="x")
        ctk.CTkLabel(card, text="📜 Transaction History", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 6))
        self.trans_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.trans_frame.pack(fill="x", padx=16, pady=(0, 14))
        self.render_trans()

    def render_trans(self):
        for w in self.trans_frame.winfo_children():
            w.destroy()
        for t in self.data["budget"]["transactions"][::-1]:
            row = ctk.CTkFrame(self.trans_frame, fg_color=C_BG, corner_radius=8)
            row.pack(fill="x", pady=2)
            ri = ctk.CTkFrame(row, fg_color="transparent")
            ri.pack(fill="x", padx=12, pady=8)
            icon = "📥" if t["type"] == "Income" else "📤"
            col = C_SUCCESS if t["type"] == "Income" else C_DANGER
            ctk.CTkLabel(ri, text=icon, font=ctk.CTkFont(size=16)).pack(side="left")
            info = ctk.CTkFrame(ri, fg_color="transparent")
            info.pack(side="left", padx=(10, 0), fill="x", expand=True)
            ctk.CTkLabel(info, text=t["desc"], font=ctk.CTkFont(size=12, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=t["date"], font=ctk.CTkFont(size=10), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w")
            sign = "+" if t["type"] == "Income" else "-"
            ctk.CTkLabel(ri, text=f"{sign}₱{t['amount']:.2f}", font=ctk.CTkFont(size=13, weight="bold"), text_color=col).pack(side="right")

    def add_trans(self):
        try:
            amt = float(self.t_amt.get().strip())
            desc = self.t_desc.get().strip() or "Unnamed"
            typ = self.t_type.get()
            today = datetime.date.today().strftime("%b %d, %Y")
            self.data["budget"]["transactions"].append({"type": typ, "desc": desc, "amount": amt, "date": today})
            if typ == "Income":
                self.data["budget"]["income"] += amt
                self.data["budget"]["balance"] += amt
            else:
                self.data["budget"]["expenses"] += amt
                self.data["budget"]["balance"] -= amt
            save_data(self.data)
            self.t_desc.delete(0, "end"); self.t_amt.delete(0, "end")
            self.build_summary()
            self.render_trans()
        except Exception:
            messagebox.showwarning("Warning", "Please enter a valid amount!")


# ============================================================
# SETTINGS PAGE
# ============================================================
class SettingsPage(BasePage):
    def __init__(self, master, data, navigate, app=None):
        super().__init__(master, data, navigate, app)
        self.header("⚙️ Settings", "Manage your profile & preferences")
        # Profile
        card = self.card()
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text="👤 Profile", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 8))
        f = ctk.CTkFrame(card, fg_color="transparent")
        f.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(f, text="Name:", font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, width=80, anchor="w").pack(side="left")
        self.name_e = ctk.CTkEntry(f, height=38, fg_color=C_BG, border_color=C_ACCENT)
        self.name_e.insert(0, data["user"]["name"])
        self.name_e.pack(side="left", fill="x", expand=True, padx=(0, 6))
        f2 = ctk.CTkFrame(card, fg_color="transparent")
        f2.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(f2, text="Course:", font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, width=80, anchor="w").pack(side="left")
        self.course_e = ctk.CTkEntry(f2, height=38, fg_color=C_BG, border_color=C_ACCENT)
        self.course_e.insert(0, data["user"]["course"])
        self.course_e.pack(side="left", fill="x", expand=True, padx=(0, 6))
        f3 = ctk.CTkFrame(card, fg_color="transparent")
        f3.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(f3, text="Password:", font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, width=80, anchor="w").pack(side="left")
        self.pw_e = ctk.CTkEntry(f3, height=38, fg_color=C_BG, border_color=C_ACCENT, show="•")
        self.pw_e.insert(0, data["user"]["password"])
        self.pw_e.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(card, text="💾 Save Profile", fg_color=C_ACCENT, hover_color="#6D28D9", command=self.save_profile).pack(anchor="w", padx=16, pady=(0, 14))
        # About
        about = self.card()
        about.pack(fill="x")
        ctk.CTkLabel(about, text="ℹ️ About StudyMate PH", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 6))
        ctk.CTkLabel(about, text="Version 1.0 · Built with Python + CustomTkinter\nPlan · Study · Achieve 🎓",
                     font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w", justify="left").pack(anchor="w", padx=16, pady=(0, 14))

    def save_profile(self):
        self.data["user"]["name"] = self.name_e.get().strip() or "User"
        self.data["user"]["course"] = self.course_e.get().strip() or "Student"
        self.data["user"]["password"] = self.pw_e.get().strip() or "1234"
        save_data(self.data)
        self.app.name_lbl.configure(text=self.data["user"]["name"])
        self.app.course_lbl.configure(text=self.data["user"]["course"])
        messagebox.showinfo("Saved", "Profile updated successfully! ✅")


# ============================================================
# DEADLINE REMINDER PAGE
# ============================================================
class DeadlineReminderPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("🔔 Deadline Reminder", "Upcoming deadlines with countdown")
        for d in sorted(data["deadlines"], key=lambda x: x["days_left"]):
            card = self.card()
            card.pack(fill="x", pady=5)
            ri = ctk.CTkFrame(card, fg_color="transparent")
            ri.pack(fill="x", padx=16, pady=14)
            urgency = C_DANGER if d["days_left"] <= 2 else (C_WARNING if d["days_left"] <= 5 else C_SUCCESS)
            ctk.CTkLabel(ri, text="📄", font=ctk.CTkFont(size=24), fg_color=d["color"], corner_radius=10, width=44, height=44).pack(side="left")
            info = ctk.CTkFrame(ri, fg_color="transparent")
            info.pack(side="left", padx=(12, 0), fill="x", expand=True)
            ctk.CTkLabel(info, text=d["title"], font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=f"📅 Due: {d['due']}", font=ctk.CTkFont(size=11), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w")
            ctk.CTkLabel(ri, text=f"⏰ {d['days_left']} days left", font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=urgency, fg_color="#2A1F10" if urgency == C_WARNING else ("#2A1010" if urgency == C_DANGER else "#102A1A"),
                         corner_radius=10).pack(side="right")


# ============================================================
# MISSED TASK RECOVERY PAGE
# ============================================================
class MissedTaskPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("♻️ Missed Task Recovery", "Recover and reschedule overdue tasks")
        overdue = [t for t in data["tasks"] if t["overdue"] and not t["done"]]
        if not overdue:
            card = self.card()
            card.pack(fill="x", pady=20)
            ctk.CTkLabel(card, text="🎉 No missed tasks! You're all caught up!", font=ctk.CTkFont(size=15), text_color=C_SUCCESS).pack(pady=30)
            return
        for t in overdue:
            card = self.card()
            card.pack(fill="x", pady=5)
            ri = ctk.CTkFrame(card, fg_color="transparent")
            ri.pack(fill="x", padx=16, pady=12)
            ctk.CTkLabel(ri, text="🔴", font=ctk.CTkFont(size=20)).pack(side="left")
            info = ctk.CTkFrame(ri, fg_color="transparent")
            info.pack(side="left", padx=(10, 0), fill="x", expand=True)
            ctk.CTkLabel(info, text=t["title"], font=ctk.CTkFont(size=13, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=f"Was due: {t['due']}", font=ctk.CTkFont(size=11), text_color=C_DANGER, anchor="w").pack(anchor="w")
            ctk.CTkButton(ri, text="♻️ Recover", width=100, height=36, fg_color=C_SUCCESS, hover_color="#059669",
                          command=lambda tid=t["id"]: self.recover(tid)).pack(side="right", padx=(6, 0))
            ctk.CTkButton(ri, text="✅ Done", width=80, height=36, fg_color=C_ACCENT, hover_color="#6D28D9",
                          command=lambda tid=t["id"]: self.mark_done(tid)).pack(side="right")

    def recover(self, tid):
        for t in self.data["tasks"]:
            if t["id"] == tid:
                t["overdue"] = False
                t["due"] = datetime.date.today().strftime("%b %d, %Y") + " (rescheduled)"
        save_data(self.data)
        messagebox.showinfo("Recovered", "Task recovered and rescheduled to today! ✅")
        self.navigate("My Tasks")

    def mark_done(self, tid):
        for t in self.data["tasks"]:
            if t["id"] == tid:
                t["done"] = True
                t["overdue"] = False
        save_data(self.data)
        messagebox.showinfo("Done", "Marked as completed! ✅")
        self.navigate("My Tasks")


# ============================================================
# EXPORT REPORTS PAGE
# ============================================================
class ExportReportsPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("📤 Export Reports", "Download your data as CSV files")
        options = [
            ("📋 Tasks Report", "tasks", "Export all your tasks"),
            ("⏰ Deadlines Report", "deadlines", "Export upcoming deadlines"),
            ("🎓 Grades Report", "grades", "Export your grade report"),
            ("💰 Budget Report", "budget", "Export your transactions"),
        ]
        for label, key, desc in options:
            card = self.card()
            card.pack(fill="x", pady=5)
            ri = ctk.CTkFrame(card, fg_color="transparent")
            ri.pack(fill="x", padx=16, pady=12)
            info = ctk.CTkFrame(ri, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(info, text=label, font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=desc, font=ctk.CTkFont(size=11), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w")
            ctk.CTkButton(ri, text="📥 Export CSV", width=130, height=38, fg_color=C_ACCENT, hover_color="#6D28D9",
                          command=lambda k=key: self.export(k)).pack(side="right")

    def export(self, key):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")],
                                            initialfile=f"studymate_{key}.csv")
        if not path:
            return
        try:
            with open(path, "w", newline="") as f:
                w = csv.writer(f)
                if key == "tasks":
                    w.writerow(["Title", "Due Date", "Category", "Status"])
                    for t in self.data["tasks"]:
                        status = "Done" if t["done"] else ("Overdue" if t["overdue"] else "Pending")
                        w.writerow([t["title"], t["due"], t["category"], status])
                elif key == "deadlines":
                    w.writerow(["Title", "Due Date", "Days Left"])
                    for d in self.data["deadlines"]:
                        w.writerow([d["title"], d["due"], d["days_left"]])
                elif key == "grades":
                    w.writerow(["Subject", "Units", "Grade"])
                    for g in self.data["grades"]:
                        w.writerow([g["subject"], g["units"], g["grade"]])
                elif key == "budget":
                    w.writerow(["Type", "Description", "Amount", "Date"])
                    for t in self.data["budget"]["transactions"]:
                        w.writerow([t["type"], t["desc"], t["amount"], t["date"]])
            messagebox.showinfo("Exported", f"Report saved to:\n{path} ✅")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")


# ============================================================
# TIME ESTIMATOR PAGE
# ============================================================
class TimeEstimatorPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("⏱️ Time Estimator", "Estimate how long a task will take")
        card = self.card()
        card.pack(fill="x", pady=(0, 12))
        f = ctk.CTkFrame(card, fg_color="transparent")
        f.pack(fill="x", padx=16, pady=16)
        ctk.CTkLabel(f, text="Task type:", font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w")
        self.task_type = ctk.CTkComboBox(f, values=["Assignment", "Project", "Research Paper", "Quiz Review", "Essay", "Lab Report"],
                                         height=40, fg_color=C_BG, button_color=C_ACCENT)
        self.task_type.set("Assignment")
        self.task_type.pack(fill="x", pady=(4, 12))
        ctk.CTkLabel(f, text="Difficulty (1-5):", font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w")
        self.diff = ctk.CTkSlider(f, from_=1, to=5, number_of_steps=4, progress_color=C_ACCENT, button_color=C_ACCENT2)
        self.diff.set(3)
        self.diff.pack(fill="x", pady=(4, 12))
        self.diff_lbl = ctk.CTkLabel(f, text="Difficulty: 3", font=ctk.CTkFont(size=12), text_color=C_TEXT)
        self.diff_lbl.pack(anchor="w")
        self.diff.configure(command=lambda v: self.diff_lbl.configure(text=f"Difficulty: {int(v)}"))
        ctk.CTkButton(f, text="🔮 Estimate Time", height=42, fg_color=C_ACCENT, hover_color="#6D28D9",
                      font=ctk.CTkFont(size=13, weight="bold"), command=self.estimate).pack(fill="x", pady=(12, 0))
        self.result = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_SUCCESS, justify="center")
        self.result.pack(pady=(0, 16))

    def estimate(self):
        base = {"Assignment": 2, "Project": 8, "Research Paper": 12, "Quiz Review": 3, "Essay": 4, "Lab Report": 3}
        hours = base[self.task_type.get()] * int(self.diff.get()) * 0.7
        self.result.configure(text=f"⏱ Estimated time: ~{hours:.1f} hours\n📅 Start at least {max(1, int(hours/4))} days before deadline!")


# ============================================================
# AI STUDY ASSISTANT PAGE (keyword-based)
# ============================================================
class AIAssistantPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("🤖 AI Study Assistant", "Ask me anything about studying!")
        self.chat_box = ctk.CTkTextbox(self, fg_color=C_CARD, font=ctk.CTkFont(size=12), corner_radius=12, height=340)
        self.chat_box.pack(fill="x", pady=(0, 10))
        self.chat_box.insert("1.0", "🤖 Hi! I'm your AI Study Assistant. Ask me about:\n- Study tips\n- Time management\n- Stress relief\n- Exam preparation\n- Motivation\n\nTry: 'How do I focus better?'\n\n")
        self.chat_box.configure(state="disabled")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        self.query = ctk.CTkEntry(row, placeholder_text="Type your question...", height=42, fg_color=C_BG, border_color=C_ACCENT)
        self.query.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.query.bind("<Return>", lambda e: self.send())
        ctk.CTkButton(row, text="➤ Send", width=90, height=42, fg_color=C_ACCENT, hover_color="#6D28D9", command=self.send).pack(side="left")

    def send(self):
        q = self.query.get().strip().lower()
        if not q:
            return
        self.query.delete(0, "end")
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"\n👤 You: {q}\n")
        resp = self.respond(q)
        self.chat_box.insert("end", f"🤖 AI: {resp}\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def respond(self, q):
        if any(w in q for w in ["focus", "concentrate", "distract"]):
            return "Try the Pomodoro technique! Study 25 min, break 5 min. Put your phone away and use Focus Mode. Clear your desk before starting. 🎯"
        elif any(w in q for w in ["time", "manage", "schedule", "procrastinat"]):
            return "Use your Study Planner! Break big tasks into small ones. Use the 2-minute rule - if it takes <2 min, do it now. Plan your day every morning. ⏰"
        elif any(w in q for w in ["stress", "anxious", "tired", "burnout", "sleep"]):
            return "Take care of yourself! Sleep 7-8 hours, drink water, take short walks. Don't forget to rest - your brain needs it. You're doing great! 💚"
        elif any(w in q for w in ["exam", "test", "quiz", "review", "cram"]):
            return "Start reviewing early! Use active recall and flashcards in Study Space. Teach the material to someone. Check Exam Countdown for your schedule. 📚"
        elif any(w in q for w in ["motivat", "lazy", "tired of", "give up"]):
            return "Remember your goals! Small steps every day lead to big results. You've come this far - keep going! Your future self will thank you. 🌟"
        elif any(w in q for w in ["note", "notes"]):
            return "Use the Cornell method! Divide your notes into cues, notes, and summary. Review them within 24 hours. Check your Notes & Files. 📝"
        elif any(w in q for w in ["hello", "hi", "hey", "kumusta", "musta"]):
            return "Hello! I'm here to help you study better. What do you need help with? 😊"
        elif any(w in q for w in ["thank", "salamat"]):
            return "You're welcome! Good luck with your studies! 💪"
        else:
            tips = ["Try breaking your task into smaller steps!", "Take a 5-minute break to recharge.", "Write down your goal where you can see it.", "Use the Study Planner to stay on track."]
            return random.choice(tips) + " (Ask me about focus, time management, exams, or motivation!)"


# ============================================================
# EXAM COUNTDOWN PAGE
# ============================================================
class ExamCountdownPage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("📆 Exam Countdown", "Days until your exams")
        self.today = datetime.date(2025, 4, 29)
        card = self.card()
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text="➕ Add Exam", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 8))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))
        self.ex_subj = ctk.CTkEntry(row, placeholder_text="Subject", height=38, fg_color=C_BG, border_color=C_ACCENT)
        self.ex_subj.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.ex_date = ctk.CTkEntry(row, placeholder_text="Date (YYYY-MM-DD)", width=180, height=38, fg_color=C_BG, border_color=C_ACCENT)
        self.ex_date.pack(side="left", padx=6)
        ctk.CTkButton(row, text="Add", width=80, height=38, fg_color=C_ACCENT, hover_color="#6D28D9", command=self.add_exam).pack(side="left", padx=(6, 0))
        self.list_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.list_frame.pack(fill="x")
        self.render_exams()

    def render_exams(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        for e in sorted(self.data["exams"], key=lambda x: x["date"]):
            try:
                edate = datetime.datetime.strptime(e["date"], "%Y-%m-%d").date()
                days = (edate - self.today).days
            except Exception:
                days = "?"
            card = self.card(self.list_frame)
            card.pack(fill="x", pady=4)
            ri = ctk.CTkFrame(card, fg_color="transparent")
            ri.pack(fill="x", padx=16, pady=12)
            color = C_DANGER if isinstance(days, int) and days <= 3 else (C_WARNING if isinstance(days, int) and days <= 7 else C_SUCCESS)
            ctk.CTkLabel(ri, text="📖", font=ctk.CTkFont(size=22)).pack(side="left")
            info = ctk.CTkFrame(ri, fg_color="transparent")
            info.pack(side="left", padx=(10, 0), fill="x", expand=True)
            ctk.CTkLabel(info, text=e["subject"], font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=f"📅 {e['date']}", font=ctk.CTkFont(size=11), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w")
            ctk.CTkLabel(ri, text=f"⏳ {days} days", font=ctk.CTkFont(size=15, weight="bold"), text_color=color).pack(side="right")

    def add_exam(self):
        subj = self.ex_subj.get().strip()
        date = self.ex_date.get().strip()
        if not subj or not date:
            messagebox.showwarning("Warning", "Fill in both subject and date!")
            return
        self.data["exams"].append({"subject": subj, "date": date})
        save_data(self.data)
        self.ex_subj.delete(0, "end"); self.ex_date.delete(0, "end")
        self.render_exams()


# ============================================================
# FOCUS MODE PAGE
# ============================================================
class FocusModePage(BasePage):
    def __init__(self, master, data, navigate):
        super().__init__(master, data, navigate)
        self.header("🌙 Focus Mode", "Distraction-free deep work session")
        self.time_left = 50 * 60
        self.running = False
        self.job = None
        card = ctk.CTkFrame(self, fg_color="#0A0A14", corner_radius=18)
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text="🎯 Deep Focus Session", font=ctk.CTkFont(size=18, weight="bold"), text_color=C_TEXT).pack(pady=(24, 6))
        ctk.CTkLabel(card, text="Put your phone away. No distractions. Just you and your work.",
                     font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM).pack(pady=(0, 16))
        self.focus_lbl = ctk.CTkLabel(card, text="50:00", font=ctk.CTkFont(size=56, weight="bold"), text_color=C_ACCENT2)
        self.focus_lbl.pack(pady=(0, 16))
        self.focus_pb = ctk.CTkProgressBar(card, progress_color=C_ACCENT2, fg_color=C_CARD, height=10)
        self.focus_pb.pack(fill="x", padx=60, pady=(0, 20))
        self.focus_pb.set(1.0)
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(pady=(0, 24))
        self.f_start = ctk.CTkButton(btns, text="▶ Start Focus", width=130, height=44, fg_color=C_ACCENT2, hover_color="#2563EB",
                                     font=ctk.CTkFont(size=13, weight="bold"), command=self.toggle)
        self.f_start.pack(side="left", padx=4)
        ctk.CTkButton(btns, text="⏹ Reset", width=110, height=44, fg_color=C_DANGER, hover_color="#B91C1C",
                      font=ctk.CTkFont(size=13, weight="bold"), command=self.reset).pack(side="left", padx=4)
        tips = self.card()
        tips.pack(fill="x")
        ctk.CTkLabel(tips, text="🧘 Focus Tips", font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT, anchor="w").pack(anchor="w", padx=16, pady=(12, 6))
        for t in ["Silence all notifications", "Keep only one tab/window open", "Have water nearby to avoid getting up", "Set a clear goal for this session"]:
            ctk.CTkLabel(tips, text=f"  ✅ {t}", font=ctk.CTkFont(size=12), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w", padx=20, pady=2)
        ctk.CTkLabel(tips, text="", height=8).pack()

    def toggle(self):
        if self.running:
            self.running = False
            self.f_start.configure(text="▶ Resume", fg_color=C_ACCENT2)
            if self.job:
                self.after_cancel(self.job)
        else:
            self.running = True
            self.f_start.configure(text="⏸ Pause", fg_color=C_WARNING)
            self.tick()

    def tick(self):
        if not self.running:
            return
        if self.time_left > 0:
            self.time_left -= 1
            m, s = divmod(self.time_left, 60)
            self.focus_lbl.configure(text=f"{m:02d}:{s:02d}")
            self.focus_pb.set(self.time_left / (50 * 60))
            self.job = self.after(1000, self.tick)
        else:
            self.running = False
            self.f_start.configure(text="▶ Start Focus", fg_color=C_ACCENT2)
            messagebox.showinfo("Focus Complete!", "Amazing! You completed a 50-minute deep focus session! 🎉 Take a well-deserved break. ☕")

    def reset(self):
        self.running = False
        if self.job:
            self.after_cancel(self.job)
        self.time_left = 50 * 60
        self.focus_lbl.configure(text="50:00")
        self.focus_pb.set(1.0)
        self.f_start.configure(text="▶ Start Focus", fg_color=C_ACCENT2)


# ============================================================
# APP CONTROLLER (loading -> login -> main)
# ============================================================
class AppController(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.data = load_data()
        self.title("StudyMate PH")
        self.geometry("1100x720")
        self.minsize(900, 620)
        self.configure(fg_color=C_BG)
        cap = make_grad_cap_image(64)
        try:
            self._icon_ref2 = ImageTk.PhotoImage(cap)
            self.iconphoto(False, self._icon_ref2)
        except Exception:
            pass
        self.current = None
        self.show_loading()

    def clear(self):
        if self.current:
            self.current.destroy()

    def show_loading(self):
        self.clear()
        self.current = LoadingScreen(self, self.show_login)

    def show_login(self):
        self.clear()
        self.current = LoginScreen(self, self.data, self.show_main)

    def show_main(self):
        self.clear()
        self.current = StudyMateApp(self, self.data)


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    controller = AppController()
    controller.mainloop()
