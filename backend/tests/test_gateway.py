from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_nginx_strips_api_prefix():
    conf = (ROOT / "deployment" / "nginx" / "nginx.conf").read_text()
    assert "location /api/" in conf
    assert "proxy_pass http://backend_api/;" in conf
    assert "location /" in conf
    assert "proxy_pass http://frontend_ui;" in conf


def test_compose_single_host_port():
    compose = (ROOT / "deployment" / "docker-compose.yml").read_text()
    assert "PANEL_PORT" in compose
    assert "PANEL_API_HOST_PORT" not in compose
    assert "PANEL_WEB_HOST_PORT" not in compose
    assert "PANEL_WORKER_HOST_PORT" not in compose
    assert "${PANEL_PORT:-8056}:80" in compose
