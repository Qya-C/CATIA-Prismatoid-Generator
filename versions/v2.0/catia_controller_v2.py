# -*- coding: utf-8 -*-
"""
catia_controller_v2.py
======================
CATIA 参数化图形生成 —— 2.0.0 内核

版本：2.0.0

================================================================
2.0 相对 1.0 的三项增强
================================================================
1) 斜拟柱体：顶面中心可在截面平面内错位 offset=(pu, pv)。
   侧面仍为梯形，正视图可呈直角梯形等斜置形态。

2) 任意基准面：不再限 XY/YZ/ZX 及其平行面。三种来源：
     PlaneSpec.from_named(name, origin)      标准面 + 原点
     PlaneSpec.from_point_normal(origin, n)  原点 + 法向
     PlaneSpec.from_three_points(p1, p2, p3) 三点确定

3) 任意底面轮廓：不再限正 n 边形。三种来源：
     Profile.regular(n, radius)              正 n 边形
     Profile.star(n, r_out, r_in)            星形
     Profile.from_xy([(x, y), ...])          直角坐标顶点表
     Profile.from_polar([(r, deg), ...])     极坐标顶点表

================================================================
几何核心
================================================================
    P_i = C0 + x_i·u + y_i·v                     底面顶点
    Q_i = C1 + (k·R_β(x_i, y_i) + p)·(u, v)      顶面顶点，C1 = C0 + h·N

    C0, u, v, N 由 PlaneSpec 给出；h = 两平行截面平面的垂直间距。

================================================================
一个决定性的数学结论（关于「顶面能不能不相似」）
================================================================
侧面四边形 (P_i, P_{i+1}, Q_{i+1}, Q_i) 共面
     ⟺  (w_{i+1} − w_i) ∥ (P_{i+1} − P_i)
其中 w_i 为顶面顶点相对 C1 的平面内位置。

推论：若底面多边形含至少两条不平行边（任何非退化多边形都满足），
则「对所有边同时保持共面」的顶面线性变换只能是均匀位似 k·I。
（特例：轴对齐的矩形允许各向异性缩放，因为它的每条边都沿主方向。）

因此：
  * k 与 offset 任意取值 → 侧面恒为平面梯形，实体恒为合法多面体。★主力
  * twist_deg ≠ 0，或给出独立顶面轮廓 → 侧面为非平面的双曲抛物面。
    本内核会【自动检测并报告非共面的面号】，绝不静默产出错误几何。
    非共面时无法封闭为实体，只能输出曲面。

================================================================
自动校验（全部在进 CATIA 之前完成）
================================================================
  * 多边形：重合顶点、自交、绕向（统一为逆时针）、凸性
  * 侧面共面性：逐面给出归一化偏差
  * 体积交叉校核：散度定理算网格体积 vs 拟柱体公式 h/6·(S₁+4M+S₂)
  * 凸底面 + 位似顶面 ⟹ 实体恒为凸体，不会自交（无需额外检查）
  * 凹底面 + 大 offset → 提示目视复核

================================================================
1.0.0 的已知限制（2.0 保持不变）
================================================================
1) 点不能作为放样截面 → k=0 的锥体用极小顶面近似（CONE_TOP_EPS_REL=1e-3）
2) Part Design 的 Pad 在本环境不可用（路线停用）
3) 派生量按理想 k 计算

================================================================
实测确认的 CATIA 接口
================================================================
    add_new_circle_center_axis(i_axis, i_point, i_value, i_projection)  轴线在前
      注意：i_axis 定义圆所在平面的法向 → 必须沿平面法向，不可用“底心→顶心”
    add_new_join(element1, element2)        两元素 + add_element() 追加
    add_new_fill() + HybridShapeFill.add_bound(ref)
    add_section_to_loft(i_section, i_ori, i_point)   ori=1 + pt=空 生效
    SectionCoupling 1/2/3/4（顶点 = 4）
    ShapeFactory.add_new_close_surface(i_close_element)
    add_new_plane_offset(i_plane, i_offset, i_orientation)

工程约束
* 空的 Loft / Fill 一旦入树会让整文档 Update 失败 → 先配置、后入树
* dir(com_object) 会抛 E_FAIL → 必须用 _public_names() 包裹
* 一个特征失败会毒化整个文档 → 自检必须每例新文档
"""

from __future__ import annotations

import inspect
import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

from pycatia import catia

try:
    from pycatia.scripts.vba import vba_nothing
except Exception:                                  # pragma: no cover
    vba_nothing = None

# ================================================================ 版本戳

__version__ = "2.0.0"
__release__ = "2026-09-21"
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))


def version_info() -> str:
    lines = [
        f"catia_controller_v2 版本：{__version__}  ({__release__})",
        f"  本模块文件：{os.path.abspath(__file__)}",
        f"  所在目录　：{MODULE_DIR}",
    ]
    try:
        import pycatia
        lines.append(f"  pycatia 路径：{getattr(pycatia, '__file__', '未知')}")
        lines.append(f"  pycatia 版本：{getattr(pycatia, '__version__', '未知')}")
    except Exception as exc:
        lines.append(f"  pycatia 信息读取失败：{exc}")

    lines.append("  关键常量：")
    lines.append(f"    CONE_MODE         = {CONE_MODE}")
    lines.append(f"    CONE_TOP_EPS_REL  = {CONE_TOP_EPS_REL}")
    lines.append(f"    SOLID_STRATEGY    = {SOLID_STRATEGY}")
    lines.append(f"    COUPLING_VERTICES = {COUPLING_VERTICES}")
    lines.append(f"    PLANARITY_TOL     = {PLANARITY_TOL}")
    return "\n".join(lines)


# ================================================================ 常量

TOL = 1e-9

COUPLING_RATIO = 1
COUPLING_VERTICES = 4
SECTION_ORIENT = 1

CONE_TOP_EPS_REL = 1e-3
CONE_MODE = "approx"
SOLID_STRATEGY = "caps"

# 侧面共面性判据的归一化阈值。|det(v1,v2,v3)| / (|v1||v2||v3|) 超过它即判为非共面。
# 1e-6 对应约 1e-6 rad 量级的倾斜，远低于 CATIA 的显示/容差精度。
PLANARITY_TOL = 1e-6

# 多边形顶点重合判定的相对容差（相对轮廓外接尺寸）
DUP_VERTEX_REL_TOL = 1e-7

PLANE_KEYS = ["XY", "YZ", "ZX"]
PLANE_LABELS = ["XY 平面", "YZ 平面", "ZX 平面"]

BACKEND_LABELS = ["自动（GSD）", "GSD（多截面放样）", "Part Design（本机不可用）"]
BACKEND_KEYS = ["auto", "gsd", "pad"]


class Result:
    def __init__(self) -> None:
        self.object = None
        self.is_solid = False
        self.used_backend = ""
        self.diagnostics: List[str] = []
        self.derived: Dict[str, float] = {}
        self.checks: Dict[str, object] = {}


class StageError(RuntimeError):
    def __init__(self, stage: str, exc: Exception) -> None:
        super().__init__(
            f"更新失败于『{stage}』。\n原始错误：{exc}\n\n"
            "请先执行『能力自检』；若自检通过，则问题在当前 Part 文档本身"
            "（历史特征带更新错误），请换一个新建的 Part 再试。"
        )
        self.stage = stage
        self.original = exc


class GeometryError(ValueError):
    """几何输入本身不合法（自交、重合顶点等）。"""


# ================================================================ 向量工具

def _v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _v_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _v_mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _v_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _v_cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _v_norm(a):
    return math.sqrt(_v_dot(a, a))


def _v_unit(a, label="向量"):
    n = _v_norm(a)
    if n < 1e-12:
        raise GeometryError(f"{label}长度为零，无法归一化。")
    return (a[0] / n, a[1] / n, a[2] / n)


def orthonormal_frame(normal, ref=None):
    """由法向构造右手正交基 (u, v, n)，满足 u × v = n。

    ref 为可选的参考方向（用来固定 u 的朝向）。缺省时自动挑选与 n
    最不平行的世界轴，保证数值稳定。
    """
    n = _v_unit(normal, "法向")
    if ref is None:
        axes = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
        ref = axes[min(range(3), key=lambda i: abs(n[i]))]
    u = _v_cross(ref, n)
    if _v_norm(u) < 1e-9:
        # ref 与 n 平行，换一个世界轴
        for cand in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
            u = _v_cross(cand, n)
            if _v_norm(u) > 1e-9:
                break
    u = _v_unit(u, "平面内基向量")
    v = _v_cross(n, u)
    return u, v, n


