"""
S2XML Compiler — Sims 2 Mod Compiler
Full GUI with: Compile, Decompile, Textures, Object Setup, Diff, Opcodes
"""
import sys, os, threading, queue, shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

if getattr(sys, 'frozen', False):
    HERE = Path(sys._MEIPASS)
else:
    HERE = Path(__file__).parent.resolve()
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ── Palette ───────────────────────────────────────────────────────────────────
C = {
    "bg":       "#0f1117",
    "surface":  "#1a1d27",
    "panel":    "#22263a",
    "border":   "#2e3250",
    "accent":   "#c96b3f",
    "accent2":  "#3f6bc9",
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
    "bhav":"#4aaa78","str":"#64b5f6","trcn":"#d4a843","tprp":"#ce93d8",
    "objf":"#ff8a65","glob":"#80cbc4","objd":"#a5d6a7","ttab":"#ffcc02",
    "bcon":"#ffab40","ctss":"#80deea","nref":"#ef9a9a","vers":"#b0bec5",
}

F_TITLE = F_BODY = F_MONO = F_SMALL = F_BOLD = None

def init_fonts():
    global F_TITLE, F_BODY, F_MONO, F_SMALL, F_BOLD
    F_TITLE = ("Segoe UI", 13, "bold")
    F_BODY  = ("Segoe UI", 9)
    F_SMALL = ("Segoe UI", 8)
    F_BOLD  = ("Segoe UI", 9, "bold")
    F_MONO  = ("Consolas", 9)

def styled_btn(parent, text, cmd, accent=False, danger=False, small=False):
    bg  = C["accent"] if accent else (C["error"] if danger else C["panel"])
    pad = (12, 5) if small else (18, 8)
    fnt = F_SMALL if small else F_BOLD
    b = tk.Button(parent, text=text, command=cmd,
                  bg=bg, fg=C["fg"],
                  activebackground=C["accent"], activeforeground=C["fg"],
                  relief="flat", bd=0, cursor="hand2",
                  font=fnt, padx=pad[0], pady=pad[1])
    def on_enter(e): b.config(bg=C["accent"] if accent else C["hover"])
    def on_leave(e): b.config(bg=bg)
    b.bind("<Enter>", on_enter)
    b.bind("<Leave>", on_leave)
    return b

def section_label(parent, text):
    return tk.Label(parent, text=text.upper(),
                    bg=parent["bg"], fg=C["fg3"],
                    font=("Segoe UI", 7, "bold"), anchor="w", padx=2)

def divider(parent):
    return tk.Frame(parent, bg=C["border"], height=1)

def labeled_entry(parent, label, var, browse_cmd=None, readonly=False):
    """Label + entry + optional browse button row."""
    section_label(parent, label).pack(fill="x", pady=(0, 3))
    row = tk.Frame(parent, bg=parent["bg"])
    row.pack(fill="x", pady=(0, 10))
    state = "readonly" if readonly else "normal"
    e = tk.Entry(row, textvariable=var,
                 bg=C["entry_bg"], fg=C["fg2"] if readonly else C["fg"],
                 insertbackground=C["fg"],
                 relief="flat", font=F_SMALL, state=state)
    e.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 5) if browse_cmd else 0)
    if browse_cmd:
        styled_btn(row, "…", browse_cmd, small=True).pack(side="right")
    return e


# ── Log pane ──────────────────────────────────────────────────────────────────
class LogPane(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["surface"], **kw)
        self._text = tk.Text(self, bg=C["surface"], fg=C["fg"],
                             insertbackground=C["fg"], font=F_MONO,
                             relief="flat", bd=0, wrap="word",
                             state="disabled", selectbackground=C["select"],
                             pady=4, padx=8)
        sb = tk.Scrollbar(self, orient="vertical", command=self._text.yview,
                          bg=C["panel"], troughcolor=C["surface"],
                          relief="flat", bd=0, width=10)
        self._text.configure(yscrollcommand=sb.set)
        self._text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for tag, col in [("ok", C["success"]), ("warn", C["warn"]),
                         ("error", C["error"]), ("dim", C["fg2"]),
                         ("dimmer", C["fg3"]), ("accent", C["accent"]),
                         ("heading", C["accent"])]:
            self._text.tag_config(tag, foreground=col)
        self._text.tag_config("heading", font=("Consolas", 10, "bold"))

    def clear(self):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")

    def append(self, line: str, tag: str = ""):
        self._text.configure(state="normal")
        if not tag:
            lo = line.lower()
            if any(x in line for x in ("✓", "identical")): tag = "ok"
            elif any(x in lo for x in ("error","✗","blocked")): tag = "error"
            elif any(x in lo for x in ("warn","⚠")): tag = "warn"
            elif line.startswith(("  →","  +")): tag = "dim"
        self._text.insert("end", line + "\n", tag)
        self._text.see("end")
        self._text.configure(state="disabled")

    def heading(self, line):
        self.append(line, "heading")


