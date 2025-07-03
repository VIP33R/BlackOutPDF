# BlackOutPDF 🇫🇷

![Logo BlackOutPDF](./BOPDF.png)

**BlackOutPDF** est une application graphique pour Linux permettant de caviarder, surligner, commenter, signer, tamponner et exporter des PDF de façon sécurisée (avec ou sans mot de passe), 100% offline.

---

## ✨ Fonctionnalités principales

- **Chargement de PDF** multi-pages
- **Caviardage** (noircir) par sélection libre
- **Surlignage** façon surligneur jaune
- **Ajout de texte**, commentaires et annotations
- **Insertion de signatures** (depuis image PNG/JPG)
- **Ajout de tampons** personnalisés
- **Zoom avant/arrière** sur toutes les pages
- **Undo** (annulation de la dernière action)
- **OCR automatique** (Tesseract)
- **Export PDF sécurisé** (avec ou sans mot de passe, caviardage irréversible)
- **Thème sombre / clair**
- **Standalone : AppImage portable pour tout Linux**
- **Multi-plateforme** (PyQt6, PyMuPDF, Pillow, Tesseract)

---

## 📦 Installation


### **Build manuel (dev Python)**

- Cloner le repo :
    ```bash
    git clone https://github.com/VIP33R/BlackOutPDF.git
    cd BlackOutPDF
    ```
- Créer un venv et installer les dépendances :
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
- Installer Tesseract OCR sur votre système :
    ```bash
    sudo apt install tesseract-ocr
    ```
- Lancer l’application en mode dev :
    ```bash
    python BOPDF.py
    ```

---

## 🛠️ Compilation AppImage (avancé)

- Après modification du code, build l’exécutable avec :
    ```bash
    ./ultimate_build.sh
    ```
- Tu obtiens `BlackOutPDF-x86_64.AppImage` prêt à distribuer !

---

## 💻 Raccourci Menu Linux

Pour ajouter BlackOutPDF au menu de ton système :

1. Crée `~/.local/share/applications/blackoutpdf.desktop`
2. Exemple de contenu :
    ```desktop
    [Desktop Entry]
    Name=BlackOutPDF
    Exec=/chemin/vers/BlackOutPDF-x86_64.AppImage
    Icon=/chemin/vers/BOPDF.png
    Type=Application
    Categories=Utility;Office;
    MimeType=application/pdf;
    ```

---

## 🧩 Dépendances

- Python 3.7+
- PyQt6
- PyMuPDF (fitz)
- Pillow
- pytesseract
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (à installer sur le système)

---

## 🗂️ Structure du projet

```txt
BlackOutPDF/
├── BOPDF.py             # Code source principal
├── icons/               # Icônes SVG
├── BOPDF.png            # Logo principal
├── dist/                # Binaire PyInstaller
├── ultimate_build.sh    # Script packaging AppImage (clean + build)
├── BlackOutPDF.AppDir/  # Structure temporaire AppImage
├── ...
