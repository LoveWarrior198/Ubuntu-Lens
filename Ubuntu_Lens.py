import sys
import os
import cv2
import pytesseract
from pytesseract import Output
import urllib.parse
import webbrowser

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, 
    QAction, QFileDialog, QToolBar, QMenu, QToolButton, 
    QMessageBox, QLineEdit, QGraphicsProxyWidget
)
from PyQt5.QtGui import QPixmap, QImage, QIcon, QPainter
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRectF

class OCRWorker(QThread):
    """
    OCR işlemini arayüzü dondurmadan arka planda yapmak için kullanılan Thread sınıfı.
    OpenCV ile ön işleme (DPI/Çözünürlük düzeltme) bu aşamada yapılır.
    """
    finished = pyqtSignal(dict, float)
    error = pyqtSignal(str)

    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path

    def run(self):
        try:
            # Görüntüyü OpenCV ile oku
            img = cv2.imread(self.image_path)
            if img is None:
                raise ValueError("Görüntü okunamadı.")

            # Büyütme oranı (Ekran görüntüleri için 2x idealdir)
            scale_factor = 2.0
            
            # 1. Upscaling (Büyütme)
            width = int(img.shape[1] * scale_factor)
            height = int(img.shape[0] * scale_factor)
            dim = (width, height)
            resized = cv2.resize(img, dim, interpolation=cv2.INTER_CUBIC)

            # 2. Grayscale (Siyah-beyaza çevirme)
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

            # 3. Thresholding (Binarization - Arka planı temizleyip yazıları belirginleştirme)
            # Otsu's thresholding ekran görüntüleri için genelde en iyi sonucu verir
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # OCR İşlemi (İngilizce ve Türkçe)
            custom_config = r'-l eng+tur --oem 3 --psm 3'
            data = pytesseract.image_to_data(thresh, output_type=Output.DICT, config=custom_config)

            self.finished.emit(data, scale_factor)

        except Exception as e:
            self.error.emit(str(e))

class InteractiveView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        
        # Zoom yaparken farenin olduğu yeri merkez alır
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse) 
        # Pencereyi büyütüp küçültürken pan (kaydırma) merkezini korur
        # Pencereyi büyütüp küçültürken pan (kaydırma) merkezini korur
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter) 
        
        self.is_custom_zoomed = False

    def set_image_ready(self):
        """Yeni resim yüklendiğinde çağrılır."""
        self.is_custom_zoomed = False
        self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)

    def get_fit_scale(self):
        """Pencereye tam sığdırma oranını matematiksel olarak hesaplar."""
        view_rect = self.viewport().rect()
        scene_rect = self.scene().sceneRect()
        
        if scene_rect.isEmpty() or view_rect.isEmpty():
            return 1.0
            
        x_ratio = view_rect.width() / scene_rect.width()
        y_ratio = view_rect.height() / scene_rect.height()
        
        # KeepAspectRatio mantığı: yatay veya dikeyden dar olan oranı seç
        return min(x_ratio, y_ratio)

    def wheelEvent(self, event):
        # Kullanıcı fare tekerleğine dokunduğu an serbest zoom moduna geç
        self.is_custom_zoomed = True
        
        if event.angleDelta().y() > 0:
            self.scale(1.15, 1.15)
        else:
            self.scale(0.85, 0.85)

    def resizeEvent(self, event):
        if not self.scene() or self.scene().sceneRect().isEmpty():
            super().resizeEvent(event)
            return

        # Pencere boyutu değişmeden önceki sığdırma katsayısını al
        old_fit_scale = self.get_fit_scale()
        
        # Standart Qt resize işlemini yap (viewport arka planda güncellenir)
        super().resizeEvent(event)
        
        # Pencere boyutu değiştikten sonraki sığdırma katsayısını al
        new_fit_scale = self.get_fit_scale()
        
        if not self.is_custom_zoomed:
            # Kullanıcı serbest zoom yapmadıysa resmi pencereye sıkıca oturt
            self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)
        else:
            # Kullanıcı zoom yaptıysa;
            # Pencerenin büyüme katsayısını hesapla ve mevcut zoom'un üstüne ekle.
            # Böylece pencere tam ekran yapıldığında görüntü de orantılı olarak devasa olur.
            ratio = new_fit_scale / old_fit_scale if old_fit_scale > 0 else 1.0
            self.scale(ratio, ratio)
        
        
