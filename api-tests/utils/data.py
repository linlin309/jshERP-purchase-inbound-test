import json
import uuid
from datetime import date
from decimal import Decimal

import requests

from client import ErpClient
from utils.assertions import assert_ok

BILL_TYPE = "入库"
SUB_TYPE = "采购"
QUANTITY = 5


def unique_number():
    return f"API-{date.today():%Y%m%d}-{uuid.uuid4().hex[:6]}"


def build_purchase_inbound(demo_data, number, quantity=QUANTITY):
    """返回 (请求体, 用例元数据)；单价取商品现价，避免顺手改掉演示资料。"""
    material = demo_data["material"]
    price = material.get("purchaseDecimal")
    if not price or float(price) <= 0:
        price = 1
    price = Decimal(str(price))
    amount = price * quantity
    info = {
        "number": number,
        "type": BILL_TYPE,
        "subType": SUB_TYPE,
        "operTime": date.today().isoformat(),
        "organId": demo_data["supplier"]["id"],
        "accountId": demo_data["account"]["id"],
        "accountIdList": "",
        "payType": "现付",
        "discountLastMoney": float(amount),
        "totalPrice": -float(amount),
        "changeAmount": -float(amount),
        "debt": 0,
        "deposit": 0,
        "remark": "API 自动化测试",
    }
    rows = [{
        "barCode": demo_data["bar_code"],
        "unit": material["unit"],
        "depotId": demo_data["depot"]["id"],
        "operNumber": quantity,
        "basicNumber": quantity,
        "unitPrice": float(price),
        "allPrice": float(amount),
        "taxRate": 0,
        "taxMoney": 0,
        "taxLastMoney": float(amount),
    }]
    body = {
        "info": json.dumps(info, ensure_ascii=False),
        "rows": json.dumps(rows, ensure_ascii=False),
    }
    meta = {
        "number": number,
        "quantity": quantity,
        "bar_code": demo_data["bar_code"],
        "depot_id": demo_data["depot"]["id"],
    }
    return body, meta


def _request(client, method, path, context, **kwargs):
    try:
        return client.request(method, path, **kwargs)
    except requests.RequestException as exc:
        raise AssertionError(
            f"{context}：请求 {method} {path} 异常 {type(exc).__name__}: {exc}"
        ) from exc


def _json(resp, context):
    try:
        return resp.json()
    except ValueError as exc:
        raise AssertionError(
            f"{context}：响应不是 JSON，HTTP {resp.status_code}，正文 {resp.text[:300]}"
        ) from exc


def find_bills(client, number):
    """按单号查列表并做精确过滤。查询本身失败会抛错，调用方不能当成“单据不存在”。"""
    search = json.dumps(
        {"type": BILL_TYPE, "subType": SUB_TYPE, "number": number}, ensure_ascii=False
    )
    context = f"单号 {number} 查询失败"
    resp = _request(
        client,
        "GET",
        "/depotHead/list",
        context,
        params={"search": search, "currentPage": 1, "pageSize": 50},
    )
    assert resp.status_code == 200, f"{context} HTTP {resp.status_code}: {resp.text[:300]}"
    body = _json(resp, context)
    assert body.get("code") == 200, f"{context}: {body}"
    data = body.get("data")
    rows = data.get("rows") if isinstance(data, dict) else None
    assert isinstance(rows, list), f"单号 {number} 查询结构不符: {data}"
    return [row for row in rows if row.get("number") == number]


def find_bill_details(client, header_id):
    """按 headerId 查明细；删除后应为空。查询失败会抛错，不能当成“明细不存在”。"""
    context = f"单据 {header_id} 明细查询失败"
    resp = _request(
        client, "GET", "/depotItem/getDetailList", context, params={"headerId": header_id}
    )
    assert resp.status_code == 200, f"{context} HTTP {resp.status_code}: {resp.text[:300]}"
    body = _json(resp, context)
    assert body.get("code") == 200, f"{context}: {body}"
    data = body.get("data")
    rows = data.get("rows") if isinstance(data, dict) else None
    assert isinstance(rows, list), f"单据 {header_id} 明细结构不符: {data}"
    return rows


def read_stock(client, depot_id, bar_code):
    data = assert_ok(
        client.get(
            "/depotItem/findStockByDepotAndBarCode",
            params={"depotId": depot_id, "barCode": bar_code},
        )
    )
    return Decimal(str(data["stock"]))


def read_flags(client):
    data = assert_ok(client.get("/systemConfig/getCurrentInfo"))
    return {key: data.get(key) for key in ("forceApprovalFlag", "updateUnitPriceFlag")}


def _verify_deleted(client, number, bill_id):
    """删除后复查主表和明细；原会话 loginOut 时换独立只读会话再查。"""
    try:
        return find_bills(client, number), find_bill_details(client, bill_id), False
    except AssertionError as exc:
        if "loginOut" not in str(exc):
            raise
        original = exc
    try:
        fresh = ErpClient(client.settings)
        fresh.login()
        return find_bills(fresh, number), find_bill_details(fresh, bill_id), True
    except Exception as exc:
        raise AssertionError(
            f"清理失败：单号 {number} 删除后原会话失效，独立会话复查失败，需人工核查。"
            f"单据 id {bill_id}；原会话错误 {type(original).__name__}: {original}；"
            f"独立会话错误 {type(exc).__name__}: {exc}"
        ) from original


def cleanup_bill(client, number):
    """按实际状态清理：查询失败或状态不明都算清理失败，保留单号与响应。"""
    found = find_bills(client, number)
    if not found:
        return
    assert len(found) == 1, f"清理失败：单号 {number} 查到 {len(found)} 条单据"
    bill = found[0]
    if bill.get("status") == "1":
        context = f"清理失败：单号 {number} 反审核"
        resp = _request(
            client, "POST", "/depotHead/batchSetStatus", context,
            json={"status": "0", "ids": str(bill["id"])},
        )
        ok = resp.status_code == 200 and _json(resp, context).get("code") == 200
        assert ok, f"{context}异常 HTTP {resp.status_code}: {resp.text[:300]}"
        found = find_bills(client, number)
        assert found and found[0].get("status") == "0", f"清理失败：单号 {number} 反审核后状态未回到未审核"
        bill = found[0]
    assert bill.get("status") == "0", (
        f"清理失败：单号 {number} 状态 {bill.get('status')} / 采购状态 {bill.get('purchaseStatus')}，"
        f"需人工反审核后再删除"
    )
    context = f"清理失败：单号 {number} 删除"
    resp = _request(client, "DELETE", "/depotHead/delete", context, params={"id": bill["id"]})
    ok = resp.status_code == 200 and _json(resp, context).get("code") == 200
    assert ok, f"{context}异常 HTTP {resp.status_code}: {resp.text[:300]}"
    remaining, details, fresh_used = _verify_deleted(client, number, bill["id"])
    suffix = "（独立会话复查）" if fresh_used else ""
    assert not remaining, f"清理失败{suffix}：单号 {number} 删除后仍能查到"
    assert not details, f"清理失败{suffix}：单号 {number} 删除后明细仍存在: {details}"
