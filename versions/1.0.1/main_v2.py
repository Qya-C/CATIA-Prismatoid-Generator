# -*- coding: utf-8 -*-
"""
main_v2.py
CATIA 参数化图形生成插件 2.0 - 主界面

新增（相对 1.0）
* 斜置：顶面中心在截面平面内错位 offset=(pu, pv)，使顶面与底面的投影不重合
* 任意基准面：标准面 / 原点+法向 / 三点确定
* 任意底面轮廓：正 n 边形 / 星形 / 顶点表（直角坐标或极坐标）
* 校验面板：自交、重合、凸性、侧面共面性、体积交叉校核

界面（2.0.1 起）
* 紧凑双栏：左侧只放参数，右侧只放只读派生量，窗口按内容自适应高度
* 高级项（尺寸驱动、校验明细）默认折叠，需要时再展开；
  斜置是主打功能，默认展开
* 基准面与轮廓的多值输入各占一行，避免纵向堆出半屏
"""

import sys
import math
import os

from PySide6.QtWidgets import (
    QApplication, QDialog, QFormLayout, QDialogButtonBox,
    QAbstractSpinBox,
    QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QGroupBox,
    QPushButton, QMessageBox, QWidget, QDoubleSpinBox, QSpinBox,
    QPlainTextEdit, QCheckBox, QStackedWidget, QToolButton, QTabWidget,
    QSizePolicy, QScrollArea, QSplitter,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFontMetrics

try:
    from catia_controller_v2 import (
        create_prismatoid, create_circular_prismatoid,
        create_polyhedron, create_circular_solid,
        run_diagnostics, dump_signatures, version_info,
        derive_polygon, derive_circular, derive_prismatoid,
        validate_profile, Profile, PlaneSpec,
        GeometryError, side_length, inradius,
        radius_from_side, radius_from_inradius,
        PLANE_KEYS, PLANE_LABELS, BACKEND_KEYS, BACKEND_LABELS,
        __version__ as CONTROLLER_VERSION,
    )
    CONTROLLER_ERROR = None
except Exception as _exc:      # pragma: no cover
    CONTROLLER_ERROR = _exc
    CONTROLLER_VERSION = "未知"


DRIVER_LABELS = ["外接圆半径 R", "边长 a", "内切圆半径 r_in"]
PLANE_MODE_LABELS = ["标准面（XY/YZ/ZX）", "原点 + 法向", "三点确定"]
PROFILE_MODE_LABELS = ["正 n 边形", "星形（内外半径）", "顶点表（直角坐标）",
                       "顶点表（极坐标）"]

# 紧凑布局下用的短标签：中文全称会把下拉框撑得很宽，
# 内层控件因此超出滚动区视口，连自己的文字都显示不全。
PLANE_MODE_LABELS_SHORT = ["标准面", "原点+法向", "三点确定"]
PROFILE_MODE_LABELS_SHORT = ["正 n 边形", "星形", "顶点表 XY", "顶点表 极坐标"]
PLANE_LABELS_SHORT = ["XY", "YZ", "ZX"]

TABLE_PLACEHOLDER_XY = (
    "# 每行一个顶点，格式：x, y\n"
    "# 可留空行；# 开头的行会被忽略\n"
    "# 顺序即绕向，程序会自动统一为逆时针\n"
    "50, 0\n"
    "25, 43.3013\n"
    "-25, 43.3013\n"
    "-50, 0\n"
    "-25, -43.3013\n"
    "25, -43.3013\n"
)
TABLE_PLACEHOLDER_POLAR = (
    "# 每行一个顶点，格式：半径, 角度(度)\n"
    "50, 0\n"
    "50, 60\n"
    "50, 120\n"
    "50, 180\n"
    "50, 240\n"
    "50, 300\n"
)

# 数值框统一限宽：不让长数字把窗口横向撑开
# 旋转框要能完整显示 "80.0000" 和上下箭头。
# 上一版压到 70~92px，箭头盖住了数字，很多控件窄到点不中 —— 这是
# 用户报"控件点不动 / 箭头与参数重合"的直接原因。
SPIN_WIDTH = 112
SPIN_WIDTH_NARROW = 96


# ============================================================ 布局工具
#
# 设计意图：参数面板的每一个字段都独立占一行时，纵向会迅速堆高
# （基准面的原点/法向/三点最多 12 行、轮廓 3 行、尺寸 4 行…），
# 这正是旧版界面占据半屏的原因。下面三个工具把"字段行"压扁、
# 让对话框按内容自适应高度。

def _apply_form_layout(form, margin=8, spacing=4):
    """统一的表单外观：标签右对齐、标签列足够宽、控件列够放下内容。

    要点：标签列宽度用字体实际度量，而不是留默认宽度 ——
    中文标签（如"底面半径 r:"）比英文宽，默认宽度会把它截断或挤压控件。
    """
    form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
    # 一律不换行：让标签与控件稳定地落在同一行、同一列上。
    # 之前混用 WrapLongRows + 自定义 _hrow 是错位的根源。
    form.setRowWrapPolicy(QFormLayout.DontWrapRows)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
    form.setHorizontalSpacing(10)
    form.setVerticalSpacing(spacing)
    form.setContentsMargins(margin, margin, margin, margin)
    return form


def _label_column_width(form, extra=8):
    """按最大标签的文本宽度，给出标签列应有的宽度。"""
    fm = QFontMetrics(form.parentWidget().font()
                      if form.parentWidget() is not None
                      else QApplication.font())
    widest = 0
    for i in range(form.rowCount()):
        item = form.itemAt(i, QFormLayout.LabelRole)
        lab = item.widget() if item is not None else None
        if lab is not None and lab.text():
            widest = max(widest, fm.horizontalAdvance(lab.text()))
    return widest + extra


def _finish_form(form, min_field=110):
    """表单填完后收尾：标签列宽按内容定，控件列给足最小宽度。"""
    try:
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for i in range(form.rowCount()):
            item = form.itemAt(i, QFormLayout.FieldRole)
            w = item.widget() if item is not None else None
            if w is None:
                continue
            if w.minimumWidth() < min_field:
                w.setMinimumWidth(min_field)
    except Exception:
        pass
    return form


def _row_items(*widgets):
    """把多个控件放进一个容器，用于 X/Y/Z 三格行。

    容器落在表单的**控件列**里，因此与单值行的起始位置对齐。
    """
    host = QWidget()
    line = QHBoxLayout(host)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(6)
    for w in widgets:
        line.addWidget(w, 0)
    line.addStretch(1)
    return host


def _hrow(items, spacing=6):
    """兼容旧调用：把 (标签, 控件) 序列压成一行，交给 _row_items 承载。"""
    ws = []
    for it in items:
        if isinstance(it, tuple):
            lab, wid = it
            if lab:
                tag = QLabel(lab)
                tag.setStyleSheet("color:#555;")
                ws.append(tag)
            ws.append(wid)
        else:
            ws.append(it)
    return _row_items(*ws)


def _xyz_row(items, width=SPIN_WIDTH_NARROW):
    """X/Y/Z 三格行：宽度必须够放下数字与箭头。"""
    for _lab, wid in items:
        wid.setMinimumWidth(width)
        wid.setMaximumWidth(width + 8)
    return _hrow(items)


def _form_row(form, label, widget):
    """统一的加行方式：始终用表单原生标签列，保证纵向对齐。"""
    if not label:
        form.addRow(widget)
    else:
        form.addRow(label, widget)


def _make_spinbox(value, min_val, max_val, decimals=3, step=1.0, width=SPIN_WIDTH):
    sb = QDoubleSpinBox()
    sb.setRange(min_val, max_val)
    sb.setDecimals(decimals)
    sb.setSingleStep(step)
    sb.setValue(value)
    # 最小宽度保证数字与上下箭头都不被压住；上限放宽，让窗口放大时可用
    sb.setMinimumWidth(96)
    sb.setMaximumWidth(width + 60)
    return sb


def enforce_min_widths(*groups, combo=124, spin=100):
    """给参数组里的每个输入控件设硬下限宽度。

    为什么必须硬设：
        QFormLayout 在空间不足时会压缩控件列（实测下拉框被压到 54px，
        文字和箭头都显示不全，用户点不中）。设了 minimumWidth 之后，
        布局无处可压，只能把对话框撑宽 —— 这正是我们想要的行为。
    """
    try:
        for grp in groups:
            if grp is None:
                continue
            for form in grp.findChildren(QFormLayout):
                for i in range(form.rowCount()):
                    item = form.itemAt(i, QFormLayout.FieldRole)
                    w = item.widget() if item is not None else None
                    if w is None:
                        continue
                    if isinstance(w, QAbstractSpinBox):
                        w.setMinimumWidth(spin)
                    elif isinstance(w, QComboBox):
                        w.setMinimumWidth(combo)
                    elif isinstance(w, QPlainTextEdit):
                        w.setMinimumWidth(260)
                    else:
                        # 容器（如 X/Y/Z 三格行）：给整个容器一个下限
                        w.setMinimumWidth(min(combo, 200))
    except Exception:
        pass


def unify_label_columns(*groups):
    """把每个参数组里所有表单的标签列统一到同一宽度。

    不统一时，标签长的组（"底面半径 r:"）会把控件列推得更右，
    与标签短的组（"边数 n:"）相差几十像素，整屏看起来错落不齐。
    """
    try:
        for grp in groups:
            if grp is None:
                continue
            forms = grp.findChildren(QFormLayout)
            if not forms:
                continue
            fm = QFontMetrics(grp.font())
            widest = 0
            for form in forms:
                for i in range(form.rowCount()):
                    item = form.itemAt(i, QFormLayout.LabelRole)
                    lab = item.widget() if item is not None else None
                    if lab is not None and lab.text():
                        widest = max(widest, fm.horizontalAdvance(lab.text()))
            if widest <= 0:
                continue
            for form in forms:
                for i in range(form.rowCount()):
                    item = form.itemAt(i, QFormLayout.LabelRole)
                    lab = item.widget() if item is not None else None
                    if lab is not None:
                        lab.setMinimumWidth(widest)
    except Exception:
        pass


def _fit_to_content(dlg, min_width, apply=False):
    """决定对话框的尺寸。

    * 宽度下限 min_width；窗口可以自由拉大（用户要的"主窗口自由缩放"）
    * 首次显示（apply=True）时按内容自然尺寸打开，受屏幕可用区域限制
    * 内容比窗口大时由 QScrollArea / 拉伸自然处理，不再把控件压碎
    """
    lay = dlg.layout()
    natural_w, natural_h = min_width, 0
    if lay is not None:
        lay.setSizeConstraint(QVBoxLayout.SetDefaultConstraint)
        hint = lay.sizeHint()
        natural_w = max(min_width, hint.width())
        natural_h = hint.height()
    dlg.setMinimumSize(min_width, 420)
    if not apply:
        return
    try:
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            w = min(natural_w, int(avail.width() * 0.95))
            h = min(natural_h, int(avail.height() * 0.90))
        else:
            w, h = natural_w, natural_h
        dlg.resize(max(min_width, w), max(420, h))
    except Exception:
        pass


def cap_dialog_to_screen(dlg, ratio=0.90):
    """窗口最大尺寸限制在屏幕可用区域内（可自由缩小，不能大到超出屏幕）。"""
    try:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        dlg.setMaximumSize(int(avail.width() * 0.98), int(avail.height() * ratio))
    except Exception:
        pass


class CollapsibleGroup(QGroupBox):
    """可折叠分组：默认收起，避免高级项长期占用屏幕。"""

    def __init__(self, title, parent=None, expanded=False):
        # 标题交给里面的 QToolButton，QGroupBox 自己不再重复显示标题，
        # 否则界面上会出现两遍同样的文字。
        super().__init__("", parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)

        self._toggle = QToolButton(self)
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._toggle.setStyleSheet("QToolButton{border:none;font-weight:bold;}")
        self._toggle.clicked.connect(self._on_toggle)
        outer.addWidget(self._toggle)

        self._body = QWidget(self)
        self._body.setVisible(expanded)
        outer.addWidget(self._body)
        self._body_form = None

    def body_form(self, margin=2):
        lay = QVBoxLayout(self._body)
        lay.setContentsMargins(0, 0, 0, 0)
        form = _apply_form_layout(QFormLayout(), margin)
        lay.addLayout(form)
        self._body_form = form
        return form

    def add_body_widget(self, w):
        lay = self._body.layout()
        if lay is None:
            lay = QVBoxLayout(self._body)
        lay.addWidget(w)

    def _on_toggle(self, checked):
        self._body.setVisible(checked)
        self._toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        # 折叠会改变内容高度，通知所在对话框重新适配窗口尺寸
        w = self.window()
        if hasattr(w, "_side_scroll"):
            _sync_dialog_size(w)


# ============================================================ 辅助

def _fmt(value, unit="mm"):
    if value is None or (isinstance(value, float) and math.isinf(value)):
        return "∞"
    return f"{value:.4f} {unit}".strip()


def _check_controller(parent):
    if CONTROLLER_ERROR is None:
        return True
    QMessageBox.critical(
        parent, "无法连接 CATIA",
        "加载几何内核失败，请确认：\n"
        "1) CATIA V5 已启动；\n"
        "2) 已安装 pycatia；\n"
        "3) 当前 Python 环境正确。\n\n"
        f"详细错误：\n{CONTROLLER_ERROR}",
    )
    return False


def _build_message(result):
    head = (f"已生成实体（{result.used_backend}）。" if result.is_solid
            else f"已生成曲面（{result.used_backend}）。")
    head += "请在 CATIA 中按 Ctrl+U 更新视图。"
    if result.diagnostics:
        head += "\n\n提示：\n" + "\n".join(f"· {d}" for d in result.diagnostics)
    return head


class TextDialog(QDialog):
    def __init__(self, title, text, parent=None, width=760, height=520):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(width, height)
        layout = QVBoxLayout(self)
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText(text)
        box.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


def _make_backend_combo():
    cb = QComboBox()
    cb.addItems(BACKEND_LABELS)
    cb.setToolTip("自动 / GSD：多截面放样 + 端盖 + 封闭。\n"
                  "Part Design：本机实测不可用，仅供排查。")
    return cb


def _parse_table(text, polar):
    """解析顶点表文本。返回 [(a, b), ...]，失败抛 GeometryError。"""
    pairs = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace("，", ",").replace("\t", ",").split(",")
        if len(parts) < 2:
            raise GeometryError(f"顶点表第 {lineno} 行无法解析（需要两个数值）：{raw!r}")
        try:
            a = float(parts[0])
            b = float(parts[1])
        except ValueError as exc:
            raise GeometryError(f"顶点表第 {lineno} 行含非数值：{raw!r}") from exc
        if polar and (b < 0 or b > 360):
            raise GeometryError(f"顶点表第 {lineno} 行角度应在 0~360 度之间：{raw!r}")
        pairs.append((a, b))
    if len(pairs) < 3:
        raise GeometryError(f"顶点表至少需要 3 个顶点，当前解析到 {len(pairs)} 个。")
    return pairs


# ============================================================
# 基准面 / 轮廓 复用小部件
# ============================================================

class PlanePanel(QGroupBox):
    """基准面输入面板：标准面 / 原点+法向 / 三点确定。

    compact=True 时把 原点/法向/三点 各压成一行三格（最多 12 行 -> 4 行）。
    """

    def __init__(self, parent=None, compact=False):
        super().__init__("基准面", parent)
        form = _apply_form_layout(QFormLayout(self))

        self.mode = QComboBox()
        self.mode.addItems(PLANE_MODE_LABELS_SHORT if compact
                           else PLANE_MODE_LABELS)
        for i, full in enumerate(PLANE_MODE_LABELS):
            self.mode.setItemData(i, full, Qt.ToolTipRole)
        _form_row(form, "定义方式:", self.mode)

        # --- 标准面 ---
        self.std_combo = QComboBox()
        self.std_combo.addItems(PLANE_LABELS_SHORT if compact else PLANE_LABELS)
        self.std_row = self._row(form, "标准面:", self.std_combo)

        self.ox = _make_spinbox(0.0, -1e6, 1e6)
        self.oy = _make_spinbox(0.0, -1e6, 1e6)
        self.oz = _make_spinbox(0.0, -1e6, 1e6)
        if compact:
            _form_row(form, "原点:",
                      _xyz_row([("X", self.ox), ("Y", self.oy), ("Z", self.oz)]))
        else:
            form.addRow("原点 X:", self.ox)
            form.addRow("原点 Y:", self.oy)
            form.addRow("原点 Z:", self.oz)

        # --- 原点 + 法向 ---
        self.nx = _make_spinbox(0.0, -1e6, 1e6, decimals=4)
        self.ny = _make_spinbox(0.0, -1e6, 1e6, decimals=4)
        self.nz = _make_spinbox(1.0, -1e6, 1e6, decimals=4)
        if compact:
            self.n_row = _xyz_row([("X", self.nx), ("Y", self.ny), ("Z", self.nz)])
            _form_row(form, "法向:", self.n_row)
            self.nx_row = self.ny_row = self.nz_row = None
        else:
            self.nx_row = self._row(form, "法向 X:", self.nx)
            self.ny_row = self._row(form, "法向 Y:", self.ny)
            self.nz_row = self._row(form, "法向 Z:", self.nz)
            self.n_row = None

        # --- 三点 ---
        self.pts = []
        self.pt_rows = []
        for k in range(3):
            bx = _make_spinbox(0.0, -1e6, 1e6)
            by = _make_spinbox(0.0, -1e6, 1e6)
            bz = _make_spinbox(0.0, -1e6, 1e6)
            self.pts.append((bx, by, bz))
            if compact:
                self.pt_rows.append(
                    self._row(form, f"P{k+1}:",
                              _xyz_row([("X", bx), ("Y", by), ("Z", bz)])))
            else:
                self.pt_rows.append(self._row(form, f"P{k+1} X:", bx))
                self.pt_rows.append(self._row(form, f"P{k+1} Y:", by))
                self.pt_rows.append(self._row(form, f"P{k+1} Z:", bz))

        self.mode.currentIndexChanged.connect(self._sync)
        self._sync()

    @staticmethod
    def _row(form, label, widget):
        form.addRow(label, widget)
        try:
            return (form.labelForField(widget), widget)
        except Exception:
            return (None, widget)

    def _set_visible(self, rows, visible):
        # 兼容两种形态：(标签控件, 输入控件) 元组，或紧凑模式下的裸容器控件
        for item in rows:
            if isinstance(item, tuple):
                lbl, w = item
                if lbl is not None:
                    lbl.setVisible(visible)
                w.setVisible(visible)
            else:
                item.setVisible(visible)

    def _sync(self):
        m = self.mode.currentIndex()
        self._set_visible([self.std_row], m == 0)
        if self.n_row is not None:
            self._set_visible([self.n_row], m == 1)
        else:
            self._set_visible([self.nx_row, self.ny_row, self.nz_row], m == 1)
        self._set_visible(self.pt_rows, m == 2)

    def build(self) -> PlaneSpec:
        origin = (self.ox.value(), self.oy.value(), self.oz.value())
        m = self.mode.currentIndex()
        if m == 0:
            return PlaneSpec.from_named(PLANE_KEYS[self.std_combo.currentIndex()],
                                        origin)
        if m == 1:
            n = (self.nx.value(), self.ny.value(), self.nz.value())
            if abs(n[0]) + abs(n[1]) + abs(n[2]) < 1e-9:
                raise GeometryError("法向向量不能为零向量。")
            return PlaneSpec.from_point_normal(origin, n)
        p1, p2, p3 = [tuple(w.value() for w in t) for t in self.pts]
        return PlaneSpec.from_three_points(p1, p2, p3)


class ProfilePanel(QGroupBox):
    """底面轮廓输入面板：正 n 边形 / 星形 / 顶点表。

    compact=True 时只放"轮廓类型 + 参数"（1~3 行），顶点表交给外层标签页，
    避免这块长期占掉 150px 以上高度。
    """

    def __init__(self, parent=None, compact=False):
        super().__init__("底面轮廓", parent)
        self._compact = compact
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        form = _apply_form_layout(QFormLayout(), margin=0)

        self.mode = QComboBox()
        self.mode.addItems(PROFILE_MODE_LABELS_SHORT if compact
                           else PROFILE_MODE_LABELS)
        for i, full in enumerate(PROFILE_MODE_LABELS):
            self.mode.setItemData(i, full, Qt.ToolTipRole)
        _form_row(form, "轮廓类型:", self.mode)

        self.n_spin = QSpinBox()
        self.n_spin.setRange(3, 400)
        self.n_spin.setValue(6)
        self.n_spin.setMaximumWidth(SPIN_WIDTH)
        self.n_spin_row = None
        form.addRow("边数 n:", self.n_spin)

        self.radius_spin = _make_spinbox(50.0, 0.01, 1e6)
        self.radius_spin.setToolTip("外接圆半径（正 n 边形 / 星形外半径）")
        form.addRow("外接圆半径 R:", self.radius_spin)

        self.rin_spin = _make_spinbox(22.0, 0.01, 1e6)
        self.rin_spin.setToolTip("星形内半径（必须小于外半径）")
        form.addRow("星形内半径 Ri:", self.rin_spin)

        layout.addLayout(form)

        self.table = QPlainTextEdit()
        self.table.setPlaceholderText(TABLE_PLACEHOLDER_XY)
        if compact:
            self.table.setMinimumHeight(80)
        else:
            self.table.setMinimumHeight(150)
            layout.addWidget(self.table)

            btn_row = QHBoxLayout()
            btn_row.setSpacing(4)
            self.btn_fill = QPushButton("按上面参数生成顶点")
            self.btn_fill.clicked.connect(self._fill_from_params)
            btn_row.addWidget(self.btn_fill)
            self.btn_clear = QPushButton("清空")
            self.btn_clear.clicked.connect(lambda: self.table.setPlainText(""))
            btn_row.addWidget(self.btn_clear)
            layout.addLayout(btn_row)

        if compact:
            self.btn_fill = QPushButton("按上面参数生成顶点")
            self.btn_fill.clicked.connect(self._fill_from_params)
            self.btn_clear = QPushButton("清空")
            self.btn_clear.clicked.connect(lambda: self.table.setPlainText(""))

        self.mode.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self):
        m = self.mode.currentIndex()
        is_reg = (m == 0)
        is_star = (m == 1)
        is_table = (m >= 2)
        self.n_spin.setVisible(is_reg or is_star)
        self.radius_spin.setVisible(is_reg or is_star)
        self.rin_spin.setVisible(is_star)
        if not self._compact:
            self.table.setVisible(is_table)
            self.btn_fill.setVisible(is_table)
            self.btn_clear.setVisible(is_table)
        if is_table:
            self.table.setPlaceholderText(
                TABLE_PLACEHOLDER_POLAR if m == 3 else TABLE_PLACEHOLDER_XY)

    def is_table_mode(self) -> bool:
        return self.mode.currentIndex() >= 2

    def _fill_from_params(self):
        m = self.mode.currentIndex()
        n = self.n_spin.value()
        r = self.radius_spin.value()
        if m == 3:
            lines = [f"{r}, {360.0 * i / n:.6g}" for i in range(n)]
        else:
            lines = []
            for i in range(n):
                th = math.radians(360.0 * i / n)
                lines.append(f"{r * math.cos(th):.6g}, {r * math.sin(th):.6g}")
        self.table.setPlainText("\n".join(lines))

    def build(self) -> Profile:
        m = self.mode.currentIndex()
        if m == 0:
            return Profile.regular(self.n_spin.value(), self.radius_spin.value())
        if m == 1:
            return Profile.star(self.n_spin.value(),
                                self.radius_spin.value(),
                                self.rin_spin.value())
        pairs = _parse_table(self.table.toPlainText(), polar=(m == 3))
        return Profile.from_polar(pairs) if m == 3 else Profile.from_xy(pairs)


