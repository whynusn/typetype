"""运行时版本单一事实源（ADR-014 决策 1）。

版本有两处来源，职责分工如下：

- ``pyproject.toml`` 的 ``version`` 是**构建期**版本源（打包元数据）。
- 本模块的 ``APP_VERSION`` 是**运行期**版本源——Nuitka 独立产物内不可读
  pyproject.toml，必须内联一个常量供 OTA 更新检查（update_checker.py）使用。

发布流程（build-release.yml）须断言两者一致，防止版本漂移：

- 发布 tag（``v*``）== ``APP_VERSION``；
- ``pyproject.toml`` version == ``APP_VERSION``。

改动版本号时两处必须同步修改。
"""

APP_VERSION = "0.1.0"
