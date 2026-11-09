# jshERP 采购入库 接口自动化

> 状态：M1.1 骨架（2026-11-09）｜ 设计文档：01-03 已建，04-05 待补

## 目标

用 pytest + requests 覆盖采购入库主链路的接口层判定，与手工测试互补；接口结论不混入本轮 43 条手工用例。

## 环境

- Python 3.12
- jshERP 后端：`http://localhost:9999/jshERP-boot`
- MySQL 3307、Redis 6379（后端依赖）
- 演示账号见仓库根 README「被测系统与复现」

## 快速开始

```powershell
cd api-tests
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env，填入 LOGIN_NAME / PASSWORD
pytest -m smoke
```

## 报告

```powershell
New-Item -ItemType Directory -Force reports | Out-Null
pytest -m smoke --html=reports/report.html --self-contained-html
```

## 目录

- `docs/`：方案、接口清单、框架设计与后续用例
- `config.py`：读取 `.env`
- `client.py`：登录与 HTTP 封装
- `conftest.py`：session 级 client
- `tests/`：pytest 用例

## 约定

- `.env`、`.venv/`、`reports/` 不入库
- 默认 `pytest` 只跑安全用例；写操作用 `pytest -m write`，配置用 `-m config`（需 `RUN_CONFIG_TESTS=1`），权限用 `-m permission`
- 失败时先检查后端 9999 是否启动、账号是否正确
