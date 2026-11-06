"""Tareitas: gestor local de tareas en Tkinter, empaquetable en un solo EXE."""
from __future__ import annotations

import calendar
import ctypes
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

# Debe ejecutarse antes de crear Tk: evita que Windows escale la interfaz
# como una imagen borrosa en pantallas de alta densidad.
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass

APP = "Tareitas"
APP_FONT = "Segoe UI Variable"
WEEKDAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
CATEGORIES = ("General", "Idea", "Comida", "Trabajo", "Deporte", "Música")
ICONS = {"General": "✓", "Idea": "💡", "Comida": "☕", "Trabajo": "▣", "Deporte": "⚽", "Música": "♫"}
PALETTES = {
    "Violeta / Lavanda": ("#c400e9", "#f4d5fa", "#a000c2", "#efd1f5"),
    "Celeste": ("#4aabd4", "#dff4fb", "#287b9d", "#d7f0fa"),
    # Rojo profundo y dorado.
    "León": ("#9B1B30", "#D4AF37", "#806A1B", "#F4E8BD"),
    # Verde esmeralda y plateado, tal como el tema Serpiente solicitado.
    "Serpiente": ("#007A4D", "#C0C0C0", "#6E7781", "#E8ECEF"),
    # Azul zafiro y bronce.
    "Cuervo": ("#0F52BA", "#CD7F32", "#7A4D29", "#E0EAF8"),
    # Negro y dorado.
    "Tejón": ("#151515", "#D4AF37", "#806A1B", "#F3E8B9"),
}

# Fondo secundario de cada tema cuando se usa modo oscuro.  No se usa un
# único gris: así los botones y tarjetas conservan la identidad del tema.
DARK_SOFT = {
    "Violeta / Lavanda": "#48335c",
    "Celeste": "#1d4d62",
    "León": "#70551A",
    "Serpiente": "#5D6870",
    "Cuervo": "#6A4525",
    "Tejón": "#70551A",
}


def data_path() -> Path:
    folder = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TareitasTk"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "tareas.db"


