#!/bin/bash

set -e

APP="BlackOutPDF"
BIN_NAME="BOPDF"
APPDIR="$APP.AppDir"
ICON_PNG="BOPDF.png"   # adapte ici si besoin
ICON_DESKTOP="BOPDF"
ICONS_DIR="icons"
PYTHON_SCRIPT="$BIN_NAME.py"

echo "==> Nettoyage..."
rm -rf dist/ build/ __pycache__/
rm -f *.spec
rm -rf "$APPDIR" "$APP-x86_64.AppImage"

echo "==> Build PyInstaller..."
pyinstaller --noconfirm --onefile --windowed --icon="$ICON_PNG" --add-data "$ICONS_DIR:$ICONS_DIR" --add-data "$ICON_PNG:." "$PYTHON_SCRIPT"

echo "==> Création de la structure AppDir..."
mkdir -p "$APPDIR/usr/share/applications"
cp "dist/$BIN_NAME" "$APPDIR/$BIN_NAME"
cp "$ICON_PNG" "$APPDIR/$ICON_PNG"
cp -r "$ICONS_DIR" "$APPDIR/$ICONS_DIR"

echo "==> Génération du .desktop..."
cat > "$APPDIR/usr/share/applications/blackoutpdf.desktop" <<EOF
[Desktop Entry]
Name=BlackOutPDF
Comment=Outil de caviardage PDF
Exec=AppRun
Icon=$ICON_DESKTOP
Terminal=false
Type=Application
Categories=Utility;Office;
MimeType=application/pdf;
EOF

cp "$APPDIR/usr/share/applications/blackoutpdf.desktop" "$APPDIR/"

echo "==> Génération du script AppRun..."
cat > "$APPDIR/AppRun" <<EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${0}")")"
export PATH="\${HERE}:\${PATH}"
exec "\${HERE}/$BIN_NAME" "\$@"
EOF
chmod +x "$APPDIR/AppRun"

# Télécharger appimagetool si absent
if ! [ -f appimagetool-x86_64.AppImage ]; then
    echo "==> Téléchargement de appimagetool..."
    wget -q 'https://github.com/AppImage/AppImageKit/releases/latest/download/appimagetool-x86_64.AppImage'
    chmod +x appimagetool-x86_64.AppImage
fi

echo "==> Construction de l'AppImage..."
./appimagetool-x86_64.AppImage "$APPDIR" "$APP-x86_64.AppImage"

if [ -f "$APP-x86_64.AppImage" ]; then
    echo -e "\n✔️ Build terminé !"
    echo "Ton AppImage est prêt : $APP-x86_64.AppImage"
else
    echo "❌ Build AppImage échoué !"
    exit 1
fi
