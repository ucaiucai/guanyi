# 管易订单自动加赠品

从**待审核订单**的 `sellerMemo` 中解析含横杠的 SKU 编码（如 `AFL-0011`、`YHG-ZP-001`），若订单明细中尚无该 `itemCode`，则查询商品库并调用 `updateDetail` 追加一行（数量 1、价格为 0），**加赠保存成功后自动提交审核**。

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
| `sku_min_length` | SKU 最短长度，默认 2 |
| `sku_allowlist_prefix` | 非空数组时仅处理以这些前缀开头的 SKU |
| `list_filters` | 与列表页筛选项一致 |
| `auto_approve` | 加赠流程结束后是否调用审核接口，默认 `true` |
| `approve_when_ready` | 未新增行但备注 SKU 均已存在时是否仍审核，默认 `true` |

Cookie 过期时接口会报错，需重新登录管易并更新 `cookie`（关注 `shiroCookie`）。

## 运行

```bash
# 正式执行（处理当前待审核列表）
python add_gift_sku.py

# 试运行：只打印将加赠/将审核的订单，不写单、不审核
python add_gift_sku.py --dry-run

# 只加赠，不审核
python add_gift_sku.py --no-approve

# 仅处理一笔订单（联调推荐，参数为平台订单号 platformCode）
python add_gift_sku.py --order-id 6952978354922788022 --dry-run
python add_gift_sku.py --order-id 6952978354922788022

# 详细日志
python add_gift_sku.py -v
```

执行结束后会生成 `run_log_YYYYMMDD_HHMMSS.json`，记录本批处理明细。

## SKU 解析规则

- 匹配备注中由 **字母、数字、`-`** 组成的连续片段
- **必须至少包含一个 `-`**（`2406NCZ`、`66ml` 等不会提取）
- 去首尾 `-` 后长度 ≥ `sku_min_length`
- 与订单已有 `itemCode` 相同则跳过

示例：

| sellerMemo | 解析结果 |
|------------|----------|
| `加赠 油 AFL-0011 66ml` | `AFL-0011` |
| `YHG-ZP-001 烟灰缸-赠品缸` | `YHG-ZP-001` |

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