class Database:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(data_path())
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks(
          id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL,
          weekdays TEXT NOT NULL DEFAULT '', interval_days INTEGER NOT NULL DEFAULT 0, start_date TEXT NOT NULL,
          end_date TEXT NOT NULL DEFAULT '', start_time TEXT NOT NULL DEFAULT '', end_time TEXT NOT NULL DEFAULT '', reminder_minutes INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS completions(task_id INTEGER NOT NULL, day TEXT NOT NULL, completed_at TEXT NOT NULL, PRIMARY KEY(task_id,day));
        CREATE TABLE IF NOT EXISTS pomodoros(id INTEGER PRIMARY KEY, title TEXT NOT NULL, work INTEGER NOT NULL, rest INTEGER NOT NULL, cycles INTEGER NOT NULL, completed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS deadline_alerts(task_id INTEGER NOT NULL, day TEXT NOT NULL, reminder_minutes INTEGER NOT NULL, PRIMARY KEY(task_id,day,reminder_minutes));
        """)
        columns={row[1] for row in self.conn.execute("PRAGMA table_info(tasks)")}
        if "reminder_minutes" not in columns:
            self.conn.execute("ALTER TABLE tasks ADD COLUMN reminder_minutes INTEGER NOT NULL DEFAULT 0")
        self.conn.commit()
        self.seed_example_task()

    def seed_example_task(self) -> None:
        """Incluye una única tarea guía solo para perfiles locales nuevos."""
        seeded=self.setting("example_task_seeded","0")
        total=self.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        if seeded == "1": return
        if total == 0:
            self.conn.execute(
                "INSERT INTO tasks(title,description,category,start_date) VALUES(?,?,?,?)",
                ("Ejemplo: organiza tu día", "Puedes editar esta tarea o eliminarla cuando crees las tuyas.", "General", date.today().isoformat()),
            )
            self.conn.commit()
        self.set_setting("example_task_seeded","1")

    def setting(self, key: str, default: str) -> str:
        row=self.conn.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value))
        self.conn.commit()

    def due(self, target: date):
        result = []
        for task in self.conn.execute("SELECT * FROM tasks WHERE active=1 ORDER BY start_time,title COLLATE NOCASE"):
            start = date.fromisoformat(task["start_date"])
            if target < start or (task["end_date"] and target > date.fromisoformat(task["end_date"])):
                continue
            weekly = str(target.weekday()) in task["weekdays"].split(",")
            periodic = task["interval_days"] > 0 and (target - start).days % task["interval_days"] == 0
            one_time = not task["weekdays"] and task["interval_days"] == 0 and target == start
            if weekly or periodic or one_time:
                result.append(task)
        return result

    def save_task(self, values: dict, task_id: int | None = None) -> None:
        fields = (values["title"].strip(), values["description"].strip(), values["category"], ",".join(map(str, values["weekdays"])), values["interval"], values["start"].isoformat(), values["end"].isoformat() if values["end"] else "", values["start_time"], values["end_time"], values["reminder_minutes"])
        if task_id:
            self.conn.execute("UPDATE tasks SET title=?,description=?,category=?,weekdays=?,interval_days=?,start_date=?,end_date=?,start_time=?,end_time=?,reminder_minutes=? WHERE id=?", (*fields, task_id))
        else:
            self.conn.execute("INSERT INTO tasks(title,description,category,weekdays,interval_days,start_date,end_date,start_time,end_time,reminder_minutes) VALUES(?,?,?,?,?,?,?,?,?,?)", fields)
        self.conn.commit()

    def delete_task(self, task_id: int) -> None:
        self.conn.execute("DELETE FROM completions WHERE task_id=?",(task_id,))
        self.conn.execute("DELETE FROM deadline_alerts WHERE task_id=?",(task_id,))
        self.conn.execute("DELETE FROM tasks WHERE id=?",(task_id,))
        self.conn.commit()

    def completed(self, task_id: int, target: date) -> bool:
        return bool(self.conn.execute("SELECT 1 FROM completions WHERE task_id=? AND day=?", (task_id, target.isoformat())).fetchone())

    def toggle(self, task_id: int, target: date, done: bool) -> None:
        if done: self.conn.execute("INSERT OR REPLACE INTO completions VALUES(?,?,?)", (task_id, target.isoformat(), datetime.now().isoformat()))
        else: self.conn.execute("DELETE FROM completions WHERE task_id=? AND day=?", (task_id, target.isoformat()))
        self.conn.commit()

    def counts(self):
        return dict(self.conn.execute("SELECT category,COUNT(*) FROM tasks WHERE active=1 GROUP BY category"))

    def history(self):
        return self.conn.execute("SELECT c.day,t.title FROM completions c JOIN tasks t ON t.id=c.task_id ORDER BY c.day DESC LIMIT 100").fetchall()

    def pomodoro_number(self):
        return self.conn.execute("SELECT COUNT(*) FROM pomodoros WHERE date(completed_at)=?", (date.today().isoformat(),)).fetchone()[0] + 1

    def save_pomodoro(self, title, work, rest, cycles):
        self.conn.execute("INSERT INTO pomodoros(title,work,rest,cycles,completed_at) VALUES(?,?,?,?,?)", (title, work, rest, cycles, datetime.now().isoformat()))
        self.conn.commit()

    def deadline_alert_was_sent(self, task_id: int, day: date, reminder_minutes: int) -> bool:
        return bool(self.conn.execute("SELECT 1 FROM deadline_alerts WHERE task_id=? AND day=? AND reminder_minutes=?",(task_id,day.isoformat(),reminder_minutes)).fetchone())

    def mark_deadline_alert_sent(self, task_id: int, day: date, reminder_minutes: int) -> None:
        self.conn.execute("INSERT OR IGNORE INTO deadline_alerts(task_id,day,reminder_minutes) VALUES(?,?,?)",(task_id,day.isoformat(),reminder_minutes))
        self.conn.commit()


class Tareitas(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(APP); self.geometry("620x850"); self.minsize(540, 720)
        # En pantallas Windows de alta densidad Tk amplía las fuentes en
        # exceso. Esta escala conserva nitidez y las reduce de forma pareja.
        self.tk.call("tk", "scaling", 1.23)
        self.db, self.day = Database(), date.today()
        saved_palette=self.db.setting("palette", "Violeta / Lavanda")
        self.palette_name = saved_palette if saved_palette in PALETTES else "Violeta / Lavanda"
        self.dark = self.db.setting("dark", "0") == "1"
        self.notice_minutes = int(self.db.setting("notice_minutes", "120"))
        self.calendar_month = self.day.replace(day=1)
        self.mini_widget = None
        self.mini_expanded = False
        self.style = ttk.Style(self); self.style.theme_use("clam")
        self.container = tk.Frame(self); self.container.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW",self.close_main_window)
        self.apply_theme(); self.show_home(); self.after(self.notice_minutes * 60_000, self.pending_notice); self.after(60_000, self.deadline_reminders)

    def colors(self):
        accent, soft, muted, page = PALETTES[self.palette_name]
        if self.dark:
            return accent, DARK_SOFT[self.palette_name], muted, "#14131a", "#202028", "#f4f0f7"
        return accent, soft, muted, page, "#ffffff", "#1f1a24"

    def apply_theme(self):
        a,s,m,p,surface,ink = self.colors(); self.configure(bg=p)
        # Las pantallas con márgenes muestran este contenedor; debe recibir el
        # fondo correcto para que no aparezca un marco blanco en modo oscuro.
        if hasattr(self, "container"): self.container.configure(bg=p)
        self.style.configure("TFrame", background=p); self.style.configure("Card.TFrame", background=surface)
        self.style.configure("TLabel", background=p, foreground=ink, font=(APP_FONT, 11)); self.style.configure("Title.TLabel", font=(APP_FONT, 25, "bold"), foreground=ink)
        self.style.configure("TButton", padding=9, font=(APP_FONT, 10, "bold"), background=s, foreground=ink, borderwidth=0)
        self.style.map("TButton", background=[("active", a)], foreground=[("active", "white")])
        self.style.configure("Accent.TButton", background=a, foreground="white"); self.style.configure("Soft.TButton", background=s, foreground=ink)
        self.style.configure("TEntry", fieldbackground=surface, foreground=ink)
        self.style.configure("TCombobox", fieldbackground=surface, background=s, foreground=ink, arrowcolor=ink, bordercolor=s, lightcolor=s, darkcolor=s)
        self.style.map("TCombobox", fieldbackground=[("readonly",surface)], foreground=[("readonly",ink)], selectbackground=[("readonly",s)], selectforeground=[("readonly",ink)])
        # El menú emergente del Combobox es nativo; estas opciones completan
        # los colores que ttk no propaga automáticamente en Windows.
        self.option_add("*TCombobox*Listbox.background",surface)
        self.option_add("*TCombobox*Listbox.foreground",ink)
        self.option_add("*TCombobox*Listbox.selectBackground",a)
        self.option_add("*TCombobox*Listbox.selectForeground","white")
        self.style.configure("Slim.Vertical.TScrollbar", background=s, troughcolor=surface, borderwidth=0, arrowsize=9, width=8)
        self.after_idle(self.apply_window_chrome)

    def apply_window_chrome(self, window=None):
        """Sincroniza la barra nativa de Windows con el modo de la app."""
        if sys.platform != "win32": return
        try:
            target=window or self; value=ctypes.c_int(1 if self.dark else 0)
            hwnd=target.winfo_id()
            # 20 es la variante actual de Windows 11; 19 cubre Windows 10.
            result=ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,20,ctypes.byref(value),ctypes.sizeof(value))
            if result: ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,19,ctypes.byref(value),ctypes.sizeof(value))
        except (AttributeError, OSError):
            pass

    def clear(self):
        self.unbind_all("<MouseWheel>")
        for child in self.container.winfo_children(): child.destroy()

    def header(self, parent, title, back=None):
        a,_,_,_,_,_ = self.colors(); bar = tk.Frame(parent, bg=a, height=94); bar.pack(fill="x"); bar.pack_propagate(False)
        if back: tk.Button(bar, text="←", command=back, bg=a, fg="white", border=0, font=(APP_FONT,18,"bold")).place(x=24,y=10)
        tk.Label(bar, text=title, bg=a, fg="white", font=(APP_FONT,24,"bold")).place(relx=.5,y=14,anchor="n")
        return bar

    def rounded_action(self, parent, text, command, bg, fg, width=150, height=46, vertical=False, font_size=10):
        """Botón Canvas para esquinas suaves sin depender de controles nativos."""
        canvas=tk.Canvas(parent,bg=parent.cget("bg"),height=height,width=width,highlightthickness=0,cursor="hand2")
        if vertical: canvas.pack(fill="x",pady=6)
        else: canvas.pack(side="left",padx=5)
        def render(_event=None):
            canvas.delete("all"); w=max(canvas.winfo_width(),width); r=min(14,height//2)
            canvas.create_arc(0,0,2*r,2*r,start=90,extent=90,fill=bg,outline=bg)
            canvas.create_arc(w-2*r,0,w,2*r,start=0,extent=90,fill=bg,outline=bg)
            canvas.create_arc(0,height-2*r,2*r,height,start=180,extent=90,fill=bg,outline=bg)
            canvas.create_arc(w-2*r,height-2*r,w,height,start=270,extent=90,fill=bg,outline=bg)
            canvas.create_rectangle(r,0,w-r,height,fill=bg,outline=bg); canvas.create_rectangle(0,r,w,height-r,fill=bg,outline=bg)
            canvas.create_text(w/2,height/2,text=text,fill=fg,font=(APP_FONT,font_size,"bold"),tags=("action",))
        canvas.bind("<Configure>",render); canvas.bind("<Button-1>",lambda _e:command()); canvas.tag_bind("action","<Button-1>",lambda _e:command())
        return canvas

    def show_home(self):
        self.clear(); a,s,m,p,surface,ink = self.colors()
        hero = tk.Frame(self.container,bg=a,height=170); hero.pack(fill="x"); hero.pack_propagate(False)
        tk.Button(hero,text="▦",command=self.show_categories,bg=a,fg="white",activebackground=a,activeforeground="white",border=0,highlightthickness=0,font=(APP_FONT,19,"bold"),cursor="hand2").place(x=35,y=35)
        appearance = tk.Button(hero,text="🎨",command=self.show_appearance,bg=a,fg="white",activebackground=a,activeforeground="white",border=0,highlightthickness=0,font=(APP_FONT,16),cursor="hand2")
        appearance.place(relx=1.0,x=-58,y=30,width=42,height=42)
        tk.Label(hero,text=self.day.strftime("%d %b"),bg=a,fg="white",font=(APP_FONT,19,"bold")).place(relx=.5,y=22,anchor="n")
        tk.Label(hero,text="Hoy",bg=a,fg="white",font=(APP_FONT,32,"bold")).place(x=31,y=98)
        tk.Label(hero,text=f"{len(self.db.due(self.day))} tareas",bg=a,fg="white",font=(APP_FONT,13)).place(x=33,y=140)
        body = tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True)
        local_label = tk.Label(body,text="Modo local",bg=surface,fg=m,font=("Segoe UI",10)); local_label.pack(anchor="e",padx=34,pady=(27,0))
        days=tk.Frame(body,bg=surface); days.pack(fill="x",padx=22,pady=(12,18))
        tk.Button(days,text="‹",command=lambda:self.set_day(self.day-timedelta(days=1)),bg=surface,fg=m,activebackground=surface,activeforeground=m,border=0,highlightthickness=0,font=("Segoe UI",23,"bold"),cursor="hand2").pack(side="left",padx=(0,2))
        for offset in range(-3,4):
            current=self.day+timedelta(days=offset); selected=current==self.day
            self.rounded_action(days,f"{current.day:02d}\n{WEEKDAYS[current.weekday()].lower()}",lambda d=current:self.set_day(d),a if selected else s,"white" if selected else ink,60,60)
        tk.Button(days,text="›",command=lambda:self.set_day(self.day+timedelta(days=1)),bg=surface,fg=m,activebackground=surface,activeforeground=m,border=0,highlightthickness=0,font=("Segoe UI",23,"bold"),cursor="hand2").pack(side="left",padx=(2,0))
        quick=tk.Frame(body,bg=surface); quick.pack(fill="x",padx=28,pady=(0,13))
        self.rounded_action(quick,"▦  Calendario",self.show_calendar,s,ink,150)
        self.rounded_action(quick,"⌛  Pomodoro",self.show_pomodoro,s,ink,150)
        def toggle_widget_from_home():
            if self.mini_widget and self.mini_widget.winfo_exists(): self.close_mini_widget()
            else: self.show_mini_widget()
            self.show_home()
        self.rounded_action(quick,"▾  Versión mini",toggle_widget_from_home,s,ink,165)
        tk.Label(body,text="Mis tareas",bg=surface,fg=ink,font=(APP_FONT,22,"bold")).pack(anchor="w",padx=28)
        tasks=self.db.due(self.day); done=sum(self.db.completed(t["id"],self.day) for t in tasks)
        self.update_mini_widget()
        progress_ink="#f7f4fa" if self.dark else m
        if tasks:
            counters=tk.Frame(body,bg=surface); counters.pack(anchor="w",padx=28,pady=(10,4))
            tk.Label(counters,text=f"{len(tasks)-done} pendientes",bg=a,fg="white",font=(APP_FONT,11,"bold"),padx=12,pady=8).pack(side="left",padx=(0,8))
            tk.Label(counters,text=f"{done} terminadas",bg=s,fg=progress_ink,font=(APP_FONT,11,"bold"),padx=12,pady=8).pack(side="left")
        # El pie se reserva antes de la zona desplazable para que nunca quede
        # fuera de la ventana, incluso cuando una lista tenga muchas tareas.
        foot=tk.Frame(body,bg=surface,height=100); foot.pack(fill="x",side="bottom",padx=28,pady=(5,18)); foot.pack_propagate(False)
        tk.Button(foot,text="Salir",command=self.destroy,bg=surface,fg=m,activebackground=surface,activeforeground=m,border=0,highlightthickness=0,font=("Segoe UI",12,"bold"),cursor="hand2").place(x=0,y=31)
        tk.Button(foot,text="Historial",command=self.show_history,bg=surface,fg=m,activebackground=surface,activeforeground=m,border=0,highlightthickness=0,font=("Segoe UI",12,"bold"),cursor="hand2").place(relx=.47,y=31,anchor="n")
        tk.Button(foot,text="+",command=lambda:self.show_task_form("General"),bg=a,fg="white",activebackground=a,activeforeground="white",border=0,highlightthickness=0,font=(APP_FONT,29,"bold"),cursor="hand2").place(relx=1.0,x=0,y=16,width=64,height=64,anchor="ne")
        canvas=tk.Canvas(body,bg=surface,highlightthickness=0); items=tk.Frame(canvas,bg=surface)
        items.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        items_window=canvas.create_window((0,0),window=items,anchor="nw")
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(items_window,width=e.width))
        canvas.pack(fill="both",expand=True,padx=28,pady=6)
        self.bind_all("<MouseWheel>",lambda event:canvas.yview_scroll(int(-event.delta/120),"units"))
        if not tasks: tk.Label(items,text="No hay tareas para este día.",bg=surface,fg=m,font=("Segoe UI",13)).pack(pady=50)
        for task in tasks: self.task_card(items,task,s,m,ink)

    def task_card(self,parent,task,soft,muted,ink):
        # Canvas permite tarjetas redondeadas reales; los controles nativos de
        # Tkinter solo pueden ser rectangulares.
        card=tk.Canvas(parent,bg=parent.cget("bg"),height=74,highlightthickness=0,cursor="hand2")
        card.pack(fill="x",pady=6)
        completed=self.db.completed(task["id"],self.day)
        detail=" · ".join(x for x in ([task["start_time"], task["description"] or f"{ICONS[task['category']]} {task['category']}"]) if x)
        title_color="#f7f4fa" if self.dark else ink
        detail_color="#dde5f2" if self.dark else muted
        def rounded_box(canvas,x1,y1,x2,y2,r,fill):
            canvas.create_arc(x1,y1,x1+2*r,y1+2*r,start=90,extent=90,fill=fill,outline=fill)
            canvas.create_arc(x2-2*r,y1,x2,y1+2*r,start=0,extent=90,fill=fill,outline=fill)
            canvas.create_arc(x1,y2-2*r,x1+2*r,y2,start=180,extent=90,fill=fill,outline=fill)
            canvas.create_arc(x2-2*r,y2-2*r,x2,y2,start=270,extent=90,fill=fill,outline=fill)
            canvas.create_rectangle(x1+r,y1,x2-r,y2,fill=fill,outline=fill)
            canvas.create_rectangle(x1,y1+r,x2,y2-r,fill=fill,outline=fill)
        def render(_event=None):
            card.delete("all")
            width=max(card.winfo_width(),300); rounded_box(card,0,1,width-2,72,14,soft)
            mark="☑" if completed else "☐"
            card.create_text(20,23,text=mark,fill=title_color,font=("Segoe UI Symbol",15),anchor="center",tags=("toggle",))
            card.create_text(42,21,text=task["title"],fill=title_color,font=(APP_FONT,11,"bold"),anchor="w",tags=("toggle",))
            card.create_text(44,47,text=detail,fill=detail_color,font=(APP_FONT,9),anchor="w",tags=("toggle",))
            card.create_text(width-54,34,text="Editar",fill=title_color,font=(APP_FONT,9,"bold"),anchor="center",tags=("edit",))
        card.bind("<Configure>",render)
        card.tag_bind("toggle","<Button-1>",lambda _e:self.complete(task["id"],not completed))
        card.tag_bind("edit","<Button-1>",lambda _e:self.show_task_form(task["category"],task))

    def set_day(self,d): self.day=d; self.show_home()
    def complete(self,tid,value): self.db.toggle(tid,self.day,value); self.show_home()

    def show_categories(self):
        self.clear(); _,s,m,p,surface,ink=self.colors(); self.header(self.container,"Crear tarea",self.show_home); body=tk.Frame(self.container,bg=p); body.pack(fill="both",expand=True,padx=34,pady=22); tk.Label(body,text="Elige una actividad",bg=p,fg=ink,font=("Segoe UI",24,"bold")).pack(anchor="w",pady=(0,14)); counts=self.db.counts()
        for category in CATEGORIES:
            self.rounded_action(body,f"{ICONS[category]}   {category}   ·   {counts.get(category,0)} tareas",lambda c=category:self.show_task_form(c),s,ink,520,72,vertical=True,font_size=14)

    def show_quick_task(self):
        """Alta simple: queda solo para el día actual sin repetir."""
        self.clear(); a,s,m,p,surface,ink=self.colors(); self.header(self.container,"Tarea rápida",self.show_home)
        body=tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True,padx=30,pady=24)
        tk.Label(body,text="Anota una tarea para hoy",bg=surface,fg=ink,font=(APP_FONT,22,"bold")).pack(anchor="w",pady=(0,5))
        tk.Label(body,text="No necesitas elegir fecha, horario ni repetición.",bg=surface,fg=m,font=(APP_FONT,11)).pack(anchor="w",pady=(0,22))
        title=tk.StringVar(); category=tk.StringVar(value="General")
        tk.Label(body,text="Nombre de la tarea *",bg=surface,fg=ink,font=(APP_FONT,12,"bold")).pack(anchor="w")
        tk.Entry(body,textvariable=title,bg=surface,fg=ink,insertbackground=ink,font=(APP_FONT,13)).pack(fill="x",pady=(4,14),ipady=5)
        tk.Label(body,text="Descripción (opcional)",bg=surface,fg=ink,font=(APP_FONT,12,"bold")).pack(anchor="w")
        description=tk.Text(body,height=5,bg=surface,fg=ink,insertbackground=ink,font=(APP_FONT,12)); description.pack(fill="x",pady=(4,14))
        tk.Label(body,text="Categoría",bg=surface,fg=ink,font=(APP_FONT,12,"bold")).pack(anchor="w")
        ttk.Combobox(body,textvariable=category,values=CATEGORIES,state="readonly",font=(APP_FONT,12)).pack(fill="x",pady=(4,22))
        def save_quick():
            if not title.get().strip(): return messagebox.showwarning(APP,"Escribe un nombre.")
            today=date.today()
            self.db.save_task({"title":title.get(),"description":description.get("1.0","end"),"category":category.get(),"weekdays":[],"interval":0,"start":today,"end":today,"start_time":"","end_time":"","reminder_minutes":0})
            self.day=today; self.show_home()
        ttk.Button(body,text="Agregar tarea para hoy",style="Accent.TButton",command=save_quick).pack(fill="x",ipady=8)

    def show_task_form(self,category,task=None):
        self.clear(); a,s,m,p,surface,ink=self.colors(); self.header(self.container,"Editar tarea" if task else "Crear tarea",self.show_categories); body=tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True,padx=30,pady=14)
        selected=tk.StringVar(value=(task["start_date"] if task else self.day.isoformat())); self.month_grid(body,date.fromisoformat(selected.get()),lambda d:selected.set(d.isoformat()))
        category_ink = "#ffffff" if self.dark else ink
        category_var=tk.StringVar(value=category)
        tk.Label(body,text="Categoría",bg=surface,fg=ink,font=(APP_FONT,11,"bold")).pack(anchor="w",pady=(6,1))
        category_select=ttk.Combobox(body,textvariable=category_var,values=CATEGORIES,state="readonly",font=(APP_FONT,12))
        category_select.pack(fill="x",pady=(0,7))
        title=tk.StringVar(value=task["title"] if task else ""); desc=tk.Text(body,height=4,bg=surface,fg=ink,insertbackground=ink); desc.insert("1.0",task["description"] if task else "")
        tk.Label(body,text="Nombre de la tarea *",bg=surface,fg=ink,font=("Segoe UI",10,"bold")).pack(anchor="w",pady=(4,1))
        tk.Entry(body,textvariable=title,bg=surface,fg=ink,insertbackground=ink,font=("Segoe UI",11)).pack(fill="x",pady=(0,7))
        tk.Label(body,text="Descripción (opcional)",bg=surface,fg=ink,font=("Segoe UI",10,"bold")).pack(anchor="w",pady=(0,1))
        desc.pack(fill="x",pady=(0,5))
        advanced=tk.LabelFrame(body,text="Repetición, horas y fecha de fin",bg=surface,fg=ink,padx=10,pady=10); advanced.pack(fill="x",pady=8); weekdays=[]
        row=tk.Frame(advanced,bg=surface); row.pack(); old=(task["weekdays"].split(",") if task else [])
        for i,name in enumerate(WEEKDAYS):
            var=tk.BooleanVar(value=str(i) in old); weekdays.append(var); tk.Checkbutton(row,text=name,variable=var,bg=surface,fg=ink,selectcolor=surface).pack(side="left")
        interval=tk.IntVar(value=task["interval_days"] if task else 0); tk.Label(advanced,text="Cada (días, 0=no usar)",bg=surface,fg=ink).pack(anchor="w"); tk.Spinbox(advanced,from_=0,to=3650,textvariable=interval).pack(anchor="w")
        end=tk.StringVar(value=task["end_date"] if task else ""); tk.Label(advanced,text="Fecha de fin (AAAA-MM-DD, opcional)",bg=surface,fg=ink).pack(anchor="w"); tk.Entry(advanced,textvariable=end,bg=surface,fg=ink).pack(fill="x")
        start_time=tk.StringVar(value=task["start_time"] if task else "")
        end_time=tk.StringVar(value=task["end_time"] if task else "")
        schedule_enabled=tk.BooleanVar(value=bool(start_time.get() or end_time.get()))
        reminder=tk.IntVar(value=int(task["reminder_minutes"]) if task and task["reminder_minutes"] else 60)
        tk.Checkbutton(advanced,text="Esta tarea tiene horario",variable=schedule_enabled,bg=surface,fg=ink,selectcolor=surface).pack(anchor="w",pady=(8,0))
        schedule_box=tk.Frame(advanced,bg=surface)
        hours=tk.Frame(schedule_box,bg=surface); hours.pack(fill="x",pady=(5,0)); tk.Label(hours,text="Desde",bg=surface,fg=ink).pack(side="left")
        tk.Entry(hours,textvariable=start_time,width=9,bg=surface,fg=ink,insertbackground=ink).pack(side="left",padx=(7,18))
        tk.Label(hours,text="Hora límite",bg=surface,fg=ink).pack(side="left"); tk.Entry(hours,textvariable=end_time,width=9,bg=surface,fg=ink,insertbackground=ink).pack(side="left",padx=7)
        tk.Label(schedule_box,text="Avisar antes de la hora límite",bg=surface,fg=ink).pack(anchor="w",pady=(7,0))
        tk.Radiobutton(schedule_box,text="30 minutos antes",variable=reminder,value=30,bg=surface,fg=ink,selectcolor=surface).pack(anchor="w")
        tk.Radiobutton(schedule_box,text="1 hora antes",variable=reminder,value=60,bg=surface,fg=ink,selectcolor=surface).pack(anchor="w")
        def toggle_schedule(*_args):
            if schedule_enabled.get(): schedule_box.pack(fill="x")
            else: schedule_box.pack_forget()
        schedule_enabled.trace_add("write",toggle_schedule); toggle_schedule()
        def save():
            if not title.get().strip(): return messagebox.showwarning(APP,"Escribe un nombre.")
            chosen=[i for i,v in enumerate(weekdays) if v.get()]
            try: start=date.fromisoformat(selected.get()); finish=date.fromisoformat(end.get()) if end.get() else None
            except ValueError: return messagebox.showwarning(APP,"Revisa las fechas.")
            if schedule_enabled.get() and not end_time.get().strip(): return messagebox.showwarning(APP,"Indica una hora límite para activar el aviso.")
            for value in (start_time.get().strip(), end_time.get().strip()):
                if value:
                    try: datetime.strptime(value, "%H:%M")
                    except ValueError: return messagebox.showwarning(APP,"Las horas deben tener formato HH:MM.")
            if finish and finish<start:return messagebox.showwarning(APP,"La fecha de fin debe ser posterior.")
            # Sin repetición ni fecha final, una tarea completa se entiende
            # como tarea de hoy y vence el mismo día.
            if not chosen and not interval.get() and not finish: finish=start
            self.db.save_task({"title":title.get(),"description":desc.get("1.0","end"),"category":category_var.get(),"weekdays":chosen,"interval":interval.get(),"start":start,"end":finish,"start_time":start_time.get().strip() if schedule_enabled.get() else "","end_time":end_time.get().strip() if schedule_enabled.get() else "","reminder_minutes":reminder.get() if schedule_enabled.get() else 0},task["id"] if task else None); self.day=start; self.show_home()
        ttk.Button(body,text="Guardar tarea",style="Accent.TButton",command=save).pack(fill="x",pady=8)
        if task:
            def delete():
                if messagebox.askyesno(APP,f"¿Eliminar la tarea ‘{task['title']}’?"):
                    self.db.delete_task(task["id"]); self.show_home()
            tk.Button(body,text="Eliminar tarea",command=delete,bg=surface,fg=m,activebackground=surface,activeforeground=m,border=0,highlightthickness=0,font=(APP_FONT,11,"bold"),cursor="hand2").pack(pady=(2,8))

    def month_grid(self,parent,shown,choose,navigate=None,large=False):
        """Calendario propio, más grande y con celdas redondeadas."""
        a,s,m,p,surface,ink=self.colors(); box=tk.Frame(parent,bg=surface); box.pack(fill="x")
        height=400 if large else 210
        canvas=tk.Canvas(box,bg=surface,height=height,highlightthickness=0); canvas.pack(fill="x")
        state={"shown":shown}
        def round_rect(x1,y1,x2,y2,r,fill):
            canvas.create_arc(x1,y1,x1+2*r,y1+2*r,start=90,extent=90,fill=fill,outline=fill)
            canvas.create_arc(x2-2*r,y1,x2,y1+2*r,start=0,extent=90,fill=fill,outline=fill)
            canvas.create_arc(x1,y2-2*r,x1+2*r,y2,start=180,extent=90,fill=fill,outline=fill)
            canvas.create_arc(x2-2*r,y2-2*r,x2,y2,start=270,extent=90,fill=fill,outline=fill)
            canvas.create_rectangle(x1+r,y1,x2-r,y2,fill=fill,outline=fill); canvas.create_rectangle(x1,y1+r,x2,y2-r,fill=fill,outline=fill)
        def shift(offset):
            current=state["shown"]; month=current.month+offset; year=current.year
            if month == 0: month,year=12,year-1
            elif month == 13: month,year=1,year+1
            state["shown"]=date(year,month,1)
            if navigate: navigate(offset)
            else: render()
        def select_day(value):
            state["shown"]=value; choose(value)
            # En la pantalla Calendario la selección vuelve a Inicio y el
            # canvas se destruye; en el formulario sí se redibuja al instante.
            if not navigate: render()
        def render(_event=None):
            canvas.delete("all"); width=max(canvas.winfo_width(),420); margin=15; nav_h=54 if large else 42
            round_rect(margin,4,margin+48,nav_h,12,s); round_rect(width-margin-48,4,width-margin,nav_h,12,s)
            canvas.create_text(margin+24,29,text="‹",fill=ink,font=("Segoe UI",19,"bold"),tags=("prev",))
            canvas.create_text(width-margin-24,29,text="›",fill=ink,font=("Segoe UI",19,"bold"),tags=("next",))
            canvas.create_text(width/2,29,text=state["shown"].strftime("%B %Y").capitalize(),fill=ink,font=("Segoe UI",16,"bold"))
            x0=margin; available=width-margin*2; cell_w=available/7; cell_h=48 if large else 19; y0=72 if large else 52
            for col,name in enumerate(WEEKDAYS): canvas.create_text(x0+cell_w*(col+.5),y0,text=name,fill=m,font=("Segoe UI",9,"bold"))
            weeks=calendar.Calendar(0).monthdatescalendar(state["shown"].year,state["shown"].month)
            for row,week in enumerate(weeks):
                for col,current in enumerate(week):
                    x1=x0+col*cell_w+3; y1=y0+15+row*(cell_h+5); x2=x0+(col+1)*cell_w-3; y2=y1+cell_h
                    active=current == state["shown"]
                    round_rect(x1,y1,x2,y2,10,a if active else s)
                    canvas.create_text((x1+x2)/2,(y1+y2)/2,text=str(current.day),fill="white" if active else ink,font=("Segoe UI",11 if large else 8,"bold"),tags=(f"day-{current.isoformat()}",))
                    canvas.tag_bind(f"day-{current.isoformat()}","<Button-1>",lambda _event,d=current:select_day(d))
            canvas.tag_bind("prev","<Button-1>",lambda _event:shift(-1)); canvas.tag_bind("next","<Button-1>",lambda _event:shift(1))
        canvas.bind("<Configure>",render)

    def show_calendar(self):
        self.clear(); _,_,_,p,surface,ink=self.colors(); self.header(self.container,"Calendario",self.show_home); body=tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True,padx=30,pady=20)
        def move(offset):
            month=self.calendar_month.month + offset; year=self.calendar_month.year
            if month == 0: month,year=12,year-1
            elif month == 13: month,year=1,year+1
            self.calendar_month=date(year,month,1); self.show_calendar()
        self.month_grid(body,self.calendar_month,lambda d:self.set_day(d),move,large=True)
        tk.Label(body,text="Selecciona un día para ver y completar sus tareas.",bg=surface,fg=ink).pack(pady=18)

    def show_history(self):
        self.clear(); _,s,m,p,surface,ink=self.colors(); self.header(self.container,"Historial",self.show_home)
        body=tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True,padx=28,pady=20)
        tk.Label(body,text="Historial de cumplimiento",bg=surface,fg=ink,font=("Segoe UI",20,"bold")).pack(anchor="w",pady=(0,12))
        history=self.db.history()
        if not history: tk.Label(body,text="Aún no hay tareas completadas.",bg=surface,fg=m,font=("Segoe UI",12)).pack(pady=35)
        for item in history:
            self.rounded_action(body,f"✓  {item['day']}  ·  {item['title']}",lambda:None,s,ink,520,64,vertical=True,font_size=12)

    def show_pomodoro(self):
        self.clear(); _,s,m,p,surface,ink=self.colors(); self.header(self.container,"Pomodoro",self.show_home)
        body=tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True,padx=26,pady=20)
        tk.Label(body,text="Enfócate a tu ritmo",bg=surface,fg=ink,font=("Segoe UI",23,"bold")).pack(anchor="w",pady=(0,16))
        tk.Label(body,text="Tarea asociada (opcional)",bg=surface,fg=ink,font=("Segoe UI",10,"bold")).pack(anchor="w")
        names=["Sin tarea asociada"]+[row[0] for row in self.db.conn.execute("SELECT title FROM tasks WHERE active=1 ORDER BY title")]; choice=tk.StringVar(value=names[0]); ttk.Combobox(body,textvariable=choice,values=names,state="readonly").pack(fill="x",pady=(3,8)); custom=tk.StringVar(); tk.Entry(body,textvariable=custom,bg=surface,fg=ink,insertbackground=ink).pack(fill="x",pady=(0,10))
        work,rest,cycles=tk.IntVar(value=25),tk.IntVar(value=5),tk.IntVar(value=4)
        controls=tk.Frame(body,bg=surface); controls.pack(fill="x",pady=(5,10))
        for label,var,limit in (("Trabajo (min)",work,180),("Descanso (min)",rest,90),("Ciclos",cycles,12)):
            row=tk.Frame(controls,bg=surface); row.pack(fill="x",pady=7); tk.Label(row,text=label,bg=surface,fg=ink,font=("Segoe UI",11,"bold")).pack(side="left"); tk.Spinbox(row,from_=1,to=limit,textvariable=var,width=8,font=("Segoe UI",11)).pack(side="right")
        timer_card=tk.Frame(body,bg=s,height=230); timer_card.pack(fill="both",expand=True,pady=(10,16)); timer_card.pack_propagate(False)
        tk.Label(timer_card,text="POMODORO",bg=s,fg=ink,font=("Segoe UI",11,"bold")).place(relx=.5,rely=.28,anchor="center")
        status=tk.Label(timer_card,text="Listo para comenzar",bg=s,fg=ink,font=("Segoe UI",22,"bold")); status.place(relx=.5,rely=.55,anchor="center"); state={"cycle":1,"break":False,"left":0,"title":""}
        def tick():
            state["left"]-=1; mins,secs=divmod(max(state["left"],0),60); status.config(text=f"{mins:02d}:{secs:02d} · ciclo {state['cycle']}/{cycles.get()}")
            if state["left"]>0: self.after(1000,tick); return
            if state["break"]: state["break"]=False; state["cycle"]+=1
            elif state["cycle"]>=cycles.get(): self.db.save_pomodoro(state["title"],work.get(),rest.get(),cycles.get()); status.config(text="¡Pomodoro completado!"); return
            else: state["break"]=True
            state["left"]=(rest.get() if state["break"] else work.get())*60; self.after(1000,tick)
        def start():
            state.update(cycle=1,break_=False); state["break"]=False; state["title"]=custom.get().strip() or (choice.get() if choice.get()!=names[0] else f"Ciclo Pomodoro {self.db.pomodoro_number()}"); state["left"]=work.get()*60; tick()
        ttk.Button(body,text="Iniciar",style="Accent.TButton",command=start).pack(fill="x",pady=(0,4),ipady=7)

    def show_appearance(self):
        self.clear(); _,s,m,p,surface,ink=self.colors(); self.header(self.container,"Apariencia",self.show_home)
        body=tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True,padx=30,pady=18)
        tk.Label(body,text="Elige tu paleta",bg=surface,fg=ink,font=("Segoe UI",20,"bold")).pack(anchor="w",pady=(0,8))
        def select_palette(name):
            self.palette_name=name; self.db.set_setting("palette",name); self.apply_theme(); self.show_appearance()
        for name in PALETTES: self.rounded_action(body,name,lambda n=name:select_palette(n),s if name != self.palette_name else self.colors()[0],ink if name != self.palette_name else "white",520,40,vertical=True,font_size=14)
        dark=tk.BooleanVar(value=self.dark)
        def toggle_dark():
            self.dark=dark.get(); self.db.set_setting("dark","1" if self.dark else "0"); self.apply_theme(); self.show_appearance()
        tk.Checkbutton(body,text="Modo oscuro",variable=dark,bg=surface,fg=ink,command=toggle_dark,selectcolor=surface,font=("Segoe UI",11,"bold")).pack(anchor="w",pady=(12,6))
        tk.Label(body,text="Avisos de tareas pendientes",bg=surface,fg=ink,font=("Segoe UI",11,"bold")).pack(anchor="w",pady=(8,2))
        frequency=tk.IntVar(value=self.notice_minutes)
        def apply_frequency():
            self.notice_minutes=frequency.get(); self.db.set_setting("notice_minutes",str(self.notice_minutes))
        tk.Radiobutton(body,text="Cada 1 hora",variable=frequency,value=60,command=apply_frequency,bg=surface,fg=ink,selectcolor=surface).pack(anchor="w")
        tk.Radiobutton(body,text="Cada 2 horas",variable=frequency,value=120,command=apply_frequency,bg=surface,fg=ink,selectcolor=surface).pack(anchor="w")
        widget_open=bool(self.mini_widget and self.mini_widget.winfo_exists())
        widget_text="Cerrar versión mini" if widget_open else "Abrir versión mini"
        def toggle_widget():
            if self.mini_widget and self.mini_widget.winfo_exists(): self.close_mini_widget()
            else: self.show_mini_widget()
            self.show_appearance()
        self.rounded_action(body,widget_text,toggle_widget,s,ink,520,46,vertical=True,font_size=14)

    def show_mini_widget(self):
        if self.mini_widget and self.mini_widget.winfo_exists():
            self.mini_widget.deiconify(); self.mini_widget.lift(); self.update_mini_widget(); return
        a,s,m,p,surface,ink = self.colors()
        widget=tk.Toplevel(self)
        self.mini_widget=widget
        widget.title("Tareitas · Versión mini")
        widget.attributes("-topmost", True)
        widget.resizable(False,False)
        width,height=330,72
        widget.geometry(f"{width}x{height}+{max(widget.winfo_screenwidth()-width-28,0)}+{42}")
        widget.configure(bg=a)
        content=tk.Frame(widget,bg=a); content.pack(fill="x",padx=12,pady=(8,0))
        self.mini_text=tk.Label(content,bg=a,fg="white",font=(APP_FONT,12,"bold"),anchor="w")
        self.mini_text.pack(side="left",fill="both",expand=True)
        tk.Button(content,text="×",command=self.exit_app,bg=a,fg="white",activebackground=a,activeforeground="white",border=0,highlightthickness=0,font=(APP_FONT,16),cursor="hand2").pack(side="right")
        self.mini_tasks=tk.Frame(widget,bg=a)
        self.mini_expand=tk.Button(widget,text="⌄",command=self.toggle_mini_widget,bg=a,fg="white",activebackground=a,activeforeground="white",border=0,highlightthickness=0,font=(APP_FONT,15,"bold"),cursor="hand2")
        self.mini_expand.pack(side="bottom",pady=(0,3))
        content.bind("<Button-1>",lambda _event:self.restore_from_widget())
        self.mini_text.bind("<Button-1>",lambda _event:self.restore_from_widget())
        widget.protocol("WM_DELETE_WINDOW",self.exit_app)
        self.update_mini_widget()
        self.after_idle(lambda:self.apply_window_chrome(widget))

    def close_mini_widget(self):
        if self.mini_widget and self.mini_widget.winfo_exists(): self.mini_widget.destroy()
        self.mini_widget=None
        self.mini_expanded=False

    def toggle_mini_widget(self):
        self.mini_expanded=not self.mini_expanded
        self.update_mini_widget()

    def complete_from_widget(self, task_id: int):
        self.db.toggle(task_id,date.today(),True)
        self.update_mini_widget()
        if self.state() != "withdrawn": self.show_home()

    def close_main_window(self):
        """Con widget abierto, la ventana principal se oculta pero sigue viva."""
        if self.mini_widget and self.mini_widget.winfo_exists():
            self.withdraw()
        else:
            self.exit_app()

    def restore_from_widget(self):
        self.deiconify(); self.lift(); self.focus_force(); self.show_home()

    def exit_app(self):
        self.close_mini_widget()
        self.destroy()

    def update_mini_widget(self):
        if not self.mini_widget or not self.mini_widget.winfo_exists(): return
        a,s,m,p,surface,ink=self.colors()
        pending_tasks=[task for task in self.db.due(date.today()) if not self.db.completed(task["id"],date.today())]
        pending=len(pending_tasks)
        plural="tarea pendiente" if pending == 1 else "tareas pendientes"
        self.mini_text.config(text=f"Tareitas  ·  {pending} {plural} hoy")
        self.mini_expand.config(text="⌃" if self.mini_expanded else "⌄")
        for child in self.mini_tasks.winfo_children(): child.destroy()
        width=330; height=90
        if self.mini_expanded:
            self.mini_tasks.pack(fill="both",expand=True,padx=12,pady=(0,10))
            height=254
            if pending_tasks:
                for task in pending_tasks[:3]:
                    tk.Button(self.mini_tasks,text=f"☐  {task['title']}",command=lambda tid=task["id"]:self.complete_from_widget(tid),bg=s,fg=ink,activebackground=s,activeforeground=ink,border=0,highlightthickness=0,anchor="w",font=(APP_FONT,11,"bold"),padx=12,pady=8,cursor="hand2").pack(fill="x",pady=3)
            else:
                tk.Label(self.mini_tasks,text="✓ Todo listo por hoy",bg=a,fg="white",font=("Segoe UI",10,"bold")).pack(pady=20)
        else:
            self.mini_tasks.pack_forget()
        x=max(self.mini_widget.winfo_screenwidth()-width-28,0)
        self.mini_widget.geometry(f"{width}x{height}+{x}+42")

    def pending_notice(self):
        pending=[t for t in self.db.due(date.today()) if not self.db.completed(t["id"],date.today())]
        if pending: messagebox.showinfo(APP,f"Tienes {len(pending)} tarea(s) pendiente(s).")
        self.after(self.notice_minutes*60_000,self.pending_notice)

    def deadline_reminders(self):
        now=datetime.now(); today=now.date()
        for task in self.db.due(today):
            minutes=int(task["reminder_minutes"] or 0)
            if not minutes or not task["end_time"] or self.db.completed(task["id"],today): continue
            try: deadline=datetime.combine(today,datetime.strptime(task["end_time"],"%H:%M").time())
            except ValueError: continue
            remaining=(deadline-now).total_seconds()/60
            if 0 < remaining <= minutes and not self.db.deadline_alert_was_sent(task["id"],today,minutes):
                self.db.mark_deadline_alert_sent(task["id"],today,minutes)
                messagebox.showinfo(APP,f"{task['title']} sigue pendiente.\nHora límite: {task['end_time']}.")
        self.update_mini_widget()
        self.after(60_000,self.deadline_reminders)


if __name__ == "__main__":
    Tareitas().mainloop()
