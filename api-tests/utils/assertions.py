def assert_ok(resp):
    body = resp.json()
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {body}"
    assert body.get("code") == 200, f"业务失败: {body}"
    assert body.get("data") is not None, f"响应 data 为空: {body}"
    return body["data"]
