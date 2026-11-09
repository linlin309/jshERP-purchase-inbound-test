import pytest

from utils.assertions import assert_ok

pytestmark = pytest.mark.smoke


def test_login_and_session(client):
    data = assert_ok(client.get("/user/getUserSession"))
    assert data, "会话信息为空"


def test_depot_list(client):
    data = assert_ok(client.get("/depot/getAllList"))
    assert data is not None, "仓库列表为空"


def test_account_list(client):
    data = assert_ok(client.get("/account/getAccount"))
    assert data is not None, "账户列表为空"
