import os
import re
import logging
import requests
import telebot
from time import time
from flask import Flask, jsonify
from threading import Thread
import pymongo

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# DB Connection
try:
    mongo_client = pymongo.MongoClient(os.getenv('MONGO_URI'))
    db = mongo_client['powerful_web_scraping_tool_bot']
    users_collection = db['users']
    banned_users_collection = db['banned_users']
    logger.info('DB Connected Successfully')
except Exception as e:
    logger.error(f'DB Connection Failed: {e}')
    raise

# Bot Connection
try:
    bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
    bot_info = bot.get_me()
    logger.info(f"@{bot_info.username} Connected")
except Exception as e:
    logger.error(f'Bot Connection Failed: {e}')
    raise

# Flask App
app = Flask(__name__)

# Ensure Videos directory exists
os.makedirs('Videos', exist_ok=True)

# Functions
def is_member(user_id):
    """Check if user is a member of the specified channel."""
    try:
        member_status = bot.get_chat_member('-1001911851456', user_id)
        return member_status.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.warning(f"Membership check failed for user {user_id}: {e}")
        return False

def format_progress_bar(filename, percentage, done, total_size, status, speed, user_mention, user_id):
    """Format download progress bar."""
    bar_length = 10
    filled_length = int(bar_length * percentage / 100)
    bar = '⬤' * filled_length + '⊙' * (bar_length - filled_length)

    def format_size(size):
        """Convert bytes to human-readable format."""
        size = int(size)
        if size < 1024:
            return f"{size} B"
        elif size < 1024 ** 2:
            return f"{size / 1024:.2f} KB"
        elif size < 1024 ** 3:
            return f"{size / 1024 ** 2:.2f} MB"
        else:
            return f"{size / 1024 ** 3:.2f} GB"

    return (
        f"┏ 𝐅𝐢𝐥𝐞𝐍𝐚𝐦𝐞: <b>{filename}</b>\n"
        f"┠ [{bar}] {percentage:.2f}%\n"
        f"┠ 𝐏𝐫𝐨𝐜𝐞𝐬𝐬𝐞𝐝: {format_size(done)} ᴏғ {format_size(total_size)}\n"
        f"┠ 𝐒𝐭𝐚𝐭𝐮𝐬: <b>{status}</b>\n"
        f"┠ 𝐒𝐩𝐞𝐞𝐝: <b>{format_size(speed)}/s</b>\n"
        f"┖ 𝐔𝐬𝐞𝐫: {user_mention} | ɪᴅ: <code>{user_id}</code>"
    )

def download_video(url, chat_id, message_id, user_mention, user_id):
    """Download video from TeraBox link with detailed progress tracking."""
    try:
        # First request to get download link
        response = requests.get(
            f'https://terabox.udayscriptsx.workers.dev/data?url={url}', 
            timeout=15
        )
        
        # Validate API response
        if response.status_code != 200:
            raise Exception(f'API request failed with status code {response.status_code}')
        
        try:
            data = response.json()
        except ValueError:
            raise Exception('Invalid JSON response from API')

        # Validate response data structure
        if not data or 'response' not in data or len(data['response']) == 0:
            raise Exception('No valid download links found')

        resolutions = data['response'][0]['resolutions']
        fast_download_link = resolutions['Fast Download']
        
        # Sanitize filename
        video_title = re.sub(r'[<>:"/\\|?*]+', '', data['response'][0]['title'])
        video_path = os.path.join('Videos', f"{video_title}.mp4")

        # Download video with progress tracking
        with open(video_path, 'wb') as video_file:
            video_response = requests.get(fast_download_link, stream=True, timeout=30)

            # Validate video download response
            if video_response.status_code != 200:
                raise Exception(f'Video download failed with status code {video_response.status_code}')

            total_length = video_response.headers.get('content-length')
            if total_length is None:
                video_file.write(video_response.content)
                total_length = len(video_response.content)
            else:
                total_length = int(total_length)
                downloaded_length = 0
                start_time = time()
                last_percentage_update = 0

                for chunk in video_response.iter_content(chunk_size=4096):
                    downloaded_length += len(chunk)
                    video_file.write(chunk)
                    
                    elapsed_time = time() - start_time
                    percentage = 100 * downloaded_length / total_length
                    speed = downloaded_length / elapsed_time if elapsed_time > 0 else 0

                    # Update progress every 7%
                    if percentage - last_percentage_update >= 7:
                        try:
                            progress = format_progress_bar(
                                video_title,
                                percentage,
                                downloaded_length,
                                total_length,
                                'Downloading',
                                speed,
                                user_mention,
                                user_id
                            )
                            bot.edit_message_text(progress, chat_id, message_id, parse_mode='HTML')
                            last_percentage_update = percentage
                        except Exception as progress_error:
                            logger.warning(f"Progress update failed: {progress_error}")

        logger.info(f"Successfully downloaded video: {video_title}")
        return video_path, video_title, total_length

    except requests.exceptions.RequestException as network_error:
        logger.error(f"Network error during download: {network_error}")
        bot.edit_message_text(f'Network Error: {str(network_error)}', chat_id, message_id)
        raise
    
    except Exception as general_error:
        logger.error(f"Download error: {general_error}")
        bot.edit_message_text(f'Download failed: {str(general_error)}', chat_id, message_id)
        raise

