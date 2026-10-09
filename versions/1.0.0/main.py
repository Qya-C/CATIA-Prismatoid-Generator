# -*- coding: utf-8 -*-
"""
main.py
CATIA 参数化图形生成插件 - 主界面
运行前请确保 CATIA V5 已经打开，并存在一个 Part 文档。
"""

import sys
import math
import os

from PySide6.QtWidgets import (
    QApplication, QDialog, QFormLayout, QDialogButtonBox,
    QVBoxLayout, QComboBox, QLabel, QGroupBox,
    QPushButton, QMessageBox, QWidget, QDoubleSpinBox, QSpinBox,
    QPlainTextEdit,
)
from PySide6.QtCore import Qt

try:
    # 注意：本行已适配版本化文件名 catia_controller_v1.py
    from catia_controller_v1 import (
        create_polyhedron, create_circular_solid,
        run_diagnostics, dump_signatures, version_info,
        derive_polygon, derive_circular,
        side_length, inradius, radius_from_side, radius_from_inradius,
        PLANE_KEYS, PLANE_LABELS, BACKEND_KEYS, BACKEND_LABELS,
        __version__ as CONTROLLER_VERSION,
    )
    CONTROLLER_ERROR = None
except Exception as _exc:      # pragma: no cover
    CONTROLLER_ERROR = _exc
    CONTROLLER_VERSION = "未知"


DRIVER_LABELS = ["外接圆半径 R", "边长 a", "内切圆半径 r_in"]


# ============================================================ 辅助

def _make_spinbox(value, min_val, max_val, decimals=3, step=1.0):
    sb = QDoubleSpinBox()
    sb.setRange(min_val, max_val)
    sb.setDecimals(decimals)
    sb.setSingleStep(step)
    sb.setValue(value)
    return sb


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
    if result.is_solid:
        head = f"已生成实体（路线：{result.used_backend or '—'}）。"
    else:
        head = f"已生成曲面（路线：{result.used_backend or '—'}）。"
    head += "请在 CATIA 中按 Ctrl+U 更新视图。"
    if result.diagnostics:
        head += "\n\n提示：\n" + "\n".join(f"· {d}" for d in result.diagnostics)
    return head


class TextDialog(QDialog):
    """通用只读文本对话框。"""

    def __init__(self, title, text, parent=None, width=820, height=620):
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
    cb.setToolTip(
        "自动 / GSD：多截面放样 + 端盖 + 封闭，覆盖全部六种图形。\n"
        "Part Design：本机实测不可用（Pad 接口报错），仅供排查。"
    )
    return cb


# ============================================================
# 对话框 A：多边形棱柱/棱锥/棱台
# ============================================================

class PolyhedronDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生成多边形棱柱 / 棱锥 / 棱台")
        self.setMinimumWidth(490)

        self._suppress = False
        self._last_driver = 0

        layout = QVBoxLayout(self)

        # --- 基准 ---
        grp_base = QGroupBox("基准")
        form_base = QFormLayout(grp_base)
        self.plane_combo = QComboBox()
        self.plane_combo.addItems(PLANE_LABELS)
        form_base.addRow("基准面:", self.plane_combo)

        self.base_x = _make_spinbox(0.0, -1e6, 1e6)
        self.base_y = _make_spinbox(0.0, -1e6, 1e6)
        self.base_z = _make_spinbox(0.0, -1e6, 1e6)
        form_base.addRow("底面中心 X:", self.base_x)
        form_base.addRow("底面中心 Y:", self.base_y)
        form_base.addRow("底面中心 Z:", self.base_z)
        layout.addWidget(grp_base)

        # --- 轮廓 ---
        grp_profile = QGroupBox("轮廓")
        form_profile = QFormLayout(grp_profile)

        self.n_spin = QSpinBox()
        self.n_spin.setRange(3, 200)
        self.n_spin.setValue(6)
        self.n_spin.setToolTip("n 是拓扑参数，创建后不可修改；需要改 n 请重新生成。")
        form_profile.addRow("边数 n（创建后不可改）:", self.n_spin)

        self.driver_combo = QComboBox()
        self.driver_combo.addItems(DRIVER_LABELS)
        form_profile.addRow("驱动量:", self.driver_combo)

        self.value_label = QLabel(f"{DRIVER_LABELS[0]}:")
        self.value_spin = _make_spinbox(50.0, 0.01, 1e6)
        form_profile.addRow(self.value_label, self.value_spin)

        self.lbl_side = QLabel("—")
        self.lbl_inradius = QLabel("—")
        form_profile.addRow("边长 a（只读）:", self.lbl_side)
        form_profile.addRow("内切圆半径（只读）:", self.lbl_inradius)
        layout.addWidget(grp_profile)

        # --- 尺寸 ---
        grp_size = QGroupBox("尺寸")
        form_size = QFormLayout(grp_size)

        self.h_spin = _make_spinbox(80.0, 0.01, 1e6)
        self.h_spin.setToolTip("两个平行截面平面的垂直间距，不是轴长。")
        form_size.addRow("垂直高 h:", self.h_spin)

        self.k_spin = _make_spinbox(1.0, 0.0, 100.0, decimals=4)
        self.k_spin.setToolTip(
            "顶面相对底面的位似比：\n"
            "k=0 锥体 / 0<k<1 棱台 / k=1 棱柱 / k>1 倒台\n"
            "注：k=0 的顶面以极小截面近似（误差约 0.1%）"
        )
        form_size.addRow("缩放比 k（0=锥）:", self.k_spin)

        self.lbl_top_r = QLabel("—")
        form_size.addRow("顶部外接半径（只读）:", self.lbl_top_r)

        self.lbl_cone_dist = QLabel("—")
        form_size.addRow("锥顶距底面（只读）:", self.lbl_cone_dist)

        self.lbl_volume = QLabel("—")
        form_size.addRow("体积（只读）:", self.lbl_volume)
        layout.addWidget(grp_size)

        # --- 输出 ---
        grp_out = QGroupBox("输出")
        form_out = QFormLayout(grp_out)
        self.output_combo = QComboBox()
        self.output_combo.addItems(["实体", "曲面"])
        form_out.addRow("输出类型:", self.output_combo)

        self.backend_combo = _make_backend_combo()
        form_out.addRow("生成方式:", self.backend_combo)
        layout.addWidget(grp_out)

        # --- 按钮 ---
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # --- 信号 ---
        self.n_spin.valueChanged.connect(self._on_n_changed)
        self.driver_combo.currentIndexChanged.connect(self._on_driver_changed)
        self.value_spin.valueChanged.connect(self._update_readonly)
        self.h_spin.valueChanged.connect(self._update_readonly)
        self.k_spin.valueChanged.connect(self._update_readonly)

        self._update_readonly()

    def _current_radius(self):
        n = max(3, self.n_spin.value())
        v = self.value_spin.value()
        idx = self.driver_combo.currentIndex()
        if idx == 1:
            return radius_from_side(n, v)
        if idx == 2:
            return radius_from_inradius(n, v)
        return v

    def _on_n_changed(self, _v):
        self._update_readonly()

    def _on_driver_changed(self, idx):
        if self._suppress:
            return
        self._suppress = True
        try:
            n = max(3, self.n_spin.value())
            v = self.value_spin.value()
            old = self._last_driver
            r = (radius_from_side(n, v) if old == 1 else
                 radius_from_inradius(n, v) if old == 2 else v)
            new_v = (side_length(n, r) if idx == 1 else
                     inradius(n, r) if idx == 2 else r)
            self.value_spin.setValue(new_v)
            self.value_label.setText(f"{DRIVER_LABELS[idx]}:")
            self._last_driver = idx
        finally:
            self._suppress = False
        self._update_readonly()

    def _update_readonly(self):
        if self._suppress:
            return
        try:
            n = max(3, self.n_spin.value())
            r = self._current_radius()
            h = self.h_spin.value()
            k = self.k_spin.value()

            self.lbl_side.setText(_fmt(side_length(n, r)))
            self.lbl_inradius.setText(_fmt(inradius(n, r)))

            if abs(k) < 1e-9:
                self.lbl_top_r.setText("≈0（锥顶，极小截面近似）")
            else:
                self.lbl_top_r.setText(_fmt(k * r))

            if abs(k - 1.0) < 1e-9:
                self.lbl_cone_dist.setText("∞（柱体）")
            else:
                self.lbl_cone_dist.setText(_fmt(h / (1.0 - k)))

            self.lbl_volume.setText(f"{derive_polygon(n, r, h, k)['volume']:.2f} mm³")
        except Exception as exc:
            self.lbl_volume.setText(f"计算失败: {exc}")

    def _on_ok(self):
        if not _check_controller(self):
            return
        try:
            result = create_polyhedron(
                n=self.n_spin.value(),
                radius=self._current_radius(),
                height=self.h_spin.value(),
                k=self.k_spin.value(),
                output_solid=self.output_combo.currentIndex() == 0,
                plane=PLANE_KEYS[self.plane_combo.currentIndex()],
                base_point=(self.base_x.value(), self.base_y.value(), self.base_z.value()),
                backend=BACKEND_KEYS[self.backend_combo.currentIndex()],
            )
            QMessageBox.information(self, "完成", _build_message(result))
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "错误", str(exc))


