"""M2.1 只读接口契约：调用真实接口，锁结构与类型，不锁文案。"""

import json

import pytest

from utils.assertions import assert_ok


def _number(value, field):
    assert isinstance(value, (int, float)) and not isinstance(value, bool), f"{field} 不是数字: {value!r}"


def test_supplier_select_returns_raw_array(client):
    resp = client.post("/supplier/findBySelect_sup", json={"key": "", "limit": 10})
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert isinstance(body, list), f"供应商下拉应返回原始数组，实际 {type(body).__name__}: {body}"
    assert body, "供应商下拉为空"
    assert {"id", "supplier"} <= set(body[0]), f"供应商字段不符: {sorted(body[0])}"


def test_depot_list(client):
    depots = assert_ok(client.get("/depot/getAllList"))
    assert isinstance(depots, list), f"仓库列表结构不符: {depots}"
    depot = depots[0]
    assert depot.get("id") is not None, f"仓库缺少 id: {depot}"
    assert depot.get("name"), f"仓库缺少 name: {depot}"


def test_account_list(client):
    data = assert_ok(client.get("/account/getAccount"))
    assert isinstance(data, dict), f"账户结构不符: {data}"
    accounts = data.get("accountList")
    assert isinstance(accounts, list), f"accountList 不是数组: {data}"
    account = accounts[0]
    assert account.get("id") is not None, f"账户缺少 id: {account}"
    assert account.get("name"), f"账户缺少 name: {account}"
    _number(account.get("currentAmount"), "account.currentAmount")


def test_material_by_barcode(client, demo_data):
    materials = assert_ok(
        client.get(
            "/material/getMaterialByBarCode",
            params={"barCode": demo_data["bar_code"], "mpList": "", "depotId": demo_data["depot"]["id"]},
        )
    )
    assert isinstance(materials, list), f"商品结构不符: {materials}"
    material = materials[0]
    assert material.get("mBarCode") == demo_data["bar_code"], f"条码不一致: {material.get('mBarCode')}"
    assert material.get("id") is not None, f"商品缺少 id: {material}"
    assert material.get("name"), f"商品缺少 name: {material}"
    for field in ("stock", "billPrice", "taxRate"):
        assert field in material, f"商品缺少 {field}: {sorted(material)}"
    _number(material.get("stock"), "material.stock")
    _number(material.get("taxRate"), "material.taxRate")


def test_depot_head_list(client):
    # subType 必传：不传会在 getBillCategory 抛 NPE，返回 code=300 数据查询异常
    search = json.dumps({"type": "入库", "subType": "采购"}, ensure_ascii=False)
    data = assert_ok(client.get("/depotHead/list", params={"search": search, "currentPage": 1, "pageSize": 3}))
    assert isinstance(data, dict), f"单据列表结构不符: {data}"
    rows, total = data.get("rows"), data.get("total")
    assert isinstance(rows, list), f"rows 不是数组: {data}"
    assert isinstance(total, int), f"total 不是整数: {total!r}"
    assert total >= len(rows), f"total({total}) 小于当前页条数({len(rows)})"
    assert len(rows) <= 3, f"pageSize=3 未生效，返回 {len(rows)} 条"
    if rows:
        assert rows[0].get("number"), f"单据缺少 number: {rows[0]}"
        assert rows[0].get("id") is not None, f"单据缺少 id: {rows[0]}"


def test_depot_head_detail_by_number(client, demo_data):
    data = assert_ok(
        client.get("/depotHead/getDetailByNumber", params={"number": demo_data["header"]["number"]})
    )
    assert isinstance(data, dict), f"单据主表结构不符: {data}"
    assert data.get("number") == demo_data["header"]["number"], f"单号不一致: {data.get('number')}"
    assert data.get("id") == demo_data["header"]["id"], f"id 不一致: {data.get('id')}"


def test_stock_by_depot_and_barcode(client, demo_data):
    data = assert_ok(
        client.get(
            "/depotItem/findStockByDepotAndBarCode",
            params={"depotId": demo_data["depot"]["id"], "barCode": demo_data["bar_code"]},
        )
    )
    assert isinstance(data, dict), f"库存结构不符: {data}"
    _number(data.get("stock"), "stock")


# 以下 6 条只校准外层结构，字段细节后续阶段再收紧


def test_calibrate_depot_head_info(client, demo_data):
    data = assert_ok(client.get("/depotHead/info", params={"id": demo_data["header"]["id"]}))
    assert isinstance(data, dict), f"info 结构不符: {data}"
    assert isinstance(data.get("info"), dict), f"info 字段不是对象: {data}"


def test_calibrate_depot_item_detail_list(client, demo_data):
    data = assert_ok(client.get("/depotItem/getDetailList", params={"headerId": demo_data["header"]["id"]}))
    assert isinstance(data, dict), f"明细结构不符: {data}"
    assert isinstance(data.get("rows"), list), f"rows 不是数组: {data}"
    assert isinstance(data.get("total"), int), f"total 不是整数: {data}"


def test_calibrate_in_out_stock(client):
    params = {
        "currentPage": 1,
        "pageSize": 5,
        "beginTime": "2026-01-01",
        "endTime": "2026-12-31",
        "materialParam": "",
    }
    data = assert_ok(client.get("/depotItem/getInOutStock", params=params))
    assert isinstance(data, dict), f"进销存结构不符: {data}"
    assert isinstance(data.get("rows"), list), f"rows 不是数组: {data}"
    assert isinstance(data.get("total"), int), f"total 不是整数: {data}"


def test_calibrate_serial_number_list(client):
    data = assert_ok(client.post("/serialNumber/getEnableSerialNumberList", json={"page": 1, "rows": 5}))
    assert isinstance(data, dict), f"序列号结构不符: {data}"
    assert isinstance(data.get("rows"), list), f"rows 不是数组: {data}"
    assert isinstance(data.get("total"), int), f"total 不是整数: {data}"


def test_calibrate_bill_list_by_link_number(client, demo_data):
    resp = client.get("/depotHead/getBillListByLinkNumber", params={"number": demo_data["header"]["number"]})
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body.get("code") == 200, f"业务失败: {body}"
    assert isinstance(body.get("data"), list), f"关联单据应为数组: {body.get('data')}"


def test_calibrate_system_config(client):
    data = assert_ok(client.get("/systemConfig/getCurrentInfo"))
    assert isinstance(data, dict), f"系统配置结构不符: {data}"
    assert "companyName" in data, f"系统配置缺少 companyName: {sorted(data)}"
