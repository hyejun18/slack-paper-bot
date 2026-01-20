# Slack Paper Bot

Slack 채널에 업로드되는 생물학 논문 PDF를 자동으로 요약하여 한글로 답변하는 봇입니다.

## 주요 기능

- Slack 채널에서 PDF 파일 업로드 자동 감지
- Google Gemini API를 사용한 논문 요약
- 한글로 구조화된 요약 제공 (technical term은 영어 유지)
- 원본 메시지에 쓰레드로 요약 게시
- 요약 캐싱으로 중복 처리 방지

## 요구사항

- Ubuntu 24.04 (또는 호환 Linux)
- Python 3.11+
- uv (Python 패키지 관리자)
- Google Gemini API Key
- Slack App (Bot Token, Signing Secret)
- 공개 IP 또는 터널 서비스 (Slack webhook 수신용)

## 빠른 시작

### 1. 저장소 클론 및 의존성 설치

```bash
cd /home/ubuntu/slack-paper-bot

# uv로 가상환경 생성 및 의존성 설치
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 2. 설정 파일 생성

```bash
cp config.yml.example config.yml
nano config.yml  # 또는 선호하는 에디터
```

### 3. HTTPS 설정 (아래 옵션 중 선택)

**옵션 A: ngrok 사용 (개발/테스트용 - 권장)**

```bash
# ngrok 설치
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok

# ngrok 실행 (별도 터미널에서)
ngrok http 8000
```

config.yml에서 SSL 비활성화:
```yaml
server:
  ssl:
    enabled: false
```

**옵션 B: Cloudflare Tunnel (무료, 프로덕션용)**

```bash
# cloudflared 설치
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# 터널 실행
cloudflared tunnel --url http://localhost:8000
```

**옵션 C: 자체 서명 인증서 (제한적)**

```bash
cd scripts
./generate_cert.sh YOUR_PUBLIC_IP
```

> **주의**: Slack은 자체 서명 인증서를 거부할 수 있습니다. ngrok이나 Cloudflare Tunnel 사용을 권장합니다.

### 4. 실행

```bash
# 개발 모드
source .venv/bin/activate
python main.py
```

## Slack App 설정 가이드

### Step 1: Slack App 생성

1. [Slack API](https://api.slack.com/apps)에 접속
2. **Create New App** 클릭
3. **From scratch** 선택
4. App 이름 입력 (예: "Paper Bot")
5. Workspace 선택 후 **Create App**

### Step 2: Bot Token Scopes 설정

1. 좌측 메뉴에서 **OAuth & Permissions** 클릭
2. **Scopes** 섹션으로 스크롤
3. **Bot Token Scopes**에서 다음 권한 추가:

| Scope | 설명 |
|-------|------|
| `channels:history` | 공개 채널 메시지 읽기 |
| `channels:read` | 공개 채널 정보 읽기 |
| `chat:write` | 메시지 전송 |
| `files:read` | 파일 다운로드 |
| `groups:history` | 비공개 채널 메시지 읽기 (선택) |
| `groups:read` | 비공개 채널 정보 읽기 (선택) |

### Step 3: App 설치 및 토큰 획득

1. **OAuth & Permissions** 페이지 상단에서 **Install to Workspace** 클릭
2. 권한 승인
3. **Bot User OAuth Token** 복사 (xoxb-로 시작)
4. config.yml의 `slack.bot_token`에 입력

### Step 4: Signing Secret 획득

1. 좌측 메뉴에서 **Basic Information** 클릭
2. **App Credentials** 섹션에서 **Signing Secret** 복사
3. config.yml의 `slack.signing_secret`에 입력

### Step 5: Event Subscriptions 설정

1. 좌측 메뉴에서 **Event Subscriptions** 클릭
2. **Enable Events** 토글 ON
3. **Request URL** 입력:
   - ngrok 사용 시: `https://abc123.ngrok.io/slack/events`
   - Cloudflare 사용 시: `https://your-tunnel.trycloudflare.com/slack/events`
   - 직접 호스팅 시: `https://YOUR_IP:8000/slack/events`
4. URL 검증 성공 확인 (봇이 실행 중이어야 함)
5. **Subscribe to bot events**에서 다음 이벤트 추가:
   - `message.channels` (공개 채널 메시지)
   - `message.groups` (비공개 채널 메시지 - 선택)
6. **Save Changes** 클릭

### Step 6: 채널에 봇 초대

```
/invite @YourBotName
```

