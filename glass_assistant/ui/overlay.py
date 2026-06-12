"""
overlay.py
==========
The "glass" window that floats on top of everything.

Layout (top to bottom):
- Title bar: app name · session timer · listening dot · copy · close
- Toolbar:   [Answer] [Analyse Screen] [Chat] [Record/Mute]
- Answer area: read-only Markdown (code blocks render as monospace)
- Chat input: a text box for typed follow-up questions (hidden until Chat)
- Footer: hotkey hints + resize grip

It's frameless, always-on-top, draggable (by the title bar) and resizable
(bottom-right grip). The window exposes Qt signals for the toolbar buttons
so the Controller can wire them to actions.
"""

from PyQt6.QtCore import Qt, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QBrush, QFont, QPen, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QFrame, QSizeGrip,
    QPushButton, QLineEdit,
)

from ..config import settings


# Typography for the whole panel. One UI font, one mono font, used everywhere
# so nothing looks "mixed". Segoe UI / Cascadia Code ship with Windows 10/11.
UI_FONT = "Segoe UI"
MONO_FONT = "Cascadia Mono, Consolas, monospace"

# Document stylesheet applied to the rendered Markdown. Qt's rich-text engine
# supports a CSS subset, so this is what turns the raw HTML into something
# readable: comfortable line-height, real code blocks, styled headings/lists.
ANSWER_CSS = f"""
    body {{
        color: {settings.text_color};
        font-family: '{UI_FONT}';
        font-size: 14px;
        line-height: 160%;
    }}
    h1, h2, h3, h4 {{
        color: #FFFFFF;
        font-weight: 600;
        margin-top: 14px;
        margin-bottom: 6px;
    }}
    h1 {{ font-size: 19px; }}
    h2 {{ font-size: 17px; }}
    h3 {{ font-size: 15px; }}
    p {{ margin-top: 0px; margin-bottom: 10px; }}
    ul, ol {{ margin-top: 0px; margin-bottom: 10px; }}
    li {{ margin-bottom: 4px; }}
    a {{ color: {settings.accent_color}; }}
    strong {{ color: #FFFFFF; }}
    code {{
        font-family: {MONO_FONT};
        font-size: 13px;
        background-color: rgba(255, 255, 255, 22);
        color: #FFD9A0;
    }}
    pre {{
        font-family: {MONO_FONT};
        font-size: 13px;
        background-color: rgba(0, 0, 0, 110);
        color: #E6EDF3;
        padding: 12px;
        margin-top: 4px;
        margin-bottom: 12px;
    }}
    pre code {{ background-color: transparent; color: #E6EDF3; }}
"""

# Button styling for the toolbar / title-bar buttons.
_BTN_CSS = """
    QPushButton {
        color: rgba(255,255,255,220);
        background: rgba(255,255,255,20);
        border: 1px solid rgba(255,255,255,30);
        border-radius: 8px;
        padding: 5px 12px;
    }
    QPushButton:hover { background: rgba(255,255,255,40); }
    QPushButton:pressed { background: rgba(255,255,255,60); }
"""

_ICON_BTN_CSS = """
    QPushButton {
        color: rgba(255,255,255,200);
        background: transparent;
        border: none; border-radius: 6px;
        padding: 2px 6px; font-size: 13px;
    }
    QPushButton:hover { background: rgba(255,255,255,35); }
"""


