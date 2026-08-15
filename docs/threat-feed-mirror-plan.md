# threat_feed 内网镜像部署方案（threat-feed-mirror-plan）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> 目标：政府内网环境下威胁情报订阅源的可用性保障（审计 P1 建议落地）
> 依据：`app/threat_feed.py` 现状（强制 https、可选签名校验、本地缓存）

---

## 〇、背景与约束

| 项 | 现状（代码事实） | 约束 |
|---|---|---|
| 订阅源地址 | `config.threat_feed_url`（默认空串） | **强制 https://**（S-4：明文 http 可被投毒/中间人篡改） |
| 拉取 | `fetch_feed(feed_url, timeout=15)` | 非 https 抛 ValueError；`file://` 需显式开启离线测试开关 |
| 签名校验 | `refresh(feed_url, verify=None)` | R1：`verify` 为可选 callable(raw_bytes)->bool，已预留 |
| 缓存 | `cache_path()` / `load_cached()` | 本地持久化，离线可复用上次结果 |
| 内网现实 | 政府内网无法直连公网情报源 | **需内网镜像 + 内部 https + 签名防篡改** |

## 一、方案架构

```
公网威胁情报源（恶意域名列表）
        │ 定时同步（每日，外部跳板/离线导入）
        ▼
内网镜像服务器（隔离区）
  ├─ 同步脚本：拉取 → 校验 → 签名（GPG）→ 落盘静态文件
  └─ HTTPS 托管：nginx 只读静态服务（内网 CA 证书）
        │ config.threat_feed_url = https://threat.internal.gov.cn/feed.txt
        ▼
Aegis 客户端（Windows 端）
  ├─ ThreatFeedUpdater.refresh(url, verify=校验回调)
  └─ 失败静默 + 本地缓存兜底（现有行为不变）
```

## 二、部署步骤

### 2.1 内网镜像服务器（隔离区，一次性搭建）

1. **同步脚本**（服务器端，可 cron 每日执行）：
   - 从公网源拉取情报文件 → 校验格式（行级域名白名单正则）
   - **GPG 签名**：`gpg --detach-sign --armor feed.txt > feed.txt.sig`（专用签名密钥，私钥仅存服务器）
   - 原子替换：写入 `feed.txt.tmp` → 校验通过 → `mv` 覆盖（防半写）
2. **HTTPS 托管**（nginx）：
   ```nginx
   server {
       listen 443 ssl;
       server_name threat.internal.gov.cn;
       ssl_certificate     /etc/ssl/internal/threat.crt;  # 内网 CA 签发
       ssl_certificate_key /etc/ssl/internal/threat.key;
       root /srv/threat-mirror;
       autoindex off;
       location / { add_header Cache-Control "no-store"; }  # 防缓存过期情报
   }
   ```
3. **更新节奏**：每日一次（威胁情报时效敏感，低于 WebView2 的 2 周节奏）

### 2.2 Aegis 客户端接入（代码已预留，仅配置）

1. **配置**：`config.threat_feed_url = "https://threat.internal.gov.cn/feed.txt"`
2. **签名校验接入**（R1 verify callable，代码已支持）：
   - 客户端内置镜像公钥（GPG 公钥随包分发，仅服务器私钥签名）
   - `refresh(url, verify=lambda raw: verify_gpg_signature(raw, sig_url, PUBLIC_KEY))`
   - 校验失败 → 丢弃数据 + 回退本地缓存（现有静默降级语义）

## 三、安全要点

| 项 | 措施 |
|---|---|
| 传输安全 | 内网 https（S-4 强制）；拒绝明文 http |
| 完整性 | GPG 签名校验（R1 verify 已预留）；公钥随包、私钥仅服务器 |
| 防投毒 | 服务器端行级域名白名单正则校验（非合法域名丢弃） |
| 防半写 | 原子替换（tmp + mv） |
| 可用性 | 客户端失败静默 + 本地缓存兜底（现有行为不变） |
| 审计 | 镜像更新日志（时间/哈希/签名验证结果）留档 |

## 四、实施清单

| 项 | 动作 | 负责人域 |
|---|---|---|
| 1 | 隔离区搭建 nginx https + 内网 CA 证书 | 运维 |
| 2 | 同步脚本（拉取/校验/GPG 签名/原子替换）+ cron | 开发+运维 |
| 3 | 客户端 GPG 公钥随包分发 + verify 回调接入（threat_feed.py 扩展） | 开发 |
| 4 | config.threat_feed_url 指向内网镜像 + 验证（selftest 覆盖 file:// 离线测试开关） | 开发 |
| 5 | 验收：内网环境全链路（镜像→签名→拉取→校验→缓存） | 测试 |

## 五、离线/降级路径（现有行为保持不变）

- 镜像不可达 → `refresh` 失败静默 → 使用本地缓存（`load_cached`）
- 签名校验失败 → 丢弃新数据 → 回退缓存（防投毒）
- 开发/测试：`file://` 显式开启离线测试开关（现有代码路径）

## 六、结论

Aegis 的威胁情报接入**已为内网镜像预留全部挂点**（https 强制、R1 verify 签名校验、本地缓存兜底）——本方案仅需服务器端搭建 + 客户端配置，无架构改动。落地优先级：P1（与 CI 转绿并列），可独立于代码交付推进。
