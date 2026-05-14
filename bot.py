import discord
from discord import app_commands
import google.generativeai as genai
import asyncio
import threading
import json
import os
import re
import random
import io
from PIL import Image
from dotenv import load_dotenv

# --- .envファイルの読み込み ---
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

target_env = os.getenv("TARGET_CHANNEL_ID")
TARGET_CHANNEL_ID = int(target_env) if target_env and target_env.isdigit() else None
MEMORY_DIR = 'memories'

# --- グローバル変数 ---
current_model_name = 'gemini-flash-latest'
current_persona = ""
user_sessions = {}
user_memories = {}  
active_users_in_session = set()
channel_buffers = {}

genai.configure(api_key=GEMINI_API_KEY)

# --- ユーザー専用モデルの生成関数 ---
def get_user_model(session_key):
    """ユーザーの長期記憶をシステムプロンプトに埋め込んだ専用モデルを作成する"""
    system_instruction = current_persona
    
    if session_key in user_memories:
        mem = user_memories[session_key]
        memory_prompt = (
            "\n\n【重要：このユーザーに関するあなたの長期記憶】\n"
            f"- 人物像・特徴: {mem.get('profile', '特に情報なし')}\n"
            f"- 過去の話題: {mem.get('topics', '特に情報なし')}\n"
            "※この記憶を踏まえて、親しみやすく自然な会話を行ってください。"
        )
        system_instruction += memory_prompt

    try:
        if system_instruction.strip():
            return genai.GenerativeModel(current_model_name, system_instruction=system_instruction.strip())
        else:
            return genai.GenerativeModel(current_model_name)
    except Exception as e:
        print(f"モデル生成エラー: {e}")
        return None

# --- Discord Botの設定 ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# --- 記憶の読み込み ---
def load_memory():
    global user_memories
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)
        return

    for filename in os.listdir(MEMORY_DIR):
        if filename.endswith(".json"):
            guild_id = filename[:-5]
            file_path = os.path.join(MEMORY_DIR, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    guild_data = json.load(f)
                
                for user_id_str, memory_data in guild_data.items():
                    session_key = f"{guild_id}_{user_id_str}"
                    user_memories[session_key] = memory_data
            except Exception as e:
                print(f"読み込みエラー({filename}): {e}")
                
    print(f"長期記憶（要約データ）を復元しました（ユーザー数: {len(user_memories)}）")

# --- 会話を要約して長期記憶として保存する処理 ---
async def summarize_and_save_memories():
    print("記憶の要約処理を開始します...")
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)

    summary_model = genai.GenerativeModel(
        'gemini-flash-latest',
        generation_config={"response_mime_type": "application/json"}
    )

    guild_data_to_save = {}

    for session_key, session in user_sessions.items():
        if not session.history:
            continue 

        guild_id, user_id = session_key.split('_', 1)
        
        history_text = "\n".join([f"{content.role}: {''.join([p.text for p in content.parts if hasattr(p, 'text')])}" for content in session.history])
        existing_memory = user_memories.get(session_key, {"profile": "なし", "topics": "なし"})

        prompt = f"""
        あなたはユーザーの記憶を整理するアシスタントです。
        以下の【既存の記憶】と【今回の会話履歴】を統合・分析し、最新のユーザー情報をJSON形式で出力してください。

        【既存の記憶】
        人物像: {existing_memory['profile']}
        過去の話題: {existing_memory['topics']}

        【今回の会話履歴】
        {history_text}

        【出力JSONフォーマット】
        {{
          "profile": "ユーザーの性格、趣味、特徴、属性などの情報を簡潔に（箇条書き形式の1つの文字列）",
          "topics": "過去から現在までに話した主な話題を簡潔に（箇条書き形式の1つの文字列）"
        }}
        """

        try:
            response = await summary_model.generate_content_async(prompt)
            new_memory = json.loads(response.text)
            
            user_memories[session_key] = new_memory

            if guild_id not in guild_data_to_save:
                guild_data_to_save[guild_id] = {}
            guild_data_to_save[guild_id][user_id] = new_memory

        except Exception as e:
            print(f"要約エラー ({session_key}): {e}")

    for guild_id, data in guild_data_to_save.items():
        file_path = os.path.join(MEMORY_DIR, f"{guild_id}.json")
        merged_data = data
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_file_data = json.load(f)
                existing_file_data.update(data)
                merged_data = existing_file_data

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存エラー({guild_id}): {e}")
            
    print("記憶の要約と保存が完了しました！")