# ── File list ─────────────────────────────────────────────────────────────────
class FileList(tk.Frame):
    def __init__(self, parent, on_change=None, accepted_exts=None, **kw):
        super().__init__(parent, bg=C["surface"], **kw)
        self._paths = []
        self._on_change = on_change
        self._accepted_exts = accepted_exts  # None = accept all
        self._selected = set()

        self._canvas = tk.Canvas(self, bg=C["surface"],
                                  highlightthickness=0, bd=0)
        self._sb = tk.Scrollbar(self, orient="vertical",
                                 command=self._canvas.yview,
                                 bg=C["panel"], troughcolor=C["surface"],
                                 relief="flat", bd=0, width=10)
        self._canvas.configure(yscrollcommand=self._sb.set)
        self._inner = tk.Frame(self._canvas, bg=C["surface"])
        self._win = self._canvas.create_window((0,0), window=self._inner, anchor="nw")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._sb.pack(side="right", fill="y")
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(
                              self._win, width=e.width))
        self._canvas.bind_all("<MouseWheel>",
                              lambda e: self._canvas.yview_scroll(
                                  int(-1*(e.delta/120)), "units"))
        self._rows = []
        self._render()

    def add(self, paths):
        added = 0
        for p in paths:
            if self._accepted_exts:
                if not any(p.name.lower().endswith(ext)
                           for ext in self._accepted_exts):
                    continue
            if p not in self._paths:
                self._paths.append(p)
                added += 1
        if added:
            self._render()
            if self._on_change: self._on_change()

    def remove_selected(self):
        self._paths = [p for i,p in enumerate(self._paths)
                       if i not in self._selected]
        self._selected.clear()
        self._render()
        if self._on_change: self._on_change()

    def clear(self):
        self._paths.clear()
        self._selected.clear()
        self._render()
        if self._on_change: self._on_change()

    def get_paths(self): return list(self._paths)
    def count(self):     return len(self._paths)

    def _badge(self, name):
        name = name.lower()
        for ext, col in TYPE_COLORS.items():
            if name.endswith(f".{ext}.xml"): return ext.upper(), col
        if name.endswith(".png"): return "PNG", "#ce93d8"
        if name.endswith(".jpg") or name.endswith(".jpeg"): return "JPG", "#80deea"
        if name.endswith(".bmp"): return "BMP", "#ffab40"
        return "FILE", C["fg3"]

    def _render(self):
        for f in self._rows: f.destroy()
        self._rows.clear()
        if not self._paths:
            lbl = tk.Label(self._inner,
                           text="No files yet — click Add Files or Add Folder",
                           bg=C["surface"], fg=C["fg3"], font=F_SMALL, pady=20)
            lbl.pack(fill="x")
            self._rows.append(lbl)
            return
        for i, path in enumerate(self._paths):
            is_sel = i in self._selected
            rbg = C["select"] if is_sel else C["surface"]
            row = tk.Frame(self._inner, bg=rbg, cursor="hand2")
            row.pack(fill="x", pady=1)
            badge_txt, badge_col = self._badge(path.name)
            tk.Label(row, text=badge_txt, bg=badge_col, fg=C["bg"],
                     font=("Segoe UI", 7, "bold"),
                     padx=5, pady=2, width=5).pack(side="left", padx=(6,6), pady=4)
            name_lbl = tk.Label(row, text=path.name, bg=rbg, fg=C["fg"],
                                 font=F_BODY, anchor="w")
            name_lbl.pack(side="left", fill="x", expand=True)
            dir_lbl = tk.Label(row, text=str(path.parent)[-38:],
                                bg=rbg, fg=C["fg3"], font=F_SMALL,
                                anchor="e", padx=8)
            dir_lbl.pack(side="right")
            def make_h(idx, r, nl, dl):
                def enter(e):
                    if idx not in self._selected:
                        for w in (r,nl,dl): w.config(bg=C["hover"])
                def leave(e):
                    bg = C["select"] if idx in self._selected else C["surface"]
                    for w in (r,nl,dl): w.config(bg=bg)
                def click(e):
                    if idx in self._selected:
                        self._selected.discard(idx)
                        for w in (r,nl,dl): w.config(bg=C["surface"])
                    else:
                        self._selected.add(idx)
                        for w in (r,nl,dl): w.config(bg=C["select"])
                return enter, leave, click
            en, le, cl = make_h(i, row, name_lbl, dir_lbl)
            for w in (row, name_lbl, dir_lbl):
                w.bind("<Enter>", en)
                w.bind("<Leave>", le)
                w.bind("<Button-1>", cl)
            self._rows.append(row)


