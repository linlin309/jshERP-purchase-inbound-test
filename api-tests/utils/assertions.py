def _json_body(resp):
    try:
        return resp.json()
    except ValueError:
        return None


def assert_ok(resp):
    body = _json_body(resp)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    assert isinstance(body, dict), f"响应不是 JSON 对象: HTTP {resp.status_code} {resp.text[:200]}"
    assert body.get("code") == 200, f"业务失败: {body}"
    return body.get("data")


def assert_business_error(resp, code=None):
    body = _json_body(resp)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    assert isinstance(body, dict), f"响应不是 JSON 对象: HTTP {resp.status_code} {resp.text[:200]}"
    assert body.get("code") != 200, f"预期业务失败，实际成功: {body}"
    if code is not None:
        assert body.get("code") == code, f"业务码不符: {body}"
    return body