# --- 終了処理 ---
async def shutdown_process(channel):
    if channel:
        await channel.send("🧠 今回の会話を記憶として整理しているよ...少し待ってね！")
        
    await summarize_and_save_memories()

    if channel:
        if active_users_in_session:
            mentions = " ".join([f"<@{uid}>" for uid in active_users_in_session])
            goodbye_messages = ["記憶完了！またな！👋", "今日はいっぱい話せて楽しかったよ！おやすみ！🌙", "ばっちり覚えたよ！また遊ぼう！🚀"]
            await channel.send(f"{mentions}\n{random.choice(goodbye_messages)}")
        else:
            await channel.send(random.choice(["誰もいなかったか...またな！👋", "今日は静かだったな...おやすみ！🌙"]))
            
    await client.close()

# --- スラッシュコマンド ---

@tree.command(name="save", description="現在の会話を長期記憶に保存します")
async def cmd_save(interaction: discord.Interaction):
    await interaction.response.send_message("🧠 記憶を整理して保存中...", ephemeral=False)
    await summarize_and_save_memories()
    await interaction.edit_original_response(content="✨ 記憶の整理と保存が完了しました！")

@tree.command(name="stop", description="Botを終了させます")
async def cmd_stop(interaction: discord.Interaction):
    await interaction.response.send_message("終了処理と記憶の保存を開始します...", ephemeral=True)
    await shutdown_process(interaction.channel)

@tree.command(name="reset", description="自分の会話履歴（記憶）を完全にリセットします")
async def cmd_reset(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id) if interaction.guild_id else "DM"
    session_key = f"{guild_id}_{interaction.user.id}"
    
    if session_key in user_sessions: del user_sessions[session_key]
    if session_key in user_memories: del user_memories[session_key]
    
    file_path = os.path.join(MEMORY_DIR, f"{guild_id}.json")
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if str(interaction.user.id) in data:
            del data[str(interaction.user.id)]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    await interaction.response.send_message(f"🧹 {interaction.user.display_name} さんの記憶を完全に消去しました。")

@tree.command(name="model", description="Geminiのモデルを変更します（flash または pro）")
@app_commands.describe(target="flash または pro を入力")
async def cmd_model(interaction: discord.Interaction, target: str):
    global current_model_name, user_sessions
    
    if target.lower() == "flash": current_model_name = "gemini-flash-latest"
    elif target.lower() == "pro": current_model_name = "gemini-pro-latest"
    else:
        await interaction.response.send_message("⚠️ `flash` か `pro` を指定してね！", ephemeral=True)
        return

    user_sessions.clear()
    await interaction.response.send_message(f"✨ モデルを **{current_model_name}** に変更したよ！（記憶は引き継がれます）")

@tree.command(name="persona", description="Botの性格（ロールプレイ）を変更します")
@app_commands.describe(character="例：ツンデレな女子高生 など")
async def cmd_persona(interaction: discord.Interaction, character: str):
    global current_persona, user_sessions
    current_persona = f"あなたは「{character}」として振る舞ってください。"
    user_sessions.clear()
    await interaction.response.send_message(f"🎭 性格を **「{character}」** に変更しました！（記憶は引き継がれます）")

# --- イベント処理 ---
@client.event
async def on_ready():
    print(f'{client.user} 起動完了！')
    await tree.sync()
    load_memory()
    channel = client.get_channel(TARGET_CHANNEL_ID) if TARGET_CHANNEL_ID else None
    if channel: await channel.send(random.choice([f"**{client.user.name}** 起動完了！コマンドは `/` を入力してね！🤖"]))

