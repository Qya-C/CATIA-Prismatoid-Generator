# 变更记录

本文件是 1.0.0（首个冻结版）的变更记录。
1.0.1 的变更记录见 [`../1.0.1/CHANGELOG.md`](../1.0.1/CHANGELOG.md)。

---

> **开发方式声明**
> 本项目全程由作者与 **DSH（DeepSeek Harness，AI 编程助手）** 协作开发完成：
> 需求定义、几何方案决策、实机验证由作者负责；代码编写、缺陷定位与文档撰写
> 由 AI 助手在作者指导下完成。所有代码均经作者在 CATIA V5 上实机验证。
> 使用本项目产生的任何结果，请自行评估其适用性。


## [1.0.0] — 2026-09-20 · 首个冻结版本

支持生成六种参数化图形，底面为**正 n 边形**或**圆**：

| 缩放比 k | 棱边体 | 回转体 |
|---|---|---|
| `k = 0` | n 棱锥 | 圆锥 |
| `0 < k < 1` | n 棱台 | 圆台 |
| `k = 1` | n 棱柱 | 圆柱 |
| `k > 1` | 倒台（上大下小） | 倒台 |

### 输入参数

| 参数 | 说明 |
|---|---|
| 基准面 | XY / YZ / ZX 三个坐标平面 |
| 基准点 | 底面中心坐标 (x, y, z) |
| 边数 n | ≥ 3 的整数；**拓扑参数，创建后不可改** |
| 驱动量 | 外接圆半径 R / 边长 a / 内切圆半径 r_in，**三选一**，互相换算 |
| 垂直高 h | 两平行截面平面的垂直间距（**不是轴长**） |
| 缩放比 k | 顶面对底面的位似比；`k=0` 自动识别为锥体 |
| 输出类型 | 实体 / 曲面 |
| 生成方式 | 自动（GSD）/ GSD / Part Design（本机不可用） |

### 派生量（只读显示）

底面积、顶面积、体积、侧棱长、半锥角、锥顶距底面距离、拔模角。

体积公式（只用到垂直高 h）：

```
V = h/3 · (S₁ + S₂ + √(S₁·S₂))      其中 S₂ = k²·S₁
k=1 → V = S₁·h        k=0 → V = S₁·h/3
```

### 几何内核

统一仿射映射，六种图形共用同一条代码路径：

```
Q_i = C₀ + h·N + k·(P_i − C₀)
```

固定约定：缩放中心 = 基准点 C₀；顶面沿用底面平面基；轮廓绕向统一逆时针。

### 已验证基线

主能力自检 **11/11 通过**（每个用例在全新空 Part 中隔离执行）：

- 3 项底层能力：点与直线、圆（轴线在前签名）、Fill（add_bound）
- 7 项六种图形实体：六棱柱、六棱台、六棱锥、三棱台、圆柱、圆台、圆锥
- 1 项曲面路径：六棱柱（不封闭）

点截面探查 2/2 不可用（符合预期，见已知限制 1）。

### 已知限制

1. **点不能作为放样截面。** 见 2.0.0 已知限制 1。
2. **Part Design 的 Pad 不可用。** 见 2.0.0 已知限制 2。
3. **派生量按理想 k 计算。** 见 2.0.0 已知限制 3。

### 冻结的公共接口

以下接口的函数签名与语义在 2.0.0 之前不再变更：

```
create_polyhedron(n, radius, height, k, output_solid=False, plane="XY",
                  base_point=(0,0,0), backend="auto") -> Result
create_circular_solid(radius, height, k, output_solid=False, plane="XY",
                      base_point=(0,0,0), backend="auto") -> Result
Result: .object / .is_solid / .used_backend / .diagnostics / .derived
derive_polygon / derive_circular
side_length / inradius / radius_from_side / radius_from_inradius / draft_angle_deg
run_diagnostics / probe_point_section / dump_signatures / version_info
PLANE_KEYS / PLANE_LABELS / BACKEND_KEYS / BACKEND_LABELS
StageError
```

### 工程约束（开发时务必遵守）

同 2.0.0。

### 规划中（未实现）

- 斜柱 / 斜台 / 斜锥：顶面中心在截面平面内错位（`p ≠ 0`），入口为
  `add_new_extrude(obj, debut, fin, direction)` → **2.0.0 已实现**
- 倾斜截面（用平面切割，得到直角梯形类形体）
- 自由顶点表（非正 n 边形轮廓） → **2.0.0 已实现**
- 扭转（`β ≠ 0`）：会破坏侧面平面性，需改构造路线 → **2.0.0 已实现（输出曲面）**
