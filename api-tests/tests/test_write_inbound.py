import json
from datetime import date
from decimal import Decimal

import allure
import pytest

from utils.assertions import assert_business_error, assert_ok
from utils.data import build_purchase_inbound, cleanup_bill, find_bills, read_stock, unique_number

pytestmark = pytest.mark.write
SUITE = "采购入库写流程"


def _bill(client, number):
    found = find_bills(client, number)
    assert len(found) == 1, f"单号 {number} 查到 {len(found)} 条单据: {found}"
    return found[0]


@allure.suite(SUITE)
@allure.title("W01 新增采购入库单（默认未审核）")
@allure.severity(allure.severity_level.CRITICAL)
def test_add_purchase_inbound(created_bill, write_client, demo_data):
    number = created_bill["number"]
    with allure.step("按单号查询单据"):
        bill = _bill(write_client, number)
    assert bill["type"] == "入库" and bill["subType"] == "采购", f"单据类型不符: {bill}"
    assert bill["status"] == "0", f"新增默认状态应为未审核，实际 {bill['status']}"
    assert bill["purchaseStatus"] == "0", f"采购状态应为未开始，实际 {bill['purchaseStatus']}"

    with allure.step("核对主表字段"):
        info = assert_ok(write_client.get("/depotHead/info", params={"id": bill["id"]}))["info"]
    assert info["number"] == number
    assert info["operTime"][:10] == date.today().isoformat(), f"业务日期不符: {info['operTime']}"
    assert info["organId"] == demo_data["supplier"]["id"], f"供应商不符: {info['organId']}"
    assert info["accountId"] == demo_data["account"]["id"], f"结算账户不符: {info['accountId']}"

    with allure.step("核对明细字段"):
        items = assert_ok(write_client.get("/depotItem/getDetailList", params={"headerId": bill["id"]}))
        rows = items["rows"]
    assert len(rows) == 1, f"明细行数不符: {rows}"
    assert rows[0]["barCode"] == created_bill["bar_code"], f"条码不符: {rows[0]}"
    assert rows[0]["depotId"] == created_bill["depot_id"], f"仓库不符: {rows[0]}"
    assert Decimal(str(rows[0]["operNumber"])) == created_bill["quantity"], f"数量不符: {rows[0]}"
    assert Decimal(str(rows[0]["basicNumber"])) == created_bill["quantity"], f"基本数量不符: {rows[0]}"


@allure.suite(SUITE)
@allure.title("W02 新增被拒且无业务残留")
@allure.severity(allure.severity_level.NORMAL)
def test_add_failure_leaves_no_bill(write_client, demo_data):
    number = unique_number()
    body, _ = build_purchase_inbound(demo_data, number)
    info = json.loads(body["info"])
    info.pop("accountId")
    body["info"] = json.dumps(info, ensure_ascii=False)
    try:
        with allure.step("缺少结算账户被拒"):
            resp = write_client.post("/depotHead/addDepotHeadAndDetail", json=body)
            assert_business_error(resp, 8500007)
        with allure.step("确认没有新增单据"):
            assert find_bills(write_client, number) == [], f"单号 {number} 不应存在"
    finally:
        cleanup_bill(write_client, number)

    with allure.step("使用已存在单号被拒"):
        duplicate = demo_data["header"]["number"]
        dup_body, _ = build_purchase_inbound(demo_data, duplicate)
        resp = write_client.post("/depotHead/addDepotHeadAndDetail", json=dup_body)
        try:
            code = resp.json().get("code")
        except (ValueError, AttributeError):
            code = None
        if resp.status_code != 200 or code != 8500022:
            # 重号意外成功时禁止自动删除任何记录，该单号属于演示数据
            try:
                found = find_bills(write_client, duplicate)
                detail = f"共 {len(found)} 条：" + (
                    "；".join(
                        f"id={row.get('id')} number={row.get('number')} "
                        f"status={row.get('status')}"
                        for row in found
                    ) or "无精确匹配记录"
                )
            except Exception as exc:
                detail = f"回查失败 {type(exc).__name__}: {exc}"
            pytest.fail(
                f"重号新增未被拒绝：HTTP {resp.status_code}，code {code}，响应 {resp.text[:500]}；"
                f"单号 {duplicate} 回查 {detail}。禁止自动删除本场景涉及的任何记录，请人工核查"
            )
        assert_business_error(resp, 8500022)
    with allure.step("确认原单未被复制"):
        found = find_bills(write_client, duplicate)
        assert len(found) == 1, f"单号 {duplicate} 查到 {len(found)} 条"
        assert found[0]["id"] == demo_data["header"]["id"], f"原单 id 变化: {found[0]}"
    # 失败路径的已知副作用：Redis 去重键 2 秒后过期；主表/明细由事务回滚，无业务残留


