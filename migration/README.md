# 修复版2迁移预览

这里的文件由 `tools/build_migration_preview.py` 根据修复版2目录内冻结的旧配置和旧缓存生成，属于独立预览副本。

- `sites.v2.preview.json`：版本化站点配置。
- `recent_10_cache.v2.preview.json`：按 `site_id` 迁移的近10期缓存预览。
- `migration-report.json`：匹配、孤儿、缺失和冲突报告。

这些文件不替换 `杀五行-修复版`，也不代表历史缓存已经被用户确认修正。发现冲突时脚本不会生成可写缓存预览。