class UbuntuLensApp(QMainWindow):
    def __init__(self, image_path=None):
        super().__init__()
        self.setWindowTitle("Ubuntu Lens")
        self.resize(1024, 768)
        self.image_path = image_path
        self.ocr_boxes = [] # Üretilen metin kutularını tutmak için
        
        self.init_ui()

        if self.image_path and os.path.exists(self.image_path):
            self.load_image(self.image_path)
        else:
            self.open_file_dialog()

    def init_ui(self):
        # --- Toolbar (Araç Çubuğu) ---
        toolbar = QToolBar("Ana Araç Çubuğu")
        toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        # Dosya Aç
        open_action = QAction("Aç...", self)
        open_action.triggered.connect(self.open_file_dialog)
        toolbar.addAction(open_action)

        toolbar.addSeparator()

        # Yakınlaştırma Kontrolleri
        zoom_in_action = QAction("Yakınlaştır (+)", self)
        zoom_in_action.triggered.connect(self.zoom_in)
        toolbar.addAction(zoom_in_action)

        zoom_out_action = QAction("Uzaklaştır (-)", self)
        zoom_out_action.triggered.connect(self.zoom_out)
        toolbar.addAction(zoom_out_action)
        
        toolbar.addSeparator()

        # OCR Butonu
        self.ocr_action = QAction("👁️ Metni Tara (OCR)", self)
        self.ocr_action.triggered.connect(self.start_ocr)
        toolbar.addAction(self.ocr_action)

        # Boşluk (Menüyü sağa yaslamak için)
        spacer = QAction(self)
        spacer.setSeparator(True)
        toolbar.addAction(spacer)

        # Sağ Üst Menü (Hamburger Menü Benzeri)
        menu_button = QToolButton()
        menu_button.setText("≡")
        menu_button.setPopupMode(QToolButton.InstantPopup)
        
        main_menu = QMenu()
        
        # Google Görsellerde Ara Action
        google_search_action = QAction("Google Lens ile Görsel Ara", self)
        google_search_action.triggered.connect(self.search_google_images)
        main_menu.addAction(google_search_action)
        
        menu_button.setMenu(main_menu)
        toolbar.addWidget(menu_button)

        # --- Ana Görüntüleme Alanı ---
        # --- Ana Görüntüleme Alanı ---
        self.scene = QGraphicsScene()
        self.view = InteractiveView(self.scene, self) # Yeni sınıfımızı çağırdık
        self.setCentralWidget(self.view)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setRenderHint(QPainter.Antialiasing, False)
        
        
        self.pixmap_item = None

    def open_file_dialog(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Fotoğraf Aç", "", "Images (*.png *.xpm *.jpg *.jpeg *.bmp *.webp)")
        if file_name:
            self.load_image(file_name)

    def load_image(self, path):
        self.image_path = path
        self.scene.clear()
        self.ocr_boxes.clear()
        
        pixmap = QPixmap(self.image_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Hata", "Görüntü yüklenemedi.")
            return

        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        
        # Resmi ortala
# Resmi yeni akıllı view üzerinden sığdır ve zoom state'ini sıfırla
        self.view.set_image_ready()
        
        # OCR butonunu tekrar aktif et
        self.ocr_action.setEnabled(True)
        self.setWindowTitle(f"Ubuntu Lens - {os.path.basename(path)}")

    def zoom_in(self):
        self.view.scale(1.2, 1.2)

    def zoom_out(self):
        self.view.scale(0.8, 0.8)

    def start_ocr(self):
        if not self.image_path:
            return

        # Kullanıcı birden fazla kez basamasın
        self.ocr_action.setEnabled(False)
        self.setWindowTitle(f"Ubuntu Lens - OCR İşleniyor... Lütfen bekleyin.")

        # Thread'i başlat
        self.worker = OCRWorker(self.image_path)
        self.worker.finished.connect(self.on_ocr_finished)
        self.worker.error.connect(self.on_ocr_error)
        self.worker.start()

    def on_ocr_finished(self, data, scale_factor):
        self.setWindowTitle(f"Ubuntu Lens - {os.path.basename(self.image_path)}")
        
        # Satırları aynı kutuda birleştirmek için sözlük
        line_groups = {}
        n_boxes = len(data['text'])
        
        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = float(data['conf'][i])
            
            # Sadece güvenilir ve boş olmayan verileri al
            if text and conf > 40:
                # Tesseract'ın yapısal hiyerarşisi: Blok -> Paragraf -> Satır
                line_id = f"{data['block_num'][i]}_{data['par_num'][i]}_{data['line_num'][i]}"
                
                left = data['left'][i]
                top = data['top'][i]
                width = data['width'][i]
                height = data['height'][i]
                right = left + width
                bottom = top + height
                
                if line_id not in line_groups:
                    line_groups[line_id] = {
                        'left': left,
                        'top': top,
                        'right': right,
                        'bottom': bottom,
                        'text': text
                    }
                else:
                    prev_right = line_groups[line_id]['right']
                    distance = left - prev_right
                    
                    # Mesafe Kontrolü: 
                    # Eğer iki parça birbirine çok yakınsa (API key gibi) boşluksuz birleştir.
                    # Değilse normal boşluk bırak. (Scale factor 2.0 olduğu için 15px tolerans makuldür)
                    space = "" if distance < 15 else " "
                    
                    line_groups[line_id]['text'] += space + text
                    
                    # Çerçeveyi (Bounding Box) yeni kelimeyi kapsayacak şekilde genişlet
                    line_groups[line_id]['left'] = min(line_groups[line_id]['left'], left)
                    line_groups[line_id]['top'] = min(line_groups[line_id]['top'], top)
                    line_groups[line_id]['right'] = max(line_groups[line_id]['right'], right)
                    line_groups[line_id]['bottom'] = max(line_groups[line_id]['bottom'], bottom)

        # Gruplanmış, tek parça satırları ekrana çiz
        for line_id, box in line_groups.items():
            # Ölçeklenmiş 2x koordinatları orijinal 1x resme geri uyarla
            x = int(box['left'] / scale_factor)
            y = int(box['top'] / scale_factor)
            w = int((box['right'] - box['left']) / scale_factor)
            h = int((box['bottom'] - box['top']) / scale_factor)

            self.create_selectable_text_box(x, y, w, h, box['text'])

    def on_ocr_error(self, err_msg):
        self.setWindowTitle(f"Ubuntu Lens - {os.path.basename(self.image_path)}")
        self.ocr_action.setEnabled(True)
        QMessageBox.critical(self, "OCR Hatası", f"Tesseract işlenirken bir hata oluştu:\n{err_msg}\n\n'tesseract-ocr' paketinin yüklü olduğundan emin olun.")

    def create_selectable_text_box(self, x, y, w, h, text):
        """
        Orijinal resmin üzerine, yazısı saydam, sadece seçimi görünen bir metin kutusu ekler.
        Böylece görsel bozulmaz ama metin kopyalanabilir olur.
        """
        line_edit = QLineEdit(text)
        line_edit.setReadOnly(True)
        # CSS Hilesi: Arka plan şeffaf, metin şeffaf, kenarlık yeşil saydam, seçim rengi belirgin.
        line_edit.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: transparent; 
                border: 1px solid rgba(0, 255, 0, 80);
                selection-background-color: rgba(0, 120, 215, 120);
                selection-color: black;
            }
        """)
        line_edit.setFixedSize(w + 4, h + 4) # Seçim kutusu biraz ferah olsun

        # QLineEdit'i Scene üzerine yerleştirmek için QGraphicsProxyWidget kullanıyoruz
        proxy = self.scene.addWidget(line_edit)
        proxy.setPos(x - 2, y - 2)
        
        self.ocr_boxes.append(proxy)

    def search_google_images(self):
        """
        Web tarayıcısında Google Lens veya Görseller aramasını tetikler.
        Not: Yerel dosya URL'leri her zaman otomatik yüklenmeyebilir, 
        bu durumda sürükle-bırak gerekebileceğini kullanıcıya bildiriyoruz.
        """
        if not self.image_path:
            return
            
        file_url = urllib.parse.quote(self.image_path)
        # Direkt lens sayfasına yönlendir (Bazı tarayıcılar yerel dosya parametresini güvenlik için reddedebilir)
        search_url = "https://images.google.com/"
        
        msg = ("Yerel dosya gizliliği nedeniyle, tarayıcınız açıldığında görseli "
               "Google Lens alanına sürükleyip bırakmanız gerekebilir.\n\nTarayıcı açılıyor...")
        QMessageBox.information(self, "Google Görseller'de Ara", msg)
        
        webbrowser.open_new_tab(search_url)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Terminalden path verilirse direkt aç, verilmezse boş başlat (dialog ile)
    initial_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    viewer = UbuntuLensApp(initial_path)
    viewer.show()
    
    sys.exit(app.exec_())