class ObliquePanel(QGroupBox):
    """斜置面板：只做"平面内错位"。

    为什么没有扭转角：
        顶面相对底面做独立扭转（β ≠ 0）时，侧棱增量不再与底边平行，
        侧面失去共面性、变成双曲抛物面，因此无法封闭为实体，只能输出曲面。
        而"顶面中心在截面平面内错开 (pu, pv)"已经完整覆盖斜置这一需求，
        且侧面恒为平面梯形，永远可以出实体。
        所以扭转被有意移除，不是遗漏。
    """

    def __init__(self, parent=None, compact=False):
        self._compact = compact
        super().__init__("斜置（顶面错位）", parent)
        form = _apply_form_layout(QFormLayout(self))

        self.pu = _make_spinbox(0.0, -1e6, 1e6)
        self.pv = _make_spinbox(0.0, -1e6, 1e6)
        self.pu.setToolTip("顶面中心相对底面中心，在截面平面内的错位（沿 u 方向）\n"
                           "只要 (pu, pv) 不为零，顶面与底面的投影就不重合，"
                           "即得到斜置形态")
        self.pv.setToolTip("顶面中心相对底面中心，在截面平面内的错位（沿 v 方向）")
        if compact:
            _form_row(form, "错位 pu/pv:", _hrow([self.pu, self.pv]))
        else:
            form.addRow("错位 pu:", self.pu)
            form.addRow("错位 pv:", self.pv)

        self.lbl_tilt = QLabel("—")
        form.addRow("倾斜角（只读）:", self.lbl_tilt)

        for w in (self.pu, self.pv):
            w.valueChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        pass   # 倾斜角需要 h，由对话框统一刷新

    def set_tilt(self, text):
        self.lbl_tilt.setText(text)

    def offset(self):
        return (self.pu.value(), self.pv.value())


