# CATIA 参数化图形生成器

> **开发方式声明**
> 本项目全程由作者与 **DSH（DeepSeek Harness，AI 编程助手）** 协作开发完成：
> 需求定义、几何方案决策、实机验证由作者负责；代码编写、缺陷定位与文档撰写
> 由 AI 助手在作者指导下完成。所有代码均经作者在 CATIA V5 上实机验证。
> 使用本项目产生的任何结果，请自行评估其适用性。

用 Python 驱动 CATIA V5，参数化生成 **n 棱锥 / n 棱台 / n 棱柱 / 圆锥 / 圆台 / 圆柱**，
并支持 **斜置**（轴线不垂直于截面）、**任意基准面**、**任意底面轮廓**。

不是六套算法，而是**同一个参数族**在不同参数下的特例——所以内核只有一份几何代码。

```
V_i(t) = C₀ + t·h·N + [1 + t(k−1)]·(x_i·u + y_i·v) + t·p
          └─ 沿法向分层 ─┘ └─ 位似缩放 ─┘        └ 平面内错位
```

- `h` 垂直高、`k` 位似比（顶面/底面）、`p` 顶面在截面平面内的错位
- `k = 0` 锥、`0 < k < 1` 台、`k = 1` 柱、`k > 1` 倒台
- `p = 0` 正置、`p ≠ 0` 斜置（侧面仍是平面梯形，照样能出实体）

---

## 功能

| 能力 | 说明 |
|---|---|
| 六种基本体 | n 棱锥 / n 棱台 / n 棱柱 / 圆锥 / 圆台 / 圆柱 |
| 斜置 | 顶面中心在截面平面内错位 `(pu, pv)`，使顶面与底面的投影不重合 |
| 任意基准面 | 标准面（XY/YZ/ZX）／原点 + 法向／三点确定 |
| 任意轮廓 | 正 n 边形／星形／顶点表（直角坐标或极坐标，自动统一绕向） |
| 驱动量互换 | 外接圆半径 R／边长 a／内切圆半径 r_in，三选一互相换算 |
| 输入校验 | 重合顶点、自交边对、凸性、侧面共面性、体积交叉校核 |
| 输出 | 实体或曲面；GSD 路线（Part Design 在本机不可用，见下） |

### 为什么界面没有"扭转角"

顶面相对底面做独立扭转（β ≠ 0）时，侧棱的增量方向 `D_{i+1} − D_i`
不再与底边 `e_i` 平行，于是侧面失去共面性、变成**双曲抛物面**，
无法封闭为实体，只能输出曲面。

而"顶面中心在截面平面内错开 `(pu, pv)`"已经完整覆盖了斜置这一需求，
并且 `D_{i+1} − D_i = (k−1)·e_i` 恒与底边平行，
**侧面永远是平面梯形，永远可以出实体**。

所以扭转是一个既多余、又会破坏实体的自由度，已被有意移除（不是遗漏）。
内核对外的 `twist_deg` 形参仍然保留，用于数学完整性与既有调用兼容，
但界面不再暴露它。

### 几何性质（决定了为什么这样做）

- **侧面恒为平面梯形**：`D_{i+1} − D_i = (k−1)·e_i` 恒与底边平行，共面判据恒成立。
  所以多边形族永远是精确多面体，不需要曲面拟合。
- **所有侧棱延长线共点**：交点 `S = C₀ + h·N/(1−k)`。棱锥/棱台/棱柱本质是
  同一个锥被两个截面截断，`k` 只是描述截平面位置的另一种写法。
- **凸轮廓 + 位似顶面 ⟹ 实体恒为凸体**，任意 `k` / `p` / `h` 都不会自交。
- **只要顶面是底面的均匀位似 + 平面内平移，侧面就必然共面。**
  能破坏共面性的只有三件事：独立扭转、独立顶面轮廓、各向异性缩放。
  内核会检出并报告非共面面号，**绝不静默产出错误几何**。

---

## 环境要求

| 项目 | 要求 |
|---|---|
| CATIA | V5 或 V5-6R（已在 V5-6R2021 / B31, win_b64 上实测） |
| Python | 3.11+，**必须 64 位**（与 CATIA 位数一致） |
| 依赖 | `pycatia`、`PySide6`、`pywin32` |

```powershell
python -m pip install pycatia PySide6 pywin32
```

> 注意：CATIA 必须已经启动。`pycatia` 通过 COM 连接正在运行的 CATIA 实例，
> 它不会替你启动 CATIA。

---

## 快速开始

### 方式一：直接运行源码

```powershell
python main_v2.py
```

双击 `start.bat` 效果相同（无控制台窗口）；出问题请用 `start_debug.bat`，报错会留在屏幕上。

### 方式二：使用打包好的单文件 EXE

双击 `CATIA_Prismatoid_Generator.exe`。单文件版启动需要 5–10 秒，属正常现象。

### 使用步骤

