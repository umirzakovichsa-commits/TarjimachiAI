require('dotenv').config();
const { Telegraf } = require('telegraf');

// Verify token
if (!process.env.BOT_TOKEN || process.env.BOT_TOKEN === 'YOUR_TELEGRAM_BOT_TOKEN') {
  console.error("Error: BOT_TOKEN is missing or not configured in .env file.");
  process.exit(1);
}

const bot = new Telegraf(process.env.BOT_TOKEN);

// In-memory storage for user translation directions
const userModes = new Map(); // Key: chatId, Value: modeKey

// Supported translation directions
const translationModes = {
  'auto_uz': { from: 'auto', to: 'uz', label: '🔄 Avto ➡️ 🇺🇿 O\'zbekcha' },
  'auto_en': { from: 'auto', to: 'en', label: '🔄 Avto ➡️ 🇬🇧 Inglizcha' },
  'auto_ru': { from: 'auto', to: 'ru', label: '🔄 Avto ➡️ 🇷🇺 Ruscha' },
  
  'uz_en': { from: 'uz', to: 'en', label: '🇺🇿 O\'zbekcha ➡️ 🇬🇧 Inglizcha' },
  'en_uz': { from: 'en', to: 'uz', label: '🇬🇧 Inglizcha ➡️ 🇺🇿 O\'zbekcha' },
  
  'uz_ru': { from: 'uz', to: 'ru', label: '🇺🇿 O\'zbekcha ➡️ 🇷🇺 Ruscha' },
  'ru_uz': { from: 'ru', to: 'uz', label: '🇷🇺 Ruscha ➡️ 🇺🇿 O\'zbekcha' },
  
  'en_ru': { from: 'en', to: 'ru', label: '🇬🇧 Inglizcha ➡️ 🇷🇺 Ruscha' },
  'ru_en': { from: 'ru', to: 'en', label: '🇷🇺 Ruscha ➡️ 🇬🇧 Inglizcha' },
};

const DEFAULT_MODE = 'auto_uz';

// Helper to get or set user mode
function getUserMode(chatId) {
  if (!userModes.has(chatId)) {
    userModes.set(chatId, DEFAULT_MODE);
  }
  return userModes.get(chatId);
}

// Helper to build keyboard markup
function getKeyboard(currentMode) {
  const buttons = Object.keys(translationModes).map(key => {
    const mode = translationModes[key];
    const isSelected = key === currentMode;
    return {
      text: `${isSelected ? '✅ ' : ''}${mode.label}`,
      callback_data: `set_mode:${key}`
    };
  });

  // Split into rows of 2 buttons
  const inline_keyboard = [];
  for (let i = 0; i < buttons.length; i += 2) {
    inline_keyboard.push(buttons.slice(i, i + 2));
  }

  return { inline_keyboard };
}

// Gemini Translation helper
async function translateWithGemini(text, from, to, apiKey) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      contents: [{
        parts: [
          { text: `Translate this text from language '${from}' to language '${to}'. Return ONLY the translated text. Do not add any explanations, markdown, introduction, or notes.\nText: ${text}` }
        ]
      }]
    })
  });
  if (!response.ok) throw new Error("Gemini translation error");
  const data = await response.json();
  if (data.candidates && data.candidates[0] && data.candidates[0].content && data.candidates[0].content.parts[0]) {
    return data.candidates[0].content.parts[0].text.trim();
  }
  return null;
}

