import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
LOCAL_API_URL = "http://127.0.0.1:8081/bot"
COOKIE_FILE = "www.youtube.com_cookies.txt"

MAX_CHUNK_SIZE = 2000 * 1024 * 1024  # 2GB

user_data = {}
progress_status = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("Access Denied.")
        return
    await update.message.reply_text("Bot ready hai! Video ya playlist ka link bhejo.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    url = update.message.text.strip()
    if not url.startswith("http"):
        return
    user_id = update.message.from_user.id
    user_data[user_id] = {"url": url}
    is_playlist = "playlist" in url or "list=" in url

    keyboard = [
        [InlineKeyboardButton("Video - 1080p", callback_data="q_1080")],
        [InlineKeyboardButton("Video - 720p", callback_data="q_720")],
        [InlineKeyboardButton("Video - 480p", callback_data="q_480")],
        [InlineKeyboardButton("Audio Only (MP3)", callback_data="q_audio")],
    ]
    text = "Playlist detect hui! Quality/format chunein:" if is_playlist else "Quality/format chunein:"
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    user_data[user_id]["is_playlist"] = is_playlist


def split_file(filepath, chunk_size=MAX_CHUNK_SIZE):
    parts = []
    base, ext = os.path.splitext(filepath)
    with open(filepath, 'rb') as f:
        idx = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            letter = chr(ord('a') + idx)
            part_path = f"{base}({letter}){ext}"
            with open(part_path, 'wb') as pf:
                pf.write(chunk)
            parts.append(part_path)
            idx += 1
    return parts


def make_progress_hook(key):
    def hook(d):
        if d['status'] == 'downloading':
            progress_status[key] = d.get('_percent_str', '0%').strip()
        elif d['status'] == 'finished':
            progress_status[key] = "100% (processing...)"
    return hook


def blocking_download(url, ydl_opts, choice):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if choice == "audio":
            filename = os.path.splitext(filename)[0] + ".mp3"
    return info, filename


async def send_file_and_cleanup(context, chat_id, filepath, caption):
    file_size = os.path.getsize(filepath)
    is_audio = filepath.endswith(".mp3")

    if file_size <= MAX_CHUNK_SIZE:
        try:
            with open(filepath, 'rb') as f:
                if is_audio:
                    await context.bot.send_audio(chat_id=chat_id, audio=f, caption=caption, read_timeout=2000, write_timeout=2000)
                else:
                    await context.bot.send_video(chat_id=chat_id, video=f, caption=caption, supports_streaming=True, read_timeout=2000, write_timeout=2000)
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id, text=f"{caption} bhejne mein error: {e}")
        finally:
            os.remove(filepath)
    else:
        await context.bot.send_message(chat_id=chat_id, text=f"{caption} 2GB se zyada hai, parts mein bhej raha hoon...")
        parts = split_file(filepath)
        os.remove(filepath)
        for i, part in enumerate(parts):
            letter = chr(ord('a') + i)
            part_caption = f"{caption} ({letter})"
            try:
                with open(part, 'rb') as pf:
                    await context.bot.send_document(chat_id=chat_id, document=pf, caption=part_caption, read_timeout=2000, write_timeout=2000)
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f"{part_caption} bhejne mein error: {e}")
            finally:
                os.remove(part)


async def process_one_video(context, chat_id, url, idx, format_opts, choice, base_ydl_opts, output_template, title_prefix):
    key = f"{chat_id}_{idx}"
    progress_status[key] = "0%"

    btn = InlineKeyboardMarkup([[InlineKeyboardButton("Progress dekhein", callback_data=f"prog_{key}")]])
    status_msg = await context.bot.send_message(chat_id=chat_id, text=f"{title_prefix} downloading...", reply_markup=btn)

    ydl_opts = {**base_ydl_opts, **format_opts, "outtmpl": output_template, "noplaylist": True,
                "progress_hooks": [make_progress_hook(key)]}

    loop = asyncio.get_event_loop()
    try:
        info, filename = await loop.run_in_executor(None, blocking_download, url, ydl_opts, choice)
        title = info.get("title", title_prefix)
        caption = f"{title_prefix}: {title}"

        await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"{title_prefix} download complete! Bhej raha hoon...")
        await send_file_and_cleanup(context, chat_id, filename, caption)
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
    except Exception as e:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"{title_prefix} mein error: {e}")
    finally:
        progress_status.pop(key, None)


async def progress_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    key = query.data.replace("prog_", "")
    percent = progress_status.get(key, "Shuru ho raha hai...")
    await query.answer(text=f"Download progress: {percent}", show_alert=True)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data.startswith("prog_"):
        await progress_button_handler(update, context)
        return

    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID or user_id not in user_data:
        return

    choice = query.data.replace("q_", "")
    url = user_data[user_id]["url"]
    is_playlist = user_data[user_id]["is_playlist"]
    chat_id = query.message.chat_id

    os.makedirs("downloads", exist_ok=True)
    base_ydl_opts = {"cookiefile": COOKIE_FILE, "quiet": True, "no_warnings": True}

    if choice == "audio":
        format_opts = {
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        }
    else:
        height = choice
        format_opts = {"format": f"best[height<={height}]/best"}

    await query.edit_message_text(f"Shuru kar raha hoon ({choice})...")

    if not is_playlist:
        output_template = "downloads/video1.%(ext)s"
        await process_one_video(context, chat_id, url, 1, format_opts, choice, base_ydl_opts, output_template, "Video 1")
        await context.bot.send_message(chat_id=chat_id, text="Ho gaya!")
        return

    try:
        with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "cookiefile": COOKIE_FILE}) as ydl:
            playlist_info = ydl.extract_info(url, download=False)
        entries = playlist_info.get("entries", [])
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"Playlist read karne mein error: {e}")
        return

    total = len(entries)
    await context.bot.send_message(chat_id=chat_id, text=f"{total} videos mile. Ek-ek karke shuru kar raha hoon...")

    for idx, entry in enumerate(entries, start=1):
        video_url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry.get('id')}"
        output_template = f"downloads/video{idx}.%(ext)s"
        await process_one_video(context, chat_id, video_url, idx, format_opts, choice, base_ydl_opts, output_template, f"Video {idx}")

    await context.bot.send_message(chat_id=chat_id, text="Playlist ki saari videos bhej di gayi!")


def main():
    application = Application.builder().token(BOT_TOKEN).base_url(LOCAL_API_URL).base_file_url(LOCAL_API_URL).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.run_polling()

if __name__ == '__main__':
    main()
