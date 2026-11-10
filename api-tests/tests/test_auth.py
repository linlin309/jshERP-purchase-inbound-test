import hashlib

import allure

from client import ErpClient
from utils.assertions import assert_ok

SUITE = "鉴权与会话"


@allure.suite(SUITE)
@allure.title("A01 登录成功返回 token 与用户信息")
@allure.severity(allure.severity_level.CRITICAL)
def test_login_returns_token(settings):
    body = ErpClient(settings).login()
    data = body.get("data") or {}
    assert body.get("code") == 200, f"登录业务码不符: {body}"
    assert data.get("msgTip") == "user can login", f"登录提示不符: {data}"
    assert data.get("token"), f"登录未返回 token: {data}"
    assert (data.get("user") or {}).get("loginName") == settings.login_name, (
        f"登录用户不符: {data.get('user')}"
    )


@allure.suite(SUITE)
@allure.title("A02 错误密码不返回 token")
@allure.severity(allure.severity_level.CRITICAL)
def test_wrong_password_returns_no_token(settings):
    # 登录接口会先删掉请求头 token 的 userId，必须用不带 token 的 client，否则会踢掉共享会话
    anonymous = ErpClient(settings)
    resp = anonymous.post(
        "/user/login",
        json={
            "loginName": settings.login_name,
            "password": hashlib.md5(b"m2-wrong-password").hexdigest(),
            "code": "",
            "uuid": "",
        },
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body.get("code") == 200, f"登录失败也应返回 code=200: {body}"
    data = body.get("data") or {}
    assert not data.get("token"), f"错误密码不应返回 token: {data}"
    assert data.get("msgTip"), f"错误密码缺少提示: {data}"


@allure.suite(SUITE)
@allure.title("A03 无 token 的受保护接口被拒绝")
@allure.severity(allure.severity_level.CRITICAL)
def test_request_without_token_is_rejected(client):
    resp = client.get("/user/getUserSession", headers={"X-Access-Token": None})
    assert "X-Access-Token" not in resp.request.headers, "请求仍带 token，用例前提不成立"
    assert resp.status_code == 500, f"HTTP {resp.status_code}: {resp.text[:200]}"
    assert "loginOut" in resp.text, f"响应不是 loginOut: {resp.text[:200]}"


@allure.suite(SUITE)
@allure.title("A04 无效 token 的受保护接口被拒绝")
@allure.severity(allure.severity_level.CRITICAL)
def test_request_with_invalid_token_is_rejected(client):
    resp = client.get("/user/getUserSession", headers={"X-Access-Token": "invalid-token-for-test"})
    assert resp.status_code == 500, f"HTTP {resp.status_code}: {resp.text[:200]}"
    assert "loginOut" in resp.text, f"响应不是 loginOut: {resp.text[:200]}"


@allure.suite(SUITE)
@allure.title("A05 退出登录后同一 token 失效")
@allure.severity(allure.severity_level.CRITICAL)
def test_logout_invalidates_token(settings, client):
    with allure.step("独立 client 登录"):
        secondary = ErpClient(settings)
        secondary.login()

    with allure.step("退出前会话有效"):
        assert_ok(secondary.get("/user/getUserSession"))

    with allure.step("调用退出接口"):
        logout = secondary.get("/user/logout")
        assert logout.status_code == 200, f"退出失败: HTTP {logout.status_code} {logout.text[:200]}"

    with allure.step("原 token 再次取会话被拒绝"):
        after = secondary.get("/user/getUserSession")
        assert after.status_code == 500, f"退出后仍可访问: HTTP {after.status_code} {after.text[:200]}"
        assert "loginOut" in after.text, f"退出后响应不是 loginOut: {after.text[:200]}"

    with allure.step("共享 client 会话不受影响"):
        assert_ok(client.get("/user/getUserSession"))
