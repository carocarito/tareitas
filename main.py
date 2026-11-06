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
          end_date TEXT NOT NULL DEFAULT '', start_time TEXT NOT NULL DEFAULT '', end_time TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS completions(task_id INTEGER NOT NULL, day TEXT NOT NULL, completed_at TEXT NOT NULL, PRIMARY KEY(task_id,day));
        CREATE TABLE IF NOT EXISTS pomodoros(id INTEGER PRIMARY KEY, title TEXT NOT NULL, work INTEGER NOT NULL, rest INTEGER NOT NULL, cycles INTEGER NOT NULL, completed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.conn.commit()

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
        fields = (values["title"].strip(), values["description"].strip(), values["category"], ",".join(map(str, values["weekdays"])), values["interval"], values["start"].isoformat(), values["end"].isoformat() if values["end"] else "", values["start_time"], values["end_time"])
        if task_id:
            self.conn.execute("UPDATE tasks SET title=?,description=?,category=?,weekdays=?,interval_days=?,start_date=?,end_date=?,start_time=?,end_time=? WHERE id=?", (*fields, task_id))
        else:
            self.conn.execute("INSERT INTO tasks(title,description,category,weekdays,interval_days,start_date,end_date,start_time,end_time) VALUES(?,?,?,?,?,?,?,?,?)", fields)
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


class Tareitas(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(APP); self.geometry("620x850"); self.minsize(540, 720)
        # En pantallas Windows de alta densidad Tk amplía las fuentes en
        # exceso. Esta escala conserva nitidez y las reduce de forma pareja.
        self.tk.call("tk", "scaling", 1.15)
        self.db, self.day = Database(), date.today()
        saved_palette=self.db.setting("palette", "Violeta / Lavanda")
        self.palette_name = saved_palette if saved_palette in PALETTES else "Violeta / Lavanda"
        self.dark = self.db.setting("dark", "0") == "1"
        self.notice_minutes = int(self.db.setting("notice_minutes", "120"))
        self.calendar_month = self.day.replace(day=1)
        self.mini_widget = None
        self.style = ttk.Style(self); self.style.theme_use("clam")
        self.container = tk.Frame(self); self.container.pack(fill="both", expand=True)
        self.apply_theme(); self.show_home(); self.after(self.notice_minutes * 60_000, self.pending_notice)

    def colors(self):
        accent, soft, muted, page = PALETTES[self.palette_name]
        if self.dark:
            return accent, DARK_SOFT[self.palette_name], muted, "#14131a", "#202028", "#f4f0f7"
        return accent, soft, muted, page, "#ffffff", "#1f1a24"

    def apply_theme(self):
        a,s,m,p,surface,ink = self.colors(); self.configure(bg=p)
        self.style.configure("TFrame", background=p); self.style.configure("Card.TFrame", background=surface)
        self.style.configure("TLabel", background=p, foreground=ink, font=("Segoe UI", 11)); self.style.configure("Title.TLabel", font=("Segoe UI", 25, "bold"), foreground=ink)
        self.style.configure("TButton", padding=9, font=("Segoe UI", 10, "bold"), background=s, foreground=ink, borderwidth=0)
        self.style.map("TButton", background=[("active", a)], foreground=[("active", "white")])
        self.style.configure("Accent.TButton", background=a, foreground="white"); self.style.configure("Soft.TButton", background=s, foreground=ink)
        self.style.configure("TEntry", fieldbackground=surface, foreground=ink); self.style.configure("TCombobox", fieldbackground=surface, foreground=ink)
        self.style.configure("Slim.Vertical.TScrollbar", background=s, troughcolor=surface, borderwidth=0, arrowsize=9, width=8)

    def clear(self):
        self.unbind_all("<MouseWheel>")
        for child in self.container.winfo_children(): child.destroy()

    def header(self, parent, title, back=None):
        a,_,_,_,_,_ = self.colors(); bar = tk.Frame(parent, bg=a, height=120); bar.pack(fill="x"); bar.pack_propagate(False)
        if back: tk.Button(bar, text="←", command=back, bg=a, fg="white", border=0, font=("Segoe UI",18,"bold")).place(x=24,y=22)
        tk.Label(bar, text=title, bg=a, fg="white", font=("Segoe UI",24,"bold")).place(relx=.5,y=25,anchor="n")
        return bar

    def rounded_action(self, parent, text, command, bg, fg, width=150):
        """Botón Canvas para esquinas suaves sin depender de controles nativos."""
        canvas=tk.Canvas(parent,bg=parent.cget("bg"),height=46,width=width,highlightthickness=0,cursor="hand2")
        canvas.pack(side="left",padx=5)
        def render(_event=None):
            canvas.delete("all"); w=max(canvas.winfo_width(),width); r=13
            canvas.create_arc(0,0,2*r,2*r,start=90,extent=90,fill=bg,outline=bg)
            canvas.create_arc(w-2*r,0,w,2*r,start=0,extent=90,fill=bg,outline=bg)
            canvas.create_arc(0,46-2*r,2*r,46,start=180,extent=90,fill=bg,outline=bg)
            canvas.create_arc(w-2*r,46-2*r,w,46,start=270,extent=90,fill=bg,outline=bg)
            canvas.create_rectangle(r,0,w-r,46,fill=bg,outline=bg); canvas.create_rectangle(0,r,w,46-r,fill=bg,outline=bg)
            canvas.create_text(w/2,23,text=text,fill=fg,font=("Segoe UI",10,"bold"),tags=("action",))
        canvas.bind("<Configure>",render); canvas.bind("<Button-1>",lambda _e:command()); canvas.tag_bind("action","<Button-1>",lambda _e:command())
        return canvas

    def show_home(self):
        self.clear(); a,s,m,p,surface,ink = self.colors()
        hero = tk.Frame(self.container,bg=a,height=246); hero.pack(fill="x"); hero.pack_propagate(False)
        tk.Button(hero,text="▦",command=self.show_categories,bg=a,fg="white",activebackground=a,activeforeground="white",border=0,highlightthickness=0,font=("Segoe UI",19,"bold"),cursor="hand2").place(x=35,y=35)
        appearance = tk.Button(hero,text="🎨",command=self.show_appearance,bg=a,fg="white",activebackground=a,activeforeground="white",border=0,highlightthickness=0,font=("Segoe UI",16),cursor="hand2")
        appearance.place(relx=1.0,x=-58,y=30,width=42,height=42)
        tk.Label(hero,text=self.day.strftime("%d %b"),bg=a,fg="white",font=("Segoe UI",18,"bold")).place(relx=.5,y=42,anchor="n")
        tk.Label(hero,text="Hoy",bg=a,fg="white",font=("Segoe UI",31,"bold")).place(x=31,y=166)
        tk.Label(hero,text=f"{len(self.db.due(self.day))} tareas",bg=a,fg="white",font=("Segoe UI",12)).place(x=33,y=211)
        body = tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True)
        local_label = tk.Label(body,text="Modo local",bg=surface,fg=m,font=("Segoe UI",10)); local_label.pack(anchor="e",padx=34,pady=(27,0))
        days=tk.Frame(body,bg=surface); days.pack(fill="x",padx=28,pady=(12,24))
        for offset in range(-2,3):
            current=self.day+timedelta(days=offset); selected=current==self.day
            tk.Button(days,text=f"{current.day:02d}\n{WEEKDAYS[current.weekday()].lower()}",command=lambda d=current:self.set_day(d),bg=a if selected else s,fg="white" if selected else ink,activebackground=a if selected else s,activeforeground="white" if selected else ink,border=0,highlightthickness=0,width=7,height=3,font=("Segoe UI",11,"bold"),cursor="hand2").pack(side="left",padx=5)
        quick=tk.Frame(body,bg=surface); quick.pack(fill="x",padx=28,pady=(0,13))
        self.rounded_action(quick,"▦  Calendario",self.show_calendar,s,ink,155)
        self.rounded_action(quick,"⌛  Pomodoro",self.show_pomodoro,s,ink,155)
        tk.Label(body,text="Mis tareas",bg=surface,fg=ink,font=("Segoe UI",25,"bold")).pack(anchor="w",padx=28)
        tasks=self.db.due(self.day); done=sum(self.db.completed(t["id"],self.day) for t in tasks)
        self.update_mini_widget()
        if tasks: tk.Label(body,text=f"{done} de {len(tasks)} completadas",bg=s,fg=m,font=("Segoe UI",11,"bold"),padx=12,pady=8).pack(anchor="w",padx=28,pady=(10,4))
        # El pie se reserva antes de la zona desplazable para que nunca quede
        # fuera de la ventana, incluso cuando una lista tenga muchas tareas.
        foot=tk.Frame(body,bg=surface,height=100); foot.pack(fill="x",side="bottom",padx=28,pady=(5,18)); foot.pack_propagate(False)
        tk.Button(foot,text="Salir",command=self.destroy,bg=surface,fg=m,activebackground=surface,activeforeground=m,border=0,highlightthickness=0,font=("Segoe UI",12,"bold"),cursor="hand2").place(x=0,y=31)
        tk.Button(foot,text="Historial",command=self.show_history,bg=surface,fg=m,activebackground=surface,activeforeground=m,border=0,highlightthickness=0,font=("Segoe UI",12,"bold"),cursor="hand2").place(relx=.47,y=31,anchor="n")
        tk.Button(foot,text="+",command=self.show_categories,bg=a,fg="white",activebackground=a,activeforeground="white",border=0,highlightthickness=0,font=("Segoe UI",29,"bold"),cursor="hand2").place(relx=1.0,x=0,y=16,width=64,height=64,anchor="ne")
        canvas=tk.Canvas(body,bg=surface,highlightthickness=0); scroll=ttk.Scrollbar(body,orient="vertical",command=canvas.yview,style="Slim.Vertical.TScrollbar"); items=tk.Frame(canvas,bg=surface); items.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all"))); canvas.create_window((0,0),window=items,anchor="nw"); canvas.configure(yscrollcommand=scroll.set); canvas.pack(side="left",fill="both",expand=True,padx=(28,0),pady=6); scroll.pack(side="right",fill="y",padx=(0,20))
        self.bind_all("<MouseWheel>",lambda event:canvas.yview_scroll(int(-event.delta/120),"units"))
        if not tasks: tk.Label(items,text="No hay tareas para este día.",bg=surface,fg=m,font=("Segoe UI",13)).pack(pady=50)
        for task in tasks: self.task_card(items,task,s,m,ink)

    def task_card(self,parent,task,soft,muted,ink):
        # Canvas permite tarjetas redondeadas reales; los controles nativos de
        # Tkinter solo pueden ser rectangulares.
        card=tk.Canvas(parent,bg=parent.cget("bg"),height=84,highlightthickness=0,cursor="hand2")
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
            width=max(card.winfo_width(),300); rounded_box(card,0,1,width-2,82,14,soft)
            mark="☑" if completed else "☐"
            card.create_text(20,27,text=mark,fill=title_color,font=("Segoe UI Symbol",17),anchor="center",tags=("toggle",))
            card.create_text(42,24,text=task["title"],fill=title_color,font=("Segoe UI",11,"bold"),anchor="w",tags=("toggle",))
            card.create_text(44,52,text=detail,fill=detail_color,font=("Segoe UI",9),anchor="w",tags=("toggle",))
            card.create_text(width-54,39,text="Editar",fill=title_color,font=("Segoe UI",9,"bold"),anchor="center",tags=("edit",))
        card.bind("<Configure>",render)
        card.tag_bind("toggle","<Button-1>",lambda _e:self.complete(task["id"],not completed))
        card.tag_bind("edit","<Button-1>",lambda _e:self.show_task_form(task["category"],task))

    def set_day(self,d): self.day=d; self.show_home()
    def complete(self,tid,value): self.db.toggle(tid,self.day,value); self.show_home()

    def show_categories(self):
        self.clear(); _,s,m,p,surface,ink=self.colors(); self.header(self.container,"Crear tarea",self.show_home); body=tk.Frame(self.container,bg=p); body.pack(fill="both",expand=True,padx=34,pady=22); tk.Label(body,text="Elige una actividad",bg=p,fg=ink,font=("Segoe UI",24,"bold")).pack(anchor="w",pady=(0,14)); counts=self.db.counts()
        for category in CATEGORIES:
            tk.Button(body,text=f"{ICONS[category]}   {category}\n     {counts.get(category,0)} tareas",command=lambda c=category:self.show_task_form(c),bg=s,fg=ink,anchor="w",justify="left",font=("Segoe UI",14,"bold"),border=0,padx=18,pady=15).pack(fill="x",pady=8)

    def show_task_form(self,category,task=None):
        self.clear(); a,s,m,p,surface,ink=self.colors(); self.header(self.container,"Editar tarea" if task else "Crear tarea",self.show_categories); body=tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True,padx=30,pady=14)
        selected=tk.StringVar(value=(task["start_date"] if task else self.day.isoformat())); self.month_grid(body,date.fromisoformat(selected.get()),lambda d:selected.set(d.isoformat()))
        category_ink = "#ffffff" if self.dark else ink
        tk.Label(body,text=f"{ICONS[category]}  {category}",bg=s,fg=category_ink,font=("Segoe UI",16,"bold"),padx=14,pady=12).pack(fill="x",pady=10)
        title=tk.StringVar(value=task["title"] if task else ""); desc=tk.Text(body,height=3,bg=surface,fg=ink,insertbackground=ink); desc.insert("1.0",task["description"] if task else "")
        tk.Label(body,text="Nombre de la tarea *",bg=surface,fg=ink,font=("Segoe UI",10,"bold")).pack(anchor="w",pady=(4,1))
        tk.Entry(body,textvariable=title,bg=surface,fg=ink,insertbackground=ink,font=("Segoe UI",11)).pack(fill="x",pady=(0,7))
        tk.Label(body,text="Descripción (opcional)",bg=surface,fg=ink,font=("Segoe UI",10,"bold")).pack(anchor="w",pady=(0,1))
        desc.pack(fill="x",pady=(0,5))
        advanced=tk.LabelFrame(body,text="Repetición, horas y fecha de fin",bg=surface,fg=ink,padx=8,pady=8); advanced.pack(fill="x",pady=8); weekdays=[]
        row=tk.Frame(advanced,bg=surface); row.pack(); old=(task["weekdays"].split(",") if task else [])
        for i,name in enumerate(WEEKDAYS):
            var=tk.BooleanVar(value=str(i) in old); weekdays.append(var); tk.Checkbutton(row,text=name,variable=var,bg=surface,fg=ink,selectcolor=surface).pack(side="left")
        interval=tk.IntVar(value=task["interval_days"] if task else 0); tk.Label(advanced,text="Cada (días, 0=no usar)",bg=surface,fg=ink).pack(anchor="w"); tk.Spinbox(advanced,from_=0,to=3650,textvariable=interval).pack(anchor="w")
        end=tk.StringVar(value=task["end_date"] if task else ""); tk.Label(advanced,text="Fecha de fin (AAAA-MM-DD, opcional)",bg=surface,fg=ink).pack(anchor="w"); tk.Entry(advanced,textvariable=end,bg=surface,fg=ink).pack(fill="x")
        hours=tk.Frame(advanced,bg=surface); hours.pack(fill="x",pady=(8,0)); tk.Label(hours,text="Desde",bg=surface,fg=ink).pack(side="left")
        start_time=tk.StringVar(value=task["start_time"] if task else ""); tk.Entry(hours,textvariable=start_time,width=9,bg=surface,fg=ink,insertbackground=ink).pack(side="left",padx=(7,18))
        tk.Label(hours,text="Hasta",bg=surface,fg=ink).pack(side="left"); end_time=tk.StringVar(value=task["end_time"] if task else ""); tk.Entry(hours,textvariable=end_time,width=9,bg=surface,fg=ink,insertbackground=ink).pack(side="left",padx=7)
        def save():
            if not title.get().strip(): return messagebox.showwarning(APP,"Escribe un nombre.")
            chosen=[i for i,v in enumerate(weekdays) if v.get()]
            try: start=date.fromisoformat(selected.get()); finish=date.fromisoformat(end.get()) if end.get() else None
            except ValueError: return messagebox.showwarning(APP,"Revisa las fechas.")
            for value in (start_time.get().strip(), end_time.get().strip()):
                if value:
                    try: datetime.strptime(value, "%H:%M")
                    except ValueError: return messagebox.showwarning(APP,"Las horas deben tener formato HH:MM.")
            if finish and finish<start:return messagebox.showwarning(APP,"La fecha de fin debe ser posterior.")
            self.db.save_task({"title":title.get(),"description":desc.get("1.0","end"),"category":category,"weekdays":chosen,"interval":interval.get(),"start":start,"end":finish,"start_time":start_time.get().strip(),"end_time":end_time.get().strip()},task["id"] if task else None); self.day=start; self.show_home()
        ttk.Button(body,text="Guardar tarea",style="Accent.TButton",command=save).pack(fill="x",pady=8)

    def month_grid(self,parent,shown,choose,navigate=None):
        a,s,m,p,surface,ink=self.colors(); box=tk.Frame(parent,bg=surface); box.pack(fill="x")
        nav=tk.Frame(box,bg=surface); nav.pack(fill="x")
        if navigate: tk.Button(nav,text="‹",command=lambda:navigate(-1),bg=s,fg=ink,border=0,font=("Segoe UI",18,"bold"),width=3).pack(side="left")
        tk.Label(nav,text=shown.strftime("%B %Y").capitalize(),bg=surface,fg=ink,font=("Segoe UI",15,"bold")).pack(side="left",expand=True)
        if navigate: tk.Button(nav,text="›",command=lambda:navigate(1),bg=s,fg=ink,border=0,font=("Segoe UI",18,"bold"),width=3).pack(side="right")
        grid=tk.Frame(box,bg=surface); grid.pack()
        for col,name in enumerate(WEEKDAYS):tk.Label(grid,text=name,bg=surface,fg=m,width=5).grid(row=0,column=col)
        for row,week in enumerate(calendar.Calendar(0).monthdatescalendar(shown.year,shown.month),1):
            for col,current in enumerate(week): tk.Button(grid,text=str(current.day),command=lambda d=current:choose(d),bg=a if current==shown else s,fg="white" if current==shown else ink,border=0,width=4).grid(row=row,column=col,padx=2,pady=2)

    def show_calendar(self):
        self.clear(); _,_,_,p,surface,ink=self.colors(); self.header(self.container,"Calendario",self.show_home); body=tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True,padx=30,pady=20)
        def move(offset):
            month=self.calendar_month.month + offset; year=self.calendar_month.year
            if month == 0: month,year=12,year-1
            elif month == 13: month,year=1,year+1
            self.calendar_month=date(year,month,1); self.show_calendar()
        self.month_grid(body,self.calendar_month,lambda d:self.set_day(d),move)
        tk.Label(body,text="Selecciona un día para ver y completar sus tareas.",bg=surface,fg=ink).pack(pady=18)

    def show_history(self):
        self.clear(); _,s,m,p,surface,ink=self.colors(); self.header(self.container,"Historial",self.show_home)
        body=tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True,padx=28,pady=20)
        tk.Label(body,text="Historial de cumplimiento",bg=surface,fg=ink,font=("Segoe UI",20,"bold")).pack(anchor="w",pady=(0,12))
        history=self.db.history()
        if not history: tk.Label(body,text="Aún no hay tareas completadas.",bg=surface,fg=m,font=("Segoe UI",12)).pack(pady=35)
        for item in history: tk.Label(body,text=f"✓  {item['day']}  ·  {item['title']}",bg=s,fg=ink,anchor="w",padx=14,pady=10).pack(fill="x",pady=4)

    def show_pomodoro(self):
        self.clear(); _,s,m,p,surface,ink=self.colors(); self.header(self.container,"Pomodoro",self.show_home)
        body=tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True,padx=30,pady=20)
        tk.Label(body,text="Enfócate a tu ritmo",bg=surface,fg=ink,font=("Segoe UI",20,"bold")).pack(anchor="w",pady=(0,12))
        tk.Label(body,text="Tarea asociada (opcional)",bg=surface,fg=ink,font=("Segoe UI",10,"bold")).pack(anchor="w")
        names=["Sin tarea asociada"]+[row[0] for row in self.db.conn.execute("SELECT title FROM tasks WHERE active=1 ORDER BY title")]; choice=tk.StringVar(value=names[0]); ttk.Combobox(body,textvariable=choice,values=names,state="readonly").pack(fill="x",pady=(3,8)); custom=tk.StringVar(); tk.Entry(body,textvariable=custom,bg=surface,fg=ink,insertbackground=ink).pack(fill="x",pady=(0,10))
        work,rest,cycles=tk.IntVar(value=25),tk.IntVar(value=5),tk.IntVar(value=4)
        for label,var,limit in (("Trabajo (min)",work,180),("Descanso (min)",rest,90),("Ciclos",cycles,12)):
            row=tk.Frame(body,bg=surface); row.pack(fill="x",pady=5); tk.Label(row,text=label,bg=surface,fg=ink).pack(side="left"); tk.Spinbox(row,from_=1,to=limit,textvariable=var,width=7).pack(side="right")
        status=tk.Label(body,text="Listo para comenzar",bg=surface,fg=ink,font=("Segoe UI",16,"bold")); status.pack(pady=18); state={"cycle":1,"break":False,"left":0,"title":""}
        def tick():
            state["left"]-=1; mins,secs=divmod(max(state["left"],0),60); status.config(text=f"{mins:02d}:{secs:02d} · ciclo {state['cycle']}/{cycles.get()}")
            if state["left"]>0: self.after(1000,tick); return
            if state["break"]: state["break"]=False; state["cycle"]+=1
            elif state["cycle"]>=cycles.get(): self.db.save_pomodoro(state["title"],work.get(),rest.get(),cycles.get()); status.config(text="¡Pomodoro completado!"); return
            else: state["break"]=True
            state["left"]=(rest.get() if state["break"] else work.get())*60; self.after(1000,tick)
        def start():
            state.update(cycle=1,break_=False); state["break"]=False; state["title"]=custom.get().strip() or (choice.get() if choice.get()!=names[0] else f"Ciclo Pomodoro {self.db.pomodoro_number()}"); state["left"]=work.get()*60; tick()
        ttk.Button(body,text="Iniciar",style="Accent.TButton",command=start).pack(fill="x",pady=10)

    def show_appearance(self):
        self.clear(); _,s,m,p,surface,ink=self.colors(); self.header(self.container,"Apariencia",self.show_home)
        body=tk.Frame(self.container,bg=surface); body.pack(fill="both",expand=True,padx=30,pady=18)
        tk.Label(body,text="Elige tu paleta",bg=surface,fg=ink,font=("Segoe UI",20,"bold")).pack(anchor="w",pady=(0,8))
        def select_palette(name):
            self.palette_name=name; self.db.set_setting("palette",name); self.apply_theme(); self.show_appearance()
        for name in PALETTES: tk.Button(body,text=name,command=lambda n=name:select_palette(n),bg=s if name != self.palette_name else self.colors()[0],fg=ink if name != self.palette_name else "white",activebackground=s,activeforeground=ink,border=0,highlightthickness=0,font=("Segoe UI",10,"bold"),pady=8).pack(fill="x",pady=3)
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
        tk.Button(body,text="Mostrar widget de pendientes",command=self.show_mini_widget,bg=s,fg=ink,activebackground=s,activeforeground=ink,border=0,highlightthickness=0,font=("Segoe UI",10,"bold"),pady=9).pack(fill="x",pady=(13,4))

    def show_mini_widget(self):
        if self.mini_widget and self.mini_widget.winfo_exists():
            self.mini_widget.deiconify(); self.mini_widget.lift(); self.update_mini_widget(); return
        a,s,m,p,surface,ink = self.colors()
        widget=tk.Toplevel(self)
        self.mini_widget=widget
        widget.title("Pendientes de Tareitas")
        widget.attributes("-topmost", True)
        widget.resizable(False,False)
        width,height=300,72
        widget.geometry(f"{width}x{height}+{max(widget.winfo_screenwidth()-width-28,0)}+{42}")
        widget.configure(bg=a)
        content=tk.Frame(widget,bg=a); content.pack(fill="both",expand=True,padx=12,pady=8)
        self.mini_text=tk.Label(content,bg=a,fg="white",font=("Segoe UI",11,"bold"),anchor="w")
        self.mini_text.pack(side="left",fill="both",expand=True)
        tk.Button(content,text="×",command=self.close_mini_widget,bg=a,fg="white",activebackground=a,activeforeground="white",border=0,highlightthickness=0,font=("Segoe UI",16),cursor="hand2").pack(side="right")
        widget.protocol("WM_DELETE_WINDOW",self.close_mini_widget)
        self.update_mini_widget()

    def close_mini_widget(self):
        if self.mini_widget and self.mini_widget.winfo_exists(): self.mini_widget.destroy()
        self.mini_widget=None

    def update_mini_widget(self):
        if not self.mini_widget or not self.mini_widget.winfo_exists(): return
        pending=sum(not self.db.completed(task["id"],date.today()) for task in self.db.due(date.today()))
        plural="tarea pendiente" if pending == 1 else "tareas pendientes"
        self.mini_text.config(text=f"Tareitas  ·  {pending} {plural} hoy")

    def pending_notice(self):
        pending=[t for t in self.db.due(date.today()) if not self.db.completed(t["id"],date.today())]
        if pending: messagebox.showinfo(APP,f"Tienes {len(pending)} tarea(s) pendiente(s).")
        self.after(self.notice_minutes*60_000,self.pending_notice)


if __name__ == "__main__":
    Tareitas().mainloop()
