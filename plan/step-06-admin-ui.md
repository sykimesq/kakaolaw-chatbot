# Step 06: 관리자 웹 화면 (HTML)

## 목표
사무소에서 예약을 보고 [확정]/[불가] 버튼을 누르는 간단한 관리자 웹 페이지를 생성한다.

## 사전 조건
- [ ] Step 05 완료 (관리자 API 존재)

## 변경할 파일
- 생성: `app/static/admin.html`
- 수정: `app/main.py` (정적 파일 서빙 + admin 페이지 라우트)

## 구현 내용

### 1. `app/static/admin.html`

간단한 HTML + fetch로 관리자 API 호출. 모바일/PC 브라우저 모두 동작.

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>법률사무소 관리자</title>
  <style>
    body { font-family: sans-serif; max-width: 700px; margin: 0 auto; padding: 16px; }
    .card { border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-bottom: 12px; }
    .badge-new { color: #d00; font-weight: bold; }
    button { margin: 4px; padding: 6px 12px; border: none; border-radius: 6px; cursor: pointer; }
    .ok { background: #4caf50; color: white; }
    .no { background: #f44336; color: white; }
  </style>
</head>
<body>
  <h2>📋 예약 신청 목록</h2>
  <div id="reservations"></div>
  <h2>📋 상담 질의 접수</h2>
  <div id="inquiries"></div>

  <script>
    async function load() {
      const [res, inq] = await Promise.all([
        fetch('/admin/reservations').then(r => r.json()),
        fetch('/admin/inquiries').then(r => r.json()),
      ]);
      const rEl = document.getElementById('reservations');
      rEl.innerHTML = res.map(r => `
        <div class="card">
          <span class="badge-new">[${r.status}]</span> ${r.name} ${r.phone}<br>
          ${r.field} · ${r.desired_dt}<br>
          <button class="ok" onclick="act(${r.id},'confirm')">확정</button>
          <button class="no" onclick="act(${r.id},'reject')">불가</button>
        </div>`).join('') || '예약 없음';
      const iEl = document.getElementById('inquiries');
      iEl.innerHTML = inq.map(i => `
        <div class="card">
          <span class="badge-new">[${i.status}]</span> ${i.name || '이름없음'} ${i.phone}<br>
          분야: ${i.field || '미정'} · 입장: ${i.position || '미정'}<br>
          ${i.summary || ''}
        </div>`).join('') || '질의 없음';
    }
    async function act(id, action) {
      await fetch(`/admin/reservations/${id}/${action}`, { method: 'POST' });
      load();
    }
    load();
  </script>
</body>
</html>
```

### 2. `app/main.py` — admin 페이지 라우트 + static

```python
from pathlib import Path
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# ... (기존 라우터 등록 후)
STATIC_DIR = Path(__file__).parent / "static"

@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return (STATIC_DIR / "admin.html").read_text(encoding="utf-8")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
```

## 검증
```bash
python -c "from app.main import app; print('OK')"
# 수동 확인: uvicorn app.main:app 실행 후 /admin 접속
uvicorn app.main:app --reload
```

## 완료 조건
- [ ] /admin 페이지 HTML 로드
- [ ] 예약 목록 fetch 동작
- [ ] 확정/불가 버튼 API 호출 동작
