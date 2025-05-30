import sys
import os
import shutil
import fitz  # PyMuPDF
import subprocess
import tempfile
import math
import json 
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QPushButton,
    QVBoxLayout, QWidget, QScrollArea, QLabel, QHBoxLayout,
    QInputDialog, QMessageBox, QComboBox, QLineEdit, QColorDialog
)
from PyQt5.QtGui import QPainter, QPixmap, QColor, QPen, QIcon, QPainterPath
from PyQt5.QtCore import Qt, QRect, QPoint
import pytesseract
from PIL import Image

# importation des fonctions annexes
from src.utils import *

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
        self.mode = "rect"
        self.free_points = []
        self.moving_rect_idx = None
        self.resizing_rect_idx = None
        self.polys = []
        self.current_poly = []

    # =========================================================
    # CaviardableImage.mousePressEvent
    # =========================================================
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        if self.mode == "rect":
            x = int(event.pos().x() / self.scale_factor)
            y = int(event.pos().y() / self.scale_factor)
            self.origin = QPoint(x, y)
            self.current_rect = QRect(self.origin, self.origin)
            self.drawing = True
            self.update()

        elif self.mode == "free":
            p = QPoint(int(event.pos().x() / self.scale_factor),
                    int(event.pos().y() / self.scale_factor))
            self.current_poly = [p]       # démarre un nouveau polygone
            self.drawing = True
            self.update()

        elif self.mode == "hand":
            pos = event.pos()
            self.moving_rect_idx = self.resizing_rect_idx = None
            for i, r in enumerate(self.rects):
                s = QRect(int(r.x() * self.scale_factor), int(r.y() * self.scale_factor),
                        int(r.width() * self.scale_factor), int(r.height() * self.scale_factor))
                # coin bas-droit → redimension
                if (s.bottomRight() - pos).manhattanLength() <= 10:
                    self.resizing_rect_idx = i
                    self.resize_origin = pos
                    self.orig_rect = QRect(r)
                    self.drawing = True
                    break
                # intérieur → déplacement
                if s.contains(pos):
                    self.moving_rect_idx = i
                    self.move_origin = pos
                    self.orig_rect = QRect(r)
                    self.drawing = True
                    break

    # =========================================================
    # CaviardableImage.mouseMoveEvent
    # =========================================================
    def mouseMoveEvent(self, event):
        if self.mode == "rect" and self.drawing:
            x = int(event.pos().x() / self.scale_factor)
            y = int(event.pos().y() / self.scale_factor)
            self.current_rect = QRect(self.origin, QPoint(x, y)).normalized()
            self.update()

        elif self.mode == "free" and self.drawing:
            p = QPoint(int(event.pos().x() / self.scale_factor),
                    int(event.pos().y() / self.scale_factor))
            self.current_poly.append(p)
            self.update()

        elif self.mode == "hand" and self.drawing:
            if self.resizing_rect_idx is not None:
                dx = (event.pos().x() - self.resize_origin.x()) / self.scale_factor
                dy = (event.pos().y() - self.resize_origin.y()) / self.scale_factor
                nr = QRect(self.orig_rect)
                nr.setWidth(max(1, int(self.orig_rect.width() + dx)))
                nr.setHeight(max(1, int(self.orig_rect.height() + dy)))
                self.rects[self.resizing_rect_idx] = nr.normalized()
                self.update()
            elif self.moving_rect_idx is not None:
                dx = (event.pos().x() - self.move_origin.x()) / self.scale_factor
                dy = (event.pos().y() - self.move_origin.y()) / self.scale_factor
                nr = QRect(self.orig_rect)
                nr.translate(int(dx), int(dy))
                self.rects[self.moving_rect_idx] = nr
                self.update()

    # =========================================================
    # CaviardableImage.mouseReleaseEvent
    # =========================================================
    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        if self.mode == "rect" and self.drawing:
            self.rects.append(self.current_rect.normalized())
            self.current_rect = QRect()
            self.drawing = False
            self.update()

        elif self.mode == "free" and self.drawing:
            if len(self.current_poly) > 2:          # au moins un triangle
                self.polys.append(self.current_poly.copy())
            self.current_poly.clear()
            self.drawing = False
            self.update()

        elif self.mode == "hand" and self.drawing:
            self.moving_rect_idx = None
            self.resizing_rect_idx = None
            self.drawing = False

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

        for poly in self.polys:
            scaled = [QPoint(int(pt.x()*self.scale_factor),
                            int(pt.y()*self.scale_factor))
                    for pt in poly]
            painter.drawPolygon(*scaled)

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

        # ----- aperçu temps-réel pour le tracé libre -------------------------------
        if self.mode == "free" and self.drawing and self.current_poly:
            painter.setPen(QPen(Qt.red, 2))
            scaled = [QPoint(int(pt.x() * self.scale_factor),
                            int(pt.y() * self.scale_factor))
                    for pt in self.current_poly]
            painter.drawPolyline(*scaled)
            
    def zoom(self, factor):
        self.scale_factor *= factor
        new_size = self.original_pixmap.size() * self.scale_factor
        self.setMinimumSize(new_size)
        self.updateGeometry()
        self.update()

    def undo_last_rect(self):
        if self.mode == "free" and self.polys:
            self.polys.pop()
        elif self.rects:
            self.rects.pop()
        self.update()

    def set_mode(self, mode):
        self.mode = mode

