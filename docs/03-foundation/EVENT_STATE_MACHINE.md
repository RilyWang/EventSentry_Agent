# 事件状态机完整定义

## 一、状态总图

```
                    ┌─────────────┐
                    │   START     │
                    │  (事件创建)  │
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │ UNVERIFIED │  │   MEDIA    │  │ OFFICIALLY │
    │   RUMOR    │  │  VERIFIED  │  │  CONFIRMED │
    │  (未证实)   │  │  (媒体验证) │  │  (官方确认) │
    └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
          │               │               │
          │               │               ▼
          │               │        ┌────────────┐
          │               │        │ SUBSTANCE  │
          │               │        │  LANDED    │
          │               │        │ (实质落地)  │
          │               │        └─────┬──────┘
          │               │               │
          ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  EXPIRED   │  │ OFFICIALLY │  │  EXPIRED   │
    │  (过期)     │  │   DENIED   │  │  (过期)     │
    └────────────┘  │  (官方否认) │  └────────────┘
                    └─────┬──────┘
                          │
                          ▼
                    ┌────────────┐
                    │  EXPIRED   │
                    │  (过期)     │
                    └────────────┘
```

## 二、状态定义

| 状态编码 | 状态名称 | 定义 | 颜色 |
|---------|---------|------|------|
| `UNVERIFIED_RUMOR` | 未证实传闻 | 仅有 T3 传闻或匿名消息，无 T1/T0 验证 | 灰色 |
| `MEDIA_VERIFIED` | 媒体验证 | 有 ≥2 家 T1 权威媒体交叉验证，但无 T0 公告 | 橙色 |
| `OFFICIALLY_CONFIRMED` | 官方确认 | 有 T0 公告或监管文件明确确认 | 绿色 |
| `OFFICIALLY_DENIED` | 官方否认 | 有 T0 公告明确否认 | 红色 |
| `SUBSTANCE_LANDED` | 实质落地 | 官方确认后，出现合同签署、产品发布、业绩兑现等实质进展 | 深绿 |
| `EXPIRED` | 已过期 | 超过 30 天无新证据，或官方否认后 7 天无新进展 | 浅灰 |

## 三、跃迁规则（Transition Rules）

### Rule 1: START → UNVERIFIED_RUMOR

**触发条件：** 系统首次抓取到某标的的某主题消息，且该消息为 T3 层级。

**动作：** 创建新 Event，状态 = UNVERIFIED_RUMOR。

**示例：** 股吧出现"腾讯要收购某 AI 公司"的匿名帖子。

---

### Rule 2: START → MEDIA_VERIFIED

**触发条件：** 系统首次抓取到某标的的某主题消息，且该消息为 T1 层级 ≥2 条（同时或短时间内）。

**动作：** 创建新 Event，状态 = MEDIA_VERIFIED。

**示例：** 财新和一财同时报道"腾讯与某 AI 公司接触"。

---

### Rule 3: START → OFFICIALLY_CONFIRMED

**触发条件：** 系统首次抓取到某标的的某主题消息，且该消息为 T0 公告直接确认。

**动作：** 创建新 Event，状态 = OFFICIALLY_CONFIRMED。

**示例：** 公司直接发公告"拟收购某 AI 公司 51% 股权"。

---

### Rule 4: UNVERIFIED_RUMOR → MEDIA_VERIFIED

**触发条件：** Event 当前为 UNVERIFIED_RUMOR，新证据中包含 ≥2 条 T1 权威媒体验证，且无 T0 否认。

**动作：** 状态跃迁为 MEDIA_VERIFIED，触发 P1 通知。

**示例：** 股吧传了一周后，财新和一财跟进报道。

---

### Rule 5: UNVERIFIED_RUMOR → OFFICIALLY_CONFIRMED

**触发条件：** Event 当前为 UNVERIFIED_RUMOR，新证据为 T0 公告确认。

**动作：** 状态跃迁为 OFFICIALLY_CONFIRMED，触发 P0 通知。

---

### Rule 6: UNVERIFIED_RUMOR → OFFICIALLY_DENIED

**触发条件：** Event 当前为 UNVERIFIED_RUMOR，新证据为 T0 公告明确否认。

**动作：** 状态跃迁为 OFFICIALLY_DENIED，触发 P0 通知。

**示例：** 公司发澄清公告"不存在应披露未披露事项"。

---

### Rule 7: MEDIA_VERIFIED → OFFICIALLY_CONFIRMED

**触发条件：** Event 当前为 MEDIA_VERIFIED，新证据为 T0 公告确认。

**动作：** 状态跃迁为 OFFICIALLY_CONFIRMED，触发 P0 通知。

---

### Rule 8: MEDIA_VERIFIED → OFFICIALLY_DENIED

**触发条件：** Event 当前为 MEDIA_VERIFIED，新证据为 T0 公告明确否认。

**动作：** 状态跃迁为 OFFICIALLY_DENIED，触发 P0 通知。

---

### Rule 9: OFFICIALLY_CONFIRMED → SUBSTANCE_LANDED

**触发条件：** Event 当前为 OFFICIALLY_CONFIRMED，新证据表明合作/收购/产品已产生实质结果（如合同金额、产品上线、收入确认）。

**动作：** 状态跃迁为 SUBSTANCE_LANDED，触发 P1 通知。

**判定标准：**
- 收购类：完成股权过户
- 合作类：产品上线并产生收入/用户数
- 产品类：获批并开售
- 业绩类：财报兑现预增数字