또는 채널 설정 > Integrations > Add apps에서 봇 추가

### Step 7: 채널 ID 확인

1. Slack에서 채널 우클릭
2. **View channel details** 클릭
3. 가장 아래에서 **Channel ID** 복사 (C로 시작)
4. config.yml의 `slack.channel_ids`에 추가

## Google Gemini API 설정

1. [Google AI Studio](https://aistudio.google.com/app/apikey) 접속
2. **Create API Key** 클릭
3. API Key 복사
4. config.yml의 `gemini.api_key`에 입력

> **무료 티어**: 분당 15 요청, 일일 1,500 요청 제공

## 설정 파일 상세

```yaml
# Slack 설정
slack:
  bot_token: "xoxb-..."      # Bot User OAuth Token
  signing_secret: "..."       # App Signing Secret
  channel_ids:                # 모니터링할 채널 ID들
    - "C0123456789"

# Gemini API 설정
gemini:
  api_key: "..."              # Google AI API Key
  model: "gemini-1.5-flash"   # 사용할 모델

# 서버 설정
server:
  host: "0.0.0.0"
  port: 8000
  ssl:
    enabled: false            # ngrok/cloudflare 사용 시 false

# 요약 설정
summary:
  max_pages: 50               # 최대 처리 페이지
  detail_level: "normal"      # short, normal, detailed
  enable_cache: true          # 캐싱 활성화
```

## systemd로 백그라운드 실행

### 서비스 파일 설치

```bash
# 서비스 파일 복사
sudo cp systemd/slack-paper-bot.service.example /etc/systemd/system/slack-paper-bot.service

# 필요시 경로 수정
sudo nano /etc/systemd/system/slack-paper-bot.service

# systemd 리로드
sudo systemctl daemon-reload

# 서비스 시작
sudo systemctl start slack-paper-bot

# 부팅 시 자동 시작
sudo systemctl enable slack-paper-bot

# 상태 확인
sudo systemctl status slack-paper-bot

# 로그 확인
journalctl -u slack-paper-bot -f
```

## 요약 형식

봇은 다음 형식으로 논문을 요약합니다:

```
**제목 (Title)**: [영어 원제목]

**저자 (Authors)**: [저자 및 소속]

**배경 (Background)**:
[연구 배경 및 목적]

**방법 (Methods)**:
- [실험 방법 1]
- [실험 방법 2]

**결과 (Results)**:
- [주요 발견 1]
- [주요 발견 2]

**결론 (Conclusion)**:
[연구의 의의]

**핵심 용어**:
- CRISPR-Cas9: [설명]
- phosphorylation: [설명]
```

## 트러블슈팅

### URL 검증 실패

```
Error: Request URL verification failed
```

**해결책**:
1. 봇이 실행 중인지 확인
2. 포트가 열려있는지 확인: `sudo ufw allow 8000`
3. Oracle Cloud 보안 규칙에서 포트 허용
4. ngrok/cloudflare URL이 올바른지 확인

### 파일 다운로드 실패

```
Error: Failed to download PDF
```

**해결책**:
1. `files:read` 스코프가 있는지 확인
2. 봇이 채널에 초대되어 있는지 확인
3. App을 다시 설치하여 권한 갱신

### Gemini API 오류

```
Error: 429 Resource has been exhausted
```

**해결책**:
1. API 할당량 확인 (무료: 분당 15요청)
2. `gemini-1.5-flash` 모델 사용 (더 빠름)
3. 요약 캐싱 활성화

### SSL 인증서 오류

```
Error: SSL certificate verify failed
```

**해결책**:
- 자체 서명 대신 ngrok 또는 Cloudflare Tunnel 사용

## 프로젝트 구조

```
slack-paper-bot/
├── main.py                     # FastAPI 메인 애플리케이션
├── config.yml.example          # 설정 파일 템플릿
├── requirements.txt            # Python 의존성
├── modules/
│   ├── __init__.py
│   ├── config.py              # 설정 로더
│   ├── pdf_parser.py          # PDF 텍스트 추출
│   ├── slack_handler.py       # Slack 이벤트 처리
│   └── summarizer.py          # Gemini 요약 생성
├── systemd/
│   └── slack-paper-bot.service.example
├── scripts/
│   └── generate_cert.sh       # SSL 인증서 생성
├── certs/                     # SSL 인증서 (gitignore)
├── cache/                     # 요약 캐시 (gitignore)
└── logs/                      # 로그 파일 (gitignore)
```

## 라이선스

MIT License
