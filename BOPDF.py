import sys
import os
import shutil
import fitz  # PyMuPDF
import subprocess
import tempfile
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QPushButton,
    QVBoxLayout, QWidget, QScrollArea, QLabel, QHBoxLayout,
    QInputDialog, QMessageBox, QComboBox, QLineEdit
)
from PyQt5.QtGui import QPainter, QPixmap, QColor, QPen
from PyQt5.QtCore import Qt, QRect, QPoint
import pytesseract
from PIL import Image


class CaviardableImage(QLabel):
    def __init__(self, pixmap, page_index):
        super().__init__()
        self.original_pixmap = pixmap
        self.page_index = page_index
        self.rects = []
        self.drawing = False
        self.origin = None
        self.current_rect = QRect()
        self.scale_factor = 1.0
        self.blackout_color = QColor(0, 0, 0, 180)
        self.setMinimumSize(pixmap.size())
        self.setPixmap(self.original_pixmap)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            x = int(event.pos().x() / self.scale_factor)
            y = int(event.pos().y() / self.scale_factor)
            self.origin = QPoint(x, y)
            self.current_rect = QRect(self.origin, self.origin)
            self.drawing = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.drawing:
            x = int(event.pos().x() / self.scale_factor)
            y = int(event.pos().y() / self.scale_factor)
            self.current_rect = QRect(self.origin, QPoint(x, y)).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drawing:
            self.rects.append(self.current_rect)
            self.current_rect = QRect()
            self.drawing = False
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        scaled_pixmap = self.original_pixmap.scaled(
            self.original_pixmap.size() * self.scale_factor,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        painter.drawPixmap(0, 0, scaled_pixmap)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self.blackout_color)

        for rect in self.rects:
            scaled_rect = QRect(
                int(rect.x() * self.scale_factor),
                int(rect.y() * self.scale_factor),
                int(rect.width() * self.scale_factor),
                int(rect.height() * self.scale_factor),
            )
            painter.drawRect(scaled_rect)

        if self.drawing:
            scaled_current = QRect(
                int(self.current_rect.x() * self.scale_factor),
                int(self.current_rect.y() * self.scale_factor),
                int(self.current_rect.width() * self.scale_factor),
                int(self.current_rect.height() * self.scale_factor),
            )
            painter.drawRect(scaled_current)

    def zoom(self, factor):
        self.scale_factor *= factor
        new_size = self.original_pixmap.size() * self.scale_factor
        self.setMinimumSize(new_size)
        self.updateGeometry()
        self.update()

    def undo_last_rect(self):
        if self.rects:
            self.rects.pop()
            self.update()


