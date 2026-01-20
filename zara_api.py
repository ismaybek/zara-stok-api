"""
Zara Stok Takip Botu - Flask API (Mobil Uygulama için)
zara_stock_bot.py'deki gelişmiş stok kontrol mantığı kullanılıyor
"""
import os
import time
import smtplib
import logging
import threading
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import requests

app = Flask(__name__)
CORS(app)

# Render.com için otomatik heartbeat başlat
def init_heartbeat():
    """Render.com ortamında otomatik heartbeat başlat"""
    global heartbeat_running, heartbeat_thread
    
    render_url = os.environ.get('RENDER_EXTERNAL_URL') or os.environ.get('SERVICE_URL')
    if render_url and not heartbeat_running:
        try:
            logging.info(f"Render.com ortamı tespit edildi: {render_url}")
            heartbeat_running = True
            heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
            heartbeat_thread.start()
            logging.info("Heartbeat otomatik başlatıldı (Render.com için)")
        except Exception as e:
            logging.error(f"Heartbeat başlatılamadı: {e}")

# İlk istek geldiğinde heartbeat başlat (Render.com için)
# Bu şekilde Flask tamamen başladıktan sonra başlar
_heartbeat_initialized = False

@app.before_request
def before_request():
    """Her istekten önce heartbeat'i başlat (sadece ilk seferinde)"""
    global _heartbeat_initialized
    if not _heartbeat_initialized:
        try:
            render_url = os.environ.get('RENDER_EXTERNAL_URL') or os.environ.get('SERVICE_URL')
            if render_url:
                init_heartbeat()
        except Exception as e:
            logging.warning(f"Heartbeat başlatılamadı (normal olabilir): {e}")
        finally:
            _heartbeat_initialized = True

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('zara_api.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Email ayarları
EMAIL = "t.aybek.33@gmail.com"
APP_PASSWORD = "gvodrtnqtvnzgtnr"

# Global değişkenler
tracking_list = []
bot_running = False
bot_thread = None
driver = None
tracked_items = {}  # Stok durumlarını saklamak için
heartbeat_running = False
heartbeat_thread = None

# Driver'ı paylaşımlı olarak başlat
def get_driver():
    global driver
    if driver is None:
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--headless=new')  # Yeni headless mod
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-software-rasterizer')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Render.com için binary location belirt (opsiyonel)
            import os
            chrome_binary = os.environ.get('GOOGLE_CHROME_BIN')
            if chrome_binary:
                chrome_options.binary_location = chrome_binary
                logging.info(f"Chrome binary kullanılıyor: {chrome_binary}")
            
            # Render.com için Chrome binary path kontrolü
            import shutil
            chrome_paths = [
                '/usr/bin/google-chrome',
                '/usr/bin/chromium-browser',
                '/usr/bin/chromium',
                '/snap/bin/chromium'
            ]
            
            chrome_binary_found = None
            for path in chrome_paths:
                if shutil.which(path) or os.path.exists(path):
                    chrome_binary_found = path
                    chrome_options.binary_location = path
                    logging.info(f"Chrome binary bulundu: {path}")
                    break
            
            # webdriver-manager ile ChromeDriver'ı otomatik indir
            # Önce Chrome binary bulunmalı, yoksa webdriver-manager hata verir
            if chrome_binary_found:
                try:
                    # ChromeDriverManager cache path ayarla (Render.com için)
                    os.environ['WDM_LOG_LEVEL'] = '0'  # Log seviyesini düşür
                    
                    # Chrome binary path'ini webdriver-manager'a söyle
                    driver_path = ChromeDriverManager().install()
                    if driver_path and os.path.exists(driver_path):
                        service = Service(driver_path)
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                        logging.info("WebDriver başarıyla başlatıldı (webdriver-manager ile)")
                    else:
                        raise Exception("ChromeDriverManager geçerli path döndürmedi")
                except Exception as e1:
                    logging.warning(f"webdriver-manager ile başlatılamadı: {e1}, doğrudan deniyor...")
                    # Fallback: Doğrudan başlatmayı dene
                    try:
                        driver = webdriver.Chrome(options=chrome_options)
                        logging.info("WebDriver başarıyla başlatıldı (doğrudan)")
                    except Exception as e2:
                        logging.error(f"Doğrudan başlatma da başarısız: {e2}")
                        raise Exception(f"WebDriver başlatılamadı. webdriver-manager: {e1}, doğrudan: {e2}")
            else:
                # Chrome binary bulunamadı, doğrudan dene (webdriver-manager olmadan)
                logging.warning("Chrome binary bulunamadı, doğrudan başlatmayı deniyor...")
                try:
                    driver = webdriver.Chrome(options=chrome_options)
                    logging.info("WebDriver başarıyla başlatıldı (doğrudan, binary bulunamadı)")
                except Exception as e:
                    logging.error(f"Doğrudan başlatma başarısız: {e}")
                    raise Exception(f"WebDriver başlatılamadı. Chrome binary bulunamadı ve doğrudan başlatma başarısız: {e}")
                
        except Exception as e:
            logging.error(f"WebDriver başlatılamadı: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            # Driver None olarak kalır, check_stock_logic bunu handle edecek
            return None
    return driver

# zara_stock_bot.py'deki check_stock metodunu Flask fonksiyonuna adapte ettik
def check_stock_logic(url_or_code):
    """
    Belirli bir stok kodunun veya URL'in stok durumunu kontrol et
    zara_stock_bot.py'deki gelişmiş check_stock metodu kullanılıyor
    """
    global driver
    
    # Driver'ı başlat - exception yakalama
    try:
        driver = get_driver()
    except Exception as e:
        logging.error(f"get_driver hatası: {e}")
        return {
            'available': False,
            'product_name': f'WebDriver başlatılamadı: {str(e)}',
            'url': url_or_code if url_or_code.startswith('http') else ''
        }
    
    # Driver başlatılamadıysa hata döndür
    if driver is None:
        return {
            'available': False,
            'product_name': 'WebDriver başlatılamadı (None döndü)',
            'url': url_or_code if url_or_code.startswith('http') else ''
        }
    
    # Driver'ın çalışıp çalışmadığını kontrol et
    try:
        # Basit bir test - eğer driver çalışmıyorsa exception fırlatır
        driver.current_url
    except Exception as e:
        logging.error(f"Driver çalışmıyor: {e}")
        # Driver'ı yeniden başlatmayı dene
        try:
            driver = None  # Reset
            driver = get_driver()
            if driver is None:
                return {
                    'available': False,
                    'product_name': 'WebDriver yeniden başlatılamadı',
                    'url': url_or_code if url_or_code.startswith('http') else ''
                }
        except Exception as e2:
            logging.error(f"Driver yeniden başlatılamadı: {e2}")
            return {
                'available': False,
                'product_name': f'WebDriver hatası: {str(e2)}',
                'url': url_or_code if url_or_code.startswith('http') else ''
            }
    
    # Eğer tam URL ise direkt kullan, değilse arama yap
    if url_or_code.startswith('http'):
        url = url_or_code
        is_direct_url = True
    else:
        url = f"https://www.zara.com/tr/tr/arama?searchTerm={url_or_code}"
        is_direct_url = False
    
    try:
        # Sayfayı yükle - exception yakalama
        try:
            driver.get(url)
            time.sleep(4)  # Sayfanın yüklenmesi için bekle
        except Exception as e:
            logging.error(f"Sayfa yüklenemedi ({url}): {e}")
            return {
                'available': False,
                'product_name': f'Sayfa yüklenemedi: {str(e)[:100]}',
                'url': url
            }
        
        # Cookie bildirimini kapat (varsa)
        try:
            cookie_button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-qa-action='accept-all-cookies'], button#onetrust-accept-btn-handler, button.cookie-button"))
            )
            cookie_button.click()
            time.sleep(1)
        except:
            pass  # Cookie butonu yoksa devam et
        
        current_url = url
        product_name = url_or_code
        
        # Eğer direkt URL değilse, arama sonuçlarından ürün bul
        if not is_direct_url:
            try:
                selectors = [
                    "article[data-qa-product-card]",
                    "article.product-card",
                    ".product-tile",
                    "a[href*='/tr/tr/product/']"
                ]
                
                product_cards = []
                for selector in selectors:
                    product_cards = driver.find_elements(By.CSS_SELECTOR, selector)
                    if product_cards:
                        break
                
                if not product_cards:
                    return {
                        'available': False,
                        'product_name': f"Ürün bulunamadı: {url_or_code}",
                        'url': url
                    }
                
                # İlk ürün linkine git
                product_link = product_cards[0].find_element(By.TAG_NAME, "a") if product_cards[0].tag_name != "a" else product_cards[0]
                product_url = product_link.get_attribute("href")
                if product_url:
                    driver.get(product_url)
                    time.sleep(3)
                    current_url = driver.current_url
            except Exception as e:
                logging.warning(f"Ürün sayfasına geçiş sırasında uyarı: {e}")
        
        # Şimdi ürün sayfasındayız, stok durumunu kontrol et
        try:
            # Ürün adını al
            name_selectors = [
                "h1[data-qa-product-name]",
                "h1.product-detail-info__name",
                ".product-detail-info__name",
                "h1.product-detail-header-info__name",
                "h1"
            ]
            for selector in name_selectors:
                try:
                    product_name_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    product_name = product_name_elem.text.strip()
                    if product_name:
                        break
                except:
                    continue
            
            # Stok durumunu kontrol et - Zara'nın gerçek metinlerine göre
            stock_available = None  # None = henüz belirlenmedi
            
            # Sayfa içeriğini al - exception yakalama
            try:
                page_source = driver.page_source
                page_text = driver.find_element(By.TAG_NAME, "body").text
            except Exception as e:
                logging.error(f"Sayfa içeriği alınamadı: {e}")
                return {
                    'available': False,
                    'product_name': f'Sayfa içeriği alınamadı: {str(e)[:100]}',
                    'url': current_url
                }
            
            # ÖNCELİK 1: "BENZER ÜRÜNLER TÜKENDİ" yazısını kontrol et (stokta yok)
            out_of_stock_indicators = [
                "BENZER ÜRÜNLER TÜKENDİ",
                "BENZER ÜRÜNLER TÜKENDI",
                "TÜKENDİ",
                "TÜKENDI",
                "tükendi",
                "out of stock"
            ]
            
            for indicator in out_of_stock_indicators:
                if indicator in page_text or indicator in page_source:
                    stock_available = False
                    logging.info(f"Stokta yok tespit edildi: '{indicator}' bulundu")
                    break
            
            # ÖNCELİK 2: "EKLE" butonu/metni kontrol et (stokta var)
            if stock_available is None:
                try:
                    # XPath ile "EKLE" içeren buton elementlerini ara
                    add_elements = driver.find_elements(By.XPATH, 
                        "//button[contains(translate(text(), 'ıİ', 'iI'), 'EKLE') or contains(translate(text(), 'ıİ', 'iI'), 'ekle')] | "
                        "//span[contains(translate(text(), 'ıİ', 'iI'), 'EKLE') or contains(translate(text(), 'ıİ', 'iI'), 'ekle')] | "
                        "//a[contains(translate(text(), 'ıİ', 'iI'), 'EKLE') or contains(translate(text(), 'ıİ', 'iI'), 'ekle')]")
                    
                    if add_elements:
                        # "EKLE" yazısı bulundu, aktif mi kontrol et
                        for elem in add_elements:
                            try:
                                if elem.is_displayed() and elem.text.strip():
                                    disabled = elem.get_attribute("disabled")
                                    elem_text = elem.text.upper()
                                    if (disabled is None or disabled == "false") and ("EKLE" in elem_text or "ADD" in elem_text):
                                        stock_available = True
                                        logging.info("Stokta var tespit edildi: 'EKLE' butonu aktif")
                                        break
                            except:
                                continue
                    
                    # Eğer hala None ise, sayfa içeriğinde "EKLE" var mı ve "TÜKENDİ" yok mu kontrol et
                    if stock_available is None:
                        has_ekle = "EKLE" in page_text.upper() or "EKLE" in page_source.upper()
                        has_tukendi = "TÜKENDİ" in page_text.upper() or "TÜKENDI" in page_text.upper() or "TUKENDI" in page_text.upper()
                        
                        if has_ekle and not has_tukendi:
                            stock_available = True
                            logging.info("Stokta var tespit edildi: 'EKLE' metni bulundu ve 'TÜKENDİ' yok")
                        elif has_tukendi:
                            stock_available = False
                            logging.info("Stokta yok tespit edildi: 'TÜKENDİ' metni bulundu")
                except Exception as e:
                    logging.warning(f"'EKLE' kontrolü sırasında hata: {e}")
            
            # ÖNCELİK 3: Sepete ekle butonu kontrolü (genel yedek yöntem)
            if stock_available is None:
                try:
                    add_to_cart_selectors = [
                        "button[data-qa-action='add-to-cart']",
                        "button.product-detail-info__actions-add-to-cart-button",
                        "button.product-detail-actions__add-to-cart",
                        "button[aria-label*='Sepete ekle']",
                        "button[aria-label*='Add to cart']",
                        "button[type='submit']"
                    ]
                    
                    for selector in add_to_cart_selectors:
                        try:
                            add_to_cart_buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                            for button in add_to_cart_buttons:
                                if button.is_displayed():
                                    disabled = button.get_attribute("disabled")
                                    if disabled is None or disabled == "false":
                                        button_text = button.text.upper()
                                        if "EKLE" in button_text or "ADD" in button_text or "SEPETE" in button_text:
                                            stock_available = True
                                            logging.info(f"Stokta var tespit edildi: Aktif buton bulundu - {button_text}")
                                            break
                            if stock_available is not None:
                                break
                        except:
                            continue
                except Exception as e:
                    logging.warning(f"Sepete ekle butonu kontrolü sırasında hata: {e}")
            
            # Eğer hala belirlenemediyse varsayılan olarak False
            if stock_available is None:
                stock_available = False
                logging.warning("Stok durumu belirlenemedi, varsayılan olarak 'stokta yok' kabul edildi")
            
            return {
                'available': stock_available,
                'product_name': product_name,
                'url': current_url
            }
            
        except Exception as e:
            logging.error(f"Stok kontrolü sırasında hata: {e}")
            return {
                'available': False,
                'product_name': 'Ürün',
                'url': current_url
            }
            
    except Exception as e:
        logging.error(f"Sayfa yükleme hatası: {e}")
        return {
            'available': False,
            'product_name': 'Ürün',
            'url': url_or_code if url_or_code.startswith('http') else ''
        }

