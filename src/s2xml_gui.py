"""
S2XML Compiler — Sims 2 Mod Compiler
A proper Windows desktop application for compiling XML mod files into .package files.
"""
import sys
import os
import threading
import queue
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

# Handle both normal execution and PyInstaller bundled exe
# When frozen, PyInstaller extracts bundled files to sys._MEIPASS
if getattr(sys, 'frozen', False):
    HERE = Path(sys._MEIPASS)
else:
    HERE = Path(__file__).parent.resolve()

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont

# ── Palette ───────────────────────────────────────────────────────────────────
C = {
    "bg":       "#0f1117",
    "surface":  "#1a1d27",
    "panel":    "#22263a",
    "border":   "#2e3250",
    "accent":   "#c96b3f",      # warm orange-red, like Sims 2 era
    "accent2":  "#3f6bc9",      # blue
    "success":  "#4aaa78",
    "warn":     "#d4a843",
    "error":    "#c94a4a",
    "fg":       "#e8e8ec",
    "fg2":      "#9399b0",
    "fg3":      "#5a6080",
    "select":   "#2e3a5a",
    "hover":    "#2a2f45",
    "entry_bg": "#13151f",
}

TYPE_COLORS = {
    "bhav": "#4aaa78",
    "str":  "#64b5f6",
    "trcn": "#d4a843",
    "tprp": "#ce93d8",
    "objf": "#ff8a65",
    "glob": "#80cbc4",
    "objd": "#a5d6a7",
    "ttab": "#ffcc02",
    "bcon": "#ffab40",
    "ctss": "#80deea",
}

# ── Fonts (set after Tk init) ─────────────────────────────────────────────────
F_TITLE  = None
F_BODY   = None
F_MONO   = None
F_SMALL  = None
F_BOLD   = None


def init_fonts():
    global F_TITLE, F_BODY, F_MONO, F_SMALL, F_BOLD
    F_TITLE = ("Segoe UI", 13, "bold")
    F_BODY  = ("Segoe UI", 9)
    F_SMALL = ("Segoe UI", 8)
    F_BOLD  = ("Segoe UI", 9, "bold")
    F_MONO  = ("Consolas", 9)


# ── Reusable widget helpers ───────────────────────────────────────────────────

def styled_btn(parent, text, cmd, accent=False, danger=False, small=False):
    bg = C["accent"] if accent else (C["error"] if danger else C["panel"])
    fg = C["fg"]
    pad_x = 12 if small else 18
    pad_y = 5  if small else 8
    fnt = F_SMALL if small else F_BOLD

    b = tk.Button(
        parent, text=text, command=cmd,
        bg=bg, fg=fg,
        activebackground=C["accent"] if accent else C["hover"],
        activeforeground=C["fg"],
        relief="flat", bd=0, cursor="hand2",
        font=fnt, padx=pad_x, pady=pad_y,
    )
    def on_enter(e): b.config(bg=C["accent"] if accent else C["hover"])
    def on_leave(e): b.config(bg=bg)
    b.bind("<Enter>", on_enter)
    b.bind("<Leave>", on_leave)
    return b


def section_label(parent, text):
    return tk.Label(
        parent, text=text.upper(),
        bg=parent["bg"] if "bg" in parent.keys() else C["bg"],
        fg=C["fg3"], font=("Segoe UI", 7, "bold"),
        anchor="w", padx=2,
    )


def divider(parent):
    return tk.Frame(parent, bg=C["border"], height=1)


# ── Log pane ──────────────────────────────────────────────────────────────────

class LogPane(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["surface"], **kw)

        self._text = tk.Text(
            self,
            bg=C["surface"], fg=C["fg"],
            insertbackground=C["fg"],
            font=F_MONO, relief="flat", bd=0,
            wrap="word", state="disabled",
            selectbackground=C["select"],
            pady=4, padx=8,
        )
        sb = tk.Scrollbar(self, orient="vertical",
                          command=self._text.yview,
                          bg=C["panel"], troughcolor=C["surface"],
                          relief="flat", bd=0, width=10)
        self._text.configure(yscrollcommand=sb.set)

        self._text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._text.tag_config("ok",      foreground=C["success"])
        self._text.tag_config("warn",    foreground=C["warn"])
        self._text.tag_config("error",   foreground=C["error"])
        self._text.tag_config("dim",     foreground=C["fg2"])
        self._text.tag_config("dimmer",  foreground=C["fg3"])
        self._text.tag_config("accent",  foreground=C["accent"])
        self._text.tag_config("heading", foreground=C["accent"],
                               font=("Consolas", 10, "bold"))
        self._text.tag_config("blue",    foreground="#64b5f6")
        for ext, col in TYPE_COLORS.items():
            self._text.tag_config(f"type_{ext}", foreground=col)

    def clear(self):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")

    def append(self, line: str, tag: str = ""):
        self._text.configure(state="normal")
        if not tag:
            lo = line.lower()
            if any(x in line for x in ("✓", "identical")):  tag = "ok"
            elif any(x in lo for x in ("error", "✗", "blocked")): tag = "error"
            elif any(x in lo for x in ("warn", "⚠")):        tag = "warn"
            elif line.startswith(("  →", "  +")):             tag = "dim"
        self._text.insert("end", line + "\n", tag)
        self._text.see("end")
        self._text.configure(state="disabled")

    def heading(self, line):
        self.append(line, "heading")

    def write(self, s):
        """Allow use as sys.stdout redirect."""
        for line in s.rstrip("\n").split("\n"):
            self.append(line)


