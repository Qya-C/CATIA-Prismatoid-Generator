# -*- coding: utf-8 -*-
"""
catia_controller.py
====================
CATIA 参数化图形生成 —— 内核 + 适配层 + 能力自检。

版本：2026.09.20-r6

实测确认的接口（改动时以此为准）
--------------------------------
    add_new_circle_center_axis(i_axis, i_point, i_value, i_projection)   轴线在前
    add_new_join(element1, element2)            两元素 + add_element() 追加
    add_new_fill()                             无参创建
    HybridShapeFill.add_bound(i_boundary)      设边界
    HybridShapeLoft.add_section_to_loft(i_section, i_ori, i_point)
                                               3 参数；ori=1 + pt=空 生效
    HybridShapeLoft.SectionCoupling            1 弧长比例 / 2 相切 / 3 相切+曲率 / 4 顶点
    ShapeFactory.add_new_close_surface(i_close_element)
    HybridShapeFactory.add_new_plane_offset(i_plane, i_offset, i_orientation)
    HybridShapeFactory.add_new_extrude(obj, off_debut, off_fin, direction)  ← 将来“斜”的入口

实测确认的两种限制（重要）
--------------------------
1) **点不能作为放样截面**。add_section_to_loft(点, 1, 空) 本身不报错，
   但随后 Update 必失败。故 k=0 的锥体改用【极小顶面】近似：
       k_eff = CONE_TOP_EPS_REL (1e-3)
   体积相对误差约等于 k_eff（0.1%），顶面是半径 0.05mm 的微小平面，肉眼不可见。

2) **Part Design 的 Pad 在本环境不可用**。add_new_pad / add_new_pad_from_ref
   对 k=1 的纯圆柱也报 E_FAIL，说明是草图与 Pad 的配合问题，非拔模所致。
   且 pycatia 的 Pad/Prism 继承链上未暴露拔模角接口。
   故 Part Design 路线整体停用（保留入口，失败时给出明确指引）。

工程约束
--------
* 空的 Loft / Fill 一旦入树，会让整文档 Update 失败 → 一律「先配置、后入树」
* 对 COM 对象调用 dir() 会抛 E_FAIL → 必须用 _public_names() 包裹
* 一个特征失败后该文档进入错误状态，后续 Update 全都连带失败
  → 自检必须每个用例用全新文档

自检结果（2026.09.20）
----------------------
主自检 11/11 通过：底层能力 3 项 + 六种图形实体 7 项 + 曲面路径 1 项。
点截面探查：不可用（符合预期），故 k=0 走极小顶面近似。
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

__version__ = "2026.09.20-r6"
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))


def version_info() -> str:
    """打印本模块与关键依赖的实际加载路径 + 关键常量取值。

    用途：排查「改了一份代码、实际跑的是另一份副本」这类问题 ——
    本项目已出现过一次（机器上存在两份 diagnose.py）。
    """
    lines = [
        f"catia_controller 版本：{__version__}",
        f"  本模块文件：{os.path.abspath(__file__)}",
        f"  所在目录　：{MODULE_DIR}",
    ]
    try:
        import pycatia
        lines.append(f"  pycatia 路径：{getattr(pycatia, '__file__', '未知')}")
        lines.append(f"  pycatia 版本：{getattr(pycatia, '__version__', '未知')}")
    except Exception as exc:
        lines.append(f"  pycatia 信息读取失败：{exc}")

    lines.append("  关键常量（用于确认加载的是哪一版行为）：")
    lines.append(f"    __version__          = {__version__}")
    lines.append(f"    CONE_MODE            = {CONE_MODE}")
    lines.append(f"    CONE_TOP_EPS_REL     = {CONE_TOP_EPS_REL}")
    lines.append(f"    SOLID_STRATEGY       = {SOLID_STRATEGY}")
    lines.append(f"    COUPLING_RATIO       = {COUPLING_RATIO}")
    lines.append(f"    COUPLING_VERTICES    = {COUPLING_VERTICES}")
    lines.append(f"    点截面已知可用       = {_POINT_SECTION_OK}")
    return "\n".join(lines)


# ================================================================ 常量

TOL = 1e-9

COUPLING_RATIO = 1          # 按弧长比例 —— 圆
COUPLING_VERTICES = 4       # 按顶点 —— 多边形（必须）

SECTION_ORIENT = 1          # add_section_to_loft 的方向参数，实测 1 可用

# k=0（锥体）的顶面近似比例。
# 顶面半径 = CONE_TOP_EPS_REL × R；体积相对误差 ≈ CONE_TOP_EPS_REL。
# 若 CATIA 报容差相关错误，把这个值调大（如 5e-3）；想更精确可调到 1e-4。
CONE_TOP_EPS_REL = 1e-3

# 锥体构造方式：
#   "approx" —— 极小顶面近似（默认，已验证可靠）
#   "point"  —— 尝试用点作末截面（本环境实测失败，保留供将来验证）
CONE_MODE = "approx"

# 点截面是否可用（由 probe_point_section() 填充；None = 未知）
_POINT_SECTION_OK: Optional[bool] = None

# 实体生成策略：
#   "caps"   —— 曲面放样 + 端盖 Fill + Join + Close Surface（已验证，5 个特征）
#   "volume" —— Loft 体积上下文（1 个特征，需 GSO；本机已确认有 GSO）
SOLID_STRATEGY = "caps"

PLANE_BASIS: Dict[str, Tuple[Tuple[float, float, float], ...]] = {
    "XY": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "YZ": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    "ZX": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
}
PLANE_KEYS = ["XY", "YZ", "ZX"]
PLANE_LABELS = ["XY 平面", "YZ 平面", "ZX 平面"]

BACKEND_LABELS = ["自动（GSD）", "GSD（多截面放样）", "Part Design（本机不可用）"]
BACKEND_KEYS = ["auto", "gsd", "pad"]


class Result:
    """一次生成操作的结果。"""

    def __init__(self) -> None:
        self.object = None
        self.is_solid = False
        self.used_backend = ""
        self.diagnostics: List[str] = []
        self.derived: Dict[str, float] = {}


class StageError(RuntimeError):
    """带阶段信息的更新失败。"""

    def __init__(self, stage: str, exc: Exception) -> None:
        super().__init__(
            f"更新失败于『{stage}』。\n"
            f"原始错误：{exc}\n\n"
            "请先执行『能力自检』；若自检通过，则问题在当前 Part 文档本身"
            "（历史特征带更新错误），请换一个新建的 Part 再试。"
        )
        self.stage = stage
        self.original = exc


# ================================================================ 纯数学层
# 不 import 任何 CATIA 接口，可在 CATIA 之外直接单测。

def side_length(n: int, radius: float) -> float:
    """正 n 边形边长 a = 2R·sin(π/n)。"""
    return 2.0 * radius * math.sin(math.pi / n)


def inradius(n: int, radius: float) -> float:
    """正 n 边形内切圆半径 = R·cos(π/n)。"""
    return radius * math.cos(math.pi / n)


def radius_from_side(n: int, side: float) -> float:
    return side / (2.0 * math.sin(math.pi / n))


def radius_from_inradius(n: int, inr: float) -> float:
    return inr / math.cos(math.pi / n)


def draft_angle_deg(n: Optional[int], radius: float, height: float, k: float) -> float:
    """Part Design 拔模角（度），供派生量展示。

    圆：      tanα = r(1−k)/h
    正 n 边形：tanα = R·cos(π/n)(1−k)/h    （按内切圆偏移，差一个 cos(π/n)）
    """
    if n is None:
        tan_a = radius * (1.0 - k) / height
    else:
        tan_a = radius * math.cos(math.pi / n) * (1.0 - k) / height
    return math.degrees(math.atan(tan_a))


def _plane_frame(plane: str):
    if plane not in PLANE_BASIS:
        raise ValueError(f"未知基准面：{plane!r}，可选 {PLANE_KEYS}。")
    u, v, nv = PLANE_BASIS[plane]
    return u, v, nv


def _check_common(n: int, radius: float, height: float, k: float, plane: str) -> None:
    if int(n) != n or n < 3:
        raise ValueError("边数 n 必须是不小于 3 的整数。")
    if radius <= 0.0:
        raise ValueError("半径必须大于 0。")
    if height <= 0.0:
        raise ValueError("垂直高 h 必须大于 0。")
    if k < 0.0:
        raise ValueError("缩放比 k 不得为负（k=0 表示锥体）。")
    if plane not in PLANE_BASIS:
        raise ValueError(f"未知基准面：{plane!r}，可选 {PLANE_KEYS}。")


def _add(base, vec, s: float = 1.0):
    return (base[0] + s * vec[0], base[1] + s * vec[1], base[2] + s * vec[2])


def plan_cone(k: float) -> Tuple[float, bool]:
    """决定 k=0 的构造方式。返回 (几何上使用的 k, 是否使用点截面)。"""
    if abs(k) >= TOL:
        return k, False
    if CONE_MODE == "point" and _POINT_SECTION_OK is not False:
        return k, True
    return CONE_TOP_EPS_REL, False


def build_polygon_sections(n: int, radius: float, height: float, k: float,
                           plane: str = "XY",
                           base_point: Sequence[float] = (0.0, 0.0, 0.0),
                           force_point: bool = False) -> Dict:
    """统一仿射映射：Q_i = C0 + h·N + k·(P_i − C0)。"""
    u, v, nv = _plane_frame(plane)
    c0 = (float(base_point[0]), float(base_point[1]), float(base_point[2]))

    def ring(scale: float):
        out = []
        for i in range(n):
            th = 2.0 * math.pi * i / n
            c, s = math.cos(th) * scale, math.sin(th) * scale
            out.append((c0[0] + c * u[0] + s * v[0],
                        c0[1] + c * u[1] + s * v[1],
                        c0[2] + c * u[2] + s * v[2]))
        return out

    bottom = ring(radius)
    top_origin = _add(c0, nv, height)

    if force_point or abs(k) < TOL:
        top, top_is_point = [top_origin], True
    else:
        sub = ring(k * radius)
        top = [(top_origin[0] + (p[0] - c0[0]),
                top_origin[1] + (p[1] - c0[1]),
                top_origin[2] + (p[2] - c0[2])) for p in sub]
        top_is_point = False

    return {"bottom": bottom, "top": top, "top_is_point": top_is_point,
            "top_origin": top_origin, "normal": nv}


def build_circular_sections(radius: float, height: float, k: float,
                            plane: str = "XY",
                            base_point: Sequence[float] = (0.0, 0.0, 0.0),
                            force_point: bool = False) -> Dict:
    u, v, nv = _plane_frame(plane)
    c0 = (float(base_point[0]), float(base_point[1]), float(base_point[2]))
    return {"bottom_center": c0, "top_center": _add(c0, nv, height),
            "top_is_point": force_point or abs(k) < TOL,
            "top_radius": k * radius, "normal": nv, "u": u, "v": v}


def derive_polygon(n: int, radius: float, height: float, k: float) -> Dict[str, float]:
    """派生量与自检数据。体积公式只用到垂直高 h。"""
    s1 = 0.5 * n * radius * radius * math.sin(2.0 * math.pi / n)
    s2 = k * k * s1
    apex = float("inf") if abs(k - 1.0) < TOL else height / (1.0 - k)
    return {"side": side_length(n, radius), "inradius": inradius(n, radius),
            "top_radius": k * radius, "bottom_area": s1, "top_area": s2,
            "volume": height / 3.0 * (s1 + s2 + math.sqrt(s1 * s2)),
            "lateral_edge": math.sqrt(height ** 2 + ((k - 1.0) * radius) ** 2),
            "apex_distance": apex,
            "draft_angle": draft_angle_deg(n, radius, height, k)}


def derive_circular(radius: float, height: float, k: float) -> Dict[str, float]:
    s1 = math.pi * radius * radius
    s2 = k * k * s1
    apex = float("inf") if abs(k - 1.0) < TOL else height / (1.0 - k)
    return {"bottom_area": s1, "top_area": s2,
            "volume": height / 3.0 * (s1 + s2 + math.sqrt(s1 * s2)),
            "lateral_edge": math.sqrt(height ** 2 + ((k - 1.0) * radius) ** 2),
            "top_radius": k * radius, "apex_distance": apex,
            "draft_angle": draft_angle_deg(None, radius, height, k)}


# ================================================================ 基础适配

def _public_names(obj, keys=None) -> List[str]:
    """安全枚举对象成员。

    对 COM 对象调用 dir() 会抛 E_FAIL，必须包起来 ——
    否则诊断代码自身会失败，并掩盖真实的出错位置。
    """
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


def _point(hsf, hbs, xyz: Sequence[float]):
    p = hsf.add_new_point_coord(float(xyz[0]), float(xyz[1]), float(xyz[2]))
    return _append(hbs, p)


def _line(hsf, hbs, part, from_obj, to_obj):
    ln = hsf.add_new_line_pt_pt(_ref(part, from_obj), _ref(part, to_obj))
    return _append(hbs, ln)


def _safe_update(part, stage: str, diagnostics: List[str], raise_on_fail: bool = True) -> bool:
    try:
        part.update()
        return True
    except Exception as exc:
        diagnostics.append(f"Update 失败于『{stage}』：{exc}")
        if raise_on_fail:
            raise StageError(stage, exc) from exc
        return False


# ================================================================ GSD 底层

def _axis_line(hsf, hbs, part, p_from, p_to):
    """轴线：底面中心 → 顶面中心，决定圆所在平面的法向。"""
    a = _point(hsf, hbs, p_from)
    b = _point(hsf, hbs, p_to)
    part.update()
    return _line(hsf, hbs, part, a, b)


def _circle(hsf, hbs, part, axis_ref, center_xyz, radius: float,
            diagnostics: List[str], label: str):
    """创建整圆。

    实测签名：add_new_circle_center_axis(i_axis, i_point, i_value, i_projection)
    —— 轴线在前。圆心取该点在轴线上的投影。
    """
    c = _point(hsf, hbs, center_xyz)
    _safe_update(part, f"创建{label}圆心", diagnostics)

    circle = hsf.add_new_circle_center_axis(
        axis_ref, _ref(part, c), float(radius), False
    )
    _append(hbs, circle)
    _safe_update(part, f"创建{label}", diagnostics)
    return circle


def _join(hsf, hbs, part, elements, diagnostics: List[str], label: str):
    """接合成一条曲线。add_new_join 需两个元素，其余用 add_element() 追加。"""
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


def _closed_wire(hsf, hbs, part, vertices, diagnostics: List[str], label: str):
    """由顶点列表建闭合多边形线框，返回 Join 对象。"""
    pts = [_point(hsf, hbs, v) for v in vertices]
    _safe_update(part, f"创建{label}顶点", diagnostics)

    m = len(pts)
    lines = [_line(hsf, hbs, part, pts[i], pts[(i + 1) % m]) for i in range(m)]
    _safe_update(part, f"创建{label}边", diagnostics)

    return _join(hsf, hbs, part, lines, diagnostics, f"{label}线框")


def _add_section(loft, sec_ref, diagnostics: List[str], index: int) -> bool:
    """给 Loft 加一个截面。

    实测签名：add_section_to_loft(i_section, i_ori, i_point)
    第 3 个参数用 vba_nothing 表示空（ori=1 + 空点 实测生效）。

    注意：返回 True 只表示"添加调用未报错"。若传入的是【点】，
    添加会成功但后续 Update 必定失败（见 CONE_MODE 说明）。
    """
    attempts = []
    if vba_nothing is not None:
        attempts.append(("ori=1, pt=空", SECTION_ORIENT, vba_nothing))
    attempts.append(("ori=1, pt=None", SECTION_ORIENT, None))
    for ori in (2, 0):
        if vba_nothing is not None:
            attempts.append((f"ori={ori}, pt=空", ori, vba_nothing))

    for name, ori, pt in attempts:
        try:
            loft.add_section_to_loft(sec_ref, ori, pt)
            diagnostics.append(f"Loft 第 {index} 个截面：已通过『{name}』添加。")
            return True
        except Exception:
            continue

    diagnostics.append(f"Loft 第 {index} 个截面添加失败。成员：{_public_names(loft)}")
    return False


def _loft(hsf, hbs, part, section_refs, coupling: int,
          diagnostics: List[str], label: str, as_volume: bool = False):
    """创建多截面放样。

    顺序至关重要：先创建并配置好所有截面，最后才放进几何图形集 ——
    空的 Loft 一旦入树，会让整文档的 Update 失败。
    """
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


def _fill(hsf, hbs, part, wire, diagnostics: List[str], label: str):
    """创建平面补片（端盖）。实测 add_new_fill() 无参创建，边界用 add_bound 设。"""
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


def _make_solid(hsf, hbs, part, section_refs, coupling: int, cap_wires,
                diagnostics: List[str], label: str):
    """按 SOLID_STRATEGY 生成实体。返回 (对象, 是否实体)。"""
    if SOLID_STRATEGY == "volume":
        try:
            loft = _loft(hsf, hbs, part, section_refs, coupling,
                         diagnostics, label, as_volume=True)
            return loft, True
        except Exception as exc:
            diagnostics.append(f"『{label}』体积放样失败，改用端盖路径：{exc}")

    loft = _loft(hsf, hbs, part, section_refs, coupling,
                 diagnostics, label, as_volume=False)
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


# ================================================================ GSD 主流程

def _build_polygon(part, res: Result, n, radius, height, k, output_solid,
                   plane, base_point):
    k_geom, use_point = plan_cone(k)
    sections = build_polygon_sections(n, radius, height, k_geom, plane,
                                      base_point, force_point=use_point)

    if abs(k) < TOL and not use_point:
        res.diagnostics.append(
            f"k=0 锥体：顶面以 {CONE_TOP_EPS_REL * 100:.3f}% 的极小截面近似"
            f"（顶面半径 {CONE_TOP_EPS_REL * radius:.4f} mm）。"
            f"体积相对误差约 {CONE_TOP_EPS_REL * 100:.2f}%，肉眼不可见。"
            "原因：本环境不接受“点”作为放样截面（添加不报错但 Update 必失败）。"
        )

    hsf = part.hybrid_shape_factory
    hbs = part.hybrid_bodies.add()
    hbs.name = f"PB_Poly_n{int(n)}_k{k:g}"
    try:
        part.in_work_object = hbs
    except Exception:
        pass
    _safe_update(part, "建立几何图形集", res.diagnostics)

    bottom_wire = _closed_wire(hsf, hbs, part, sections["bottom"],
                               res.diagnostics, "底面")
    cap_wires = [bottom_wire]
    section_refs = [_ref(part, bottom_wire)]

    if sections["top_is_point"]:
        apex = _point(hsf, hbs, sections["top"][0])
        _safe_update(part, "创建锥顶", res.diagnostics)
        section_refs.append(_ref(part, apex))
        res.diagnostics.append("顶面按锥顶（点）处理（CONE_MODE=point）。")
    else:
        top_wire = _closed_wire(hsf, hbs, part, sections["top"],
                                res.diagnostics, "顶面")
        cap_wires.append(top_wire)
        section_refs.append(_ref(part, top_wire))

    if output_solid:
        obj, is_solid = _make_solid(hsf, hbs, part, section_refs,
                                    COUPLING_VERTICES, cap_wires,
                                    res.diagnostics, "多边形")
        res.object, res.is_solid = obj, is_solid
    else:
        res.object = _loft(hsf, hbs, part, section_refs, COUPLING_VERTICES,
                           res.diagnostics, "多边形")

    _safe_update(part, "收尾更新", res.diagnostics)
    return res


def _build_circular(part, res: Result, radius, height, k, output_solid,
                    plane, base_point):
    k_geom, use_point = plan_cone(k)
    sec = build_circular_sections(radius, height, k_geom, plane,
                                  base_point, force_point=use_point)

    if abs(k) < TOL and not use_point:
        res.diagnostics.append(
            f"k=0 圆锥：顶面以 {CONE_TOP_EPS_REL * 100:.3f}% 的极小截面近似"
            f"（顶面半径 {CONE_TOP_EPS_REL * radius:.4f} mm）。"
            f"体积相对误差约 {CONE_TOP_EPS_REL * 100:.2f}%，肉眼不可见。"
            "原因：本环境不接受“点”作为放样截面（添加不报错但 Update 必失败）。"
        )

    hsf = part.hybrid_shape_factory
    hbs = part.hybrid_bodies.add()
    hbs.name = f"PB_Circ_k{k:g}"
    try:
        part.in_work_object = hbs
    except Exception:
        pass
    _safe_update(part, "建立几何图形集", res.diagnostics)

    axis = _axis_line(hsf, hbs, part, sec["bottom_center"], sec["top_center"])
    axis_ref = _ref(part, axis)

    bottom_circle = _circle(hsf, hbs, part, axis_ref, sec["bottom_center"],
                            radius, res.diagnostics, "底面圆")
    cap_wires = [bottom_circle]
    section_refs = [_ref(part, bottom_circle)]

    if sec["top_is_point"]:
        apex = _point(hsf, hbs, sec["top_center"])
        _safe_update(part, "创建锥顶", res.diagnostics)
        section_refs.append(_ref(part, apex))
        res.diagnostics.append("顶面按锥顶（点）处理（CONE_MODE=point）。")
    else:
        top_circle = _circle(hsf, hbs, part, axis_ref, sec["top_center"],
                             sec["top_radius"], res.diagnostics, "顶面圆")
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


# ================================================================ Part Design（本机不可用）

def _pd_base_plane(part, plane_key: str):
    oe = part.origin_elements
    return {"XY": oe.plane_xy, "YZ": oe.plane_yz, "ZX": oe.plane_zx}[plane_key]


def _pd_make_sketch(part, hbs, plane_key: str, base_point,
                    profile_fn, diagnostics: List[str], label: str):
    """创建草图并返回 Sketch 对象。"""
    u, v, nv = _plane_frame(plane_key)
    ox, oy, oz = base_point
    n_comp = ox * nv[0] + oy * nv[1] + oz * nv[2]
    u_comp = ox * u[0] + oy * u[1] + oz * u[2]
    v_comp = ox * v[0] + oy * v[1] + oz * v[2]

    base_ref = _ref(part, _pd_base_plane(part, plane_key))
    if abs(n_comp) > 1e-7:
        hsf = part.hybrid_shape_factory
        off = hsf.add_new_plane_offset(base_ref, n_comp, False)
        hbs.append_hybrid_shape(off)
        _safe_update(part, f"{label}基准面偏移", diagnostics)
        plane_ref = _ref(part, off)
    else:
        plane_ref = base_ref

    sketch = None
    errors = []
    try:
        part.in_work_object = part.main_body
    except Exception:
        pass
    for cname, getter in (
        ("主体", lambda: part.main_body.sketches.add(plane_ref)),
        ("几何图形集", lambda: hbs.hybrid_sketches.add(plane_ref)),
    ):
        try:
            sketch = getter()
            diagnostics.append(f"{label}：草图已创建（容器：{cname}）。")
            break
        except Exception as exc:
            errors.append(f"{cname}: {exc}")

    if sketch is None:
        raise RuntimeError(f"{label}：草图创建失败（{'；'.join(errors)}）")

    f2d = sketch.open_edition()
    profile_fn(f2d, u_comp, v_comp)
    sketch.close_edition()
    _safe_update(part, f"{label}草图", diagnostics)
    return sketch


def _pd_poly_profile(n: int, radius: float):
    def draw(f2d, cu, cv):
        pts = []
        for i in range(n):
            th = 2.0 * math.pi * i / n
            pts.append(f2d.create_point(cu + radius * math.cos(th),
                                        cv + radius * math.sin(th)))
        for i in range(n):
            th1 = 2.0 * math.pi * i / n
            th2 = 2.0 * math.pi * (i + 1) / n
            ln = f2d.create_line(cu + radius * math.cos(th1),
                                 cv + radius * math.sin(th1),
                                 cu + radius * math.cos(th2),
                                 cv + radius * math.sin(th2))
            ln.start_point = pts[i]
            ln.end_point = pts[(i + 1) % n]
    return draw


def _pd_circle_profile(radius: float):
    def draw(f2d, cu, cv):
        m = getattr(f2d, "create_closed_circle", None)
        if callable(m):
            m(cu, cv, radius)
            return
        raise RuntimeError(
            f"草图内创建圆失败。成员：{_public_names(f2d, ['circle'])}"
        )
    return draw


def _pd_unavailable(diagnostics: List[str], label: str):
    """Part Design 路线在本环境不可用，给出明确说明。"""
    diagnostics.append(
        f"{label}：Part Design 路线在本机不可用。"
        "实测 add_new_pad 与 add_new_pad_from_ref 对纯圆柱（k=1）也返回 E_FAIL，"
        "说明是草图与 Pad 的配合问题，非拔模所致；"
        "且 pycatia 的 Pad/Prism 继承链上未暴露拔模角接口，本也无法生成锥/台。"
        "请把『生成方式』保持为『自动（GSD）』。"
    )
    raise RuntimeError(f"{label}：Part Design 不可用，请改用 GSD 路线。")


def _pd_polyhedron(part, res: Result, n, radius, height, k, output_solid,
                   plane, base_point):
    _pd_unavailable(res.diagnostics, "多边形")


def _pd_circular(part, res: Result, radius, height, k, output_solid,
                 plane, base_point):
    _pd_unavailable(res.diagnostics, "圆形")


# ================================================================ 对外主函数

def create_polyhedron(n: int = 6, radius: float = 50.0, height: float = 80.0,
                      k: float = 1.0, output_solid: bool = False,
                      plane: str = "XY",
                      base_point: Sequence[float] = (0.0, 0.0, 0.0),
                      backend: str = "auto") -> Result:
    """n 棱柱 / n 棱锥 / n 棱台（正族，轴线垂直底面）。"""
    _check_common(n, radius, height, k, plane)

    part, _doc = _get_part()
    res = Result()
    res.derived = derive_polygon(n, radius, height, k)      # 按理想 k 报告

    pre: List[str] = []
    if not _safe_update(part, "文档预检", pre, raise_on_fail=False):
        raise StageError("文档预检", RuntimeError("该 Part 文档自身无法更新"))

    if backend == "pad":
        _pd_polyhedron(part, res, n, radius, height, k, output_solid,
                       plane, base_point)
        res.used_backend = "pad"
        return res

    _build_polygon(part, res, n, radius, height, k, output_solid,
                   plane, base_point)
    res.used_backend = "gsd"
    return res


def create_circular_solid(radius: float = 50.0, height: float = 80.0,
                          k: float = 1.0, output_solid: bool = False,
                          plane: str = "XY",
                          base_point: Sequence[float] = (0.0, 0.0, 0.0),
                          backend: str = "auto") -> Result:
    """圆柱 / 圆锥 / 圆台（正族，轴线垂直底面）。"""
    _check_common(3, radius, height, k, plane)

    part, _doc = _get_part()
    res = Result()
    res.derived = derive_circular(radius, height, k)

    pre: List[str] = []
    if not _safe_update(part, "文档预检", pre, raise_on_fail=False):
        raise StageError("文档预检", RuntimeError("该 Part 文档自身无法更新"))

    if backend == "pad":
        _pd_circular(part, res, radius, height, k, output_solid,
                     plane, base_point)
        res.used_backend = "pad"
        return res

    _build_circular(part, res, radius, height, k, output_solid,
                    plane, base_point)
    res.used_backend = "gsd"
    return res


# ================================================================ 能力自检

class _Probe:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: List[Tuple[str, bool, str]] = []

    def step(self, stage: str, fn) -> bool:
        try:
            fn()
        except Exception as exc:
            self.rows.append((stage, False, f"{type(exc).__name__}: {exc}"))
            return False
        self.rows.append((stage, True, ""))
        return True

    @property
    def ok(self) -> bool:
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


# ---------- 底层能力 ----------

def _c_baseline(probe, doc, part, hsf, hbs, diag):
    a = _point(hsf, hbs, (0, 0, 0))
    b = _point(hsf, hbs, (0, 0, 50))
    probe.step("点入集后 update", part.update)
    probe.step("创建直线", lambda: _line(hsf, hbs, part, a, b))


def _c_circle(probe, doc, part, hsf, hbs, diag):
    axis = _axis_line(hsf, hbs, part, (0, 0, 0), (0, 0, 50))
    part.update()
    probe.step("创建圆（轴线在前）",
               lambda: _circle(hsf, hbs, part, _ref(part, axis), (0, 0, 0),
                               50.0, diag, "测试圆"))


def _c_fill(probe, doc, part, hsf, hbs, diag):
    axis = _axis_line(hsf, hbs, part, (0, 0, 0), (0, 0, 50))
    part.update()
    holder = {}
    probe.step("创建圆", lambda: holder.setdefault(
        "c", _circle(hsf, hbs, part, _ref(part, axis), (0, 0, 0), 50.0, diag, "圆")))
    probe.step("创建 Fill（add_bound）",
               lambda: _fill(hsf, hbs, part, holder["c"], diag, "测试Fill"))


# ---------- 六种图形的实体整链 + 曲面路径 ----------

def _poly_solid_case(n, radius, height, k, label):
    def run(probe, doc, part, hsf, hbs, diag):
        def go():
            res = Result()
            res.derived = derive_polygon(n, radius, height, k)
            _build_polygon(part, res, n, radius, height, k, True,
                           "XY", (0, 0, 0))
            diag.extend(res.diagnostics)
            if not res.is_solid:
                raise RuntimeError("未得到实体")
        probe.step(label, go)
    return run


def _circ_solid_case(radius, height, k, label):
    def run(probe, doc, part, hsf, hbs, diag):
        def go():
            res = Result()
            res.derived = derive_circular(radius, height, k)
            _build_circular(part, res, radius, height, k, True,
                            "XY", (0, 0, 0))
            diag.extend(res.diagnostics)
            if not res.is_solid:
                raise RuntimeError("未得到实体")
        probe.step(label, go)
    return run


def _surface_case(n, radius, height, k, label):
    """曲面输出路径（不封闭为实体）—— 与实体路径是两条不同的代码分支。"""
    def run(probe, doc, part, hsf, hbs, diag):
        def go():
            res = Result()
            res.derived = derive_polygon(n, radius, height, k)
            _build_polygon(part, res, n, radius, height, k, False,
                           "XY", (0, 0, 0))
            diag.extend(res.diagnostics)
            if res.object is None:
                raise RuntimeError("未得到曲面")
        probe.step(label, go)
    return run


# ---------- 主自检名单：全部为「应当通过」的用例 ----------

_CASES = [
    ("底层·点与直线", _c_baseline),
    ("底层·圆（轴线在前）", _c_circle),
    ("底层·Fill（add_bound）", _c_fill),

    ("★实体·六棱柱（k=1）", _poly_solid_case(6, 50.0, 80.0, 1.0, "六棱柱")),
    ("★实体·六棱台（k=0.5）", _poly_solid_case(6, 50.0, 80.0, 0.5, "六棱台")),
    ("★实体·六棱锥（k=0）", _poly_solid_case(6, 50.0, 80.0, 0.0, "六棱锥")),
    ("★实体·三棱台（n=3,k=0.3）", _poly_solid_case(3, 50.0, 80.0, 0.3, "三棱台")),

    ("★实体·圆柱（k=1）", _circ_solid_case(50.0, 80.0, 1.0, "圆柱")),
    ("★实体·圆台（k=0.5）", _circ_solid_case(50.0, 80.0, 0.5, "圆台")),
    ("★实体·圆锥（k=0）", _circ_solid_case(50.0, 80.0, 0.0, "圆锥")),

    ("★曲面·六棱柱（不封闭）", _surface_case(6, 50.0, 80.0, 1.0, "六棱柱曲面")),
]


def run_diagnostics(progress=None):
    """主能力自检：每个用例在【全新空 Part】中隔离执行。

    返回 (results, conclusion)。全部用例都应当通过。
    """
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
        lines.append("全部通过 —— 六种图形（棱柱/棱锥/棱台/圆柱/圆锥/圆台）")
        lines.append("的实体与曲面路径均可用。")
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
    """【独立探查】点截面能否作为放样截面。

    这是一个**探测性**用例，预期结果是「不可用」——
    若将来某个 CATIA 版本支持了，可把 CONE_MODE 改为 "point"
    以获得真正的锥顶（无近似误差）。

    返回 (是否可用, 说明文本)。**不计入主自检的通过率。**
    """
    global _POINT_SECTION_OK
    lines = []
    ok_any = False

    for coupling in (1, 4):
        name = f"点截面 coupling={coupling}"

        def fn(p, doc, part, hsf, hbs, d):
            axis = _axis_line(hsf, hbs, part, (0, 0, 0), (0, 0, 80))
            part.update()
            c = _circle(hsf, hbs, part, _ref(part, axis), (0, 0, 0),
                        50.0, d, "底圆")
            apex = _point(hsf, hbs, (0, 0, 80))
            _loft(hsf, hbs, part, [_ref(part, c), _ref(part, apex)],
                  coupling, d, "圆锥")

        r = _run_case(fn, name)
        if r["ok"]:
            ok_any = True
            lines.append(f"  {name}：✅ 可用")
        else:
            stage, _ok, msg = r["first_fail"]
            lines.append(f"  {name}：❌ 不可用（{stage}）")
        for d in r.get("diag", []):
            lines.append(f"      · {d}")

    _POINT_SECTION_OK = ok_any
    if ok_any:
        lines.append("")
        lines.append("  → 结论：点截面可用！可把 CONE_MODE 改为 \"point\"，")
        lines.append("     k=0 的锥体将使用真正的锥顶，无近似误差。")
    else:
        lines.append("")
        lines.append("  → 结论：点截面不可用（符合预期）。")
        lines.append(f"     k=0 的锥体继续使用极小顶面近似"
                     f"（CONE_TOP_EPS_REL = {CONE_TOP_EPS_REL}，"
                     f"误差约 {CONE_TOP_EPS_REL * 100:.2f}%）。")

    return ok_any, "\n".join(lines)


def dump_signatures() -> str:
    """打印相关方法的真实签名（本机实测）。"""
    out = ["相关方法签名（本机实测）", "-" * 62]
    for mod_name, cls_name, keys in (
        ("pycatia.hybrid_shape_interfaces.hybrid_shape_factory",
         "HybridShapeFactory",
         ("circle", "join", "fill", "loft", "close", "extrude", "plane", "revolve")),
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
        names = sorted(n for n in dir(cls)
                       if any(k in n for k in keys) and not n.startswith("_"))
        for n in names:
            try:
                sig = inspect.signature(getattr(cls, n))
                params = [q.name for q in sig.parameters.values() if q.name != "self"]
                out.append(f"  {n}({', '.join(params)})")
            except Exception as exc:
                out.append(f"  {n}   <无法获取签名：{exc}>")
    return "\n".join(out)


# ================================================================
# 已实测确认的接口与限制（改动时以本清单为准）
#
# 接口
#   add_new_circle_center_axis(i_axis, i_point, i_value, i_projection)   轴线在前
#   add_new_join(element1, element2)              两元素 + add_element() 追加
#   add_new_fill() + HybridShapeFill.add_bound(ref)
#   add_section_to_loft(i_section, i_ori, i_point)   ori=1 + pt=空 生效
#   SectionCoupling 1/2/3/4（顶点=4）
#   ShapeFactory.add_new_close_surface(i_close_element)
#   add_new_plane_offset(i_plane, i_offset, i_orientation)
#   add_new_extrude(obj, off_debut, off_fin, direction)   ← 将来“斜”的入口
#
# 限制（均已实测）
#   1. 点不能作为放样截面 → k=0 用 CONE_TOP_EPS_REL 极小顶面近似
#   2. Part Design Pad 在本环境不可用（k=1 的圆柱也 E_FAIL）
#   3. 空 Loft / Fill 不得入树 → 先配置、后入树
#   4. dir(com_object) 会抛 E_FAIL → 用 _public_names() 包裹
#   5. 一个特征失败会毒化整个文档 → 自检必须每例新文档
# ================================================================