# ============================================================
# 只读派生量面板（右栏）
# ============================================================

class DerivedPanel(QGroupBox):
    """只读派生量集中显示，取代原来散落在各参数组里的行。"""

    def __init__(self, rows, parent=None, title="派生量（只读）"):
        super().__init__(title, parent)
        form = _apply_form_layout(QFormLayout(self), margin=6)
        self.labels = {}
        for key, label, tip in rows:
            lab = QLabel("—")
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if tip:
                lab.setToolTip(tip)
            form.addRow(label, lab)
            self.labels[key] = lab

    def set(self, key, text):
        lab = self.labels.get(key)
        if lab is not None:
            lab.setText(text)


# ============================================================
# 对话框 A：多边形（棱柱/棱锥/棱台 + 斜拟柱体）
# ============================================================

class PolyhedronDialog(QDialog):
    """多边形拟柱体：棱柱 / 棱锥 / 棱台（含斜置）。

    布局：左侧参数（随窗口缩放）+ 右侧只读派生量，中间用 QSplitter 分隔，
    用户可以拖动分隔条调整比例。窗口拉得过小时出现滚动条。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生成多边形拟柱体（含斜置）")

        self._suppress = False
        self._last_driver = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        # 左右分栏：可拖动分隔条，比例随用户调整
        self.split = QSplitter(Qt.Horizontal)
        outer.addWidget(self.split, 1)

        # ---------------- 左：参数 ----------------
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)
        lv.setSpacing(8)

        # --- 尺寸 / 输出 ---
        grp_size = QGroupBox("尺寸 / 输出")
        form_size = _apply_form_layout(QFormLayout(grp_size))
        self.h_spin = _make_spinbox(80.0, 0.01, 1e6)
        self.h_spin.setToolTip("两个平行截面平面的垂直间距，不是轴长。")
        _form_row(form_size, "垂直高 h:", self.h_spin)
        self.k_spin = _make_spinbox(1.0, 0.0, 100.0, decimals=4)
        self.k_spin.setToolTip("顶面相对底面的均匀位似比：\n"
                               "k=0 锥 / (0,1) 台 / 1 柱 / >1 倒台\n"
                               "k=0 时顶面以极小截面近似（误差约 0.1%）")
        _form_row(form_size, "缩放比 k:", self.k_spin)
        # 输出每次生成都要用，必须一眼可见、随手可改
        self.output_combo = QComboBox()
        self.output_combo.addItems(["实体", "曲面"])
        _form_row(form_size, "输出类型:", self.output_combo)
        self.backend_combo = _make_backend_combo()
        _form_row(form_size, "生成方式:", self.backend_combo)
        lv.addWidget(grp_size)

        # --- 基准面 ---
        self.plane_panel = PlanePanel(compact=True)
        lv.addWidget(self.plane_panel)

        # --- 底面轮廓 ---
        self.profile_panel = ProfilePanel(compact=True)
        lv.addWidget(self.profile_panel)

        # --- 顶点表（内联，仅"顶点表"模式下出现）---
        self.table_block = QGroupBox("顶点表")
        v_tbl = QVBoxLayout(self.table_block)
        v_tbl.setContentsMargins(8, 8, 8, 8)
        v_tbl.setSpacing(6)
        self.profile_panel.table.setMinimumHeight(140)
        v_tbl.addWidget(self.profile_panel.table, 1)
        row_tbl = QHBoxLayout()
        row_tbl.setSpacing(6)
        row_tbl.addWidget(self.profile_panel.btn_fill)
        row_tbl.addWidget(self.profile_panel.btn_clear)
        row_tbl.addStretch()
        v_tbl.addLayout(row_tbl)
        self.table_block.setVisible(False)
        lv.addWidget(self.table_block)

        # --- 尺寸驱动（折叠块）---
        self.grp_driver = CollapsibleGroup("尺寸驱动（正 n 边形 / 星形）",
                                           expanded=False)
        form_drv = self.grp_driver.body_form()
        self.driver_combo = QComboBox()
        self.driver_combo.addItems(DRIVER_LABELS)
        _form_row(form_drv, "驱动量:", self.driver_combo)
        self.value_label = QLabel(f"{DRIVER_LABELS[0]}:")
        self.value_spin = _make_spinbox(50.0, 0.01, 1e6)
        form_drv.addRow(self.value_label, self.value_spin)
        self.btn_apply_driver = QPushButton("应用到『外接圆半径 R』")
        self.btn_apply_driver.clicked.connect(self._apply_driver)
        form_drv.addRow("", self.btn_apply_driver)
        lv.addWidget(self.grp_driver)

        # --- 斜置（主打功能，默认展开）---
        self.oblique_panel = ObliquePanel(compact=True)
        self.grp_oblique = CollapsibleGroup("斜置（顶面错位）", expanded=True)
        self.grp_oblique.add_body_widget(self.oblique_panel)
        lv.addWidget(self.grp_oblique)
        lv.addStretch(1)
        self.split.addWidget(left)

        # ---------------- 右：只读 + 校验 ----------------
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        rv.setSpacing(8)

        self.derived = DerivedPanel([
            ("side", "边长 a:", None),
            ("inradius", "内切圆半径:", None),
            ("cone", "锥顶距底面:", None),
            ("volume", "体积:", None),
            ("tilt", "倾斜角:", "offset 非零时顶面相对底面的倾斜角"),
        ], title="派生量（只读）")
        rv.addWidget(self.derived)

        self.grp_chk = CollapsibleGroup("校验明细", expanded=False)
        form_chk = self.grp_chk.body_form()
        self.btn_check = QPushButton("立即校验")
        self.btn_check.clicked.connect(self._run_checks)
        form_chk.addRow("", self.btn_check)
        self.lbl_chk = QLabel("—")
        self.lbl_chk.setWordWrap(True)
        self.lbl_chk.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form_chk.addRow(self.lbl_chk)
        rv.addWidget(self.grp_chk)
        rv.addStretch(1)
        self.split.addWidget(right)

        # 初始比例：参数区略宽于结果区
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 2)
        self.split.setChildrenCollapsible(False)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # --- 信号 ---
        self.value_spin.valueChanged.connect(self._update_readonly)
        self.h_spin.valueChanged.connect(self._update_readonly)
        self.k_spin.valueChanged.connect(self._update_readonly)
        self.oblique_panel.pu.valueChanged.connect(self._update_readonly)
        self.oblique_panel.pv.valueChanged.connect(self._update_readonly)
        self.profile_panel.mode.currentIndexChanged.connect(self._on_profile_mode)
        self.profile_panel.n_spin.valueChanged.connect(self._update_readonly)
        self.profile_panel.radius_spin.valueChanged.connect(self._update_readonly)
        self.profile_panel.rin_spin.valueChanged.connect(self._update_readonly)

        self._on_profile_mode()
        self._update_readonly()
        enforce_min_widths(grp_size, self.plane_panel, self.profile_panel,
                           self.grp_driver, self.oblique_panel)
        unify_label_columns(grp_size, self.plane_panel, self.profile_panel,
                            self.grp_driver, self.oblique_panel)
        _fit_to_content(self, 660)

    # ---------------- 逻辑 ----------------

    def _on_profile_mode(self):
        """顶点表块只在『顶点表』轮廓模式下出现。"""
        try:
            self.table_block.setVisible(self.profile_panel.is_table_mode())
        except Exception:
            pass
        self._update_readonly()

    def _current_radius(self):
        n = max(3, self.profile_panel.n_spin.value())
        v = self.value_spin.value()
        idx = self.driver_combo.currentIndex()
        if idx == 1:
            return radius_from_side(n, v)
        if idx == 2:
            return radius_from_inradius(n, v)
        return v

    def _apply_driver(self):
        r = self._current_radius()
        self.profile_panel.radius_spin.setValue(r)
        self._update_readonly()

    def _update_readonly(self):
        if self._suppress:
            return
        try:
            h = self.h_spin.value()
            k = self.k_spin.value()
            pu, pv = self.oblique_panel.offset()

            tilt = math.degrees(math.atan2(math.hypot(pu, pv), h))
            self.oblique_panel.set_tilt(f"{tilt:.4f}°")
            self.derived.set("tilt", f"{tilt:.4f}°")

            n = max(3, self.profile_panel.n_spin.value())
            r = self._current_radius()
            self.derived.set("side", _fmt(side_length(n, r)))
            self.derived.set("inradius", _fmt(inradius(n, r)))

            if abs(k - 1.0) < 1e-9:
                self.derived.set("cone", "∞（柱体）")
            else:
                self.derived.set("cone", _fmt(h / (1.0 - k)))

            d = derive_polygon(n, r, h, k)
            self.derived.set("volume", f"{d['volume']:.2f} mm³")
        except Exception as exc:
            self.derived.set("volume", f"计算失败: {exc}")

    def _run_checks(self):
        try:
            plane = self.plane_panel.build()
            prof = self.profile_panel.build()
        except Exception as exc:
            self.lbl_chk.setText(f"输入错误：{exc}")
            return

        rep = validate_profile(prof)
        lines = [
            f"顶点数：{rep['n']}",
            f"凸性：{'凸' if rep['convex'] else '凹'}",
            f"面积：{rep['area']:.3f} mm²",
            f"重合顶点：{rep['duplicates'] if rep['duplicates'] else '无'}",
            f"自交边对：{rep['self_intersections'] if rep['self_intersections'] else '无'}",
        ]
        try:
            d = derive_prismatoid(
                plane, prof, self.h_spin.value(), self.k_spin.value(),
                self.oblique_panel.offset(), 0.0,
                None)
            lines.append(f"侧面非共面数：{d['nonplanar_faces']}")
            lines.append(f"体积(公式)：{d['volume']:.3f} mm³")
            lines.append(f"体积(网格)：{d['volume_mesh']:.3f} mm³")
            lines.append(f"体积校核比：{d['volume_ratio']:.6f}  (应≈1)")
            lines.append(f"顶面相对底面倾斜角：{d['tilt_angle_deg']:.4f}°")
        except Exception as exc:
            lines.append(f"几何计算失败：{exc}")
        self.grp_chk._toggle.setChecked(True)
        self.grp_chk._on_toggle(True)
        self.lbl_chk.setText("\n".join(lines))

    def _on_ok(self):
        if not _check_controller(self):
            return
        try:
            plane = self.plane_panel.build()
            prof = self.profile_panel.build()
            result = create_prismatoid(
                plane=plane, profile=prof,
                height=self.h_spin.value(),
                k=self.k_spin.value(),
                offset=self.oblique_panel.offset(),
                # 扭转已移除：offset 使侧面恒为平面梯形，永远可以出实体
                twist_deg=0.0,
                output_solid=self.output_combo.currentIndex() == 0,
                allow_nonplanar=False,
                backend=BACKEND_KEYS[self.backend_combo.currentIndex()],
            )
            QMessageBox.information(self, "完成", _build_message(result))
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "错误", str(exc))

    def showEvent(self, event):
        cap_dialog_to_screen(self, 0.90)
        super().showEvent(event)
        _fit_to_content(self, 660, apply=True)


class CircularDialog(QDialog):
    """圆形拟柱体：圆柱 / 圆锥 / 圆台（含斜置）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生成圆形拟柱体（含斜置）")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        self.split = QSplitter(Qt.Horizontal)
        outer.addWidget(self.split, 1)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)
        lv.setSpacing(8)

        grp_size = QGroupBox("尺寸 / 输出")
        form_size = _apply_form_layout(QFormLayout(grp_size))
        self.radius_spin = _make_spinbox(50.0, 0.01, 1e6)
        _form_row(form_size, "底面半径 r:", self.radius_spin)
        self.h_spin = _make_spinbox(80.0, 0.01, 1e6)
        self.h_spin.setToolTip("两个平行截面平面的垂直间距，不是轴长。")
        _form_row(form_size, "垂直高 h:", self.h_spin)
        self.k_spin = _make_spinbox(1.0, 0.0, 100.0, decimals=4)
        self.k_spin.setToolTip("k=0 圆锥 / (0,1) 圆台 / 1 圆柱 / >1 倒台\n"
                               "k=0 时顶面以极小截面近似（误差约 0.1%）")
        _form_row(form_size, "缩放比 k:", self.k_spin)
        self.output_combo = QComboBox()
        self.output_combo.addItems(["实体", "曲面"])
        _form_row(form_size, "输出类型:", self.output_combo)
        self.backend_combo = _make_backend_combo()
        _form_row(form_size, "生成方式:", self.backend_combo)
        lv.addWidget(grp_size)

        self.plane_panel = PlanePanel(compact=True)
        lv.addWidget(self.plane_panel)

        self.oblique_panel = ObliquePanel(compact=True)
        self.grp_oblique = CollapsibleGroup("斜置（顶面错位）", expanded=True)
        self.grp_oblique.add_body_widget(self.oblique_panel)
        lv.addWidget(self.grp_oblique)
        lv.addStretch(1)
        self.split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        rv.setSpacing(8)
        self.derived = DerivedPanel([
            ("top_r", "顶部半径:", None),
            ("cone", "锥顶距底面:", None),
            ("volume", "体积:", None),
            ("tilt", "倾斜角:", None),
        ], title="派生量（只读）")
        rv.addWidget(self.derived)
        rv.addStretch(1)
        self.split.addWidget(right)

        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 2)
        self.split.setChildrenCollapsible(False)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        for w in (self.radius_spin, self.h_spin, self.k_spin,
                  self.oblique_panel.pu, self.oblique_panel.pv):
            w.valueChanged.connect(self._update_readonly)

        self._update_readonly()
        enforce_min_widths(grp_size, self.plane_panel, self.oblique_panel)
        unify_label_columns(grp_size, self.plane_panel, self.oblique_panel)
        _fit_to_content(self, 560)

    def _update_readonly(self):
        try:
            r = self.radius_spin.value()
            h = self.h_spin.value()
            k = self.k_spin.value()
            pu, pv = self.oblique_panel.offset()
            tilt = math.degrees(math.atan2(math.hypot(pu, pv), h))
            self.oblique_panel.set_tilt(f"{tilt:.4f}°")
            self.derived.set("tilt", f"{tilt:.4f}°")

            self.derived.set("top_r",
                             "≈0（锥顶，极小截面近似）"
                             if abs(k) < 1e-9 else _fmt(k * r))
            self.derived.set("cone",
                             "∞（柱体）" if abs(k - 1.0) < 1e-9
                             else _fmt(h / (1.0 - k)))
            self.derived.set("volume",
                             f"{derive_circular(r, h, k)['volume']:.2f} mm³")
        except Exception as exc:
            self.derived.set("volume", f"计算失败: {exc}")

    def _on_ok(self):
        if not _check_controller(self):
            return
        try:
            plane = self.plane_panel.build()
            result = create_circular_prismatoid(
                plane=plane,
                radius=self.radius_spin.value(),
                height=self.h_spin.value(),
                k=self.k_spin.value(),
                offset=self.oblique_panel.offset(),
                output_solid=self.output_combo.currentIndex() == 0,
                backend=BACKEND_KEYS[self.backend_combo.currentIndex()],
            )
            QMessageBox.information(self, "完成", _build_message(result))
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "错误", str(exc))

    def showEvent(self, event):
        cap_dialog_to_screen(self, 0.90)
        super().showEvent(event)
        _fit_to_content(self, 560, apply=True)


