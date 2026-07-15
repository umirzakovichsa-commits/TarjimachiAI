# 3 Tilda Tarjimon va Ovozli Tarjima Telegram Bot

Ushbu bot Telegram orqali yuborilgan matnli va ovozli xabarlarni o'zbek, ingliz va rus tillari o'rtasida tarjima qilib beradi.

## Xususiyatlari
- **Matn tarjimasi:** Bepul Google Translate API integratsiyasi.
- **Ovozli xabarlar tarjimasi (STT):** AssemblyAI yoki OpenAI Whisper yordamida ovozni eshitib, matnga o'girish va tarjima qilish.
- **Qulay interfeys:** Tarjima yo'nalishini tanlash uchun interaktiv inline tugmalar menyusi.
- **Moslashuvchanlik:** Mahalliy kompyuterda (Polling) va serverda (Webhook) muammosiz ishlash.

---

## Mahalliy O'rnatish va Ishga Tushirish

1. **Paketlarni o'rnatish:**
   ```bash
   npm.cmd install
   ```

2. **`.env` faylini sozlash:**
   `.env` faylini ochib, o'z kalitlaringizni kiriting:
   ```env
   BOT_TOKEN=sizning_telegram_bot_tokeningiz
   ASSEMBLYAI_API_KEY=sizning_assemblyai_kalitingiz
   ```

3. **Ishga tushirish:**
   ```bash
   npm.cmd run start
   ```

---

## 24/7 Render.com Hostingiga Joylashtirish Yo'riqnomasi

Botni kompyuter o'chirilganda ham doimiy (24/7) ishlashi uchun quyidagi amallarni bajaring:

### 1. Kodlarni GitHub'ga yuklash
Loyiha papkasida terminalni ochib, kodlarni GitHub repozitoriyangizga yuklang:
```bash
git init
git add .
git commit -m "initial commit"
# O'z GitHub repozitoriyangizga ulang va yuklang:
git remote add origin https://github.com/USERNAME/REPO_NAME.git
git branch -M main
git push -u origin main
```

### 2. Render.com saytida sozlash
1. [Render.com](https://render.com/) saytiga kiring va GitHub profilingiz orqali kiring (Sign in with GitHub).
2. **"New +"** -> **"Web Service"** tugmasini bosing.
3. Yuqorida GitHub'ga yuklagan repozitoriyangizni tanlang (**Connect**).
4. Quyidagi parametrlarni kiriting:
   - **Name:** `telegram-translator-bot` (yoki istalgan nom)
   - **Runtime:** `Node`
   - **Build Command:** `npm install`
   - **Start Command:** `node index.js`
5. **Environment Variables** (Muhit o'zgaruvchilari) bo'limiga kiring (**Advanced** -> **Add Environment Variable**) va quyidagilarni qo'shing:
   - `BOT_TOKEN` = *Sizning Telegram Bot Tokeningiz*
   - `ASSEMBLYAI_API_KEY` = *Sizning AssemblyAI Kalitingiz*
   - `WEBHOOK_DOMAIN` = *Render sizga bergan sayt havolasi (masalan, `https://telegram-translator-bot-xyz.onrender.com`)*
6. **"Deploy Web Service"** tugmasini bosing va o'rnatilishini kuting.

Render botni muvaffaqiyatli ishga tushirgandan so'ng, Telegram botingiz kompyuteringiz o'chirilgan holatda ham 24/7 davomida ishlaydi!
