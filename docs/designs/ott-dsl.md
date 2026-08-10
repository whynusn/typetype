# OTT DSL 设计（L1.5 受限原语引擎）

<!-- 状态: draft | 创建: 2026-08-07 | 关联: ADR-011 Phase 1, L1 解释器 -->

> 状态：已实现（1.1-1.5 已落地，ADR-011 Phase 1）；真实站点验证挂起｜依据：[ADR-011](./../decisions/011-ott-source-ecosystem-hardening-plan.md) Phase 1
> 关联：[L1 解释器实现](../../src/backend/integration/ott_rule_interpreter.py)

---

## 1. 背景与动机

L1 声明式规则（`ott-rule`）为无图灵完备的抓取描述：

- `extract` 仅限 JSON path / 命名正则 / CSS 选择器三选一
- `transform` 仅限 `trim` / `replace` / `truncate` 固定管道
- `request.url` 仅允许公网 http(s)，无请求体构造能力

极速杯等真实源需要**组合能力**（如：抓取 → 时间戳 → AES 加密 → 构造请求体 → 提交），L1 表达不了。DSL（L1.5）在保持"客户端从网络订阅的一切内容均无任意代码执行"不变式的前提下，提供受限的原语组合引擎。

## 2. 与 L1 的关系

- **L1 是 L1.5 的子集**：仅含旧字段（`request.url/method/headers` + `extract` + `transform`）的规则走 L1 子集路径，行为不变。
- **schema v2**（Phase 1.3）新增字段：`request.body`、`steps`、`permissions`、`rights`。
- **运行时分流**：仅含旧字段 → 现有 L1 解释器路径；含 `steps` → L1.5 求值器。旧规则向后兼容，不迁移。
- 单条规则不得混用 `transform` 与 `steps`（schema 校验拒绝）。

## 3. 类型系统

| 类型 | 说明 | 例 |
|:--- |:--- |:--- |
| `str` | 文本 | `"abc"` |
| `bytes` | 字节串（显式类型，编码/加密原语的输入输出） | `b"\x01\x02"` |
| `int` | 整数 | `42` |
| `bool` | 布尔 | `true` |
| `list` | 列表 | `["a", "b"]` |
| `dict` | 对象 | `{"k": "v"}` |

规则：

- 字面量 `bytes` 用 `b"..."` 前缀；JSON 中即 `{"fn": "utf8_encode", "args": ["文本"]}` 这类显式转换，无隐式 str↔bytes 转换。
- 数字原语只接受 `int`（无 float，避免精度与平台差异）。
- 类型不匹配 → 求值错误（见 §6 异常处理），不自动转换。

## 4. 原语签名

签名格式：`name(arg1: T1, arg2: T2) -> Ret`。全部为纯函数，无状态，无副作用。

### 第一批（Phase 1.1a：基础能力）

| 原语 | 签名 | 说明 |
|:--- |:--- |:--- |
| `str` | `str(v: any) -> str` | 转字符串 |
| `int` | `int(v: any) -> int` | 转整数（可解析数字串） |
| `bool` | `bool(v: any) -> bool` | 转布尔 |
| `len` | `len(v: str\|list\|dict\|bytes) -> int` | 长度 |
| `if` | `if(cond: bool, a: any, b: any) -> any` | 条件选择 |
| `eq` | `eq(a: any, b: any) -> bool` | 相等判断 |
| `not` | `not(v: bool) -> bool` | 取反 |
| `add` | `add(a: int, b: int) -> int` | 加法 |
| `sub` | `sub(a: int, b: int) -> int` | 减法 |
| `mul` | `mul(a: int, b: int) -> int` | 乘法 |
| `div` | `div(a: int, b: int) -> int` | 整除（除零 → 错误） |
| `mod` | `mod(a: int, b: int) -> int` | 取模（除零 → 错误） |
| `bit_and` | `bit_and(a: int, b: int) -> int` | 位与 |
| `bit_or` | `bit_or(a: int, b: int) -> int` | 位或 |
| `bit_xor` | `bit_xor(a: int, b: int) -> int` | 位异或 |
| `bit_shift` | `bit_shift(v: int, n: int) -> int` | 左移（负 n 右移） |
| `now_unix` | `now_unix() -> int` | 当前 Unix 秒 |
| `now_iso` | `now_iso() -> str` | 当前 ISO8601 UTC |
| `random_int` | `random_int(min: int, max: int) -> int` | 区间随机整数 |
| `regex_extract` | `regex_extract(text: str, pattern: str) -> str` | 首个匹配（无命名组取 group 0）；走子进程执行，受 1s 超时与 10KB 上限约束（同 L1） |
| `regex_replace` | `regex_replace(text: str, pattern: str, repl: str) -> str` | 全部替换；同样走子进程 |
| `base64_encode` | `base64_encode(v: bytes) -> str` | Base64 编码 |
| `base64_decode` | `base64_decode(v: str) -> bytes` | Base64 解码 |
| `url_encode` | `url_encode(v: str) -> str` | URL 百分号编码 |
| `url_decode` | `url_decode(v: str) -> str` | URL 解码 |
| `hex_encode` | `hex_encode(v: bytes) -> str` | 十六进制编码 |
| `hex_decode` | `hex_decode(v: str) -> bytes` | 十六进制解码 |
| `utf8_encode` | `utf8_encode(v: str) -> bytes` | UTF-8 编码 |
| `utf8_decode` | `utf8_decode(v: bytes) -> str` | UTF-8 解码（非法序列 → 错误） |
| `json_encode` | `json_encode(v: any) -> str` | JSON 序列化 |
| `json_decode` | `json_decode(v: str) -> any` | JSON 解析（≤1MB） |
| `dict_get` | `dict_get(d: dict, key: str, default: any) -> any` | 取键（缺省返回 default） |
| `list_get` | `list_get(l: list, i: int, default: any) -> any` | 按下标取（越界返回 default） |
| `list_len` | `list_len(l: list) -> int` | 列表长度（等价 `len`） |
| `list_join` | `list_join(l: list, sep: str) -> str` | 字符串拼接 |
| `url_join` | `url_join(base: str, path: str) -> str` | URL 拼接（同 `urljoin` 语义） |
| `url_query` | `url_query(url: str, key: str) -> str` | 取查询参数 |
| `concat` | `concat(a: str, b: str) -> str` | 字符串连接 |