1. 启动 CATIA V5，新建或打开一个 **Part** 文档
2. 运行本插件，选择「生成多边形拟柱体」或「生成圆形拟柱体」
3. 填参数 → 确定 → 回 CATIA 按 `Ctrl+U` 更新视图

---

## 参数说明

| 参数 | 含义 |
|---|---|
| 垂直高 h | 两个平行截面平面的**垂直间距**，不是轴长 |
| 缩放比 k | 顶面对底面的均匀位似比；`k=0` 即锥 |
| 错位 pu / pv | 顶面中心相对底面中心在截面平面内的错位（斜置就靠它） |
| 扭转角 β | 顶面绕平面原点扭转；`≠0` 会让侧面失去共面性 |
| 基准面 | 标准面 / 原点+法向 / 三点确定 |
| 轮廓 | 正 n 边形（R）／星形（Ro, Ri）／顶点表 |
| 输出类型 | 实体 / 曲面 |

三种"高"务必分清：**垂直高 `h`**（两截面法向距离）≠ 轴长 ≠ 侧棱长。
体积公式只用到 `h`：

```
V = h/6 · (S₁ + 4M + S₂)          拟柱体通用公式
```

---

## 自检

### 1. 纯数学自检（不需要 CATIA，10 秒）

```powershell
python -c "
from catia_controller_v2 import *
ps = PlaneSpec.from_named('XY')
prof = Profile.regular(7, 40.0)
sec = build_prismatoid(ps, prof, 60.0, 0.4, (13.0, -7.0), 0.0, None)
print('非共面面：', side_planarity_report(sec['bottom'], sec['top']))
d = derive_prismatoid(ps, prof, 60.0, 0.4, (13.0, -7.0), 0.0, None)
print('体积校核比：', d['volume_ratio'])
"
```

期望输出：`非共面面：[]`、`体积校核比：1.0`。

### 2. 能力自检（需要 CATIA）

```powershell
python diagnose_v2.py
```

期望：**22 / 22 全部通过**。

> 自检会在 CATIA 中新建并关闭若干**空** Part 文档（不保存）。
> 跑之前请先保存手头正在编辑的文档：一个特征失败后该文档会进入错误状态，
> 后续更新全部连带失败，所以自检必须每个用例用全新文档。

### 3. 图形界面

```powershell
python main_v2.py
```

---

## 打包

```powershell
.\build.bat
```

`build.bat` 会先打包，然后自动对 EXE 做一次启动冒烟测试（约 12 秒，
测试期间会打开并自动关闭插件窗口）。只打包不测试则运行 `build_once.bat`。

产物为单文件 `CATIA_Prismatoid_Generator.exe`。若要换成带文件夹的 `--onedir` 模式，
把 `build_once.bat` 里的 `set "ONEFILE=1"` 改成 `0`。

把 `app.ico` 放在脚本同目录即可自动使用为图标。

### 脚本如何找到 Python

`.bat` 都按以下顺序探测解释器，支持路径含空格，也支持环境变量覆盖：

1. `%PYTHON_EXE%`（无控制台启动用 `%PYTHONW_EXE%`）环境变量
2. 脚本同目录下的 `python.exe` / `pythonw.exe`（便携版布局）
3. `py -3` / `pyw -3` 启动器（python.org 安装包自带）—— **多数机器走这条**
4. 扫描 `PATH`，但**每个候选都必须真的跑通 `import sys` 才会被采用**

**脚本刻意区分"启动器"和"真实 exe 路径"两种调用形态**：

```bat
py -3 -c "import sys"              rem 启动器：绝对不能加引号
"C:\Program Files\...\python.exe"  rem 真实路径：必须加引号（可能含空格）
```

### 四个已经踩过的 `.bat` 陷阱

这些坑都很隐蔽，改脚本前请先读这一节。它们全部已在当前脚本中规避。

**坑 1：中文会让批处理解析崩坏**

`cmd.exe` 按**当前代码页**（简体中文 Windows 通常是 GBK/936）按字节读取批处理文件。
`.bat` 存成 UTF-8 时，其中的中文变成无效字节序列，会把**同一行的命令字符一起吃掉**：

```
'cho' is not recognized as an internal or external command
'e.bat"' is not recognized as an internal or external command
'f' is not recognized as an internal or external command
```

注意 `echo` 变成了 `cho`、`if` 变成了 `f` —— 脚本会以极难定位的方式崩掉。

> 规定：**`.bat` 只允许 ASCII，注释也用英文。** 中文说明写在 `.md` 文件里
> （UTF-8，不受代码页影响）。

**坑 2：`where python` 会匹配路径片段**

`where python` 不只看文件名，只要 PATH 上任何一层目录名含 `python`
（例如项目放在 `...\CATIA Python 工作目录\...`），它就会返回一个**被截断的无效路径**。
只靠"排除 WindowsApps"拦不住这种情况。

> 对策：候选解释器必须真的执行 `import sys` 成功才被采用。

**坑 3：`for /f` 不能嵌在 `if (...)` 括号块里**