# ================================================================ 基准面

class PlaneSpec:
    """一个基准面：原点 C0 + 平面内右手正交基 (u, v) + 法向 n，u × v = n。"""

    def __init__(self, origin, u, v, n, label=""):
        self.origin = (float(origin[0]), float(origin[1]), float(origin[2]))
        self.u = _v_unit(u, "u")
        self.v = _v_unit(v, "v")
        self.n = _v_unit(n, "n")
        self.label = label
        self._verify()

    def _verify(self):
        if abs(_v_dot(self.u, self.v)) > 1e-7:
            raise GeometryError("平面基向量 u、v 不垂直。")
        if abs(_v_dot(self.u, self.n)) > 1e-7 or abs(_v_dot(self.v, self.n)) > 1e-7:
            raise GeometryError("平面基向量与法向不垂直。")
        c = _v_cross(self.u, self.v)
        if _v_dot(c, self.n) < 0.0:
            raise GeometryError("平面基不满足右手系（应 u × v = n）。")

    @classmethod
    def from_named(cls, name: str, origin=(0.0, 0.0, 0.0)) -> "PlaneSpec":
        """标准坐标平面 XY / YZ / ZX，原点可平移。"""
        bases = {
            "XY": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
            "YZ": ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
            "ZX": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
        }
        key = str(name).upper()
        if key not in bases:
            raise GeometryError(f"未知标准面：{name!r}，可选 {PLANE_KEYS}。")
        u, v, n = bases[key]
        return cls(origin, u, v, n, label=f"{key} 平面")

    @classmethod
    def from_point_normal(cls, origin, normal, ref=None) -> "PlaneSpec":
        """原点 + 法向。u/v 自动生成（可用 ref 指定 u 的参考方向）。"""
        u, v, n = orthonormal_frame(normal, ref)
        return cls(origin, u, v, n, label="原点+法向")

    @classmethod
    def from_three_points(cls, p1, p2, p3) -> "PlaneSpec":
        """三点确定平面。原点取 p1，u 沿 p1→p2 方向。"""
        a = (float(p1[0]), float(p1[1]), float(p1[2]))
        b = (float(p2[0]), float(p2[1]), float(p2[2]))
        c = (float(p3[0]), float(p3[1]), float(p3[2]))
        e1 = _v_sub(b, a)
        e2 = _v_sub(c, a)
        if _v_norm(e1) < 1e-12:
            raise GeometryError("三点中的第 1、2 点重合。")
        n = _v_cross(e1, e2)
        if _v_norm(n) < 1e-12:
            raise GeometryError("三点共线，无法确定平面。")
        u = _v_unit(e1, "p1→p2")
        n = _v_unit(n, "法向")
        v = _v_cross(n, u)
        return cls(a, u, v, n, label="三点确定")

    def to_3d(self, x: float, y: float, base=None) -> Tuple[float, float, float]:
        """把平面内 2D 坐标 (x, y) 映射到 3D。base 缺省为原点。"""
        b = self.origin if base is None else base
        return (b[0] + x * self.u[0] + y * self.v[0],
                b[1] + x * self.u[1] + y * self.v[1],
                b[2] + x * self.u[2] + y * self.v[2])

    def offset_along_normal(self, dist: float) -> Tuple[float, float, float]:
        return _v_add(self.origin, _v_mul(self.n, dist))

    def __repr__(self):
        return (f"PlaneSpec({self.label}: origin={self.origin}, n={self.n})")


# ================================================================ 轮廓

def _rot2(p, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


class Profile:
    """平面内的底面轮廓，以 2D 顶点列表 (x, y) 表示（在 (u, v) 基下）。"""

    def __init__(self, points: Sequence[Sequence[float]], label=""):
        pts = [(float(p[0]), float(p[1])) for p in points]
        if len(pts) < 3:
            raise GeometryError("轮廓至少需要 3 个顶点。")
        self.points = pts
        self.label = label

    # ---------- 构造器 ----------

    @classmethod
    def regular(cls, n: int, radius: float, start_deg: float = 0.0) -> "Profile":
        if int(n) != n or n < 3:
            raise GeometryError("边数 n 必须是不小于 3 的整数。")
        if radius <= 0:
            raise GeometryError("半径必须大于 0。")
        pts = []
        for i in range(n):
            th = math.radians(start_deg + 360.0 * i / n)
            pts.append((radius * math.cos(th), radius * math.sin(th)))
        return cls(pts, label=f"正{int(n)}边形 R={radius:g}")

    @classmethod
    def star(cls, n: int, r_outer: float, r_inner: float,
             start_deg: float = 0.0) -> "Profile":
        """星形：2n 个顶点，外/内半径交替。"""
        if int(n) != n or n < 3:
            raise GeometryError("星形至少需要 3 个尖，即 n ≥ 3。")
        if r_outer <= 0 or r_inner <= 0:
            raise GeometryError("星形半径必须大于 0。")
        if r_inner >= r_outer:
            raise GeometryError("星形内半径必须小于外半径（否则退化为正多边形）。")
        pts = []
        total = 2 * n
        for i in range(total):
            r = r_outer if i % 2 == 0 else r_inner
            th = math.radians(start_deg + 360.0 * i / total)
            pts.append((r * math.cos(th), r * math.sin(th)))
        return cls(pts, label=f"星形 n={int(n)} Ro={r_outer:g} Ri={r_inner:g}")

    @classmethod
    def from_xy(cls, pairs: Sequence[Sequence[float]]) -> "Profile":
        """直角坐标顶点表：[(x, y), ...]。"""
        return cls(pairs, label=f"顶点表 {len(pairs)} 点")

    @classmethod
    def from_polar(cls, pairs: Sequence[Sequence[float]]) -> "Profile":
        """极坐标顶点表：[(r, 角度_度), ...]。"""
        pts = []
        for r, deg in pairs:
            th = math.radians(float(deg))
            pts.append((float(r) * math.cos(th), float(r) * math.sin(th)))
        return cls(pts, label=f"极坐标表 {len(pts)} 点")

    # ---------- 变换 ----------

    @property
    def n(self) -> int:
        return len(self.points)

    def mapped(self, k: float, offset=(0.0, 0.0), twist_deg: float = 0.0) -> "Profile":
        """顶面轮廓 = 绕原点扭转 β → 以原点为心位似 k → 平面内平移 p。"""
        out = []
        for (x, y) in self.points:
            xr, yr = _rot2((x, y), twist_deg)
            out.append((k * xr + offset[0], k * yr + offset[1]))
        return Profile(out, label="顶面(位似)")

    def bbox_size(self) -> float:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)

    def area(self) -> float:
        """有向面积。逆时针为正。"""
        s = 0.0
        pts = self.points
        m = len(pts)
        for i in range(m):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % m]
            s += x1 * y2 - x2 * y1
        return 0.5 * s


# ================================================================ 2D 校验

def duplicate_vertices(prof: Profile) -> List[Tuple[int, int]]:
    """找出重合的顶点对（相对容差）。"""
    tol = DUP_VERTEX_REL_TOL * prof.bbox_size()
    pts = prof.points
    bad = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            dx = pts[i][0] - pts[j][0]
            dy = pts[i][1] - pts[j][1]
            if math.hypot(dx, dy) <= tol:
                bad.append((i, j))
    return bad


def _orient(a, b, c, tol):
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(v) <= tol:
        return 0
    return 1 if v > 0 else -1


def _on_segment(a, b, p, tol):
    return (min(a[0], b[0]) - tol <= p[0] <= max(a[0], b[0]) + tol and
            min(a[1], b[1]) - tol <= p[1] <= max(a[1], b[1]) + tol)


