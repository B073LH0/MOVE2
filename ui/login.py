# -*- coding: utf-8 -*-
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PySide6.QtCore import Qt
from firebase_client import firebase_login_email_password, init_firebase_admin

class LoginScreen(QWidget):
    def __init__(self, on_success):
        super().__init__(); self.on_success = on_success
        v=QVBoxLayout(self); v.setAlignment(Qt.AlignCenter)
        v.addWidget(QLabel("<h2>Sintec MOVE Baropodometria</h2>"))
        self.email=QLineEdit(); self.email.setPlaceholderText("E-mail")
        self.pw=QLineEdit(); self.pw.setPlaceholderText("Senha"); self.pw.setEchoMode(QLineEdit.Password)
        self.btn=QPushButton("Entrar")
        v.addWidget(self.email); v.addWidget(self.pw); v.addWidget(self.btn)
        self.btn.clicked.connect(self.do_login); init_firebase_admin()

    def do_login(self):
        try:
            firebase_login_email_password(self.email.text().strip(), self.pw.text().strip())
            self.on_success()
        except Exception as e:
            QMessageBox.critical(self,"Erro de Login",f"{e}")
