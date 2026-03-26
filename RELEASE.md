# 发布流程（标准版）

## 版本规则
- 使用语义化版本：`vX.Y.Z`
- 入口文件固定：`index.html`
- 发布产物：
  - `school-advisor-vX.Y.Z-latest.html`
  - `versions/vX.Y.Z-YYYYMMDD.html`
  - `VERSION.json`
  - `versions/CHANGELOG.md`

## 发布命令
```bash
python3 scripts/release.py \
  --version v8.0.1 \
  --date 2026-03-26 \
  --notes "修复筛选逻辑" \
  --notes "更新虹口区数据"
```

## 数据发布（与版本发布配套）
```bash
python3 backend/tools/update_bootstrap.py --file /path/to/new-data.json
```

## Git 操作规范
1. `git add .`
2. `git commit -m "release: vX.Y.Z"`
3. `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
4. `git push origin main --tags`

## 自动同步到 Cloudflare 仓库（推荐）
项目已提供工作流：`.github/workflows/sync_to_cloudflare_repo.yml`

触发条件：
- push 到 `main` 或 `master`
- 手动触发 `workflow_dispatch`

首次配置（只需一次）：
1. 在 `primary-school-advisor` 仓库创建 PAT（Classic）或 Fine-grained token，授予目标仓库 `school-advisor` 的写权限
2. 在 `primary-school-advisor` 仓库设置 Secret：`CF_SYNC_TOKEN`
3. 可选设置 Repository Variables：
   - `CF_TARGET_REPO`（默认 `kallenhu1-spec/school-advisor`）
   - `CF_TARGET_BRANCH`（默认 `main`）

配置完成后：
- 你只需要 `git push origin main`
- GitHub Actions 会自动把当前提交同步到 `school-advisor/main`
- Cloudflare Pages 会按既有设置自动部署

## 注意事项
- 历史版本文件不覆盖，只新增。
- `data/*.db` 不入库，数据库由脚本初始化/更新。
