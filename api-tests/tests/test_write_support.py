import types

import pytest

import client as client_module
import utils.data as data


class _Resp:
    status_code = 200
    text = '{"code":200}'

    def json(self):
        return {"code": 200}


class _Session:
    def __init__(self):
        self.sent = []

    def request(self, method, url, **kwargs):
        self.sent.append((method, url))
        return _Resp()


class _Client:
    def __init__(self):
        self.settings = object()
        self.logged_in = False

    def login(self):
        self.logged_in = True


def _patch_queries(monkeypatch, find_bills, find_details):
    monkeypatch.setattr(data, "find_bills", find_bills)
    monkeypatch.setattr(data, "find_bill_details", find_details)


def test_write_requests_are_spaced(monkeypatch):
    clock = [0.0]
    slept = []

    def fake_sleep(seconds):
        slept.append(seconds)
        clock[0] += seconds

    fake_time = types.SimpleNamespace(monotonic=lambda: clock[0], sleep=fake_sleep)
    monkeypatch.setattr(client_module, "time", fake_time)
    client_module.ErpClient._last_write_at = None

    c = client_module.ErpClient(
        types.SimpleNamespace(base_url="http://stub", timeout=1), allow_write=True
    )
    c.session = _Session()
    try:
        c.request("POST", "/depotHead/addDepotHeadAndDetail", json={})
        assert slept == []
        c.request("POST", "/depotHead/batchSetStatus", json={})
        assert len(slept) == 1
        assert slept[0] == pytest.approx(client_module.WRITE_INTERVAL_SECONDS)
        count = len(slept)
        c.request("GET", "/depotHead/list")
        c.request("GET", "/user/logout")
        assert len(slept) == count
    finally:
        client_module.ErpClient.instances.remove(c)
        client_module.ErpClient._last_write_at = None


def test_write_interval_is_shared_across_clients(monkeypatch):
    clock = [0.0]
    slept = []

    def fake_sleep(seconds):
        slept.append(seconds)
        clock[0] += seconds

    fake_time = types.SimpleNamespace(monotonic=lambda: clock[0], sleep=fake_sleep)
    monkeypatch.setattr(client_module, "time", fake_time)
    client_module.ErpClient._last_write_at = None

    settings = types.SimpleNamespace(base_url="http://stub", timeout=1)
    first = client_module.ErpClient(settings, allow_write=True)
    second = client_module.ErpClient(settings, allow_write=True)
    first.session = _Session()
    second.session = _Session()
    try:
        first.request("POST", "/depotHead/addDepotHeadAndDetail", json={})
        second.request("POST", "/depotHead/batchSetStatus", json={})
        assert len(slept) == 1
        assert slept[0] == pytest.approx(client_module.WRITE_INTERVAL_SECONDS)
    finally:
        for c in (first, second):
            client_module.ErpClient.instances.remove(c)
        client_module.ErpClient._last_write_at = None


def test_login_out_uses_fresh_session(monkeypatch):
    original = _Client()
    fresh = _Client()

    def find_bills(client, number):
        if client is original:
            raise AssertionError("单号 API-X 查询失败 HTTP 500: loginOut")
        return []

    _patch_queries(monkeypatch, find_bills, lambda client, header_id: [])
    monkeypatch.setattr(data, "ErpClient", lambda settings: fresh)

    assert data._verify_deleted(original, "API-X", 1) == ([], [], True)
    assert fresh.logged_in


def test_fresh_session_failure_is_not_cleanup_success(monkeypatch):
    original = _Client()
    fresh = _Client()

    def find_bills(client, number):
        if client is original:
            raise AssertionError("单号 API-X 查询失败 HTTP 500: loginOut")
        raise AssertionError("独立会话查询失败 HTTP 500")

    _patch_queries(monkeypatch, find_bills, lambda client, header_id: [])
    monkeypatch.setattr(data, "ErpClient", lambda settings: fresh)

    with pytest.raises(AssertionError) as excinfo:
        data._verify_deleted(original, "API-X", 1)
    message = str(excinfo.value)
    assert "需人工核查" in message
    assert "loginOut" in message


def test_detail_residue_fails_cleanup(monkeypatch):
    bill = {"id": 7, "number": "API-X", "status": "0", "purchaseStatus": "0"}
    calls = {"count": 0}

    def find_bills(client, number):
        calls["count"] += 1
        return [bill] if calls["count"] == 1 else []

    _patch_queries(monkeypatch, find_bills, lambda client, header_id: [{"id": 9}])
    monkeypatch.setattr(data, "_request", lambda *args, **kwargs: _Resp())
    monkeypatch.setattr(data, "_json", lambda resp, context: {"code": 200})

    with pytest.raises(AssertionError, match="明细仍存在"):
        data.cleanup_bill(_Client(), "API-X")


def test_no_fresh_session_when_original_is_healthy(monkeypatch):
    def fail_if_created(settings):
        raise AssertionError("原会话正常时不应创建独立会话")

    _patch_queries(monkeypatch, lambda client, number: [], lambda client, header_id: [])
    monkeypatch.setattr(data, "ErpClient", fail_if_created)

    assert data._verify_deleted(_Client(), "API-X", 1) == ([], [], False)
