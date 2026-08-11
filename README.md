# Trợ lý chứng khoán cá nhân

Agent cá nhân theo dõi giá/watchlist/danh mục chứng khoán Việt Nam, chat qua Telegram,
dùng Claude làm bộ não, Supabase làm bộ nhớ, có trang admin để chỉnh prompt/config.

**Agent chỉ đề xuất, không tự đặt lệnh giao dịch thật.** Bạn tự thực hiện giao dịch trên
app của công ty chứng khoán mình đang dùng.

## Kiến trúc

```
Telegram (owner) <-> Bot (python-telegram-bot, polling)
                         |
                         +-- Claude API (Tool Runner) --> market_data adapter (VNDirect / vnstock)
                         |
                         +-- Supabase (Postgres): holdings, watchlist, conversation_messages,
                                                    prompts, config, price_cache, alerts_log

Admin website (FastAPI, cùng process) --> sửa prompts/config trong Supabase
VPS (Docker) --> chạy 1 container duy nhất, admin site đứng sau reverse proxy có sẵn
```

## Bước 0 - Tạo các tài khoản/hạ tầng cần thiết

### 1. Anthropic - chọn 1 trong 2 cách

**Cách A - API key trả theo lượng dùng (đơn giản nhất):** lấy tại
https://console.anthropic.com -> API Keys, dán vào `ANTHROPIC_API_KEY` trong `.env`.

**Cách B - Dùng gói Claude Pro/Max của bạn (đang dùng cách này):**

> ⚠️ Cơ chế đăng nhập OAuth này chủ yếu được thiết kế cho Claude Code. Dùng nó cho
> một app tự viết gọi trực tiếp Messages API (như bot này) *có thể* hoạt động vì cùng
> dùng chung cơ chế xác thực của SDK, nhưng chưa có tài liệu chính thức xác nhận ổn
> định 100% cho use case này. Nếu sau này gặp lỗi `permission_error` khi gọi Claude,
> quay lại Cách A (điền `ANTHROPIC_API_KEY`) là fallback chắc chắn hoạt động.

1. Cài `ant` CLI (trên máy tính cá nhân hoặc trực tiếp trên VPS qua SSH) - xem
   hướng dẫn cài tại https://github.com/anthropics/anthropic-cli/releases (Linux/VPS)
   hoặc `brew install anthropics/tap/ant` (macOS).
2. Trong thư mục project (trên máy sẽ chạy Docker - thường là VPS):
   ```bash
   mkdir -p anthropic-config
   ANTHROPIC_CONFIG_DIR="$(pwd)/anthropic-config" ant auth login --no-browser
   ```
3. Lệnh trên in ra 1 URL - mở URL đó trên điện thoại/máy tính bất kỳ có trình duyệt,
   đăng nhập bằng tài khoản Claude.ai (Pro/Max) của bạn, rồi dán mã xác nhận ngược lại
   vào terminal SSH.
4. Cho phép container đọc được thư mục credentials vừa tạo:
   ```bash
   chmod -R go+rX anthropic-config
   ```
5. Trong `.env`, để `ANTHROPIC_API_KEY` **trống** và giữ
   `ANTHROPIC_CONFIG_DIR=/anthropic-config` (đường dẫn trong container, đã map sẵn
   trong `docker-compose.yml`). Bot sẽ tự nhận credentials từ đây khi khởi động.