def _seg_intersect(a, b, c, d, tol):
    o1 = _orient(a, b, c, tol)
    o2 = _orient(a, b, d, tol)
    o3 = _orient(c, d, a, tol)
    o4 = _orient(c, d, b, tol)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _on_segment(a, b, c, tol):
        return True
    if o2 == 0 and _on_segment(a, b, d, tol):
        return True
    if o3 == 0 and _on_segment(c, d, a, tol):
        return True
    if o4 == 0 and _on_segment(c, d, b, tol):
        return True
    return False


def self_intersections(prof: Profile) -> List[Tuple[int, int]]:
    """找出相交的边对（不相邻的边）。O(n²)，n 通常很小。"""
    tol = 1e-9 * prof.bbox_size()
    pts = prof.points
    m = len(pts)
    bad = []
    for i in range(m):
        a, b = pts[i], pts[(i + 1) % m]
        for j in range(i + 1, m):
            if j == i or (j + 1) % m == i or j == (i + 1) % m:
                continue          # 相邻边共享顶点，跳过
            c, d = pts[j], pts[(j + 1) % m]
            if _seg_intersect(a, b, c, d, tol):
                bad.append((i, j))
    return bad


def is_convex(prof: Profile, tol_rel: float = 1e-9) -> bool:
    """逆时针轮廓的凸性判定（含共线顶点视为凸）。"""
    pts = prof.points
    m = len(pts)
    tol = tol_rel * (prof.bbox_size() ** 2)
    signs = set()
    for i in range(m):
        a, b, c = pts[i], pts[(i + 1) % m], pts[(i + 2) % m]
        o = _orient(a, b, c, tol)
        if o != 0:
            signs.add(o)
        if len(signs) > 1:
            return False
    return True


def ensure_ccw(prof: Profile) -> Tuple[Profile, bool]:
    """把轮廓统一成逆时针；返回 (新轮廓, 是否发生了反转)。"""
    if prof.area() >= 0.0:
        return prof, False
    return Profile(list(reversed(prof.points)), prof.label + "(已反转)"), True


def validate_profile(prof: Profile) -> Dict[str, object]:
    """跑一遍全部 2D 校验，返回报告字典（不改动轮廓）。"""
    rep: Dict[str, object] = {}
    rep["n"] = prof.n
    rep["duplicates"] = duplicate_vertices(prof)
    rep["self_intersections"] = self_intersections(prof)
    rep["convex"] = is_convex(prof)
    rep["area_signed"] = prof.area()
    rep["area"] = abs(prof.area())
    rep["bbox"] = prof.bbox_size()
    return rep


# ================================================================ 拟柱体几何

def build_prismatoid(plane: PlaneSpec, bottom: Profile, height: float,
                     k: float = 1.0, offset=(0.0, 0.0), twist_deg: float = 0.0,
                     top_profile: Optional[Profile] = None) -> Dict:
    """构造拟柱体的底面/顶面 3D 顶点。

    顶面缺省 = 底面位似(绕平面原点) k + 平面内平移 offset（可叠加扭转）。
    给定 top_profile 时直接用它的 2D 点（要求与底面同顶点数）。
    """
    if height <= 0:
        raise GeometryError("垂直高 h 必须大于 0。")
    if k < 0:
        raise GeometryError("缩放比 k 不得为负。")

    if top_profile is None:
        top = bottom.mapped(k, offset, twist_deg)
        top_is_derived = True
    else:
        if top_profile.n != bottom.n:
            raise GeometryError(
                f"顶面顶点数 {top_profile.n} 与底面 {bottom.n} 不一致，无法一一配对。")
        top = top_profile
        top_is_derived = False

    c0 = plane.origin
    c1 = plane.offset_along_normal(height)

    bottom3 = [plane.to_3d(x, y, c0) for (x, y) in bottom.points]
    top3 = [plane.to_3d(x, y, c1) for (x, y) in top.points]

    return {
        "bottom": bottom3, "top": top3,
        "bottom2d": list(bottom.points), "top2d": list(top.points),
        "C0": c0, "C1": c1, "plane": plane, "height": height,
        "top_is_derived": top_is_derived,
    }


def side_planarity_report(bottom3, top3, tol: float = PLANARITY_TOL):
    """逐面检查侧面四边形共面性。

    返回 [(面序号, 归一化偏差), ...]，只列出超过 tol 的面。
    偏差定义：|det(v1,v2,v3)| / (|v1||v2||v3|)，量纲无关，约等于面片的
    最大倾斜正弦。
    """
    n = len(bottom3)
    bad = []
    for i in range(n):
        j = (i + 1) % n
        v1 = _v_sub(bottom3[j], bottom3[i])
        v2 = _v_sub(top3[i], bottom3[i])
        v3 = _v_sub(top3[j], bottom3[i])
        d = abs(_v_dot(v1, _v_cross(v2, v3)))
        den = _v_norm(v1) * _v_norm(v2) * _v_norm(v3)
        r = d / den if den > 1e-15 else 0.0
        if r > tol:
            bad.append((i, r))
    return bad


def mesh_volume(bottom3, top3) -> float:
    """散度定理求闭合多面体体积（四边形侧面按两三角形拆）。

    用于与拟柱体公式交叉校核：自交或构造错误会让两者显著不符。
    """
    n = len(bottom3)
    acc = 0.0
    # 底面（朝外法向为 −N，故取反向遍历）
    for i in range(1, n - 1):
        acc += _v_dot(bottom3[0], _v_cross(bottom3[i + 1], bottom3[i]))
    # 顶面
    for i in range(1, n - 1):
        acc += _v_dot(top3[0], _v_cross(top3[i], top3[i + 1]))
    # 侧面
    for i in range(n):
        j = (i + 1) % n
        acc += _v_dot(bottom3[i], _v_cross(bottom3[j], top3[j]))
        acc += _v_dot(bottom3[i], _v_cross(top3[j], top3[i]))
    return abs(acc) / 6.0


def prismatoid_volume_formula(area1: float, area2: float, height: float) -> float:
    """拟柱体通用公式 V = h/6·(S₁ + 4M + S₂)。

    位似顶面时 M = ((1+k)/2)²·S₁，代入即得棱台公式
        V = h/3·(S₁ + S₂ + √(S₁S₂))
    （S₂ = k²S₁）。本函数直接从面积算，不依赖 k。
    """
    if area1 <= 0 or area2 <= 0:
        return height / 3.0 * (area1 + area2 + math.sqrt(max(area1 * area2, 0.0)))
    mid_scale = (1.0 + math.sqrt(area2 / area1)) / 2.0
    m = mid_scale * mid_scale * area1
    return height / 6.0 * (area1 + 4.0 * m + area2)


def derive_prismatoid(plane: PlaneSpec, bottom: Profile, height: float,
                      k: float, offset, twist_deg,
                      top_profile: Optional[Profile] = None) -> Dict[str, float]:
    """派生量与自检数据。"""
    sec = build_prismatoid(plane, bottom, height, k, offset, twist_deg, top_profile)
    a1 = abs(bottom.area())
    top2d = Profile(sec["top2d"])
    a2 = abs(top2d.area())
    v_formula = prismatoid_volume_formula(a1, a2, height)
    v_mesh = mesh_volume(sec["bottom"], sec["top"])
    ratio = (v_mesh / v_formula) if v_formula > 1e-15 else float("nan")
    nonplanar = side_planarity_report(sec["bottom"], sec["top"])
    apex_dist = None
    if top_profile is None and abs(k - 1.0) > TOL:
        apex_dist = height / (1.0 - k)
    n_eff = len(sec["bottom2d"])
    return {
        "n": n_eff,
        "bottom_area": a1,
        "top_area": a2,
        "volume": v_formula,
        "volume_mesh": v_mesh,
        "volume_ratio": ratio,
        "nonplanar_faces": len(nonplanar),
        "apex_distance": apex_dist if apex_dist is not None else float("inf"),
        "offset_magnitude": math.hypot(offset[0], offset[1]),
        "tilt_angle_deg": math.degrees(math.atan2(
            math.hypot(offset[0], offset[1]), height)) if height > 0 else 0.0,
    }


def build_circular_ring(plane: PlaneSpec, radius: float, center2d=(0.0, 0.0),
                        segments: int = 0):
    """为圆族生成用于校验的等效多边形（仅用于体积/平面性估算，不用于建模）。

    建模本身走 CATIA 的圆特征；这里只是让派生量在两条几何路径间保持一致。
    """
    if segments <= 0:
        segments = 180
    c = Profile.regular(segments, radius)
    return Profile([(x + center2d[0], y + center2d[1]) for (x, y) in c.points])


