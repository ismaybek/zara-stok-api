from flask import Flask, request, jsonify, render_template_string, send_from_directory
from flask_cors import CORS
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import logging
from datetime import datetime
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
CORS(app)  # Mobil uygulama için CORS

# Logging
logging.basicConfig(level=logging.INFO)

# Global değişkenler
driver_pool = {}
tracking_items = {}
bot_thread = None
bot_running = False

# Email ayarları
EMAIL = "t.aybek.33@gmail.com"
APP_PASSWORD = "gvodrtnqtvnzgtnr"

# Mobil uyumlu HTML template
MOBILE_HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Zara Stok Takip</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 600px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 28px;
            margin-bottom: 10px;
        }
        
        .card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .input-group {
            margin-bottom: 15px;
        }
        
        .input-group label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 600;
        }
        
        .input-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }
        
        .input-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .btn {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .btn-primary {
            background: #667eea;
            color: white;
        }
        
        .btn-primary:hover {
            background: #5568d3;
        }
        
        .btn-success {
            background: #48bb78;
            color: white;
        }
        
        .btn-danger {
            background: #f56565;
            color: white;
        }
        
        .result {
            margin-top: 20px;
            padding: 15px;
            border-radius: 8px;
            display: none;
        }
        
        .result.success {
            background: #c6f6d5;
            color: #22543d;
            border: 2px solid #48bb78;
        }
        
        .result.error {
            background: #fed7d7;
            color: #742a2a;
            border: 2px solid #f56565;
        }
        
        .result.warning {
            background: #feebc8;
            color: #744210;
            border: 2px solid #ed8936;
        }
        
        .loading {
            text-align: center;
            padding: 20px;
            display: none;
        }
        
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .tracking-list {
            margin-top: 20px;
        }
        
        .tracking-item {
            background: #f7fafc;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        
        .tracking-item h4 {
            margin-bottom: 5px;
            color: #2d3748;
        }
        
        .tracking-item p {
            color: #718096;
            font-size: 14px;
        }
        
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            margin-top: 5px;
        }
        
        .status-available {
            background: #c6f6d5;
            color: #22543d;
        }
        
        .status-unavailable {
            background: #fed7d7;
            color: #742a2a;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛍️ Zara Stok Takip</h1>
            <p>Ürün stok durumunu anında kontrol edin</p>
        </div>
        
        <div class="card">
            <h2>Stok Kontrol Et</h2>
            <div class="input-group">
                <label>Ürün URL'i veya Stok Kodu</label>
                <input type="text" id="stockInput" placeholder="https://www.zara.com/tr/tr/... veya 3920/958/800">
            </div>
            <button class="btn btn-primary" onclick="checkStock()">🔍 Kontrol Et</button>
            
            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>Kontrol ediliyor...</p>
            </div>
            
            <div class="result" id="result"></div>
        </div>
        
        <div class="card">
            <h2>Otomatik Takip</h2>
            <div class="input-group">
                <label>Takip Etmek İstediğiniz URL</label>
                <input type="text" id="trackInput" placeholder="https://www.zara.com/tr/tr/...">
            </div>
            <button class="btn btn-success" onclick="addTracking()">➕ Takip Listesine Ekle</button>
            <button class="btn btn-danger" onclick="stopBot()">⏹️ Botu Durdur</button>
            <button class="btn btn-primary" onclick="startBot()">▶️ Botu Başlat</button>
        </div>
        
        <div class="card tracking-list">
            <h2>Takip Listesi</h2>
            <div id="trackingList">
                <p>Henüz takip edilen ürün yok.</p>
            </div>
        </div>
    </div>
    
    <script>
        async function checkStock() {
            const input = document.getElementById('stockInput').value;
            if (!input.trim()) {
                showResult('Lütfen bir URL veya stok kodu girin!', 'warning');
                return;
            }
            
            document.getElementById('loading').style.display = 'block';
            document.getElementById('result').style.display = 'none';
            
            try {
                const response = await fetch('/api/check', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: input})
                });
                
                const data = await response.json();
                document.getElementById('loading').style.display = 'none';
                
                if (data.success) {
                    const status = data.available ? '✅ STOKTA VAR' : '❌ STOKTA YOK';
                    const className = data.available ? 'success' : 'error';
                    showResult(`${status}<br><strong>${data.product_name}</strong><br><a href="${data.url}" target="_blank">Ürünü Görüntüle</a>`, className);
                } else {
                    showResult(`Hata: ${data.message}`, 'error');
                }
            } catch (error) {
                document.getElementById('loading').style.display = 'none';
                showResult(`Bir hata oluştu: ${error.message}`, 'error');
            }
        }
        
        async function addTracking() {
            const input = document.getElementById('trackInput').value;
            if (!input.trim()) {
                showResult('Lütfen bir URL girin!', 'warning');
                return;
            }
            
            try {
                const response = await fetch('/api/track', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: input})
                });
                
                const data = await response.json();
                if (data.success) {
                    showResult('Ürün takip listesine eklendi!', 'success');
                    loadTrackingList();
                } else {
                    showResult(`Hata: ${data.message}`, 'error');
                }
            } catch (error) {
                showResult(`Bir hata oluştu: ${error.message}`, 'error');
            }
        }
        
        async function startBot() {
            try {
                const response = await fetch('/api/bot/start', {method: 'POST'});
                const data = await response.json();
                showResult(data.message, data.success ? 'success' : 'error');
            } catch (error) {
                showResult(`Hata: ${error.message}`, 'error');
            }
        }
        
        async function stopBot() {
            try {
                const response = await fetch('/api/bot/stop', {method: 'POST'});
                const data = await response.json();
                showResult(data.message, data.success ? 'success' : 'error');
            } catch (error) {
                showResult(`Hata: ${error.message}`, 'error');
            }
        }
        
        async function loadTrackingList() {
            try {
                const response = await fetch('/api/tracking/list');
                const data = await response.json();
                const listDiv = document.getElementById('trackingList');
                
                if (data.items && data.items.length > 0) {
                    listDiv.innerHTML = data.items.map(item => `
                        <div class="tracking-item">
                            <h4>${item.name}</h4>
                            <p>${item.url}</p>
                            <span class="status-badge ${item.status ? 'status-available' : 'status-unavailable'}">
                                ${item.status ? '✅ Stokta Var' : '❌ Stokta Yok'}
                            </span>
                        </div>
                    `).join('');
                } else {
                    listDiv.innerHTML = '<p>Henüz takip edilen ürün yok.</p>';
                }
            } catch (error) {
                console.error('Liste yüklenemedi:', error);
            }
        }
        
        function showResult(message, type) {
            const resultDiv = document.getElementById('result');
            resultDiv.innerHTML = message;
            resultDiv.className = 'result ' + type;
            resultDiv.style.display = 'block';
        }
        
        // Sayfa yüklendiğinde listeyi yükle
        loadTrackingList();
        
        // PWA - Service Worker kayıt
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/service-worker.js')
                    .then(reg => console.log('Service Worker kaydedildi'))
                    .catch(err => console.log('Service Worker hatası:', err));
            });
        }
        
        // PWA - Kurulum istemi
        let deferredPrompt;
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
            // Kurulum butonu göster
            showInstallButton();
        });
        
        function showInstallButton() {
            const installBtn = document.createElement('button');
            installBtn.className = 'btn btn-success';
            installBtn.innerHTML = '📱 Uygulamayı Yükle';
            installBtn.style.marginTop = '10px';
            installBtn.onclick = installApp;
            document.querySelector('.header').appendChild(installBtn);
        }
        
        async function installApp() {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                const { outcome } = await deferredPrompt.userChoice;
                console.log(`Kullanıcı seçimi: ${outcome}`);
                deferredPrompt = null;
            }
        }
        
        // PWA - Service Worker kayıt
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/service-worker.js')
                    .then(reg => console.log('Service Worker kaydedildi'))
                    .catch(err => console.log('Service Worker hatası:', err));
            });
        }
        
        // PWA - Kurulum istemi
        let deferredPrompt;
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
            // Kurulum butonu göster
            showInstallButton();
        });
        
        function showInstallButton() {
            const installBtn = document.createElement('button');
            installBtn.className = 'btn btn-success';
            installBtn.innerHTML = '📱 Uygulamayı Yükle';
            installBtn.style.marginTop = '10px';
            installBtn.onclick = installApp;
            document.querySelector('.header').appendChild(installBtn);
        }
        
        async function installApp() {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                const { outcome } = await deferredPrompt.userChoice;
                console.log(`Kullanıcı seçimi: ${outcome}`);
                deferredPrompt = null;
            }
        }
    </script>
