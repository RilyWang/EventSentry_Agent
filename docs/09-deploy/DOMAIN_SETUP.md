# 用 `rilywang.cn` 固定访问地址（Cloudflare 方案）

> 目标：把项目部署成 **https://eventsentry.rilywang.cn** —— 永久固定地址
> 方案：Cloudflare 具名隧道（Named Tunnel）+ 自有域名
> 成本：**全免费，不需要信用卡**
> 更新日期：2026-10-09

---

## 现状（已核查）

| 项 | 值 |
|----|-----|
| 域名 | `rilywang.cn` |
| 当前 DNS 托管 | **阿里云**（NS：`dns29.hichina.com`、`dns30.hichina.com`） |
| 是否在 Cloudflare | ❌ 否 |
| 现有解析记录 | 无 |

**为什么必须迁到 Cloudflare：**
Cloudflare 隧道的 DNS 记录必须是**由 Cloudflare 自己托管**的（隧道路由靠 Cloudflare 内部映射）。
域名 DNS 在阿里云时，指向 `xxx.cfargotunnel.com` 的 CNAME **不会生效**。

所以流程是：**迁 NS → 建隧道 → 绑域名**。全程只有「改 NS」和「建 Token」需要你动手两次。

---

## 第一步：在 Cloudflare 添加站点

1. 打开 https://dash.cloudflare.com/sign-up 注册（也可用已有账号登录）
2. 登录后点 **+ Add a site**（添加站点）
3. 输入 `rilywang.cn` → **Continue**
4. 套餐选 **Free**（$0）→ **Continue**
5. Cloudflare 会扫描现有 DNS 记录，直接 **Continue**
6. 页面会给出**两个名称服务器（Nameserver）**，形如：

   ```
   xxxx.ns.cloudflare.com
   yyyy.ns.cloudflare.com
   ```

   **把这两个地址复制下来**（下一步要用）

> 💡 先别关这个页面，第二步需要对照。

---

## 第二步：在阿里云把 DNS 改为 Cloudflare 的

1. 打开阿里云域名控制台：https://dc.console.aliyun.com/next/index#/domain/list/all-domain
2. 找到 **rilywang.cn** → 点右侧 **管理**
3. 左侧菜单找 **DNS 修改**（部分界面在「基本信息」页有 **修改DNS** 按钮）
4. 点 **修改DNS服务器**
5. **删掉**原有的两条：
   - `dns29.hichina.com`
   - `dns30.hichina.com`
6. **填入** Cloudflare 给的两个 Nameserver
7. 确认提交

> ⚠️ 阿里云可能提示"DNS 修改后解析将失效"——正常，因为我们正是要把解析迁移到 Cloudflare。

---

## 第三步：等待生效（Cloudflare 变 Active）

| 项 | 说明 |
|----|------|
| 生效时间 | `.cn` 域名通常 **5 分钟 ~ 2 小时**（最长 24 小时） |
| 如何判断 | Cloudflare 后台该站点状态变为 **Active**；同时会收到邮件 |
| 自助检查 | 命令行执行 `nslookup -type=NS rilywang.cn`，看到 `*.ns.cloudflare.com` 即为生效 |

生效后在 Cloudflare 后台 → 该域名 → **DNS** 页，确认已有记录列表。

---

## 第四步：创建 API Token（一次性）

Cloudflare 右上角头像 → **我的个人资料（My Profile）** → **API 令牌（API Tokens）** → **创建令牌** → 选 **创建自定义令牌**

**权限必须勾选以下三项：**

| 类型 | 资源 | 权限级别 |
|------|------|---------|
| Account | Cloudflare Tunnel | **编辑（Edit）** |
| Zone | DNS | **编辑（Edit）** |
| Zone | Zone | **读取（Read）** |

**区域资源（Zone Resources）**：选 `包括 → 特定区域 → rilywang.cn`

→ 点 **继续以显示摘要** → **创建令牌**
→ **立刻复制**（只显示这一次）

> ⚠️ 上次你给我的 Token 校验返回 401 Invalid，多半是权限没勾全或复制不全。这次请确认三项权限都在。

---

## 第五步：交给我，一条命令完成

把 **Token** 发我即可（域名已知：`rilywang.cn`，子域名用 `eventsentry`）。

我会执行：

```bash
# 1) 把 Token 写入 server/.env（该文件已被 .gitignore 排除，不会进仓库）
# 2) 一键部署
python server/deploy_cloudflare_named.py rilywang.cn eventsentry
```

脚本自动完成：

| 步骤 | 动作 |
|------|------|
| 1 | 校验 Token 有效性 |
| 2 | 定位 Zone（rilywang.cn） |
| 3 | 创建具名隧道 `eventsentry` |
| 4 | 写入隧道凭据与 `config.yml` |
| 5 | 添加 DNS CNAME：`eventsentry` → `<隧道ID>.cfargotunnel.com` |
| 6 | 启动隧道 + 健康检查 |

**最终地址**：**https://eventsentry.rilywang.cn**

部署脚本同时会拉起 `server/keepalive.py` 守护进程，隧道断了会自动重连（具名隧道地址**不变**）。

---

## 关键区别：具名隧道 vs 快速隧道

| 项 | 快速隧道（当前临时用） | **具名隧道（本方案）** |
|----|---------------------|---------------------|
| 地址 | `xxx.trycloudflare.com`，**重启就变** | `eventsentry.rilywang.cn`，**永久不变** |
| 需要域名 | 否 | **是** |
| 需要 Token | 否 | 是（建隧道+绑DNS各一次） |
| 可用性 | 无保证 | 稳定 |

---

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| Cloudflare 一直 Pending | NS 还没改或没生效 | 回阿里云确认 NS 已是 Cloudflare 的；等待传播 |
| `Invalid API Token` (401) | 权限没勾全 / 复制不全 | 重新创建，确保三项权限 + Zone 选 rilywang.cn |
| 域名生效但打不开 | 隧道未启动 | 检查 `D:\Zcode\tools\tunnel_eventsentry.log` |
| 502 / 1033 | 隧道连上了但源站没起 | 确认本地 `http://localhost:3000/api/ping` 返回 200 |
| 想回滚 DNS | 想在阿里云恢复解析 | 阿里云控制台重新改回 `dns29/dns30.hichina.com` |

---

## 附：如果不想迁 NS（备选）

若你**不愿改 NS**，可以保留阿里云 DNS，改成在 Render 上部署再用阿里云加 CNAME：

- 优点：不用迁 NS、也不用信用卡
- 详见 [`PAAS_DEPLOY.md`](./PAAS_DEPLOY.md) 与本文档旧版说明

但按你的要求「只用 Cloudflare + 阿里云域名」，**推荐走上面的具名隧道方案**。

---

*相关：[`CLOUDFLARE_STABLE.md`](./CLOUDFLARE_STABLE.md)（临时隧道说明） ｜ [`PAAS_DEPLOY.md`](./PAAS_DEPLOY.md)（PaaS 备选）*
