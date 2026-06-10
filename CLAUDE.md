# Slack Paper Bot

Slack 채널에 업로드된 생물학 논문 PDF를 자동으로 요약하는 봇.

## 기술 스택

- **Framework**: FastAPI + Uvicorn (HTTP 모드) / slack-bolt SocketModeHandler (Socket Mode)
- **PDF 파싱**: PyMuPDF (fitz) - pdfplumber보다 훨씬 빠름
- **LLM**: Google Gemini 2.0 Flash (`google-generativeai` 패키지)
- **Slack SDK**: slack-sdk, slack-bolt
- **Python**: 3.x with uv (가상환경: `.venv/`)

## 서버 실행

```bash
cd /home/ubuntu/slack-paper-bot
source .venv/bin/activate
python main.py
```

백그라운드 실행:
```bash
nohup python main.py > logs/server.log 2>&1 &
```

## 주요 파일

```
slack-paper-bot/
├── main.py                 # FastAPI 앱, Slack 이벤트 핸들링
├── config.yml              # 설정 파일 (API 키, 채널 ID 등)
├── requirements.txt        # 의존성 목록
├── modules/
│   ├── config.py           # 설정 로더
│   ├── slack_handler.py    # Slack API 통신
│   ├── pdf_parser.py       # PDF 텍스트 추출 (PyMuPDF)
│   └── summarizer.py       # Gemini API로 요약 생성
├── certs/
│   ├── cert.pem            # SSL 인증서 (자체 서명)
│   └── key.pem             # SSL 키
├── cache/                  # 요약 캐시 (JSON)
└── logs/                   # 로그 파일
```

## 실행 모드

`config.yml`의 `slack.mode`로 선택:

| 모드 | 설명 | 필요 조건 |
|---|---|---|
| `socket` | Socket Mode (WebSocket) | App-Level Token (`xapp-`) |
| `http` | HTTP webhook | 공개 IP, SSL 인증서 |

## 설정 (config.yml)

### Socket Mode (권장, 공개 IP 불필요)
```yaml
slack:
  mode: "socket"
  bot_token: "xoxb-..."
  signing_secret: "..."
  app_token: "xapp-..."   # connections:write scope 필요
  channel_ids:
    - "C0A2GBX9E6Q"
    - "C09HAUJLJ8Y"

gemini:
  api_key: "AIza..."
  model: "gemini-2.0-flash"
```

### HTTP Mode (기존 방식)
```yaml
slack:
  mode: "http"
  bot_token: "xoxb-..."
  signing_secret: "..."
  channel_ids:
    - "C0A2GBX9E6Q"

gemini:
  api_key: "AIza..."
  model: "gemini-2.0-flash"

server:
  host: "0.0.0.0"
  port: 8000
  ssl:
    enabled: true
    cert_file: "certs/cert.pem"
    key_file: "certs/key.pem"
```

## Slack App 필수 권한

- `channels:history`, `channels:read`
- `chat:write`
- `files:read`
- `reactions:write`

Event Subscriptions:
- `file_shared`
- `message.channels`

### Socket Mode 추가 설정 (Slack App 콘솔)

1. **Socket Mode** 활성화 (App Settings → Socket Mode)
2. **App-Level Tokens** → Generate Token → scope: `connections:write` → `xapp-` 토큰 생성
3. Event Subscriptions의 Request URL 제거 (Socket Mode로 대체)

## 요약 프롬프트

- 위치: `modules/summarizer.py` → `PROMPTS` dict
- 레벨: `short`, `normal`, `detailed`
- 프롬프트는 영어, 출력은 한글 (기술 용어는 영어 유지)

## 알려진 이슈

- `google.generativeai` 패키지 deprecated 경고 발생 (기능은 정상 작동)
- 향후 `google.genai` 패키지로 마이그레이션 필요

## 캐시 초기화

프롬프트 변경 후 캐시 삭제:
```bash
rm -rf cache/*.json
```
