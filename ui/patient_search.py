# -*- coding: utf-8 -*-
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QMessageBox
)
from PySide6.QtCore import Qt
from firebase_client import firebase_session
from data_access import list_patients_by_cpf, list_sessions

class PatientSearchScreen(QWidget):
    def __init__(self, open_static_cb, open_motion_cb, logout_cb=None):
        """
        open_static_cb(uid, cpf, session_key)
        open_motion_cb(uid, cpf, session_key)
        logout_cb() -> opcional
        """
        super().__init__()
        self.open_static_cb = open_static_cb
        self.open_motion_cb = open_motion_cb
        self.logout_cb = logout_cb

        v = QVBoxLayout(self); v.setAlignment(Qt.AlignTop)

        # Título + Sair
        top = QHBoxLayout()
        top.addWidget(QLabel("<h3>Pesquisa de Paciente por CPF</h3>"))
        top.addStretch(1)
        if callable(self.logout_cb):
            btn_logout = QPushButton("Sair")
            btn_logout.clicked.connect(self.logout_cb)
            top.addWidget(btn_logout)
        v.addLayout(top)

        # Busca
        hl = QHBoxLayout()
        self.edit = QLineEdit(); self.edit.setPlaceholderText("Digite o CPF")
        self.btn = QPushButton("Pesquisar")
        hl.addWidget(self.edit); hl.addWidget(self.btn)
        v.addLayout(hl)

        # Resultados
        self.results = QListWidget()
        v.addWidget(QLabel("Resultados:")); v.addWidget(self.results)

        v.addWidget(QLabel("Sessões Estáticas:"))
        self.list_est = QListWidget(); v.addWidget(self.list_est)

        v.addWidget(QLabel("Sessões de Movimento:"))
        self.list_mov = QListWidget(); v.addWidget(self.list_mov)

        hb = QHBoxLayout()
        self.btn_open_est = QPushButton("Abrir Estático")
        self.btn_open_mov = QPushButton("Abrir Movimento")
        hb.addWidget(self.btn_open_est); hb.addWidget(self.btn_open_mov)
        v.addLayout(hb)

        # sinais
        self.btn.clicked.connect(self.do_search)
        self.results.currentTextChanged.connect(self.load_sessions)
        self.btn_open_est.clicked.connect(self.open_static)
        self.btn_open_mov.clicked.connect(self.open_motion)

    # Lógica
    def do_search(self):
        cpf = self.edit.text().strip()
        if not cpf:
            QMessageBox.warning(self, "Atenção", "Informe um CPF.")
            return
        self.results.clear(); self.list_est.clear(); self.list_mov.clear()
        for cpf_key, profile in list_patients_by_cpf(cpf):
            nome = profile.get("name", "(sem nome)")
            self.results.addItem(f"{cpf_key} — {nome}")

    def selected_cpf(self):
        it = self.results.currentItem()
        if not it: return None
        return it.text().split("—", 1)[0].strip()

    def load_sessions(self, _):
        self.list_est.clear(); self.list_mov.clear()
        cpf = self.selected_cpf()
        if not cpf: return
        uid = firebase_session.user_uid or ""
        for s in list_sessions(uid, cpf, "estatico"):
            self.list_est.addItem(s)
        for s in list_sessions(uid, cpf, "movimento"):
            self.list_mov.addItem(s)

    def open_static(self):
        cpf = self.selected_cpf(); it = self.list_est.currentItem()
        if not (cpf and it):
            QMessageBox.warning(self, "Atenção", "Selecione paciente e sessão estática.")
            return
        self.open_static_cb(firebase_session.user_uid, cpf, it.text())

    def open_motion(self):
        cpf = self.selected_cpf(); it = self.list_mov.currentItem()
        if not (cpf and it):
            QMessageBox.warning(self, "Atenção", "Selecione paciente e sessão de movimento.")
            return
        self.open_motion_cb(firebase_session.user_uid, cpf, it.text())