class BlackoutPDF(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BlackOutPDF")
        self.resize(1200, 900)
        self.pdf_path = None
        self.image_widgets = []
        self.password = None

        layout = QVBoxLayout()
        top_bar = QHBoxLayout()

        self.open_button = QPushButton("📂 Ouvrir PDF")
        self.open_button.clicked.connect(self.load_pdf)
        self.export_button = QPushButton("💾 Exporter PDF sécurisé")
        self.export_button.clicked.connect(self.export_pdf)
        self.export_button.setEnabled(False)
        self.zoom_in = QPushButton("🔍+")
        self.zoom_out = QPushButton("🔍–")
        self.zoom_in.clicked.connect(lambda: self.adjust_zoom(1.1))
        self.zoom_out.clicked.connect(lambda: self.adjust_zoom(0.9))
        self.undo_btn = QPushButton("↩️ Annuler")
        self.undo_btn.clicked.connect(self.undo_last_rectangle)
        self.ocr_btn = QPushButton("🧠 OCR")
        self.ocr_btn.clicked.connect(self.run_ocr)
        self.to_word_btn = QPushButton("⇄ Convertir en Word")
        self.to_word_btn.clicked.connect(self.convert_to_word)

        self.theme_selector = QComboBox()
        self.theme_selector.addItems(["Thème Clair", "Thème Sombre"])
        self.theme_selector.currentIndexChanged.connect(self.change_theme)

        top_bar.addWidget(self.theme_selector)
        top_bar.addWidget(self.open_button)
        top_bar.addWidget(self.export_button)
        top_bar.addWidget(self.zoom_in)
        top_bar.addWidget(self.zoom_out)
        top_bar.addWidget(self.undo_btn)
        top_bar.addWidget(self.ocr_btn)
        top_bar.addWidget(self.to_word_btn)

        layout.addLayout(top_bar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout()
        self.scroll_content.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.temp_dir = tempfile.mkdtemp()
        self.apply_light_theme()

    def adjust_zoom(self, factor):
        for widget in self.image_widgets:
            widget.zoom(factor)

    def undo_last_rectangle(self):
        for widget in self.image_widgets:
            widget.undo_last_rect()

    def load_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir un PDF", "", "PDF (*.pdf)")
        if not path:
            return
        self.pdf_path = path
        self.image_widgets.clear()
        for i in reversed(range(self.scroll_layout.count())):
            self.scroll_layout.itemAt(i).widget().setParent(None)

        self.doc = fitz.open(path)
        for page_index in range(len(self.doc)):
            pix = self.doc[page_index].get_pixmap(dpi=150)
            img_path = os.path.join(self.temp_dir, f"page_{page_index}.png")
            pix.save(img_path)
            pixmap = QPixmap(img_path)
            label = CaviardableImage(pixmap, page_index)
            self.image_widgets.append(label)
            self.scroll_layout.addWidget(label)

        self.export_button.setEnabled(True)

    def export_pdf(self):
        try:
            use_password = QMessageBox.question(
                self,
                "Mot de passe",
                "Souhaitez-vous protéger le PDF par mot de passe ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if use_password == QMessageBox.Yes:
                password_dialog = QInputDialog(self)
                password_dialog.setWindowTitle("Mot de passe")
                password_dialog.setLabelText("Entrez le mot de passe :")
                password_dialog.setTextEchoMode(QLineEdit.Password)
                password_dialog.setModal(True)
                password_dialog.show()
                password_dialog.raise_()
                password_dialog.activateWindow()

                if password_dialog.exec_() == QInputDialog.Accepted:
                    password = password_dialog.textValue()
                    if not password:
                        QMessageBox.warning(self, "Export annulé", "Aucun mot de passe saisi. Export annulé.")
                        return
                    self.password = password
                else:
                    QMessageBox.information(self, "Export annulé", "Export annulé par l'utilisateur.")
                    return
            else:
                self.password = None

            output_path, _ = QFileDialog.getSaveFileName(
                self, "Enregistrer sous", "caviarde.pdf", "PDF (*.pdf)"
            )
            if not output_path:
                return

            doc = fitz.open(self.pdf_path)

            dpi = 150
            scale = 72 / dpi

            for label in self.image_widgets:
                page = doc[label.page_index]

                # dimensions réelles (points PDF) et pixmap (pixels)
                page_w, page_h = page.rect.width, page.rect.height
                pix_w,  pix_h  = label.original_pixmap.width(), label.original_pixmap.height()

                # facteurs d’échelle independants de la résolution choisie au rendu
                sx = page_w / pix_w
                sy = page_h / pix_h

                for rect in label.rects:
                    x0 = rect.x() * sx
                    x1 = (rect.x() + rect.width()) * sx

                    y0 = rect.y() * sy                          # haut du rectangle
                    y1 = (rect.y() + rect.height()) * sy        # bas du rectangle

                    pdf_rect = fitz.Rect(x0, y0, x1, y1)
                    page.add_redact_annot(pdf_rect, fill=(0, 0, 0))

                page.apply_redactions()

            save_kwargs = {}
            if self.password:  # chiffrement facultatif
                save_kwargs.update({
                    "encryption": fitz.PDF_ENCRYPT_AES_256,
                    "owner_pw": self.password,
                    "user_pw": self.password,
                })

            doc.save(output_path, garbage=4, deflate=True, clean=True, **save_kwargs)

            doc.close()

            QMessageBox.information(self, "Export", "Le PDF a été exporté avec succès !")

            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                self.temp_dir = tempfile.mkdtemp()

        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", f"Impossible d'exporter le PDF :\n{e}")

    def convert_to_word(self):
        if not self.pdf_path:
            return
        output_path, _ = QFileDialog.getSaveFileName(self, "Enregistrer Word sous", "document.docx", "DOCX (*.docx)")
        if not output_path:
            return
        try:
            subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "docx", self.pdf_path, "--outdir", os.path.dirname(output_path)],
                check=True,
            )
            QMessageBox.information(self, "Conversion", "Conversion terminée !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la conversion :\n{e}")

    def run_ocr(self):
        if not self.pdf_path:
            return
        try:
            self.doc = fitz.open(self.pdf_path)
            for label in self.image_widgets:
                img_path = os.path.join(self.temp_dir, f"page_{label.page_index}.png")
                img = Image.open(img_path)
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                label.rects.clear()
                for i, text in enumerate(data["text"]):
                    if text.strip():
                        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                        label.rects.append(QRect(x, y, w, h))
                label.update()
            QMessageBox.information(self, "OCR", "Analyse OCR terminée !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur OCR", f"Erreur lors de l'OCR :\n{e}")

    def change_theme(self, index):
        if index == 0:
            self.apply_light_theme()
        else:
            self.apply_dark_theme()

    def apply_light_theme(self):
        self.setStyleSheet("""
            QWidget {
                background-color: white;
                color: black;
            }
            QPushButton {
                background-color: #e1e1e1;
                border: 1px solid #aaa;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #c1c1c1;
            }
            QComboBox {
                background-color: white;
                border: 1px solid #aaa;
            }
        """)

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: white;
            }
            QPushButton {
                background-color: #444;
                border: 1px solid #666;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #666;
            }
            QComboBox {
                background-color: #3a3a3a;
                border: 1px solid #666;
            }
        """)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BlackoutPDF()
    window.show()
    sys.exit(app.exec_())
