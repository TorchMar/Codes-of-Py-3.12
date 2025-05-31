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

    def on_select_course(self, course: SelectionClass):
        daemon = App.SelectDaemon(course)
        daemon.signal.connect(self.selection_window.finish_select)
        self.daemon_map[course.name] = daemon
        daemon.start()

    def clear_selection(self):
        #self.selection_window.clear_selection() #清空已选课程列表
        #for course in self.daemon_map:     #终止抢课进程
        #    self.daemon_map[course].quit()
        pass

    def on_remove_course(self, course: SelectionClass):
        self.daemon_map[course.name].quit()

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