</body>
</html>
"""

def get_driver():
    """WebDriver pool yönetimi"""
    thread_id = threading.current_thread().ident
    if thread_id not in driver_pool:
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        try:
            driver_pool[thread_id] = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            # Chrome bulunamazsa webdriver-manager kullan (cloud servisler için)
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver_pool[thread_id] = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver_pool[thread_id]

def check_stock_logic(url_or_code):
    """Stok kontrol mantığı"""
    driver = get_driver()
    
    if url_or_code.startswith('http'):
        url = url_or_code
    else:
        url = f"https://www.zara.com/tr/tr/arama?searchTerm={url_or_code}"
    
    try:
        driver.get(url)
        time.sleep(3)
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        page_source = driver.page_source
        
        # TÜKENDİ kontrolü
        if "BENZER ÜRÜNLER TÜKENDİ" in page_text or "TÜKENDİ" in page_text:
            return {'available': False, 'product_name': 'Ürün', 'url': driver.current_url}
        
        # EKLE kontrolü
        if "EKLE" in page_text.upper() and "TÜKENDİ" not in page_text.upper():
            # Ürün adını bul
            try:
                name = driver.find_element(By.CSS_SELECTOR, "h1").text
            except:
                name = "Ürün"
            return {'available': True, 'product_name': name, 'url': driver.current_url}
        
        return {'available': False, 'product_name': 'Ürün', 'url': driver.current_url}
    except Exception as e:
        logging.error(f"Stok kontrolü hatası: {e}")
        return None

@app.route('/')
def index():
    return render_template_string(MOBILE_HTML)

@app.route('/manifest.json')
def manifest():
    return send_from_directory('.', 'manifest.json', mimetype='application/manifest+json')

@app.route('/service-worker.js')
def service_worker():
    return send_from_directory('.', 'service-worker.js', mimetype='application/javascript')

@app.route('/api/check', methods=['POST'])
def check_stock():
    data = request.json
    url = data.get('url', '')
    
    result = check_stock_logic(url)
    if result:
        return jsonify({
            'success': True,
            'available': result['available'],
            'product_name': result['product_name'],
            'url': result['url']
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Stok kontrolü yapılamadı'
        })

@app.route('/api/track', methods=['POST'])
def add_tracking():
    data = request.json
    url = data.get('url', '')
    
    if url not in tracking_items:
        result = check_stock_logic(url)
        tracking_items[url] = {
            'name': result['product_name'] if result else 'Ürün',
            'status': result['available'] if result else False,
            'url': url
        }
        return jsonify({'success': True, 'message': 'Ürün eklendi'})
    return jsonify({'success': False, 'message': 'Ürün zaten listede'})

@app.route('/api/tracking/list', methods=['GET'])
def get_tracking_list():
    items = [{'url': k, **v} for k, v in tracking_items.items()]
    return jsonify({'items': items})

@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    """Botu başlat - Cloud serviste sürekli çalışır, telefon kapalı olsa bile"""
    global bot_thread, bot_running
    
    if bot_running:
        return jsonify({
            'success': False, 
            'message': 'Bot zaten çalışıyor. Arka planda kontrol yapıyor ve email gönderiyor.'
        })
    
    if not tracking_items:
        return jsonify({
            'success': False,
            'message': 'Önce takip listesine en az bir ürün ekleyin!'
        })
    
    bot_running = True
    bot_thread = threading.Thread(target=bot_loop, daemon=True)
    bot_thread.start()
    
    logging.info(f"Bot başlatıldı - {len(tracking_items)} ürün takip ediliyor")
    
    return jsonify({
        'success': True, 
        'message': f'Bot başlatıldı! {len(tracking_items)} ürün takip ediliyor. Her 10 dakikada bir kontrol yapılacak ve stok durumu değiştiğinde email gönderilecek. Telefonunuz kapalı olsa bile bot çalışmaya devam eder.'
    })

@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    global bot_running
    bot_running = False
    return jsonify({'success': True, 'message': 'Bot durduruldu'})

def bot_loop():
    """Bot döngüsü - her 10 dakikada bir kontrol eder
    
    Bu fonksiyon cloud serviste sürekli çalışır.
    Telefon veya bilgisayar kapalı olsa bile bot çalışmaya devam eder.
    """
    global bot_running
    
    logging.info("Bot döngüsü başlatıldı - 10 dakikada bir kontrol edecek")
    
    while bot_running:
        try:
            logging.info(f"Stok kontrolü yapılıyor... ({len(tracking_items)} ürün)")
            
            for url, item in tracking_items.items():
                try:
                    result = check_stock_logic(url)
                    if result and result['available'] != item['status']:
                        # Durum değişti, email gönder
                        logging.info(f"Stok durumu değişti: {item['name']}")
                        send_email_notification(url, result)
                        tracking_items[url]['status'] = result['available']
                        tracking_items[url]['name'] = result.get('product_name', item['name'])
                    else:
                        logging.info(f"Stok durumu değişmedi: {item['name']}")
                except Exception as e:
                    logging.error(f"Ürün kontrolü hatası ({url}): {e}")
            
            logging.info("Kontrol tamamlandı, 10 dakika bekleniyor...")
            
            # 10 dakika bekle (600 saniye)
            for _ in range(600):
                if not bot_running:
                    logging.info("Bot durduruldu")
                    break
                time.sleep(1)
                
        except Exception as e:
            logging.error(f"Bot döngüsü hatası: {e}")
            time.sleep(60)  # Hata durumunda 1 dakika bekle

def send_email_notification(url, result):
    """Email bildirimi gönder"""
    try:
        app_password = APP_PASSWORD.replace(" ", "")
        msg = MIMEMultipart()
        msg['From'] = EMAIL
        msg['To'] = EMAIL
        msg['Subject'] = f"🔔 Zara Stok Durumu - {result['product_name']}"
        
        body = f"{result['product_name']}\n"
        body += f"Durum: {'✅ STOKTA VAR' if result['available'] else '❌ STOKTA YOK'}\n"
        body += f"Link: {url}\n"
        body += f"Zaman: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL, app_password)
        server.send_message(msg)
        server.quit()
        
        logging.info("Email gönderildi")
    except Exception as e:
        logging.error(f"Email gönderilemedi: {e}")

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Zara Stok Takip API başlatılıyor...")
    print(f"📱 Mobil uyumlu arayüz: http://0.0.0.0:{port}")
    print("📧 Email: t.aybek.33@gmail.com")
    app.run(host='0.0.0.0', port=port, debug=False)