### 第二批（Phase 1.1b：加密原语）

| 原语 | 签名 | 说明 |
|:--- |:--- |:--- |
| `md5` | `md5(v: bytes) -> str` | MD5 十六进制摘要 |
| `sha1` | `sha1(v: bytes) -> str` | SHA-1 十六进制摘要 |
| `sha256` | `sha256(v: bytes) -> str` | SHA-256 十六进制摘要 |
| `hmac_sha256` | `hmac_sha256(key: bytes, msg: bytes) -> str` | HMAC-SHA256 十六进制 |
| `aes_cbc_encrypt` | `aes_cbc_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes` | AES-128-CBC 加密（ZeroPadding，与现网 `crypt.py` 一致） |
| `aes_cbc_decrypt` | `aes_cbc_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes` | AES-128-CBC 解密（ZeroPadding 去填充） |
| `xor` | `xor(a: bytes, b: bytes) -> bytes` | 字节逐位异或（长度取短者） |

加密原语为纯计算，无密钥存储（密钥来自规则字面量或上层注入，见 §5 `permissions`）。

## 5. 引擎约束（Phase 1.2）

| 约束 | 值 | 说明 |
|:--- |:--- |:--- |
| 纯函数无状态 | — | 无变量赋值、无循环、无副作用；表达式为函数调用树 |
| 单值大小 | ≤1MB | 任何中间值超过 → 求值中止 |
| 步间数据 | ≤2MB | `steps` 相邻步传递数据总量上限 |
| 表达式深度 | ≤32 | 嵌套调用深度超限 → 错误 |
| 求值调用数 | ≤1000 | 全规则原语调用总数超限 → 中止 |
| steps 数 | ≤8 | 单规则步骤上限 |
| 循环原语 | 无 | 不提供 map/while/filter 等可迭代执行原语 |
| 字节串 | 显式 | 无隐式 str↔bytes 转换 |
| 异常 | 不暴露细节 | 统一 `evaluation_error`，不泄露堆栈/内部路径 |

`steps` 为顺序管道：`{"steps": [{"fn": "...", "args": [...]}, ...]}`，前一步输出作为后一步首参。无分支/循环控制流。

## 6. schema v2 与运行时分流（Phase 1.3）

新增字段（`ott-rule-v2.schema.json`）：

```json
{
  "rule": {
    "request": {"url": "...", "method": "POST", "headers": {}, "body": "..."},
    "steps": [{"fn": "sha256", "args": [{"ref": "body"}]}],
    "permissions": {"network": ["https://api.example.com"]},
    "rights": {"min_api_level": 1}
  }
}
```

