# v1.0.0 —— 已冻结

> **这是早期版本，保留仅供对照，不再更新。新项目请用 [`../v2.0`](../v2.0)。**

## 能力范围

支持生成六种参数化图形，底面为**正 n 边形**或**圆**：

| 缩放比 k | 棱边体 | 回转体 |
|---|---|---|
| `k = 0` | n 棱锥 | 圆锥 |
| `0 < k < 1` | n 棱台 | 圆台 |
| `k = 1` | n 棱柱 | 圆柱 |
| `k > 1` | 倒台（上大下小） | 倒台 |

基准面限 XY / YZ / ZX 三个坐标平面及其平行面。

## 与 v2.0 的区别

v2.0 在此基础上增加了：

- **斜置**：顶面中心在截面平面内错位 `(pu, pv)`
- **任意基准面**：标准面 / 原点 + 法向 / 三点确定
- **任意轮廓**：星形、顶点表（直角坐标或极坐标）
- 四类输入校验：重合顶点、自交边对、凸性、体积交叉校核
- 修复了 `k=0` 多边形棱锥无法生成实体的缺陷

v1.0 的 `twist_deg` 参数在 v2.0 中已从界面移除（它会让侧面变成双曲抛物面、
无法封闭为实体）。

## 文件

| 文件 | 说明 |
|---|---|
| `catia_controller_v1.py` | 几何内核 + CATIA 接口 + 能力自检用例 |
| `main.py` | 图形界面 |
| `diagnose_v1.py` | 命令行能力自检（期望 11/11 通过） |
| `rthook_log.py` | PyInstaller 运行时钩子：崩溃写入 `launch_log.txt` |
| `build.bat` | 打包成单文件 EXE |
| `start.bat` / `start_debug.bat` | 启动脚本 |

## 运行

```powershell
python main.py            REM 直接运行
python diagnose_v1.py     REM 能力自检（需要 CATIA，期望 11/11）
build.bat                 REM 打包成 EXE
```

需要 CATIA V5 已启动 + Python 3.11 (64 位) + `pycatia` / `PySide6` / `pywin32`。

## 变更记录

见 [CHANGELOG.md](CHANGELOG.md)。
