import discord
import google.generativeai as genai
import asyncio
import threading
import json
import os
import re
import random  # ← ランダム機能を使うために追加
from dotenv import load_dotenv  # ← これを追加！

# --- .envファイルの読み込み ---
load_dotenv()  # ← これを実行することで .env の中身が使えるようになります

# --- 設定部分（ここを書き換えてください） ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))  # チャンネルID(数字)
MEMORY_FILE = 'memory.json'

# --- Geminiの設定 ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-flash-latest')
except Exception as e:
    print(f"Gemini設定エラー: {e}")

# 変数定義
user_sessions = {}
active_users_in_session = set() # 今回会話したユーザーIDリスト

# --- 共通関数: 終了処理 ---
async def shutdown_process(channel):
    """Botの終了処理を行う（挨拶 -> 保存 -> 切断）"""
    print("終了処理を実行中...")
    
    if channel:
        if active_users_in_session:
            # 会話した人全員にメンション
            mentions = " ".join([f"<@{uid}>" for uid in active_users_in_session])
           # ★ 誰かと会話した時の終了メッセージ（ランダム）
            goodbye_messages = [
                "またな！👋",
                "今日はいっぱい話せて楽しかったよ！おやすみ！🌙",
                "それじゃあね！また遊ぼう！🚀",
                "お疲れ様！また呼んでね！✨",
                "バイバイ！次もよろしくね！😆"
            ]
            await channel.send(f"{mentions}\n{random.choice(goodbye_messages)}")
        else:
            # ★ 誰も会話していなかった時の終了メッセージ（ランダム）
            lonely_goodbye_messages = [
                "誰もいなかったか...またな！👋",
                "今日は静かだったな...おやすみ！🌙",
                "今回は出番なしか...次は呼んでね！💤",
                "さみしいけど、また今度ね！🍂"
            ]
            await channel.send(random.choice(lonely_goodbye_messages))
    
    save_memory()
    await client.close()

# --- 記憶の保存・読み込み関数 ---
def save_memory():
    """現在の会話履歴を保存"""
    data_to_save = {}
    for user_id, session in user_sessions.items():
        history_data = []
        for content in session.history:
            text = "".join([part.text for part in content.parts])
            role = content.role
            history_data.append({"role": role, "parts": [text]})
        data_to_save[str(user_id)] = history_data

    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            print(">> メモリーを保存しました")
    except Exception as e:
        print(f"保存エラー: {e}")

def load_memory():
    """起動時に会話履歴を復元"""
    if not os.path.exists(MEMORY_FILE):
        return
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
        for user_id_str, history_list in saved_data.items():
            user_id = int(user_id_str)
            formatted_history = [{"role": item["role"], "parts": item["parts"]} for item in history_list]
            user_sessions[user_id] = model.start_chat(history=formatted_history)
        print(f"会話履歴を復元しました（ユーザー数: {len(user_sessions)}）")
    except Exception as e:
        print(f"読み込みエラー: {e}")

# --- Discord Botの設定 ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# --- コンソール入力監視 ---
def console_monitor():
    while True:
        try:
            command = input("コマンド ('exit':終了, 'save':保存): ")
            
            if command.strip() == "exit":
                # コンソールからの終了指令
                async def run_shutdown():
                    channel = client.get_channel(TARGET_CHANNEL_ID)
                    await shutdown_process(channel)
                
                asyncio.run_coroutine_threadsafe(run_shutdown(), client.loop)
                break
            
            elif command.strip() == "save":
                save_memory()
                
        except EOFError:
            break

# --- イベント処理 ---

@client.event
async def on_ready():
    print('--------------------------------------------------')
    print(f'{client.user} としてログインしました')
    load_memory()
    print('--------------------------------------------------')
    
    channel = client.get_channel(TARGET_CHANNEL_ID)
    if channel:
        # ★ 起動時の挨拶メッセージ（ランダム）
        greeting_messages = [
            f"**{client.user.name} 参上！** 😤",
            f"やっほー！**{client.user.name}** が来たよ！✨",
            f"**{client.user.name}** 起動完了！今日もよろしくね！🤖",
            f"ふふふ、**{client.user.name}** のお出ましだ！🔥",
            f"待たせたな！**{client.user.name}** だぞ！😎"
        ]
        await channel.send(random.choice(greeting_messages))

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if TARGET_CHANNEL_ID and message.channel.id != TARGET_CHANNEL_ID:
        return

    # ★反応条件のチェック
    # 1. Botへのメンションがある
    is_mentioned = client.user in message.mentions
    # 2. 文章内に 'gemini' が含まれている (大文字小文字無視)
    has_keyword = 'gemini' in message.content.lower()

    # どちらもなければ無視
    if not (is_mentioned or has_keyword):
        return

    # ★ここで会話ユーザーリストに追加（コマンドの場合も含む）
    active_users_in_session.add(message.author.id)

    # メンションIDの削除処理（Botへのメンションだけ消す）
    clean_text = message.content
    clean_text = re.sub(r'<@!?{}>'.format(client.user.id), '', clean_text).strip()

    # --- コマンド処理 ---
    
    # 1. 終了コマンド
    if clean_text == "!stop":
        await shutdown_process(message.channel)
        return

    # 2. 手動保存コマンド
    if clean_text == "!記憶を保存":
        save_memory()
        await message.reply("💾 会話データを手動保存しました！")
        return

    # 3. リセットコマンド
    if clean_text == "!reset":
        user_id = message.author.id
        if user_id in user_sessions:
            del user_sessions[user_id]
            save_memory()
            await message.reply(f"🧹 {message.author.display_name} さんの記憶を消去しました。")
        else:
            await message.reply("記憶データはありません。")
        return

    # --- Geminiとの会話処理 ---
    
    user_id = message.author.id
    
    if user_id not in user_sessions:
        user_sessions[user_id] = model.start_chat(history=[])

    chat_session = user_sessions[user_id]

    try:
        async with message.channel.typing():
            response = chat_session.send_message(clean_text)
            reply_text = response.text
            save_memory() # 自動保存

            if len(reply_text) > 2000:
                first_chunk = True
                for i in range(0, len(reply_text), 2000):
                    chunk = reply_text[i:i+2000]
                    if first_chunk:
                        await message.reply(chunk)
                        first_chunk = False
                    else:
                        await message.channel.send(chunk)
            else:
                await message.reply(reply_text)

    except Exception as e:
        print(f"エラー: {e}")
        await message.reply(f"エラーが発生しました: {e}")

# --- 実行部分 ---
if __name__ == '__main__':
    monitor_thread = threading.Thread(target=console_monitor, daemon=True)
    monitor_thread.start()
    
    try:
        client.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"起動エラー: {e}")
