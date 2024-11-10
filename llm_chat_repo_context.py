import os
import shutil
import argparse
import logging
from datetime import datetime
from dulwich import porcelain
import tempfile
import time
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import tiktoken
from tkinter import filedialog

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def is_binary(file_path):
    try:
        with open(file_path, 'tr') as check_file:
            check_file.read()
            return False
    except:
        return True

def is_git_related(path):
    git_patterns = ['.git', '.gitignore', '.gitattributes']
    return any(pattern in path for pattern in git_patterns)

def should_exclude(file, ignore_git, exclude_license, exclude_readme):
    if ignore_git and is_git_related(file):
        return True
    if exclude_license and file.lower() in ['license', 'license.txt', 'license.md']:
        return True
    if exclude_readme and file.lower() in ['readme', 'readme.txt', 'readme.md']:
        return True
    return False

def get_structure(path, only_dirs=False, exclude=None, include=None, ignore_git=True, exclude_license=True, exclude_readme=False):
    structure = []
    for root, dirs, files in os.walk(path):
        if ignore_git and is_git_related(root):
            continue
        
        level = root.replace(path, '').count(os.sep)
        indent = '│   ' * (level - 1) + '├── '
        subindent = '│   ' * level + '├── '
        
        if only_dirs:
            structure.append(f'{indent}{os.path.basename(root)}/')
        else:
            structure.append(f'{indent}{os.path.basename(root)}/')
            for f in files:
                if should_exclude(f, ignore_git, exclude_license, exclude_readme):
                    continue
                if exclude and any(f.endswith(ext) for ext in exclude):
                    continue
                if include and not any(f.endswith(ext) for ext in include):
                    continue
                structure.append(f'{subindent}{f}')
    return '\n'.join(structure)

def convert_notebook_to_markdown(file_path):
    """Convert Jupyter notebook to markdown using jupytext."""
    try:
        import jupytext
        notebook = jupytext.read(file_path)
        return jupytext.writes(notebook, fmt='md')
    except Exception as e:
        logging.error(f"Error converting notebook {file_path}: {str(e)}")
        return None

def concatenate_files(path, exclude=None, include=None, ignore_git=True, exclude_license=True, exclude_readme=False):
    content = []
    file_positions = {}
    current_position = 0
    
    for root, dirs, files in sorted(os.walk(path)):
        if ignore_git and is_git_related(root):
            continue
        
        rel_path = os.path.relpath(root, path)
        if rel_path != '.':
            header = f"\n---{rel_path}/---\n"
        else:
            header = f"\n---/---\n"
        content.append(header)
        current_position += len(header)
        
        for file in sorted(files):
            if should_exclude(file, ignore_git, exclude_license, exclude_readme):
                continue
            file_path = os.path.join(root, file)
            
            # Handle different file types
            if file.endswith('.ipynb'):
                md_content = convert_notebook_to_markdown(file_path)
                if md_content is None:
                    continue
                file_content = md_content
            else:
                if is_binary(file_path):
                    continue
                if exclude and any(file.endswith(ext) for ext in exclude):
                    continue
                if include and not any(file.endswith(ext) for ext in include):
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                except Exception as e:
                    logging.error(f"Error reading file {file_path}: {str(e)}")
                    continue
            
            file_header = f"\n--{file}--\n"
            content.append(file_header)
            file_positions[os.path.join(rel_path, file)] = current_position
            current_position += len(file_header)
            content.append(file_content)
            current_position += len(file_content)
    
    return '\n'.join(content), file_positions