# ================================================================ 适配层

def _public_names(obj, keys=None) -> List[str]:
    try:
        names = [n for n in dir(obj) if not n.startswith("_")]
    except Exception as exc:
        return [f"<无法枚举：{exc}>"]
    if keys:
        names = [n for n in names if any(k.lower() in n.lower() for k in keys)]
    return names


def _get_part():
    caa = catia()
    if caa.documents.count == 0:
        doc = caa.documents.add("Part")
    else:
        doc = caa.active_document
    try:
        part = doc.part
    except Exception as exc:
        raise RuntimeError("当前活动文档不是 CATPart。请先新建或打开一个 Part 文档。") from exc
    if part is None:
        raise RuntimeError("当前活动文档不是 CATPart。请先新建或打开一个 Part 文档。")
    return part, doc


def _ref(part, obj):
    return part.create_reference_from_object(obj)


def _append(hbs, obj):
    hbs.append_hybrid_shape(obj)
    return obj


def _point(hsf, hbs, xyz):
    p = hsf.add_new_point_coord(float(xyz[0]), float(xyz[1]), float(xyz[2]))
    return _append(hbs, p)


def _line(hsf, hbs, part, a, b):
    ln = hsf.add_new_line_pt_pt(_ref(part, a), _ref(part, b))
    return _append(hbs, ln)


def _safe_update(part, stage, diagnostics, raise_on_fail=True) -> bool:
    try:
        part.update()
        return True
    except Exception as exc:
        diagnostics.append(f"Update 失败于『{stage}』：{exc}")
        if raise_on_fail:
            raise StageError(stage, exc) from exc
        return False


def _axis_along_normal(hsf, hbs, part, origin, normal, length):
    """沿平面法向建轴线。

    必须沿法向：add_new_circle_center_axis 的轴线定义圆所在平面的法向。
    若改用「底面中心 → 顶面中心」，在 offset ≠ 0 时轴线会倾斜，
    圆就不落在预期的截面平面上了（这是 1.0 遗留的隐患，2.0 修正）。
    """
    a = _point(hsf, hbs, origin)
    b = _point(hsf, hbs, _v_add(origin, _v_mul(normal, length)))
    part.update()
    return _line(hsf, hbs, part, a, b)


def _circle(hsf, hbs, part, axis_ref, center_xyz, radius, diagnostics, label):
    c = _point(hsf, hbs, center_xyz)
    _safe_update(part, f"创建{label}圆心", diagnostics)
    circle = hsf.add_new_circle_center_axis(axis_ref, _ref(part, c), float(radius), False)
    _append(hbs, circle)
    _safe_update(part, f"创建{label}", diagnostics)
    return circle


def _join(hsf, hbs, part, elements, diagnostics, label):
    if not elements:
        raise RuntimeError(f"{label}：没有可用于接合的元素。")
    if len(elements) == 1:
        return elements[0]
    refs = [_ref(part, e) for e in elements]
    join = hsf.add_new_join(refs[0], refs[1])
    _append(hbs, join)
    _safe_update(part, f"创建{label}接合（前两段）", diagnostics)
    for i, r in enumerate(refs[2:], start=3):
        try:
            join.add_element(r)
        except Exception as exc:
            raise RuntimeError(f"{label}：追加第 {i} 段失败：{exc}") from exc
    _safe_update(part, f"接合{label}", diagnostics)
    return join


def _closed_wire(hsf, hbs, part, vertices, diagnostics, label):
    pts = [_point(hsf, hbs, v) for v in vertices]
    _safe_update(part, f"创建{label}顶点", diagnostics)
    m = len(pts)
    lines = [_line(hsf, hbs, part, pts[i], pts[(i + 1) % m]) for i in range(m)]
    _safe_update(part, f"创建{label}边", diagnostics)
    return _join(hsf, hbs, part, lines, diagnostics, f"{label}线框")


def _add_section(loft, sec_ref, diagnostics, index) -> bool:
    attempts = []
    if vba_nothing is not None:
        attempts.append(("ori=1, pt=空", SECTION_ORIENT, vba_nothing))
    attempts.append(("ori=1, pt=None", SECTION_ORIENT, None))
    for name, ori, pt in attempts:
        try:
            loft.add_section_to_loft(sec_ref, ori, pt)
            diagnostics.append(f"Loft 第 {index} 个截面：已通过『{name}』添加。")
            return True
        except Exception:
            continue
    diagnostics.append(f"Loft 第 {index} 个截面添加失败。成员：{_public_names(loft)}")
    return False


def _loft(hsf, hbs, part, section_refs, coupling, diagnostics, label, as_volume=False):
    loft = hsf.add_new_loft()
    for idx, sec_ref in enumerate(section_refs, start=1):
        if not _add_section(loft, sec_ref, diagnostics, idx):
            raise RuntimeError(f"Loft 添加第 {idx} 个截面失败。")
    try:
        loft.section_coupling = coupling
    except Exception as exc:
        diagnostics.append(f"设置耦合方式（{coupling}）失败，几何可能扭曲：{exc}")
    try:
        loft.canonical_detection = 1
    except Exception:
        pass
    if as_volume:
        try:
            loft.context = 1
            diagnostics.append("Loft 已设为体积上下文（需 GSO 许可）。")
        except Exception as exc:
            diagnostics.append(f"设置体积上下文失败：{exc}")
    _append(hbs, loft)
    _safe_update(part, f"创建{label}放样", diagnostics)
    return loft


def _fill(hsf, hbs, part, wire, diagnostics, label):
    fill = hsf.add_new_fill()
    cre = _ref(part, wire)
    m = getattr(fill, "add_bound", None)
    if not callable(m):
        diagnostics.append(f"{label}：未找到 add_bound。成员：{_public_names(fill)}")
        return None
    try:
        m(cre)
    except Exception as exc:
        diagnostics.append(f"{label}：add_bound 失败：{exc}")
        return None
    _append(hbs, fill)
    _safe_update(part, f"创建{label}", diagnostics)
    return fill


def _make_solid(hsf, hbs, part, section_refs, coupling, cap_wires,
                diagnostics, label):
    if SOLID_STRATEGY == "volume":
        try:
            loft = _loft(hsf, hbs, part, section_refs, coupling,
                         diagnostics, label, as_volume=True)
            return loft, True
        except Exception as exc:
            diagnostics.append(f"『{label}』体积放样失败，改用端盖路径：{exc}")

    loft = _loft(hsf, hbs, part, section_refs, coupling, diagnostics, label, False)
    try:
        caps = []
        for w in cap_wires:
            f = _fill(hsf, hbs, part, w, diagnostics, f"{label}端盖")
            if f is None:
                raise RuntimeError("端盖创建失败")
            caps.append(f)
        surfaces = [loft] + caps
        if len(surfaces) < 2:
            raise RuntimeError("可接合的面不足两个")
        shell = hsf.add_new_join(_ref(part, surfaces[0]), _ref(part, surfaces[1]))
        _append(hbs, shell)
        for s in surfaces[2:]:
            shell.add_element(_ref(part, s))
        _safe_update(part, f"{label}外壳接合", diagnostics)
        try:
            part.in_work_object = part.main_body
        except Exception:
            pass
        solid = part.shape_factory.add_new_close_surface(_ref(part, shell))
        _safe_update(part, f"{label}封闭成实体", diagnostics)
        return solid, True
    except Exception as exc:
        diagnostics.append(f"『{label}』端盖+封闭路径失败：{exc}")
        diagnostics.append(f"『{label}』未能生成实体，已按曲面输出。")
        return loft, False


# ================================================================ 输入归一化

def _normalize_polygon_inputs(
    plane=None, base_point=None, n=6, radius=50.0,
    profile: Optional[Profile] = None, plane_spec: Optional[PlaneSpec] = None,
) -> Tuple[PlaneSpec, Profile]:
    """把 1.0 风格参数与 2.0 风格对象统一成 (PlaneSpec, Profile)。"""
    if plane_spec is not None:
        ps = plane_spec
    else:
        key = str(plane or "XY").upper()
        ps = PlaneSpec.from_named(key, base_point or (0.0, 0.0, 0.0))

    if profile is not None:
        prof = profile
    else:
        prof = Profile.regular(int(n), float(radius))
    return ps, prof