class Overlay(QWidget):
    # Toolbar actions the Controller listens to.
    analyse_requested = pyqtSignal()       # "Analyse Screen"
    answer_requested = pyqtSignal()        # "Answer" (the last heard question)
    record_toggled = pyqtSignal()          # "Record/Mute"
    chat_submitted = pyqtSignal(str)       # user typed a chat message
    new_chat_requested = pyqtSignal()      # clear the conversation memory

    def __init__(self):
        super().__init__()

        self._short_text = ""   # just the ANSWER section
        self._full_text = ""    # the entire response (answer + details)
        self._compact = False   # False = show full, True = show short only
        self._drag_offset = None
        self._elapsed = 0       # seconds, for the session timer

        self._build_window()
        self._build_widgets()
        self._start_timer()
        self._place_top_right()
        self.set_status("Ready")
        self.set_listening(settings.voice_enabled)

    # ----------------------------------------------------------------- setup
    def _build_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(settings.window_min_width, settings.window_min_height)
        self.resize(settings.window_width, settings.window_height)

    def _button(self, text: str, tip: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setFont(QFont(UI_FONT, 9, QFont.Weight.DemiBold))
        btn.setStyleSheet(_BTN_CSS)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if tip:
            btn.setToolTip(tip)
        return btn

    def _icon_button(self, text: str, tip: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setStyleSheet(_ICON_BTN_CSS)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(24)
        if tip:
            btn.setToolTip(tip)
        return btn

    def _build_widgets(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(10)

        # --- Title bar (DRAG HANDLE): name · timer · dot · copy · close ---
        titlebar = QHBoxLayout()
        titlebar.setSpacing(8)
        title = QLabel("⚡ Glass Assistant")
        title.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {settings.accent_color}; letter-spacing:0.3px;")

        self.dot_label = QLabel("●")
        self.dot_label.setFont(QFont(UI_FONT, 10))

        self.timer_label = QLabel("00:00")
        self.timer_label.setFont(QFont(MONO_FONT.split(",")[0], 10))
        self.timer_label.setStyleSheet("color: rgba(255,255,255,170);")

        self.new_btn = self._icon_button("⟲", "New chat (clear memory)")
        self.new_btn.clicked.connect(lambda: self.new_chat_requested.emit())
        self.copy_btn = self._icon_button("⧉", "Copy answer")
        self.copy_btn.clicked.connect(lambda: self._copy_answer())
        self.close_btn = self._icon_button("✕", "Hide panel (Ctrl+Shift+H)")
        self.close_btn.clicked.connect(lambda: self.hide())

        titlebar.addWidget(title)
        titlebar.addStretch(1)
        titlebar.addWidget(self.dot_label)
        titlebar.addWidget(self.timer_label)
        titlebar.addWidget(self.new_btn)
        titlebar.addWidget(self.copy_btn)
        titlebar.addWidget(self.close_btn)
        layout.addLayout(titlebar)

        # --- Toolbar of clickable actions ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.answer_btn = self._button("Answer", "Answer the last question heard")
        self.analyse_btn = self._button("Analyse Screen", "Screenshot + answer (Ctrl+Space)")
        self.chat_btn = self._button("Chat", "Type a follow-up question")
        self.record_btn = self._button("● Rec", "Mute / unmute listening (Ctrl+Shift+M)")
        self.answer_btn.clicked.connect(lambda: self.answer_requested.emit())
        self.analyse_btn.clicked.connect(lambda: self.analyse_requested.emit())
        self.chat_btn.clicked.connect(lambda: self.toggle_chat())
        self.record_btn.clicked.connect(lambda: self.record_toggled.emit())
        for b in (self.answer_btn, self.analyse_btn, self.chat_btn, self.record_btn):
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        self.status_label = QLabel()
        self.status_label.setFont(QFont(UI_FONT, 9))
        self.status_label.setStyleSheet(
            "color: rgba(255,255,255,160); background: rgba(255,255,255,18);"
            "border-radius: 9px; padding: 2px 10px;"
        )
        toolbar.addWidget(self.status_label)
        layout.addLayout(toolbar)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(255,255,255,28); border: none;")
        layout.addWidget(divider)

        # --- Answer area ---
        self.answer_view = QTextEdit()
        self.answer_view.setReadOnly(True)
        self.answer_view.setFrameShape(QFrame.Shape.NoFrame)
        self.answer_view.setFont(QFont(UI_FONT, 11))
        self.answer_view.document().setDocumentMargin(0)
        self.answer_view.document().setDefaultStyleSheet(ANSWER_CSS)
        self.answer_view.setStyleSheet(
            "QTextEdit { background: transparent; border: none;"
            f" color: {settings.text_color}; }}"
            "QScrollBar:vertical { background: transparent; width: 8px; margin: 2px 0; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,55);"
            " border-radius: 4px; min-height: 30px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(255,255,255,90); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        self.answer_view.viewport().setAutoFillBackground(False)
        layout.addWidget(self.answer_view, stretch=1)

        # --- Chat input row (hidden until "Chat" is toggled) ---
        self.chat_row = QWidget()
        chat_layout = QHBoxLayout(self.chat_row)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(8)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type a follow-up question and press Enter…")
        self.chat_input.setFont(QFont(UI_FONT, 11))
        self.chat_input.setStyleSheet(
            "QLineEdit { color: #fff; background: rgba(255,255,255,22);"
            " border: 1px solid rgba(255,255,255,40); border-radius: 8px;"
            " padding: 7px 10px; }"
            "QLineEdit:focus { border: 1px solid %s; }" % settings.accent_color
        )
        self.chat_input.returnPressed.connect(self._submit_chat)
        send_btn = self._button("Send")
        send_btn.clicked.connect(lambda: self._submit_chat())
        chat_layout.addWidget(self.chat_input, stretch=1)
        chat_layout.addWidget(send_btn)
        self.chat_row.setVisible(False)
        layout.addWidget(self.chat_row)

        # --- Footer: hints + resize grip ---
        bottom = QHBoxLayout()
        self.hint_label = QLabel(
            "Ctrl+Space analyse · Ctrl+Shift+C chat · Ctrl+Shift+M mute · "
            "Ctrl+Shift+H hide · Ctrl+Shift+Q quit"
        )
        self.hint_label.setFont(QFont(UI_FONT, 8))
        self.hint_label.setStyleSheet("color: rgba(255,255,255,110);")
        self.hint_label.setWordWrap(True)
        bottom.addWidget(self.hint_label, stretch=1)
        grip = QSizeGrip(self)
        grip.setFixedSize(14, 14)
        bottom.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        layout.addLayout(bottom)

    def _start_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        self._elapsed += 1
        m, s = divmod(self._elapsed, 60)
        self.timer_label.setText(f"{m:02d}:{s:02d}")

    def _place_top_right(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.width() - settings.margin
        y = screen.top() + settings.margin
        self.move(x, y)

    # --------------------------------------------------------------- painting
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setBrush(QBrush(QColor(*settings.background_color)))
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawRoundedRect(rect, 16, 16)

    # ------------------------------------------------------- drag-to-move
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (event.globalPosition().toPoint()
                                 - self.frameGeometry().topLeft())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and (
                event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    # --------------------------------------------------------- render helpers
    def _render_markdown(self, text: str):
        self.answer_view.setMarkdown(text)

    def _render_plain(self, text: str):
        self.answer_view.setPlainText(text)

    def _set_dot(self, color: str):
        self.dot_label.setStyleSheet(f"color: {color};")

    # ------------------------------------------------------- chat / clipboard
    def toggle_chat(self):
        show = not self.chat_row.isVisible()
        self.chat_row.setVisible(show)
        if show:
            self.show()
            self.raise_()
            self.activateWindow()
            self.chat_input.setFocus()

    def _submit_chat(self):
        text = self.chat_input.text().strip()
        if text:
            self.chat_input.clear()
            self.chat_submitted.emit(text)

    def _copy_answer(self):
        if self._full_text:
            QGuiApplication.clipboard().setText(self._full_text)
            self.set_status("Copied ✓")

    # ------------------------------------------------------------- public API
    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_listening(self, enabled: bool):
        if enabled:
            self.record_btn.setText("● Rec")
            self._set_dot("#46d369")          # green = listening
            self.set_status("Listening")
        else:
            self.record_btn.setText("🔇 Muted")
            self._set_dot("rgba(255,255,255,90)")   # grey = muted

    def show_thinking(self):
        self._set_dot("#f5a623")              # amber = working
        self.set_status("Thinking…")
        self._render_plain("Looking at your screen…")
        self.show()
        self.raise_()

    def show_transcribing(self):
        self._set_dot("#f5a623")
        self.set_status("Transcribing…")
        self._render_plain("Heard you — transcribing…")
        self.show()
        self.raise_()

    def show_caption(self, text: str):
        self._set_dot("#46d369")
        self.set_status("Listening…")
        self._render_markdown(f"*listening…*\n\n{text}")
        self.show()
        self.raise_()

    def show_heard(self, question: str):
        self._set_dot("#f5a623")
        self.set_status("Thinking…")
        self._render_markdown(f"**You asked:**\n\n> {question}\n\n*Thinking…*")
        self.show()
        self.raise_()

    def show_answer(self, short_text: str, full_text: str, source: str = ""):
        self._short_text = short_text
        self._full_text = full_text
        self._compact = False
        self._set_dot("#46d369")
        self.set_status(f"Answer · {source}" if source else "Answer")
        self._render_markdown(full_text)
        self.show()
        self.raise_()

    def show_error(self, message: str):
        self._short_text = message
        self._full_text = message
        self._set_dot("#ff5c5c")
        self.set_status("Error")
        self._render_plain(message)
        self.show()
        self.raise_()

    def toggle_expand(self):
        if not self._full_text:
            return
        self._compact = not self._compact
        self._render_markdown(self._short_text if self._compact else self._full_text)
        self.set_status("Compact" if self._compact else "Answer")

    def toggle_visible(self):
        self.setVisible(not self.isVisible())
        if self.isVisible():
            self.raise_()

    def clear(self):
        """Wipe the current answer (used when starting a new chat)."""
        self._short_text = ""
        self._full_text = ""
        self._render_plain("")
        self.set_status("New chat")