// Free Translation API with Fallbacks
async function translateText(text, from, to) {
  const browserHeaders = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://translate.google.com/'
  };

  // Try 1: Chrome Extension Google Translate API (highly stable, bypasses IP blocks)
  try {
    const url = `https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=${from}&tl=${to}&q=${encodeURIComponent(text)}`;
    const response = await fetch(url, { headers: browserHeaders });
    if (response.ok) {
      const data = await response.json();
      if (Array.isArray(data) && data[0]) {
        if (Array.isArray(data[0])) {
          return data[0][0]; // For auto-detection: [["translatedText", "lang"]]
        }
        return data[0]; // For explicit language pairs: ["translatedText"]
      }
    }
  } catch (err) {
    console.warn("Chrome Translate failed, trying fallback...", err);
  }

  // Try 2: Standard Google Translate API
  try {
    const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=${from}&tl=${to}&dt=t&q=${encodeURIComponent(text)}`;
    const response = await fetch(url, { headers: browserHeaders });
    if (response.ok) {
      const data = await response.json();
      const translatedText = data[0].map(x => x[0]).join('');
      return translatedText;
    }
  } catch (err) {
    console.warn("Standard Google Translate failed, trying fallback...", err);
  }

  // Try 3: Gemini Translate (if valid key is provided)
  const hasGemini = !!process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY !== 'YOUR_GEMINI_API_KEY' && !process.env.GEMINI_API_KEY.startsWith('AQ.');
  if (hasGemini) {
    try {
      const geminiTranslation = await translateWithGemini(text, from, to, process.env.GEMINI_API_KEY);
      if (geminiTranslation) return geminiTranslation;
    } catch (err) {
      console.warn("Gemini Translate failed, trying fallback...", err);
    }
  }

  // Try 4: MyMemory API (Free)
  try {
    const langPair = `${from === 'auto' ? 'en' : from}|${to}`;
    const url = `https://api.mymemory.translated.net/get?q=${encodeURIComponent(text)}&langpair=${langPair}`;
    const response = await fetch(url, {
      headers: {
        'User-Agent': browserHeaders['User-Agent']
      }
    });
    if (response.ok) {
      const data = await response.json();
      if (data.responseData && data.responseData.translatedText) {
        return data.responseData.translatedText;
      }
    }
  } catch (err) {
    console.error("MyMemory Translate failed:", err);
  }

  throw new Error("Barcha tarjima provayderlarida xatolik yuz berdi. Iltimos keyinroq urinib ko'ring.");
}

// Gemini Speech-to-Text helper (uses Gemini 1.5 Flash)
async function transcribeWithGemini(audioUrl, apiKey) {
  const audioResponse = await fetch(audioUrl);
  const audioBuffer = await audioResponse.arrayBuffer();
  const base64Data = Buffer.from(audioBuffer).toString('base64');

  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      contents: [{
        parts: [
          { text: "Transcribe this audio. Return ONLY the transcribed text in its original language. Do not add any introduction, markdown, quotes, explanations, or notes. If the audio is empty or has no speech, return an empty string." },
          {
            inlineData: {
              mimeType: "audio/ogg",
              data: base64Data
            }
          }
        ]
      }]
    })
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Gemini STT error: ${response.status} - ${errText}`);
  }

  const result = await response.json();
  if (result.candidates && result.candidates[0] && result.candidates[0].content && result.candidates[0].content.parts[0]) {
    return result.candidates[0].content.parts[0].text;
  }
  return '';
}

// OpenAI Whisper Speech-to-Text helper
async function transcribeWithOpenAI(audioUrl, apiKey) {
  // Download the voice file from Telegram
  const audioResponse = await fetch(audioUrl);
  const audioBuffer = await audioResponse.arrayBuffer();

  const formData = new FormData();
  const blob = new Blob([audioBuffer], { type: 'audio/ogg' });
  formData.append('file', blob, 'voice.ogg');
  formData.append('model', 'whisper-1');

  const response = await fetch('https://api.openai.com/v1/audio/transcriptions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`
    },
    body: formData
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`OpenAI STT error: ${response.status} - ${errText}`);
  }

  const result = await response.json();
  return result.text;
}