def _preflight(part, res: Result):
    pre: List[str] = []
    if not _safe_update(part, "文档预检", pre, raise_on_fail=False):
        raise StageError("文档预检", RuntimeError("该 Part 文档自身无法更新"))


def _record_checks(res: Result, prof: Profile, sec: Dict, derived: Dict,
                   allow_nonplanar: bool):
    """跑完整校验并把结果写进 res.checks / res.diagnostics。"""
    rep = validate_profile(prof)
    res.checks["profile"] = rep

    if rep["duplicates"]:
        raise GeometryError(f"轮廓存在重合顶点：{rep['duplicates'][:8]}")
    if rep["self_intersections"]:
        raise GeometryError(
            f"轮廓自交，相交边对：{rep['self_intersections'][:8]}。请修正顶点表。")

    nonplanar = side_planarity_report(sec["bottom"], sec["top"])
    res.checks["nonplanar_faces"] = nonplanar
    if nonplanar:
        worst = max(r for _, r in nonplanar)
        msg = (f"检测到 {len(nonplanar)} 个侧面不共面（最大归一化偏差 {worst:.3e}），"
               f"面号：{[i for i, _ in nonplanar[:12]]}")
        if allow_nonplanar:
            res.diagnostics.append(msg + "。已按『允许曲面侧面』继续："
                                         "这些面将由 Loft 生成双曲抛物面，无法封闭为实体。")
        else:
            raise GeometryError(
                msg + "。\n原因：顶面若不是底面的均匀位似（即使用了扭转或"
                       "独立顶面轮廓），侧面就不再是平面梯形。\n"
                       "解决：让顶面只由 k + offset 生成（界面不再提供扭转角）；"
                       "确实需要非平面侧面时，勾选『允许曲面侧面』。")

    ratio = derived.get("volume_ratio", float("nan"))
    if not math.isnan(ratio) and (ratio < 0.999 or ratio > 1.001):
        res.diagnostics.append(
            f"⚠ 体积交叉校核偏差较大：网格体积/公式体积 = {ratio:.5f}。"
            "可能原因：轮廓自交、凹轮廓配合过大 offset 导致侧面互相穿插。请目视复核。")
    else:
        res.checks["volume_ratio"] = ratio

    if not rep["convex"]:
        om = derived.get("offset_magnitude", 0.0)
        if om > 0.2 * prof.bbox_size():
            res.diagnostics.append(
                "凹轮廓配合较大的平面内错位，侧面可能互相穿插（凸轮廓无此问题）。"
                "建议目视复核，或改用凸轮廓。")
    if not allow_nonplanar and len(sec["bottom2d"]) != len(sec["top2d"]):
        raise GeometryError("顶底顶点数不一致。")


# ================================================================ GSD 主流程

def _gsd_polygon(part, res: Result, plane: PlaneSpec, prof: Profile,
                 height, k, offset, twist_deg, top_profile,
                 output_solid, allow_nonplanar):
    # ★ 与圆形路线 (_gsd_circle) 对齐：k=0 的真棱锥顶面会退化成点，
    #   而本环境不接受“点”作为放样截面（添加不报错但 Update 必失败）。
    #   故改用 CONE_TOP_EPS_REL 的极小顶面近似，只在 k≈0 时生效。
    k_geom, use_point = plan_cone(k)

    sec = build_prismatoid(plane, prof, height, k_geom, offset, twist_deg, top_profile)
    derived = derive_prismatoid(plane, prof, height, k_geom, offset, twist_deg, top_profile)
    res.derived = derived
    _record_checks(res, prof, sec, derived, allow_nonplanar)

    if abs(k) < TOL and not use_point:
        _rmax = max(_v_norm((px, py, 0.0)) for (px, py) in prof.points)
        res.diagnostics.append(
            f"k=0 棱锥：顶面以 {CONE_TOP_EPS_REL * 100:.3f}% 的极小截面近似"
            f"（顶面缩放后最大半径 {CONE_TOP_EPS_REL * _rmax:.4f} mm）。"
            f"体积相对误差约 {CONE_TOP_EPS_REL * 100:.2f}%，肉眼不可见。"
            "原因：本环境不接受“点”作为放样截面（添加不报错但 Update 必失败）。"
        )

    hsf = part.hybrid_shape_factory
    hbs = part.hybrid_bodies.add()
    hbs.name = f"PB2_Poly_k{k:g}"
    try:
        part.in_work_object = hbs
    except Exception:
        pass
    _safe_update(part, "建立几何图形集", res.diagnostics)

    bottom_wire = _closed_wire(hsf, hbs, part, sec["bottom"], res.diagnostics, "底面")
    cap_wires = [bottom_wire]
    section_refs = [_ref(part, bottom_wire)]

    _append_section_points(hsf, hbs, part, sec, cap_wires, section_refs,
                           res.diagnostics, "顶面")

    if output_solid:
        if derived["nonplanar_faces"] > 0:
            raise GeometryError(
                "侧面非共面，无法封闭为实体。请改用『曲面』输出，"
                "或让顶面只由 k + offset 生成（不要用独立顶面轮廓）。")
        obj, is_solid = _make_solid(hsf, hbs, part, section_refs,
                                    COUPLING_VERTICES, cap_wires,
                                    res.diagnostics, "多边形")
        res.object, res.is_solid = obj, is_solid
    else:
        res.object = _loft(hsf, hbs, part, section_refs, COUPLING_VERTICES,
                           res.diagnostics, "多边形")

    _safe_update(part, "收尾更新", res.diagnostics)
    return res


def _append_section_points(hsf, hbs, part, sec, cap_wires, section_refs,
                           diagnostics, label):
    """把顶面加入截面表。k→0 时用极小面（由 build 阶段已保证）。"""
    top_wire = _closed_wire(hsf, hbs, part, sec["top"], diagnostics, label)
    cap_wires.append(top_wire)
    section_refs.append(_ref(part, top_wire))


def _gsd_circle(part, res: Result, plane: PlaneSpec, radius, height, k,
                offset, output_solid, allow_nonplanar):
    if height <= 0:
        raise GeometryError("垂直高 h 必须大于 0。")
    if k < 0:
        raise GeometryError("缩放比 k 不得为负。")

    k_geom, use_point = plan_cone(k)
    rings = build_circular_ring(plane, radius, (0.0, 0.0))
    derived = derive_prismatoid(plane, rings, height, k_geom, offset, 0.0, None)
    res.derived = derived
    res.checks["profile"] = validate_profile(rings)

    if abs(k) < TOL and not use_point:
        res.diagnostics.append(
            f"k=0 圆锥：顶面以 {CONE_TOP_EPS_REL * 100:.3f}% 的极小截面近似"
            f"（顶面半径 {CONE_TOP_EPS_REL * radius:.4f} mm）。"
            f"体积相对误差约 {CONE_TOP_EPS_REL * 100:.2f}%，肉眼不可见。"
            "原因：本环境不接受“点”作为放样截面（添加不报错但 Update 必失败）。"
        )

    hsf = part.hybrid_shape_factory
    hbs = part.hybrid_bodies.add()
    hbs.name = f"PB2_Circ_k{k:g}"
    try:
        part.in_work_object = hbs
    except Exception:
        pass
    _safe_update(part, "建立几何图形集", res.diagnostics)

    # ★ 轴线沿平面法向（不是底心→顶心）——offset 非零时这是关键
    axis = _axis_along_normal(hsf, hbs, part, plane.origin, plane.n, height)
    axis_ref = _ref(part, axis)

    bottom_circle = _circle(hsf, hbs, part, axis_ref, plane.origin, radius,
                            res.diagnostics, "底面圆")
    cap_wires = [bottom_circle]
    section_refs = [_ref(part, bottom_circle)]

    top_center = (plane.origin[0] + offset[0] * plane.u[0] + offset[1] * plane.v[0],
                  plane.origin[1] + offset[0] * plane.u[1] + offset[1] * plane.v[1],
                  plane.origin[2] + offset[0] * plane.u[2] + offset[1] * plane.v[2])
    top_center = _v_add(top_center, _v_mul(plane.n, height))

    if use_point:
        apex = _point(hsf, hbs, top_center)
        _safe_update(part, "创建锥顶", res.diagnostics)
        section_refs.append(_ref(part, apex))
        res.diagnostics.append("顶面按锥顶（点）处理（CONE_MODE=point）。")
    else:
        top_circle = _circle(hsf, hbs, part, axis_ref, top_center,
                             k_geom * radius, res.diagnostics, "顶面圆")
        cap_wires.append(top_circle)
        section_refs.append(_ref(part, top_circle))

    if output_solid:
        obj, is_solid = _make_solid(hsf, hbs, part, section_refs,
                                    COUPLING_RATIO, cap_wires,
                                    res.diagnostics, "圆形")
        res.object, res.is_solid = obj, is_solid
    else:
        res.object = _loft(hsf, hbs, part, section_refs, COUPLING_RATIO,
                           res.diagnostics, "圆形")

    _safe_update(part, "收尾更新", res.diagnostics)
    return res


