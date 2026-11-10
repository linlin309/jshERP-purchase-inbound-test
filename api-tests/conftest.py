import pytest
import requests

from client import READONLY_CALLS, ErpClient
from config import load_settings
from utils.assertions import assert_ok

_CLIENT = None


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def client(settings):
    global _CLIENT
    c = ErpClient(settings)
    try:
        c.login()
    except requests.ConnectionError as exc:
        pytest.exit(
            f"无法连接后端 {settings.base_url}，请先启动 jshERP-boot（9999）后重试。\n{exc}",
            returncode=2,
        )
    _CLIENT = c
    return c


def _need_list(value, what):
    """结构不符算契约问题（失败）；列表为空算前置数据不足（跳过）。"""
    assert isinstance(value, list), f"{what} 结构不符: {type(value).__name__}"
    if not value:
        pytest.skip(f"前置数据不足：{what} 为空，请先在演示环境准备数据")
    return value


def _need_id(item, what):
    assert isinstance(item, dict), f"{what} 结构不符: {type(item).__name__}"
    assert item.get("id") is not None, f"{what} 缺少 id: {item}"
    return item


@pytest.fixture(scope="session")
def demo_data(client):
    """动态取演示数据，避免把仓库 14 / 条码 1001 写成常量。"""
    depots = _need_list(assert_ok(client.get("/depot/getAllList")), "仓库列表")
    depot = _need_id(next((d for d in depots if d.get("isDefault")), depots[0]), "仓库")

    account_data = assert_ok(client.get("/account/getAccount"))
    assert isinstance(account_data, dict), f"账户结构不符: {account_data}"
    accounts = _need_list(account_data.get("accountList"), "结算账户列表")
    account = _need_id(next((a for a in accounts if a.get("isDefault")), accounts[0]), "结算账户")

    resp = client.post("/supplier/findBySelect_sup", json={"key": "", "limit": 10})
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    suppliers = _need_list(resp.json(), "供应商下拉")
    supplier = _need_id(suppliers[0], "供应商")

    list_resp = client.get(
        "/depotHead/list",
        params={"search": '{"type":"入库","subType":"采购"}', "currentPage": 1, "pageSize": 1},
    )
    list_data = assert_ok(list_resp)
    assert isinstance(list_data, dict), f"单据列表结构不符: {list_data}"
    headers = _need_list(list_data.get("rows"), "采购入库单列表")
    header = _need_id(headers[0], "采购入库单")

    items = assert_ok(client.get("/depotItem/getDetailList", params={"headerId": header["id"]}))
    assert isinstance(items, dict), f"单据明细结构不符: {items}"
    rows = _need_list(items.get("rows"), "采购入库单明细")
    bar_code = rows[0].get("barCode")
    assert bar_code, f"单据明细缺少 barCode: {rows[0]}"

    materials = _need_list(
        assert_ok(
            client.get(
                "/material/getMaterialByBarCode",
                params={"barCode": bar_code, "mpList": "", "depotId": depot["id"]},
            )
        ),
        f"条码 {bar_code} 对应商品",
    )
    material = _need_id(materials[0], "商品")

    return {
        "depot": depot,
        "account": account,
        "supplier": supplier,
        "header": header,
        "bar_code": bar_code,
        "material": material,
    }


def pytest_sessionfinish(session, exitstatus):
    """事后兜底：理论上请求已在 client 事前拦截，这里只做核对和汇总。"""
    if _CLIENT is None:
        return
    calls = _CLIENT.calls
    bad = [(m, p) for m, p, _ in calls if (m, p) not in READONLY_CALLS]
    print(f"\n[只读守卫] 本次共 {len(calls)} 次接口调用")
    if bad:
        print(f"[只读守卫] 出现白名单外调用: {bad}")
        session.exitstatus = 1
    else:
        print("[只读守卫] 全部命中只读白名单")
