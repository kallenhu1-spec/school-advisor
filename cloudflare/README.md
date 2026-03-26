# Cloudflare Workers + D1（免费版）部署说明

这套方案用于把线上 `school-advisor.pages.dev` 变成真实动态数据源，不依赖本地 `127.0.0.1`。

## 1. 在 Cloudflare 创建 D1 数据库

在 Cloudflare Dashboard:

1. `Storage & databases` -> `D1 SQL Database` -> `Create`
2. 名称建议：`school_advisor_prod`
3. 复制数据库 `database_id`

## 2. 在 Pages 项目绑定 D1

进入 `Workers & Pages` -> `school-advisor` -> `Settings` -> `Functions`:

1. `D1 database bindings` 新增：
   - Variable name: `DB`
   - D1 database: 选择刚创建的库
2. `Environment Variables` 新增：
   - `PUBLISH_TOKEN` = 你自定义的一段长随机字符串（例如 32 位）

## 3. 初始化 D1 表结构

在 D1 控制台执行：

```sql
-- 文件：cloudflare/d1/schema.sql
CREATE TABLE IF NOT EXISTS bootstrap_payload (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

## 4. 推送代码到 Cloudflare 绑定仓库

确保本仓库 `functions/` 目录已被推送到 Cloudflare 正在监听的 repo（你当前是 `cf/main`）。

推送后，线上会提供 API：

- `GET /api/health`
- `GET /api/bootstrap`
- `POST /api/admin/bootstrap`（需要 `Authorization: Bearer <PUBLISH_TOKEN>`）

## 5. 首次发布数据到 D1

在本地项目根目录执行：

```bash
python3 backend/tools/publish_cloudflare_api.py \
  --url https://school-advisor.pages.dev/api/admin/bootstrap \
  --token 你的PUBLISH_TOKEN
```

成功后，访问：

- `https://school-advisor.pages.dev/api/health`
- `https://school-advisor.pages.dev/api/bootstrap`

应能看到 `hasPayload=true` 和学校数据。

## 6. 后续更新数据

每次你本地后台改完并“数据推送前台”后，执行一次：

```bash
python3 backend/tools/publish_cloudflare_api.py \
  --url https://school-advisor.pages.dev/api/admin/bootstrap \
  --token 你的PUBLISH_TOKEN
```

线上页面会直接读取 `/api/bootstrap` 最新数据，不需要购买服务器。
