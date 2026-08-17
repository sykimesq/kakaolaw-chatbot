"""관리자 페이지 인증(HTTP Basic Auth) 테스트.

기본(인증 미설정) 상태에서는 /admin 페이지·API가 인증 없이 동작하고,
ADMIN_USERNAME/ADMIN_PASSWORD가 설정되면 401로 보호된다.
"""
import base64

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _basic(user: str, pw: str) -> dict:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_admin_open_when_auth_unset():
    """인증 미설정(기본값)이면 /admin 페이지와 API가 열려 있다."""
    assert not (settings.admin_username and settings.admin_password)
    with TestClient(app) as c:
        assert c.get("/admin").status_code == 200
        assert c.get("/admin/inquiries").status_code == 200


def test_admin_requires_auth_when_set(monkeypatch):
    """인증 설정 시 자격증명 없이는 401, 올바른 자격증명이면 200."""
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "secret")
    with TestClient(app) as c:
        # 자격증명 없음 → 401 + WWW-Authenticate 헤더
        r = c.get("/admin")
        assert r.status_code == 401
        assert r.headers.get("WWW-Authenticate", "").startswith("Basic")
        # API도 동일하게 보호
        assert c.get("/admin/inquiries").status_code == 401
        # 잘못된 자격증명 → 401
        assert c.get("/admin", headers=_basic("admin", "wrong")).status_code == 401
        # 올바른 자격증명 → 200
        assert c.get("/admin", headers=_basic("admin", "secret")).status_code == 200
        assert (
            c.get("/admin/inquiries", headers=_basic("admin", "secret")).status_code
            == 200
        )
