def test_nonexistent_number_returns_error(client):
    number = "API-NOT-EXIST-0000"
    resp = client.get("/depotHead/getDetailByNumber", params={"number": number})
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body.get("code") != 200, f"不存在的单号不应返回成功: {body}"
    data = body.get("data")
    assert not (isinstance(data, dict) and data.get("number") == number), f"返回了单据: {data}"
