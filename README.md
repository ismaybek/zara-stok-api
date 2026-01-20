# 🛍️ Zara Stok Takip Botu

Zara ürünlerinin stok durumunu otomatik olarak takip eden ve email bildirimi gönderen API servisi.

## ✨ Özellikler

- ✅ Otomatik stok kontrolü (10 dakikada bir)
- ✅ Email bildirimleri (stok durumu değiştiğinde)
- ✅ Mobil uyumlu web arayüzü (PWA)
- ✅ RESTful API
- ✅ Cloud servis desteği (Render.com, Railway.app)
- ✅ Bilgisayar veya telefon gerektirmez

## 🚀 Hızlı Başlangıç

### 1. Deploy Edin (Render.com)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com)

1. Render.com'a GitHub hesabınızla giriş yapın
2. "New Web Service" seçin
3. Bu repository'yi bağlayın
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `gunicorn zara_api:app`
6. Deploy edin!

### 2. API'yi Kullanın

Deploy sonrası aldığınız URL'i kullanın:
```
https://your-app.onrender.com
```

**API Endpoints:**
- `GET /` - Web arayüzü
- `POST /api/check` - Stok kontrolü
- `POST /api/track` - Takip listesine ekle
- `GET /api/tracking/list` - Takip listesi
- `POST /api/bot/start` - Botu başlat
- `POST /api/bot/stop` - Botu durdur

### 3. Mobil Uygulama

URL'i mobil tarayıcıda açın ve "Ana Ekrana Ekle" yapın.

## 📋 Gereksinimler

- Python 3.11+
- Chrome/Chromium (Selenium için)

## 🔧 Yerel Kurulum

```bash
# Paketleri yükle
pip install -r requirements.txt

# API'yi başlat
python zara_api.py
```

## 📱 Mobil Kullanım

1. API'yi cloud servise deploy edin
2. Mobil tarayıcıda URL'i açın
3. "Ana Ekrana Ekle" yapın
4. Botu başlatın ve ürünleri ekleyin
5. Telefonu kapatın - bot arka planda çalışır!

## 📧 Email Ayarları

`zara_api.py` dosyasında email ayarlarını güncelleyin:

```python
EMAIL = "your-email@gmail.com"
APP_PASSWORD = "your-app-password"
```

Gmail için uygulama şifresi oluşturun: https://myaccount.google.com/apppasswords

## 🤖 Bot Nasıl Çalışır?

- Bot cloud serviste 24/7 çalışır
- Her 10 dakikada bir stok kontrolü yapar
- Stok durumu değiştiğinde email gönderir
- Telefon veya bilgisayar açık olması gerekmez

## 📄 Lisans

MIT License

## 📞 Destek

Sorunlar için GitHub Issues kullanın.