// AssemblyAI Speech-to-Text helper
async function transcribeWithAssemblyAI(audioUrl, apiKey) {
  // Download the voice file from Telegram
  const audioResponse = await fetch(audioUrl);
  const audioBuffer = await audioResponse.arrayBuffer();

  // 1. Upload audio buffer
  const uploadResponse = await fetch('https://api.assemblyai.com/v2/upload', {
    method: 'POST',
    headers: {
      'authorization': apiKey,
      'content-type': 'application/octet-stream'
    },
    body: audioBuffer
  });

  if (!uploadResponse.ok) {
    const errText = await uploadResponse.text();
    throw new Error(`AssemblyAI upload error: ${errText}`);
  }

  const uploadResult = await uploadResponse.json();
  const uploadUrl = uploadResult.upload_url;

  // 2. Request transcription with auto language detection
  const transcriptResponse = await fetch('https://api.assemblyai.com/v2/transcript', {
    method: 'POST',
    headers: {
      'authorization': apiKey,
      'content-type': 'application/json'
    },
    body: JSON.stringify({
      audio_url: uploadUrl,
      language_detection: true
    })
  });

  if (!transcriptResponse.ok) {
    const errText = await transcriptResponse.text();
    throw new Error(`AssemblyAI transcript request error: ${errText}`);
  }

  const transcriptResult = await transcriptResponse.json();
  const transcriptId = transcriptResult.id;

  // 3. Poll status
  let status = 'queued';
  while (status === 'queued' || status === 'processing') {
    await new Promise(resolve => setTimeout(resolve, 1500));
    const pollResponse = await fetch(`https://api.assemblyai.com/v2/transcript/${transcriptId}`, {
      headers: { 'authorization': apiKey }
    });
    if (!pollResponse.ok) {
      throw new Error(`AssemblyAI status polling error`);
    }
    const pollResult = await pollResponse.json();
    status = pollResult.status;
    if (status === 'completed') {
      return pollResult.text;
    } else if (status === 'failed') {
      throw new Error(`AssemblyAI transcription failed: ${pollResult.error}`);
    }
  }
  return '';
}

// Start command
bot.start(async (ctx) => {
  const chatId = ctx.chat.id;
  const currentMode = getUserMode(chatId);
  const modeInfo = translationModes[currentMode];

  const welcomeText = 
    `👋 <b>Assalomu alaykum! Tarjimon botga xush kelibsiz!</b>\n\n` +
    `Ushbu bot matn va ovozli xabarlarni 3 tilda tarjima qiladi:\n` +
    `🇺🇿 <b>O'zbekcha</b>, 🇬🇧 <b>Inglizcha</b> va 🇷🇺 <b>Ruscha</b>.\n\n` +
    `Joriy tarjima rejimi: <b>${modeInfo.label}</b>\n\n` +
    `👇 Quyidagi menyudan tarjima yo'nalishini tanlang va menga matn yoki ovozli xabar yuboring:`;

  await ctx.replyWithHTML(welcomeText, {
    reply_markup: getKeyboard(currentMode)
  });
});

// Menu command
bot.command(['menu', 'settings'], async (ctx) => {
  const chatId = ctx.chat.id;
  const currentMode = getUserMode(chatId);
  
  await ctx.replyWithHTML("⚙️ <b>Tarjima tilini tanlang:</b>", {
    reply_markup: getKeyboard(currentMode)
  });
});

// Handle mode selection (Callback query)
bot.on('callback_query', async (ctx) => {
  try {
    const data = ctx.callbackQuery.data;
    if (data.startsWith('set_mode:')) {
      const modeKey = data.split(':')[1];
      if (translationModes[modeKey]) {
        const chatId = ctx.chat.id;
        userModes.set(chatId, modeKey);
        
        const modeInfo = translationModes[modeKey];
        
        // Acknowledge callback
        await ctx.answerCbQuery(`Tarjima rejimi o'rnatildi: ${modeInfo.label}`);
        
        // Update menu message keyboard
        await ctx.editMessageText(`⚙️ <b>Tarjima rejimi tanlandi:</b>\n👉 <b>${modeInfo.label}</b>\n\nEndi botga matn yoki ovoz yuborishingiz mumkin.`, {
          parse_mode: 'HTML',
          reply_markup: getKeyboard(modeKey)
        });
      }
    }
  } catch (error) {
    console.error("Callback query error:", error);
  }
});

// Handle text messages
bot.on('text', async (ctx) => {
  const text = ctx.message.text;
  if (text.startsWith('/')) return; // Ignore other command calls

  const chatId = ctx.chat.id;
  const currentMode = getUserMode(chatId);
  const mode = translationModes[currentMode];

  await ctx.sendChatAction('typing');

  try {
    const translation = await translateText(text, mode.from, mode.to);
    
    const responseText = 
      `📝 <b>Asl matn:</b>\n<i>"${text}"</i>\n\n` +
      `➡️ <b>Tarjima:</b>\n<b>${translation}</b>\n\n` +
      `🧭 <i>Rejim: ${mode.label}</i>`;

    await ctx.replyWithHTML(responseText, {
      reply_to_message_id: ctx.message.message_id
    });
  } catch (error) {
    console.error("Text translation error:", error);
    await ctx.reply(`❌ Tarjima qilishda xatolik yuz berdi: ${error.message}`);
  }
});

