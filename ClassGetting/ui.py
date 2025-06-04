from typing import List
import json
import os
import base64

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QLabel, QComboBox, QLineEdit, QListWidget, QListWidgetItem
from pysjtu.models import SelectionClass

ACCOUNTS_FILE = "accounts.json"

def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_account(username, password):
    accounts = load_accounts()
    # 简单去重
    accounts = [acc for acc in accounts if acc["username"] != username]
    accounts.insert(0, {"username": username, "password": password})
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

def get_password(username):
    accounts = load_accounts()
    for acc in accounts:
        if acc["username"] == username:
            return acc["password"]
    return ""

def lesson_time_to_str(time_field):
    # time_field 可能是 LessonTime 或 List[LessonTime]
    if not time_field:
        return "未知"
    if isinstance(time_field, list):
        times = time_field
    else:
        times = [time_field]
    weekday_map = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}
    result = []
    for t in times:
        weekday = weekday_map.get(t.weekday, str(t.weekday))
        # 处理周数
        week_str = "未知周"
        if hasattr(t, "week") and t.week:
            week_parts = []
            # 支持 range 或 int
            for w in t.week:
                if isinstance(w, range):
                    week_parts.append(f"{w.start}-{w.stop-1}周")
                else:
                    week_parts.append(f"{w}周")
            # 合并连续周为区间，不连续周用 /
            # 先把所有周数展开为列表
            week_nums = []
            for w in t.week:
                if isinstance(w, range):
                    week_nums.extend(list(w))
                else:
                    week_nums.append(w)
            week_nums = sorted(set(week_nums))
            # 合并连续区间
            ranges = []
            start = prev = week_nums[0]
            for num in week_nums[1:]:
                if num == prev + 1:
                    prev = num
                else:
                    if start == prev:
                        ranges.append(f"{start}")
                    else:
                        ranges.append(f"{start}-{prev}")
                    start = prev = num
            if start == prev:
                ranges.append(f"{start}")
            else:
                ranges.append(f"{start}-{prev}")
            week_str = "/".join(ranges) + "周"
        for rng in t.time:
            start = rng.start
            end = rng.stop - 1  # Python range 的 stop 是开区间
            result.append(f"星期{weekday} 第{start}-{end}节（{week_str}）")
    return "; ".join(result)

class CourseSelectionWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.on_select_course_handler = None
        self.on_remove_course_handler = None

        # 设置窗体标题和初始大小
        self.setWindowTitle('抢课助手')
        self.setFixedHeight(600)
        self.setFixedWidth(800)

        # 添加关键词搜索框
        keyword_label = QLabel('关键词：', self)
        keyword_label.setGeometry(50, 50, 60, 20)
        self.keyword_edit = QLineEdit(self)
        self.keyword_edit.setGeometry(110, 50, 200, 20)

        # 添加课程类型下拉框
        sector_label = QLabel('分区：', self)
        sector_label.setGeometry(400, 50, 80, 20)
        self.sector_combobox = QComboBox(self)
        self.sector_combobox.setGeometry(440, 50, 200, 20)

        # 添加课程搜索结果列表
        result_label = QLabel('搜索结果：', self)
        result_label.setGeometry(50, 100, 80, 20)
        self.result_list = QListWidget(self)
        self.result_list.setGeometry(50, 130, 350, 400)

        # 添加已选课程列表
        selected_label = QLabel('已选课程：', self)
        selected_label.setGeometry(450, 100, 80, 20)
        self.selected_list = QListWidget(self)
        self.selected_list.setGeometry(450, 130, 300, 400)

        # 添加选中框
        self.result_list.itemClicked.connect(self.on_result_item_clicked)
        self.result_list.setSelectionMode(QListWidget.MultiSelection)
        self.result_list.setSelectionBehavior(QListWidget.SelectRows)
        self.result_list.setAlternatingRowColors(True)
        # self.result_list.setStyleSheet("QListWidget::item:selected{background-color: rgb(200, 200, 200);}")

        # 新增：维护 selected_courses
        self.selected_courses = []

    def clear_selection(self):
        self.selected_list.clear()

    def finish_select(self, course: SelectionClass):
        for i in range(self.selected_list.count()):
            selected_item = self.selected_list.item(i)
            if selected_item.data(Qt.UserRole) == course:
                selected_item.setText(selected_item.text().replace("抢课中...", "已选上"))

    def set_on_select_course_handler(self, handler):
        self.on_select_course_handler = handler

    def set_on_remove_course_handler(self, handler):
        self.on_remove_course_handler = handler

    def add_sector_selection_handler(self, handler):
        self.sector_combobox.currentIndexChanged.connect(lambda: handler(self.sector_combobox.currentText()))

    def add_search_handler(self, handler):
        self.keyword_edit.returnPressed.connect(lambda: handler(self.keyword_edit.text()))

    def add_sectors(self, sectors: List[str]):
        self.sector_combobox.addItems(sectors)

    def set_search_results(self, results: List[SelectionClass]):
        print(results)
        self.result_list.clear()
        for result in results:
            self.add_search_result(result)

    def add_search_result(self, result: SelectionClass):
        teachers = ', '.join([t[0] for t in result.teachers]) if hasattr(result, 'teachers') and result.teachers else '未知'
        time_info = lesson_time_to_str(result.time)
        text = f"{result.name} | 教师: {teachers} | 时间: {time_info} | 容量：{result.students_registered}/{result.students_planned}"
        item = QListWidgetItem(text, self.result_list)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)
        item.setData(Qt.UserRole, result)

    def on_result_item_clicked(self, item):
        # 处理选中结果
        if item.checkState() == Qt.Checked:
            self.add_selected_item(item)
        else:
            self.remove_selected_item(item)

    def add_selected_item(self, item):
        course: SelectionClass = item.data(Qt.UserRole)
        selected_text = f"{course.name} 状态：抢课中..."
        selected_item = QListWidgetItem(selected_text, self.selected_list)
        selected_item.setData(Qt.UserRole, course)
        # 新增：维护 selected_courses
        if course not in self.selected_courses:
            self.selected_courses.append(course)
        if self.on_select_course_handler is not None:
            self.on_select_course_handler(course)

    def remove_selected_item(self, item):
        course: SelectionClass = item.data(Qt.UserRole)
        # 从已选列表中移除选中的课程
        for i in range(self.selected_list.count()):
            selected_item = self.selected_list.item(i)
            if selected_item.data(Qt.UserRole) == item.data(Qt.UserRole):
                self.selected_list.takeItem(i)
                if course in self.selected_courses:
                    self.selected_courses.remove(course)
                if self.on_remove_course_handler is not None:
                    self.on_remove_course_handler(course)
                break


class LoginDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(LoginDialog, self).__init__(parent)

        self.setWindowTitle('使用 Jaccount 登录')
        self.setFixedWidth(350)

        self.username_combo = QtWidgets.QComboBox(self)
        self.username_combo.setEditable(True)
        self.username_combo.setFixedWidth(200)
        accounts = load_accounts()
        self.username_combo.addItems([acc["username"] for acc in accounts])

        self.password_input = QtWidgets.QLineEdit(self)
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)

        # 选择历史账号时自动填充密码
        self.username_combo.currentIndexChanged.connect(
            lambda idx: self.fill_password(self.username_combo.currentText())
        )
        # 编辑框内容变化时也自动填充密码
        self.username_combo.lineEdit().textChanged.connect(self.fill_password)

        # 初始化时自动填充第一个账号的密码
        if self.username_combo.count() > 0:
            self.fill_password(self.username_combo.currentText())

        self.login_button = QtWidgets.QPushButton('登录', self)
        self.cancel_button = QtWidgets.QPushButton('取消', self)

        form_layout = QtWidgets.QFormLayout(self)
        form_layout.addRow('用户名:', self.username_combo)
        form_layout.addRow('密码:', self.password_input)
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.cancel_button)
        form_layout.addRow(button_layout)

        self.login_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def fill_password(self, username):
        pwd = get_password(username)
        self.password_input.setText(pwd)

    def get_username_password(self):
        return self.username_combo.currentText(), self.password_input.text()

    def accept(self):
        username, password = self.get_username_password()
        save_account(username, password)
        super(LoginDialog, self).accept()
