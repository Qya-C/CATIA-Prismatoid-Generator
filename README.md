# CATIA 参数化图形生成器

用 Python 驱动 CATIA V5，参数化生成 **n 棱锥 / n 棱台 / n 棱柱 / 圆锥 / 圆台 / 圆柱**，
并支持 **斜置**（轴线不垂直于截面）、**任意基准面**、**任意底面轮廓**。

本仓库只提供**源码**，不含打包好的 EXE。需要 EXE 请按各版本目录里的说明自行运行 `build.bat`。

---

## 核心思路：六种体是同一个参数族

n 棱锥 / n 棱台 / n 棱柱 / 圆锥 / 圆台 / 圆柱不是六套算法，而是同一个
"两平行截面 + 直纹侧面"参数族在不同参数下的特例，因此内核只有一份几何代码。

```
V_i(t) = C₀ + t·h·N + [1 + t(k−1)]·(x_i·u + y_i·v) + t·p
          └─ 沿法向分层 ─┘ └─ 位似缩放 ─┘        └ 平面内错位
```

| 参数 | 含义 |
|---|---|
| `h` | 两个平行截面平面的**垂直间距**（不是轴长） |
| `k` | 顶面相对底面的均匀位似比 |
| `p = (pu, pv)` | 顶面中心在截面平面内的错位 —— **斜置的来源** |

| 缩放比 `k` | 棱边体 | 回转体 |
|---|---|---|
| `k = 0` | n 棱锥 | 圆锥 |
| `0 < k < 1` | n 棱台 | 圆台 |
| `k = 1` | n 棱柱 | 圆柱 |
| `k > 1` | 倒台（上大下小） | 倒台 |

### 三条关键几何性质

- **侧面恒为平面梯形**：`D_{i+1} − D_i = (k−1)·e_i` 恒与底边平行，共面判据恒成立。
  所以多边形族永远是**精确多面体**，不需要曲面拟合。
- **所有侧棱延长线共点**：交点 `S = C₀ + h·N/(1−k)`。棱锥/棱台/棱柱本质上是
  同一个锥被两个截面截断，`k` 只是描述截平面位置的另一种写法。
- **凸轮廓 + 位似顶面 ⟹ 实体恒为凸体**，任意 `k` / `p` / `h` 都不会自交。

> 只要顶面是底面的**均匀位似 + 平面内平移**，侧面就必然共面、必然能出实体。
> 能破坏共面性的只有三件事：独立扭转、独立顶面轮廓、各向异性缩放。

---

## 版本

| 版本 | 目录 | 状态 | 能力 |
|---|---|---|---|
| **v2.0** | [`versions/v2.0`](versions/v2.0) | **现役 / 推荐** | 斜置、任意基准面（标准面 / 原点+法向 / 三点确定）、任意轮廓（正 n 边形 / 星形 / 顶点表）、四类输入校验、可自由缩放的界面 |
| v1.0 | [`versions/v1.0`](versions/v1.0) | 已冻结（保留供对照） | 六种图形，底面限正 n 边形或圆，基准面限 XY/YZ/ZX |

**新用户请直接用 v2.0。** v1.0 是早期版本，保留是为了对照旧行为，不再更新。

各版本目录内都有自己的 `README.md` 与 `CHANGELOG.md`。

---

## 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows |
| CATIA | V5 或 V5-6R（已在 V5-6R2021 / B31, win_b64 上实测） |
| Python | 3.11+，**必须 64 位**（与 CATIA 位数一致） |
| 依赖 | `pycatia`、`PySide6`、`pywin32` |

```powershell
python -m pip install pycatia PySide6 pywin32
```

> CATIA 必须**已经启动**。`pycatia` 通过 COM 连接正在运行的 CATIA 实例，
> 它不会替你启动 CATIA。

---

## 快速开始（以 v2.0 为例）

```powershell
cd versions/v2.0

REM 方式一：直接运行源码
python main_v2.py

REM 方式二：双击 start.bat（无控制台窗口）
REM 出问题时用 start_debug.bat，报错会留在屏幕上

REM 方式三：先自检
python diagnose_v2.py          REM 需要 CATIA，期望 22/22 通过
```

使用步骤：启动 CATIA → 新建或打开一个 **Part** 文档 → 运行本插件 →
填参数 → 确定 → 回 CATIA 按 `Ctrl+U` 更新视图。

打包成单文件 EXE：

```powershell
build.bat
```

---

## 仓库结构

```
README.md                  本文件
LICENSE                    MIT
.gitignore
versions/
    v1.0/                  已冻结的旧版
        catia_controller_v1.py
        main.py
        diagnose_v1.py
        rthook_log.py
        build.bat / start.bat / start_debug.bat
    v2.0/                  现役版
        catia_controller_v2.py     几何内核
        main_v2.py                 图形界面（PySide6）
        diagnose_v2.py             命令行能力自检
        rthook_log.py              PyInstaller 崩溃日志钩子
        build.bat / build_once.bat 打包
        start.bat / start_debug.bat 启动
        README.md / CHANGELOG.md
```

---

## 已知限制

1. **点不能作为放样截面。** `add_section_to_loft(点, 1, 空)` 不报错，但随后 Update 必失败。
   所以 `k = 0` 的锥体/棱锥一律用**极小顶面近似**：顶面尺寸 = `CONE_TOP_EPS_REL × R`
   （默认 `1e-3`，R=50 时约 0.05 mm），体积相对误差约 **0.1%**，肉眼不可见。

2. **Part Design 路线的 Pad 不可用。** `add_new_pad` / `add_new_pad_from_ref`
   对 `k=1` 的纯圆柱也返回 `E_FAIL`；且 pycatia 的 `Pad/Prism` 继承链未暴露拔模角接口。
   故只用 GSD 路线。

3. **派生量按理想 `k` 计算。** `k=0` 时界面显示的体积是精确的数学真值（`S₁h/3`），
   而实际几何体积比它大约 0.1%（顶面是极小截面而非真正的点）。**这是有意为之，请勿"修正"。**

4. **凹轮廓配大 offset 可能出现侧面互相穿插。** 体积交叉校核会报警，需目视复核。

---

## 许可证

[MIT](LICENSE) —— 可自由使用、修改、再分发（含商用），只需保留版权声明。
依赖 `pycatia` 同样采用 MIT。

## 致谢

- [pycatia](https://github.com/evereux/pycatia) —— CATIA V5 的 Python 接口
- 几何方案参考 CATIA 官方 GSD（创成式外形设计）的放样 / 填充 / 封闭能力
