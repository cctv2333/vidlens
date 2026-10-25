# 发布（维护者）

> GitHub 新版界面：入口在仓库 **Settings → 最下面「Security and quality」→ Secrets and variables → Actions**。
> 直达链接（打开就是这个页面）：
> <https://github.com/cctv2333/vidlens/settings/secrets/actions>
>
> 页面上有两个区块：
> - **Environment secrets** —— 环境级（对应 workflow 里的 `environment: pypi`）
> - **Repository secrets** —— 仓库级（本仓库用这个，绿色按钮 **New repository secret**）

## 0. 一次性准备

### A. PyPI token

1. 注册 / 登录 <https://pypi.org>
2. 创建 token：<https://pypi.org/manage/account/token/> → **Add a new token**
   - **首次发布**：Scope 选 **Entire account (all projects)**
     （项目 `vidlens-mcp` 还不存在，没法选具体项目）
   - 首次发布成功后：删掉旧 token，换成 **Project: vidlens-mcp** 的 token
   - 值以 `pypi-` 开头，**只显示一次**
3. 写进 GitHub：<https://github.com/cctv2333/vidlens/settings/secrets/actions/new>
   - **Name**: `PYPI_API_TOKEN`
   - **Secret**: 粘贴上面那串 `pypi-...`
   - 点 **Add secret**

### B. 不想用 token？PyPI 支持 OIDC（推荐长期方案）

`release.yml` 的 `pypi` job 已经带 `id-token: write` 和 `environment: pypi`。
如果改用 Trusted Publishing：

1. 打开 <https://pypi.org/manage/account/publishing/> → **Add a pending publisher**
   - PyPI Project Name: `vidlens-mcp`
   - Owner: `cctv2333`
   - Repository name: `vidlens`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
2. 把 `release.yml` 里 publish 步骤的 `password:` 一行删掉（只留 `print-hash`）
3. 之后不需要任何 secret

## 1. 发版

```bash
cd D:\vidlens\vidlens
git tag v1.4.1          # 必须是 v* 开头
git push origin v1.4.1
```

`release.yml` 会：构建 sdist + wheel → 发 PyPI → 把产物挂到 GitHub Release。

## 2. 验证

- Actions：<https://github.com/cctv2333/vidlens/actions/workflows/release.yml>
- PyPI：<https://pypi.org/project/vidlens-mcp/>
- 用户侧：

```bash
pipx install "vidlens-mcp[all]"
vidlens doctor
# MCP 配置：{"command": "vidlens-mcp"}
```

## 3. 常见失败

| 现象 | 原因 | 处理 |
|---|---|---|
| `403 Invalid or non-existent authentication` | secret 名字拼错 / token 过期 | 重新建 token，确认 Name 是 `PYPI_API_TOKEN` |
| `400 File already exists` | 同版本号已发布过 | 改 `pyproject.toml` 的 version 后重新打 tag（PyPI 不允许覆盖） |
| `invalid-publisher`（OIDC） | pending publisher 的 owner/repo/workflow 对不上 | 大小写、文件名 `release.yml`、environment `pypi` 都要一致 |