---

### Rule 10: OFFICIALLY_CONFIRMED → EXPIRED

**触发条件：** Event 当前为 OFFICIALLY_CONFIRMED，超过 90 天无新证据，且未进入 SUBSTANCE_LANDED。

**动作：** 状态跃迁为 EXPIRED，触发 P1 通知，事件归档。

**说明：** 官方确认后长期无实质进展，市场关注度下降，事件自然终结。

---

### Rule 11: OFFICIALLY_DENIED → EXPIRED

**触发条件：** Event 当前为 OFFICIALLY_DENIED，超过 7 天无新 T0/T1 证据。

**动作：** 状态跃迁为 EXPIRED，触发 P1 通知，事件归档。

**说明：** 官方否认后若市场仍有传闻（仅 T3），不再改变状态，直到过期。

---

### Rule 12: OFFICIALLY_DENIED → MEDIA_VERIFIED（特殊：否认被推翻）

**触发条件：** Event 当前为 OFFICIALLY_DENIED，新出现 ≥2 条 T1 证据指向同一主题，且出现新的 T0 公告"补充说明"或"更正"。

**动作：** 状态跃迁为 MEDIA_VERIFIED 或 OFFICIALLY_CONFIRMED（取决于新 T0 内容），触发 P0 通知，并生成"更正提醒"。

**示例：** 公司先否认"不存在收购"，后更正为"正在筹划，存在不确定性"。

---

### Rule 13: UNVERIFIED_RUMOR → EXPIRED

**触发条件：** Event 当前为 UNVERIFIED_RUMOR，超过 30 天无新证据。

**动作：** 状态跃迁为 EXPIRED，不触发通知（静默归档）。

---

## 四、跃迁优先级

当单条新证据可能触发多条规则时，按以下优先级裁决：

```
T0 公告确认/否认 > T1 交叉验证 > T2 观点补充 > T3 传闻补充
```

**冲突处理：**
- 同时出现 T0 确认和 T0 否认（如补充公告推翻原公告）→ 以时间最新的 T0 为准
- 同时出现 T1 验证和 T0 否认 → T0 优先，状态为 OFFICIALLY_DENIED
- T3 传闻与当前状态无关（如传新对象）→ 触发"主题偏移检测"，可能拆分为新事件

## 五、通知触发映射

| 跃迁路径 | 通知优先级 | 通知文案示例 |
|---------|-----------|------------|
| 任何状态 → OFFICIALLY_CONFIRMED | P0（强推送） | "您关注的 [腾讯 AI 进展] 已获官方确认，点击查看详情" |
| 任何状态 → OFFICIALLY_DENIED | P0（强推送） | "您关注的 [腾讯收购传闻] 已被官方否认，注意风险" |
| 任何状态 → SUBSTANCE_LANDED | P1（弱提醒） | "[腾讯 AI 合作] 已有实质进展，合作产品正式上线" |
| UNVERIFIED_RUMOR → MEDIA_VERIFIED | P1（弱提醒） | "[腾讯 AI 进展] 获权威媒体交叉验证" |
| 任何状态 → EXPIRED | P1（弱提醒） | "[某事件] 已超过 30 天无新进展，已标记为过期" |
| 同一状态下新增证据 | P2（静默） | 不入通知队列，仅更新证据列表 |

## 六、状态与 Face 卡片标签映射

| 状态 | Face 卡片主标签 | 建议显示色 | 用户感知 |
|------|----------------|-----------|---------|
| UNVERIFIED_RUMOR | 传闻待证实 | 灰色 | "这事还没谱，听听就好" |
| MEDIA_VERIFIED | 媒体验证中 | 橙色 | "多家权威媒体报道，值得关注" |
| OFFICIALLY_CONFIRMED | 官方已确认 | 蓝色/绿色 | "公司自己认了，但注意是否落地" |
| OFFICIALLY_DENIED | 官方已否认 | 红色 | "公司说没有，大概率是假的" |
| SUBSTANCE_LANDED | 实质已落地 | 深绿 | "这事成了，影响开始兑现" |
| EXPIRED | 事件已过期 | 浅灰 | "这事过去了，不用关注了" |

## 七、边界案例处理

### Case 1: 更正公告

**场景：** 公司先发公告"不存在收购"，2 天后发补充公告"正在筹划收购"。

**处理：**
1. 第一个公告节点保留，状态标注"已更正"
2. 新增第二个节点，状态 = OFFICIALLY_CONFIRMED
3. 事件整体状态以最新 T0 为准 = OFFICIALLY_CONFIRMED
4. 向用户推送"更正提醒"："此前官方否认状态已被更新"

### Case 2: 主题偏移

**场景：** 传闻"收购 A 公司" → 官方否认 → 新传闻"收购 B 公司" → 官方证实。

**处理：**
1. "收购 A 公司"事件状态 = OFFICIALLY_DENIED → EXPIRED
2. 创建新事件"收购 B 公司"，状态 = OFFICIALLY_CONFIRMED
3. 两个事件在 UI 上显示"关联提示"："此前曾有收购 A 公司的传闻，已被否认"

### Case 3: 长期悬置

**场景：** 官方确认"正在筹划"，但 60 天无实质进展。

**处理：**
1. 状态保持 OFFICIALLY_CONFIRMED（不自动降级）
2. Face 卡片风险句更新："已确认 60 天但无实质进展，存在流产风险"
3. 达到 90 天 → 跃迁为 EXPIRED
