import os
import shutil
import argparse
import logging
import sys
from datetime import datetime
from dulwich import porcelain
import tempfile
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel, QLineEdit,
    QCheckBox, QTextEdit, QVBoxLayout, QHBoxLayout, QFileDialog, QTreeWidget,
    QTreeWidgetItem, QMessageBox, QSplitter, QProgressDialog, QTabWidget,
    QRadioButton, QButtonGroup, QFrame, QToolButton, QStyle
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QIcon, QFont
import tiktoken

# Set up logging
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

# Repository Analysis Thread
class AnalysisThread(QThread):
    progress_signal = pyqtSignal(str, int)
    finished_signal = pyqtSignal(str, dict, str)
    error_signal = pyqtSignal(str)

    def __init__(self, source_path, args, session_folder, output_file, is_local=False, pat=None):
        super().__init__()
        self.source_path = source_path
        self.args = args
        self.session_folder = session_folder
        self.output_file = output_file
        self.is_local = is_local
        self.pat = pat

    def run(self):
        temp_dir = None
        try:
            if self.is_local:
                # Using local folder directly
                folder_path = self.source_path
                self.progress_signal.emit("Analyzing local folder...", 25)
            else:
                # Clone the repository to a temporary directory
                temp_dir = tempfile.mkdtemp()
                self.progress_signal.emit("Cloning repository...", 25)
                logging.info(f"Cloning repository: {self.source_path}")

                # Add authentication if PAT is provided
                if self.pat:
                    # For GitHub, insert PAT into URL
                    if 'github.com' in self.source_path:
                        repo_url = self.source_path.replace('https://', f'https://{self.pat}@')
                    else:
                        repo_url = self.source_path
                else:
                    repo_url = self.source_path

                try:
                    porcelain.clone(repo_url, temp_dir)
                except Exception as e:
                    self.error_signal.emit(f"Failed to clone repository: {str(e)}")
                    safe_remove(temp_dir)
                    return

                folder_path = temp_dir

            self.progress_signal.emit("Generating folder structure...", 50)
            logging.info("Generating folder structure")
            structure = get_structure(
                folder_path,
                self.args.directories,
                self.args.exclude,
                self.args.include,
                not self.args.include_git,
                not self.args.include_license,
                self.args.exclude_readme
            )

            content = f"Folder structure:\n{structure}\n"
            file_positions = {}

            if self.args.concatenate:
                self.progress_signal.emit("Concatenating file contents...", 75)
                logging.info("Concatenating file contents")
                concat_content, file_positions = concatenate_files(
                    folder_path,
                    self.args.exclude,
                    self.args.include,
                    not self.args.include_git,
                    not self.args.include_license,
                    self.args.exclude_readme
                )
                content += f"\nConcatenated content:\n{concat_content}"

            self.progress_signal.emit("Saving results...", 90)
            # Save content to file
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(content)

            logging.info(f"Output written to {self.output_file}")
            self.finished_signal.emit(content, file_positions, self.session_folder)

        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
            self.error_signal.emit(str(e))
        finally:
            if temp_dir:
                logging.info("Cleaning up temporary directory")
                time.sleep(1)
                safe_remove(temp_dir)

