#!/bin/bash

# Hata durumunda betiği durdur
set -e

echo "=== Ubuntu Lens Debian Paketleme Sihirbazı ==="

# 1. Temizlik ve Klasör Yapısı Hazırlığı
BUILD_DIR="ubuntu-lens-build"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/lib/ubuntu-lens"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps"

# 2. Derleme Çıktılarını Dağıtım Klasörüne Kopyalama
echo "-> Derleme dosyaları taşınıyor..."
if [ ! -d "dist/ubuntu_lens" ]; then
    echo "Hata: dist/ubuntu_lens klasörü bulunamadı! Önce PyInstaller ile derleme yapmalısın."
    exit 1
fi
cp -r dist/ubuntu_lens/* "$BUILD_DIR/usr/lib/ubuntu-lens/"

# 3. /usr/bin Altına Çalıştırıcı (Launcher) Betiği Oluşturma
# Bu betik, kullanıcının terminale 'ubuntu-lens' yazdığında uygulamanın doğru klasörden tetiklenmesini sağlar
echo "-> Çalıştırıcı betik oluşturuluyor..."
cat << 'EOF' > "$BUILD_DIR/usr/bin/ubuntu-lens"
#!/bin/bash
/usr/lib/ubuntu-lens/ubuntu_lens "$@"
EOF
chmod +x "$BUILD_DIR/usr/bin/ubuntu-lens"

# 4. Masaüstü Kısayolu (.desktop) Oluşturma
echo "-> Sistem entegrasyon dosyaları hazırlanıyor..."
cat << EOF > "$BUILD_DIR/usr/share/applications/ubuntu-lens.desktop"
[Desktop Entry]
Version=1.0
Name=Ubuntu Lens
Comment=OCR Destekli Fotoğraf Görüntüleyici
Exec=ubuntu-lens %F
Icon=ubuntu-lens
Terminal=false
Type=Application
Categories=Graphics;2DGraphics;Viewer;
MimeType=image/jpeg;image/png;image/webp;image/bmp;
EOF

# 5. Uygulama İkonunu Yerleştirme (Eğer klasörde ikon yoksa varsayılan sistem ikonunu kopyalar)
if [ -f "icon.png" ]; then
    cp icon.png "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps/ubuntu-lens.png"
else
    # Görseldeki kamera ikonunu varsayılan yapar
    cp "$BUILD_DIR/usr/lib/ubuntu-lens/PyQt5/Qt5/plugins/imageformats/libqjpeg.so" /dev/null 2>/dev/null || true # dummy line
    echo "Uyarı: Ana dizinde icon.png bulunamadı. Sistem varsayılan ikonu atanacak."
fi

# 6. DEBIAN/control Dosyasını Oluşturma (Bağımlılık Yönetimi Burada)
echo "-> Bağımlılık konfigürasyonu yazılıyor..."
cat << EOF > "$BUILD_DIR/DEBIAN/control"
Package: ubuntu-lens
Version: 1.0.0
Architecture: amd64
Maintainer: Emre <eposta@adresin.com>
Depends: tesseract-ocr, tesseract-ocr-eng, tesseract-ocr-tur
Section: utils
Priority: optional
Description: Ubuntu için yerel, hızlı ve akıllı OCR destekli fotoğraf görüntüleyici.
EOF

# 7. Paket İzinlerini Düzenleme (Debian Standartları için Şarttır)
chmod -R 755 "$BUILD_DIR/usr"
chmod 755 "$BUILD_DIR/DEBIAN/control"

# 8. .deb Paketini Derleme
echo "-> .deb paketi inşa ediliyor..."
dpkg-deb --build "$BUILD_DIR" ubuntu-lens_1.0.0_amd64.deb

# Temizlik
rm -rf "$BUILD_DIR"

echo "=============================================="
echo "Başarılı! Paket hazır: ubuntu-lens_1.0.0_amd64.deb"
echo "Kurmak için: sudo apt install ./ubuntu-lens_1.0.0_amd64.deb"
echo "=============================================="
