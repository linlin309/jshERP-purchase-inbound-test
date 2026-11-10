import allure
import pytest

from utils.assertions import assert_ok

pytestmark = pytest.mark.smoke
SUITE = "基础冒烟"


@allure.suite(SUITE)
@allure.title("S01 登录后会话可用")
@allure.severity(allure.severity_level.CRITICAL)
def test_login_and_session(client):
    data = assert_ok(client.get("/user/getUserSession"))
    assert isinstance(data, dict), f"会话结构不符: {data}"
    user = data.get("user")
    assert isinstance(user, dict), f"会话 user 结构不符: {data}"
    assert user.get("loginName"), f"会话缺少 loginName: {data}"


@allure.suite(SUITE)
@allure.title("S02 仓库列表可用")
@allure.severity(allure.severity_level.CRITICAL)
def test_depot_list(client):
    data = assert_ok(client.get("/depot/getAllList"))
    assert isinstance(data, list), f"仓库列表结构不符: {data}"


@allure.suite(SUITE)
@allure.title("S03 结算账户列表可用")
@allure.severity(allure.severity_level.NORMAL)
def test_account_list(client):
    data = assert_ok(client.get("/account/getAccount"))
    assert isinstance(data, dict), f"账户结构不符: {data}"
    assert isinstance(data.get("accountList"), list), f"账户列表结构不符: {data}"