def safe_remove(path):
    def onerror(func, path, exc_info):
        logging.warning(f"Failed to remove {path}. Skipping.")
    
    if os.path.isdir(path):
        shutil.rmtree(path, onerror=onerror)
    elif os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            logging.warning(f"Failed to remove file {path}: {str(e)}")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configure window
        self.title("LLM Chat Repo Context")
        
        # Maximize the window
        self.update_idletasks()  # Update "requested size" from geometry manager
        max_width = self.winfo_screenwidth()
        max_height = self.winfo_screenheight()
        self.geometry(f"{max_width}x{max_height}+0+0")
        
        # Try to set the state to 'zoomed' on Windows
        if self.winfo_screenheight() < max_height:
            self.state('zoomed')

        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # Create main frame
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Create left frame for inputs
        self.left_frame = ctk.CTkFrame(self.main_frame, width=300)
        self.left_frame.pack(side="left", fill="y", padx=(0, 10))

        # Create right frame for output
        self.right_frame = ctk.CTkFrame(self.main_frame)
        self.right_frame.pack(side="right", fill="both", expand=True)

        self.setup_left_frame()
        self.setup_right_frame()

    def on_text_modified(self, event):
        self.text_display.edit_modified(False)  # Reset the modified flag
        self.update_counts()

    def setup_left_frame(self):
        # Load Session button
        self.load_session_button = ctk.CTkButton(self.left_frame, text="Load Session", command=self.load_session, fg_color="#8E44AD", hover_color="#9B59B6")
        self.load_session_button.pack(pady=(0, 20), padx=10)
        # Repository address
        self.repo_label = ctk.CTkLabel(self.left_frame, text="Repository address:")
        self.repo_label.pack(pady=(10, 5), padx=10, anchor="w")
        self.repo_entry = ctk.CTkEntry(self.left_frame, width=280)
        self.repo_entry.pack(pady=(0, 20), padx=10)

        # Options
        self.options_label = ctk.CTkLabel(self.left_frame, text="Options:", font=("", 16, "bold"))
        self.options_label.pack(pady=(0, 10), padx=10, anchor="w")

        # Concatenate switch
        self.concatenate_var = ctk.StringVar(value="off")
        self.concatenate_switch = ctk.CTkSwitch(self.left_frame, text="Append concatenated contents", variable=self.concatenate_var, onvalue="on", offvalue="off")
        self.concatenate_switch.pack(pady=(0, 10), padx=10, anchor="w")

        # Include file types
        self.include_label = ctk.CTkLabel(self.left_frame, text="Include file types:")
        self.include_label.pack(pady=(0, 5), padx=10, anchor="w")
        self.include_entry = ctk.CTkEntry(self.left_frame, width=280)
        self.include_entry.pack(pady=(0, 10), padx=10)

        # Exclude file types
        self.exclude_label = ctk.CTkLabel(self.left_frame, text="Exclude file types:")
        self.exclude_label.pack(pady=(0, 5), padx=10, anchor="w")
        self.exclude_entry = ctk.CTkEntry(self.left_frame, width=280)
        self.exclude_entry.pack(pady=(0, 10), padx=10)

        # Include git files switch
        self.include_git_var = ctk.StringVar(value="off")
        self.include_git_switch = ctk.CTkSwitch(self.left_frame, text="Include git files", variable=self.include_git_var, onvalue="on", offvalue="off")
        self.include_git_switch.pack(pady=(0, 10), padx=10, anchor="w")

        # Exclude Readme switch
        self.exclude_readme_var = ctk.StringVar(value="off")
        self.exclude_readme_switch = ctk.CTkSwitch(self.left_frame, text="Exclude Readme", variable=self.exclude_readme_var, onvalue="on", offvalue="off")
        self.exclude_readme_switch.pack(pady=(0, 10), padx=10, anchor="w")

        # Exclude license switch
        self.exclude_license_var = ctk.StringVar(value="on")
        self.exclude_license_switch = ctk.CTkSwitch(self.left_frame, text="Exclude license", variable=self.exclude_license_var, onvalue="on", offvalue="off")
        self.exclude_license_switch.pack(pady=(0, 20), padx=10, anchor="w")

        # Analyze button
        self.analyze_button = ctk.CTkButton(self.left_frame, text="Analyze Repository", command=self.analyze_repo, fg_color="#8E44AD", hover_color="#9B59B6")
        self.analyze_button.pack(pady=(0, 20), padx=10)

    def setup_right_frame(self):
        # Create a frame for the sidebar and text display
        self.display_frame = ctk.CTkFrame(self.right_frame)
        self.display_frame.pack(fill="both", expand=True)

        # Create a frame for the sidebar
        self.sidebar_frame = ctk.CTkFrame(self.display_frame, width=200)
        self.sidebar_frame.pack_forget()  # Initially hide the sidebar frame
        self.sidebar_frame.pack_propagate(False)  # Prevent frame from shrinking

        # Create the "Copy Selected" button and place it at the top of the sidebar frame
        self.copy_selected_button = ctk.CTkButton(self.sidebar_frame, text="Copy Selected", command=self.copy_selected_files, fg_color="#8E44AD", hover_color="#9B59B6")
        self.copy_selected_button.pack(side="top", pady=(0, 10), padx=10, fill="x")

        # Create the sidebar
        self.sidebar = ttk.Treeview(self.sidebar_frame, show="tree")
        self.sidebar.pack(side="top", fill="both", expand=True)
        self.sidebar_style = ttk.Style()
        self.sidebar_style.theme_use("default")
        self.sidebar_style.configure("Treeview", 
                                    background="#2b2b2b", 
                                    foreground="white", 
                                    fieldbackground="#2b2b2b",
                                    borderwidth=0)
        self.sidebar_style.map('Treeview', background=[('selected', '#1f538d')])
        self.sidebar_style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])

        # Create a frame for the buttons and text display
        self.text_frame = ctk.CTkFrame(self.display_frame)
        self.text_frame.pack(side="right", fill="both", expand=True, padx=(10, 0), pady=10)

        # Create a frame for the counts
        self.count_frame = ctk.CTkFrame(self.text_frame)
        self.count_frame.pack(fill="x", padx=10, pady=(10, 5))

        # Create labels for character and token counts
        self.char_count_label = ctk.CTkLabel(self.count_frame, text="Characters: 0")
        self.char_count_label.pack(side="left", padx=(0, 10))

        self.token_count_label = ctk.CTkLabel(self.count_frame, text="Tokens: 0")
        self.token_count_label.pack(side="left")

        # Create a frame for buttons
        self.button_frame = ctk.CTkFrame(self.text_frame)
        self.button_frame.pack(fill="x", padx=10, pady=(5, 5))

        # Create the copy button
        self.copy_button = ctk.CTkButton(self.button_frame, text="Copy", command=self.copy_text, fg_color="#8E44AD", hover_color="#9B59B6")
        self.copy_button.pack(side="left", padx=(0, 5))

        # Create the save button
        self.save_button = ctk.CTkButton(self.button_frame, text="Save", command=self.save_changes, fg_color="#8E44AD", hover_color="#9B59B6")
        self.save_button.pack(side="left")

        # Create the text display
        self.text_display = ctk.CTkTextbox(self.text_frame, wrap="word")
        self.text_display.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        # Bind the update_counts method to key release and mouse release events
        self.text_display.bind("<KeyRelease>", self.update_counts)
        self.text_display.bind("<ButtonRelease-1>", self.update_counts)

    def save_changes(self):
        try:
            content = self.text_display.get("1.0", "end-1c")
            with open(self.current_output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            self.show_message("Changes saved successfully!")
            self.update_counts()
        except Exception as e:
            self.show_error(f"An error occurred while saving: {str(e)}")

    def show_message(self, message):
        message_window = ctk.CTkToplevel(self)
        message_window.title("Message")
        message_window.attributes('-topmost', True)
        
        # Set the desired size
        width = 500
        height = 200
        
        # Center the window on the screen
        screen_width = message_window.winfo_screenwidth()
        screen_height = message_window.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        message_window.geometry(f"{width}x{height}+{x}+{y}")
        
        message_label = ctk.CTkLabel(message_window, text=message, wraplength=460, font=("Arial", 12))
        message_label.pack(pady=15, padx=15, expand=True)
        
        ok_button = ctk.CTkButton(message_window, text="OK", command=message_window.destroy, width=80, height=25, font=("Arial", 11))
        ok_button.pack(pady=10)
        
        # Wait for the window to be created and then update its size
        message_window.update()
        message_window.minsize(width, height)
        message_window.maxsize(width, height)
        
        # Lift the window to the top
        message_window.lift()
        message_window.focus_force()

    def copy_selected_files(self):
        selected_items = self.sidebar.selection()
        if not selected_items:
            self.show_message("No files selected")
            return

        copied_content = []
        content = self.text_display.get("1.0", "end-1c")

        for item in selected_items:
            parts = item.split('/')
            search_text = parts[-1]
            
            if len(parts) == 1:  # top-level folder
                search_pattern = f"---{search_text}---"
            elif '.' in search_text:  # file
                search_pattern = f"--{search_text}--"
            else:  # subfolder
                search_pattern = f"---{search_text}/---"
            
            start_index = content.find(search_pattern)
            if start_index != -1:
                content_start = start_index + len(search_pattern)
                next_file_index = content.find("\n--", content_start)
                next_folder_index = content.find("\n---", content_start)
                
                if next_file_index != -1 and (next_folder_index == -1 or next_file_index < next_folder_index):
                    end_index = next_file_index
                elif next_folder_index != -1:
                    end_index = next_folder_index
                else:
                    end_index = len(content)
                
                file_content = content[content_start:end_index].strip()
                copied_content.append(f"{search_pattern}\n{file_content}")

        if copied_content:
            full_content = "\n\n".join(copied_content)
            self.clipboard_clear()
            self.clipboard_append(full_content)
            self.clipboard_get()  # For Linux
            self.show_message(f"Content of {len(selected_items)} file(s) copied to clipboard")
        else:
            self.show_message("No content found for selected files")

    def show_error(self, message):
        error_window = ctk.CTkToplevel(self)
        error_window.title("Error")
        error_window.geometry("400x300")
        error_window.attributes('-topmost', True)  # Makes the window stay on top
        
        # Center the window on the screen
        error_window.update_idletasks()
        width = error_window.winfo_width()
        height = error_window.winfo_height()
        x = (error_window.winfo_screenwidth() // 2) - (width // 2)
        y = (error_window.winfo_screenheight() // 2) - (height // 2)
        error_window.geometry('{}x{}+{}+{}'.format(width, height, x, y))
        
        error_label = ctk.CTkLabel(error_window, text=message, wraplength=350, font=("Arial", 14))
        error_label.pack(pady=20, padx=20, expand=True)
        
        ok_button = ctk.CTkButton(error_window, text="OK", command=error_window.destroy, width=100, height=30, font=("Arial", 12))
        ok_button.pack(pady=10)

    def count_tokens(self, text):
        try:
            encoding = tiktoken.encoding_for_model("gpt-4")
            return len(encoding.encode(text))
        except Exception as e:
            logging.error(f"Error counting tokens: {str(e)}")
            return 0

    def update_counts(self, event=None):
        text = self.text_display.get("1.0", "end-1c")
        char_count = len(text)
        token_count = self.count_tokens(text)
        self.char_count_label.configure(text=f"Characters: {char_count}")
        self.token_count_label.configure(text=f"Tokens: {token_count}")

    def load_session(self):
        ai_chat_repo_helper_dir = os.path.join(os.getcwd(), "LLM_Chat_Repo_Context")
        session_folder = filedialog.askdirectory(title="Select Session Folder", initialdir=ai_chat_repo_helper_dir)
        if session_folder:
            session_name = os.path.basename(session_folder)
            analysis_file = os.path.join(session_folder, f"{session_name}.txt")
            if os.path.exists(analysis_file):
                with open(analysis_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.text_display.delete("1.0", "end")
                self.text_display.insert("1.0", content)
                self.current_session_folder = session_folder
                self.current_output_file = analysis_file
                self.update_counts()
                self.show_message("Session loaded successfully!")
            else:
                self.show_error(f"Invalid session folder: {session_name}.txt not found.")

    def analyze_repo(self):
        repo_url = self.repo_entry.get()
        if not repo_url:
            self.show_error("Please enter a repository URL")
            return

        # Prepare arguments
        args = argparse.Namespace(
            input=repo_url,
            directories=False,
            exclude=self.exclude_entry.get().split() if self.exclude_entry.get() else None,
            include=self.include_entry.get().split() if self.include_entry.get() else None,
            concatenate=self.concatenate_var.get() == "on",
            include_git=self.include_git_var.get() == "on",
            include_license=self.exclude_license_var.get() == "off",
            exclude_readme=self.exclude_readme_var.get() == "on"
        )

        # Clear current session data
        self.current_session_folder = None
        self.current_output_file = None

        # Run analysis
        try:
            self.run_analysis(args)
        except Exception as e:
            self.show_error(f"An error occurred: {str(e)}")

    def run_analysis(self, args):
        # Normalize the input URL
        repo_url = args.input
        if not repo_url.endswith('.git'):
            repo_url += '.git'

        repo_name = repo_url.split('/')[-1].replace('.git', '')
        session_name = f"{repo_name}_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}"
        
        # Create the session folder inside AI_Chat_Repo_Helper
        ai_chat_repo_helper_dir = os.path.join(os.getcwd(), "AI_Chat_Repo_Helper")
        self.current_session_folder = os.path.join(ai_chat_repo_helper_dir, session_name)
        os.makedirs(self.current_session_folder, exist_ok=True)
        
        # Name the text file the same as the session folder
        self.current_output_file = os.path.join(self.current_session_folder, f"{session_name}.txt")

        temp_dir = tempfile.mkdtemp()
        try:
            logging.info(f"Cloning repository: {repo_url}")
            porcelain.clone(repo_url, temp_dir)
            
            logging.info("Generating folder structure")
            structure = get_structure(
                temp_dir, 
                args.directories, 
                args.exclude, 
                args.include, 
                not args.include_git, 
                not args.include_license, 
                args.exclude_readme
            )
            
            content = f"Folder structure:\n{structure}\n"
            
            if args.concatenate:
                logging.info("Concatenating file contents")
                concat_content, file_positions = concatenate_files(
                    temp_dir, 
                    args.exclude, 
                    args.include, 
                    not args.include_git, 
                    not args.include_license, 
                    args.exclude_readme
                )
                content += f"\nConcatenated content:\n{concat_content}"
            else:
                file_positions = {}
            
            # Clear previous content and sidebar
            self.text_display.delete("1.0", "end")
            self.sidebar.pack_forget()

            # Display content in the text widget
            self.text_display.delete("1.0", "end")
            self.text_display.insert("1.0", content)
            self.update_counts()  # Update counts after inserting text
            
            # Update sidebar if concatenation was selected
            if args.concatenate:
                self.update_sidebar(file_positions)
            else:
                self.sidebar.pack_forget()
                self.text_frame.pack(side="left", fill="both", expand=True)
            
            # Save content to file
            with open(self.current_output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logging.info(f"Output written to {self.current_output_file}")
            self.show_message(f"Analysis completed. Session saved in:\n{self.current_session_folder}")
            
        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
            raise
        finally:
            logging.info("Cleaning up temporary directory")
            time.sleep(1)
            safe_remove(temp_dir)

    def update_sidebar(self, file_positions):
        if not file_positions:
            self.sidebar_frame.pack_forget()  # Hide sidebar if there's no content
            return

        # Show and update sidebar if there's content
        self.sidebar_frame.pack(side="left", fill="y", padx=(10, 0), pady=10)
        self.text_frame.pack(side="right", fill="both", expand=True, padx=(10, 0), pady=10)

        self.sidebar.delete(*self.sidebar.get_children())
        
        # Make sure the sidebar is visible and fills the frame
        self.sidebar.pack(side="top", fill="both", expand=True)

        for path, position in file_positions.items():
            parts = path.split(os.sep)
            current_path = ""
            for i, part in enumerate(parts):
                current_path += part if i == 0 else f"/{part}"
                parent_path = "/".join(parts[:i]) if i > 0 else ""
                
                if not self.sidebar.exists(current_path):
                    self.sidebar.insert(parent_path, "end", current_path, text=part, open=True)

        self.sidebar.bind("<<TreeviewSelect>>", self.scroll_to_file)

        # Ensure the sidebar frame maintains its width
        self.sidebar_frame.configure(width=200)
        self.sidebar_frame.pack_propagate(False)


    def scroll_to_file(self, event):
        selected_item = self.sidebar.selection()[0]
        parts = selected_item.split('/')
        search_text = parts[-1]  # Get the last part of the path
        
        if len(parts) == 1:  # It's a top-level folder
            search_pattern = f"---{search_text}---"
        elif '.' in search_text:  # It's a file
            search_pattern = f"--{search_text}--"
        else:  # It's a subfolder
            search_pattern = f"---{search_text}/---"
        
        content = self.text_display.get("1.0", "end-1c")
        start_index = content.find(search_pattern)
        
        if start_index != -1:
            line_number = content.count('\n', 0, start_index) + 1
            self.text_display.see(f"{line_number}.0")
            self.text_display.tag_remove("highlight", "1.0", "end")
            self.text_display.tag_add("highlight", f"{line_number}.0", f"{line_number}.0 lineend")
            self.text_display.tag_config("highlight", background="#8E44AD", foreground="white")
            
            # Ensure the highlighted line is visible
            self.text_display.after(100, lambda: self.text_display.see(f"{line_number}.0"))

    def copy_text(self):
        selected_text = self.text_display.selection_get() if self.text_display.tag_ranges("sel") else self.text_display.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(selected_text)
        self.clipboard_get()  # For Linux, this is needed to push to system clipboard

def main_gui():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main_gui()