class App(QMainWindow):
    def __init__(self):
        super().__init__()

        # Main window configuration
        self.setWindowTitle("LLM Chat Repo Context")
        self.resize(1400, 900)

        # Central widget and main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # Create left panel for controls
        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_panel.setFixedWidth(300)

        # Create right panel (will contain splitter for tree and text)
        self.right_panel = QWidget()
        self.right_layout = QHBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(0, 0, 0, 0)

        # Add panels to main layout
        self.main_layout.addWidget(self.left_panel)
        self.main_layout.addWidget(self.right_panel)

        # Setup the left panel contents
        self.setup_left_panel()

        # Setup the right panel contents
        self.setup_right_panel()

        # Initialize state variables
        self.current_session_folder = None
        self.current_output_file = None
        self.file_positions = {}
        self.progress_dialog = None
        self.local_folder_path = None

        # Setup dark theme
        self.setup_dark_theme()

    def setup_dark_theme(self):
        # Set dark theme using Qt stylesheets
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
                font-family: Arial, sans-serif;
            }
            QPushButton {
                background-color: #8E44AD;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 14px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #9B59B6;
            }
            QPushButton:pressed {
                background-color: #7D3C98;
            }
            QToolButton {
                background-color: #8E44AD;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px;
                min-height: 24px;
                min-width: 24px;
            }
            QToolButton:hover {
                background-color: #9B59B6;
            }
            QToolButton:pressed {
                background-color: #7D3C98;
            }
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: white;
                min-height: 25px;
            }
            QTextEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                color: white;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                padding: 5px;
                selection-background-color: #1f538d;
            }
            QTreeWidget {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                color: white;
                selection-background-color: #1f538d;
                alternate-background-color: #333333;
                outline: none;
            }
            QTreeWidget::item {
                min-height: 25px;
                border-bottom: 1px solid #444444;
            }
            QTreeWidget::item:selected {
                background-color: #1f538d;
            }
            QTreeWidget::indicator {
                width: 16px;
                height: 16px;
            }
            QTreeWidget::indicator:checked {
                image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>');
                background-color: #8E44AD;
                border: 1px solid #8E44AD;
                border-radius: 3px;
            }
            QTreeWidget::indicator:unchecked {
                background-color: #444444;
                border: 1px solid #555555;
                border-radius: 3px;
            }
            QLabel {
                font-size: 14px;
            }
            QCheckBox, QRadioButton {
                spacing: 8px;
                min-height: 25px;
            }
            QCheckBox::indicator, QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #555555;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                background-color: #8E44AD;
                border: 2px solid #8E44AD;
            }
            QCheckBox::indicator:checked {
                image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>');
            }
            QRadioButton::indicator {
                border-radius: 9px;
            }
            QRadioButton::indicator:checked {
                image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 24 24" fill="white"></svg>');
            }
            QCheckBox::indicator:unchecked:hover, QRadioButton::indicator:unchecked:hover {
                border-color: #9B59B6;
            }
            QSplitter::handle {
                background-color: #444444;
                width: 2px;
            }
            QScrollBar:vertical {
                border: none;
                background: #3c3c3c;
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                border: none;
                background: #3c3c3c;
                height: 12px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #555555;
                border-radius: 3px;
                min-width: 20px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QProgressDialog {
                background-color: #2b2b2b;
                border: 1px solid #555555;
                border-radius: 5px;
            }
            QProgressDialog QProgressBar {
                border: 1px solid #555555;
                border-radius: 3px;
                background-color: #3c3c3c;
                text-align: center;
                color: white;
            }
            QProgressDialog QProgressBar::chunk {
                background-color: #8E44AD;
                width: 20px;
            }
            QProgressDialog QPushButton {
                min-width: 80px;
                min-height: 30px;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #2b2b2b;
            }
            QTabWidget::tab-bar {
                alignment: left;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #8E44AD;
                border: 1px solid #8E44AD;
            }
            QTabBar::tab:hover:!selected {
                background-color: #444444;
            }
            QFrame[frameShape="4"] { /* HLine */
                background-color: #555555;
                max-height: 1px;
                border: none;
            }
            .ButtonGroup {
                background-color: #363636;
                border-radius: 5px;
                padding: 2px;
            }
        """)

    def setup_left_panel(self):
        # Application title
        title_label = QLabel("LLM Chat Repo Context")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #8E44AD; padding: 10px 0;")
        self.left_layout.addWidget(title_label)
        self.left_layout.addSpacing(5)

        # Load Session button
        self.load_session_button = QPushButton("Load Session")
        self.load_session_button.setIcon(QIcon.fromTheme("folder-open"))
        self.load_session_button.clicked.connect(self.load_session)
        self.left_layout.addWidget(self.load_session_button)
        self.left_layout.addSpacing(10)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        self.left_layout.addWidget(separator)
        self.left_layout.addSpacing(10)

        # Source selection section
        source_label = QLabel("Source:")
        source_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.left_layout.addWidget(source_label)

        # Radio buttons for source selection
        self.source_group = QButtonGroup(self)

        self.repo_radio = QRadioButton("Remote Repository")
        self.repo_radio.setChecked(True)
        self.repo_radio.toggled.connect(self.toggle_source_input)
        self.left_layout.addWidget(self.repo_radio)
        self.source_group.addButton(self.repo_radio)

        self.local_radio = QRadioButton("Local Folder")
        self.local_radio.toggled.connect(self.toggle_source_input)
        self.left_layout.addWidget(self.local_radio)
        self.source_group.addButton(self.local_radio)
        self.left_layout.addSpacing(5)

        # Source input container (will contain either repo URL or local folder path)
        self.source_container = QWidget()
        self.source_layout = QVBoxLayout(self.source_container)
        self.source_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.addWidget(self.source_container)

        # Repository address (default view)
        self.repo_input_widget = QWidget()
        self.repo_input_layout = QVBoxLayout(self.repo_input_widget)
        self.repo_input_layout.setContentsMargins(0, 0, 0, 0)
        self.repo_label = QLabel("Repository URL:")
        self.repo_entry = QLineEdit()
        self.repo_entry.setPlaceholderText("Enter GitHub repo URL")

        self.pat_label = QLabel("Personal Access Token (Optional):")
        self.pat_entry = QLineEdit()
        self.pat_entry.setPlaceholderText("For private repositories")
        self.pat_entry.setEchoMode(QLineEdit.EchoMode.Password)

        self.repo_input_layout.addWidget(self.repo_label)
        self.repo_input_layout.addWidget(self.repo_entry)
        self.repo_input_layout.addWidget(self.pat_label)
        self.repo_input_layout.addWidget(self.pat_entry)
        self.repo_input_layout.addWidget(self.repo_entry)

        # Local folder selection
        self.local_input_widget = QWidget()
        self.local_input_layout = QVBoxLayout(self.local_input_widget)
        self.local_input_layout.setContentsMargins(0, 0, 0, 0)

        self.local_path_label = QLabel("Local folder path:")
        self.local_path_display = QLineEdit()
        self.local_path_display.setReadOnly(True)
        self.local_path_display.setPlaceholderText("No folder selected")

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_local_folder)

        self.local_input_layout.addWidget(self.local_path_label)
        self.local_input_layout.addWidget(self.local_path_display)
        self.local_input_layout.addWidget(self.browse_button)

        # Add repository input to source container (default view)
        self.source_layout.addWidget(self.repo_input_widget)
        self.local_input_widget.hide()  # Initially hide the local input widget

        self.left_layout.addSpacing(10)

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        self.left_layout.addWidget(separator2)
        self.left_layout.addSpacing(10)

        # Options section
        self.options_label = QLabel("Options:")
        self.options_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.left_layout.addWidget(self.options_label)
        self.left_layout.addSpacing(10)

        # Concatenate checkbox
        self.concatenate_checkbox = QCheckBox("Append concatenated contents")
        self.left_layout.addWidget(self.concatenate_checkbox)
        self.left_layout.addSpacing(10)

        # Include file types
        self.include_label = QLabel("Include file types:")
        self.left_layout.addWidget(self.include_label)
        self.include_entry = QLineEdit()
        self.include_entry.setPlaceholderText("e.g. .py .js .java")
        self.left_layout.addWidget(self.include_entry)
        self.left_layout.addSpacing(10)

        # Exclude file types
        self.exclude_label = QLabel("Exclude file types:")
        self.left_layout.addWidget(self.exclude_label)
        self.exclude_entry = QLineEdit()
        self.exclude_entry.setPlaceholderText("e.g. .log .tmp .bak")
        self.left_layout.addWidget(self.exclude_entry)
        self.left_layout.addSpacing(10)

        # Checkboxes for various options
        self.include_git_checkbox = QCheckBox("Include git files")
        self.left_layout.addWidget(self.include_git_checkbox)

        self.exclude_readme_checkbox = QCheckBox("Exclude Readme")
        self.left_layout.addWidget(self.exclude_readme_checkbox)

        self.exclude_license_checkbox = QCheckBox("Exclude license")
        self.exclude_license_checkbox.setChecked(True)
        self.left_layout.addWidget(self.exclude_license_checkbox)
        self.left_layout.addSpacing(20)

        # Analyze button
        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                padding: 10px;
                background-color: #8E44AD;
                font-size: 15px;
            }
        """)
        self.analyze_button.clicked.connect(self.analyze_source)
        self.left_layout.addWidget(self.analyze_button)

        # Add spacer to push everything to the top
        self.left_layout.addStretch()

        # Add a version label at the bottom
        version_label = QLabel("v1.3.0")
        version_label.setStyleSheet("color: #777777; font-size: 12px;")
        version_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.left_layout.addWidget(version_label)

    def toggle_source_input(self):
        # Show or hide the appropriate input widget based on radio button selection
        if self.repo_radio.isChecked():
            self.repo_input_widget.show()
            self.local_input_widget.hide()
            self.source_layout.addWidget(self.repo_input_widget)
        else:
            self.repo_input_widget.hide()
            self.local_input_widget.show()
            self.source_layout.addWidget(self.local_input_widget)

    def browse_local_folder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Analyze",
            os.path.expanduser("~")
        )

        if folder_path:
            self.local_folder_path = folder_path
            # Show only the folder name in the text field for cleaner UI
            folder_name = os.path.basename(folder_path)
            parent_dir = os.path.basename(os.path.dirname(folder_path))
            display_path = f"{parent_dir}/{folder_name}" if parent_dir else folder_name

            # Set tooltip to show full path on hover
            self.local_path_display.setToolTip(folder_path)
            self.local_path_display.setText(display_path)

    def setup_right_panel(self):
        # Create a splitter to divide tree view and text display
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_layout.addWidget(self.splitter)

        # Create a container for the tree and buttons
        self.tree_container = QWidget()
        self.tree_layout = QVBoxLayout(self.tree_container)
        self.tree_layout.setContentsMargins(0, 0, 0, 0)

        # Create tree toolbar with compact buttons
        self.tree_toolbar = QWidget()
        self.tree_toolbar.setProperty("class", "ButtonGroup")
        self.tree_toolbar_layout = QHBoxLayout(self.tree_toolbar)
        self.tree_toolbar_layout.setContentsMargins(5, 5, 5, 5)
        self.tree_toolbar_layout.setSpacing(5)

        # Create compact buttons with icons
        self.copy_selected_button = QToolButton()
        self.copy_selected_button.setText("Copy Files")
        self.copy_selected_button.setToolTip("Copy selected files to clipboard")
        self.copy_selected_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_selected_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_selected_button.clicked.connect(self.copy_selected_files)
        self.tree_toolbar_layout.addWidget(self.copy_selected_button)

        self.select_all_button = QToolButton()
        self.select_all_button.setToolTip("Select all files")
        self.select_all_button.setIcon(QIcon.fromTheme("edit-select-all"))
        self.select_all_button.clicked.connect(self.select_all_files)
        self.tree_toolbar_layout.addWidget(self.select_all_button)

        self.deselect_all_button = QToolButton()
        self.deselect_all_button.setToolTip("Deselect all files")
        self.deselect_all_button.setIcon(QIcon.fromTheme("edit-clear"))
        self.deselect_all_button.clicked.connect(self.deselect_all_files)
        self.tree_toolbar_layout.addWidget(self.deselect_all_button)

        self.tree_toolbar_layout.addStretch()

        # Add tree toolbar to main layout
        self.tree_layout.addWidget(self.tree_toolbar)

        # Tree widget for file structure
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setColumnCount(1)
        self.file_tree.itemClicked.connect(self.on_tree_item_clicked)
        self.file_tree.itemChanged.connect(self.on_item_changed)  # Connect to the itemChanged signal
        self.file_tree.setMinimumWidth(250)
        self.file_tree.setAlternatingRowColors(True)

        # Add tree to the container
        self.tree_layout.addWidget(self.file_tree)

        # Add tree container to splitter
        self.splitter.addWidget(self.tree_container)
        self.tree_container.hide()  # Initially hidden

        # Create a container for text display and buttons
        self.text_container = QWidget()
        self.text_layout = QVBoxLayout(self.text_container)
        self.text_layout.setContentsMargins(0, 0, 0, 0)

        # Create central toolbar for text display
        self.text_actions_frame = QWidget()
        self.text_actions_layout = QVBoxLayout(self.text_actions_frame)
        self.text_actions_layout.setContentsMargins(0, 0, 0, 10)

        # Create a centered toolbar for text actions
        self.text_toolbar = QWidget()
        self.text_toolbar.setProperty("class", "ButtonGroup")
        self.text_toolbar.setFixedWidth(350)  # Set a fixed width for the toolbar
        self.text_toolbar_layout = QHBoxLayout(self.text_toolbar)
        self.text_toolbar_layout.setContentsMargins(5, 5, 5, 5)
        self.text_toolbar_layout.setSpacing(5)

        # Create compact buttons with icons
        self.copy_all_button = QToolButton()
        self.copy_all_button.setText("Copy All")
        self.copy_all_button.setToolTip("Copy all text to clipboard")
        self.copy_all_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_all_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_all_button.clicked.connect(self.copy_text)
        self.text_toolbar_layout.addWidget(self.copy_all_button)

        self.copy_selection_button = QToolButton()
        self.copy_selection_button.setText("Copy Selection")
        self.copy_selection_button.setToolTip("Copy selected text to clipboard")
        self.copy_selection_button.setIcon(QIcon.fromTheme("edit-cut"))
        self.copy_selection_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_selection_button.clicked.connect(self.copy_selection)
        self.text_toolbar_layout.addWidget(self.copy_selection_button)

        self.save_button = QToolButton()
        self.save_button.setText("Save")
        self.save_button.setToolTip("Save changes")
        self.save_button.setIcon(QIcon.fromTheme("document-save"))
        self.save_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.save_button.clicked.connect(self.save_changes)
        self.text_toolbar_layout.addWidget(self.save_button)

        # Center the toolbar in the frame
        self.text_actions_layout.addWidget(self.text_toolbar, 0, Qt.AlignmentFlag.AlignCenter)

        # Add the toolbar to the text layout
        self.text_layout.addWidget(self.text_actions_frame)

        # Create a frame for the counts that will be right-aligned
        self.count_frame = QWidget()
        self.count_layout = QHBoxLayout(self.count_frame)
        self.count_layout.setContentsMargins(0, 0, 0, 5)

        # Add character and token count labels
        self.char_count_label = QLabel("Characters: 0")
        self.count_layout.addWidget(self.char_count_label)

        self.token_count_label = QLabel("Tokens: 0")
        self.count_layout.addWidget(self.token_count_label)

        self.count_layout.addStretch()

        # Add count frame to text layout
        self.text_layout.addWidget(self.count_frame, 0, Qt.AlignmentFlag.AlignRight)

        # Add text edit for displaying content
        self.text_display = QTextEdit()
        self.text_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.text_display.textChanged.connect(self.update_counts)
        self.text_display.setTabStopDistance(QFont("Consolas").pointSizeF() * 4)
        self.text_layout.addWidget(self.text_display)

        # Add text container to splitter
        self.splitter.addWidget(self.text_container)

        # Set splitter proportions (25% tree, 75% text)
        self.splitter.setSizes([250, 750])

    def on_tree_item_clicked(self, item, column):
        # Navigate to the file in the text display
        self.scroll_to_file(item)

    def on_item_changed(self, item, column):
        # Ensure we're not triggering recursive updates
        if hasattr(self, '_updating_items') and self._updating_items:
            return

        self._updating_items = True

        # Get the state being propagated
        is_checked = item.checkState(0) == Qt.CheckState.Checked

        # Propagate check state to all children
        self.update_children_check_state(item, is_checked)

        # Update parent check state based on children
        self.update_parent_check_state(item.parent())

        self._updating_items = False

    def update_children_check_state(self, parent_item, checked):
        if parent_item is None:
            return

        check_state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked

        # Update all child items
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child.setCheckState(0, check_state)
            # Recursively update grandchildren
            self.update_children_check_state(child, checked)

    def update_parent_check_state(self, parent_item):
        if parent_item is None:
            return

        # Count checked and total children
        total_children = parent_item.childCount()
        checked_children = sum(1 for i in range(total_children)
                             if parent_item.child(i).checkState(0) == Qt.CheckState.Checked)

        # Update parent state based on children
        if checked_children == 0:
            parent_item.setCheckState(0, Qt.CheckState.Unchecked)
        elif checked_children == total_children:
            parent_item.setCheckState(0, Qt.CheckState.Checked)
        else:
            parent_item.setCheckState(0, Qt.CheckState.PartiallyChecked)

        # Continue up the tree
        self.update_parent_check_state(parent_item.parent())

    def select_all_files(self):
        self._updating_items = True
        # Update root items
        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item.setCheckState(0, Qt.CheckState.Checked)
            self.update_children_check_state(item, True)
        self._updating_items = False

    def deselect_all_files(self):
        self._updating_items = True
        # Update root items
        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            self.update_children_check_state(item, False)
        self._updating_items = False

    def load_session(self):
        ai_chat_repo_helper_dir = os.path.join(os.getcwd(), "LLM_Chat_Repo_Context")
        os.makedirs(ai_chat_repo_helper_dir, exist_ok=True)

        session_folder = QFileDialog.getExistingDirectory(
            self,
            "Select Session Folder",
            ai_chat_repo_helper_dir
        )

        if session_folder:
            session_name = os.path.basename(session_folder)
            analysis_file = os.path.join(session_folder, f"{session_name}.txt")

            if os.path.exists(analysis_file):
                with open(analysis_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                self.text_display.clear()
                self.text_display.setPlainText(content)
                self.current_session_folder = session_folder
                self.current_output_file = analysis_file
                self.update_counts()

                # Check if the session includes concatenated files
                if "Concatenated content:" in content:
                    self.update_sidebar_from_content(content)
                else:
                    self.tree_container.hide()

                self.show_message("Session loaded successfully!")
            else:
                self.show_error(f"Invalid session folder: {session_name}.txt not found.")

    def update_sidebar_from_content(self, content):
        # Extract file positions from content
        self.file_positions = {}
        lines = content.split('\n')

        current_folder = ""
        for i, line in enumerate(lines):
            if line.startswith("---") and line.endswith("---"):
                # This is a folder marker
                folder_name = line.strip('-')
                current_folder = folder_name
            elif line.startswith("--") and line.endswith("--"):
                # This is a file marker
                file_name = line.strip('-')
                if current_folder == "/":
                    path = file_name
                else:
                    path = os.path.join(current_folder, file_name)

                # Store the position (line number)
                self.file_positions[path] = i

        if self.file_positions:
            self.update_sidebar(self.file_positions)
            self.tree_container.show()

    def analyze_source(self):
        # Determine whether to analyze a remote repo or local folder
        is_local = self.local_radio.isChecked()

        if is_local:
            source_path = self.local_folder_path
            if not source_path or not os.path.isdir(source_path):
                self.show_error("Please select a valid local folder")
                return
        else:
            source_path = self.repo_entry.text()
            if not source_path:
                self.show_error("Please enter a repository URL")
                return

        # Prepare arguments
        args = argparse.Namespace(
            input=source_path,
            directories=False,
            exclude=self.exclude_entry.text().split() if self.exclude_entry.text() else None,
            include=self.include_entry.text().split() if self.include_entry.text() else None,
            concatenate=self.concatenate_checkbox.isChecked(),
            include_git=self.include_git_checkbox.isChecked(),
            include_license=not self.exclude_license_checkbox.isChecked(),
            exclude_readme=self.exclude_readme_checkbox.isChecked()
        )

        # Clear current session data
        self.current_session_folder = None
        self.current_output_file = None

        # Run analysis
        try:
            self.start_analysis(args, is_local)
        except Exception as e:
            self.show_error(f"An error occurred: {str(e)}")

    def start_analysis(self, args, is_local=False):
        source_path = args.input

        # Create a session name based on the source type
        if is_local:
            # Use the folder name for local folders
            folder_name = os.path.basename(source_path)
            session_name = f"{folder_name}_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}"
        else:
            # Use repo name for remote repositories
            if not source_path.endswith('.git') and '://' in source_path:
                source_path += '.git'
            repo_name = source_path.split('/')[-1].replace('.git', '')
            session_name = f"{repo_name}_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}"

        # Create the session folder
        ai_chat_repo_helper_dir = os.path.join(os.getcwd(), "LLM_Chat_Repo_Context")
        os.makedirs(ai_chat_repo_helper_dir, exist_ok=True)

        self.current_session_folder = os.path.join(ai_chat_repo_helper_dir, session_name)
        os.makedirs(self.current_session_folder, exist_ok=True)

        # Name the text file the same as the session folder
        self.current_output_file = os.path.join(self.current_session_folder, f"{session_name}.txt")

        # Create progress dialog
        self.progress_dialog = QProgressDialog(
            "Analyzing...", "Cancel", 0, 100, self
        )
        self.progress_dialog.setWindowTitle("Analysis Progress")
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumSize(QSize(400, 100))
        # Start analysis thread
        pat = self.pat_entry.text() if hasattr(self, 'pat_entry') and not is_local else None
        self.analysis_thread = AnalysisThread(
            source_path, args, self.current_session_folder, self.current_output_file, is_local, pat
        )

        self.analysis_thread.progress_signal.connect(self.update_progress)
        self.analysis_thread.finished_signal.connect(self.analysis_completed)
        self.analysis_thread.error_signal.connect(self.handle_analysis_error)
        self.analysis_thread.start()

        self.progress_dialog.canceled.connect(self.analysis_thread.terminate)
        self.progress_dialog.show()

    def update_progress(self, message, value):
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)
            self.progress_dialog.setValue(value)

    def handle_analysis_error(self, error_message):
        if self.progress_dialog:
            self.progress_dialog.close()
        self.show_error(error_message)

    def analysis_completed(self, content, file_positions, session_folder):
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        # Update UI
        self.text_display.clear()
        self.text_display.setPlainText(content)
        self.update_counts()

        # Update file tree if we have file positions
        if file_positions:
            self.file_positions = file_positions
            self.update_sidebar(file_positions)
            self.tree_container.show()
        else:
            self.tree_container.hide()

        # Show success message
        self.show_message(f"Analysis completed. Session saved in:\n{session_folder}")

    def update_sidebar(self, file_positions):
        if not file_positions:
            self.tree_container.hide()
            return

        # Clear the tree
        self.file_tree.clear()

        # Disconnect signal temporarily to prevent events during tree building
        self.file_tree.itemChanged.disconnect(self.on_item_changed)

        # Create a dictionary to store tree items
        tree_items = {}

        # Add root item
        root_item = QTreeWidgetItem(self.file_tree, ["/"])
        root_item.setCheckState(0, Qt.CheckState.Unchecked)
        root_item.setFlags(root_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        root_item.setIcon(0, QIcon.fromTheme("folder"))
        tree_items["/"] = root_item

        # Add all other items
        for path in sorted(file_positions.keys()):
            parts = path.split(os.sep)

            # Handle the case where the path starts with "."
            if parts[0] == '.':
                parts = parts[1:]

            current_path = ""
            parent_item = root_item

            for i, part in enumerate(parts):
                if not part:  # Skip empty parts
                    continue

                if i < len(parts) - 1:  # This is a directory
                    current_path = current_path + "/" + part if current_path else part

                    if current_path not in tree_items:
                        # Create new directory item
                        item = QTreeWidgetItem(parent_item, [part])
                        item.setCheckState(0, Qt.CheckState.Unchecked)
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setIcon(0, QIcon.fromTheme("folder"))
                        tree_items[current_path] = item

                    parent_item = tree_items[current_path]
                else:  # This is a file
                    # Create file item
                    item = QTreeWidgetItem(parent_item, [part])
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

                    # Set an icon based on file extension
                    if part.endswith(('.py')):
                        item.setIcon(0, QIcon.fromTheme("text-x-python"))
                    elif part.endswith(('.js')):
                        item.setIcon(0, QIcon.fromTheme("text-x-javascript"))
                    elif part.endswith(('.html', '.htm')):
                        item.setIcon(0, QIcon.fromTheme("text-html"))
                    elif part.endswith(('.css')):
                        item.setIcon(0, QIcon.fromTheme("text-css"))
                    elif part.endswith(('.md')):
                        item.setIcon(0, QIcon.fromTheme("text-x-markdown"))
                    elif part.endswith(('.json')):
                        item.setIcon(0, QIcon.fromTheme("application-json"))
                    elif part.endswith(('.xml')):
                        item.setIcon(0, QIcon.fromTheme("application-xml"))
                    elif part.endswith(('.txt')):
                        item.setIcon(0, QIcon.fromTheme("text-plain"))
                    else:
                        item.setIcon(0, QIcon.fromTheme("text-x-generic"))

        # Expand all items
        self.file_tree.expandAll()

        # Reconnect signal
        self.file_tree.itemChanged.connect(self.on_item_changed)

        # Show the tree container
        self.tree_container.show()

    def scroll_to_file(self, item):
        # Get the full path of the item
        path = []
        current = item
        while current is not None:
            path.insert(0, current.text(0))
            current = current.parent()

        # Remove the root / if it exists
        if path and path[0] == "/":
            path = path[1:]

        # Construct the search pattern
        if len(path) > 1:  # It's a file inside a directory
            search_pattern = f"--{path[-1]}--"
        elif '.' in path[0]:  # It's a top-level file
            search_pattern = f"--{path[0]}--"
        else:  # It's a top-level directory
            search_pattern = f"---{path[0]}/---"

        # Search for the pattern in the text
        text = self.text_display.toPlainText()
        cursor = self.text_display.textCursor()

        # Remove any existing highlighting
        cursor.select(QTextCursor.SelectionType.Document)
        format = QTextCharFormat()
        cursor.setCharFormat(format)

        # Move cursor to the start
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.text_display.setTextCursor(cursor)

        # Search for the pattern
        found = self.text_display.find(search_pattern)

        if found:
            # Highlight the line
            cursor = self.text_display.textCursor()
            format = QTextCharFormat()
            format.setBackground(QColor("#8E44AD"))
            format.setForeground(QColor("white"))

            # Select the whole line
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)

            # Apply the format
            cursor.mergeCharFormat(format)

            # Scroll to the position
            self.text_display.ensureCursorVisible()

    def get_checked_items(self, parent_item=None):
        checked_items = []

        if parent_item is None:
            # Start from the root
            root = self.file_tree.invisibleRootItem()
            for i in range(root.childCount()):
                checked_items.extend(self.get_checked_items(root.child(i)))
        else:
            # Process this item
            if parent_item.checkState(0) == Qt.CheckState.Checked:
                # Get the full path
                path = []
                current = parent_item
                while current is not None and current.text(0) != "/":
                    path.insert(0, current.text(0))
                    current = current.parent()

                if path:  # Avoid empty paths
                    # Determine if it's a file or directory
                    is_file = (parent_item.childCount() == 0 or '.' in path[-1])
                    if is_file:
                        checked_items.append((path, "file"))
                    else:
                        checked_items.append((path, "directory"))

            # Process children
            for i in range(parent_item.childCount()):
                child_items = self.get_checked_items(parent_item.child(i))
                checked_items.extend(child_items)

        return checked_items

    def copy_selected_files(self):
        # Get the checked items from the tree
        checked_items = self.get_checked_items()

        if not checked_items:
            self.show_message("No files selected - please check items to copy")
            return

        copied_content = []
        content = self.text_display.toPlainText()

        for path_parts, item_type in checked_items:
            # Only process files, not directories
            if item_type == "directory":
                continue

            # Construct the search pattern for the file
            search_pattern = f"--{path_parts[-1]}--"

            # If the file is in a subdirectory, we need to check the path
            if len(path_parts) > 1:
                # Check if we can find the exact path in the file_positions
                full_path = os.path.join(*path_parts)
            else:
                full_path = path_parts[0]

            # Find the pattern in the text
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
            clipboard = QApplication.clipboard()
            clipboard.setText(full_content)
            self.show_toast_message(f"{len(copied_content)} file(s) copied")
        else:
            self.show_message("No content found for selected files")

    def copy_text(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_display.toPlainText())
        self.show_toast_message("All text copied")

    def copy_selection(self):
        cursor = self.text_display.textCursor()
        if cursor.hasSelection():
            clipboard = QApplication.clipboard()
            clipboard.setText(cursor.selectedText())
            self.show_toast_message("Selection copied")
        else:
            self.show_message("No text selected")

    def show_toast_message(self, message):
        # Create a semi-transparent notification
        status_msg = QLabel(message, self)
        status_msg.setStyleSheet("""
            background-color: rgba(142, 68, 173, 0.8);
            color: white;
            border-radius: 15px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: bold;
        """)
        status_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_msg.adjustSize()

        # Center on the main window
        x = (self.width() - status_msg.width()) // 2
        y = self.height() - status_msg.height() - 30  # Position at the bottom
        status_msg.move(x, y)
        status_msg.show()

        # Auto-hide after 1.5 seconds
        timer = QTimer(self)
        timer.singleShot(1500, status_msg.deleteLater)

    def save_changes(self):
        try:
            content = self.text_display.toPlainText()
            with open(self.current_output_file, 'w', encoding='utf-8') as f:
                f.write(content)

            # Show brief confirmation message
            self.show_toast_message("Changes saved")
            self.update_counts()
        except Exception as e:
            self.show_error(f"An error occurred while saving: {str(e)}")

    def show_message(self, message):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Message")
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #2b2b2b;
                color: white;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #8E44AD;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #9B59B6;
            }
        """)
        msg_box.exec()

    def show_error(self, message):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Error")
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #2b2b2b;
                color: white;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #8E44AD;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #9B59B6;
            }
        """)
        msg_box.exec()

    def count_tokens(self, text):
        try:
            encoding = tiktoken.encoding_for_model("gpt-4")
            return len(encoding.encode(text))
        except Exception as e:
            logging.error(f"Error counting tokens: {str(e)}")
            return 0

    def update_counts(self):
        text = self.text_display.toPlainText()
        char_count = len(text)
        token_count = self.count_tokens(text)
        self.char_count_label.setText(f"Characters: {char_count}")
        self.token_count_label.setText(f"Tokens: {token_count}")


def main():
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
