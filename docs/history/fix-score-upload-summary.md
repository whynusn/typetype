# 成绩上传修复 - 实施总结

## 分支：`fix/score-upload-pipeline`

## 问题现象
1. 打开应用不点"载文"直接打字 → 成绩上传失败
2. 上传"示例文本"后直接打字 → 成绩上传失败
3. 只有手动"载文"后才能正常上传成绩

## 根因分析（3 轮子代理评审确认）

### 根因 1：UpperPane 过早调用 handleLoadedText
`UpperPane.qml` 的 `Component.onCompleted` 在文本加载完成前就调用了
`handleLoadedText`，启用了打字（readOnly=False）。此时 `text_id` 尚未设置
（仍为 0），用户在默认文本上打完字后，`_submit_score` 检查 `text_id <= 0`
直接 return，成绩被静默跳过。

### 根因 2：上传结果 ID 被丢弃
`UploadTextAdapter._do_upload_cloud` 收到服务端返回的真实文本 ID，但只是
log 了一下就丢弃了。`uploadFinished` 信号只携带 `(bool, str)`，没有 text_id。
用户上传后继续打字，`text_id` 始终为 None。

### 根因 3：加载失败时错误地启用了打字
`onTextLoadFailed` 调用 `applyLoadedText(message)`，把错误消息当作可打字
文本，并启用了打字。用户在错误消息上打字，成绩无法提交。

## 修复方案

### Commit 1: `129ab6a` - 时序和 ID 传递
| 文件 | 修改 |
|------|------|
| `UpperPane.qml` | 移除 `Component.onCompleted` 中的 `handleLoadedText` 调用 |
| `UploadTextAdapter` | `uploadFinished` 信号新增 `int` 参数传递服务端文本 ID |
| `UploadTextAdapter._do_upload_cloud` | 返回 `result_id` 而非丢弃 |
| `TypingPage.qml` | 新增 `onUploadResult` 监听，云端上传成功时自动 `setTextId` |
| `UploadTextPage.qml` | 信号处理适配新签名 |

### Commit 2: `3f4d9f2` - 高优先级修复
| 文件 | 修改 |
|------|------|
| `Bridge.uploadText` | 异常路径 `emit` 补齐第三个 `int` 参数 |
| `TypingPage.qml` | `onTextLoadFailed` 不再调用 `applyLoadedText` |

## 修改文件清单
```
src/backend/presentation/adapters/upload_text_adapter.py  | 18 +++---
src/backend/presentation/bridge.py                        |  4 +-
src/qml/pages/TypingPage.qml                              | 15 ++++-
src/qml/pages/UploadTextPage.qml                          |  2 +-
src/qml/typing/UpperPane.qml                              |  8 +--
```
共 5 文件，+31/-16 行

## 验证结果
- ✅ 87 测试全部通过
- ✅ ruff lint 全部通过
- ✅ ruff format 全部通过
- ✅ 3 轮子代理评审确认修复完整

## 场景覆盖
| 场景 | 状态 | 说明 |
|------|------|------|
| A: 打开应用直接打字 | ✅ | sync 加载完成后才启用打字 |
| B: 上传到云端后打字 | ✅ | 上传 ID 通过信号传递到 setTextId |
| C: 加载失败 | ✅ | 不启用打字，保持 readOnly |
| D: 服务端未知 sourceKey | ✅ | 回退到 "custom"，hash 查找一致 |

## 架构合规性
- ✅ 未引入 hash 计算到 Adapter 层
- ✅ source_key 不进入成绩提交链路
- ✅ Presentation 未直接依赖 Integration
- ✅ 只有服务端存在的文本才能提交成绩