### 2. Telegram Bot (chưa có - làm theo các bước sau)
1. Mở Telegram, tìm **@BotFather**, gửi `/newbot`.
2. Đặt tên hiển thị và username (phải kết thúc bằng `bot`, ví dụ `MyStockAgentBot`).
3. BotFather trả về một token dạng `123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   -> dán vào `TELEGRAM_BOT_TOKEN`.
4. Lấy Telegram user ID (số) của chính bạn để chỉ mình bạn dùng được bot: mở chat với
   **@userinfobot** (hoặc @getidsbot), nó sẽ trả về ID dạng số -> dán vào `TELEGRAM_OWNER_ID`.

### 3. Supabase (project mới)
1. Tạo project mới tại https://supabase.com/dashboard.
2. Vào **SQL Editor**, dán toàn bộ nội dung [`supabase/schema.sql`](supabase/schema.sql) và chạy.
3. Vào **Project Settings -> API**:
   - `Project URL` -> dán vào `SUPABASE_URL`
   - `service_role` key (không phải `anon` key) -> dán vào `SUPABASE_SERVICE_KEY`
     (đây là key có quyền ghi/đọc mọi bảng, chỉ dùng ở backend, không bao giờ đưa ra frontend)

### 4. Mật khẩu trang admin
Trang admin chỉ có 1 tài khoản (chính bạn). Tạo password hash:

```bash
python -c "from app.admin.auth import hash_password; print(hash_password('mật-khẩu-của-bạn'))"
```

Dán kết quả vào `ADMIN_PASSWORD_HASH` trong `.env`. Đồng thời đặt `ADMIN_SESSION_SECRET`
thành một chuỗi ngẫu nhiên dài (`python -c "import secrets; print(secrets.token_hex(32))"`).

### 5. Cấu hình `.env`
```bash
cp .env.example .env
```
Điền tất cả các giá trị ở trên vào `.env`.

## Chạy thử cục bộ (không cần Docker)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

Mở http://localhost:8080/admin để vào trang admin, mở Telegram chat với bot để test chat.

## Chạy bằng Docker (khuyến nghị cho VPS)

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

Container bind vào `127.0.0.1:8080` (không public trực tiếp) - xem phần deploy VPS dưới đây
để biết cách trỏ domain vào nó qua reverse proxy.

## Deploy lên VPS (Hostinger, dùng chung với dịch vụ khác)

VPS đang dùng chung nên **kiểm tra trước khi cài** để tránh xung đột:

```bash
docker ps                     # container nào đang chạy, chiếm port nào
sudo ss -tlnp                 # port nào đang mở
sudo systemctl status nginx caddy 2>/dev/null   # có reverse proxy sẵn chưa
```

Nếu port `8080` đã bị dùng, đổi cổng host trong `docker-compose.yml`
(`"127.0.0.1:8080:8080"` -> đổi số bên trái, ví dụ `18080`).

### Nếu VPS đã có Nginx/Caddy chạy sẵn
Thêm 1 site/server block mới trỏ tới `127.0.0.1:<port>` cho subdomain quản trị
(ví dụ `agent-admin.tencuaban.com`), xin SSL bằng certbot (Nginx) hoặc để Caddy tự làm.

### Nếu VPS chưa có reverse proxy nào
Cài Caddy (tự động xin SSL, cấu hình ít nhất):

```bash
sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:
```
agent-admin.tencuaban.com {
    reverse_proxy 127.0.0.1:8080
}
```

```bash
sudo systemctl reload caddy
```

Bot Telegram chạy polling (không cần domain/webhook), nên chỉ trang admin mới cần
domain + SSL ở trên.

### Copy code lên VPS và chạy
```bash
git clone <repo-url> stock-agent   # hoặc scp cả thư mục lên
cd stock-agent
cp .env.example .env   # rồi điền giá trị thật
docker compose up -d --build
```

## Lưu ý quan trọng

- **Nguồn dữ liệu VNDirect (`app/tools/market_data.py`) là API không chính thức** - endpoint
  có thể thay đổi hoặc bị chặn bất cứ lúc nào. Nếu gặp lỗi liên tục, đổi
  `MARKET_DATA_SOURCE=vnstock` trong `.env` để chuyển sang nguồn tổng hợp `vnstock`
  (aggregator VCI/TCBS/MSN) mà không cần sửa code khác.
- **Secrets không bao giờ đi qua trang admin** - `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`,
  `SUPABASE_SERVICE_KEY` chỉ nằm trong `.env` trên VPS. Trang admin chỉ sửa được
  `prompts`/`config` (không nhạy cảm) trong Supabase.
- **Agent không đặt lệnh giao dịch thật** - chỉ đề xuất ý tưởng qua chat, không tích hợp
  API broker.
- Mỗi lần sửa prompt trên trang admin sẽ tạo **version mới** (không đè lên bản cũ) -
  xem lịch sử ở trang Prompts để biết cần rollback thì sửa lại nội dung cũ và lưu.
