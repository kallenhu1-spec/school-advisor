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
4. `git push origin master --tags`

## 注意事项
- 历史版本文件不覆盖，只新增。
- `data/*.db` 不入库，数据库由脚本初始化/更新。