class BlackoutPDF(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("BlackOutPDF")
        self.resize(1200, 900)
        icon_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "BOPDF.png")
        self.setWindowIcon(QIcon(icon_path))
        self.pdf_path = None
        self.image_widgets = []
        self.password = None
        self.rsa_pub_path  = None     # PEM publique pour chiffrer
        self.rsa_priv_path = None     # PEM privée  pour déchiffrer

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
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
        self.color_btn = QPushButton("🎨 Couleur")
        self.color_btn.clicked.connect(self.choose_color)
        self.caviard_rgb = (0, 0, 0)
        self.pub_btn    = QPushButton("🗝️  Publique")
        self.priv_btn   = QPushButton("🔑 Privée")
        self.pub_btn.clicked.connect(self.pick_public_key)
        self.priv_btn.clicked.connect(self.pick_private_key)

        self.theme_selector = QComboBox()
        self.theme_selector.addItems(["Thème Clair", "Thème Sombre"])
        self.theme_selector.currentIndexChanged.connect(self.change_theme)
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["▭ Rectangle", "✏️ Libre", "✋ Main"])
        self.mode_selector.currentIndexChanged.connect(self.mode_changed)
        self.restore_btn = QPushButton("🗃️ Restaurer PDF")
        self.restore_btn.clicked.connect(self.restore_pdf)
        top_bar.addWidget(self.restore_btn)
        top_bar.addWidget(self.pub_btn)
        top_bar.addWidget(self.priv_btn)
        top_bar.addWidget(self.mode_selector)
        top_bar.addWidget(self.theme_selector)
        top_bar.addWidget(self.open_button)
        top_bar.addWidget(self.export_button)
        top_bar.addWidget(self.zoom_in)
        top_bar.addWidget(self.zoom_out)
        top_bar.addWidget(self.undo_btn)
        top_bar.addWidget(self.ocr_btn)
        top_bar.addWidget(self.to_word_btn)
        top_bar.addWidget(self.color_btn)

        layout.addLayout(top_bar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout()
        self.scroll_content.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_content)
        self.current_mode = "rect"          # mode actif par défaut
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

                cipher_pub_pem = open(self.rsa_pub_path, "rb").read() if self.rsa_pub_path else None

                for rect in label.rects:
                    x0, x1 = rect.x()*sx, (rect.x()+rect.width())*sx
                    y0, y1 = rect.y()*sy, (rect.y()+rect.height())*sy
                    box    = fitz.Rect(x0, y0, x1, y1)

                    # ── texte sous le rectangle ────────────────────────────
                    original_txt = page.get_text("text", clip=box)

                    if cipher_pub_pem and (original_txt.strip() or True):
                        # 1) capture « photo » de la zone (résolution 150 dpi)
                        snap_pix   = page.get_pixmap(clip=box, dpi=150)
                        snap_png   = snap_pix.tobytes("png")                       # bytes PNG

                        # 2) on emballe tout dans le payload JSON
                        payload = json.dumps({
                            "rect": [x0, y0, x1, y1],                              # position
                            "txt" : original_txt,                                  # texte brut
                            "img" : base64.b64encode(snap_png).decode()            # snapshot
                        })

                        blob = hybrid_encrypt(cipher_pub_pem, payload)

                        annot = page.add_text_annot(box.tl, "")
                        annot.set_info(subject="CAVBLOB", content=blob)
                        annot.update(opacity=0)        # totalement invisible

                    # caviardage visuel
                    page.add_redact_annot(box, fill=self.caviard_rgb)


                # --- polygones libres : on découpe finement la forme -----------------------
                def slice_poly_to_rects(poly_pts, step=2):
                    """
                    Poly-remplissage complet :
                    • balaye le polygone avec un pas vertical de <step> points (≈ 0,7 mm).
                    • pour chaque bande horizontale [y, y+step], calcule les
                        intersections de la ligne médiane avec les arêtes,
                        puis loge un rectangle plein entre chaque paire d’intersections.
                    """
                    xs, ys = zip(*poly_pts)
                    y_min, y_max = min(ys), max(ys)
                    rects = []

                    edges = list(zip(poly_pts, poly_pts[1:] + poly_pts[:1]))  # arêtes (x0,y0)->(x1,y1)

                    y = y_min
                    while y < y_max:
                        y_next = min(y + step, y_max)
                        y_mid = (y + y_next) / 2.0                # ligne d’échantillonnage

                        inter = []
                        for (x0, y0), (x1, y1) in edges:
                            # sauter les segments horizontaux
                            if y0 == y1:
                                continue
                            # ray-casting : la ligne horizontale croise-t-elle l’arête ?
                            if (y0 <= y_mid < y1) or (y1 <= y_mid < y0):
                                t = (y_mid - y0) / (y1 - y0)
                                inter.append(x0 + t * (x1 - x0))

                        inter.sort()
                        for i in range(0, len(inter) - 1, 2):
                            x_left, x_right = inter[i], inter[i + 1]
                            if x_right > x_left:                  # sécurité
                                rects.append(fitz.Rect(x_left, y, x_right, y_next))
                        y = y_next

                    return rects


                for poly in label.polys:
                    # conversion vers coordonnées PDF
                    pts_pdf = [(pt.x() * sx, pt.y() * sy) for pt in poly]
                    for r in slice_poly_to_rects(pts_pdf, step=4):     # 4 pt ≈ 1,4 mm
                        page.add_redact_annot(r, fill=self.caviard_rgb)


                # appliquer toutes les redactions de la page une fois seulement
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
        QWidget       { background:#f5f6fa; color:#222; font:13px 'Segoe UI',sans-serif; }
        QScrollArea   { border:none; }
        QPushButton   { background:#fff; border:1px solid #c8c8c8; border-radius:6px; padding:6px 12px; }
        QPushButton:hover   { background:#e9f1ff; border-color:#5b8eff; }
        QPushButton:pressed { background:#d0e0ff; }
        QComboBox     { background:#fff; border:1px solid #c8c8c8; border-radius:6px; padding:4px 8px 4px 6px; }
        QComboBox::drop-down { border-left:0; }
        """)

    def apply_dark_theme(self):
        self.setStyleSheet("""
        QWidget       { background:#1e1e1e; color:#e0e0e0; font:13px 'Segoe UI',sans-serif; }
        QScrollArea   { border:none; }
        QPushButton   { background:#2b2b2b; border:1px solid #3d3d3d; border-radius:6px; padding:6px 12px; }
        QPushButton:hover   { background:#3a3a3a; border-color:#5b8eff; }
        QPushButton:pressed { background:#444; }
        QComboBox     { background:#2b2b2b; border:1px solid #3d3d3d; border-radius:6px; padding:4px 8px 4px 6px; }
        QComboBox::drop-down { border-left:0; }
        """)

    def choose_color(self):
        initial = QColor(*(int(c * 255) for c in self.caviard_rgb))
        col = QColorDialog.getColor(initial, self,
                                    "Choisir la couleur de caviardage",
                                    QColorDialog.ShowAlphaChannel)
        if col.isValid():
            self.caviard_rgb = (col.red() / 255.0, col.green() / 255.0, col.blue() / 255.0)
            for w in self.image_widgets:
                w.blackout_color = QColor(col.red(), col.green(), col.blue(), 180)
                w.update()

    def mode_changed(self, index):
        modes = {0: "rect", 1: "free", 2: "hand"}
        self.current_mode = modes.get(index, "rect")
        for w in self.image_widgets:
            w.set_mode(self.current_mode)

    def pick_public_key(self):
        p,_ = QFileDialog.getOpenFileName(self, "Clé publique PEM", "", "PEM (*.pem)")
        if p: self.rsa_pub_path = p

    def pick_private_key(self):
        p,_ = QFileDialog.getOpenFileName(self, "Clé privée PEM", "", "PEM (*.pem)")
        if p: self.rsa_priv_path = p

    def extract_original(self):
        if not (self.pdf_path and self.rsa_priv_path):
            QMessageBox.warning(self, "Manque clé/ PDF",
                                "Sélectionnez d'abord le PDF et la clé *privée*.")
            return

        with open(self.rsa_priv_path, "rb") as fh:
            priv_pem = fh.read()

        doc = fitz.open(self.pdf_path)
        recovered = []
        for page in doc:
            for annot in page.annots() or []:
                if annot.info.get("subject") != "CAVBLOB":
                    continue
                blob = annot.info.get("content", "")
                try:
                    payload = json.loads(hybrid_decrypt(priv_pem, blob))
                    rect    = fitz.Rect(*payload["rect"])

                    # 1) repeindre la zone en blanc (on « efface » le masque noir recopié)
                    dst_page.draw_rect(rect, fill=(1,1,1), overlay=True)

                    # 2) recoller le snapshot d’origine
                    img_bytes = base64.b64decode(payload["img"])
                    dst_page.insert_image(
                        rect, stream=img_bytes,
                        keep_proportion=False, overlay=True
                    )
                except Exception:
                    pass
        doc.close()

        if not recovered:
            QMessageBox.information(self, "Aucun résultat",
                                    "Rien n'a pu être déchiffré avec cette clé.")
            return

        out,_ = QFileDialog.getSaveFileName(self, "Enregistrer", "restaure.txt", "TXT (*.txt)")
        if out:
            with open(out, "w", encoding="utf-8") as f:
                f.write("\n\n--- page break ---\n\n".join(recovered))
            QMessageBox.information(self, "OK", f"Texte enregistré : {out}")

    def restore_pdf(self):
        if not (self.pdf_path and self.rsa_priv_path):
            QMessageBox.warning(self, "Manque clé/PDF",
                                "Chargez le PDF et la clé *privée* d’abord.")
            return

        with open(self.rsa_priv_path, "rb") as fh:
            priv_pem = fh.read()

        src = fitz.open(self.pdf_path)
        dst = fitz.open()                       # PDF vierge
        for pno, page in enumerate(src):
            dst.new_page(width=page.rect.width, height=page.rect.height)
            dst_page = dst[pno]

            # on commence par recopier tout le contenu actuel (images, dessin, etc.)
            dst_page.show_pdf_page(page.rect, src, pno)

            # puis on regarde les blobs
            for annot in page.annots() or []:
                if annot.info.get("subject") != "CAVBLOB":
                    continue
                blob = annot.info.get("content", "")
                try:
                    payload   = json.loads(hybrid_decrypt(priv_pem, blob))
                    rect      = fitz.Rect(*payload["rect"])

                    # 1) recoller l’image d’origine (snapshot)
                    img_bytes = base64.b64decode(payload["img"])
                    dst_page.insert_image(
                        rect,
                        stream=img_bytes,
                        keep_proportion=False,     # on étire exactement dans le rectangle
                        overlay=True               # au-dessus de TOUT le contenu existant
                    )
                except Exception:
                    pass

        out, _ = QFileDialog.getSaveFileName(self, "Enregistrer PDF restauré",
                                            "restaure.pdf", "PDF (*.pdf)")
        if out:
            dst.save(out, garbage=4, deflate=True)
            QMessageBox.information(self, "OK",
                                    f"PDF restauré enregistré :\n{out}")

        src.close()
        dst.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BlackoutPDF()
    window.show()
    sys.exit(app.exec_())