# ============================================================
# 主窗口
# ============================================================

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"CATIA 参数化图形生成器 2.0  [内核 {CONTROLLER_VERSION}]")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel("CATIA 参数化图形生成器 2.0")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel("先打开 CATIA V5 并新建／打开一个 Part 文档。")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666;")
        layout.addWidget(desc)

        btn_poly = QPushButton("生成多边形拟柱体")
        btn_poly.setToolTip("棱柱 / 棱锥 / 棱台，含斜置、任意基准面、任意多边形")
        btn_poly.setMinimumHeight(34)
        btn_poly.clicked.connect(self._open_poly)
        layout.addWidget(btn_poly)

        btn_circ = QPushButton("生成圆形拟柱体")
        btn_circ.setToolTip("圆柱 / 圆锥 / 圆台，含斜置、任意基准面")
        btn_circ.setMinimumHeight(34)
        btn_circ.clicked.connect(self._open_circ)
        layout.addWidget(btn_circ)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        btn_ver = QPushButton("版本信息")
        btn_ver.clicked.connect(self._show_version)
        tools.addWidget(btn_ver)
        btn_diag = QPushButton("能力自检")
        btn_diag.clicked.connect(self._run_diag)
        tools.addWidget(btn_diag)
        btn_sig = QPushButton("API 签名")
        btn_sig.clicked.connect(self._dump_sig)
        tools.addWidget(btn_sig)
        layout.addLayout(tools)

        hint = QLabel(f"内核 {CONTROLLER_VERSION}　|　斜置 / 任意平面 / 任意多边形")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

    def _open_poly(self):
        try:
            PolyhedronDialog(self).exec()
        except Exception as exc:
            QMessageBox.critical(self, "对话框错误", f"无法打开对话框：\n{exc}")

    def _open_circ(self):
        try:
            CircularDialog(self).exec()
        except Exception as exc:
            QMessageBox.critical(self, "对话框错误", f"无法打开对话框：\n{exc}")

    def _run_diag(self):
        if not _check_controller(self):
            return
        ans = QMessageBox.question(
            self, "确认执行自检",
            "自检会在 CATIA 中新建并关闭若干【空】Part 文档（不保存）。\n"
            "请先确认手头正在编辑的文档已保存。\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ans != QMessageBox.Yes:
            return
        try:
            results, conclusion = run_diagnostics()
        except Exception as exc:
            QMessageBox.critical(self, "自检失败", f"自检过程异常：\n{exc}")
            return

        lines = ["【〇、版本与路径】", version_info(), "", "【自检明细】"]
        for idx, r in enumerate(results, start=1):
            lines.append(f"[{idx}] {'通过' if r['ok'] else '失败'}  {r['case']}")
            for stage, ok2, msg in r["rows"]:
                lines.append(f"       {'✓' if ok2 else '✗'} {stage}")
                if msg:
                    lines.append(f"         {msg}")
            for d in r.get("diag", []):
                lines.append(f"       · {d}")
        lines += ["", "=" * 64, "【结论】", conclusion]
        TextDialog("能力自检结果", "\n".join(lines), self).exec()

    def _dump_sig(self):
        if not _check_controller(self):
            return
        try:
            text = dump_signatures()
        except Exception as exc:
            text = f"获取签名失败：{exc}"
        TextDialog("API 方法签名", text, self, width=760, height=520).exec()

    def _show_version(self):
        if CONTROLLER_ERROR is not None:
            QMessageBox.critical(self, "无法连接 CATIA",
                                 f"内核未加载成功。\n\n{CONTROLLER_ERROR}")
            return
        try:
            text = version_info()
        except Exception as exc:
            text = f"读取版本信息失败：{exc}"
        text += f"\n\n本界面文件：{os.path.abspath(__file__)}"
        TextDialog("版本 / 路径信息", text, self, width=720, height=420).exec()


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
