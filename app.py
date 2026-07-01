"""
PyToExe - GUI wrapper around PyInstaller for building Windows executables
from Python scripts, with icon assignment and common packaging options.
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

APP_TITLE = "PyToExe"
CONFIG_EXT = ".p2e.json"


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


class ListEditor(ttk.Frame):
    """Reusable add/remove list widget for data files, binaries, hidden imports."""

    def __init__(self, parent, columns, add_callback):
        super().__init__(parent)
        self.columns = columns
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=4)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=180)
        self.tree.grid(row=0, column=0, columnspan=3, sticky="nsew")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scroll.set)
        scroll.grid(row=0, column=3, sticky="ns")

        btns = ttk.Frame(self)
        btns.grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Button(btns, text="Add", command=lambda: add_callback(self)).pack(side="left")
        ttk.Button(btns, text="Remove Selected", command=self.remove_selected).pack(side="left", padx=(6, 0))

        self.columnconfigure(0, weight=1)

    def add_row(self, values):
        self.tree.insert("", "end", values=values)

    def remove_selected(self):
        for item in self.tree.selection():
            self.tree.delete(item)

    def rows(self):
        return [self.tree.item(i, "values") for i in self.tree.get_children()]

    def clear(self):
        for i in self.tree.get_children():
            self.tree.delete(i)


class PyToExeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x720")
        self.minsize(700, 640)

        self.script_path = tk.StringVar()
        self.icon_path = tk.StringVar()
        self.app_name = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "dist"))
        self.onefile = tk.BooleanVar(value=True)
        self.windowed = tk.BooleanVar(value=True)
        self.clean_build = tk.BooleanVar(value=True)
        self.no_confirm = tk.BooleanVar(value=True)
        self.upx = tk.BooleanVar(value=True)
        self.hidden_imports = tk.StringVar()
        self.extra_args = tk.StringVar()

        self.build_proc = None
        self.log_queue = queue.Queue()
        self._converted_icon_tmp = None

        self._build_menu()
        self._build_ui()
        self._poll_log_queue()
        self._check_pyinstaller()

    # ---------- UI construction ----------

    def _build_menu(self):
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Save Preset...", command=self.save_preset)
        filemenu.add_command(label="Load Preset...", command=self.load_preset)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filemenu)
        self.config(menu=menubar)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Script selection ---
        script_frame = ttk.LabelFrame(main, text="Script")
        script_frame.pack(fill="x", **pad)
        ttk.Entry(script_frame, textvariable=self.script_path).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(script_frame, text="Browse...", command=self.pick_script).pack(side="left", padx=6, pady=6)

        # --- Basic options ---
        opts = ttk.LabelFrame(main, text="Options")
        opts.pack(fill="x", **pad)

        row = ttk.Frame(opts)
        row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text="App name:", width=14).pack(side="left")
        ttk.Entry(row, textvariable=self.app_name).pack(side="left", fill="x", expand=True)

        row2 = ttk.Frame(opts)
        row2.pack(fill="x", padx=6, pady=4)
        ttk.Label(row2, text="Output dir:", width=14).pack(side="left")
        ttk.Entry(row2, textvariable=self.output_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Browse...", command=self.pick_output_dir).pack(side="left", padx=(6, 0))

        row3 = ttk.Frame(opts)
        row3.pack(fill="x", padx=6, pady=4)
        ttk.Label(row3, text="Icon (.ico/.png/.jpg):", width=18).pack(side="left")
        ttk.Entry(row3, textvariable=self.icon_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row3, text="Browse...", command=self.pick_icon).pack(side="left", padx=(6, 0))
        ttk.Button(row3, text="Clear", command=lambda: self.icon_path.set("")).pack(side="left", padx=(4, 0))

        checks = ttk.Frame(opts)
        checks.pack(fill="x", padx=6, pady=4)
        ttk.Checkbutton(checks, text="One file (.exe only)", variable=self.onefile).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks, text="Windowed (no console)", variable=self.windowed).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks, text="Clean build", variable=self.clean_build).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks, text="UPX compression", variable=self.upx).pack(side="left")

        row4 = ttk.Frame(opts)
        row4.pack(fill="x", padx=6, pady=4)
        ttk.Label(row4, text="Hidden imports:", width=18).pack(side="left")
        ttk.Entry(row4, textvariable=self.hidden_imports).pack(side="left", fill="x", expand=True)
        ttk.Label(row4, text="(comma-separated)").pack(side="left", padx=(6, 0))

        row5 = ttk.Frame(opts)
        row5.pack(fill="x", padx=6, pady=4)
        ttk.Label(row5, text="Extra CLI args:", width=18).pack(side="left")
        ttk.Entry(row5, textvariable=self.extra_args).pack(side="left", fill="x", expand=True)

        # --- Data files ---
        data_frame = ttk.LabelFrame(main, text="Additional Data Files/Folders (--add-data)")
        data_frame.pack(fill="x", **pad)
        self.data_editor = ListEditor(data_frame, ("Source", "Dest in bundle"), self._add_data_row)
        self.data_editor.pack(fill="x", padx=6, pady=6)

        # --- Build controls ---
        ctrl = ttk.Frame(main)
        ctrl.pack(fill="x", **pad)
        self.build_btn = ttk.Button(ctrl, text="Build EXE", command=self.start_build)
        self.build_btn.pack(side="left")
        self.stop_btn = ttk.Button(ctrl, text="Stop", command=self.stop_build, state="disabled")
        self.stop_btn.pack(side="left", padx=(6, 0))
        ttk.Button(ctrl, text="Open Output Folder", command=self.open_output_folder).pack(side="left", padx=(6, 0))
        self.progress = ttk.Progressbar(ctrl, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 0))

        # --- Log ---
        log_frame = ttk.LabelFrame(main, text="Build Log")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=14, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(main, textvariable=self.status_var, anchor="w").pack(fill="x", padx=8)

    # ---------- Pickers ----------

    def pick_script(self):
        path = filedialog.askopenfilename(title="Select Python script", filetypes=[("Python files", "*.py"), ("All files", "*.*")])
        if path:
            self.script_path.set(path)
            if not self.app_name.get():
                self.app_name.set(Path(path).stem)
            if not self.output_dir.get():
                self.output_dir.set(str(Path(path).parent / "dist"))

    def pick_icon(self):
        path = filedialog.askopenfilename(
            title="Select icon image",
            filetypes=[("Icon/Image files", "*.ico *.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")],
        )
        if path:
            self.icon_path.set(path)

    def pick_output_dir(self):
        path = filedialog.askdirectory(title="Select output directory")
        if path:
            self.output_dir.set(path)

    def _add_data_row(self, editor: ListEditor):
        src = filedialog.askopenfilename(title="Select file to bundle")
        if not src:
            src_dir = filedialog.askdirectory(title="Or select a folder to bundle")
            if not src_dir:
                return
            src = src_dir
        dest = "." if os.path.isdir(src) else "."
        editor.add_row((src, dest))

    # ---------- Presets ----------

    def _collect_config(self):
        return {
            "script_path": self.script_path.get(),
            "icon_path": self.icon_path.get(),
            "app_name": self.app_name.get(),
            "output_dir": self.output_dir.get(),
            "onefile": self.onefile.get(),
            "windowed": self.windowed.get(),
            "clean_build": self.clean_build.get(),
            "upx": self.upx.get(),
            "hidden_imports": self.hidden_imports.get(),
            "extra_args": self.extra_args.get(),
            "data_files": self.data_editor.rows(),
        }

    def save_preset(self):
        path = filedialog.asksaveasfilename(defaultextension=CONFIG_EXT, filetypes=[("PyToExe preset", f"*{CONFIG_EXT}")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._collect_config(), f, indent=2)
        self.status_var.set(f"Preset saved: {path}")

    def load_preset(self):
        path = filedialog.askopenfilename(filetypes=[("PyToExe preset", f"*{CONFIG_EXT}"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.script_path.set(cfg.get("script_path", ""))
        self.icon_path.set(cfg.get("icon_path", ""))
        self.app_name.set(cfg.get("app_name", ""))
        self.output_dir.set(cfg.get("output_dir", ""))
        self.onefile.set(cfg.get("onefile", True))
        self.windowed.set(cfg.get("windowed", True))
        self.clean_build.set(cfg.get("clean_build", True))
        self.upx.set(cfg.get("upx", True))
        self.hidden_imports.set(cfg.get("hidden_imports", ""))
        self.extra_args.set(cfg.get("extra_args", ""))
        self.data_editor.clear()
        for row in cfg.get("data_files", []):
            self.data_editor.add_row(tuple(row))
        self.status_var.set(f"Preset loaded: {path}")

    # ---------- PyInstaller availability ----------

    def _check_pyinstaller(self):
        try:
            subprocess.run([sys.executable, "-m", "PyInstaller", "--version"], capture_output=True, check=True)
        except Exception:
            if messagebox.askyesno(APP_TITLE, "PyInstaller is not installed. Install it now?"):
                self._append_log("Installing PyInstaller...\n")
                threading.Thread(target=self._install_pyinstaller, daemon=True).start()

    def _install_pyinstaller(self):
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"],
                capture_output=True, text=True,
            )
            self.log_queue.put(proc.stdout + proc.stderr)
            self.log_queue.put("PyInstaller installation finished.\n")
        except Exception as e:
            self.log_queue.put(f"Failed to install PyInstaller: {e}\n")

    # ---------- Icon conversion ----------

    def _resolve_icon(self):
        """Return a path to a .ico file for the chosen icon, converting if needed."""
        icon = self.icon_path.get().strip()
        if not icon:
            return None
        if icon.lower().endswith(".ico"):
            return icon
        if not PIL_AVAILABLE:
            raise RuntimeError("Selected icon is not .ico and Pillow is unavailable for conversion. "
                                "Install Pillow or supply a .ico file.")
        img = Image.open(icon)
        tmp_dir = tempfile.mkdtemp(prefix="pytoexe_icon_")
        ico_path = os.path.join(tmp_dir, "icon.ico")
        img.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        self._converted_icon_tmp = tmp_dir
        return ico_path

    # ---------- Build ----------

    def start_build(self):
        script = self.script_path.get().strip()
        if not script or not os.path.isfile(script):
            messagebox.showerror(APP_TITLE, "Select a valid Python script first.")
            return
        try:
            icon = self._resolve_icon()
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return

        out_dir = self.output_dir.get().strip() or str(Path(script).parent / "dist")
        os.makedirs(out_dir, exist_ok=True)
        work_dir = os.path.join(tempfile.gettempdir(), "pytoexe_build")
        spec_dir = out_dir

        cmd = [sys.executable, "-m", "PyInstaller", script, "--distpath", out_dir, "--workpath", work_dir, "--specpath", spec_dir]

        name = self.app_name.get().strip()
        if name:
            cmd += ["--name", name]
        if self.onefile.get():
            cmd.append("--onefile")
        else:
            cmd.append("--onedir")
        if self.windowed.get():
            cmd.append("--windowed")
        else:
            cmd.append("--console")
        if self.clean_build.get():
            cmd.append("--clean")
        if self.no_confirm.get():
            cmd.append("--noconfirm")
        if not self.upx.get():
            cmd.append("--noupx")
        if icon:
            cmd += ["--icon", icon]

        for imp in [i.strip() for i in self.hidden_imports.get().split(",") if i.strip()]:
            cmd += ["--hidden-import", imp]

        for src, dest in self.data_editor.rows():
            cmd += ["--add-data", f"{src}{os.pathsep}{dest}"]

        extra = self.extra_args.get().strip()
        if extra:
            cmd += extra.split()

        self._append_log(f"Running: {' '.join(cmd)}\n\n")
        self.build_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.start(12)
        self.status_var.set("Building...")

        threading.Thread(target=self._run_build, args=(cmd,), daemon=True).start()

    def _run_build(self, cmd):
        try:
            self.build_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True,
            )
            for line in self.build_proc.stdout:
                self.log_queue.put(line)
            self.build_proc.wait()
            rc = self.build_proc.returncode
        except Exception as e:
            self.log_queue.put(f"\nBuild error: {e}\n")
            rc = -1
        finally:
            if self._converted_icon_tmp:
                shutil.rmtree(self._converted_icon_tmp, ignore_errors=True)
                self._converted_icon_tmp = None
            self.log_queue.put(("__DONE__", rc))

    def stop_build(self):
        if self.build_proc and self.build_proc.poll() is None:
            self.build_proc.terminate()
            self._append_log("\nBuild cancelled by user.\n")

    def _poll_log_queue(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__DONE__":
                    rc = item[1]
                    self.progress.stop()
                    self.build_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
                    if rc == 0:
                        self.status_var.set("Build succeeded.")
                        self._append_log("\nBuild succeeded.\n")
                    else:
                        self.status_var.set(f"Build failed (exit code {rc}).")
                        self._append_log(f"\nBuild failed (exit code {rc}).\n")
                else:
                    self._append_log(item)
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _append_log(self, text):
        self.log_text.config(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def open_output_folder(self):
        out_dir = self.output_dir.get().strip()
        if not out_dir or not os.path.isdir(out_dir):
            messagebox.showinfo(APP_TITLE, "Output folder does not exist yet.")
            return
        if sys.platform == "win32":
            os.startfile(out_dir)
        elif sys.platform == "darwin":
            subprocess.run(["open", out_dir])
        else:
            subprocess.run(["xdg-open", out_dir])


if __name__ == "__main__":
    app = PyToExeApp()
    app.mainloop()
