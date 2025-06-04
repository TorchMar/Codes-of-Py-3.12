import sys
import time
from threading import Thread
from typing import Optional, List

import pysjtu
from PyQt5 import QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal
from pysjtu.exceptions import LoginException, FullCapacityException, SelectionNotAvailableException
from pysjtu.models import SelectionSector, SelectionClass

from ui import LoginDialog, CourseSelectionWindow


class App:
    def __init__(self):
        self.daemon_map: dict = dict()
        self.app = QtWidgets.QApplication(sys.argv)
        self.cli: Optional[pysjtu.Client] = None
        self.selection_window: Optional[CourseSelectionWindow] = None
        self.sector: Optional[SelectionSector] = None
        self.selected_courses: List[SelectionClass] = []
        self.keyword: str = ""

    @staticmethod
    def quit():
        sys.exit(0)

    def handle_login(self):
        login_dialog = LoginDialog()
        while True:
            if login_dialog.exec_() == QtWidgets.QDialog.Accepted:
                username, password = login_dialog.get_username_password()
                print('用户名:', username)
                #print('密码:', password)
                # 显示“正在登录...”窗口
                logging_box = QtWidgets.QMessageBox(self.selection_window)
                logging_box.setWindowTitle("提示")
                logging_box.setText("正在登录...")
                logging_box.setStandardButtons(QtWidgets.QMessageBox.NoButton)
                logging_box.show()
                QtWidgets.QApplication.processEvents()  # 立即刷新界面
                try:
                    self.cli = pysjtu.create_client(username=username, password=password)
                    print('登录成功！')
                    print(f"已成功登录为{self.cli.student_id}。")
                    # 登录成功弹窗
                    QtWidgets.QMessageBox.information(
                        self.selection_window,
                        "登录成功！",
                        f"已成功登录为{self.cli.student_id}。"
                    )
                    return
                except LoginException:
                    print('用户名或密码错误！')
                    QtWidgets.QMessageBox.warning(
                        self.selection_window,
                        "提示",
                        "用户名或密码错误！"
                    )
                except Exception as e:
                    print(e)
            else:
                print('登录已取消！')
                self.quit()

    def fetch_sectors(self):
        try:
            sectors = [sector.name for sector in self.cli.course_selection_sectors]
            self.selection_window.add_sectors(sectors)
            self.sector = self.cli.course_selection_sectors[0]
        except SelectionNotAvailableException:
            print("对不起，当前不属于选课阶段。")
            QtWidgets.QMessageBox.warning(
                self.selection_window,
                "提示",
                "对不起，当前不属于选课阶段。"
            )
            self.quit()

    #def fetch_sectors(self):
    #    sectors = [sector.name for sector in self.cli.course_selection_sectors]
    #    self.selection_window.add_sectors(sectors)
    #    self.sector = self.cli.course_selection_sectors[0]
        
    @staticmethod
    def meet_keyword(klass: SelectionClass, keyword: str) -> bool:
        return keyword in klass.name or keyword in klass.class_name

    def fetch_search_results(self):
        if len(self.keyword) == 0:
            results = self.sector.classes
        else:
            results = list(filter(lambda klass: self.meet_keyword(klass, self.keyword), self.sector.classes))
        self.selection_window.set_search_results(results)

    def change_sector(self, sector: str):
        self.sector = next(filter(lambda s: s.name == sector, self.cli.course_selection_sectors))
        print(self.sector)
        self.clear_selection()
        self.fetch_search_results()

    def search(self, keyword: str):
        print(keyword)
        self.keyword = keyword
        self.fetch_search_results()
        
    def get_selected_class_of_same_course(self, course: SelectionClass):
        """
        检查当前课表中是否已选同一课程的其他班级
        返回已选班级对象，否则返回 None
        """
        # 获取当前学年和学期（请根据实际情况传参）
        year = 2025
        semester = 0
        try:
            schedule = self.cli.schedule(year, semester)
        except Exception as e:
            print("获取课表失败：", e)
            return None

        for klass in schedule:
            # pysjtu 的 schedule 返回的对象字段名可能和 SelectionClass 不完全一致，请根据实际字段名调整
            if hasattr(klass, "name") and hasattr(klass, "class_id"):
                if klass.name == course.name and klass.class_id != course.class_name:
                    return klass
        return None
    
    class SwitchClassDaemon(QThread):
        signal = pyqtSignal(SelectionClass)

        def __init__(self, old_class: SelectionClass, new_class: SelectionClass, app_ref):
            super().__init__()
            self.old_class = old_class
            self.new_class = new_class
            self.app_ref = app_ref

        def run(self):
            while True:
                time.sleep(1)
                try:
                    year = 2025
                    semester = 0
                    try:
                        schedule = self.app_ref.cli.schedule(year, semester)
                        # 判断是否还选着 old_class
                        has_old = any(
                            hasattr(k, "course_id") and hasattr(k, "class_id") and
                            k.course_id == self.old_class.course_id and k.class_id == self.old_class.class_id
                            for k in schedule
                        )
                        # sector.classes 里找 SelectionClass 实例
                        old_class = next((k for k in self.app_ref.sector.classes
                                          if k.class_id == self.old_class.class_id), self.old_class)
                        new_class = next((k for k in self.app_ref.sector.classes
                                          if k.class_id == self.new_class.class_id), self.new_class)
                    except Exception as e:
                        print("刷新课表失败：", e)
                        old_class = self.old_class
                        new_class = self.new_class
                        has_old = True  # 保守处理

                    if new_class.students_registered < new_class.students_planned:
                        print(f"{new_class.name} {new_class.class_name} 有余量，尝试切换")
                        # 只有还选着 old_class 时才退课
                        if has_old:
                            try:
                                old_class.drop()
                                print("退课成功")
                            except Exception as e:
                                print("退课失败", e)
                                time.sleep(1)
                                continue
                            time.sleep(1)  # 退课后等一会再选新班级
                        try:
                            new_class.register()
                            print("切换成功")
                            break
                        except Exception as e:
                            print("切换失败，尝试恢复原班级", e)
                            # 恢复原班级
                            try:
                                old_class.register()
                                print("恢复原班级成功")
                            except Exception as e2:
                                print("恢复原班级失败", e2)
                            time.sleep(1)
                    else:
                        print(f"{new_class.name} {new_class.class_name} 仍无余量，继续监听")
                except Exception as e:
                    print("监听或切换时异常", e)
            self.signal.emit(self.new_class)
        
    class SelectDaemon(QThread):
        signal = pyqtSignal(SelectionClass)

        def __init__(self, course: SelectionClass):
            self.course = course
            super().__init__()

        def run(self) -> None:
            while not self.course.is_registered():
                time.sleep(1)
                try:
                    print(f"Trying to register {self.course.name}...")
                    self.course.register()  # or klass.drop()
                    print("Succeed, quit")
                    break
                except FullCapacityException:
                    print(f"Failed, retry to register {self.course.name}")
                    pass  # retry
                except Exception as e:
                    print(e)  # or handle other exceptions
            print(f"{self.course.name} 的抢课守护线程退出")
            self.signal.emit(self.course)

    #def on_select_course(self, course: SelectionClass):
    #    daemon = App.SelectDaemon(course)
    #    daemon.signal.connect(self.selection_window.finish_select)
    #    self.daemon_map[course.name] = daemon
    #    daemon.start()
    def on_select_course(self, course: SelectionClass):
        old_class = self.get_selected_class_of_same_course(course)
        if old_class is None:
            # 直接抢课
            daemon = App.SelectDaemon(course)
            daemon.signal.connect(self.selection_window.finish_select)
            self.daemon_map[course.name] = daemon
            daemon.start()
        else:
            # 切换班级守护线程
            switch_daemon = App.SwitchClassDaemon(old_class, course, self)
            switch_daemon.signal.connect(self.selection_window.finish_select)
            key = f"{course.name}-{course.class_id}-switch"
            self.daemon_map[key] = switch_daemon
            switch_daemon.start()
            
    def clear_selection(self):
        #self.selection_window.clear_selection() #清空已选课程列表
        #for course in self.daemon_map:     #终止抢课进程
        #    self.daemon_map[course].quit()
        pass

    def on_remove_course(self, course: SelectionClass):
        key = f"{course.name}-{course.class_id}"
        if key in self.daemon_map:
            self.daemon_map[key].quit()
            del self.daemon_map[key]
        else:
            print(f"未找到 key={key} 的抢课线程")

    def handle_selection(self):
        self.selection_window = CourseSelectionWindow()
        self.selection_window.add_sector_selection_handler(self.change_sector)
        self.selection_window.add_search_handler(self.search)
        self.selection_window.set_on_select_course_handler(self.on_select_course)
        self.selection_window.set_on_remove_course_handler(self.on_remove_course)
        self.fetch_sectors()
        self.selection_window.show()

    def run(self):
        self.handle_login()
        self.handle_selection()
        sys.exit(self.app.exec_())