def send_email(subject, body):
    """Email gönder - zara_stock_bot.py'deki send_email metodu"""
    try:
        app_password = APP_PASSWORD.replace(" ", "")
        
        msg = MIMEMultipart()
        msg['From'] = EMAIL
        msg['To'] = EMAIL
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        logging.info(f"Email gönderiliyor: {subject}")
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        logging.info("SMTP sunucusuna bağlandı, giriş yapılıyor...")
        server.login(EMAIL, app_password)
        logging.info("Giriş başarılı, email gönderiliyor...")
        server.send_message(msg)
        server.quit()
        
        logging.info(f"✅ Email başarıyla gönderildi: {subject}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        logging.error(f"❌ Email gönderilemedi - Kimlik doğrulama hatası: {e}")
        return False
    except Exception as e:
        logging.error(f"❌ Email gönderilemedi: {e}")
        return False

def heartbeat_loop():
    """Heartbeat döngüsü - Render.com uyku modunu engellemek için her 5 dakikada bir ping"""
    global heartbeat_running
    
    # Render.com URL'ini otomatik algıla
    render_url = os.environ.get('RENDER_EXTERNAL_URL') or os.environ.get('SERVICE_URL')
    
    if not render_url:
        # Eğer Render.com'da değilse heartbeat'e gerek yok
        logging.info("Heartbeat devre dışı (yerel ortam)")
        return
    
    logging.info(f"Heartbeat başlatıldı: {render_url}")
    
    while heartbeat_running:
        try:
            requests.get(render_url, timeout=5)
            logging.debug(f"Heartbeat ping: {render_url}")
        except Exception as e:
            logging.warning(f"Heartbeat hatası: {e}")
        
        # 5 dakika bekle (Render.com 15 dakika uyuyor, güvenli)
        for _ in range(30):  # 30 * 10 saniye = 5 dakika
            if not heartbeat_running:
                break
            time.sleep(10)
    
    logging.info("Heartbeat durduruldu")

def bot_loop():
    """Bot döngüsü - her 10 dakikada bir kontrol eder"""
    global bot_running, tracking_list, tracked_items
    
    logging.info("Bot döngüsü başlatıldı")
    
    # İlk çalıştırmada test emaili gönder
    try:
        send_email(
            "✅ Zara Stok Botu Başlatıldı",
            f"Zara Stok Takip Botu başarıyla başlatıldı.\n\n"
            f"Email: {EMAIL}\n"
            f"Takip edilen ürün sayısı: {len(tracking_list)}\n"
            f"Kontrol aralığı: 10 dakika\n"
            f"Başlangıç zamanı: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            f"Bot çalışıyor ve stok durumunu takip ediyor."
        )
    except Exception as e:
        logging.error(f"Test emaili gönderilemedi: {e}")
    
    while bot_running:
        try:
            # Tüm takip edilen ürünleri kontrol et
            if tracking_list:
                logging.info(f"Stok kontrolü başlatılıyor... ({len(tracking_list)} ürün)")
                email_body_parts = []
                changes_detected = False
                
                for item_url in tracking_list:
                    try:
                        result = check_stock_logic(item_url)
                        
                        # Önceki durumu kontrol et
                        previous_status = tracked_items.get(item_url, None)
                        current_status = result['available']
                        
                        # Durum değiştiyse veya ilk kontrol ise
                        if previous_status is None or previous_status != current_status:
                            changes_detected = True
                            status_change = ""
                            if previous_status is not None:
                                status_change = f" (Durum değişti: {'Stokta yoktu' if previous_status else 'Stokta vardı'} → {'Stokta var' if current_status else 'Stokta yok'})"
                            
                            status_text = "✅ STOKTA VAR" if current_status else "❌ STOKTA YOK"
                            email_body_parts.append(f"{status_text}: {result['product_name']}{status_change}")
                            email_body_parts.append(f"Link: {result['url']}\n")
                            
                            logging.info(f"{status_text}: {result['product_name']}")
                        
                        # Mevcut durumu kaydet
                        tracked_items[item_url] = current_status
                        time.sleep(2)
                        
                    except Exception as e:
                        logging.error(f"Stok kontrolü hatası ({item_url}): {e}")
                
                # Değişiklik varsa email gönder
                if changes_detected:
                    subject = f"🔔 Zara Stok Durumu Güncellendi - {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                    body = "\n".join(email_body_parts)
                    body += f"\n\nKontrol zamanı: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                    send_email(subject, body)
                else:
                    logging.info("Stok durumunda değişiklik yok.")
            
            # 10 dakika bekle
            for _ in range(60):  # 60 * 10 saniye = 10 dakika
                if not bot_running:
                    break
                time.sleep(10)
                
        except Exception as e:
            logging.error(f"Bot döngüsü hatası: {e}")
            time.sleep(60)  # Hata durumunda 1 dakika bekle
    
    logging.info("Bot döngüsü durduruldu")

# API Endpoints
@app.route('/')
def index():
    """Web arayüzü - PWA"""
    html = '''<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Zara Stok Takip</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 {
            text-align: center;
            color: #333;
            margin-bottom: 30px;
            font-size: 28px;
        }
        .section {
            margin-bottom: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
        }
        .section h2 {
            color: #667eea;
            margin-bottom: 15px;
            font-size: 20px;
        }
        input[type="text"] {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
            margin-bottom: 10px;
        }
        button {
            width: 100%;
            padding: 14px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            margin-top: 10px;
            transition: background 0.3s;
        }
        button:hover {
            background: #5568d3;
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .status {
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            font-weight: bold;
        }
        .status.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .status.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .status.info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        .list-item {
            padding: 15px;
            background: white;
            border-radius: 8px;
            margin-bottom: 10px;
            border-left: 4px solid #667eea;
        }
        .list-item h3 {
            color: #333;
            margin-bottom: 5px;
        }
        .list-item p {
            color: #666;
            font-size: 14px;
        }
        .bot-status {
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            font-weight: bold;
            margin-bottom: 20px;
        }
        .bot-status.running {
            background: #d4edda;
            color: #155724;
        }
        .bot-status.stopped {
            background: #f8d7da;
            color: #721c24;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🛍️ Zara Stok Takip</h1>
        
        <div id="botStatus" class="bot-status stopped">Bot Durmuş</div>
        
        <div class="section">
            <h2>1. Stok Kontrol Et</h2>
            <input type="text" id="checkUrl" placeholder="Ürün URL'i veya stok kodu">
            <button onclick="checkStock()">Stok Kontrol Et</button>
            <div id="checkResult"></div>
        </div>
        
        <div class="section">
            <h2>2. Otomatik Takip</h2>
            <input type="text" id="trackUrl" placeholder="Takip edilecek ürün URL'i">
            <button onclick="addTracking()">Takip Listesine Ekle</button>
        </div>
        
        <div class="section">
            <h2>3. Bot Yönetimi</h2>
            <button id="startBtn" onclick="startBot()">Botu Başlat</button>
            <button id="stopBtn" onclick="stopBot()" disabled>Botu Durdur</button>
        </div>
        
        <div class="section">
            <h2>4. Takip Listesi</h2>
            <button onclick="loadTrackingList()">Listeyi Yenile</button>
            <div id="trackingList"></div>
        </div>
    </div>

    <script>
        function checkStock() {
            const url = document.getElementById('checkUrl').value.trim();
            if (!url) {
                showResult('checkResult', 'Lütfen URL veya stok kodu girin', 'error');
                return;
            }
            
            showResult('checkResult', 'Kontrol ediliyor...', 'info');
            
            fetch('/api/check', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url: url})
            })
            .then(r => {
                if (!r.ok) {
                    throw new Error(`HTTP ${r.status}: ${r.statusText}`);
                }
                const contentType = r.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    return r.text().then(text => {
                        throw new Error('JSON bekleniyordu ama HTML geldi. Sunucu hatası olabilir.');
                    });
                }
                return r.json();
            })
            .then(data => {
                if (data.success) {
                    const status = data.available ? '✅ STOKTA VAR' : '❌ STOKTA YOK';
                    showResult('checkResult', `${status}<br>${data.product_name}<br><a href="${data.url}" target="_blank">Ürün Linki</a>`, data.available ? 'success' : 'error');
                } else {
                    showResult('checkResult', data.message || 'Hata oluştu', 'error');
                }
            })
            .catch(e => {
                showResult('checkResult', 'Bağlantı hatası: ' + e.message, 'error');
                console.error('API Hatası:', e);
            });
        }
        
        function addTracking() {
            const url = document.getElementById('trackUrl').value.trim();
            if (!url) {
                alert('Lütfen URL girin');
                return;
            }
            
            fetch('/api/track', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url: url})
            })
            .then(r => {
                if (!r.ok) {
                    throw new Error(`HTTP ${r.status}: ${r.statusText}`);
                }
                const contentType = r.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    return r.text().then(text => {
                        throw new Error('JSON bekleniyordu ama HTML geldi. Sunucu hatası olabilir.');
                    });
                }
                return r.json();
            })
            .then(data => {
                if (data.success) {
                    alert('Takip listesine eklendi!');
                    document.getElementById('trackUrl').value = '';
                    loadTrackingList();
                } else {
                    alert(data.message || 'Hata oluştu');
                }
            })
            .catch(e => {
                alert('Bağlantı hatası: ' + e.message);
                console.error('API Hatası:', e);
            });
        }
        
        function startBot() {
            fetch('/api/bot/start', {method: 'POST'})
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.statusText}`);
                const contentType = r.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    return r.text().then(text => {
                        throw new Error('JSON bekleniyordu ama HTML geldi.');
                    });
                }
                return r.json();
            })
            .then(data => {
                if (data.success) {
                    updateBotStatus(true);
                    alert('Bot başlatıldı!');
                } else {
                    alert(data.message || 'Hata oluştu');
                }
            })
            .catch(e => {
                alert('Bağlantı hatası: ' + e.message);
                console.error('API Hatası:', e);
            });
        }
        
        function stopBot() {
            fetch('/api/bot/stop', {method: 'POST'})
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.statusText}`);
                const contentType = r.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    return r.text().then(text => {
                        throw new Error('JSON bekleniyordu ama HTML geldi.');
                    });
                }
                return r.json();
            })
            .then(data => {
                if (data.success) {
                    updateBotStatus(false);
                    alert('Bot durduruldu!');
                } else {
                    alert(data.message || 'Hata oluştu');
                }
            })
            .catch(e => {
                alert('Bağlantı hatası: ' + e.message);
                console.error('API Hatası:', e);
            });
        }
        
        function loadTrackingList() {
            fetch('/api/tracking/list')
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.statusText}`);
                const contentType = r.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    return r.text().then(text => {
                        throw new Error('JSON bekleniyordu ama HTML geldi.');
                    });
                }
                return r.json();
            })
            .then(data => {
                const listDiv = document.getElementById('trackingList');
                if (data.items && data.items.length > 0) {
                    listDiv.innerHTML = data.items.map((item, idx) => `
                        <div class="list-item">
                            <h3>${item.product_name || 'Ürün ' + (idx + 1)}</h3>
                            <p>${item.available ? '✅ STOKTA VAR' : '❌ STOKTA YOK'}</p>
                            <p><a href="${item.url}" target="_blank">Link</a></p>
                        </div>
                    `).join('');
                } else {
                    listDiv.innerHTML = '<p>Takip listesi boş</p>';
                }
            })
            .catch(e => {
                document.getElementById('trackingList').innerHTML = '<p>Yüklenemedi: ' + e.message + '</p>';
                console.error('API Hatası:', e);
            });
        }
        
        function showResult(id, message, type) {
            const div = document.getElementById(id);
            div.innerHTML = `<div class="status ${type}">${message}</div>`;
        }
        
        function updateBotStatus(running) {
            const statusDiv = document.getElementById('botStatus');
            const startBtn = document.getElementById('startBtn');
            const stopBtn = document.getElementById('stopBtn');
            
            if (running) {
                statusDiv.className = 'bot-status running';
                statusDiv.textContent = '✅ Bot Çalışıyor';
                startBtn.disabled = true;
                stopBtn.disabled = false;
            } else {
                statusDiv.className = 'bot-status stopped';
                statusDiv.textContent = '❌ Bot Durmuş';
                startBtn.disabled = false;
                stopBtn.disabled = true;
            }
        }
        
        // Sayfa yüklendiğinde durumu kontrol et
        fetch('/api/bot/status')
        .then(r => {
            if (!r.ok) return null;
            const contentType = r.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                return null;
            }
            return r.json();
        })
        .then(data => {
            if (data && data.running) {
                updateBotStatus(true);
            }
            loadTrackingList();
        })
        .catch(e => {
            console.error('Bot durum kontrolü hatası:', e);
            loadTrackingList();
        });
    </script>
</body>
</html>'''
    return html

@app.route('/api/check', methods=['POST'])
def api_check():
    """Stok kontrolü"""
    try:
        # Content-Type kontrolü
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type application/json olmalı'}), 400
        
        data = request.json
        if data is None:
            return jsonify({'success': False, 'message': 'JSON verisi eksik'}), 400
        
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'success': False, 'message': 'URL gerekli'}), 400
        
        # check_stock_logic çağrısı - exception yakalama
        try:
            result = check_stock_logic(url)
            
            # Result dictionary kontrolü
            if not isinstance(result, dict):
                logging.error(f"check_stock_logic beklenmeyen tip döndürdü: {type(result)}")
                return jsonify({'success': False, 'message': 'Stok kontrolü beklenmeyen sonuç döndürdü'}), 500
            
            # Gerekli key'lerin varlığını kontrol et
            if 'available' not in result or 'product_name' not in result or 'url' not in result:
                logging.error(f"check_stock_logic eksik key'ler döndürdü: {result.keys()}")
                return jsonify({'success': False, 'message': 'Stok kontrolü eksik bilgi döndürdü'}), 500
            
            return jsonify({
                'success': True,
                'available': result['available'],
                'product_name': result['product_name'],
                'url': result['url']
            })
        except Exception as e:
            logging.error(f"check_stock_logic hatası: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False, 
                'message': f'Stok kontrolü sırasında hata: {str(e)}'
            }), 500
        
    except Exception as e:
        logging.error(f"API check genel hatası: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'message': f'Sunucu hatası: {str(e)}'
        }), 500

