# Circle Monitor

Circle, USDC, 주요 경쟁사, 미국 규제/법안 관련 "진짜 새로운 정보만" 골라서 알림으로 보내는 Python 모니터링 봇입니다. 기본 설계는 `RSS/웹 수집 -> 정규화 -> 신규성 판정 -> SQLite 저장 -> 알림 전송` 흐름입니다.

## 1. 아키텍처

### 폴더 구조

```text
circle analysis/
├─ config.example.toml
├─ pyproject.toml
├─ README.md
├─ src/
│  └─ circle_monitor/
│     ├─ cli.py
│     ├─ app.py
│     ├─ analysis.py
│     ├─ config.py
│     ├─ logging_utils.py
│     ├─ models.py
│     ├─ repository.py
│     ├─ dedupe.py
│     ├─ formatting.py
│     ├─ retry.py
│     ├─ sources/
│     │  ├─ base.py
│     │  ├─ rss.py
│     │  └─ website.py
│     └─ notifiers/
│        ├─ base.py
│        ├─ stdout.py
│        ├─ telegram.py
│        ├─ discord.py
│        └─ slack.py
└─ tests/
   ├─ test_dedupe.py
   └─ test_repository.py
```

### 데이터 흐름

1. `cli.py`가 설정 파일을 읽고 로그/DB를 초기화합니다.
2. `app.py`가 주기적으로 각 소스를 순회하며 아이템을 가져옵니다.
3. `analysis.py`가 제목, 본문, 키워드, 시간, URL을 정규화하고 이벤트 후보를 만듭니다.
4. `dedupe.py`가 기존 이벤트 DB와 비교해서 신규 여부를 판정합니다.
5. 신규 이벤트만 `repository.py`를 통해 SQLite에 저장합니다.
6. `formatting.py`가 요구사항 형식의 메시지를 만들고, `notifiers`가 Telegram/Discord/Slack/stdout으로 전송합니다.

### 신규성 판정 로직

다음 조건을 함께 사용합니다.

1. URL canonicalization
2. 제목 유사도(`SequenceMatcher`)
3. 본문 핵심 토큰 유사도(Jaccard)
4. 동일 카테고리/근접 시간대 비교
5. 기존 이벤트 대비 "새 수치/새 문서/새 단계/새 규제 조치" 존재 여부 탐지

후속 기사라도 새로운 수치, 문서 번호, 법안 단계, 파트너십, 소송 단계가 없으면 중복으로 처리합니다.

## 2. 빠른 시작

### Windows 또는 Ubuntu 공통

```bash
python -m venv .venv
```

PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -e .[dev]
Copy-Item config.example.toml config.toml
python -m circle_monitor.cli --config config.toml --once
```

Bash:

```bash
source .venv/bin/activate
pip install -e '.[dev]'
cp config.example.toml config.toml
python -m circle_monitor.cli --config config.toml --once
```

## 3. 설정

`config.toml`에서 아래를 조정합니다.

- `poll_interval_seconds`: 수집 주기
- `database_path`: SQLite 경로
- `log_path`: 로그 파일 경로
- `alert_recency_hours`: 이 시간창 안에서 발생한 이벤트만 알림 허용
- `notifications.enabled`: `stdout`, `telegram`, `discord`, `slack` 중 활성화할 전송기
- `sources`: RSS 또는 웹 수집 대상
- `filters.required_keywords`: 기본 관심 키워드
- `filters.high_impact_keywords`: 우선순위를 높게 볼 키워드

### Telegram 사용 예

```toml
[notifications]
enabled = ["telegram"]

[notifications.telegram]
bot_token = "123456:ABCDEF"
chat_id = "123456789"
```

### Discord 사용 예

```toml
[notifications]
enabled = ["discord"]

[notifications.discord]
webhook_url = "https://discord.com/api/webhooks/..."
```

## 3-1. OpenAI LLM 연동

알림 문구를 더 자연스러운 한국어 분석 리포트처럼 만들고 싶다면 OpenAI API를 붙일 수 있습니다.

중요:

- ChatGPT Plus/Pro와 API 과금은 별도입니다.
- API 키는 `platform.openai.com`에서 만들어 환경변수로 넣어야 합니다.

PowerShell:

```powershell
$env:OPENAI_API_KEY="sk-..."
python -m circle_monitor.cli --config config.toml --once
```

`config.toml`의 `[llm]` 섹션에서 모델을 바꿀 수 있습니다.

## 4. 실행 방법

한 번만 실행:

```bash
python -m circle_monitor.cli --config config.toml --once
```

상시 실행:

```bash
python -m circle_monitor.cli --config config.toml
```

첫 실행에서는 과거 이벤트를 알리지 않고 DB에만 기준선으로 저장합니다. 이후에는 `alert_recency_hours` 안에서 발생한 이벤트만 알림 대상으로 봅니다.

## 5. Google Cloud VM 배포

Ubuntu 24.04 기준입니다.

### 패키지 설치

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

### 코드 배치

```bash
git clone <your-repo-url> circle-monitor
cd circle-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e '.[dev]'
cp config.example.toml config.toml
mkdir -p data logs
```

`config.toml`에 웹훅/토큰을 설정한 뒤 시험 실행합니다.

```bash
python -m circle_monitor.cli --config config.toml --once
```

### systemd 등록

`/etc/systemd/system/circle-monitor.service`

```ini
[Unit]
Description=Circle Monitoring Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/circle-monitor
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/ubuntu/circle-monitor/.venv/bin/python -m circle_monitor.cli --config /home/ubuntu/circle-monitor/config.toml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

적용:

```bash
sudo systemctl daemon-reload
sudo systemctl enable circle-monitor
sudo systemctl start circle-monitor
sudo systemctl status circle-monitor
journalctl -u circle-monitor -f
```

### PM2 대안

```bash
sudo npm install -g pm2
pm2 start "/home/ubuntu/circle-monitor/.venv/bin/python -m circle_monitor.cli --config /home/ubuntu/circle-monitor/config.toml" --name circle-monitor
pm2 save
pm2 startup
```

## 6. 테스트

```bash
pytest
```

### 수동 테스트 체크리스트

1. `--once`로 실행해 초기 부트스트랩이 과거 기사 대량 발송 없이 끝나는지 확인
2. 같은 기사 URL/유사 제목을 다시 입력했을 때 중복으로 걸러지는지 확인
3. 같은 사건이지만 새로운 수치/문서 번호가 추가되면 신규로 통과하는지 확인
4. Telegram/Discord/Slack 설정 후 실제 알림이 전송되는지 확인

## 7. 운영 팁

- RSS만으로 부족하면 `[[sources]]`에 웹페이지 수집 대상을 추가합니다.
- SEC EDGAR처럼 HTML 구조가 복잡한 소스는 추후 전용 소스 클래스를 추가하는 방식으로 확장하면 됩니다.
- LLM 기반 요약을 붙이고 싶다면 `analysis.py` 내부의 `EventAnalyzer`를 확장해 요약 단계만 교체하면 됩니다.