- `request.body`：无 `steps` 时为字面量，有 `steps` 时经管道构造。body 类型规范化：str/bytes 直传、dict/list → JSON 序列化、int/bool 字符串化、其余类型规则拒绝。`{"ref": "body"}` 引用 body 字面量作为 steps 输入。
- `steps` 输出经 `request.body` 模板构造请求体；`Content-Type` 等 HTTP 头必须由规则在 `request.headers` 显式声明（`httpx content=` 不自动添加 JSON 头）。
- `permissions.network`：域名白名单（子域匹配），**声明时生效**——URL 不在白名单内整条规则拒绝；未声明回退 `validate_url` 基线。
- `rights.min_api_level`：客户端低于声明 API level 时整条规则标记不兼容。
- 校验拒绝：`transform` 与 `steps` 并存、未知原语、steps 超限（MAX_STEPS/MAX_CALLS/1MB）。

## 7. 极速杯迁移验证（Phase 1.4，mock 验证完成 2026-08-07；真实站点验证挂起）

- 新 `tests/fixtures/rule-samples/jisubei.json`：用 DSL 表达极速杯请求并跑通 mock，零引擎改动。
- **实现要点**：
  - `request.body: null` + 单步全嵌套表达式：`base64_encode(aes_cbc_encrypt(utf8_encode(KEY), utf8_encode(IV), utf8_encode(json 模板)))` → `regex_replace("^." → "")` 去 base64 首字符 → 嵌套 `concat` 拼 `{"0": "..."}`。
  - 因 `aes_cbc_encrypt` 的 data 非首参，**不能**用多步管道（会前置首参）；`body: null` 时 `run_steps` 首步不前置，单步全嵌套表达式可直接求值。
  - key/iv 为二进制 16 字节，JSON 只能以 str 表达 → 用 `utf8_encode("c9ec834c80f77237")` 还原字节。
  - `timestamp` 用 `str(now_unix())` 经 concat 注入；payload 为 ASCII → `utf8_encode` 与参考脚本 `latin-1` 编码字节等价。
  - **零填充差异（已确认可接受）**：参考脚本 `_zero_pad` 对齐时跳过填充；DSL `_zero_pad` 恒补满块。本 payload 长度 mod 16 = 15，两种实现均补 1 字节，结果一致。若未来 payload 恰好 16 字节对齐，两实现相差一个整块，需要求值器对齐参考行为。
  - 响应明文：`msg["0"]` 为正文、`msg["a_name"]` 为标题；`extract: {"title": "$.msg.a_name", "content": "$.msg.0"}`（`_navigate_parts` 用 `current.get(part)`，数字键 `$.msg.0` 按字符串键取）。
  - `request.headers` 显式声明 `Content-Type: application/json`（对应参考脚本 `json=post_payload`，schema v2 要求 body 类型由规则声明）。
  - `permissions.network: ["www.jsxiaoshi.com"]` + `rights.min_api_level: 2`（`CLIENT_API_LEVEL=2`，federation 装配已传 `api_level=CLIENT_API_LEVEL`）。
- 验证：`TestJisubeiRule`（`tests/test_ott_rule_interpreter.py`）patch `time.time` 固定时间戳，字节级断言请求体与参考脚本算法一致，并断言响应提取。
- 验收：mock 服务端收到与现网一致格式的请求体（字节级等价）；组合矩阵用例全过。

## 8. 安全边界（复用 L1 红线）

- 求值器为纯函数白名单执行：未知原语、未声明 `permissions` 的 URL、超限值一律拒绝。
- 正则原语复用 0.B1 子进程方案（1s 超时 + 10KB 上限 + 嵌套量词静态拒绝）。
- 无文件 I/O、无子进程、无网络原语——网络仅通过规则 `request` 声明发生，受 `permissions.network` 约束。
- 加密原语密钥来自规则字面量：规则作者自持密钥风险自担（与 L3 脚本沙箱同等级信任模型）。
- 异常统一 `evaluation_error`，不泄露实现细节。

## 9. 评审与排期

本设计文档评审通过后：

1. Phase 1.1a 基础原语 → 1.1b 加密原语（`ott_dsl.py` 纯函数求值器）
2. Phase 1.2 引擎约束落地 + 资源上限测试
3. Phase 1.3 schema v2 + 运行时分流
4. Phase 1.4 极速杯 mock 验证（前置：jsxiaoshi.com 许可确认）
5. Phase 1.5 组合安全测试（矩阵 + 模糊测试断言资源上限）

---

## 待评审问题（已定案 2026-08-07）

1. **AES 密钥位宽** → 固定 128（现网 `crypt.py` 16 字节密钥 `c9ec834c80f77237`，ZeroPadding 非 PKCS7，已同步原语签名）
2. **`request.body` 模板** → `{ref}` 字符串模板（简单可读，静态可校验）
3. **加密密钥注入** → 仅规则字面量（YAGNI，注入通道后议）
4. **极速杯抓取许可** → mock 验证已确认（字节级 AES 请求体与参考脚本一致）；真实站点可用性/抓取许可仍待确认（ADR-011 待确认项 3）
