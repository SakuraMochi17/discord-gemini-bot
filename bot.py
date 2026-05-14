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
from PIL import Image  # 画像処理用
from dotenv import load_dotenv

# --- .envファイルの読み込み ---
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))
MEMORY_FILE = 'memory.json'

# --- グローバル変数 ---
current_model_name = 'gemini-flash-latest'
current_persona = ""  # Botの性格（システムプロンプト）
user_sessions = {}
active_users_in_session = set()
channel_buffer = []  # ← ★これを追加！（チャンネルの会話を一時保存するリスト）


# --- Geminiモデルの初期化関数 ---
def create_model():
    """現在の設定（モデル・性格）でGeminiを再構築する"""
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        if current_persona:
            return genai.GenerativeModel(current_model_name, system_instruction=current_persona)
        else:
            return genai.GenerativeModel(current_model_name)
    except Exception as e:
        print(f"Gemini設定エラー: {e}")
        return None

model = create_model()

# --- Discord Botの設定 ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client) # スラッシュコマンド用

# --- 記憶の保存・読み込み関数 ---
def save_memory():
    data_to_save = {}
    for user_id, session in user_sessions.items():
        history_data = []
        for content in session.history:
            # 画像などのテキスト以外のパーツは保存が難しいため、テキストのみ抽出して保存
            parts_text = [part.text for part in content.parts if hasattr(part, 'text')]
            if parts_text:
                history_data.append({"role": content.role, "parts": ["".join(parts_text)]})
        data_to_save[str(user_id)] = history_data
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存エラー: {e}")

def load_memory():
    global user_sessions
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

# --- 終了処理 ---
async def shutdown_process(channel):
    print("終了処理を実行中...")
    if channel:
        if active_users_in_session:
            mentions = " ".join([f"<@{uid}>" for uid in active_users_in_session])
            goodbye_messages = ["またな！👋", "今日はいっぱい話せて楽しかったよ！おやすみ！🌙", "それじゃあね！また遊ぼう！🚀", "お疲れ様！また呼んでね！✨"]
            await channel.send(f"{mentions}\n{random.choice(goodbye_messages)}")
        else:
            lonely_messages = ["誰もいなかったか...またな！👋", "今日は静かだったな...おやすみ！🌙", "今回は出番なしか...次は呼んでね！💤"]
            await channel.send(random.choice(lonely_messages))
    save_memory()
    await client.close()

# --- ★【機能4】スラッシュコマンドの定義 ---

@tree.command(name="stop", description="Botを終了させます")
async def cmd_stop(interaction: discord.Interaction):
    await interaction.response.send_message("終了処理を開始します...", ephemeral=True)
    await shutdown_process(interaction.channel)