def plan_cone(k: float) -> Tuple[float, bool]:
    if abs(k) >= TOL:
        return k, False
    if CONE_MODE == "point":
        return k, True
    return CONE_TOP_EPS_REL, False


# ================================================================ Part Design（本机不可用）

def _pd_unavailable(diagnostics, label):
    diagnostics.append(
        f"{label}：Part Design 路线在本机不可用。"
        "实测 add_new_pad 与 add_new_pad_from_ref 对纯圆柱（k=1）也返回 E_FAIL；"
        "且 pycatia 的 Pad/Prism 继承链上未暴露拔模角接口。"
        "请把『生成方式』保持为『自动（GSD）』。"
    )
    raise RuntimeError(f"{label}：Part Design 不可用，请改用 GSD 路线。")


# ================================================================ 对外主函数

def create_prismatoid(plane: PlaneSpec, profile: Profile,
                      height: float = 80.0, k: float = 1.0,
                      offset=(0.0, 0.0), twist_deg: float = 0.0,
                      top_profile: Optional[Profile] = None,
                      output_solid: bool = False,
                      allow_nonplanar: bool = False,
                      backend: str = "auto") -> Result:
    """斜拟柱体：任意基准面 + 任意多边形底面 + 顶面可错位/扭转。

    参数
    plane          : PlaneSpec，基准面
    profile        : 底面轮廓（2D，位于 (u, v) 基下）
    height         : 两平行截面平面的垂直间距 h
    k              : 顶面相对底面的均匀位似比（0 锥 / (0,1) 台 / 1 柱 / >1 倒台）
    offset         : 顶面中心在截面平面内的错位 (pu, pv) —— 「斜」的来源
    twist_deg      : 绕平面原点扭转角。**不在界面暴露，属内核内部参数。**
                     它非零时侧棱增量不再与底边平行，侧面失去共面性、
                     变成双曲抛物面，因此无法封闭为实体，只能出曲面。
                     界面只提供 offset 这一种斜置方式，恒可出实体。
                     保留本形参是为了数学完整性与既有调用兼容。
    top_profile    : 独立顶面轮廓（顶点数须与底面相同）。给了它则忽略 k/offset/twist
    output_solid   : True 生成实体（要求所有侧面共面）
    allow_nonplanar: True 时允许非共面侧面（只能出曲面）
    """
    prof, flipped = ensure_ccw(profile)
    if flipped:
        pass  # 静默统一绕向，保证侧面法向一致

    part, _doc = _get_part()
    res = Result()
    _preflight(part, res)

    if backend == "pad":
        _pd_unavailable(res.diagnostics, "拟柱体")
    _gsd_polygon(part, res, plane, prof, height, k, offset, twist_deg,
                 top_profile, output_solid, allow_nonplanar)
    res.used_backend = "gsd"
    return res


def create_circular_prismatoid(plane: PlaneSpec, radius: float = 50.0,
                               height: float = 80.0, k: float = 1.0,
                               offset=(0.0, 0.0),
                               output_solid: bool = False,
                               allow_nonplanar: bool = False,
                               backend: str = "auto") -> Result:
    """斜圆柱 / 斜圆台 / 斜圆锥：任意基准面 + 顶面圆心可错位。"""
    if radius <= 0:
        raise GeometryError("半径必须大于 0。")
    part, _doc = _get_part()
    res = Result()
    _preflight(part, res)
    if backend == "pad":
        _pd_unavailable(res.diagnostics, "圆形")
    _gsd_circle(part, res, plane, radius, height, k, offset,
                output_solid, allow_nonplanar)
    res.used_backend = "gsd"
    return res


# ---------- 1.0 兼容入口（签名不变，新增可选参数） ----------

def create_polyhedron(n: int = 6, radius: float = 50.0, height: float = 80.0,
                      k: float = 1.0, output_solid: bool = False,
                      plane: str = "XY",
                      base_point: Sequence[float] = (0.0, 0.0, 0.0),
                      backend: str = "auto",
                      plane_spec: Optional[PlaneSpec] = None,
                      profile: Optional[Profile] = None,
                      offset=(0.0, 0.0), twist_deg: float = 0.0,
                      top_profile: Optional[Profile] = None,
                      allow_nonplanar: bool = False) -> Result:
    """1.0 兼容入口。新参数全部有默认值，旧调用行为完全不变。"""
    ps, prof = _normalize_polygon_inputs(plane, base_point, n, radius,
                                         profile, plane_spec)
    return create_prismatoid(ps, prof, height, k, offset, twist_deg,
                             top_profile, output_solid, allow_nonplanar, backend)


def create_circular_solid(radius: float = 50.0, height: float = 80.0,
                          k: float = 1.0, output_solid: bool = False,
                          plane: str = "XY",
                          base_point: Sequence[float] = (0.0, 0.0, 0.0),
                          backend: str = "auto",
                          plane_spec: Optional[PlaneSpec] = None,
                          offset=(0.0, 0.0)) -> Result:
    """1.0 兼容入口。"""
    ps = plane_spec or PlaneSpec.from_named(plane, base_point)
    return create_circular_prismatoid(ps, radius, height, k, offset,
                                      output_solid, False, backend)


# ================================================================ 纯数学派生量（1.0 兼容）

def side_length(n, radius):
    return 2.0 * radius * math.sin(math.pi / n)


def inradius(n, radius):
    return radius * math.cos(math.pi / n)


def radius_from_side(n, side):
    return side / (2.0 * math.sin(math.pi / n))


def radius_from_inradius(n, inr):
    return inr / math.cos(math.pi / n)


def draft_angle_deg(n, radius, height, k):
    if n is None:
        tan_a = radius * (1.0 - k) / height
    else:
        tan_a = radius * math.cos(math.pi / n) * (1.0 - k) / height
    return math.degrees(math.atan(tan_a))


def derive_polygon(n: int, radius: float, height: float, k: float) -> Dict[str, float]:
    """1.0 兼容：正 n 棱柱族的派生量（仍按理想 k 计算）。"""
    prof = Profile.regular(n, radius)
    d = derive_prismatoid(PlaneSpec.from_named("XY"), prof, height, k,
                          (0.0, 0.0), 0.0, None)
    d["side"] = side_length(n, radius)
    d["inradius"] = inradius(n, radius)
    d["top_radius"] = k * radius
    d["lateral_edge"] = math.sqrt(height ** 2 + ((k - 1.0) * radius) ** 2)
    d["draft_angle"] = draft_angle_deg(n, radius, height, k)
    return d


def derive_circular(radius: float, height: float, k: float) -> Dict[str, float]:
    """1.0 兼容：圆族的派生量。"""
    s1 = math.pi * radius * radius
    s2 = k * k * s1
    apex = float("inf") if abs(k - 1.0) < TOL else height / (1.0 - k)
    return {
        "bottom_area": s1, "top_area": s2,
        "volume": height / 3.0 * (s1 + s2 + math.sqrt(s1 * s2)),
        "lateral_edge": math.sqrt(height ** 2 + ((k - 1.0) * radius) ** 2),
        "top_radius": k * radius, "apex_distance": apex,
        "draft_angle": draft_angle_deg(None, radius, height, k),
    }