# ── Main App ──────────────────────────────────────────────────────────────────
class S2XMLApp(tk.Tk):
    def __init__(self):
        super().__init__()
        init_fonts()
        self.title("S2XML — Sims 2 Mod Compiler")
        self.configure(bg=C["bg"])
        self.geometry("1020x700")
        self.minsize(860, 580)

        self._output_path = None
        self._log_queue   = queue.Queue()
        self._active_log  = None

        self._setup_styles()
        self._build_ui()
        self._poll_log()

    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=0)
        s.configure("TNotebook.Tab", background=C["panel"], foreground=C["fg2"],
                    padding=[16, 8], font=F_BOLD, borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", C["surface"]), ("active", C["hover"])],
              foreground=[("selected", C["fg"]),      ("active", C["fg"])])

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=C["accent"], height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="S2XML", bg=C["accent"], fg="white",
                 font=("Segoe UI", 16, "bold"), padx=20).pack(side="left", pady=10)
        tk.Label(header, text="Sims 2 Mod Compiler", bg=C["accent"], fg="#cccccc",
                 font=("Segoe UI", 10), padx=0).pack(side="left", pady=10)
        self._status_var = tk.StringVar(value="Ready")
        self._status_lbl = tk.Label(header, textvariable=self._status_var,
                                     bg=C["surface"], fg=C["fg2"],
                                     font=F_SMALL, padx=10, pady=4)
        self._status_lbl.pack(side="right", padx=16, pady=14)

        # Notebook
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True)
        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_change)

        self._compile_tab    = self._build_compile_tab()
        self._decompile_tab  = self._build_decompile_tab()
        self._texture_tab    = self._build_texture_tab()
        self._objsetup_tab   = self._build_objsetup_tab()
        self._diff_tab       = self._build_diff_tab()
        self._opcodes_tab    = self._build_opcodes_tab()

        self._nb.add(self._compile_tab,   text="  Compile  ")
        self._nb.add(self._decompile_tab, text="  Decompile  ")
        self._nb.add(self._texture_tab,   text="  Textures  ")
        self._nb.add(self._objsetup_tab,  text="  Object Setup  ")
        self._nb.add(self._diff_tab,      text="  Diff  ")
        self._nb.add(self._opcodes_tab,   text="  Opcodes  ")

        self._active_log = self._compile_log

    def _on_tab_change(self, e):
        idx  = self._nb.index(self._nb.select())
        logs = [self._compile_log, self._decompile_log,
                self._texture_log, self._objsetup_log,
                self._diff_log, self._opcodes_log]
        self._active_log = logs[idx] if idx < len(logs) else self._compile_log
        if idx == 5 and not self._opcodes_log._text.get("1.0","2.0").strip():
            self._populate_opcodes()

    # ── Sidebar helper ────────────────────────────────────────────────────────
    def _make_sidebar(self, parent, title, width=300):
        sb = tk.Frame(parent, bg=C["surface"], width=width)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)
        sh = tk.Frame(sb, bg=C["panel"], height=44)
        sh.pack(fill="x")
        sh.pack_propagate(False)
        tk.Label(sh, text=title, bg=C["panel"], fg=C["fg"],
                 font=F_BOLD, padx=14).pack(side="left", pady=10)
        body = tk.Frame(sb, bg=C["surface"])
        body.pack(fill="both", expand=True, padx=12, pady=12)
        return sb, body

    def _make_log_panel(self, parent, title):
        right = tk.Frame(parent, bg=C["bg"])
        right.pack(side="right", fill="both", expand=True)
        lh = tk.Frame(right, bg=C["bg"], height=44)
        lh.pack(fill="x")
        lh.pack_propagate(False)
        tk.Label(lh, text=title, bg=C["bg"], fg=C["fg"],
                 font=F_BOLD, padx=14).pack(side="left", pady=12)
        log = LogPane(right)
        log.pack(fill="both", expand=True)
        styled_btn(lh, "Clear", log.clear, small=True).pack(
            side="right", padx=10, pady=10)
        return right, log

    # ── COMPILE TAB ───────────────────────────────────────────────────────────
    def _build_compile_tab(self):
        outer = tk.Frame(self._nb, bg=C["bg"])
        sb, body = self._make_sidebar(outer, "Resource Files")

        # File count in header
        self._file_count_var = tk.StringVar(value="0 files")
        tk.Label(sb.winfo_children()[0], textvariable=self._file_count_var,
                 bg=C["panel"], fg=C["fg3"], font=F_SMALL,
                 padx=8).pack(side="right", pady=10)

        self._file_list = FileList(sb, on_change=self._on_files_changed)
        self._file_list.pack(fill="both", expand=True)

        divider(sb).pack(fill="x")
        btn_area = tk.Frame(sb, bg=C["surface"], pady=10)
        btn_area.pack(fill="x")
        r1 = tk.Frame(btn_area, bg=C["surface"])
        r1.pack(fill="x", padx=10, pady=(0,6))
        styled_btn(r1, "＋  Add Files",  self._add_files,  accent=True).pack(side="left", fill="x", expand=True, padx=(0,5))
        styled_btn(r1, "＋  Add Folder", self._add_folder, accent=True).pack(side="right", fill="x", expand=True)
        r2 = tk.Frame(btn_area, bg=C["surface"])
        r2.pack(fill="x", padx=10)
        styled_btn(r2, "✕  Remove Selected", self._remove_selected, small=True).pack(side="left", padx=(0,5))
        styled_btn(r2, "Clear All", self._clear_all, small=True).pack(side="left")

        divider(sb).pack(fill="x", pady=(8,0))
        out_area = tk.Frame(sb, bg=C["surface"], pady=10)
        out_area.pack(fill="x")
        section_label(out_area, "Output .package").pack(fill="x", padx=12, pady=(0,4))
        out_row = tk.Frame(out_area, bg=C["surface"])
        out_row.pack(fill="x", padx=10)
        self._out_entry_var = tk.StringVar(value="Auto-named")
        tk.Entry(out_row, textvariable=self._out_entry_var,
                 bg=C["entry_bg"], fg=C["fg2"], insertbackground=C["fg"],
                 relief="flat", font=F_SMALL, state="readonly").pack(
                     side="left", fill="x", expand=True, ipady=6, padx=(0,5))
        styled_btn(out_row, "…", self._choose_output, small=True).pack(side="right")

        divider(sb).pack(fill="x", pady=(8,0))
        act = tk.Frame(sb, bg=C["surface"], pady=12)
        act.pack(fill="x")
        self._lint_only = tk.BooleanVar(value=False)
        tk.Checkbutton(act, text="  Lint only (validate, no output)",
                       variable=self._lint_only,
                       bg=C["surface"], fg=C["fg2"], selectcolor=C["panel"],
                       activebackground=C["surface"], activeforeground=C["fg"],
                       font=F_SMALL, cursor="hand2").pack(anchor="w", padx=12, pady=(0,10))
        self._compile_btn = styled_btn(act, "▶   Compile Package",
                                       self._run_compile, accent=True)
        self._compile_btn.pack(fill="x", padx=10)
        self._compile_btn.configure(pady=12, font=("Segoe UI", 10, "bold"))

        _, self._compile_log = self._make_log_panel(outer, "Compiler Output")
        self._compile_log.heading("S2XML Compiler ready.")
        self._compile_log.append("Add XML files on the left, then click Compile Package.", "dim")
        self._compile_log.append("")
        self._compile_log.append("Supported types: .bhav.xml  .str.xml  .trcn.xml  .tprp.xml", "dimmer")
        self._compile_log.append("  .objf.xml  .glob.xml  .objd.xml  .ttab.xml  .bcon.xml", "dimmer")
        self._compile_log.append("  .ctss.xml  .nref.xml  .vers.xml  .ttas.xml", "dimmer")
        return outer

    # ── DECOMPILE TAB ─────────────────────────────────────────────────────────
    def _build_decompile_tab(self):
        outer = tk.Frame(self._nb, bg=C["bg"])
        sb, body = self._make_sidebar(outer, "Decompile .package → XML")

        self._dec_in  = tk.StringVar()
        self._dec_out = tk.StringVar(value="Same folder as .package")
        labeled_entry(body, "Input .package file", self._dec_in,
                      browse_cmd=self._browse_pkg_in)
        labeled_entry(body, "Output folder", self._dec_out,
                      browse_cmd=self._browse_dec_out)

        divider(body).pack(fill="x", pady=(0,12))
        self._dec_info_only = tk.BooleanVar(value=False)
        tk.Checkbutton(body, text="  List resources only (no files)",
                       variable=self._dec_info_only,
                       bg=C["surface"], fg=C["fg2"], selectcolor=C["panel"],
                       activebackground=C["surface"], font=F_SMALL,
                       cursor="hand2").pack(anchor="w", pady=(0,12))
        styled_btn(body, "▶   Decompile", self._run_decompile,
                   accent=True).pack(fill="x", pady=(4,0), ipady=6)
        tk.Label(body, text="Extracts every resource to editable XML.\nUnknown types are preserved as raw data.",
                 bg=C["surface"], fg=C["fg3"], font=F_SMALL,
                 justify="left", anchor="w").pack(fill="x", pady=(16,0))

        _, self._decompile_log = self._make_log_panel(outer, "Decompiler Output")
        return outer

    # ── TEXTURE TAB ───────────────────────────────────────────────────────────
    def _build_texture_tab(self):
        outer = tk.Frame(self._nb, bg=C["bg"])
        sb, body = self._make_sidebar(outer, "Texture Import", width=320)

        tk.Label(body,
                 text="Import PNG/JPG images and convert them\nto Sims 2 texture resources.",
                 bg=C["surface"], fg=C["fg2"], font=F_SMALL,
                 justify="left", anchor="w").pack(fill="x", pady=(0,12))

        self._tex_list = FileList(sb, accepted_exts=[".png",".jpg",".jpeg",".bmp"])
        self._tex_list.pack(fill="both", expand=True)

        divider(sb).pack(fill="x")
        btn_area = tk.Frame(sb, bg=C["surface"], pady=8)
        btn_area.pack(fill="x")
        r1 = tk.Frame(btn_area, bg=C["surface"])
        r1.pack(fill="x", padx=10, pady=(0,6))
        styled_btn(r1, "＋  Add Images", self._add_textures, accent=True).pack(
            fill="x", expand=True)

        divider(sb).pack(fill="x")
        opts = tk.Frame(sb, bg=C["surface"], pady=10)
        opts.pack(fill="x", padx=12)

        section_label(opts, "Output Format").pack(fill="x", pady=(0,4))
        self._tex_fmt = tk.StringVar(value="dxt1")
        fmts = [
            ("DXT1 — RGB, no alpha (smallest)", "dxt1"),
            ("Raw RGBA — full quality, larger", "raw"),
        ]
        for label, val in fmts:
            tk.Radiobutton(opts, text=label, variable=self._tex_fmt, value=val,
                           bg=C["surface"], fg=C["fg2"], selectcolor=C["panel"],
                           activebackground=C["surface"], font=F_SMALL,
                           cursor="hand2").pack(anchor="w")

        section_label(opts, "Also Generate").pack(fill="x", pady=(10,4))
        self._tex_make_txmt = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text="  TXMT material definition",
                       variable=self._tex_make_txmt,
                       bg=C["surface"], fg=C["fg2"], selectcolor=C["panel"],
                       activebackground=C["surface"], font=F_SMALL,
                       cursor="hand2").pack(anchor="w")

        section_label(opts, "Output .package").pack(fill="x", pady=(10,4))
        out_row = tk.Frame(opts, bg=C["surface"])
        out_row.pack(fill="x")
        self._tex_out_var = tk.StringVar(value="Auto-named")
        tk.Entry(out_row, textvariable=self._tex_out_var,
                 bg=C["entry_bg"], fg=C["fg2"], insertbackground=C["fg"],
                 relief="flat", font=F_SMALL, state="readonly").pack(
                     side="left", fill="x", expand=True, ipady=5, padx=(0,5))
        styled_btn(out_row, "…", self._choose_tex_out, small=True).pack(side="right")

        divider(sb).pack(fill="x", pady=(8,0))
        act = tk.Frame(sb, bg=C["surface"], pady=12)
        act.pack(fill="x")
        styled_btn(act, "▶   Convert & Package",
                   self._run_texture, accent=True).pack(
                       fill="x", padx=10, ipady=8)
        act.children[list(act.children)[-1]].configure(
            font=("Segoe UI", 10, "bold"))

        _, self._texture_log = self._make_log_panel(outer, "Texture Output")
        self._texture_log.heading("Texture Importer ready.")
        self._texture_log.append(
            "Add PNG/JPG images on the left and click Convert & Package.", "dim")
        self._texture_log.append(
            "Each image becomes a TXTR resource (+ optional TXMT) in the package.", "dimmer")
        return outer

    # ── OBJECT SETUP TAB ──────────────────────────────────────────────────────
    def _build_objsetup_tab(self):
        outer = tk.Frame(self._nb, bg=C["bg"])
        sb, body = self._make_sidebar(outer, "Object Setup", width=340)

        tk.Label(body,
                 text="Fill in the form to generate a fully wired\n"
                      "OBJD + GLOB + OBJf + TTAB in one click.",
                 bg=C["surface"], fg=C["fg2"], font=F_SMALL,
                 justify="left", anchor="w").pack(fill="x", pady=(0,10))

        divider(body).pack(fill="x", pady=(0,10))

        # Object basics
        section_label(body, "Object Name").pack(fill="x", pady=(0,3))
        self._obj_name = tk.StringVar()
        tk.Entry(body, textvariable=self._obj_name,
                 bg=C["entry_bg"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=F_BODY).pack(fill="x", ipady=6, pady=(0,8))

        section_label(body, "Catalog Description").pack(fill="x", pady=(0,3))
        self._obj_desc = tk.StringVar()
        tk.Entry(body, textvariable=self._obj_desc,
                 bg=C["entry_bg"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=F_BODY).pack(fill="x", ipady=6, pady=(0,8))

        # Two column row
        row2 = tk.Frame(body, bg=C["surface"])
        row2.pack(fill="x", pady=(0,8))
        left2 = tk.Frame(row2, bg=C["surface"])
        left2.pack(side="left", fill="x", expand=True, padx=(0,8))
        right2 = tk.Frame(row2, bg=C["surface"])
        right2.pack(side="right", fill="x", expand=True)

        section_label(left2,  "Price (§)").pack(fill="x", pady=(0,3))
        self._obj_price = tk.StringVar(value="100")
        tk.Entry(left2, textvariable=self._obj_price,
                 bg=C["entry_bg"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=F_BODY, width=10).pack(fill="x", ipady=6)

        section_label(right2, "GUID (hex)").pack(fill="x", pady=(0,3))
        self._obj_guid = tk.StringVar(value="0x12345678")
        tk.Entry(right2, textvariable=self._obj_guid,
                 bg=C["entry_bg"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=F_BODY, width=12).pack(fill="x", ipady=6)

        section_label(body, "Group ID (hex)").pack(fill="x", pady=(0,3))
        self._obj_group = tk.StringVar(value="0x7FD46CD0")
        tk.Entry(body, textvariable=self._obj_group,
                 bg=C["entry_bg"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=F_BODY).pack(fill="x", ipady=6, pady=(0,8))

        section_label(body, "Room Sort").pack(fill="x", pady=(0,3))
        self._obj_room = tk.StringVar(value="Miscellaneous")
        room_cb = ttk.Combobox(body, textvariable=self._obj_room,
                                font=F_BODY, state="readonly",
                                values=["Miscellaneous","Seating","Surfaces",
                                        "Appliances","Electronics","Plumbing",
                                        "Lighting","Decorative","Kids","Exercise",
                                        "Career","Hobbies"])
        room_cb.pack(fill="x", ipady=4, pady=(0,8))

        divider(body).pack(fill="x", pady=(0,10))

        # Interactions
        section_label(body, "Interactions (one per line: Name | action_inst | guard_inst)").pack(
            fill="x", pady=(0,3))
        self._obj_interactions = tk.Text(body, bg=C["entry_bg"], fg=C["fg"],
                                          insertbackground=C["fg"],
                                          relief="flat", font=F_MONO,
                                          height=4, padx=4, pady=4)
        self._obj_interactions.pack(fill="x", pady=(0,8))
        self._obj_interactions.insert("1.0", "Sit | 0x1001 | 0x0000\nSleep | 0x1002 | 0x0000")

        divider(body).pack(fill="x", pady=(0,10))

        section_label(body, "Output .package").pack(fill="x", pady=(0,3))
        out_row = tk.Frame(body, bg=C["surface"])
        out_row.pack(fill="x", pady=(0,10))
        self._obj_out_var = tk.StringVar(value="Auto-named")
        tk.Entry(out_row, textvariable=self._obj_out_var,
                 bg=C["entry_bg"], fg=C["fg2"], insertbackground=C["fg"],
                 relief="flat", font=F_SMALL, state="readonly").pack(
                     side="left", fill="x", expand=True, ipady=5, padx=(0,5))
        styled_btn(out_row, "…", self._choose_obj_out, small=True).pack(side="right")

        styled_btn(body, "▶   Generate Object Resources",
                   self._run_objsetup, accent=True).pack(
                       fill="x", ipady=8)
        body.winfo_children()[-1].configure(font=("Segoe UI", 10, "bold"))

        _, self._objsetup_log = self._make_log_panel(outer, "Object Setup Output")
        self._objsetup_log.heading("Object Setup ready.")
        self._objsetup_log.append(
            "Fill in the form and click Generate to create a complete object package.", "dim")
        self._objsetup_log.append(
            "Generates: OBJD + GLOB + OBJf + TTAB + STR# all correctly wired.", "dimmer")
        return outer

    # ── DIFF TAB ──────────────────────────────────────────────────────────────
    def _build_diff_tab(self):
        outer = tk.Frame(self._nb, bg=C["bg"])
        sb, body = self._make_sidebar(outer, "Compare Packages")

        self._diff_a = tk.StringVar()
        self._diff_b = tk.StringVar()
        labeled_entry(body, "Package A  (original)", self._diff_a,
                      browse_cmd=lambda: self._browse_pkg(self._diff_a))
        labeled_entry(body, "Package B  (modified)", self._diff_b,
                      browse_cmd=lambda: self._browse_pkg(self._diff_b))

        divider(body).pack(fill="x", pady=(0,12))
        self._diff_brief = tk.BooleanVar(value=False)
        tk.Checkbutton(body, text="  Brief summary only",
                       variable=self._diff_brief,
                       bg=C["surface"], fg=C["fg2"], selectcolor=C["panel"],
                       activebackground=C["surface"], font=F_SMALL,
                       cursor="hand2").pack(anchor="w", pady=(0,12))
        styled_btn(body, "▶   Compare", self._run_diff,
                   accent=True).pack(fill="x", ipady=6)

        _, self._diff_log = self._make_log_panel(outer, "Diff Output")
        return outer

    # ── OPCODES TAB ───────────────────────────────────────────────────────────
    def _build_opcodes_tab(self):
        outer = tk.Frame(self._nb, bg=C["bg"])
        bar = tk.Frame(outer, bg=C["panel"], height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="Search opcodes:", bg=C["panel"], fg=C["fg2"],
                 font=F_BODY, padx=14).pack(side="left", pady=13)
        self._op_query = tk.StringVar()
        self._op_query.trace_add("write", lambda *_: self._populate_opcodes())
        tk.Entry(bar, textvariable=self._op_query,
                 bg=C["entry_bg"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=F_BODY, width=28).pack(
                     side="left", ipady=7, pady=10)
        tk.Label(bar, text="Type a name (animate, relationship…) or code (0x0025)",
                 bg=C["panel"], fg=C["fg3"], font=F_SMALL, padx=14).pack(side="left")
        self._opcodes_log = LogPane(outer)
        self._opcodes_log.pack(fill="both", expand=True)
        return outer

    def _populate_opcodes(self):
        try:
            from opcodes import OPCODES
        except ImportError:
            return
        query = self._op_query.get().strip().lower()
        self._opcodes_log.clear()
        count = 0
        for code in sorted(OPCODES):
            info  = OPCODES[code]
            name  = info.get("name", "")
            notes = info.get("notes", "")
            ops_t = " ".join(o for o in info.get("operands", []) if o)
            if query and not any(query in x for x in
                                 [name.lower(), notes.lower(),
                                  ops_t.lower(), f"0x{code:04x}"]):
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
            f"  {count} opcode(s)" + (f" matching '{query}'" if query else ""), "dimmer")

    # ── File actions ──────────────────────────────────────────────────────────
    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select XML resource files",
            filetypes=[("XML files","*.xml"),("All files","*.*")], parent=self)
        if paths: self._file_list.add([Path(p) for p in paths])

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select folder", parent=self)
        if folder:
            xmls = sorted(Path(folder).glob("*.xml"))
            if not xmls:
                messagebox.showinfo("No XML files",
                                    f"No .xml files found in:\n{folder}", parent=self)
            else:
                self._file_list.add(xmls)

    def _add_textures(self):
        paths = filedialog.askopenfilenames(
            title="Select image files",
            filetypes=[("Images","*.png *.jpg *.jpeg *.bmp"),("All","*.*")],
            parent=self)
        if paths: self._tex_list.add([Path(p) for p in paths])

    def _remove_selected(self):  self._file_list.remove_selected()
    def _clear_all(self):
        if self._file_list.count() == 0: return
        if messagebox.askyesno("Clear all","Remove all files?",parent=self):
            self._file_list.clear()

    def _on_files_changed(self):
        n = self._file_list.count()
        self._file_count_var.set(f"{n} file{'s' if n!=1 else ''}")

    def _choose_output(self):
        p = filedialog.asksaveasfilename(
            title="Save .package as…", defaultextension=".package",
            filetypes=[("Sims 2 package","*.package")], parent=self)
        if p:
            self._output_path = Path(p)
            self._out_entry_var.set(self._output_path.name)

    def _choose_tex_out(self):
        p = filedialog.asksaveasfilename(
            title="Save texture package as…", defaultextension=".package",
            filetypes=[("Sims 2 package","*.package")], parent=self)
        if p: self._tex_out_var.set(p)

    def _choose_obj_out(self):
        p = filedialog.asksaveasfilename(
            title="Save object package as…", defaultextension=".package",
            filetypes=[("Sims 2 package","*.package")], parent=self)
        if p: self._obj_out_var.set(p)

    def _browse_pkg_in(self):
        p = filedialog.askopenfilename(title="Open .package",
            filetypes=[("Sims 2 package","*.package")], parent=self)
        if p: self._dec_in.set(p)

    def _browse_dec_out(self):
        d = filedialog.askdirectory(title="Output folder", parent=self)
        if d: self._dec_out.set(d)

    def _browse_pkg(self, var):
        p = filedialog.askopenfilename(title="Select .package",
            filetypes=[("Sims 2 package","*.package")], parent=self)
        if p: var.set(p)

    def _set_status(self, text, color=None):
        self._status_var.set(text)
        self._status_lbl.config(fg=color or C["fg2"])

    # ── Run: Compile ──────────────────────────────────────────────────────────
    def _run_compile(self):
        files = self._file_list.get_paths()
        if not files:
            messagebox.showwarning("No files","Add some XML files first.",parent=self)
            return
        out_path = self._output_path
        if not out_path:
            first = files[0]
            out_path = first.parent / f"{first.parent.name or first.stem}.package"
        lint_only = self._lint_only.get()
        self._compile_btn.config(state="disabled", text="Working…")
        self._compile_log.clear()
        self._compile_log.heading(
            f"{'Linting' if lint_only else 'Compiling'}  "
            f"{len(files)} resource(s)  →  {out_path.name}\n")
        self._set_status("Compiling…", C["warn"])

        def task():
            try:
                from xml_parser  import parse_resource_xml, set_global_constants, TYPE_NAMES
                from dbpf_writer import DBPFWriter
                from linter      import lint_resources

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
                    except Exception: pass
                if global_consts:
                    set_global_constants(global_consts)
                    self._q(f"  Loaded {len(global_consts)} named constant(s)\n","dim")

                resources, file_names, counts, success = [], [], {}, True
                for xf in files:
                    try:
                        tid,gid,iid,data = parse_resource_xml(str(xf))
                        resources.append((tid,gid,iid,data))
                        file_names.append(xf.name)
                        tname = TYPE_NAMES.get(tid, f"0x{tid:08X}")
                        counts[tname] = counts.get(tname,0) + 1
                        self._q(f"  + {xf.name:<44} [{tname}]","dim")
                    except Exception as e:
                        self._q(f"  ✗ {xf.name}: {e}","error")
                        success = False

                if not resources:
                    self._q("\nNo resources compiled.","error")
                    self._set_status("Failed", C["error"])
                    return

                self._q("")
                msgs   = lint_resources(resources, file_names)
                errors = [m for m in msgs if m.level=="error"]
                warns  = [m for m in msgs if m.level=="warning"]
                for m in errors: self._q(str(m),"error")
                for m in warns:  self._q(str(m),"warn")
                if not msgs: self._q("  ✓ No lint issues","ok")
                else: self._q(f"\n  {len(errors)} error(s)   {len(warns)} warning(s)")

                if errors:
                    self._q(f"\n  Blocked — fix {len(errors)} error(s).","error")
                    self._set_status(f"{len(errors)} lint error(s)", C["error"])
                    return

                if lint_only:
                    summary = "  ".join(f"{n}×{c}" for n,c in sorted(counts.items()))
                    self._q(f"\n  ✓ Lint passed — {len(resources)} resource(s)  [{summary}]","ok")
                    self._set_status("Lint OK", C["success"])
                    return

                writer = DBPFWriter()
                for t,g,i,d in resources: writer.add_resource(t,g,i,d)
                pkg = writer.write_package()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(pkg)
                summary = "  ".join(f"{n}×{c}" for n,c in sorted(counts.items()))
                kb = len(pkg)/1024
                self._q(f"\n  ✓  {out_path.name}","ok")
                self._q(f"     {len(resources)} resource(s)   [{summary}]   {kb:.1f} KB","dim")
                self._q(f"     Saved to: {out_path}","dim")
                self._set_status(f"✓ {out_path.name}", C["success"])
                self.after(200, lambda: self._offer_open(out_path.parent))
            except Exception as e:
                import traceback
                self._q(f"\nUnexpected error: {e}","error")
                self._q(traceback.format_exc(),"error")
                self._set_status("Error", C["error"])
            finally:
                self.after(0, lambda: self._compile_btn.config(
                    state="normal", text="▶   Compile Package"))

        threading.Thread(target=task, daemon=True).start()

    # ── Run: Decompile ────────────────────────────────────────────────────────
    def _run_decompile(self):
        pkg_str = self._dec_in.get().strip()
        if not pkg_str:
            messagebox.showwarning("No file","Choose a .package file.",parent=self)
            return
        pkg = Path(pkg_str)
        if not pkg.exists():
            messagebox.showerror("Not found",f"File not found:\n{pkg}",parent=self)
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
                self._q(f"  {len(resources)} resource(s) found\n","dim")
                if info_only:
                    for i,res in enumerate(resources):
                        tname = TYPE_NAMES.get(res.type_id,f"0x{res.type_id:08X}")
                        name  = getattr(res,"name","") or ""
                        raw   = "  [unsupported]" if isinstance(res,RawResource) else ""
                        self._q(f"  [{i:2d}]  {tname:<6}  inst=0x{res.instance_id:08X}   '{name}'{raw}")
                    self._set_status("Listed", C["success"])
                    return
                out_dir.mkdir(parents=True, exist_ok=True)
                bhav_map = {r.instance_id:r for r in resources if isinstance(r,DecodedBHAV)}
                counts = {}
                for res in resources:
                    tname = TYPE_NAMES.get(res.type_id,f"0x{res.type_id:08X}")
                    try:
                        xp = write_resource_xml(res, out_dir, bhav_map=bhav_map)
                        counts[tname] = counts.get(tname,0) + 1
                        raw = "  [raw]" if isinstance(res,RawResource) else ""
                        self._q(f"  → {xp.name:<52} [{tname}]{raw}","dim")
                    except Exception as e:
                        self._q(f"  ✗ {tname} 0x{res.instance_id:08X}: {e}","error")
                summary = "  ".join(f"{n}×{c}" for n,c in sorted(counts.items()))
                self._q(f"\n  ✓  {sum(counts.values())} file(s)  [{summary}]","ok")
                self._q(f"     Output: {out_dir}","dim")
                self._set_status("✓ Done", C["success"])
                self.after(200, lambda: self._offer_open(out_dir))
            except Exception as e:
                import traceback
                self._q(f"\nError: {e}","error")
                self._q(traceback.format_exc(),"error")
                self._set_status("Error", C["error"])

        threading.Thread(target=task, daemon=True).start()

    # ── Run: Texture ──────────────────────────────────────────────────────────
    def _run_texture(self):
        files = self._tex_list.get_paths()
        if not files:
            messagebox.showwarning("No images","Add some image files first.",parent=self)
            return
        fmt      = self._tex_fmt.get()
        make_txmt = self._tex_make_txmt.get()
        out_str  = self._tex_out_var.get()
        out_path = Path(out_str) if out_str != "Auto-named" \
                   else files[0].parent / (files[0].stem + "_textures.package")

        self._texture_log.clear()
        self._texture_log.heading(f"Converting {len(files)} image(s)  →  {out_path.name}\n")
        self._set_status("Converting…", C["warn"])

        def task():
            try:
                from txtr_encoder import image_to_txtr, make_txmt as mk_txmt
                from dbpf_writer  import DBPFWriter

                writer = DBPFWriter()
                counts = 0

                for i, img_path in enumerate(files):
                    try:
                        inst_id = 0x00000001 + i * 2
                        self._q(f"  Converting {img_path.name}…","dim")
                        tid,gid,iid,data = image_to_txtr(
                            str(img_path), fmt=fmt,
                            instance_id=inst_id)
                        writer.add_resource(tid, gid, iid, data)
                        counts += 1
                        self._q(f"  ✓  TXTR  {img_path.name}  ({len(data)//1024} KB)","ok")

                        if make_txmt:
                            tex_name = img_path.stem
                            tid2,gid2,iid2,data2 = mk_txmt(
                                tex_name, instance_id=inst_id+1)
                            writer.add_resource(tid2, gid2, iid2, data2)
                            self._q(f"  ✓  TXMT  {tex_name}","ok")
                            counts += 1

                    except Exception as e:
                        self._q(f"  ✗ {img_path.name}: {e}","error")

                if counts == 0:
                    self._q("\nNo textures converted.","error")
                    self._set_status("Failed", C["error"])
                    return

                pkg = writer.write_package()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(pkg)
                kb = len(pkg)/1024
                self._q(f"\n  ✓  {out_path.name}  ({counts} resources, {kb:.1f} KB)","ok")
                self._q(f"     Saved to: {out_path}","dim")
                self._set_status(f"✓ {out_path.name}", C["success"])
                self.after(200, lambda: self._offer_open(out_path.parent))

            except ImportError as e:
                self._q(f"\nMissing dependency: {e}","error")
                self._q("Pillow is required for texture import.","error")
                self._set_status("Error", C["error"])
            except Exception as e:
                import traceback
                self._q(f"\nError: {e}","error")
                self._q(traceback.format_exc(),"error")
                self._set_status("Error", C["error"])

        threading.Thread(target=task, daemon=True).start()

    # ── Run: Object Setup ─────────────────────────────────────────────────────
    def _run_objsetup(self):
        name = self._obj_name.get().strip()
        if not name:
            messagebox.showwarning("No name","Enter an object name.",parent=self)
            return

        desc  = self._obj_desc.get().strip()
        price = self._obj_price.get().strip()
        guid  = self._obj_guid.get().strip()
        group = self._obj_group.get().strip()
        room_names = ["Miscellaneous","Seating","Surfaces","Appliances",
                      "Electronics","Plumbing","Lighting","Decorative",
                      "Kids","Exercise","Career","Hobbies"]
        room_sort = room_names.index(self._obj_room.get()) \
                    if self._obj_room.get() in room_names else 0

        interactions_raw = self._obj_interactions.get("1.0","end").strip().splitlines()
        interactions = []
        for line in interactions_raw:
            parts = [x.strip() for x in line.split("|")]
            if len(parts) >= 2:
                iname   = parts[0]
                action  = parts[1] if len(parts) > 1 else "0x1001"
                guard   = parts[2] if len(parts) > 2 else "0x0000"
                interactions.append((iname, action, guard))

        out_str  = self._obj_out_var.get()
        out_path = Path(out_str) if out_str != "Auto-named" \
                   else Path.home() / "Desktop" / f"{name.replace(' ','_')}_object.package"

        self._objsetup_log.clear()
        self._objsetup_log.heading(f"Generating object resources for '{name}'\n")
        self._set_status("Generating…", C["warn"])

        def task():
            try:
                from dbpf_writer         import DBPFWriter
                from glob_objd_encoders  import GLOBResource, OBJDResource, TYPE_GLOB, TYPE_OBJD
                from misc_encoders       import OBJfResource
                from ttab_ctss_bcon_encoders import (TTABResource, TTABEntry,
                    AGE_ALL, TTAB_FLAG_IS_AUTONOMOUS, TYPE_TTAB, TYPE_CTSS, CTSSResource)
                from str_encoder         import STRResource
                from dbpf_reader         import TYPE_STR, TYPE_OBJf

                try:
                    group_id = int(group, 0)
                except ValueError:
                    group_id = 0x7FD46CD0

                try:
                    guid_val = int(guid, 0)
                except ValueError:
                    guid_val = 0x12345678

                try:
                    price_val = int(price)
                except ValueError:
                    price_val = 100

                writer = DBPFWriter()

                # OBJD
                objd = OBJDResource(
                    name=name, group_id=group_id, instance_id=0x0001,
                    initial_price=price_val, room_sort=room_sort,
                    interaction_group=group_id, guid=guid_val,
                )
                writer.add_resource(TYPE_OBJD, group_id, 0x0001, objd.encode())
                self._q("  ✓  OBJD (object definition)","ok")

                # GLOB
                glob = GLOBResource(name=name, bhav_group=group_id)
                writer.add_resource(TYPE_GLOB, group_id, 0x0001, glob.encode())
                self._q("  ✓  GLOB (behaviour link)","ok")

                # STR# pie menu strings
                str_res = STRResource(name=f"Object Functions - {name}")
                for iname, _, _ in interactions:
                    str_res.add(iname, "", "en-us")
                writer.add_resource(0x53545223, group_id, 0x0001, str_res.encode())
                self._q(f"  ✓  STR# ({len(interactions)} interaction string(s))","ok")

                # OBJf
                objf = OBJfResource(name=f"Object Functions - {name}")
                for _, action, guard in interactions:
                    try: a = int(action, 0)
                    except: a = 0
                    try: g = int(guard, 0)
                    except: g = 0
                    objf.add(a, g)
                writer.add_resource(0x4F424A66, group_id, 0x0001, objf.encode())
                self._q(f"  ✓  OBJf ({len(interactions)} slot(s))","ok")

                # TTAB
                ttab = TTABResource(name=f"Pie Menu Functions - {name}")
                for i, (iname, action, guard) in enumerate(interactions):
                    try: a = int(action, 0)
                    except: a = 0
                    try: g = int(guard, 0)
                    except: g = 0
                    ttab.add(action=a, guard=g, str_index=i,
                             autonomy=0, flags=TTAB_FLAG_IS_AUTONOMOUS,
                             age_flags=AGE_ALL)
                writer.add_resource(TYPE_TTAB, group_id, 0x0001, ttab.encode())
                self._q(f"  ✓  TTAB ({len(interactions)} interaction(s))","ok")

                # CTSS catalog description
                if desc:
                    ctss = CTSSResource(name=f"Catalog Strings - {name}")
                    ctss.add(name, desc, instance=0x0001)
                    writer.add_resource(TYPE_CTSS, group_id, 0x0002, ctss.encode())
                    self._q("  ✓  CTSS (catalog description)","ok")

                pkg = writer.write_package()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(pkg)
                kb = len(pkg)/1024
                self._q(f"\n  ✓  {out_path.name}  ({kb:.1f} KB)","ok")
                self._q(f"     Saved to: {out_path}","dim")
                self._q(f"\n  Next steps:","dim")
                self._q(f"  — Add BHAV files for actions 0x1001, 0x1002… via the Compile tab","dimmer")
                self._q(f"  — Merge the compiled BHAVs package with this one","dimmer")
                self._set_status(f"✓ {out_path.name}", C["success"])
                self.after(200, lambda: self._offer_open(out_path.parent))

            except Exception as e:
                import traceback
                self._q(f"\nError: {e}","error")
                self._q(traceback.format_exc(),"error")
                self._set_status("Error", C["error"])

        threading.Thread(target=task, daemon=True).start()

    # ── Run: Diff ─────────────────────────────────────────────────────────────
    def _run_diff(self):
        a_str = self._diff_a.get().strip()
        b_str = self._diff_b.get().strip()
        if not a_str or not b_str:
            messagebox.showwarning("Missing files","Choose both packages.",parent=self)
            return
        pa, pb = Path(a_str), Path(b_str)
        for p in (pa, pb):
            if not p.exists():
                messagebox.showerror("Not found",f"Not found:\n{p}",parent=self)
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
                self._q(f"\nError: {e}","error")
                self._set_status("Error", C["error"])

        threading.Thread(target=task, daemon=True).start()

    # ── Thread log ────────────────────────────────────────────────────────────
    def _q(self, line, tag=""):
        self._log_queue.put((line, tag))

    def _poll_log(self):
        log = self._active_log or self._compile_log
        try:
            while True:
                line, tag = self._log_queue.get_nowait()
                if log: log.append(line, tag)
        except queue.Empty:
            pass
        self.after(50, self._poll_log)

    def _offer_open(self, folder):
        if messagebox.askyesno("Done",
                                f"Open output folder?\n\n{folder}", parent=self):
            os.startfile(str(folder))


if __name__ == "__main__":
    app = S2XMLApp()
    app.mainloop()
