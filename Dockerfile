# Sử dụng Python 3.12 slim làm image cơ sở
FROM python:3.12-slim

# Thiết lập thư mục làm việc trong container
WORKDIR /app

# Cài đặt uv và các thư viện core hệ thống để build packages (như psycopg2)
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
RUN pip install uv

# Copy các file cấu hình dependency
COPY pyproject.toml uv.lock ./

# Cài đặt các dependencies thông qua uv (tạo ảo venv & sync the lock file)
RUN uv sync --frozen --no-install-project

# Copy toàn bộ mã nguồn vào thư mục làm việc
COPY . .

# Expose port (8080 là port mặc định thường dùng cho App Runner)
EXPOSE 8000

# Chạy FastAPI thông qua uv run uvicorn
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]