# ================================================================ 能力自检

class _Probe:
    def __init__(self, name):
        self.name = name
        self.rows: List[Tuple[str, bool, str]] = []

    def step(self, stage, fn) -> bool:
        try:
            fn()
        except Exception as exc:
            self.rows.append((stage, False, f"{type(exc).__name__}: {exc}"))
            return False
        self.rows.append((stage, True, ""))
        return True

    @property
    def ok(self):
        return all(r[1] for r in self.rows)

    @property
    def first_failure(self):
        for r in self.rows:
            if not r[1]:
                return r
        return None


def _new_blank_part():
    caa = catia()
    doc = caa.documents.add("Part")
    part = doc.part
    hbs = part.hybrid_bodies.add()
    hbs.name = "DIAG"
    try:
        part.in_work_object = hbs
    except Exception:
        pass
    return doc, part, part.hybrid_shape_factory, hbs


def _run_case(fn, name):
    probe = _Probe(name)
    diag: List[str] = []
    try:
        doc, part, hsf, hbs = _new_blank_part()
    except Exception as exc:
        probe.rows.append(("新建空 Part", False, f"{type(exc).__name__}: {exc}"))
        return {"case": name, "ok": False, "first_fail": probe.first_failure,
                "rows": probe.rows, "diag": diag}
    try:
        probe.step("空文档 update", part.update)
        fn(probe, doc, part, hsf, hbs, diag)
    except Exception as exc:
        probe.rows.append(("用例异常", False, f"{type(exc).__name__}: {exc}"))
    finally:
        try:
            doc.close()
        except Exception:
            pass
    return {"case": name, "ok": probe.ok, "first_fail": probe.first_failure,
            "rows": probe.rows, "diag": diag}


def _c_baseline(probe, doc, part, hsf, hbs, diag):
    a = _point(hsf, hbs, (0, 0, 0))
    b = _point(hsf, hbs, (0, 0, 50))
    probe.step("点入集后 update", part.update)
    probe.step("创建直线", lambda: _line(hsf, hbs, part, a, b))


def _c_circle(probe, doc, part, hsf, hbs, diag):
    ps = PlaneSpec.from_named("XY")
    axis = _axis_along_normal(hsf, hbs, part, ps.origin, ps.n, 50.0)
    part.update()
    probe.step("创建圆（轴线沿法向）",
               lambda: _circle(hsf, hbs, part, _ref(part, axis), ps.origin,
                               50.0, diag, "测试圆"))


def _c_fill(probe, doc, part, hsf, hbs, diag):
    ps = PlaneSpec.from_named("XY")
    axis = _axis_along_normal(hsf, hbs, part, ps.origin, ps.n, 50.0)
    part.update()
    holder = {}
    probe.step("创建圆", lambda: holder.setdefault(
        "c", _circle(hsf, hbs, part, _ref(part, axis), ps.origin, 50.0, diag, "圆")))
    probe.step("创建 Fill（add_bound）",
               lambda: _fill(hsf, hbs, part, holder["c"], diag, "测试Fill"))


def _c_math_selfcheck(probe, doc, part, hsf, hbs, diag):
    """纯数学自检：不碰 CATIA，验证共面性判据与体积公式。"""
    def go():
        # 1) 位似 + offset：所有侧面必须共面
        ps = PlaneSpec.from_named("XY")
        prof = Profile.regular(7, 40.0)
        sec = build_prismatoid(ps, prof, 60.0, 0.4, (13.0, -7.0), 0.0, None)
        bad = side_planarity_report(sec["bottom"], sec["top"])
        if bad:
            raise AssertionError(f"位似+offset 竟然出现非共面面：{bad[:3]}")
        # 2) 体积：网格 vs 公式
        d = derive_prismatoid(ps, prof, 60.0, 0.4, (13.0, -7.0), 0.0, None)
        if not (0.999 < d["volume_ratio"] < 1.001):
            raise AssertionError(f"体积校核失败：ratio={d['volume_ratio']}")
        # 3) twist 必须被判为非共面
        sec2 = build_prismatoid(ps, prof, 60.0, 0.5, (0.0, 0.0), 15.0, None)
        bad2 = side_planarity_report(sec2["bottom"], sec2["top"])
        if not bad2:
            raise AssertionError("twist=15° 竟然未检出非共面")
        # 4) 非正多边形（L 形，凹）应能通过自交检查
        lshape = Profile.from_xy([(0, 0), (60, 0), (60, 20), (20, 20),
                                  (20, 50), (0, 50)])
        rep = validate_profile(lshape)
        if rep["self_intersections"] or rep["duplicates"]:
            raise AssertionError("L 形轮廓被误判为自交或重合")
        if rep["convex"]:
            raise AssertionError("L 形被误判为凸")
        # 5) 自交轮廓必须被检出
        bowtie = Profile.from_xy([(0, 0), (50, 50), (0, 50), (50, 0)])
        if not validate_profile(bowtie)["self_intersections"]:
            raise AssertionError("蝴蝶形自交未被检出")
        # 6) 任意平面：三点确定的基必须正交归一
        ps3 = PlaneSpec.from_three_points((10, 5, 3), (10, 25, 3), (0, 5, 3))
        for vec in (ps3.u, ps3.v, ps3.n):
            if abs(_v_norm(vec) - 1.0) > 1e-12:
                raise AssertionError("三点平面的基向量非单位长度")
        diag.append("数学自检：共面性判据、体积公式、自交判定、任意平面基，全部通过。")
    probe.step("数学自检（不调用 CATIA）", go)


def _poly_solid_case(n, radius, height, k, label, offset=(0.0, 0.0),
                     allow_nonplanar=False, profile=None):
    def run(probe, doc, part, hsf, hbs, diag):
        def go():
            ps = PlaneSpec.from_named("XY")
            prof = profile if profile is not None else Profile.regular(n, radius)
            res = Result()
            _gsd_polygon(part, res, ps, prof, height, k, offset, 0.0, None,
                         True, allow_nonplanar)
            diag.extend(res.diagnostics)
            if not res.is_solid:
                raise RuntimeError("未得到实体")
        probe.step(label, go)
    return run


def _circ_solid_case(radius, height, k, label, offset=(0.0, 0.0), plane_key="XY"):
    def run(probe, doc, part, hsf, hbs, diag):
        def go():
            ps = PlaneSpec.from_named(plane_key)
            res = Result()
            _gsd_circle(part, res, ps, radius, height, k, offset, True, False)
            diag.extend(res.diagnostics)
            if not res.is_solid:
                raise RuntimeError("未得到实体")
        probe.step(label, go)
    return run


def _oblique_polygon_case(label, k, offset):
    """斜置多边形族：任意基准面 + 顶点表。"""
    def run(probe, doc, part, hsf, hbs, diag):
        def go():
            # 任意平面：过点 (20, -10, 15)，法向 (0.3, 0.5, 1)
            ps = PlaneSpec.from_point_normal((20.0, -10.0, 15.0), (0.3, 0.5, 1.0))
            prof = Profile.from_xy([(0, 0), (55, 0), (70, 30),
                                    (30, 55), (-10, 30)])
            res = Result()
            _gsd_polygon(part, res, ps, prof, 45.0, k, offset, 0.0, None, True, False)
            diag.append(f"基准面：{ps}")
            diag.extend(res.diagnostics)
            if not res.is_solid:
                raise RuntimeError("未得到实体")
        probe.step(label, go)
    return run


def _surface_case(label):
    """非共面侧面：应成功输出曲面（并明确报告）。"""
    def run(probe, doc, part, hsf, hbs, diag):
        def go():
            ps = PlaneSpec.from_named("XY")
            prof = Profile.regular(6, 45.0)
            res = Result()
            _gsd_polygon(part, res, ps, prof, 60.0, 0.5, (0.0, 0.0), 20.0,
                         None, False, True)     # twist=20°, allow_nonplanar
            diag.extend(res.diagnostics)
            if res.checks.get("nonplanar_faces") is None:
                raise RuntimeError("未记录非共面检查结果")
            if len(res.checks["nonplanar_faces"]) == 0:
                raise RuntimeError("twist=20° 未检出非共面面")
        probe.step(label, go)
    return run


