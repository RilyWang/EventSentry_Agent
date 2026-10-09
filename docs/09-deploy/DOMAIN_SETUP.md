# 用自己的域名固定访问地址

> 域名：`rilywang.cn`（DNS 托管在**阿里云**，NS = `dns29/dns30.hichina.com`）
> 更新日期：2026-10-09

---

## 现状核查

| 项 | 结果 |
|----|------|
| 域名 | `rilywang.cn` |
| DNS 托管 | **阿里云**（`dns29.hichina.com` / `dns30.hichina.com`） |
| 是否在 Cloudflare | ❌ 否 |
| 现有解析记录 | 无（域名尚未指向任何服务） |

---

## 两条路线对比

| 维度 | 路线 A：阿里云 DNS + Render | 路线 B：迁移 Cloudflare + 具名隧道 |
|------|---------------------------|-----------------------------------|
| 要改 NS 吗 | ❌ 不用 | ✅ 要在阿里云把 NS 改成 Cloudflare 的 |
| 需要信用卡吗 | ❌ 不用 | ❌ 不用 |
| 依赖你电脑开机 | ❌ **不依赖** | ✅ **依赖**（服务跑在本机） |
| 生效时间 | 几分钟 | DNS 迁移 5 分钟~24 小时 |
| 最终地址 | `https://eventsentry.rilywang.cn` | 同左 |
| 推荐度 | ⭐⭐⭐ **首选** | ⭐⭐ 备选 |

**结论：路线 A 更优**——不用改 NS、不用信用卡，且评委任何时间都能访问（不受你电脑开关机影响）。

---

## 路线 A：阿里云 DNS + Render 部署

### 步骤 1：在 Render 部署（约 5 分钟）

1. 打开 https://render.com → **Get Started** → 用 **GitHub** 登录
2. 控制台 → **New +** → **Blueprint**
3. 选择仓库 **EventSentry_Agent** → Render 自动读取根目录 `render.yaml` → 点 **Apply**
4. 在 **Environment** 里填两个密钥：
   - `LLM_API_KEY` = 你的智谱 GLM Key
   - `SERPER_API_KEY` = 你的 Serper Key
5. 等 3-5 分钟构建完成 → 得到 `https://eventsentry.onrender.com`

### 步骤 2：在 Render 绑定自定义域名

1. Render 服务页 → **Settings** → **Custom Domains** → **Add Custom Domain**
2. 输入 `eventsentry.rilywang.cn` → 保存
3. Render 会给出一个 **CNAME 目标地址**（形如 `eventsentry.onrender.com`）

### 步骤 3：在阿里云加一条解析记录

1. 登录 **阿里云域名控制台**：https://dns.console.aliyun.com
2. 找到 `rilywang.cn` → **解析设置** → **添加记录**
3. 按下表填写：

| 字段 | 填写内容 |
|------|----------|
| 记录类型 | **CNAME** |
| 主机记录 | `eventsentry` |
| 解析线路 | 默认 |
| 记录值 | Render 给你的 CNAME 目标（如 `eventsentry.onrender.com`） |
| TTL | 10 分钟 |

4. 保存 → 等几分钟生效

### 步骤 4：验证

浏览器打开 **https://eventsentry.rilywang.cn** → 应该看到 EventSentry 首页

> ⚠️ Render 免费实例闲置 15 分钟会休眠，首次访问需等 30-60 秒冷启动。
> ✅ 数据库已支持「从仓库内置库自举」，部署后**开箱就有 121 个真实事件**。

---

## 路线 B：迁移到 Cloudflare + 具名隧道

### 步骤 1：把域名接入 Cloudflare

1. 打开 https://dash.cloudflare.com → **Add a site** → 输入 `rilywang.cn` → 选 **Free** 套餐
2. Cloudflare 给出**两个 NS 地址**（形如 `xxx.ns.cloudflare.com`）
3. 去**阿里云域名控制台** → 找到域名 → **DNS 修改** → 改成 Cloudflare 给的这两个 NS
4. 等 Cloudflare 后台状态变为 **Active**（通常几分钟）

### 步骤 2：创建 API Token

Cloudflare 后台 → 头像 → **我的个人资料** → **API 令牌** → **创建令牌** → **自定义令牌**

三项权限都要：

| 类型 | 资源 | 权限 |
|------|------|------|
| Account | Cloudflare Tunnel | **Edit** |
| Zone | DNS | **Edit** |
| Zone | Zone | **Read** |

### 步骤 3：写入凭据并一键部署

```bash
cd D:/Zcode/Agent_投资事件追踪
# 把 token 写入 server/.env（该文件已被 .gitignore 排除）
echo "CLOUDFLARE_API_TOKEN=<你的Token>" >> server/.env

# 一条命令完成：建隧道 → 绑 DNS → 启动
python server/deploy_cloudflare_named.py rilywang.cn eventsentry
```

最终地址：**https://eventsentry.rilywang.cn**

> ⚠️ 路线 B 下服务仍跑在你本机，**电脑关机评委就打不开**。

---

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| `render.com` 打不开 | 网络问题 | 换网络或用手机热点 |
| Render 构建失败 | 未识别 Dockerfile | 确认 `render.yaml` 的 `dockerContext: ./server` |
| 自定义域名一直不生效 | DNS 未生效 | `nslookup eventsentry.rilywang.cn` 检查是否解析到目标 |
| Cloudflare 提示 Token 无效 | 权限没勾全 | 三项权限重新创建令牌 |
| 域名一直不是 Active | NS 未生效 | 阿里云控制台确认 NS 已改成 Cloudflare 的；等待传播 |

---

*相关：[`PAAS_DEPLOY.md`](./PAAS_DEPLOY.md)（无域名方案） ｜ [`CLOUDFLARE_STABLE.md`](./CLOUDFLARE_STABLE.md)（临时隧道说明）*
