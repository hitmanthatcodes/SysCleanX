# SysCleanX.py
# A system cleaning and application uninstaller utility for Windows.
# --- Standard Library Imports ---
import os
import sys
import ctypes
import threading
import time
import shutil
import glob
import subprocess
import webbrowser
from typing import List, Tuple, Dict

# --- Third-party Library Imports ---
# Import winreg for registry access, handle absence on non-Windows systems.
try:
    import winreg
except ImportError:
    winreg = None  # Gracefully handle non-Windows environments.

# Import customtkinter for the GUI, with error handling for missing dependency.
try:
    import customtkinter as ctk
    from tkinter import messagebox
except ImportError as e:
    print(f"Error: Missing required module {e}")
    print("Please install: pip install customtkinter")
    input("Press Enter to exit...")
    sys.exit(1)

class SystemScanner:
    """Handles scanning the system for temporary files, caches, and installed applications."""

    def __init__(self):
        """Initializes the scanner with a dictionary of target locations."""
        # Define common locations for temporary files and caches.
        # 'REGISTRY_CLEANUP' is a special key for a registry operation.
        self.temp_locations = {
            "Clean User's Temp": [
                os.environ.get('TEMP', ''),
                os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Temp')
            ],
            "Clean Recent Items": [
                os.path.join(os.environ.get('USERPROFILE', ''), 'Recent'),
                os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Recent')
            ],
            "Clear Internet Cache": [
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data', 'Default', 'Cache'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Edge', 'User Data', 'Default', 'Cache'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Mozilla', 'Firefox', 'Profiles'),
                os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Microsoft', 'Windows', 'INetCache'),
                os.path.join(os.environ.get('APPDATA', ''), 'Opera Software', 'Opera Stable', 'Cache'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'BraveSoftware', 'Brave-Browser', 'User Data', 'Default', 'Cache'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Vivaldi', 'User Data', 'Default', 'Cache')
            ],
            "Clear Desktop Run History": ["REGISTRY_CLEANUP"],
            "Clean Prefetch": [r"C:\Windows\Prefetch"],
            "Clear Recycle Bin": [r"C:\$Recycle.Bin"],
            "Clean Windows Temp": [r"C:\Windows\Temp"],
            "Clear Drivers Cache": [
                r"C:\Windows\System32\DriverStore\Temp",
                r"C:\Windows\Temp\DriverStore",
                r"C:\ProgramData\NVIDIA Corporation\Downloader",
            ],
            "Clean Windows Update Cache": [r"C:\Windows\SoftwareDistribution\Download"],
            "Clean Thumbnail Cache": [os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Explorer', 'thumbcache_*.db')],
            "Clean Application Caches": [
                os.path.join(os.environ.get('APPDATA', ''), 'discord', 'Cache'),
                os.path.join(os.environ.get('APPDATA', ''), 'discord', 'Code Cache'),
                r"C:\Program Files (x86)\Steam\appcache",
            ],
            "Clean Memory Dumps": [r"C:\Windows\Minump", r"C:\Windows\MEMORY.DMP"]
        }

    def scan_directory_safely(self, directory_path: str) -> Tuple[int, int]:
        """
        Calculates the total size and file count of a directory, ignoring errors.

        Args:
            directory_path: The path to the directory or file to scan.

        Returns:
            A tuple containing the total size in bytes and the total file count.
        """
        total_size, file_count = 0, 0
        try:
            if not os.path.exists(directory_path): return 0, 0
            # Handle if the path is a single file.
            if os.path.isfile(directory_path):
                return os.path.getsize(directory_path), 1
            # Walk through directory to sum up file sizes and counts.
            for root, _, files in os.walk(directory_path, topdown=False):
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        # Ensure the file exists and is not a symbolic link before getting its size.
                        if os.path.exists(file_path) and not os.path.islink(file_path):
                            total_size += os.path.getsize(file_path)
                            file_count += 1
                    except (OSError, FileNotFoundError):
                        # Ignore files that cannot be accessed or are removed during scan.
                        continue
        except (OSError, PermissionError):
            # Ignore directories that cannot be accessed.
            pass
        return total_size, file_count

    def scan_firefox_cache(self, firefox_profiles_dir: str) -> Tuple[int, int]:
        """
        Specifically scans Firefox cache directories, which are located in profile folders.

        Args:
            firefox_profiles_dir: The root directory containing Firefox profiles.

        Returns:
            A tuple containing the total size in bytes and file count of all cache directories.
        """
        total_size, file_count = 0, 0
        try:
            if os.path.exists(firefox_profiles_dir):
                for profile in os.listdir(firefox_profiles_dir):
                    cache_dir = os.path.join(firefox_profiles_dir, profile, 'cache2')
                    if os.path.isdir(cache_dir):
                        size, count = self.scan_directory_safely(cache_dir)
                        total_size += size
                        file_count += count
        except (OSError, PermissionError):
            pass
        return total_size, file_count

    def scan_location_size(self, location_paths: List[str]) -> Tuple[int, int]:
        """
        Scans a list of file/directory paths or patterns and returns their total size and count.

        Args:
            location_paths: A list of paths, which can include wildcards.

        Returns:
            A tuple containing the total size in bytes and total file count.
        """
        total_size, file_count = 0, 0
        for path_pattern in location_paths:
            # Handle special cases for non-filesystem items.
            if path_pattern == "REGISTRY_CLEANUP":
                file_count += 1
                total_size += 1024  # Assign a nominal size for UI representation.
                continue
            if "Firefox\\Profiles" in path_pattern or "Firefox/Profiles" in path_pattern:
                size, count = self.scan_firefox_cache(path_pattern)
                total_size += size
                file_count += count
                continue
            
            # Use glob to handle wildcard patterns.
            for path in glob.glob(path_pattern):
                size, count = self.scan_directory_safely(path)
                total_size += size
                file_count += count
        return total_size, file_count

    def scan_all_locations(self, progress_callback=None) -> Dict:
        """
        Scans all predefined locations and returns the results.

        Args:
            progress_callback: An optional function to call for progress updates.

        Returns:
            A dictionary with scan results for each location.
        """
        results = {}
        total_locations = len(self.temp_locations)
        for i, (name, paths) in enumerate(self.temp_locations.items()):
            if progress_callback:
                progress_callback(i / total_locations, f"Scanning: {name}")
            size, count = self.scan_location_size(paths)
            results[name] = {"size": size, "count": count, "size_mb": size / (1024 * 1024)}
            time.sleep(0.05)  # Small delay for smoother progress bar update.
        if progress_callback:
            progress_callback(1.0, "Scan complete!")
        return results

    def get_installed_apps(self) -> List[Dict]:
        """
        Retrieves a list of installed applications from the Windows Registry.

        Returns:
            A sorted list of dictionaries, each containing an app's name and uninstall command.
        """
        installed_apps = []
        uninstall_key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
        # Check both HKEY_CURRENT_USER and HKEY_LOCAL_MACHINE for a comprehensive list.
        for hkey in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
            try:
                with winreg.OpenKey(hkey, uninstall_key) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                # Retrieve the display name and uninstall command for each application.
                                display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                uninstall_string = winreg.QueryValueEx(subkey, "UninstallString")[0]
                                if display_name and uninstall_string:
                                    installed_apps.append({"name": display_name, "command": uninstall_string})
                        except (FileNotFoundError, OSError):
                            # Some subkeys may not have the required values.
                            continue
            except FileNotFoundError:
                # The 'Uninstall' key might not exist.
                continue
        return sorted(installed_apps, key=lambda x: x['name'])

class SystemCleaner:
    """Handles the deletion of files and registry keys identified by the scanner."""

    def __init__(self, scanner: SystemScanner):
        """Initializes the cleaner with a SystemScanner instance."""
        self.scanner = scanner

    def clean_directory_safely(self, path: str) -> Tuple[int, int]:
        """
        Deletes a file or directory and calculates the amount of space freed.

        Args:
            path: The path to the file or directory to delete.

        Returns:
            A tuple containing the number of files deleted and bytes freed.
        """
        if not os.path.exists(path): return 0, 0
        initial_size, initial_count = self.scanner.scan_directory_safely(path)
        if initial_count == 0: return 0, 0
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                # Use shutil.rmtree for recursive directory deletion.
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            # Catch any exception during deletion to prevent crashes.
            pass
        final_size, final_count = self.scanner.scan_directory_safely(path)
        return max(0, initial_count - final_count), max(0, initial_size - final_size)

    def clean_firefox_cache(self, firefox_profiles_dir: str) -> Tuple[int, int]:
        """
        Specifically cleans Firefox cache directories.

        Args:
            firefox_profiles_dir: The root directory containing Firefox profiles.

        Returns:
            A tuple of total files deleted and bytes freed.
        """
        total_deleted, total_freed = 0, 0
        try:
            if os.path.exists(firefox_profiles_dir):
                for profile in os.listdir(firefox_profiles_dir):
                    cache_dir = os.path.join(firefox_profiles_dir, profile, 'cache2')
                    if os.path.isdir(cache_dir):
                        deleted, freed = self.clean_directory_safely(cache_dir)
                        total_deleted += deleted
                        total_freed += freed
        except (OSError, PermissionError):
            pass
        return total_deleted, total_freed

    def clear_run_history(self) -> Tuple[int, int]:
        """
        Clears the Windows Run dialog (Win+R) history from the registry.

        Returns:
            A tuple representing the count and size of cleared items for stats.
        """
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as key:
                mrulist, _ = winreg.QueryValueEx(key, "MRUList")
                for value_name in list(mrulist):
                    try:
                        winreg.DeleteValue(key, value_name)
                    except FileNotFoundError:
                        continue
                winreg.SetValueEx(key, "MRUList", 0, winreg.REG_SZ, "")
            return 1, 1024  # Return nominal values for success.
        except Exception:
            return 0, 0

    def clean_location(self, location_paths: List[str]) -> Tuple[int, int]:
        """
        Cleans a list of file/directory paths or special locations.

        Args:
            location_paths: A list of paths or special keys to clean.

        Returns:
            A tuple of total files deleted and bytes freed.
        """
        files_deleted, bytes_freed = 0, 0
        for path_pattern in location_paths:
            if path_pattern == "REGISTRY_CLEANUP":
                deleted, freed = self.clear_run_history()
            elif "Firefox\\Profiles" in path_pattern or "Firefox/Profiles" in path_pattern:
                deleted, freed = self.clean_firefox_cache(path_pattern)
            else:
                deleted, freed = 0, 0
                for path in glob.glob(path_pattern):
                    d, f = self.clean_directory_safely(path)
                    deleted += d
                    freed += f
            files_deleted += deleted
            bytes_freed += freed
        return files_deleted, bytes_freed

class SysCleanXApp:
    """Main application class that builds and manages the customtkinter GUI."""

    def __init__(self):
        """Initializes the application window, frames, and state variables."""
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.title("SysCleanX")
        self.set_icon('SysCleanX.ico')
        
        # Configure window properties.
        self.root.geometry("600x550")
        self.root.resizable(True, True)
        self.root.minsize(500, 450)
        self.root.configure(fg_color="#2B2B2B")

        # Initialize backend components.
        self.scanner = SystemScanner()
        self.cleaner = SystemCleaner(self.scanner)
        
        # State variables to manage application flow.
        self.scan_results = {}
        self.checkboxes = {}
        self.is_scanning = False
        self.is_cleaning = False
        self.is_populating_apps = False

        # Create main UI frames.
        self.cleaner_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.uninstaller_frame = ctk.CTkFrame(self.root, fg_color="transparent")

        # Build UI elements.
        self.create_cleaner_ui()
        self.create_uninstaller_ui()

        # Set the initial view and start the first scan.
        self.show_cleaner_frame()
        self.start_scan()

    def set_icon(self, icon_path):
        """Sets the application window icon, supporting bundled executables."""
        try:
            # Determine the base path for resources, accommodating PyInstaller's temporary folder.
            base_path = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.abspath(".")
            full_icon_path = os.path.join(base_path, icon_path)
            if os.path.exists(full_icon_path):
                self.root.iconbitmap(full_icon_path)
        except Exception as e:
            print(f"Error setting icon: {e}")

    def show_cleaner_frame(self):
        """Switches the view to the main cleaner interface."""
        self.uninstaller_frame.pack_forget()
        self.root.title("SysCleanX")
        self.cleaner_frame.pack(fill="both", expand=True, padx=20, pady=20)

    def show_uninstaller_frame(self):
        """Switches the view to the application uninstaller."""
        self.cleaner_frame.pack_forget()
        self.root.title("SysCleanX - Uninstaller")
        self.uninstaller_frame.pack(fill="both", expand=True, padx=20, pady=20)
        self.start_populating_apps()

    def create_cleaner_ui(self):
        """Builds all widgets for the cleaner frame."""
        # --- Title and Credit ---
        title_container_frame = ctk.CTkFrame(self.cleaner_frame, fg_color="transparent")
        title_container_frame.pack(fill="x", pady=(0, 15))
        title_group_frame = ctk.CTkFrame(title_container_frame, fg_color="transparent")
        title_group_frame.pack()
        title_label = ctk.CTkLabel(title_group_frame, text="SysCleanX", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"))
        title_label.grid(row=0, column=0, rowspan=2)
        credit_label = ctk.CTkLabel(title_group_frame, text="By Hitman", font=ctk.CTkFont(family="Segoe UI", size=12), text_color="gray60", cursor="hand2")
        credit_label.grid(row=1, column=1, sticky="s", padx=(5, 0), pady=(8, 0))
        credit_label.bind("<Button-1>", lambda e: webbrowser.open_new("https://discord.gg/Ayn7uzBgbC"))

        # --- Checkbox List ---
        checkbox_frame = ctk.CTkScrollableFrame(self.cleaner_frame, fg_color="#3C3C3C", border_width=0)
        checkbox_frame.pack(fill="both", expand=True, pady=5)
        
        accent_color = "#007BFF"
        for option in self.scanner.temp_locations.keys():
            var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(
                checkbox_frame, text=f"{option} (Scanning...)", variable=var,
                font=ctk.CTkFont(family="Segoe UI", size=13), fg_color=accent_color, hover_color="#0056b3")
            cb.pack(anchor="w", padx=15, pady=8)
            self.checkboxes[option] = {"var": var, "widget": cb}
            
        # --- Status Label ---
        self.status_label = ctk.CTkLabel(self.cleaner_frame, text="Initializing scan...", font=ctk.CTkFont(family="Segoe UI", size=12), text_color="gray80")
        self.status_label.pack(pady=(15, 10))
        
        # --- Action Buttons ---
        button_frame = ctk.CTkFrame(self.cleaner_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(10, 0))
        button_frame.columnconfigure(0, weight=1)
        
        self.action_button = ctk.CTkButton(
            button_frame, text="Scan System", height=35, font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color=accent_color, hover_color="#0056b3", command=self.handle_action_button)
        self.action_button.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        self.uninstaller_button = ctk.CTkButton(
            button_frame, text="App Uninstaller", height=30, font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#4A4A4A", hover_color="#5A5A5A", command=self.show_uninstaller_frame)
        self.uninstaller_button.grid(row=1, column=0, sticky="ew")

    def create_uninstaller_ui(self):
        """Builds all widgets for the uninstaller frame."""
        title_label = ctk.CTkLabel(self.uninstaller_frame, text="Application Uninstaller", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"))
        title_label.pack(pady=(0, 15))
        
        self.apps_frame = ctk.CTkScrollableFrame(self.uninstaller_frame, fg_color="#3C3C3C")
        self.apps_frame.pack(fill="both", expand=True, pady=5)
        
        button_frame = ctk.CTkFrame(self.uninstaller_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(10, 0))
        button_frame.columnconfigure(0, weight=1)
        
        self.back_button = ctk.CTkButton(
            button_frame, text="Back to Cleaner", height=35, font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            fg_color="#007BFF", hover_color="#0056b3", command=self.show_cleaner_frame)
        self.back_button.grid(row=0, column=0, sticky="ew")

    def start_populating_apps(self):
        """Initiates fetching the list of installed applications in a separate thread."""
        if self.is_populating_apps:
            return
        self.is_populating_apps = True
        
        # Clear previous list and show a loading message.
        for widget in self.apps_frame.winfo_children():
            widget.destroy()
        loading_label = ctk.CTkLabel(self.apps_frame, text="Loading applications...", font=ctk.CTkFont(family="Segoe UI", size=14))
        loading_label.pack(pady=30)
        self.back_button.configure(state="disabled")

        # Run the app fetching in a thread to avoid freezing the GUI.
        threading.Thread(target=self.apps_thread_worker, daemon=True).start()

    def apps_thread_worker(self):
        """Worker function that calls the scanner to get installed apps."""
        apps = self.scanner.get_installed_apps()
        # Schedule the GUI update on the main thread.
        self.root.after(0, self.update_apps_list, apps)

    def update_apps_list(self, apps: List[Dict]):
        """Populates the uninstaller UI with the fetched list of applications."""
        for widget in self.apps_frame.winfo_children():
            widget.destroy()

        if not apps:
            ctk.CTkLabel(self.apps_frame, text="Could not retrieve installed applications.").pack(pady=20)
        else:
            for app in apps:
                app_frame = ctk.CTkFrame(self.apps_frame, fg_color="transparent")
                app_frame.pack(fill="x", pady=4, padx=5)
                app_frame.columnconfigure(0, weight=1)
                ctk.CTkLabel(app_frame, text=app['name'], wraplength=450, justify="left").grid(row=0, column=0, sticky="w", padx=5)
                uninstall_btn = ctk.CTkButton(
                    app_frame, text="Uninstall", width=100, 
                    fg_color="#007BFF", hover_color="#0056b3",
                    command=lambda cmd=app['command']: self.run_uninstaller(cmd))
                uninstall_btn.grid(row=0, column=1, padx=5)
        
        self.back_button.configure(state="normal")
        self.is_populating_apps = False

    def handle_action_button(self):
        """Handles clicks on the main action button (Scan or Clean)."""
        if self.is_scanning or self.is_cleaning: return
        # If scan results exist, the button's function is to clean. Otherwise, it's to scan.
        if self.scan_results: self.start_clean()
        else: self.start_scan()
            
    def update_status(self, text: str):
        """Thread-safe method to update the status label."""
        self.root.after(0, lambda: self.status_label.configure(text=text))

    def start_scan(self):
        """Initiates the system scan process."""
        if self.is_scanning: return
        self.is_scanning = True
        self.scan_results = {}
        # Update UI to reflect scanning state.
        self.action_button.configure(state="disabled", text="Scanning...")
        self.uninstaller_button.configure(state="disabled")
        for option, data in self.checkboxes.items():
            data["widget"].configure(text=f"{option} (Scanning...)")
            data["var"].set(False)
        # Start scanning in a new thread.
        threading.Thread(target=self.scan_thread, daemon=True).start()

    def scan_thread(self):
        """Worker function for scanning."""
        try:
            self.scan_results = self.scanner.scan_all_locations(progress_callback=lambda p, m: self.update_status(m))
            self.root.after(0, self.scan_complete)
        except Exception as e:
            self.root.after(0, self.scan_error, str(e))

    def scan_complete(self):
        """Updates the UI after a successful scan."""
        self.is_scanning = False
        total_files, total_size_mb = 0, 0
        for option, data in self.checkboxes.items():
            result = self.scan_results.get(option, {"count": 0, "size_mb": 0})
            files, size_mb = result["count"], result["size_mb"]
            total_files += files
            total_size_mb += size_mb
            # Update checkbox text with scan results and enable if files were found.
            if files > 0:
                data["widget"].configure(text=f"{option} ({files} files, {size_mb:.1f} MB)", state="normal")
                data["var"].set(True)
            else:
                data["widget"].configure(text=f"{option} (Empty)", state="disabled")
        self.status_label.configure(text=f"Found {total_files} files ({total_size_mb:.1f} MB) to clean.")
        self.action_button.configure(state="normal", text="Clean Selected")
        self.uninstaller_button.configure(state="normal")
        if total_files == 0:
            self.action_button.configure(state="disabled", text="Nothing to Clean")

    def scan_error(self, error):
        """Updates the UI after a failed scan."""
        self.is_scanning = False
        self.status_label.configure(text=f"Scan failed: {error}")
        self.action_button.configure(state="normal", text="Scan Again")
        self.uninstaller_button.configure(state="normal")

    def start_clean(self):
        """Initiates the cleaning process based on user selection."""
        selected_items = [opt for opt, data in self.checkboxes.items() if data["var"].get()]
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select at least one item to clean.")
            return
        self.is_cleaning = True
        # Update UI to reflect cleaning state.
        self.action_button.configure(state="disabled", text="Cleaning...")
        self.uninstaller_button.configure(state="disabled")
        self.update_status("Cleaning selected items...")
        # Start cleaning in a new thread.
        threading.Thread(target=self.clean_thread, args=(selected_items,), daemon=True).start()

    def clean_thread(self, selected_items):
        """Worker function for cleaning."""
        try:
            cleaned_files, bytes_freed = 0, 0
            for i, item in enumerate(selected_items):
                self.update_status(f"Cleaning: {item}")
                paths = self.scanner.temp_locations[item]
                files_deleted, bytes_deleted = self.cleaner.clean_location(paths)
                cleaned_files += files_deleted
                bytes_freed += bytes_deleted
                time.sleep(0.1) # Small delay for smoother progress update.
            self.root.after(0, self.clean_complete, cleaned_files, bytes_freed)
        except Exception as e:
            self.root.after(0, self.clean_error, str(e))

    def clean_complete(self, files_cleaned, bytes_freed):
        """Updates the UI after a successful cleaning operation."""
        self.is_cleaning = False
        mb_freed = bytes_freed / (1024 * 1024)
        self.status_label.configure(text=f"Success! Cleaned {files_cleaned} files, freed {mb_freed:.1f} MB.")
        # Reset UI for another scan.
        self.action_button.configure(state="normal", text="Scan Again")
        self.uninstaller_button.configure(state="normal")
        self.scan_results = {}
        for option, data in self.checkboxes.items():
            data["widget"].configure(text=f"{option}", state="disabled")
            data["var"].set(False)

    def clean_error(self, error):
        """Updates the UI after a failed cleaning operation."""
        self.is_cleaning = False
        self.status_label.configure(text=f"Cleaning failed: {error}")
        self.action_button.configure(state="normal", text="Clean Selected")
        self.uninstaller_button.configure(state="normal")
        messagebox.showerror("Cleaning Error", f"An error occurred during cleaning:\n{error}")

    def run_uninstaller(self, command):
        """Launches an application's uninstaller using its command."""
        try:
            # Use Popen to run the uninstaller as a separate, non-blocking process.
            subprocess.Popen(command, shell=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch uninstaller for command:\n'{command}'\n\nError: {e}")

    def run(self):
        """Starts the main event loop for the application."""
        self.root.mainloop()

def main():
    """Main function to set up and run the application."""
    # Ensure the script is running on Windows.
    if os.name != 'nt':
        print("SysCleanX is designed for Windows systems only.")
        return
    
    # Request administrator privileges for proper functionality.
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            # Re-launch the script with elevated privileges.
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            sys.exit(0)
    except Exception:
        # Proceed without admin rights if elevation fails, functionality may be limited.
        print("Administrator privileges are required to run this application effectively.")
        pass
    
    app = SysCleanXApp()
    app.run()

# --- Script Entry Point ---
if __name__ == "__main__":
    main()