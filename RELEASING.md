# 发布（维护者）

发布走 **Trusted Publishing（OIDC）**：仓库里没有、也不需要长期 PyPI token。

## 一次性配置

> `vidlens-mcp` 1.4.1 已经用账号 token 首发过；现在改成 OIDC。

1. 打开 <https://pypi.org/manage/project/vidlens-mcp/settings/publishing/>
2. **Add a new publisher** → 选 **GitHub**，填：

   | 字段 | 值 |
   |---|---|
   | Owner | `cctv2333` |
   | Repository name | `vidlens` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

3. 保存（这些字段必须和工作流里完全一致，大小写也算）
4. 收尾：
   - GitHub → Settings → Secrets and variables → Actions → 删除 `PYPI_API_TOKEN`
   - PyPI → Account settings → API tokens → 撤销旧 token

`.github/workflows/release.yml` 里已经删掉 `password:`，只留 `id-token: write` + `environment: pypi`。

## 发版

```powershell
cd D:\vidlens\vidlens
git tag v1.4.2
git push origin v1.4.2
```

`release.yml` 会：构建 sdist + wheel → OIDC 发 PyPI（自动带 attestations）→ 挂到 GitHub Release。

## 验证

- Actions：<https://github.com/cctv2333/vidlens/actions/workflows/release.yml>
- PyPI：<https://pypi.org/project/vidlens-mcp/>
- 用户侧：`pipx install "vidlens-mcp[all]"`

## 常见失败

| 现象 | 原因 | 处理 |
|---|---|---|
| `invalid-publisher` / `invalid-pending-publisher` | owner/repo/workflow/environment 有任一不符 | 对照上表逐字改；workflow 必须是 `release.yml` |
| `400 File already exists` | 同版本号已发布 | 改 `pyproject.toml` version 再打新 tag（PyPI 不允许覆盖） |
| `403` 仍提示 token | 工作流还在传 `password` | 确认 `release.yml` 里没有 `password:` 行 |
| 环境保护卡住 | `pypi` environment 配了 required reviewers | 去 Settings → Environments 调整 |
