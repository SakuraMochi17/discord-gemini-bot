import google.generativeai as genai

# ここにAPIキーを入れてください
GEMINI_API_KEY = 'AIzaSyDiW4n4j_X-acmwERbtdeIYaZkYcDmSI8w'

genai.configure(api_key=GEMINI_API_KEY)

print("利用可能なモデル一覧:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")

        
# DISCORD_TOKEN = 'MTQ0NjAyMTk5MDE5MTIwNjQyMA.GW4RkA.B5Csux7vLDy0MAeHW-fQ9gRfNz4wujTNNNUI9s'
# GEMINI_API_KEY = 'AIzaSyDiW4n4j_X-acmwERbtdeIYaZkYcDmSI8w'
# TARGET_CHANNEL_ID = 1446026602797334599