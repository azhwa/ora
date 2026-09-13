# 🏹 Oracle Always Free ARM Hunter (Python + Telegram Monitor)

Bot ringan (~30 MB RAM) dan stabil untuk memburu VPS **Always Free Ampere A1 (ARM)** di Oracle Cloud. Dirancang khusus untuk berjalan 24/7 di VPS Linux (misal **Oracle Always Free x86 Micro**).

---

## 🌟 Fitur Utama
- **Ringan & Hemat Resource:** Konsumsi memori hanya ~30-40 MB RAM (Sangat aman untuk VPS Micro 1 GB).
- **Integrasi Telegram:**
  - 🚀 Notifikasi saat bot mulai berjalan.
  - ⏳ Heartbeat berkala (misal tiap 300 attempt) mengabarkan bot masih aktif.
  - 🎉 **Notifikasi Instan saat Berhasil:** Mengirimkan IP Publik, OCID, dan perintah SSH siap pakai!
  - 🛑 Notifikasi jika terjadi kesalahan fatal (kuota akun habis, kredensial salah).
- **Rotasi Availability Domain (AD):** Otomatis berpindah-pindah AD setiap percobaan.
- **Smart Retry:** Hanya mengulang saat kapasitas habis (*Out of capacity* / 429 / 5xx) dengan interval acak 30-60 detik.
- **Auto Background (systemd / PM2):** Bisa berjalan di latar belakang dan otomatis hidup kembali saat VPS reboot.
- **Anti-Lockout SSH Guaranteed:** Menjamin 100% Anda bisa langsung login SSH dari Laptop/PC maupun Telegram.

---

## 🔑 Jaminan 100% Langsung Bisa Login SSH (Anti-Lockout)

Tidak perlu khawatir berhasil buat instance tapi tidak bisa login! Sistem ini dirancang dengan 4 lapis perlindungan:

1. **Multi-Key Injection (Laptop + VPS):**
   Public key Laptop Anda (`DESKTOP-FULQ0UT`) sudah tersimpan di `config.json`. Saat bot berjalan di remote VPS, bot akan menanamkan **public key laptop Anda** DAN **key VPS** sekaligus ke `/home/ubuntu/.ssh/authorized_keys` instance baru.
2. **Langsung Login dari Laptop Tanpa Salin Key:**
   Begitu notifikasi Telegram masuk, Anda cukup buka PowerShell / Terminal di PC Anda dan jalankan:
   ```powershell
   ssh -i ~/.ssh/oraclehost_id_rsa ubuntu@<IP_PUBLIK_DARI_TELEGRAM>
   ```
   *Langsung masuk ke server baru Anda!*
3. **Kirim File Kunci Privat ke Chat Telegram (sendDocument):**
   Bot secara otomatis mengunggah file private key langsung ke chat Telegram Anda sebagai lampiran dokumen. Jika Anda sedang di luar dan ingin login dari HP (via Termius / JuiceSSH), tinggal unduh key langsung dari Telegram.
4. **Verifikasi Port 22 & Subnet Otomatis:**
   Sebelum berburu dimulai (*Preflight check*), bot memeriksa aturan Security List subnet Anda untuk memastikan Ingress Port 22 (SSH) benar-benar terbuka ke internet.
5. **Username Resmi Canonical Ubuntu:**
   Username login default untuk image Ubuntu di Oracle Cloud adalah **`ubuntu`** (bukan `root` atau `opc`).

---

## 📱 Langkah 1: Siapkan Bot Telegram (1 Menit)

1. **Buat Bot Telegram:**
   - Buka Telegram dan cari bot bernama **`@BotFather`**.
   - Kirim pesan: `/newbot`
   - Ikuti instruksi: beri nama bot dan username (misal `MyOracleHunterBot`).
   - `@BotFather` akan memberikan **HTTP API Token** (contoh: `123456789:ABCdefGhIJKlmNoPQRstuVWxYz`).
   - Simpan token ini.