# ── File list ─────────────────────────────────────────────────────────────────

class FileList(tk.Frame):
    def __init__(self, parent, on_change=None, **kw):
        super().__init__(parent, bg=C["surface"], **kw)
        self._paths: list[Path] = []
        self._on_change = on_change

        # Canvas + scrollbar for custom rows
        self._canvas = tk.Canvas(self, bg=C["surface"], highlightthickness=0,
                                  bd=0)
        self._sb = tk.Scrollbar(self, orient="vertical",
                                 command=self._canvas.yview,
                                 bg=C["panel"], troughcolor=C["surface"],
                                 relief="flat", bd=0, width=10)
        self._canvas.configure(yscrollcommand=self._sb.set)
        self._inner = tk.Frame(self._canvas, bg=C["surface"])
        self._win = self._canvas.create_window((0, 0), window=self._inner,
                                                anchor="nw")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._sb.pack(side="right", fill="y")

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self._row_frames: list[tk.Frame] = []
        self._selected: set[int] = set()

        self._render()

    def _on_inner_configure(self, e):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._win, width=e.width)

    def _on_mousewheel(self, e):
        self._canvas.yview_scroll(int(-1*(e.delta/120)), "units")

    def add(self, paths: list[Path]):
        added = 0
        for p in paths:
            if p not in self._paths:
                self._paths.append(p)
                added += 1
        if added:
            self._render()
            if self._on_change:
                self._on_change()

    def remove_selected(self):
        keep = [p for i, p in enumerate(self._paths) if i not in self._selected]
        self._paths = keep
        self._selected.clear()
        self._render()
        if self._on_change:
            self._on_change()

    def clear(self):
        self._paths.clear()
        self._selected.clear()
        self._render()
        if self._on_change:
            self._on_change()

    def get_paths(self) -> list[Path]:
        return list(self._paths)

    def count(self) -> int:
        return len(self._paths)

    def _get_type_tag(self, name: str) -> str:
        name = name.lower()
        for ext in TYPE_COLORS:
            if name.endswith(f".{ext}.xml"):
                return ext
        return ""

    def _render(self):
        for f in self._row_frames:
            f.destroy()
        self._row_frames.clear()

        if not self._paths:
            placeholder = tk.Label(
                self._inner,
                text="No files yet — click Add Files or Add Folder",
                bg=C["surface"], fg=C["fg3"],
                font=F_SMALL, pady=20,
            )
            placeholder.pack(fill="x")
            self._row_frames.append(placeholder)
            return

        for i, path in enumerate(self._paths):
            is_sel = i in self._selected
            row_bg = C["select"] if is_sel else C["surface"]

            row = tk.Frame(self._inner, bg=row_bg, cursor="hand2")
            row.pack(fill="x", pady=1)

            # Type badge
            ext = self._get_type_tag(path.name)
            badge_color = TYPE_COLORS.get(ext, C["fg3"])
            badge = tk.Label(row, text=(ext.upper() if ext else "XML"),
                             bg=badge_color, fg=C["bg"],
                             font=("Segoe UI", 7, "bold"),
                             padx=5, pady=2, width=5)
            badge.pack(side="left", padx=(6, 6), pady=4)

            # Filename
            name_lbl = tk.Label(row, text=path.name,
                                 bg=row_bg, fg=C["fg"],
                                 font=F_BODY, anchor="w")
            name_lbl.pack(side="left", fill="x", expand=True)

            # Parent folder (dim)
            dir_lbl = tk.Label(row, text=str(path.parent)[-40:],
                                bg=row_bg, fg=C["fg3"],
                                font=F_SMALL, anchor="e", padx=8)
            dir_lbl.pack(side="right")

            # Hover / click
            def make_handler(idx, r, nl, dl):
                def enter(e):
                    if idx not in self._selected:
                        r.config(bg=C["hover"])
                        nl.config(bg=C["hover"])
                        dl.config(bg=C["hover"])
                def leave(e):
                    bg = C["select"] if idx in self._selected else C["surface"]
                    r.config(bg=bg); nl.config(bg=bg); dl.config(bg=bg)
                def click(e):
                    if idx in self._selected:
                        self._selected.discard(idx)
                        r.config(bg=C["surface"])
                        nl.config(bg=C["surface"])
                        dl.config(bg=C["surface"])
                    else:
                        self._selected.add(idx)
                        r.config(bg=C["select"])
                        nl.config(bg=C["select"])
                        dl.config(bg=C["select"])
                return enter, leave, click

            enter, leave, click = make_handler(i, row, name_lbl, dir_lbl)
            for w in (row, name_lbl, dir_lbl, badge):
                w.bind("<Enter>", enter)
                w.bind("<Leave>", leave)
                w.bind("<Button-1>", click)

            self._row_frames.append(row)


