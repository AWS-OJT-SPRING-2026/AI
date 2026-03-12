import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from app.models.schema import Book

# Load environment variables
load_dotenv()


# ==========================================
# Đoạn code sử dụng LLM_model cơ bản
# ==========================================
# Khởi tạo OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Lấy tên model từ file .env
llm_model = os.getenv("LLM_MODEL", "gpt-5-mini")

print(f"\nĐang gọi model: {llm_model} ...")

# Tạo request completion
response = client.chat.completions.create(
    model=llm_model,
    messages=[
        {"role": "system", "content": "Bạn là một trợ lý AI hữu ích."},
        {"role": "user", "content": "Xin chào, bạn có thể giúp gì cho tôi?"}
    ]
)

# In kết quả
print("\n-------- LLM Response --------")
print(response.choices[0].message.content)