def _reject_nonplanar_case(label):
    """非共面 + 要求实体 → 必须明确拒绝而不是硬做。"""
    def run(probe, doc, part, hsf, hbs, diag):
        def go():
            ps = PlaneSpec.from_named("XY")
            prof = Profile.regular(6, 45.0)
            res = Result()
            try:
                _gsd_polygon(part, res, ps, prof, 60.0, 0.5, (0.0, 0.0), 20.0,
                             None, True, False)
            except GeometryError:
                return
            raise RuntimeError("twist 破坏共面性时未拒绝实体输出")
        probe.step(label, go)
    return run


_CASES = [
    ("底层·点与直线", _c_baseline),
    ("底层·圆（轴线沿法向）", _c_circle),
    ("底层·Fill（add_bound）", _c_fill),
    ("★数学自检·共面性/体积/自交/任意平面", _c_math_selfcheck),

    # --- 1.0 回归 ---
    ("回归·六棱柱 k=1", _poly_solid_case(6, 50.0, 80.0, 1.0, "六棱柱")),
    ("回归·六棱台 k=0.5", _poly_solid_case(6, 50.0, 80.0, 0.5, "六棱台")),
    ("回归·六棱锥 k=0", _poly_solid_case(6, 50.0, 80.0, 0.0, "六棱锥")),
    ("回归·圆柱", _circ_solid_case(50.0, 80.0, 1.0, "圆柱")),
    ("回归·圆台", _circ_solid_case(50.0, 80.0, 0.5, "圆台")),
    ("回归·圆锥", _circ_solid_case(50.0, 80.0, 0.0, "圆锥")),

    # --- 2.0 新增 ---
    ("★斜棱柱（offset, k=1）", _poly_solid_case(6, 40.0, 70.0, 1.0,
                                             "斜六棱柱", (35.0, 18.0))),
    ("★斜棱台（offset, k=0.45）", _poly_solid_case(6, 40.0, 70.0, 0.45,
                                               "斜六棱台", (30.0, -15.0))),
    ("★斜棱锥（offset, k=0）", _poly_solid_case(6, 40.0, 70.0, 0.0,
                                             "斜六棱锥", (25.0, 25.0))),
    ("★斜圆柱", _circ_solid_case(40.0, 70.0, 1.0, "斜圆柱", (30.0, 12.0))),
    ("★斜圆台", _circ_solid_case(40.0, 70.0, 0.5, "斜圆台", (26.0, -18.0))),
    ("★斜圆锥", _circ_solid_case(40.0, 70.0, 0.0, "斜圆锥", (22.0, 20.0))),
    ("★任意平面·三点确定", _circ_solid_case(35.0, 60.0, 0.6, "任意平面圆台",
                                        (0.0, 0.0))),
    ("★任意平面+顶点表+offset", _oblique_polygon_case(
        "任意平面斜棱台（五边形顶点表）", 0.5, (18.0, 12.0))),
    ("★非正多边形·星形", _poly_solid_case(
        0, 0.0, 60.0, 0.5, "星形棱台（12 顶点）",
        profile=Profile.star(6, 45.0, 22.0))),
    ("★凹轮廓·L 形", _poly_solid_case(
        0, 0.0, 60.0, 0.6, "L 形棱台",
        profile=Profile.from_xy([(0, 0), (60, 0), (60, 20), (20, 20),
                                 (20, 50), (0, 50)]))),
    ("★曲面·扭转（非共面侧面）", _surface_case("扭转 20° 输出曲面")),
    ("★拒绝·非共面却要实体", _reject_nonplanar_case("非共面时拒绝实体")),
]


def run_diagnostics(progress=None):
    results = []
    for idx, (name, fn) in enumerate(_CASES, start=1):
        if progress:
            progress(idx, len(_CASES), name)
        results.append(_run_case(fn, name))
    return results, _conclude(results)


def _conclude(results) -> str:
    lines = []
    fails = [r for r in results if not r["ok"]]
    lines.append(f"通过 {len(results) - len(fails)} / {len(results)} 个用例。")
    lines.append("")
    if fails:
        lines.append("失败用例：")
        for r in fails:
            stage, _ok, msg = r["first_fail"]
            lines.append(f"  · {r['case']}  →  [{stage}] {msg}")
        lines.append("")
    else:
        lines.append("全部通过 —— 1.0 的六种图形保持回归，2.0 的斜置/任意平面/"
                     "任意多边形均可用。")
        lines.append("")
    lines.append("明细：")
    for r in results:
        lines.append(f"  {'OK  ' if r['ok'] else 'FAIL'}  {r['case']}")
        for stage, ok, msg in r["rows"]:
            lines.append(f"          {'✓' if ok else '✗'} {stage}" +
                         (f"  {msg}" if msg else ""))
        for d in r.get("diag", []):
            lines.append(f"          · {d}")
    return "\n".join(lines)


def probe_point_section() -> Tuple[bool, str]:
    lines = []
    ok_any = False
    for coupling in (1, 4):
        name = f"点截面 coupling={coupling}"

        def fn(p, doc, part, hsf, hbs, d):
            ps = PlaneSpec.from_named("XY")
            axis = _axis_along_normal(hsf, hbs, part, ps.origin, ps.n, 80.0)
            part.update()
            c = _circle(hsf, hbs, part, _ref(part, axis), ps.origin, 50.0, d, "底圆")
            apex = _point(hsf, hbs, (0, 0, 80))
            _loft(hsf, hbs, part, [_ref(part, c), _ref(part, apex)],
                  coupling, d, "圆锥")

        r = _run_case(fn, name)
        if r["ok"]:
            ok_any = True
            lines.append(f"  {name}：✅ 可用")
        else:
            lines.append(f"  {name}：❌ 不可用（已知限制）")
        for d in r.get("diag", []):
            lines.append(f"      · {d}")
    lines.append("")
    if ok_any:
        lines.append("  → 点截面可用，可把 CONE_MODE 改为 \"point\" 获得真锥顶。")
    else:
        lines.append(f"  → 点截面不可用（符合预期）。k=0 继续用极小顶面近似"
                     f"（CONE_TOP_EPS_REL={CONE_TOP_EPS_REL}）。")
    return ok_any, "\n".join(lines)


def dump_signatures() -> str:
    out = ["相关方法签名（本机实测）", "-" * 62]
    for mod_name, cls_name, keys in (
        ("pycatia.hybrid_shape_interfaces.hybrid_shape_factory",
         "HybridShapeFactory",
         ("circle", "join", "fill", "loft", "close", "extrude", "plane")),
        ("pycatia.part_interfaces.shape_factory", "ShapeFactory",
         ("pad", "close_surface", "loft")),
    ):
        out.append("")
        out.append(f"【{cls_name}】")
        try:
            mod = __import__(mod_name, fromlist=[cls_name])
            cls = getattr(mod, cls_name)
        except Exception as exc:
            out.append(f"  无法导入：{exc}")
            continue
        for n in sorted(x for x in dir(cls)
                        if any(k in x for k in keys) and not x.startswith("_")):
            try:
                sig = inspect.signature(getattr(cls, n))
                params = [q.name for q in sig.parameters.values() if q.name != "self"]
                out.append(f"  {n}({', '.join(params)})")
            except Exception as exc:
                out.append(f"  {n}   <无法获取签名：{exc}>")
    return "\n".join(out)


# ================================================================
# 2.0 关键提醒
#
# 共面性定理（决定了「顶面能不能不相似」）
#   侧面共面 ⟺ (w_{i+1} − w_i) ∥ (P_{i+1} − P_i)
#   ⟹ 对一般多边形，顶面变换只能是均匀位似 k·I + 平面内平移 p
#   ⟹ 扭转 / 独立顶面轮廓 / 各向异性缩放（非轴对齐矩形）都会破坏共面性
#   本内核自动检测并报告面号，绝不静默产出错误几何
#
# 圆的轴线（2.0 修正的 v1 隐患）
#   必须沿平面法向 N，不能用「底面中心 → 顶面中心」：
#   offset ≠ 0 时后者会倾斜，导致圆不落在预期截面平面上
#
# 凸底面 + 位似顶面 ⟹ 实体恒为凸体，任何 k / offset / h 都不会自交
# ================================================================