# ============================================================
# 对话框 B：圆形回转体
# ============================================================

class CircularDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生成圆柱 / 圆锥 / 圆台")
        self.setMinimumWidth(490)

        layout = QVBoxLayout(self)

        grp_base = QGroupBox("基准")
        form_base = QFormLayout(grp_base)
        self.plane_combo = QComboBox()
        self.plane_combo.addItems(PLANE_LABELS)
        form_base.addRow("基准面:", self.plane_combo)

        self.base_x = _make_spinbox(0.0, -1e6, 1e6)
        self.base_y = _make_spinbox(0.0, -1e6, 1e6)
        self.base_z = _make_spinbox(0.0, -1e6, 1e6)
        form_base.addRow("圆心 X:", self.base_x)
        form_base.addRow("圆心 Y:", self.base_y)
        form_base.addRow("圆心 Z:", self.base_z)
        layout.addWidget(grp_base)

        grp_size = QGroupBox("尺寸")
        form_size = QFormLayout(grp_size)

        self.radius_spin = _make_spinbox(50.0, 0.01, 1e6)
        form_size.addRow("底面半径 r:", self.radius_spin)

        self.h_spin = _make_spinbox(80.0, 0.01, 1e6)
        self.h_spin.setToolTip("两个平行截面平面的垂直间距，不是轴长。")
        form_size.addRow("垂直高 h:", self.h_spin)

        self.k_spin = _make_spinbox(1.0, 0.0, 100.0, decimals=4)
        self.k_spin.setToolTip(
            "顶面相对底面的位似比：\n"
            "k=0 圆锥 / 0<k<1 圆台 / k=1 圆柱 / k>1 倒台\n"
            "注：k=0 的顶面以极小截面近似（误差约 0.1%）"
        )
        form_size.addRow("缩放比 k（0=锥）:", self.k_spin)

        self.lbl_top_r = QLabel("—")
        form_size.addRow("顶部半径（只读）:", self.lbl_top_r)

        self.lbl_cone_dist = QLabel("—")
        form_size.addRow("锥顶距底面（只读）:", self.lbl_cone_dist)

        self.lbl_volume = QLabel("—")
        form_size.addRow("体积（只读）:", self.lbl_volume)

        self.radius_spin.valueChanged.connect(self._update_readonly)
        self.h_spin.valueChanged.connect(self._update_readonly)
        self.k_spin.valueChanged.connect(self._update_readonly)

        layout.addWidget(grp_size)

        grp_out = QGroupBox("输出")
        form_out = QFormLayout(grp_out)
        self.output_combo = QComboBox()
        self.output_combo.addItems(["实体", "曲面"])
        form_out.addRow("输出类型:", self.output_combo)

        self.backend_combo = _make_backend_combo()
        form_out.addRow("生成方式:", self.backend_combo)
        layout.addWidget(grp_out)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_readonly()

    def _update_readonly(self):
        try:
            r = self.radius_spin.value()
            h = self.h_spin.value()
            k = self.k_spin.value()

            if abs(k) < 1e-9:
                self.lbl_top_r.setText("≈0（锥顶，极小截面近似）")
            else:
                self.lbl_top_r.setText(_fmt(k * r))

            if abs(k - 1.0) < 1e-9:
                self.lbl_cone_dist.setText("∞（柱体）")
            else:
                self.lbl_cone_dist.setText(_fmt(h / (1.0 - k)))

            self.lbl_volume.setText(f"{derive_circular(r, h, k)['volume']:.2f} mm³")
        except Exception as exc:
            self.lbl_volume.setText(f"计算失败: {exc}")

    def _on_ok(self):
        if not _check_controller(self):
            return
        try:
            result = create_circular_solid(
                radius=self.radius_spin.value(),
                height=self.h_spin.value(),
                k=self.k_spin.value(),
                output_solid=self.output_combo.currentIndex() == 0,
                plane=PLANE_KEYS[self.plane_combo.currentIndex()],
                base_point=(self.base_x.value(), self.base_y.value(), self.base_z.value()),
                backend=BACKEND_KEYS[self.backend_combo.currentIndex()],
            )
            QMessageBox.information(self, "完成", _build_message(result))
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "错误", str(exc))