@tree.command(name="reset", description="自分の会話履歴（記憶）をリセットします")
async def cmd_reset(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in user_sessions:
        del user_sessions[user_id]
        save_memory()
        await interaction.response.send_message(f"🧹 {interaction.user.display_name} さんの記憶を消去しました。")
    else:
        await interaction.response.send_message("記憶データはありません。", ephemeral=True)

@tree.command(name="model", description="Geminiのモデルを変更します（flash または pro）")
@app_commands.describe(target="flash または pro を入力")
async def cmd_model(interaction: discord.Interaction, target: str):
    global current_model_name, model, user_sessions
    
    if target.lower() == "flash":
        current_model_name = "gemini-flash-latest"
    elif target.lower() == "pro":
        current_model_name = "gemini-pro-latest"
    else:
        await interaction.response.send_message("⚠️ `flash` か `pro` を指定してね！", ephemeral=True)
        return

    model = create_model()
    user_sessions.clear() # モデル変更時はエラー防止のため全員の記憶をリセット
    save_memory()
    await interaction.response.send_message(f"✨ モデルを **{current_model_name}** に変更し、全員の記憶をリセットしたよ！")

# --- ★【機能2】性格変更コマンド ---
@tree.command(name="persona", description="Botの性格（ロールプレイ）を変更します")
@app_commands.describe(character="例：ツンデレな女子高生、冷静な執事、関西弁のおじさん など")
async def cmd_persona(interaction: discord.Interaction, character: str):
    global current_persona, model, user_sessions
    current_persona = f"あなたは「{character}」として振る舞ってください。"
    
    model = create_model()
    user_sessions.clear() # 性格が変わるのでこれまでの会話もリセット
    save_memory()
    await interaction.response.send_message(f"🎭 性格を **「{character}」** に変更しました！（※設定反映のため記憶をリセットしました）")

# --- ★【機能3】会話要約コマンド ---
@tree.command(name="summary", description="このチャンネルの最近の会話を要約します")
@app_commands.describe(limit="何件前までのメッセージを読み込むか（10〜100件）")
async def cmd_summary(interaction: discord.Interaction, limit: int = 30):
    await interaction.response.defer() # 処理に時間がかかるので「考え中...」を表示させる
    
    if limit > 100: limit = 100
    
    messages = []
    async for msg in interaction.channel.history(limit=limit):
        if msg.author != client.user: # 自分の発言以外を取得
            messages.append(f"{msg.author.display_name}: {msg.content}")
            
    messages.reverse() # 古い順に並べ替え
    chat_log = "\n".join(messages)
    
    prompt = f"以下のチャットログを読んで、現在どんな話題で盛り上がっているか、簡潔に楽しく要約して教えてください。\n\n【チャットログ】\n{chat_log}"
    
    try:
        response = model.generate_content(prompt)
        await interaction.followup.send(f"**【直近 {limit} 件の会話要約】**\n{response.text}")
    except Exception as e:
        await interaction.followup.send("ごめん、要約中にエラーが出ちゃった💦")

# --- イベント処理 ---
@client.event
async def on_ready():
    print(f'{client.user} 起動完了！')
    await tree.sync() # スラッシュコマンドをDiscordに登録
    print('>> スラッシュコマンドを同期しました')
    load_memory()
    
    channel = client.get_channel(TARGET_CHANNEL_ID)
    if channel:
        greetings = [f"**{client.user.name}** 起動完了！コマンドは `/` を入力してね！🤖"]
        await channel.send(random.choice(greetings))

@client.event
async def on_message(message):
    global channel_buffer

    if message.author == client.user: return
    
    # 💡 現在の場所が「スレッドの中」かどうかを判定
    is_in_thread = isinstance(message.channel, discord.Thread)

    # チャンネルのフィルタリング（メインチャンネルか、そのチャンネル内のスレッドでのみ動作）
    if not is_in_thread:
        if TARGET_CHANNEL_ID and message.channel.id != TARGET_CHANNEL_ID: return
    else:
        if TARGET_CHANNEL_ID and message.channel.parent_id != TARGET_CHANNEL_ID: return

    # テキストの整形
    clean_text = re.sub(r'<@!?{}>'.format(client.user.id), '', message.content).strip()
    log_text = clean_text or ("(画像が送信されました)" if message.attachments else "(無言)")

    # 💡 スレッド「外」のメインチャンネルでのみ、会話をバッファ（一時メモ）に記録する
    if not is_in_thread:
        channel_buffer.append(f"{message.author.display_name}: {log_text}")
        if len(channel_buffer) > 30: channel_buffer.pop(0)

    # 反応条件のチェック
    is_mentioned = client.user in message.mentions
    has_keyword = 'gemini' in message.content.lower()

    # 💡 返事をするべきかどうかの判定（スレッド内なら無条件でTrueになる）
    should_respond = is_in_thread or is_mentioned or has_keyword

    if not should_respond:
        return  # 反応条件を満たさなければここで終了

    # --- 以下、Botが返事をする時の処理 ---
    active_users_in_session.add(message.author.id)

    user_id = message.author.id
    if user_id not in user_sessions:
        user_sessions[user_id] = model.start_chat(history=[])

    chat_session = user_sessions[user_id]

    target_channel = message.channel  # デフォルトの送信先
    content_parts = []

    # 💡 パターンA：メインチャンネルでメンションされた場合（スレッドを作成）
    if not is_in_thread and is_mentioned:
        # スレッドのタイトルを決める（発言の先頭15文字、空なら「〇〇の会話」）
        thread_title = clean_text[:15] + "..." if len(clean_text) > 15 else clean_text
        if not thread_title: thread_title = f"{message.author.display_name}の会話"
        
        # メッセージに紐づくスレッドを作成し、送信先をそのスレッドに変更
        target_channel = await message.create_thread(name=thread_title, auto_archive_duration=60)
        
        # バッファを読み込んでGeminiに渡す
        combined_text = "\n".join(channel_buffer)
        content_parts.append(f"以下の会話の流れを踏まえて、最後の発言に対して返答してください。\n\n【これまでの会話】\n{combined_text}")
        channel_buffer.clear()

    # 💡 パターンB：メインチャンネルで「gemini」と呼ばれた場合（スレッドを作らない）
    elif not is_in_thread and has_keyword:
        combined_text = "\n".join(channel_buffer)
        content_parts.append(f"以下の会話の流れを踏まえて、最後の発言に対して返答してください。\n\n【これまでの会話】\n{combined_text}")
        channel_buffer.clear()

    # 💡 パターンC：スレッド内の場合（バッファを使わず、そのまま会話する）
    else:
        content_parts.append(clean_text if clean_text else "やあ！")

    # 画像の処理
    if message.attachments:
        for att in message.attachments:
            if att.content_type and att.content_type.startswith('image/'):
                try:
                    img_bytes = await att.read()
                    img = Image.open(io.BytesIO(img_bytes))
                    content_parts.append(img)
                except Exception as e:
                    print(f"画像読み込みエラー: {e}")

    try:
        async with target_channel.typing():
            response = chat_session.send_message(content_parts)
            reply_text = response.text
            save_memory()

            # 返信処理（文字数オーバー時の分割対応）
            if len(reply_text) > 2000:
                for i in range(0, len(reply_text), 2000):
                    chunk = reply_text[i:i+2000]
                    if i == 0 and not is_in_thread and not is_mentioned:
                        # メインチャンネルでの初回の返信のみリプライ
                        await message.reply(chunk, mention_author=False)
                    else:
                        await target_channel.send(chunk)
            else:
                if not is_in_thread and not is_mentioned:
                    await message.reply(reply_text, mention_author=False)
                else:
                    await target_channel.send(reply_text)

    except Exception as e:
        print(f"エラー: {e}")
        if not is_in_thread and not is_mentioned:
            await message.reply(f"エラーが発生しました: {e}", mention_author=False)
        else:
            await target_channel.send(f"エラーが発生しました: {e}")
            

# コンソール入力監視（変更なし）
def console_monitor():
    while True:
        try:
            command = input("コマンド ('exit':終了): ")
            if command.strip() == "exit":
                asyncio.run_coroutine_threadsafe(shutdown_process(client.get_channel(TARGET_CHANNEL_ID)), client.loop)
                break
        except EOFError: break

if __name__ == '__main__':
    threading.Thread(target=console_monitor, daemon=True).start()
    client.run(DISCORD_TOKEN)