# ── Main application ──────────────────────────────────────────────────────────

class S2XMLApp(tk.Tk):
    def __init__(self):
        super().__init__()
        init_fonts()

        self.title("S2XML — Sims 2 Mod Compiler")
        self.configure(bg=C["bg"])
        self.geometry("980x680")
        self.minsize(800, 560)

        self._output_path: Path | None = None
        self._log_queue: queue.Queue = queue.Queue()
        self._active_log: LogPane | None = None

        self._setup_styles()
        self._build_ui()
        self._poll_log()

    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook",
                     background=C["bg"],
                     borderwidth=0, tabmargins=0)
        s.configure("TNotebook.Tab",
                     background=C["panel"],
                     foreground=C["fg2"],
                     padding=[20, 9],
                     font=F_BOLD,
                     borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", C["surface"]), ("active", C["hover"])],
              foreground=[("selected", C["fg"]),      ("active", C["fg"])])
        s.configure("TSeparator", background=C["border"])

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Titlebar area ────────────────────────────────────────────────────
        header = tk.Frame(self, bg=C["accent"], height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header,
                 text="S2XML",
                 bg=C["accent"], fg="white",
                 font=("Segoe UI", 16, "bold"),
                 padx=20).pack(side="left", pady=10)

        tk.Label(header,
                 text="Sims 2 Mod Compiler",
                 bg=C["accent"], fg="#cccccc",
                 font=("Segoe UI", 10),
                 padx=0).pack(side="left", pady=10)

        # Status pill (top right)
        self._status_var = tk.StringVar(value="Ready")
        self._status_lbl = tk.Label(header,
                                     textvariable=self._status_var,
                                     bg=C["surface"], fg=C["fg2"],
                                     font=F_SMALL, padx=10, pady=4,
                                     relief="flat")
        self._status_lbl.pack(side="right", padx=16, pady=14)

        # ── Tab notebook ─────────────────────────────────────────────────────
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True)
        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_change)

        self._compile_tab   = self._build_compile_tab()
        self._decompile_tab = self._build_decompile_tab()
        self._diff_tab      = self._build_diff_tab()
        self._opcodes_tab   = self._build_opcodes_tab()

        self._nb.add(self._compile_tab,   text="  Compile  ")
        self._nb.add(self._decompile_tab, text="  Decompile  ")
        self._nb.add(self._diff_tab,      text="  Diff  ")
        self._nb.add(self._opcodes_tab,   text="  Opcodes  ")

        self._active_log = self._compile_log

    def _on_tab_change(self, e):
        idx = self._nb.index(self._nb.select())
        logs = [self._compile_log, self._decompile_log,
                self._diff_log, self._opcodes_log]
        self._active_log = logs[idx] if idx < len(logs) else self._compile_log

        if idx == 3:  # Opcodes tab — populate on first visit
            if not self._opcodes_log._text.get("1.0", "2.0").strip():
                self._populate_opcodes()

    # ── Compile tab ───────────────────────────────────────────────────────────

    def _build_compile_tab(self):
        outer = tk.Frame(self._nb, bg=C["bg"])

        # ── Left sidebar ─────────────────────────────────────────────────────
        sidebar = tk.Frame(outer, bg=C["surface"], width=300)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Sidebar header
        sh = tk.Frame(sidebar, bg=C["panel"], height=44)
        sh.pack(fill="x")
        sh.pack_propagate(False)
        tk.Label(sh, text="Resource Files",
                 bg=C["panel"], fg=C["fg"],
                 font=F_BOLD, padx=14).pack(side="left", pady=10)

        # File count badge
        self._file_count_var = tk.StringVar(value="0 files")
        tk.Label(sh, textvariable=self._file_count_var,
                 bg=C["panel"], fg=C["fg3"],
                 font=F_SMALL, padx=8).pack(side="right", pady=10)

        # File list
        self._file_list = FileList(sidebar,
                                    on_change=self._on_files_changed)
        self._file_list.pack(fill="both", expand=True, pady=0)

        divider(sidebar).pack(fill="x")

        # Add/remove buttons
        btn_area = tk.Frame(sidebar, bg=C["surface"], pady=10)
        btn_area.pack(fill="x")

        row1 = tk.Frame(btn_area, bg=C["surface"])
        row1.pack(fill="x", padx=10, pady=(0, 6))
        styled_btn(row1, "＋  Add Files",   self._add_files,  accent=True).pack(side="left", fill="x", expand=True, padx=(0, 5))
        styled_btn(row1, "＋  Add Folder",  self._add_folder, accent=True).pack(side="right", fill="x", expand=True)

        row2 = tk.Frame(btn_area, bg=C["surface"])
        row2.pack(fill="x", padx=10)
        styled_btn(row2, "✕  Remove Selected", self._remove_selected, small=True).pack(side="left", padx=(0, 5))
        styled_btn(row2, "Clear All", self._clear_all, small=True).pack(side="left")

        divider(sidebar).pack(fill="x", pady=(8, 0))

        # Output path section
        out_area = tk.Frame(sidebar, bg=C["surface"], pady=10)
        out_area.pack(fill="x")

        section_label(out_area, "Output .package").pack(fill="x", padx=12, pady=(0, 4))

        out_row = tk.Frame(out_area, bg=C["surface"])
        out_row.pack(fill="x", padx=10)

        self._out_entry_var = tk.StringVar(value="Auto-named")
        out_entry = tk.Entry(out_row, textvariable=self._out_entry_var,
                             bg=C["entry_bg"], fg=C["fg2"],
                             insertbackground=C["fg"],
                             relief="flat", font=F_SMALL,
                             state="readonly")
        out_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 5))
        styled_btn(out_row, "…", self._choose_output, small=True).pack(side="right")

        divider(sidebar).pack(fill="x", pady=(8, 0))

        # Lint checkbox + Compile button
        action_area = tk.Frame(sidebar, bg=C["surface"], pady=12)
        action_area.pack(fill="x")

        self._lint_only = tk.BooleanVar(value=False)
        ck = tk.Checkbutton(action_area,
                             text="  Lint only (validate, no output)",
                             variable=self._lint_only,
                             bg=C["surface"], fg=C["fg2"],
                             selectcolor=C["panel"],
                             activebackground=C["surface"],
                             activeforeground=C["fg"],
                             font=F_SMALL, cursor="hand2")
        ck.pack(anchor="w", padx=12, pady=(0, 10))

        self._compile_btn = styled_btn(
            action_area, "▶   Compile Package",
            self._run_compile, accent=True,
        )
        self._compile_btn.pack(fill="x", padx=10)
        self._compile_btn.configure(pady=12, font=("Segoe UI", 10, "bold"))

        # ── Right: output log ─────────────────────────────────────────────────
        right = tk.Frame(outer, bg=C["bg"])
        right.pack(side="right", fill="both", expand=True)

        log_header = tk.Frame(right, bg=C["bg"], height=44)
        log_header.pack(fill="x")
        log_header.pack_propagate(False)
        tk.Label(log_header, text="Compiler Output",
                 bg=C["bg"], fg=C["fg"],
                 font=F_BOLD, padx=14).pack(side="left", pady=12)
        styled_btn(log_header, "Clear", lambda: self._compile_log.clear(),
                   small=True).pack(side="right", padx=10, pady=10)

        self._compile_log = LogPane(right)
        self._compile_log.pack(fill="both", expand=True, padx=0, pady=0)

        self._compile_log.heading("S2XML Compiler ready.")
        self._compile_log.append(
            "Add your XML files on the left, then click Compile Package.", "dim")
        self._compile_log.append("")
        self._compile_log.append(
            "File types:  .bhav.xml  .str.xml  .trcn.xml  "
            ".tprp.xml  .objf.xml  .glob.xml  .objd.xml  .ttab.xml  .bcon.xml", "dimmer")

        return outer

    # ── Decompile tab ─────────────────────────────────────────────────────────

    def _build_decompile_tab(self):
        outer = tk.Frame(self._nb, bg=C["bg"])

        # ── Sidebar ───────────────────────────────────────────────────────────
        sidebar = tk.Frame(outer, bg=C["surface"], width=300)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        sh = tk.Frame(sidebar, bg=C["panel"], height=44)
        sh.pack(fill="x")
        sh.pack_propagate(False)
        tk.Label(sh, text="Decompile .package → XML",
                 bg=C["panel"], fg=C["fg"],
                 font=F_BOLD, padx=14).pack(side="left", pady=10)

        body = tk.Frame(sidebar, bg=C["surface"])
        body.pack(fill="both", expand=True, padx=12, pady=12)

        # Input
        section_label(body, "Input .package file").pack(fill="x", pady=(0, 4))
        in_row = tk.Frame(body, bg=C["surface"])
        in_row.pack(fill="x", pady=(0, 12))
        self._dec_in = tk.StringVar()
        tk.Entry(in_row, textvariable=self._dec_in,
                 bg=C["entry_bg"], fg=C["fg"],
                 insertbackground=C["fg"],
                 relief="flat", font=F_SMALL).pack(
                     side="left", fill="x", expand=True, ipady=6, padx=(0, 5))
        styled_btn(in_row, "Browse…", self._browse_pkg_in, small=True).pack(side="right")

        # Output folder
        section_label(body, "Output folder (for XML files)").pack(fill="x", pady=(0, 4))
        out_row = tk.Frame(body, bg=C["surface"])
        out_row.pack(fill="x", pady=(0, 16))
        self._dec_out = tk.StringVar(value="Same folder as .package")
        tk.Entry(out_row, textvariable=self._dec_out,
                 bg=C["entry_bg"], fg=C["fg2"],
                 insertbackground=C["fg"],
                 relief="flat", font=F_SMALL).pack(
                     side="left", fill="x", expand=True, ipady=6, padx=(0, 5))
        styled_btn(out_row, "Browse…", self._browse_dec_out, small=True).pack(side="right")

        divider(body).pack(fill="x", pady=(0, 12))

        self._dec_info_only = tk.BooleanVar(value=False)
        tk.Checkbutton(body,
                        text="  List resources only (don't write files)",
                        variable=self._dec_info_only,
                        bg=C["surface"], fg=C["fg2"],
                        selectcolor=C["panel"],
                        activebackground=C["surface"],
                        activeforeground=C["fg"],
                        font=F_SMALL, cursor="hand2").pack(anchor="w", pady=(0, 12))

        styled_btn(body, "▶   Decompile",
                   self._run_decompile, accent=True).pack(
                       fill="x", pady=(4, 0), ipady=6)

        # Hint
        tk.Label(body,
                 text="Extracts every resource from a .package into\neditable XML files.",
                 bg=C["surface"], fg=C["fg3"],
                 font=F_SMALL, justify="left", anchor="w").pack(
                     fill="x", pady=(16, 0))

        # ── Log ──────────────────────────────────────────────────────────────
        right = tk.Frame(outer, bg=C["bg"])
        right.pack(side="right", fill="both", expand=True)

        log_header = tk.Frame(right, bg=C["bg"], height=44)
        log_header.pack(fill="x")
        log_header.pack_propagate(False)
        tk.Label(log_header, text="Decompiler Output",
                 bg=C["bg"], fg=C["fg"],
                 font=F_BOLD, padx=14).pack(side="left", pady=12)
        styled_btn(log_header, "Clear",
                   lambda: self._decompile_log.clear(),
                   small=True).pack(side="right", padx=10, pady=10)

        self._decompile_log = LogPane(right)
        self._decompile_log.pack(fill="both", expand=True)

        return outer

    # ── Diff tab ──────────────────────────────────────────────────────────────

    def _build_diff_tab(self):
        outer = tk.Frame(self._nb, bg=C["bg"])

        sidebar = tk.Frame(outer, bg=C["surface"], width=300)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        sh = tk.Frame(sidebar, bg=C["panel"], height=44)
        sh.pack(fill="x")
        sh.pack_propagate(False)
        tk.Label(sh, text="Compare Packages",
                 bg=C["panel"], fg=C["fg"],
                 font=F_BOLD, padx=14).pack(side="left", pady=10)

        body = tk.Frame(sidebar, bg=C["surface"])
        body.pack(fill="both", expand=True, padx=12, pady=12)

        section_label(body, "Package A  (original)").pack(fill="x", pady=(0, 4))
        row_a = tk.Frame(body, bg=C["surface"])
        row_a.pack(fill="x", pady=(0, 12))
        self._diff_a = tk.StringVar()
        tk.Entry(row_a, textvariable=self._diff_a,
                 bg=C["entry_bg"], fg=C["fg"],
                 insertbackground=C["fg"],
                 relief="flat", font=F_SMALL).pack(
                     side="left", fill="x", expand=True, ipady=6, padx=(0, 5))
        styled_btn(row_a, "Browse…",
                   lambda: self._browse_pkg(self._diff_a), small=True).pack(side="right")

        section_label(body, "Package B  (modified)").pack(fill="x", pady=(0, 4))
        row_b = tk.Frame(body, bg=C["surface"])
        row_b.pack(fill="x", pady=(0, 16))
        self._diff_b = tk.StringVar()
        tk.Entry(row_b, textvariable=self._diff_b,
                 bg=C["entry_bg"], fg=C["fg"],
                 insertbackground=C["fg"],
                 relief="flat", font=F_SMALL).pack(
                     side="left", fill="x", expand=True, ipady=6, padx=(0, 5))
        styled_btn(row_b, "Browse…",
                   lambda: self._browse_pkg(self._diff_b), small=True).pack(side="right")

        divider(body).pack(fill="x", pady=(0, 12))

        self._diff_brief = tk.BooleanVar(value=False)
        tk.Checkbutton(body,
                        text="  Brief summary only",
                        variable=self._diff_brief,
                        bg=C["surface"], fg=C["fg2"],
                        selectcolor=C["panel"],
                        activebackground=C["surface"],
                        font=F_SMALL, cursor="hand2").pack(anchor="w", pady=(0, 12))

        styled_btn(body, "▶   Compare",
                   self._run_diff, accent=True).pack(
                       fill="x", pady=(4, 0), ipady=6)

        right = tk.Frame(outer, bg=C["bg"])
        right.pack(side="right", fill="both", expand=True)

        log_header = tk.Frame(right, bg=C["bg"], height=44)
        log_header.pack(fill="x")
        log_header.pack_propagate(False)
        tk.Label(log_header, text="Diff Output",
                 bg=C["bg"], fg=C["fg"],
                 font=F_BOLD, padx=14).pack(side="left", pady=12)
        styled_btn(log_header, "Clear",
                   lambda: self._diff_log.clear(),
                   small=True).pack(side="right", padx=10, pady=10)

        self._diff_log = LogPane(right)
        self._diff_log.pack(fill="both", expand=True)

        return outer

    # ── Opcodes tab ───────────────────────────────────────────────────────────

    def _build_opcodes_tab(self):
        outer = tk.Frame(self._nb, bg=C["bg"])

        # Search bar
        bar = tk.Frame(outer, bg=C["panel"], height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="Search opcodes:",
                 bg=C["panel"], fg=C["fg2"],
                 font=F_BODY, padx=14).pack(side="left", pady=13)
        self._op_query = tk.StringVar()
        self._op_query.trace_add("write", lambda *_: self._populate_opcodes())
        tk.Entry(bar, textvariable=self._op_query,
                 bg=C["entry_bg"], fg=C["fg"],
                 insertbackground=C["fg"],
                 relief="flat", font=F_BODY, width=28).pack(
                     side="left", ipady=7, pady=10)
        tk.Label(bar,
                 text="Type an opcode (0x0025) or keyword (relationship, animate…)",
                 bg=C["panel"], fg=C["fg3"],
                 font=F_SMALL, padx=14).pack(side="left")

        self._opcodes_log = LogPane(outer)
        self._opcodes_log.pack(fill="both", expand=True)

        return outer

    def _populate_opcodes(self):
        try:
            from opcodes import OPCODES
        except ImportError:
            self._opcodes_log.append("opcodes.py not found.", "error")
            return

        query = self._op_query.get().strip().lower()
        self._opcodes_log.clear()
        count = 0

        for code in sorted(OPCODES):
            info  = OPCODES[code]
            name  = info.get("name", "")
            notes = info.get("notes", "")
            ops_text = " ".join(o for o in info.get("operands", []) if o)

            if query:
                if not (query in name.lower() or
                        query in notes.lower() or
                        query in ops_text.lower() or
                        query in f"0x{code:04x}"):
                    continue

            self._opcodes_log.append(f"  0x{code:04X}  {name}", "ok")
            if notes:
                self._opcodes_log.append(f"           {notes}", "dimmer")
            for i, lbl in enumerate(info.get("operands", [])):
                if lbl:
                    self._opcodes_log.append(f"           op{i}: {lbl}", "dim")
            self._opcodes_log.append("")
            count += 1

        self._opcodes_log.append(
            f"  {'All' if not query else count} opcode(s)" +
            (f" matching '{query}'" if query else ""), "dimmer")

    # ── File operations ───────────────────────────────────────────────────────

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select XML resource files",
            filetypes=[
                ("XML files", "*.xml"),
                ("All files", "*.*"),
            ],
            parent=self,
        )
        if paths:
            self._file_list.add([Path(p) for p in paths])

    def _add_folder(self):
        folder = filedialog.askdirectory(
            title="Select folder containing XML files",
            parent=self,
        )
        if folder:
            xmls = sorted(Path(folder).glob("*.xml"))
            if not xmls:
                messagebox.showinfo("No XML files",
                                    f"No .xml files found in:\n{folder}", parent=self)
            else:
                self._file_list.add(xmls)

    def _remove_selected(self):
        self._file_list.remove_selected()

    def _clear_all(self):
        if self._file_list.count() == 0:
            return
        if messagebox.askyesno("Clear all", "Remove all files from the list?",
                               parent=self):
            self._file_list.clear()

    def _on_files_changed(self):
        n = self._file_list.count()
        self._file_count_var.set(f"{n} file{'s' if n != 1 else ''}")

    def _choose_output(self):
        p = filedialog.asksaveasfilename(
            title="Save .package as…",
            defaultextension=".package",
            filetypes=[("Sims 2 package", "*.package"), ("All files", "*.*")],
            parent=self,
        )
        if p:
            self._output_path = Path(p)
            self._out_entry_var.set(self._output_path.name)

    def _browse_pkg_in(self):
        p = filedialog.askopenfilename(
            title="Open .package file",
            filetypes=[("Sims 2 package", "*.package"), ("All files", "*.*")],
            parent=self,
        )
        if p:
            self._dec_in.set(p)

    def _browse_dec_out(self):
        d = filedialog.askdirectory(title="Select output folder", parent=self)
        if d:
            self._dec_out.set(d)

    def _browse_pkg(self, var: tk.StringVar):
        p = filedialog.askopenfilename(
            title="Select .package",
            filetypes=[("Sims 2 package", "*.package"), ("All files", "*.*")],
            parent=self,
        )
        if p:
            var.set(p)

    # ── Run actions (in background threads) ───────────────────────────────────

    def _set_status(self, text: str, color: str = None):
        self._status_var.set(text)
        self._status_lbl.config(fg=color or C["fg2"])

    def _run_compile(self):
        files = self._file_list.get_paths()
        if not files:
            messagebox.showwarning("No files",
                                   "Add some XML files first.", parent=self)
            return

        out_path = self._output_path
        if not out_path:
            first = files[0]
            name  = first.parent.name or first.stem
            out_path = first.parent / f"{name}.package"

        lint_only = self._lint_only.get()
        self._compile_btn.config(state="disabled", text="Working…")
        self._compile_log.clear()
        self._compile_log.heading(
            f"{'Linting' if lint_only else 'Compiling'}  {len(files)} resource(s)"
            f"  →  {out_path.name}\n")
        self._set_status("Compiling…", C["warn"])

        def task():
            try:
                from xml_parser  import parse_resource_xml, set_global_constants, TYPE_NAMES
                from dbpf_writer import DBPFWriter
                from linter      import lint_resources

                # Pass 1: collect constants
                global_consts = {}
                for xf in files:
                    try:
                        root = ET.parse(str(xf)).getroot()
                        if root.tag.lower() == "trcn":
                            for c in root.findall("constant"):
                                n, v = c.get("name",""), c.get("value","0")
                                if n:
                                    try: global_consts[n] = int(v, 0)
                                    except ValueError: pass
                    except Exception:
                        pass

                if global_consts:
                    set_global_constants(global_consts)
                    self._q(f"  Loaded {len(global_consts)} named constant(s)\n", "dim")

                # Pass 2: parse
                resources, file_names, counts, success = [], [], {}, True
                for xf in files:
                    try:
                        tid, gid, iid, data = parse_resource_xml(str(xf))
                        resources.append((tid, gid, iid, data))
                        file_names.append(xf.name)
                        tname = TYPE_NAMES.get(tid, f"0x{tid:08X}")
                        counts[tname] = counts.get(tname, 0) + 1
                        self._q(f"  + {xf.name:<44} [{tname}]", "dim")
                    except Exception as e:
                        self._q(f"  ✗ {xf.name}: {e}", "error")
                        success = False

                if not resources:
                    self._q("\nNo resources compiled successfully.", "error")
                    self._set_status("Failed", C["error"])
                    return

                # Lint
                self._q("")
                msgs   = lint_resources(resources, file_names)
                errors = [m for m in msgs if m.level == "error"]
                warns  = [m for m in msgs if m.level == "warning"]

                for m in errors: self._q(str(m), "error")
                for m in warns:  self._q(str(m), "warn")
                if not msgs:
                    self._q("  ✓ No lint issues found", "ok")
                else:
                    self._q(f"\n  {len(errors)} error(s)   {len(warns)} warning(s)")

                if errors:
                    self._q(f"\n  Blocked — fix {len(errors)} error(s) before compiling.", "error")
                    self._set_status(f"{len(errors)} lint error(s)", C["error"])
                    return

                if lint_only:
                    summary = "  ".join(f"{n}×{c}" for n, c in sorted(counts.items()))
                    self._q(f"\n  ✓ Lint passed — {len(resources)} resource(s)  [{summary}]", "ok")
                    self._set_status("Lint OK", C["success"])
                    return

                # Write
                writer = DBPFWriter()
                for t, g, i, d in resources:
                    writer.add_resource(t, g, i, d)

                pkg = writer.write_package()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(pkg)

                summary = "  ".join(f"{n}×{c}" for n, c in sorted(counts.items()))
                kb      = len(pkg) / 1024
                self._q(f"\n  ✓  {out_path.name}", "ok")
                self._q(f"     {len(resources)} resource(s)   [{summary}]   {kb:.1f} KB", "dim")
                self._q(f"     Saved to: {out_path}", "dim")
                self._set_status(f"✓ {out_path.name}", C["success"])

                # Offer open folder
                self.after(200, lambda: self._offer_open(out_path.parent))

            except Exception as e:
                import traceback
                self._q(f"\nUnexpected error: {e}", "error")
                self._q(traceback.format_exc(), "error")
                self._set_status("Error", C["error"])
            finally:
                self.after(0, lambda: self._compile_btn.config(
                    state="normal", text="▶   Compile Package"))

        threading.Thread(target=task, daemon=True).start()

    def _run_decompile(self):
        pkg_str = self._dec_in.get().strip()
        if not pkg_str:
            messagebox.showwarning("No file", "Choose a .package file.", parent=self)
            return
        pkg = Path(pkg_str)
        if not pkg.exists():
            messagebox.showerror("Not found", f"File not found:\n{pkg}", parent=self)
            return

        out_str = self._dec_out.get().strip()
        out_dir = Path(out_str) if out_str and "Same folder" not in out_str \
                  else pkg.parent / pkg.stem

        info_only = self._dec_info_only.get()
        self._decompile_log.clear()
        self._decompile_log.heading(
            f"{'Listing' if info_only else 'Decompiling'}  {pkg.name}\n")
        self._set_status("Decompiling…", C["warn"])

        def task():
            try:
                from dbpf_reader    import read_package, TYPE_NAMES, RawResource, DecodedBHAV
                from xml_serializer import write_resource_xml

                resources = read_package(str(pkg))
                self._q(f"  {len(resources)} resource(s) found\n", "dim")

                if info_only:
                    for i, res in enumerate(resources):
                        tname = TYPE_NAMES.get(res.type_id, f"0x{res.type_id:08X}")
                        name  = getattr(res, "name", "") or ""
                        raw   = "  [unsupported]" if isinstance(res, RawResource) else ""
                        self._q(f"  [{i:2d}]  {tname:<6}  "
                                f"inst=0x{res.instance_id:08X}   '{name}'{raw}")
                    self._set_status("Listed", C["success"])
                    return

                out_dir.mkdir(parents=True, exist_ok=True)
                bhav_map = {r.instance_id: r for r in resources
                            if isinstance(r, DecodedBHAV)}
                counts = {}

                for res in resources:
                    tname = TYPE_NAMES.get(res.type_id, f"0x{res.type_id:08X}")
                    try:
                        xp = write_resource_xml(res, out_dir, bhav_map=bhav_map)
                        counts[tname] = counts.get(tname, 0) + 1
                        raw = "  [raw]" if isinstance(res, RawResource) else ""
                        self._q(f"  → {xp.name:<52} [{tname}]{raw}", "dim")
                    except Exception as e:
                        self._q(f"  ✗ {tname} 0x{res.instance_id:08X}: {e}", "error")

                summary = "  ".join(f"{n}×{c}" for n, c in sorted(counts.items()))
                self._q(f"\n  ✓  {sum(counts.values())} file(s) written  [{summary}]", "ok")
                self._q(f"     Output: {out_dir}", "dim")
                self._set_status("✓ Done", C["success"])
                self.after(200, lambda: self._offer_open(out_dir))

            except Exception as e:
                import traceback
                self._q(f"\nError: {e}", "error")
                self._q(traceback.format_exc(), "error")
                self._set_status("Error", C["error"])

        threading.Thread(target=task, daemon=True).start()

    def _run_diff(self):
        a_str = self._diff_a.get().strip()
        b_str = self._diff_b.get().strip()
        if not a_str or not b_str:
            messagebox.showwarning("Missing files",
                                   "Choose both packages.", parent=self)
            return
        pa, pb = Path(a_str), Path(b_str)
        for p in (pa, pb):
            if not p.exists():
                messagebox.showerror("Not found", f"File not found:\n{p}", parent=self)
                return

        self._diff_log.clear()
        self._diff_log.heading(f"Comparing  {pa.name}  vs  {pb.name}\n")
        self._set_status("Comparing…", C["warn"])

        def task():
            try:
                from s2xml_diff import diff_packages
                from io import StringIO
                import contextlib

                buf = StringIO()
                with contextlib.redirect_stdout(buf):
                    diff_packages(pa, pb, brief=self._diff_brief.get())

                for line in buf.getvalue().splitlines():
                    self._q(line)

                self._set_status("Done", C["success"])
            except Exception as e:
                self._q(f"\nError: {e}", "error")
                self._set_status("Error", C["error"])

        threading.Thread(target=task, daemon=True).start()

    # ── Thread-safe log queue ─────────────────────────────────────────────────

    def _q(self, line: str, tag: str = ""):
        self._log_queue.put((line, tag))

    def _poll_log(self):
        log = self._active_log or self._compile_log
        try:
            while True:
                line, tag = self._log_queue.get_nowait()
                if log:
                    log.append(line, tag)
        except queue.Empty:
            pass
        self.after(50, self._poll_log)

    def _offer_open(self, folder: Path):
        if messagebox.askyesno("Done",
                                f"Open output folder in Explorer?\n\n{folder}",
                                parent=self):
            os.startfile(str(folder))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = S2XMLApp()
    app.mainloop()
