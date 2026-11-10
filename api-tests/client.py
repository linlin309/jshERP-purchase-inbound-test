import hashlib
import time

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

# 写接口：只有 write_client（allow_write=True）能发；write marker 只是筛选用例，不放行请求
WRITE_CALLS = {
    ("POST", "/depotHead/addDepotHeadAndDetail"),
    ("POST", "/depotHead/batchSetStatus"),
    ("DELETE", "/depotHead/delete"),
}

# 同用户同 IP 同秒内两次「单据」日志会被后端强制退出；日志落库点不同，1.1 秒仍可能同秒，取 2 秒
WRITE_INTERVAL_SECONDS = 2.0


class ErpClient:
    # 只读守卫汇总所有客户端，A05 的独立 client 也能被核对到
    instances = []
    # 所有写客户端共用：跨用例换了 client 实例也要间隔
    _last_write_at = None

    def __init__(self, settings, allow_write=False):
        self.settings = settings
        self.allow_write = allow_write
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
        registered = (method, path_only) in READONLY_CALLS or (method, path_only) in SESSION_CALLS
        # 写接口必须显式 allow_write，共享 client 永远拿不到这个开关
        allowed = registered or (self.allow_write and (method, path_only) in WRITE_CALLS)
        if not allowed:
            if (method, path_only) in WRITE_CALLS:
                raise RuntimeError(
                    f"写接口 {method} {path} 需通过 write_client 在 write 用例中调用；"
                    f"write marker 只筛选用例，不授权请求"
                )
            raise RuntimeError(
                f"接口 {method} {path} 不在只读白名单或会话操作内；确认无写副作用后再登记"
            )
        if self.allow_write and (method, path_only) in WRITE_CALLS:
            now = time.monotonic()
            if ErpClient._last_write_at is not None:
                wait = WRITE_INTERVAL_SECONDS - (now - ErpClient._last_write_at)
                if wait > 0:
                    time.sleep(wait)
            ErpClient._last_write_at = time.monotonic()
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
