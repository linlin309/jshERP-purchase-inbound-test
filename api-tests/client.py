import hashlib

import requests

# M2 只读白名单：新增接口前先确认无写副作用，再显式加进来
READONLY_CALLS = {
    ("POST", "/user/login"),
    ("POST", "/supplier/findBySelect_sup"),
    ("POST", "/serialNumber/getEnableSerialNumberList"),
    ("GET", "/user/getUserSession"),
    ("GET", "/depot/getAllList"),
    ("GET", "/account/getAccount"),
    ("GET", "/material/getMaterialByBarCode"),
    ("GET", "/depotHead/list"),
    ("GET", "/depotHead/getDetailByNumber"),
    ("GET", "/depotHead/info"),
    ("GET", "/depotHead/getBillListByLinkNumber"),
    ("GET", "/depotItem/getDetailList"),
    ("GET", "/depotItem/findStockByDepotAndBarCode"),
    ("GET", "/depotItem/getInOutStock"),
    ("GET", "/systemConfig/getCurrentInfo"),
}


class ErpClient:
    def __init__(self, settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.calls = []

    def login(self):
        resp = self.request(
            "POST",
            "/user/login",
            json={
                "loginName": self.settings.login_name,
                "password": hashlib.md5(self.settings.password.encode("utf-8")).hexdigest(),
                "code": "",
                "uuid": "",
            },
        )
        resp.raise_for_status()
        body = resp.json()
        token = (body.get("data") or {}).get("token")
        if body.get("code") != 200 or not token:
            raise RuntimeError(f"登录失败: {body}")
        self.session.headers["X-Access-Token"] = token
        return body

    def request(self, method, path, **kwargs):
        method = method.upper()
        # 事前拦截：只读白名单外的请求不发出去
        if (method, path.split("?")[0]) not in READONLY_CALLS:
            raise RuntimeError(
                f"接口 {method} {path} 不在只读白名单内；确认无写副作用后再加入 client.READONLY_CALLS"
            )
        kwargs.setdefault("timeout", self.settings.timeout)
        resp = self.session.request(method, f"{self.settings.base_url}{path}", **kwargs)
        self.calls.append((method, path.split("?")[0], resp.status_code))
        return resp

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)
