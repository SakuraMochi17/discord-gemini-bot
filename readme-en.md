# 🤖 Discord Gemini AI Bot

A multi-functional chat bot that allows you to easily use Google's high-performance generative AI, "Gemini," directly on Discord.
More than just a simple Q&A tool, it functions as a smart assistant capable of understanding channel context ("reading the room"), analyzing images, changing personalities, and summarizing conversations.

## ✨ Key Features

* **💬 Context-Aware Natural Conversation**
The bot remembers up to the last 30 messages in a channel, allowing for responses based on context (e.g., "Regarding what we were just talking about...").
* **🧵 Topic Organization via Threads**
When you mention the bot, it automatically creates a dedicated thread for its reply. This keeps the main channel clean and allows you to focus on specific topics. Inside the thread, no further mentions are required to continue the conversation.
* **👀 Image Recognition (Multimodal Support)**
By attaching an image and sending a message, Gemini will analyze the image content to provide explanations or answer questions.
* **🎭 Persona (Personality) Customization**
You can freely change the bot's tone and personality with a single command.
* **📝 Conversation Summary**
The bot reads recent chat logs and provides a quick summary of what the current discussion is about.

---

## 🎮 Basic Usage

In the designated channel where the bot is installed, you can interact with it using the following methods:

1. **Mentioning the Bot (`@Bot [message]`)**
* The bot automatically **creates a dedicated thread** and replies within it.
* Inside the thread, you can continue the conversation without mentioning the bot.


2. **Using the Keyword (`gemini [message]`)**
* If the message contains the word `gemini` (case-insensitive), the bot will reply directly in the channel without creating a thread.
* Note: The bot uses "Reply without mention" to avoid unnecessary notification sounds.


3. **Sending Images**
* Attach an image and call the bot with a comment to get a response regarding the image content.



---

## ⌨️ Slash Commands

Type `/` in the Discord chat bar to access the following commands:

| Command | Description |
| --- | --- |
| `/summary [limit]` | Summarizes the most recent conversation in the channel (Default: 30 messages, Max: 100). |
| `/persona [character]` | Changes the bot's personality or tone (e.g., Tsundere, Butler, etc.). *Note: Memory will be reset.* |
| `/model [flash/pro]` | Switches between Gemini models. Choose `flash` for speed or `pro` for high precision. |
| `/reset` | Clears your conversation history with the bot and resets the topic. |
| `/stop` | Safely shuts down the bot system. |

---

## 🛠️ Setup Instructions

Follow these steps to run the bot in your own environment.

### 1. Prerequisites

Obtain the following three pieces of information:

* **Discord Bot Token**: Create a bot on the [Discord Developer Portal](https://discord.com/developers/applications) and retrieve the token.
* ⚠️ **Important**: In the Bot settings tab, ensure **"Message Content Intent"** is turned **ON**.


* **Gemini API Key**: Get your API key from [Google AI Studio](https://aistudio.google.com/).
* **Target Channel ID**: Copy the ID (numeric) of the Discord channel where you want the bot to operate.

### 2. Installation

Clone the repository and install the required Python libraries.

```bash
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
pip install discord.py google-generativeai pillow python-dotenv

```

### 3. Environment Variables (.env)

Create a file named `.env` in the bot's root directory and add the information gathered in Step 1.

```env
DISCORD_TOKEN=your_discord_token_here
GEMINI_API_KEY=your_gemini_api_key_here
TARGET_CHANNEL_ID=your_target_channel_id_here

```

### 4. Running the Bot

Start the bot using the following command:

```bash
python bot.py

```

Setup is successful if the console displays `[Bot Name] is now online!`.

---

## 📂 File Structure

* `bot.py`: The main program for the bot.
* `.env`: Stores sensitive information like tokens (※ Do not share this on GitHub).
* `.gitignore`: Lists files to be excluded from Git version control.
* `memory.json`: Automatically stores conversation history per user. This file is loaded at startup and updated during conversations or upon shutdown.