# Telegram Bot Commands and Handlers
@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Handle /start command."""
    user = message.from_user

    bot.send_chat_action(message.chat.id, 'typing')

    # Store User To DB
    if not users_collection.find_one({'user_id': user.id}):
        users_collection.insert_one({
            'user_id': user.id,
            'first_name': user.first_name,
            'downloads': 0
        })

    inline_keyboard = telebot.types.InlineKeyboardMarkup()
    inline_keyboard.row(
        telebot.types.InlineKeyboardButton("〇 𝐉𝐨𝐢𝐧𝐞 𝐂𝐡𝐚𝐧𝐧𝐞𝐥 〇", url=f"https://t.me/terao2"),
        telebot.types.InlineKeyboardButton("🫧 𝐎𝐡 𝐁𝐡𝐚𝐢 🫧", url="tg://user?id=1352497419")
    )

    welcome_message = (
        f"ᴡᴇʟᴄᴏᴍᴇ, <a href='tg://user?id={user.id}'>{user.first_name}</a>.\n\n"
        "🔄 ɪ ᴀᴍ ᴀ ᴛᴇʀᴀʙᴏx ᴅᴏᴡɴʟᴏᴀᴅᴇʀ ʙᴏᴛ.\n"
        "sᴇɴᴅ ᴍᴇ ᴀɴʏ ᴛᴇʀᴀʙᴏx ʟɪɴᴋ ɪ ᴡɪʟʟ ᴅᴏᴡɴʟᴏᴀᴅ ᴡɪᴛʜɪɴ ғᴇᴡ sᴇᴄᴏɴᴅs\n"
        "ᴀɴᴅ sᴇɴᴅ ɪᴛ ᴛᴏ ʏᴏᴜ ✨"
    )

    bot.send_photo(
        message.chat.id,
        photo="https://graph.org/file/4e8a1172e8ba4b7a0bdfa.jpg",
        caption=welcome_message,
        parse_mode='HTML',
        reply_markup=inline_keyboard
    )

# Rest of the existing code remains the same (ban, unban, broadcast, etc.)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle incoming messages."""
    user = message.from_user

    # Ignore command messages
    if message.text.startswith('/'):
        return

    bot.send_chat_action(message.chat.id, 'typing')

    # Check if user is banned
    if banned_users_collection.find_one({'user_id': user.id}):
        bot.send_message(message.chat.id, "You are banned from using this bot.")
        return

    # Check User Member or Not
    if not is_member(user.id):
        bot.send_message(
            message.chat.id,
            "ʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ᴍʏ ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴜsᴇ ᴍᴇ.",
            reply_markup=telebot.types.InlineKeyboardMarkup().add(
                telebot.types.InlineKeyboardButton("〇 𝐉𝐨𝐢𝐧𝐞 𝐂𝐡𝐚𝐧𝐧𝐞𝐥 〇", url=f"https://t.me/terao2")
            )
        )
        return
        
    video_url = message.text
    chat_id = message.chat.id
    user_mention = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
    user_id = user.id

    if re.match(r'http[s]?://.*tera', video_url):
        progress_msg = bot.send_message(chat_id, '⎋ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ʏᴏᴜʀ ᴠɪᴅᴇᴏ...')
        try:
            video_path, video_title, video_size = download_video(video_url, chat_id, progress_msg.message_id, user_mention, user_id)
            bot.edit_message_text('sᴇɴᴅɪɴɢ ʏᴏᴜ ᴛʜᴇ ᴍᴇᴅɪᴀ...🤤', chat_id, progress_msg.message_id)

            video_size_mb = video_size / (1024 * 1024)

            dump_channel_video = bot.send_video(
                os.getenv('DUMP_CHAT_ID'), 
                open(video_path, 'rb'), 
                caption=f"📂 {video_title}\n📦 {video_size_mb:.2f} MB\n🪪 𝐔𝐬𝐞𝐫 𝐁𝐲 : {user_mention}\n♂️ 𝐔𝐬𝐞𝐫 𝐋𝐢𝐧𝐤: tg://user?id={user_id}", 
                parse_mode='HTML'
            )
            bot.copy_message(chat_id, os.getenv('DUMP_CHAT_ID'), dump_channel_video.message_id)

            bot.send_sticker(chat_id, "CAACAgIAAxkBAAEM0yZm6Xz0hczRb-S5YkRIck7cjvQyNQACCh0AAsGoIEkIjTf-YvDReDYE")
            
            # Update user download count
            users_collection.update_one(
                {'user_id': user.id},
                {'$inc': {'downloads': 1}},
                upsert=True
            )
            
            # Clean up
            bot.delete_message(chat_id, progress_msg.message_id)
            bot.delete_message(chat_id, message.message_id)
            os.remove(video_path)

        except Exception as e:
            logger.error(f"Video download failed: {e}")
            bot.edit_message_text(f'Download failed: {str(e)}', chat_id, progress_msg.message_id)
    else:
        bot.send_message(chat_id, 'ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴛᴇʀᴀʙᴏx ʟɪɴᴋ.')

# Flask Routes
@app.route('/')
def index():
    """Home route."""
    return 'Bot Is Alive'

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify(status='OK'), 200

# Main Execution
if __name__ == "__main__":
    # Start Flask app in a separate thread
    def run_flask():
        """Run Flask server."""
        app.run(host='0.0.0.0', port=8000)

    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Start polling for Telegram updates
    try:
        logger.info("Starting bot polling...")
        bot.polling(none_stop=True)
    except Exception as e:
        logger.error(f"Error in bot polling: {str(e)}")
        
# @SudoR2spr by - WOODcraft