@client.event
async def on_message(message):
    global channel_buffers

    if message.author == client.user: return
    is_in_thread = isinstance(message.channel, discord.Thread)

    if not is_in_thread:
        if TARGET_CHANNEL_ID and message.channel.id != TARGET_CHANNEL_ID: return
    else:
        if TARGET_CHANNEL_ID and message.channel.parent_id != TARGET_CHANNEL_ID: return

    active_users_in_session.add(message.author.id)

    clean_text = re.sub(r'<@!?{}>'.format(client.user.id), '', message.content).strip()
    log_text = clean_text or ("(画像が送信されました)" if message.attachments else "(無言)")

    channel_id = message.channel.id
    if channel_id not in channel_buffers: channel_buffers[channel_id] = []

    if not is_in_thread:
        channel_buffers[channel_id].append(f"{message.author.display_name}: {log_text}")
        if len(channel_buffers[channel_id]) > 30: channel_buffers[channel_id].pop(0)

    is_mentioned = client.user in message.mentions
    has_keyword = 'gemini' in message.content.lower()
    should_respond = is_in_thread or is_mentioned or has_keyword

    if not should_respond:
        try:
            await message.add_reaction(random.choice(["👀", "📝", "🤔", "👂", "✨"]))
        except: pass
        return

    # --- 返事をする時の処理 ---
    guild_id = str(message.guild.id) if message.guild else "DM"
    session_key = f"{guild_id}_{message.author.id}"

    if session_key not in user_sessions:
        user_model = get_user_model(session_key)
        user_sessions[session_key] = user_model.start_chat(history=[])

    chat_session = user_sessions[session_key]
    target_channel = message.channel
    content_parts = []

    if not is_in_thread and is_mentioned:
        thread_title = clean_text[:15] + "..." if len(clean_text) > 15 else clean_text
        if not thread_title: thread_title = f"{message.author.display_name}の会話"
        target_channel = await message.create_thread(name=thread_title, auto_archive_duration=60)
        
        combined_text = "\n".join(channel_buffers[channel_id])
        content_parts.append(f"以下の会話の流れを踏まえて、最後の発言に対して返答してください。\n\n【これまでの会話】\n{combined_text}")
        channel_buffers[channel_id].clear()
    elif not is_in_thread and has_keyword:
        combined_text = "\n".join(channel_buffers[channel_id])
        content_parts.append(f"以下の会話の流れを踏まえて、最後の発言に対して返答してください。\n\n【これまでの会話】\n{combined_text}")
        channel_buffers[channel_id].clear()
    else:
        content_parts.append(clean_text if clean_text else "やあ！")

    if message.attachments:
        for att in message.attachments:
            if att.content_type and att.content_type.startswith('image/'):
                try:
                    img_bytes = await att.read()
                    img = Image.open(io.BytesIO(img_bytes))
                    content_parts.append(img)
                except Exception as e: print(f"画像エラー: {e}")

    try:
        async with target_channel.typing():
            response = await chat_session.send_message_async(content_parts)
            reply_text = response.text

            if len(reply_text) > 2000:
                for i in range(0, len(reply_text), 2000):
                    chunk = reply_text[i:i+2000]
                    if i == 0 and not is_in_thread and not is_mentioned: await message.reply(chunk, mention_author=False)
                    else: await target_channel.send(chunk)
            else:
                if not is_in_thread and not is_mentioned: await message.reply(reply_text, mention_author=False)
                else: await target_channel.send(reply_text)

    except Exception as e:
        print(f"エラー: {e}")
        error_msg = f"エラーが発生しました: {e}"
        if not is_in_thread and not is_mentioned: await message.reply(error_msg, mention_author=False)
        else: await target_channel.send(error_msg)

def console_monitor():
    while True:
        try:
            command = input("コマンド ('exit':終了): ")
            if command.strip() == "exit":
                channel = client.get_channel(TARGET_CHANNEL_ID) if TARGET_CHANNEL_ID else None
                asyncio.run_coroutine_threadsafe(shutdown_process(channel), client.loop)
                break
        except EOFError: break

if __name__ == '__main__':
    threading.Thread(target=console_monitor, daemon=True).start()
    client.run(DISCORD_TOKEN)