# ============================================================
# 主窗口
# ============================================================

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"CATIA 参数化图形生成器  [内核 {CONTROLLER_VERSION}]")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)

        title = QLabel("CATIA 参数化图形生成器")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 8px;")
        layout.addWidget(title)

        ver = QLabel(f"内核版本：{CONTROLLER_VERSION}")
        ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet("color: #666; padding-bottom: 6px;")
        layout.addWidget(ver)

        desc = QLabel(
            "请先打开 CATIA V5 并新建或打开一个 Part 文档。\n"
            "若生成时报错，请先执行『能力自检』。"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn_poly = QPushButton("生成多边形棱柱 / 棱锥 / 棱台")
        btn_poly.setMinimumHeight(48)
        btn_poly.clicked.connect(self._open_poly)
        layout.addWidget(btn_poly)

        btn_circ = QPushButton("生成圆柱 / 圆锥 / 圆台")
        btn_circ.setMinimumHeight(48)
        btn_circ.clicked.connect(self._open_circ)
        layout.addWidget(btn_circ)

        btn_diag = QPushButton("能力自检（定位 Update 失败）")
        btn_diag.setMinimumHeight(40)
        btn_diag.clicked.connect(self._run_diag)
        layout.addWidget(btn_diag)

        btn_sig = QPushButton("打印 API 方法签名")
        btn_sig.setMinimumHeight(34)
        btn_sig.clicked.connect(self._dump_sig)
        layout.addWidget(btn_sig)

        btn_ver = QPushButton("显示版本 / 路径信息")
        btn_ver.setMinimumHeight(34)
        btn_ver.clicked.connect(self._show_version)
        layout.addWidget(btn_ver)

        layout.addStretch()

    def _open_poly(self):
        try:
            PolyhedronDialog(self).exec()
        except Exception as exc:
            QMessageBox.critical(self, "多边形对话框错误", f"无法打开对话框：\n{exc}")

    def _open_circ(self):
        try:
            CircularDialog(self).exec()
        except Exception as exc:
            QMessageBox.critical(self, "圆形对话框错误", f"无法打开对话框：\n{exc}")

    def _run_diag(self):
        if not _check_controller(self):
            return
        ans = QMessageBox.question(
            self, "确认执行自检",
            "自检会在 CATIA 中新建并关闭若干【空】Part 文档（不保存）。\n"
            "请先确认手头正在编辑的文档已保存。\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if ans != QMessageBox.Yes:
            return
        try:
            results, conclusion = run_diagnostics()
        except Exception as exc:
            QMessageBox.critical(self, "自检失败", f"自检过程异常：\n{exc}")
            return

        lines = ["【〇、版本与路径】", version_info(), ""]
        lines.append("【自检明细】")
        for idx, r in enumerate(results, start=1):
            lines.append(f"[{idx}] {'通过' if r['ok'] else '失败'}  {r['case']}")
            for stage, ok2, msg in r["rows"]:
                lines.append(f"       {'✓' if ok2 else '✗'} {stage}")
                if msg:
                    lines.append(f"         {msg}")
            for d in r.get("diag", []):
                lines.append(f"       · {d}")
        lines.append("")
        lines.append("=" * 64)
        lines.append("【结论】")
        lines.append(conclusion)

        TextDialog("能力自检结果", "\n".join(lines), self,
                   width=880, height=680).exec()

    def _dump_sig(self):
        if not _check_controller(self):
            return
        try:
            text = dump_signatures()
        except Exception as exc:
            text = f"获取签名失败：{exc}"
        TextDialog("API 方法签名", text, self, width=800, height=600).exec()

    def _show_version(self):
        if CONTROLLER_ERROR is not None:
            QMessageBox.critical(
                self, "无法连接 CATIA",
                f"内核未加载成功，版本信息不可用。\n\n详细错误：\n{CONTROLLER_ERROR}",
            )
            return
        try:
            text = version_info()
        except Exception as exc:
            text = f"读取版本信息失败：{exc}"
        text += f"\n\n本界面文件：{os.path.abspath(__file__)}"
        TextDialog("版本 / 路径信息", text, self, width=780, height=480).exec()


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())