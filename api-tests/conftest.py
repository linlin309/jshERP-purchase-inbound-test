import pytest
import requests

from client import READONLY_CALLS, SESSION_CALLS, WRITE_CALLS, ErpClient
from config import load_settings
from utils.assertions import assert_ok
from utils.data import build_purchase_inbound, cleanup_bill, find_bills, read_flags, unique_number


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def client(settings):
    return _client_or_exit(settings)


def _client_or_exit(settings, allow_write=False):
    c = ErpClient(settings, allow_write=allow_write)
    try:
        c.login()
    except requests.ConnectionError as exc:
        pytest.exit(
            f"无法连接后端 {settings.base_url}，请先启动 jshERP-boot（9999）后重试。\n{exc}",
            returncode=2,
        )
    return c


@pytest.fixture
def write_client(settings, request):
    """写用例的独立会话；marker 只筛选用例，allow_write 才放行写请求。"""
    if request.node.get_closest_marker("write") is None:
        pytest.fail("写接口只能由带 write marker 的用例通过 write_client 调用")
    return _client_or_exit(settings, allow_write=True)


@pytest.fixture(scope="session")
def system_flags(client):
    return read_flags(client)


@pytest.fixture
def force_approval(system_flags):
    if system_flags.get("forceApprovalFlag") != "1":
        pytest.skip("forceApprovalFlag != 1，库存变动时机不同，跳过依赖库存的写用例")


@pytest.fixture
def force_approval_bill(force_approval, created_bill):
    """库存相关写用例专用：前置不满足时先跳过，不会发送新增请求。"""
    return created_bill


def _recover_failed_add(client, number, add_error):
    """新增异常时按单号回查并清理；不重发请求，不把查询失败当成单据不存在。"""
    try:
        found = find_bills(client, number)
    except Exception as exc:
        raise AssertionError(
            f"新增异常且无法确认单据状态，需人工核查。单号 {number}；"
            f"新增异常 {type(add_error).__name__}: {add_error}；"
            f"回查异常 {type(exc).__name__}: {exc}"
        ) from add_error
    if not found:
        raise AssertionError(
            f"新增请求异常，回查未发现单据。单号 {number}；"
            f"新增异常 {type(add_error).__name__}: {add_error}"
        ) from add_error
    try:
        cleanup_bill(client, number)
    except Exception as exc:
        raise AssertionError(
            f"新增请求异常且单据已创建，清理失败。单号 {number}；"
            f"新增异常 {type(add_error).__name__}: {add_error}；"
            f"清理异常 {type(exc).__name__}: {exc}"
        ) from add_error
    raise AssertionError(
        f"新增请求异常，单据已创建并已清理。单号 {number}；"
        f"新增异常 {type(add_error).__name__}: {add_error}"
    ) from add_error


@pytest.fixture
def created_bill(write_client, demo_data, system_flags):
    if system_flags.get("updateUnitPriceFlag") == "1":
        pytest.skip("updateUnitPriceFlag=1 时建单会改商品采购价，需隔离商品后再跑写用例")
    number = unique_number()
    body, bill = build_purchase_inbound(demo_data, number)
    try:
        assert_ok(write_client.post("/depotHead/addDepotHeadAndDetail", json=body))
    except Exception as exc:
        _recover_failed_add(write_client, number, exc)
    yield bill
    cleanup_bill(write_client, number)


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
    """事后兜底：请求已在 client 事前拦截，这里只做核对和汇总。"""
    calls = [call for c in ErpClient.instances for call in c.calls]
    if not calls:
        return
    readonly = [(m, p) for m, p, _ in calls if (m, p) in READONLY_CALLS]
    session_ops = [(m, p) for m, p, _ in calls if (m, p) in SESSION_CALLS]
    writes = [(m, p) for m, p, _ in calls if (m, p) in WRITE_CALLS]
    bad = [
        (m, p)
        for m, p, _ in calls
        if (m, p) not in READONLY_CALLS
        and (m, p) not in SESSION_CALLS
        and (m, p) not in WRITE_CALLS
    ]
    print(
        f"\n[接口守卫] 本次共 {len(calls)} 次接口调用"
        f"（只读 {len(readonly)} / 会话操作 {len(session_ops)} / 写操作 {len(writes)}）"
    )
    if bad:
        print(f"[接口守卫] 出现未登记调用: {bad}")
        session.exitstatus = 1
    else:
        print("[接口守卫] 全部命中已登记接口")
