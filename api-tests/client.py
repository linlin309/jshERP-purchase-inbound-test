import hashlib

import requests


class ErpClient:
    def __init__(self, settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def login(self):
        resp = self.session.post(
            f"{self.settings.base_url}/user/login",
            json={
                "loginName": self.settings.login_name,
                "password": hashlib.md5(self.settings.password.encode("utf-8")).hexdigest(),
                "code": "",
                "uuid": "",
            },
            timeout=self.settings.timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        token = (body.get("data") or {}).get("token")
        if body.get("code") != 200 or not token:
            raise RuntimeError(f"登录失败: {body}")
        self.session.headers["X-Access-Token"] = token
        return body

    def request(self, method, path, **kwargs):
        kwargs.setdefault("timeout", self.settings.timeout)
        return self.session.request(method, f"{self.settings.base_url}{path}", **kwargs)

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)
