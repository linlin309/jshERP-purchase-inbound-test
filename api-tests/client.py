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

# 会话状态操作：只改 Redis 里的会话，不改业务数据；不能混进只读白名单
SESSION_CALLS = {
    ("GET", "/user/logout"),
}


class ErpClient:
    # 只读守卫汇总所有客户端，A05 的独立 client 也能被核对到
    instances = []

    def __init__(self, settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.calls = []
        ErpClient.instances.append(self)

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
        path_only = path.split("?")[0]
        # 事前拦截：只读白名单与会话操作之外的请求不发出去
        if (method, path_only) not in READONLY_CALLS and (method, path_only) not in SESSION_CALLS:
            raise RuntimeError(
                f"接口 {method} {path} 不在只读白名单或会话操作内；确认无写副作用后再登记"
            )
        kwargs.setdefault("timeout", self.settings.timeout)
        resp = self.session.request(method, f"{self.settings.base_url}{path}", **kwargs)
        self.calls.append((method, path_only, resp.status_code))
        return resp

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)