@app.route('/api/track', methods=['POST'])
def api_track():
    """Takip listesine ekle"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'success': False, 'message': 'URL gerekli'}), 400
        
        if url not in tracking_list:
            tracking_list.append(url)
            logging.info(f"Takip listesine eklendi: {url}")
        
        return jsonify({'success': True, 'message': 'Eklendi'})
    except Exception as e:
        logging.error(f"API track hatası: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/tracking/list', methods=['GET'])
def api_tracking_list():
    """Takip listesi"""
    try:
        items = []
        
        # Tracking list boşsa direkt boş liste döndür
        if not tracking_list:
            return jsonify({'success': True, 'items': []})
        
        # Her URL için stok kontrolü yap
        for url in tracking_list:
            try:
                result = check_stock_logic(url)
                
                # Result kontrolü
                if not isinstance(result, dict):
                    logging.warning(f"check_stock_logic beklenmeyen tip döndürdü: {type(result)}")
                    items.append({
                        'url': url,
                        'available': False,
                        'product_name': 'Hata: Beklenmeyen sonuç'
                    })
                    continue
                
                # Key kontrolü
                items.append({
                    'url': url,
                    'available': result.get('available', False),
                    'product_name': result.get('product_name', 'Ürün')
                })
            except Exception as e:
                logging.error(f"Tracking list item hatası ({url}): {e}", exc_info=True)
                # Hata olsa bile devam et, diğerlerini kontrol et
                items.append({
                    'url': url,
                    'available': False,
                    'product_name': f'Hata: {str(e)[:50]}'
                })
        
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        logging.error(f"API tracking list genel hatası: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'message': f'Takip listesi yüklenemedi: {str(e)}'
        }), 500

@app.route('/api/bot/start', methods=['POST'])
def api_bot_start():
    """Botu başlat"""
    global bot_running, bot_thread, heartbeat_running, heartbeat_thread
    
    try:
        if bot_running:
            return jsonify({'success': False, 'message': 'Bot zaten çalışıyor'})
        
        # Heartbeat'i başlat (Render.com için)
        if not heartbeat_running:
            heartbeat_running = True
            heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
            heartbeat_thread.start()
            logging.info("Heartbeat başlatıldı")
        
        # Bot'u başlat
        bot_running = True
        bot_thread = threading.Thread(target=bot_loop, daemon=True)
        bot_thread.start()
        
        logging.info("Bot başlatıldı")
        return jsonify({'success': True, 'message': 'Bot başlatıldı'})
    except Exception as e:
        logging.error(f"Bot başlatma hatası: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/bot/stop', methods=['POST'])
def api_bot_stop():
    """Botu durdur"""
    global bot_running, heartbeat_running
    
    try:
        bot_running = False
        # Heartbeat'i de durdur (isteğe bağlı - isterseniz sürekli çalışsın)
        # heartbeat_running = False
        logging.info("Bot durduruldu")
        return jsonify({'success': True, 'message': 'Bot durduruldu'})
    except Exception as e:
        logging.error(f"Bot durdurma hatası: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/bot/status', methods=['GET'])
def api_bot_status():
    """Bot durumu"""
    return jsonify({'success': True, 'running': bot_running})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    # Yerel çalıştırma için heartbeat başlat (hata olursa devam et)
    try:
        init_heartbeat()
    except Exception as e:
        logging.warning(f"Heartbeat başlatılamadı (normal olabilir): {e}")
    
    app.run(host='0.0.0.0', port=port, debug=False)