@allure.suite(SUITE)
@allure.title("W03 审核通过后库存增加")
@allure.severity(allure.severity_level.CRITICAL)
def test_audit_increases_stock(force_approval_bill, write_client):
    meta = force_approval_bill
    number = meta["number"]
    bill = _bill(write_client, number)
    before = read_stock(write_client, meta["depot_id"], meta["bar_code"])

    with allure.step("审核单据"):
        assert_ok(write_client.post("/depotHead/batchSetStatus", json={"status": "1", "ids": str(bill["id"])}))
    assert _bill(write_client, number)["status"] == "1", f"审核后状态不符，单号 {number}"
    after = read_stock(write_client, meta["depot_id"], meta["bar_code"])
    expected = before + meta["quantity"]
    assert after == expected, f"单号 {number} 库存不符：审核前 {before}，审核后 {after}，期望 {expected}"

    with allure.step("重复审核被拒"):
        resp = write_client.post("/depotHead/batchSetStatus", json={"status": "1", "ids": str(bill["id"])})
        assert_business_error(resp, 8500012)


@allure.suite(SUITE)
@allure.title("W04 反审核后库存恢复")
@allure.severity(allure.severity_level.CRITICAL)
def test_unaudit_restores_stock(force_approval_bill, write_client):
    meta = force_approval_bill
    number = meta["number"]
    bill = _bill(write_client, number)
    baseline = read_stock(write_client, meta["depot_id"], meta["bar_code"])
    assert_ok(write_client.post("/depotHead/batchSetStatus", json={"status": "1", "ids": str(bill["id"])}))
    audited = read_stock(write_client, meta["depot_id"], meta["bar_code"])
    assert audited == baseline + meta["quantity"], f"单号 {number} 审核后库存未增加"

    with allure.step("反审核单据"):
        assert_ok(write_client.post("/depotHead/batchSetStatus", json={"status": "0", "ids": str(bill["id"])}))
    assert _bill(write_client, number)["status"] == "0", f"反审核后状态不符，单号 {number}"
    after = read_stock(write_client, meta["depot_id"], meta["bar_code"])
    assert after == baseline, f"单号 {number} 库存未恢复：基线 {baseline}，反审核后 {after}"

    with allure.step("重复反审核被拒"):
        resp = write_client.post("/depotHead/batchSetStatus", json={"status": "0", "ids": str(bill["id"])})
        assert_business_error(resp, 8500013)


@allure.suite(SUITE)
@allure.title("W05 已审核不可删除，反审核后可删除")
@allure.severity(allure.severity_level.CRITICAL)
def test_delete_requires_unaudited(force_approval_bill, write_client):
    meta = force_approval_bill
    number = meta["number"]
    bill = _bill(write_client, number)
    baseline = read_stock(write_client, meta["depot_id"], meta["bar_code"])
    assert_ok(write_client.post("/depotHead/batchSetStatus", json={"status": "1", "ids": str(bill["id"])}))
    audited = read_stock(write_client, meta["depot_id"], meta["bar_code"])

    with allure.step("删除已审核单据被拒"):
        resp = write_client.delete("/depotHead/delete", params={"id": bill["id"]})
        assert_business_error(resp, 8500011)
    assert _bill(write_client, number)["status"] == "1", f"单号 {number} 被拒删除后状态变化"
    assert read_stock(write_client, meta["depot_id"], meta["bar_code"]) == audited, "被拒删除不应影响库存"

    with allure.step("反审核后删除成功"):
        assert_ok(write_client.post("/depotHead/batchSetStatus", json={"status": "0", "ids": str(bill["id"])}))
        assert read_stock(write_client, meta["depot_id"], meta["bar_code"]) == baseline
        assert_ok(write_client.delete("/depotHead/delete", params={"id": bill["id"]}))
    with allure.step("确认无单据残留"):
        assert find_bills(write_client, number) == [], f"单号 {number} 删除后仍能查到"
    assert read_stock(write_client, meta["depot_id"], meta["bar_code"]) == baseline
