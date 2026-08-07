#!/bin/bash
# GCP e2-micro 1-shot 설치 스크립트 — 카카오톡 법률사무소 챗봇
# 사용법: VM에서 이 스크립트를 실행 (처음 한 번만)
# 이후 업데이트는 3줄만:
#   cd ~/kakaolaw && git pull origin main && sudo systemctl restart kakaolaw

set -e

# ── sudo 가용성 자동 감지 ──────────────────────────────
SUDO=""
if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    SUDO="sudo"
else
    echo "⚠️  sudo 권한이 없습니다. root로 실행하거나, sudo 권한을 받으세요."
    exit 1
fi

echo "▶ apt update + 필수 패키지 설치"
$SUDO apt update
$SUDO apt install -y git python3-venv python3-dev build-essential

echo "▶ 코드 clone (없으면)"
if [ ! -d ~/kakaolaw ]; then
    git clone https://github.com/YOUR_GITHUB_USER/kakaolaw-chatbot.git ~/kakaolaw
fi
cd ~/kakaolaw

echo "▶ Python venv + 의존성 설치"
if [ ! -d venv ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "▶ .env 확인 (OPENROUTER_API_KEY 등)"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  .env 파일을 생성했습니다. 반드시 편집해서 OPENROUTER_API_KEY를 설정하세요."
    echo "    nano ~/kakaolaw/.env"
fi

echo "▶ systemd 서비스 등록"
$SUDO tee /etc/systemd/system/kakaolaw.service > /dev/null <<'EOF'
[Unit]
Description=Kakao Law Chatbot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/kakaolaw
Environment="PATH=/home/ubuntu/kakaolaw/venv/bin"
ExecStart=/home/ubuntu/kakaolaw/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/kakaolaw/logs/stdout.log
StandardError=append:/home/ubuntu/kakaolaw/logs/stderr.log

[Install]
WantedBy=multi-user.target
EOF

echo "▶ 로그 디렉토리 생성"
mkdir -p ~/kakaolaw/logs

echo "▶ systemd 활성화 + 시작"
$SUDO systemctl daemon-reload
$SUDO systemctl enable kakaolaw
$SUDO systemctl start kakaolaw

echo "✅ 설치 완료. 상태 확인:"
$SUDO systemctl status kakaolaw --no-pager | head -10

echo ""
echo "⚠️  .env에 OPENROUTER_API_KEY가 설정돼 있지 않으면 되묻기가 동작하지 않습니다."
echo "    편집: nano ~/kakaolaw/.env  → 저장 Ctrl+O → 종료 Ctrl+X"
echo "    재시작: sudo systemctl restart kakaolaw"
