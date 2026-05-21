# 管易订单自动加赠品

从**待审核订单**的 `sellerMemo` 中解析 SKU 及加赠数量（如「两组 2406NCZ」加 2 件），按操作日志判断是否已加赠，再调用 `updateDetail` 追加明细，**保存成功后自动提交审核**。

若备注中的赠品 SKU 已全部在明细中（仅跳过、无失败），默认也会提交审核（`approve_when_ready`）。

## 环境

- Python 3.9+
- 依赖：`pip install -r requirements.txt`

## 配置

```bash
cp config.example.json config.json
```

编辑 `config.json`：

| 字段 | 说明 |
|------|------|
| `cookie` | 浏览器登录管易后，从 DevTools → Network 任意请求复制完整 `Cookie` |
| `shop_ids` | 店铺 ID，与待审核列表筛选一致 |
| `warehouse_id` | 查商品库存用的仓库 ID |
| `page_size` | 列表每页条数，默认 50 |
| `max_pages` | 最多拉取页数，`null` 表示拉完全部 |
| `request_delay_sec` | 请求间隔，降低风控 |
| `min_order_age_minutes` | 只处理创建时间早于「当前 − N 分钟」的订单，默认 `30`（半小时内不处理）；`0` 表示不限制。`--order-id` 指定单笔时不受此限制 |
| `sku_min_length` | SKU 最短长度，默认 2 |
| `sku_allowlist_prefix` | 非空数组时仅处理以这些前缀开头的 SKU |
| `list_filters` | 与列表页筛选项一致 |
| `auto_approve` | 加赠流程结束后是否调用审核接口，默认 `true` |
| `approve_when_ready` | 未新增行但备注 SKU 均已存在时是否仍审核，默认 `true` |
| `feishu` | 执行完成后写入飞书多维表「订单记录表」，见下表 |

### 飞书多维表 (`feishu`)

默认同步到：[订单记录表](https://doubleline.feishu.cn/wiki/TosvwRZ7lifUu9kIuKgcjuNqnTw)

| 字段 | 写入内容 |
|------|----------|
| 订单号 | `platformCode` |
| 备注 | `sellerMemo` |
| 加赠商品编码 | SKU |
| 加赠商品名称 | 商品名称 |
| 加赠商品规格 | 处理说明 / 错误信息 |
| 审核状态 | 已通过 / 待审核 / 已拒绝 |
| 审核时间 | 状态为「已通过」时写入当前时间 |

依赖本机已配置 `lark-cli` 且能 `--as user` 访问该 Base。`--no-feishu` 可跳过同步。

Cookie 过期时接口会报错，需重新登录管易并更新 `cookie`（关注 `shiroCookie`）。

## 运行

```bash
# 正式执行（处理当前待审核列表）
python add_gift_sku.py

# 试运行：只打印将加赠/将审核的订单，不写单、不审核
python add_gift_sku.py --dry-run

# 只加赠，不审核
python add_gift_sku.py --no-approve

# 不同步飞书
python add_gift_sku.py --no-feishu

# 仅处理一笔订单（联调推荐，参数为平台订单号 platformCode）
python add_gift_sku.py --order-id 6952978354922788022 --dry-run
python add_gift_sku.py --order-id 6952978354922788022

# 详细日志
python add_gift_sku.py -v
```

执行结束后会在 `logs/` 目录生成 `run_log_YYYYMMDD_HHMMSS.json`，记录本批处理明细。

## SKU 解析规则

- 匹配备注中由 **字母、数字、`-`** 组成的连续片段
- 满足其一即可：**含 `-`**（如 `AFL-0011`），或 **同时含字母与数字**（如 `2406NCZ`、`WT26004`）
- 去首尾 `-` 后长度 ≥ `sku_min_length`；纯字母或纯数字片段不提取
- **排除容量规格**：`66ml`、`133ml`、`500g` 等（数字+ml/L/g/kg 等），避免与商品编码混淆
- 是否已加赠：查询操作日志，`action=修改` 且 `memo` 含「新增商品」「商品代码XXX」则视为已加赠并跳过

示例：

| sellerMemo | 解析结果 |
|------------|----------|
| `加赠 油 AFL-0011 66ml` | 仅 `AFL-0011`（`66ml` 视为规格不解析） |
| `YHG-ZP-001 烟灰缸-赠品缸` | `YHG-ZP-001` |
| `加赠 2406NCZ` | `2406NCZ` ×1 |
| `加赠 两组 火石 2406NCZ` | `2406NCZ` ×2 |
| `加赠 2个 YHG-ZP-001` | `YHG-ZP-001` ×2 |
| `加赠 油 AFL-0011 66ml    YHG-ZP-001 烟灰缸-赠品缸` | `AFL-0011` ×1、`YHG-ZP-001` ×1（`66ml` 为规格忽略） |

**一单多 SKU**：备注里可出现多个编码，程序会按顺序逐个加赠（每个 SKU 各调一次保存接口）。数量取自每个 SKU **前面** 的文字，支持 `两组/2个/五件/×3` 等；默认 1，上限 `gift_max_qty`（默认 99）。

## 验证步骤

1. **配置**：`config.json` 中 Cookie、`shop_ids`、`warehouse_id` 与浏览器待审核页一致。
2. **试运行**：`python add_gift_sku.py --dry-run`，对照管易待审核列表，确认解析 SKU 与「已存在跳过」是否符合预期。
3. **单笔联调**：选一笔备注含赠品 SKU、明细尚未包含该码的订单：
   ```bash
   python add_gift_sku.py --order-id <platformCode> --dry-run
   python add_gift_sku.py --order-id <platformCode>
   ```
   在管易 UI 打开该单，确认明细新增一行且价格为 0。
4. **重复执行**：对同一订单再跑，应显示 `skipped_already_exists`，不应重复加行。

## 文件说明

| 文件 | 作用 |
|------|------|
| `add_gift_sku.py` | 主入口 |
| `guanyi_client.py` | 管易 HTTP 接口 |
| `sku_parser.py` | 备注 SKU 解析 |
| `config.example.json` | 配置模板 |

## 常见问题

- **认证失败**：更新 Cookie，确认账号有订单编辑权限。
- **product_not_found**：SKU 在指定仓库商品库不存在，或 `itemCode` 与备注不一致。
- **ambiguous_product**：模糊搜索返回多条且 `itemCode` 无精确匹配，需人工核对商品。
