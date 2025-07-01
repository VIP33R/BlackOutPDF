import sys
import os
import shutil
import fitz  # PyMuPDF
import tempfile
import uuid
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QVBoxLayout, QWidget,
    QScrollArea, QLabel, QHBoxLayout, QInputDialog, QMessageBox,
    QLineEdit, QToolButton, QFrame, QPushButton, QColorDialog, QMenu
)
from PyQt6.QtGui import QPainter, QPixmap, QColor, QMouseEvent, QCursor, QIcon, QFont, QImage
from PyQt6.QtCore import Qt, QRect, QPoint, QSize
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

class CaviardableImage(QLabel):
    HANDLE_SIZE = 12
    def __init__(self, pixmap, page_index, parent=None):
        super().__init__(parent)
        self.original_pixmap = pixmap
        self.page_index = page_index
        self.rects = []
        self.highlights = []
        self.comments = []
        self.signatures = []
        self.stamps = []
        self.textboxes = []
        self.drawing = False
        self.origin = None
        self.current_rect = QRect()
        self.scale_factor = 1.0
        self.blackout_color = QColor(0, 0, 0, 255)
        self.highlight_color = QColor(255, 255, 0, 110)
        self.mode = None
        self.placing_signature = None
        self.placing_signature_original = None
        self.placing_stamp = None
        self.placing_stamp_original = None
        self.selected_item = None
        self.selected_offset = None
        self.resizing_handle = None
        self.setMinimumSize(pixmap.size())
        self.setPixmap(self.original_pixmap)
        self.setMouseTracking(True)

    def set_mode(self, mode):
        self.mode = mode
        self.selected_item = None
        self.resizing_handle = None
        self.selected_offset = None

    def zoom(self, factor):
        self.scale_factor *= factor
        new_size = self.original_pixmap.size() * self.scale_factor
        self.setMinimumSize(new_size)
        self.updateGeometry()
        self.update()

    def item_at_pos(self, x, y):
        for i, (rect, _, _, _) in reversed(list(enumerate(self.textboxes))):
            r = self.scaled_rect(rect)
            if r.contains(x, y):
                return ('textbox', i, rect, False)
        for i, (rect, _, _) in reversed(list(enumerate(self.signatures))):
            r = self.scaled_rect(rect)
            if r.contains(x, y):
                return ('signature', i, rect, False)
        for i, (rect, _, _) in reversed(list(enumerate(self.stamps))):
            r = self.scaled_rect(rect)
            if r.contains(x, y):
                return ('stamp', i, rect, True)
        return None

    def handle_at_pos(self, rect, x, y):
        handles = self.get_handles(rect)
        for key, handle_rect in handles.items():
            if handle_rect.contains(x, y):
                return key
        return None

    def scaled_rect(self, rect):
        return QRect(
            int(rect.x() * self.scale_factor),
            int(rect.y() * self.scale_factor),
            int(rect.width() * self.scale_factor),
            int(rect.height() * self.scale_factor)
        )

    def get_handles(self, rect):
        r = self.scaled_rect(rect)
        s = self.HANDLE_SIZE
        return {
            'nw': QRect(r.left() - s//2, r.top() - s//2, s, s),
            'ne': QRect(r.right() - s//2, r.top() - s//2, s, s),
            'sw': QRect(r.left() - s//2, r.bottom() - s//2, s, s),
            'se': QRect(r.right() - s//2, r.bottom() - s//2, s, s),
        }

    def mousePressEvent(self, event: QMouseEvent):
        x = int(event.position().x())
        y = int(event.position().y())
        parent = self.parent()
        while parent and not isinstance(parent, BlackoutPDF):
            parent = parent.parent()
        item = self.item_at_pos(x, y)
        if item and self.mode is None:
            typ, idx, rect, _ = item
            self.selected_item = (typ, idx)
            handle = self.handle_at_pos(rect, x, y)
            self.resizing_handle = handle
            if handle is None:
                rx, ry = self.scaled_rect(rect).x(), self.scaled_rect(rect).y()
                self.selected_offset = (x - rx, y - ry)
            else:
                self.selected_offset = None
            self.update()
            if typ == "textbox" and event.button() == Qt.MouseButton.RightButton:
                self.show_textbox_context_menu(idx, event.globalPosition())
            return
        if self.mode == 'comment':
            x_scaled = int(event.position().x() / self.scale_factor)
            y_scaled = int(event.position().y() / self.scale_factor)
            text, ok = QInputDialog.getText(self, "Ajouter un commentaire", "Texte :")
            if ok and text.strip():
                rect = QRect(x_scaled, y_scaled, 20, 20)
                self.comments.append((rect, text))
                if parent:
                    parent.history.append({"page": self.page_index, "type": "comment", "data": rect})
                self.update()
            return
        if self.mode == 'signature' and self.placing_signature and self.placing_signature_original:
            x_scaled = int(event.position().x() / self.scale_factor)
            y_scaled = int(event.position().y() / self.scale_factor)
            rect = QRect(x_scaled, y_scaled,
                         self.placing_signature.width(),
                         self.placing_signature.height())
            self.signatures.append((rect, self.placing_signature, self.placing_signature_original))
            if parent:
                parent.history.append({"page": self.page_index, "type": "signature", "data": rect})
            self.placing_signature = None
            self.placing_signature_original = None
            self.mode = None
            self.update()
            return
        if self.mode == 'stamp' and self.placing_stamp and self.placing_stamp_original:
            x_scaled = int(event.position().x() / self.scale_factor)
            y_scaled = int(event.position().y() / self.scale_factor)
            rect = QRect(x_scaled, y_scaled,
                         self.placing_stamp.width(),
                         self.placing_stamp.height())
            self.stamps.append((rect, self.placing_stamp, self.placing_stamp_original))
            if parent:
                parent.history.append({"page": self.page_index, "type": "stamp", "data": rect})
            self.placing_stamp = None
            self.placing_stamp_original = None
            self.mode = None
            self.update()
            return
        if self.mode == 'textbox':
            x_scaled = int(event.position().x() / self.scale_factor)
            y_scaled = int(event.position().y() / self.scale_factor)
            text, ok = QInputDialog.getText(self, "Ajouter du texte", "Texte :")
            if ok and text.strip():
                font_size, ok2 = QInputDialog.getInt(self, "Taille police", "Taille du texte :", 17, 8, 80)
                if not ok2:
                    font_size = 17
                rect = QRect(x_scaled, y_scaled, 200, int(font_size * 2))
                color = QColor("#191919")
                self.textboxes.append([rect, text, font_size, color])
                if parent:
                    parent.history.append({"page": self.page_index, "type": "textbox", "data": rect})
                self.update()
            self.mode = None
            return
        if self.mode in ('blackout', 'highlight'):
            if event.button() == Qt.MouseButton.LeftButton:
                x_scaled = int(event.position().x() / self.scale_factor)
                y_scaled = int(event.position().y() / self.scale_factor)
                self.origin = QPoint(x_scaled, y_scaled)
                self.current_rect = QRect(self.origin, self.origin)
                self.drawing = True
                self.update()

    def mouseMoveEvent(self, event):
        x = int(event.position().x())
        y = int(event.position().y())
        if self.selected_item and self.mode is None:
            typ, idx = self.selected_item
            if typ == 'textbox':
                rect, text, size, color = self.textboxes[idx]
            elif typ == 'signature':
                rect, pix, orig = self.signatures[idx]
            else:
                rect, pix, orig = self.stamps[idx]
            if self.resizing_handle:
                s = self.scale_factor
                min_size = 16
                nx = int(event.position().x() / s)
                ny = int(event.position().y() / s)
                r = rect
                if self.resizing_handle == 'nw':
                    diff_w = (r.right() - nx)
                    diff_h = (r.bottom() - ny)
                    if diff_w > min_size and diff_h > min_size:
                        r.setTopLeft(QPoint(nx, ny))
                elif self.resizing_handle == 'ne':
                    diff_w = (nx - r.left())
                    diff_h = (r.bottom() - ny)
                    if diff_w > min_size and diff_h > min_size:
                        r.setTopRight(QPoint(nx, ny))
                elif self.resizing_handle == 'sw':
                    diff_w = (r.right() - nx)
                    diff_h = (ny - r.top())
                    if diff_w > min_size and diff_h > min_size:
                        r.setBottomLeft(QPoint(nx, ny))
                elif self.resizing_handle == 'se':
                    diff_w = (nx - r.left())
                    diff_h = (ny - r.top())
                    if diff_w > min_size and diff_h > min_size:
                        r.setBottomRight(QPoint(nx, ny))
                if typ == 'textbox':
                    self.textboxes[idx][0] = r
                elif typ == 'signature':
                    new_pix = orig.scaled(r.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.signatures[idx] = (r, new_pix, orig)
                else:
                    new_pix = orig.scaled(r.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.stamps[idx] = (r, new_pix, orig)
            elif self.selected_offset:
                s = self.scale_factor
                offset_x, offset_y = self.selected_offset
                nx = int((event.position().x() - offset_x) / s)
                ny = int((event.position().y() - offset_y) / s)
                r = rect
                r.moveTo(nx, ny)
                if typ == 'textbox':
                    self.textboxes[idx][0] = r
                elif typ == 'signature':
                    self.signatures[idx] = (r, pix, orig)
                else:
                    self.stamps[idx] = (r, pix, orig)
            self.update()
            return
        if self.drawing and self.mode in ('blackout', 'highlight'):
            x_scaled = int(event.position().x() / self.scale_factor)
            y_scaled = int(event.position().y() / self.scale_factor)
            self.current_rect = QRect(self.origin, QPoint(x_scaled, y_scaled)).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.selected_item and (self.resizing_handle or self.selected_offset):
            self.resizing_handle = None
            self.selected_offset = None
            self.update()
            return
        parent = self.parent()
        while parent and not isinstance(parent, BlackoutPDF):
            parent = parent.parent()
        if self.drawing and self.mode in ('blackout', 'highlight'):
            if self.current_rect.width() > 5 and self.current_rect.height() > 5:
                if self.mode == 'blackout':
                    self.rects.append(self.current_rect)
                    if parent:
                        parent.history.append({"page": self.page_index, "type": "blackout", "data": self.current_rect})
                else:
                    self.highlights.append(self.current_rect)
                    if parent:
                        parent.history.append({"page": self.page_index, "type": "highlight", "data": self.current_rect})
            self.current_rect = QRect()
            self.drawing = False
            self.update()
        self.selected_item = None
        self.resizing_handle = None
        self.selected_offset = None

    def mouseDoubleClickEvent(self, event):
        self.selected_item = None
        self.resizing_handle = None
        self.selected_offset = None
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.selected_item:
            typ, idx = self.selected_item
            if typ == 'textbox':
                del self.textboxes[idx]
            elif typ == 'signature':
                del self.signatures[idx]
            else:
                del self.stamps[idx]
            self.selected_item = None
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        scaled = self.original_pixmap.scaled(
            self.original_pixmap.size() * self.scale_factor,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        painter.drawPixmap(0, 0, scaled)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.blackout_color)
        for r in self.rects:
            rect = QRect(int(r.x() * self.scale_factor), int(r.y() * self.scale_factor),
                         int(r.width() * self.scale_factor), int(r.height() * self.scale_factor))
            painter.drawRect(rect)
        painter.setBrush(self.highlight_color)
        for r in self.highlights:
            rect = QRect(int(r.x() * self.scale_factor), int(r.y() * self.scale_factor),
                         int(r.width() * self.scale_factor), int(r.height() * self.scale_factor))
            painter.drawRect(rect)
        for r, _ in self.comments:
            rect = QRect(int(r.x() * self.scale_factor), int(r.y() * self.scale_factor), 20, 20)
            painter.setBrush(QColor(255, 255, 0, 180))
            painter.drawEllipse(rect)
        for idx, (r, text, size, color) in enumerate(self.textboxes):
            rect = QRect(int(r.x() * self.scale_factor), int(r.y() * self.scale_factor),
                         int(r.width() * self.scale_factor), int(r.height() * self.scale_factor))
            font = QFont("Arial", int(size * self.scale_factor))
            painter.setFont(font)
            painter.setPen(color)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            if self.selected_item == ('textbox', idx):
                painter.setPen(QColor("#3687ff"))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
                for hrect in self.get_handles(r).values():
                    painter.setBrush(QColor("#fff"))
                    painter.setPen(QColor("#3687ff"))
                    painter.drawEllipse(hrect)
        for idx, (r, pix, orig) in enumerate(self.signatures):
            rect = QRect(int(r.x() * self.scale_factor), int(r.y() * self.scale_factor),
                         int(r.width() * self.scale_factor), int(r.height() * self.scale_factor))
            painter.drawPixmap(rect, pix)
            if self.selected_item == ('signature', idx):
                painter.setPen(QColor("#3687ff"))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
                for hrect in self.get_handles(r).values():
                    painter.setBrush(QColor("#fff"))
                    painter.setPen(QColor("#3687ff"))
                    painter.drawEllipse(hrect)
        for idx, (r, pix, orig) in enumerate(self.stamps):
            rect = QRect(int(r.x() * self.scale_factor), int(r.y() * self.scale_factor),
                         int(r.width() * self.scale_factor), int(r.height() * self.scale_factor))
            painter.drawPixmap(rect, pix)
            if self.selected_item == ('stamp', idx):
                painter.setPen(QColor("#ff7138"))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
                for hrect in self.get_handles(r).values():
                    painter.setBrush(QColor("#fff"))
                    painter.setPen(QColor("#ff7138"))
                    painter.drawEllipse(hrect)
        if self.drawing and self.mode in ('blackout', 'highlight') and self.current_rect.width() > 2 and self.current_rect.height() > 2:
            painter.setBrush(QColor(0, 0, 0, 120) if self.mode == 'blackout' else self.highlight_color)
            rect = QRect(int(self.current_rect.x() * self.scale_factor), int(self.current_rect.y() * self.scale_factor),
                         int(self.current_rect.width() * self.scale_factor), int(self.current_rect.height() * self.scale_factor))
            painter.setPen(QColor("#222") if self.mode == 'blackout' else QColor("#ffe700"))
            painter.drawRect(rect)

    def show_textbox_context_menu(self, idx, global_pos):
        menu = QMenu()
        color_action = menu.addAction("Couleur…")
        font_action = menu.addAction("Taille police…")
        del_action = menu.addAction("Supprimer")
        action = menu.exec(global_pos.toPoint())
        if action == color_action:
            color = QColorDialog.getColor(self.textboxes[idx][3], self, "Choisir couleur")
            if color.isValid():
                self.textboxes[idx][3] = color
                self.update()
        elif action == font_action:
            size, ok = QInputDialog.getInt(self, "Taille police", "Taille du texte :", self.textboxes[idx][2], 8, 80)
            if ok:
                self.textboxes[idx][2] = size
                self.update()
        elif action == del_action:
            del self.textboxes[idx]
            self.update()

class BlackoutPDF(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BlackOutPDF 🇫🇷")
        self.resize(1280, 900)
        self.pdf_path = None
        self.image_widgets = []
        self.temp_dir = tempfile.mkdtemp()
        self.password = None
        self.signature_path = None
        self.stamp_path = None
        self.comment_popup_shown = False
        self.history = []
        self.label_buttons = []
        self.dark_mode = True

        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(100)
        sidebar.setStyleSheet("""
            QFrame {
                background: #20283B;
                border-right: none;
            }
        """)
        self.side_layout = QVBoxLayout(sidebar)
        self.side_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.side_layout.setSpacing(0)
        self.side_layout.setContentsMargins(0, 8, 0, 8)

        logo_sidebar = QLabel()
        logo_sidebar_pix = QPixmap("logo.png").scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        logo_sidebar.setPixmap(logo_sidebar_pix)
        logo_sidebar.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        logo_sidebar.setFixedHeight(54)
        self.side_layout.addWidget(logo_sidebar)

        creux = QWidget()
        creux.setFixedHeight(18)
        self.side_layout.addWidget(creux)

        def add_side_btn(icon: str, label: str, callback, active_color="#0055A4"):
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 3, 0, 3)
            layout.setSpacing(0)
            btn = QToolButton()
            icon_path = icon if os.path.exists(icon) else ""
            if icon_path:
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(22, 22))
            else:
                btn.setText(label[:2].upper())
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet("""
                QToolButton {
                    border: none;
                    background: transparent;
                    border-radius: 12px;
                    padding: 4px;
                }
                QToolButton:hover {
                    background: rgba(0,85,164,0.10);
                }
            """)
            btn.clicked.connect(callback)
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)
            text_label = QLabel(label)
            text_label.setStyleSheet("""
                font-size: 11px;
                font-weight: 400;
                color: #bbb;
                background: transparent;
                padding: 0;
                margin: 0;
            """)
            text_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            text_label.setWordWrap(True)
            text_label.setMaximumWidth(96)
            layout.addWidget(text_label, alignment=Qt.AlignmentFlag.AlignHCenter)
            self.side_layout.addWidget(container)
            return btn

        add_side_btn("icons/folder.svg", "Ouvrir PDF", self.load_pdf)
        add_side_btn("icons/lock.svg", "Export sécurisé", self.export_pdf_secured)
        add_side_btn("icons/skip-back.svg", "Annuler", self.undo_last_action)
        self.side_layout.addSpacing(4)
        add_side_btn("icons/eye-off.svg", "Caviarder", lambda: self.set_mode_for_all("blackout"))
        add_side_btn("icons/eye.svg", "Surligner", lambda: self.set_mode_for_all("highlight"))
        add_side_btn("icons/message-circle.svg", "Commenter", lambda: self.set_mode_for_all("comment"))
        add_side_btn("icons/pen-tool.svg", "Signer", self.start_signature_placement)
        add_side_btn("icons/tag.svg", "Tampon", self.start_stamp_placement)
        add_side_btn("icons/type.svg", "Texte", lambda: self.set_mode_for_all("textbox"))
        self.side_layout.addSpacing(4)
        add_side_btn("icons/check-circle.svg", "OCR", self.run_ocr)
        add_side_btn("icons/moon.svg", "Thème", self.toggle_theme)
        self.side_layout.addStretch()

        vcontent = QVBoxLayout()
        vcontent.setSpacing(0)
        vcontent.setContentsMargins(0,0,0,0)

        header = QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet("""
    QFrame {
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 #0055A4, stop:0.43 #fff, stop:1 #EF4135
        );
        border-bottom: 2px solid #0055A4;
    }
""")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12,0,12,0)
        header_layout.setSpacing(12)
        self.title_label = QLabel("BlackOutPDF 🇫🇷")
        self.title_label.setFont(QFont("Arial", 15, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color:#0055A4; letter-spacing:0.03em; font-weight:700;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        self.zoom_plus = QPushButton("+")
        self.zoom_plus.setFixedSize(28,28)
        self.zoom_plus.setStyleSheet("""
            QPushButton {
                font-size:15px; font-weight:600;
                background:#fff; color:#0055A4; border-radius:14px;
                border:2px solid #0055A4; }
            QPushButton:hover { background:#eaf2fb; }
        """)
        self.zoom_plus.clicked.connect(lambda: self.adjust_zoom(1.1))
        header_layout.addWidget(self.zoom_plus)
        self.zoom_minus = QPushButton("-")
        self.zoom_minus.setFixedSize(28,28)
        self.zoom_minus.setStyleSheet("""
            QPushButton {
                font-size:15px; font-weight:600;
                background:#fff; color:#EF4135; border-radius:14px;
                border:2px solid #EF4135; }
            QPushButton:hover { background:#fbeaea; }
        """)
        self.zoom_minus.clicked.connect(lambda: self.adjust_zoom(0.9))
        header_layout.addWidget(self.zoom_minus)
        vcontent.addWidget(header)

        content_frame = QFrame()
        content_frame.setStyleSheet("""
            QFrame {
                background:#212436;
                border-radius: 13px;
                margin: 10px 8px 8px 8px;
                box-shadow: 0 0 0 4px #232840, 0 0 20px 2px #0055A480, 0 0 60px 6px #EF413540;
                border: 1.5px solid #0055A4;
            }
        """)
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(18,13,18,13)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border:none; background:transparent; }
        """)
        self.content_holder = QWidget()
        self.scroll_layout = QVBoxLayout(self.content_holder)
        self.scroll_area.setWidget(self.content_holder)
        content_layout.addWidget(self.scroll_area)
        vcontent.addWidget(content_frame)

        main_layout.addWidget(sidebar)
        main_layout.addLayout(vcontent)
        self.setCentralWidget(central)
        self.apply_dark_theme()

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QWidget { background: #181B27; color: #fff; font-family: Arial, Inter, sans-serif;}
            QScrollArea { border: none; }
            QFrame { background: #20283B;}
            QToolButton, QLabel { color: #fff; }
        """)
        self.title_label.setStyleSheet("color:#fff; font-weight:700; letter-spacing:0.03em;")
        self.side_layout.parentWidget().setStyleSheet("""
            QFrame {
                background: #20283B;
                border-right: none;
            }
        """)

    def apply_light_theme(self):
        self.setStyleSheet("""
            QWidget { background: #F7F8FA; color: #083169; font-family: Arial, Inter, sans-serif;}
            QScrollArea { border: none; }
            QFrame { background: #f5f8fe;}
            QToolButton, QLabel { color: #083169; }
        """)
        self.title_label.setStyleSheet("color:#0055A4; font-weight:700; letter-spacing:0.03em;")
        self.side_layout.parentWidget().setStyleSheet("""
            QFrame {
                background: #f5f8fe;
                border-right: none;
            }
        """)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self.apply_dark_theme()
        else:
            self.apply_light_theme()
        self.update()

    def set_mode_for_all(self, mode):
        if not self.image_widgets:
            QMessageBox.warning(self, "Mode", "Aucun document chargé.")
            return
        for widget in self.image_widgets:
            widget.set_mode(mode)

    def adjust_zoom(self, factor):
        if not self.image_widgets:
            QMessageBox.warning(self, "Zoom", "Aucun document chargé.")
            return
        for widget in self.image_widgets:
            widget.zoom(factor)

    def undo_last_action(self):
        if not self.history:
            QMessageBox.information(self, "Annuler", "Rien à annuler.")
            return
        last = self.history.pop()
        page_index = last["page"]
        action_type = last["type"]
        data = last.get("data", None)
        widget = self.image_widgets[page_index]
        if action_type == "blackout" and data in widget.rects:
            widget.rects.remove(data)
        elif action_type == "highlight" and data in widget.highlights:
            widget.highlights.remove(data)
        elif action_type == "comment":
            widget.comments = [c for c in widget.comments if c[0] != data]
        elif action_type == "signature":
            widget.signatures = [c for c in widget.signatures if c[0] != data]
        elif action_type == "stamp":
            widget.stamps = [c for c in widget.stamps if c[0] != data]
        elif action_type == "textbox":
            widget.textboxes = [t for t in widget.textboxes if t[0] != data]
        widget.update()

    def start_signature_placement(self):
        img_path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image de signature", "", "Images (*.png *.jpg *.jpeg)"
        )
        if not img_path:
            return
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Signature", "Image non valide.")
            return
        self.signature_path = img_path
        scaled_pixmap = pixmap.scaledToWidth(90, Qt.TransformationMode.SmoothTransformation)
        for widget in self.image_widgets:
            widget.mode = "signature"
            widget.placing_signature = scaled_pixmap
            widget.placing_signature_original = pixmap
        QMessageBox.information(self, "Signature", "Cliquez sur la page pour positionner la signature.")

    def start_stamp_placement(self):
        img_path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image de tampon", "", "Images (*.png *.jpg *.jpeg)"
        )
        if not img_path:
            return
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Tampon", "Image non valide.")
            return
        self.stamp_path = img_path
        scaled_pixmap = pixmap.scaledToWidth(90, Qt.TransformationMode.SmoothTransformation)
        for widget in self.image_widgets:
            widget.mode = "stamp"
            widget.placing_stamp = scaled_pixmap
            widget.placing_stamp_original = pixmap
        QMessageBox.information(self, "Tampon", "Cliquez sur la page pour positionner le tampon.")

    def load_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir un PDF", "", "PDF (*.pdf)")
        if not path:
            return
        self.pdf_path = path
        self.image_widgets.clear()
        self.history.clear()
        self.comment_popup_shown = False
        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        try:
            for f in os.listdir(self.temp_dir):
                try:
                    os.remove(os.path.join(self.temp_dir, f))
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.doc = fitz.open(path)
            if self.doc.is_encrypted:
                password, ok = QInputDialog.getText(
                    self, "Mot de passe", "Entrez le mot de passe du PDF :", QLineEdit.EchoMode.Password
                )
                if not (ok and self.doc.authenticate(password)):
                    QMessageBox.critical(self, "Erreur", "Mot de passe incorrect.")
                    return
            for page_index in range(len(self.doc)):
                pix = self.doc[page_index].get_pixmap(dpi=150)
                img_path = os.path.join(self.temp_dir, f"page_{page_index}.png")
                pix.save(img_path)
                label = CaviardableImage(QPixmap(img_path), page_index, parent=self)
                self.image_widgets.append(label)
                self.scroll_layout.addWidget(label)
            self.title_label.setText(os.path.basename(self.pdf_path))
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'ouverture", f"{e}")

    def export_pdf_secured(self):
        if not getattr(self, "pdf_path", None):
            QMessageBox.warning(self, "Export", "Aucun PDF chargé.")
            return
        output_path, _ = QFileDialog.getSaveFileName(self, "Enregistrer PDF sécurisé", "caviarde_redact.pdf", "PDF (*.pdf)")
        if not output_path:
            return

        ask_password = QMessageBox.question(
            self, "Protection", "Souhaitez-vous protéger le PDF par mot de passe ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        password = None
        if ask_password == QMessageBox.StandardButton.Yes:
            password, ok = QInputDialog.getText(
                self, "Mot de passe", "Entrez le mot de passe :", QLineEdit.EchoMode.Password
            )
            if not (ok and password):
                QMessageBox.warning(self, "Export", "Mot de passe non validé.")
                return

        pdf = fitz.open(self.pdf_path)
        for idx, widget in enumerate(self.image_widgets):
            page = pdf[idx]
            scale = page.rect.width / widget.original_pixmap.width()
            for r in widget.rects:
                redact_rect = fitz.Rect(
                    r.x() * scale,
                    r.y() * scale,
                    (r.x() + r.width()) * scale,
                    (r.y() + r.height()) * scale
                )
                page.add_redact_annot(redact_rect, fill=(0,0,0))
            for h in widget.highlights:
                highlight_rect = fitz.Rect(
                    h.x() * scale,
                    h.y() * scale,
                    (h.x() + h.width()) * scale,
                    (h.y() + h.height()) * scale
                )
                highlight = page.add_highlight_annot(highlight_rect)
                highlight.set_colors(stroke=(1,1,0))
                highlight.update()
            # Correction : signature/tampon en PNG temporaire
            for r, pix, orig in widget.signatures:
                img = QImage(pix.toImage())
                tmp_name = os.path.join(self.temp_dir, f"sig_{uuid.uuid4().hex}.png")
                img.save(tmp_name)
                pixmap = fitz.Pixmap(tmp_name)
                sign_rect = fitz.Rect(
                    r.x() * scale,
                    r.y() * scale,
                    (r.x() + r.width()) * scale,
                    (r.y() + r.height()) * scale
                )
                page.insert_image(sign_rect, pixmap=pixmap)
                try:
                    os.remove(tmp_name)
                except Exception:
                    pass
            for r, pix, orig in widget.stamps:
                img = QImage(pix.toImage())
                tmp_name = os.path.join(self.temp_dir, f"stamp_{uuid.uuid4().hex}.png")
                img.save(tmp_name)
                pixmap = fitz.Pixmap(tmp_name)
                stamp_rect = fitz.Rect(
                    r.x() * scale,
                    r.y() * scale,
                    (r.x() + r.width()) * scale,
                    (r.y() + r.height()) * scale
                )
                page.insert_image(stamp_rect, pixmap=pixmap)
                try:
                    os.remove(tmp_name)
                except Exception:
                    pass
            for r, text, size, color in widget.textboxes:
                text_rect = fitz.Rect(
                    r.x() * scale,
                    r.y() * scale,
                    (r.x() + r.width()) * scale,
                    (r.y() + r.height()) * scale
                )
                page.insert_textbox(
                    text_rect,
                    text,
                    fontsize=size * scale,
                    fontname="helv",
                    color=(color.redF(), color.greenF(), color.blueF()),
                    align=fitz.TEXT_ALIGN_LEFT
                )
            for rect, txt in widget.comments:
                comment_rect = fitz.Rect(
                    rect.x() * scale, rect.y() * scale, (rect.x()+20)*scale, (rect.y()+20)*scale
                )
                page.add_text_annot(comment_rect.tl, txt)
        for page in pdf:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        try:
            if password:
                if not isinstance(password, str):
                    password = str(password)
                pdf.save(output_path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
            else:
                pdf.save(output_path)
            QMessageBox.information(self, "Export", "PDF exporté avec caviardages sécurisés et le reste éditable.")
        except Exception as e:
            print(f"[BUG EXPORT PDF] {e}")
            QMessageBox.critical(self, "Erreur Export", f"Erreur lors de l’export sécurisé du PDF :\n{e}")

    def run_ocr(self):
        if not self.pdf_path:
            QMessageBox.warning(self, "OCR", "Aucun PDF chargé.")
            return
        try:
            for widget in self.image_widgets:
                img_path = os.path.join(self.temp_dir, f"page_{widget.page_index}.png")
                img = Image.open(img_path).convert("RGB")
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                widget.rects.clear()
                for i, text in enumerate(data["text"]):
                    if text.strip():
                        x, y = data["left"][i], data["top"][i]
                        w, h = data["width"][i], data["height"][i]
                        widget.rects.append(QRect(x, y, w, h))
                widget.update()
            QMessageBox.information(self, "OCR", "Caviardage OCR appliqué !")
        except Exception as e:
            QMessageBox.critical(self, "OCR", f"Erreur OCR : {e}")

    def closeEvent(self, event):
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BlackoutPDF()
    window.show()
    sys.exit(app.exec())
