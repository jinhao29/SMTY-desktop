# -*- coding: utf-8 -*-
"""路由聚合。"""
from routers import auth, students, coaches, lessons, checkins, packages, backup, ocr

all_routers = [auth.router, students.router, coaches.router, lessons.router,
               checkins.router, packages.router, backup.router, ocr.router]