// Handle voice messages
bot.on('voice', async (ctx) => {
  const chatId = ctx.chat.id;
  const currentMode = getUserMode(chatId);
  const mode = translationModes[currentMode];

  const hasGemini = !!process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY !== 'YOUR_GEMINI_API_KEY';
  const hasOpenAI = !!process.env.OPENAI_API_KEY && process.env.OPENAI_API_KEY !== 'YOUR_OPENAI_API_KEY';
  const hasAssembly = !!process.env.ASSEMBLYAI_API_KEY && process.env.ASSEMBLYAI_API_KEY !== 'YOUR_ASSEMBLYAI_API_KEY';

  if (!hasGemini && !hasOpenAI && !hasAssembly) {
    return ctx.replyWithHTML(
      `🎙 <b>Ovozli xabar qabul qilindi!</b>\n\n` +
      `Lekin ovozli xabarlarni matnga o'girish uchun API kaliti sozlanmagan.\n` +
      `Uni ishlatish uchun bot boshqaruvchisi <code>.env</code> fayliga <code>GEMINI_API_KEY</code>, <code>OPENAI_API_KEY</code> yoki <code>ASSEMBLYAI_API_KEY</code> ni kiritishi kerak.\n\n` +
      `<i>Hozircha faqat matnli xabarlarni tarjima qila olaman.</i>`,
      { reply_to_message_id: ctx.message.message_id }
    );
  }

  await ctx.sendChatAction('typing');
  const statusMsg = await ctx.reply("🎙 Ovoz eshitilmoqda, iltimos kuting...");

  try {
    const fileId = ctx.message.voice.file_id;
    const fileLink = await ctx.telegram.getFileLink(fileId);

    let transcription = "";
    if (hasGemini) {
      transcription = await transcribeWithGemini(fileLink.href, process.env.GEMINI_API_KEY);
    } else if (hasOpenAI) {
      transcription = await transcribeWithOpenAI(fileLink.href, process.env.OPENAI_API_KEY);
    } else {
      transcription = await transcribeWithAssemblyAI(fileLink.href, process.env.ASSEMBLYAI_API_KEY);
    }

    if (!transcription || transcription.trim() === "") {
      await ctx.telegram.deleteMessage(chatId, statusMsg.message_id);
      return ctx.reply("Ovozdan hech qanday matn aniqlay olmadim.", {
        reply_to_message_id: ctx.message.message_id
      });
    }

    // Translate transcription
    const translation = await translateText(transcription, mode.from, mode.to);

    // Delete temporary status message
    await ctx.telegram.deleteMessage(chatId, statusMsg.message_id);

    const responseText = 
      `🗣 <b>Eshitilgan matn:</b>\n<i>"${transcription}"</i>\n\n` +
      `➡️ <b>Tarjima:</b>\n<b>${translation}</b>\n\n` +
      `🧭 <i>Rejim: ${mode.label}</i>`;

    await ctx.replyWithHTML(responseText, {
      reply_to_message_id: ctx.message.message_id
    });

  } catch (error) {
    console.error("Voice transcription/translation error:", error);
    try {
      await ctx.telegram.deleteMessage(chatId, statusMsg.message_id);
    } catch (_) {}
    await ctx.reply(`❌ Ovozli tarjimada xatolik yuz berdi: ${error.message}`, {
      reply_to_message_id: ctx.message.message_id
    });
  }
});

// Launch bot
const PORT = process.env.PORT || 3000;
const WEBHOOK_DOMAIN = process.env.WEBHOOK_DOMAIN;

if (WEBHOOK_DOMAIN) {
  // Webhook mode (for Render.com or other hostings)
  bot.launch({
    webhook: {
      domain: WEBHOOK_DOMAIN,
      port: PORT
    }
  }).then(() => {
    console.log(`🚀 Telegram Translator Bot is running on Webhook mode at ${WEBHOOK_DOMAIN}`);
  }).catch((error) => {
    console.error('Failed to start Telegram Bot in Webhook mode:', error);
  });
} else {
  // Polling mode (for local testing)
  bot.launch().then(() => {
    console.log('🚀 Telegram Translator Bot is successfully running on Polling mode (Local)!');
  }).catch((error) => {
    console.error('Failed to start Telegram Bot in Polling mode:', error);
  });
}

// Enable graceful stop
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