下面这种写法会让 cmd 解析器崩掉：

```bat
if not defined PY (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PY set "PY=%%~fP"
    )
)
```

报错信息是极具误导性的 `Edit was unexpected at this time.` ——
解析器错位之后，把后续提示文案里的 `Edit this file` 当成了命令。

> 对策：改用 `goto` 标签 + `call` 子程序；括号块内只保留最简单的
> `if` / `echo` / `set`。

**坑 4：`py` 启动器不能被引号包住**

```bat
"py" -3 -c "import sys"      rem 失败
py -3 -c "import sys"        rem 正常
```

被引号包住时 `py.exe` 会把"被引用的自身"当成文件名，再拼到自己的目录上，
于是报出这个看起来很奇怪的错误：

```
Unable to create process using 'C:\...\Python311\py" -c "import sys"'
```

因为多数机器都走第 3 条探测路径（`py -3`），这个坑会让脚本**必然失败**。
旧版脚本对 `%PY%` 一律加引号，就正好踩中。

> 对策：用一个 `PYLAUNCH` 标志区分两种形态，分别用加引号／不加引号的调用方式。

---

## 项目结构

```
main_v2.py                 图形界面（PySide6）
catia_controller_v2.py     几何内核 + CATIA 接口 + 能力自检用例
diagnose_v2.py             命令行能力自检
rthook_log.py              PyInstaller 运行时钩子：崩溃写入 launch_log.txt
build.bat                  打包 + 冒烟测试
build_once.bat             仅打包
start.bat                  无控制台启动
start_debug.bat            带控制台启动（排错用）
CHANGELOG.md               变更记录
```

内核对外接口：

```python
create_prismatoid(plane, profile, height, k, offset, twist_deg,
                  output_solid, allow_nonplanar, backend) -> Result
create_circular_prismatoid(plane, radius, height, k, offset,
                           output_solid, backend) -> Result

Result: .object / .is_solid / .used_backend / .diagnostics / .derived
PlaneSpec: from_named / from_point_normal / from_three_points
Profile:   regular / star / from_xy / from_polar
```

---

## 已知限制

1. **点不能作为放样截面。**
   `add_section_to_loft(点, 1, 空)` 不报错，但随后 Update 必失败。
   所以 `k = 0` 的锥体/棱锥一律用**极小顶面近似**：顶面尺寸 =
   `CONE_TOP_EPS_REL × R`（默认 `1e-3`，R=50 时约 0.05 mm），
   体积相对误差约 **0.1%**，肉眼不可见。圆与多边形两条路线都是这么处理的。
   探查函数 `probe_point_section()` 会持续监测；若将来 CATIA 支持点截面，
   把 `CONE_MODE` 切到 `"point"` 即可。

2. **Part Design 路线的 Pad 不可用。**
   `add_new_pad` / `add_new_pad_from_ref` 对 `k=1` 的纯圆柱也返回 `E_FAIL`；
   且 pycatia 的 `Pad/Prism` 继承链未暴露拔模角接口。故本机只用 GSD 路线。

3. **派生量按理想 `k` 计算。**
   `k=0` 时界面显示的体积是精确的数学真值（`S₁h/3`），而实际几何体积比它
   大约 0.1%（因为顶面是极小截面而非真正的点）。**这是有意为之，请勿"修正"。**

4. **扭转 / 独立顶面轮廓 / 各向异性缩放会破坏侧面共面性**，此时只能输出曲面。

5. **凹轮廓配大 offset 可能出现侧面互相穿插。** 体积交叉校核会报警，
   需目视复核（自检里的「扭转 20°」用例比值 0.92635，就是这种情况的示例）。

---

## 开发约定（改代码前请先读）

- **空的 Loft / Fill 一旦入树，会让整文档 Update 失败** → 先配置、后入树
- 对 COM 对象调用 `dir()` 会抛 `E_FAIL` → 必须用 `_public_names()` 包裹
- 一个特征失败后该文档进入错误状态，后续 Update 全部连带失败
  → **自检必须每个用例用全新文档**
- 存在多份代码副本时会互相遮蔽 → 用 `version_info()` + 同目录检查识别
- `k=0` 的近似逻辑**两条路线必须同源**（都走 `plan_cone()`），
  否则会出现"圆锥能画、棱锥画不出来"这类只影响一类图形的缺陷

---

## 许可证

[MIT](LICENSE) —— 你可以自由使用、修改、再分发（包括商用），
只需保留版权声明。本项目的依赖 `pycatia` 同样采用 MIT，兼容性最好。

> **上传前请做一件事**：把 `LICENSE` 第一行的 `<YOUR NAME>`
> 替换成你的名字或 GitHub 用户名。

---

## 致谢

- [pycatia](https://github.com/evereux/pycatia) —— CATIA V5 的 Python 接口
- 几何方案参考 CATIA 官方 GSD（创成式外形设计）的放样 / 填充 / 封闭能力