2. **Dapatkan Chat ID Anda:**
   - Cari bot bernama **`@userinfobot`** di Telegram.
   - Klik Start / kirim sembarang pesan.
   - Bot akan membalas dengan **Id** Anda (contoh: `987654321`).
   - Simpan nomor ID ini.

3. **Buka Chat dengan Bot Anda:**
   - Buka bot yang baru Anda buat tadi di Telegram, lalu klik **Start** (agar bot punya izin mengirim pesan ke Anda).

---

## ⚙️ Langkah 2: Isi Token di `config.json`

Buka file `config.json` di folder ini, lalu isi bagian bawah:
```json
  "telegram_bot_token": "MASUKKAN_TOKEN_BOTFATHER_DI_SINI",
  "telegram_chat_id": "MASUKKAN_CHAT_ID_DI_SINI"
```

---

## 🚀 Langkah 3: Pindahkan & Jalankan di VPS Micro

### 1. File yang Dibutuhkan di VPS:
Salin file-file berikut ke VPS Anda:
1. Folder `OracleHunter-Py/` ini.
2. File kunci API OCI: `C:\Users\azama\.oci\oci_api_key.pem`
3. File kunci SSH: `C:\Users\azama\.ssh\oraclehost_id_rsa` dan `oraclehost_id_rsa.pub`

> **Tips Cepat Upload via SCP dari PowerShell di PC Anda:**
> ```powershell
> # Buat folder di VPS
> ssh ubuntu@<IP_VPS_MICRO> "mkdir -p ~/.oci ~/.ssh ~/OracleHunter-Py"
>
> # Upload file kunci
> scp C:\Users\azama\.oci\oci_api_key.pem ubuntu@<IP_VPS_MICRO>:~/.oci/
> scp C:\Users\azama\.ssh\oraclehost_id_rsa* ubuntu@<IP_VPS_MICRO>:~/.ssh/
>
> # Upload script bot
> scp -r D:\PROJECT\Script\Oracle-Hunter\OracleHunter-Py\* ubuntu@<IP_VPS_MICRO>:~/OracleHunter-Py/
> ```

### 2. Jalankan Script Setup di VPS:
Masuk ke VPS Anda via SSH:
```bash
ssh ubuntu@<IP_VPS_MICRO>
cd ~/OracleHunter-Py
chmod +x setup.sh
./setup.sh
```

---

## 🟢 Menjalankan Menggunakan PM2 (Paling Direkomendasikan)

Jika Anda menyukai **PM2**, project ini sudah dilengkapi file konfigurasi [**`ecosystem.config.js`**](file:///D:/PROJECT/Script/Oracle-Hunter/OracleHunter-Py/ecosystem.config.js).

### 1. Jalankan Bot via PM2:
```bash
cd ~/OracleHunter-Py
pm2 start ecosystem.config.js
```

### 2. Simpan agar Otomatis Hidup saat VPS Reboot:
```bash
pm2 save
pm2 startup
```
*(Copy dan jalankan baris perintah `sudo env PATH=...` yang disarankan oleh PM2 jika ada).*

### 3. Perintah PM2 yang Sering Digunakan:
* **Melihat Status Bot:**
  ```bash
  pm2 status
  ```
* **Melihat Log Streaming Secara Real-Time:**
  ```bash
  pm2 logs oracle-hunter
  ```
* **Restart Bot:**
  ```bash
  pm2 restart oracle-hunter
  ```
* **Menghentikan Bot:**
  ```bash
  pm2 stop oracle-hunter
  ```

---

## 🛠️ Alternatif: Menjalankan Menggunakan Systemd

Jika Anda lebih memilih service bawaan Linux (**systemd**):
* **Cek Status:** `sudo systemctl status oracle-hunter`
* **Melihat Log Live:** `tail -f ~/OracleHunter-Py/oracle_hunter.log`
* **Stop:** `sudo systemctl stop oracle-hunter`
* **Start:** `sudo systemctl start oracle-hunter`
* **Tes Notifikasi Telegram:**
  ```bash
  source .venv/bin/activate
  python3 hunter.py --test-telegram
  ```
