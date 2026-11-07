from __future__ import annotations

import asyncio

import pytest
import respx
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Settings


@pytest.mark.parametrize('value, enabled', [(None, True), ('true', True), ('false', False)])
def test_vless_environment_defaults_to_enabled(monkeypatch, value, enabled):
    monkeypatch.setenv('VPN_AGENT_TOKEN', 'token')
    monkeypatch.setenv('VPN_BACKEND_URL', 'https://backend.example.test')
    monkeypatch.setenv('XRAY_VLESS_INBOUND_TAG', 'vless-reality')
    monkeypatch.delenv('VPN_VLESS_ENABLED', raising=False)
    if value is not None:
        monkeypatch.setenv('VPN_VLESS_ENABLED', value)
    assert Settings.from_environment().vless_enabled is enabled


def test_hysteria_only_bootstrap_management_auth_and_health_without_xray(monkeypatch):
    def unexpected_xray(**kwargs):
        pytest.fail('Hysteria-only nodes must not create an Xray client')

    monkeypatch.setattr('src.app.create_xray_client', unexpected_xray)
    app = create_app(settings=Settings(
        agent_token='token', backend_url='https://backend.example.test', vless_enabled=False,
    ))
    body = {'vless_uuid': '11111111-1111-1111-1111-111111111111', 'hysteria_secret': 'first'}
    with respx.mock:
        respx.get('https://backend.example.test/api/v1/vpn/agent/profiles/').respond(
            200, json=[{'access_id': 7, **body}],
        )
        client = TestClient(app)
        asyncio.run(app.state.bootstrap_service())
        assert client.get('/health').json() == {'status': 'ok'}
        assert client.post('/auth', json={'auth': 'first', 'addr': '192.0.2.1:443', 'tx': 0}).json() == {'ok': True, 'id': '7'}
        headers = {'Authorization': 'Bearer token'}
        assert client.put('/api/v1/profiles/7', headers=headers,
                          json={**body, 'hysteria_secret': 'second'}).status_code == 200
        assert client.post('/auth', json={'auth': 'second', 'addr': '192.0.2.1:443', 'tx': 0}).json() == {'ok': True, 'id': '7'}
        assert client.post('/auth', json={'auth': 'first', 'addr': '192.0.2.1:443', 'tx': 0}).json()['ok'] is False
        assert client.delete('/api/v1/profiles/7', headers=headers).status_code == 204
        assert client.delete('/api/v1/profiles/7', headers=headers).status_code == 204
        assert client.post('/auth', json={'auth': 'second', 'addr': '192.0.2.1:443', 'tx': 0}).json()['ok'] is False
        client.close()


def test_hysteria_only_still_requires_bootstrap():
    app = create_app(settings=Settings(agent_token='token', vless_enabled=False))
    with TestClient(app) as client:
        assert client.get('/health').status_code == 503
