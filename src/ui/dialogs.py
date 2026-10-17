import os
import tempfile
import threading
import webbrowser
from typing import Dict, List, Optional, Tuple
import wx
from src.core.models import Post, User
from src.audio.manager import sound_manager
from src.audio.speech import speech_manager
from src.core.config import config_manager, DEFAULT_SHORTCUTS, DEFAULT_GLOBAL_SHORTCUTS


class SelectLinkDialog(wx.Dialog):
    """
    Diálogo acessível com caixa de combinação para o usuário escolher
    qual link deseja abrir no navegador quando uma publicação possui múltiplos links.
    """
    def __init__(self, parent: wx.Window, links: List[str], post_author: str = ""):
        title = f"Escolher link - {post_author}" if post_author else "Escolher link para abrir"
        super().__init__(
            parent,
            title=title,
            size=(560, 220),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self.links = links
        self.selected_link: Optional[str] = links[0] if links else None
        self._init_ui()
        self.CenterOnParent()

    def _init_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Rótulo acessível com acelerador de teclado (&S)
        label = wx.StaticText(panel, label="&Selecione o link que deseja abrir no navegador:")
        sizer.Add(label, 0, wx.ALL, 10)

        # Caixa de combinação nativa Win32 (SysComboBox32)
        # O modo ReadOnly permite navegação direta e fluida por setas no NVDA e JAWS
        self.combo = wx.ComboBox(
            panel,
            choices=self.links,
            style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        if self.links:
            self.combo.SetSelection(0)
        sizer.Add(self.combo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Linha de botões acessíveis
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        open_btn = wx.Button(panel, wx.ID_OK, label="&Abrir Link")
        open_btn.SetDefault()
        btn_sizer.Add(open_btn, 0, wx.RIGHT, 10)

        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="&Cancelar")
        btn_sizer.Add(cancel_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(sizer)

        self.Bind(wx.EVT_BUTTON, self._on_confirm, id=wx.ID_OK)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        # Foco inicial na caixa de combinação para o leitor de tela anunciar imediatamente
        wx.CallAfter(self.combo.SetFocus)

    def _on_confirm(self, event):
        idx = self.combo.GetSelection()
        if idx != wx.NOT_FOUND and 0 <= idx < len(self.links):
            self.selected_link = self.links[idx]
        elif self.combo.GetValue():
            self.selected_link = self.combo.GetValue()
        self.EndModal(wx.ID_OK)

    def _on_char_hook(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        elif key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_confirm(event)
        else:
            event.Skip()

    def get_selected_link(self) -> Optional[str]:
        return self.selected_link


class PostDetailsDialog(wx.Dialog):
    """
    Exibe o conteúdo completo da publicação em uma caixa de texto acessível.
    Permite leitura linha a linha, caractere por caractere e cópia de conteúdo.
    """
    def __init__(self, parent: wx.Window, post: Post):
        super().__init__(
            parent,
            title=f"Detalhes da publicação de {post.author_name}",
            size=(600, 450),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self.post = post
        self._init_ui()
        self.CenterOnParent()

    def _init_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Rótulo acessível para o leitor de tela
        label = wx.StaticText(panel, label="Conteúdo completo da publicação:")
        sizer.Add(label, 0, wx.ALL, 10)

        # Caixa de texto acessível somente-leitura com scroll
        self.text_ctrl = wx.TextCtrl(
            panel,
            value=self.post.to_accessible_full(),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2
        )
        sizer.Add(self.text_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Linha de botões acessíveis
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        copy_btn = wx.Button(panel, label="&Copiar Texto")
        copy_btn.Bind(wx.EVT_BUTTON, self._on_copy)
        btn_sizer.Add(copy_btn, 0, wx.RIGHT, 10)

        links = self.post.get_all_links()
        if links:
            open_link_btn = wx.Button(panel, label="&Abrir Link no Navegador")
            open_link_btn.Bind(wx.EVT_BUTTON, self._on_open_link)
            btn_sizer.Add(open_link_btn, 0, wx.RIGHT, 10)

        close_btn = wx.Button(panel, wx.ID_CANCEL, label="&Fechar")
        btn_sizer.Add(close_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(sizer)

        # Atalho Escape para fechar
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        
        # Foco inicial no texto para o leitor de tela ler imediatamente
        wx.CallAfter(self.text_ctrl.SetFocus)

    def _on_copy(self, event):
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.post.to_accessible_full()))
            wx.TheClipboard.Close()
            wx.MessageBox("Texto copiado para a área de transferência.", "Copiado", wx.OK | wx.ICON_INFORMATION, self)

    def _on_open_link(self, event):
        links = self.post.get_all_links()
        if not links:
            wx.MessageBox("Nenhum link encontrado nesta publicação.", "Sem links", wx.OK | wx.ICON_INFORMATION, self)
            return

        if len(links) == 1:
            webbrowser.open(links[0])
        else:
            dlg = SelectLinkDialog(self, links, post_author=self.post.author_name)
            if dlg.ShowModal() == wx.ID_OK:
                selected = dlg.get_selected_link()
                if selected:
                    webbrowser.open(selected)
            dlg.Destroy()

    def _on_char_hook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()


class NewPostDialog(wx.Dialog):
    """
    Diálogo acessível para composição e publicação de novo post/tweet.
    Inclui contador de caracteres dinâmico (limite 280) e atalho Ctrl+Enter para envio.
    """
    MAX_CHARS = 280

    def __init__(self, parent: wx.Window):
        super().__init__(
            parent,
            title="Nova Publicação (280 caracteres restantes)",
            size=(580, 320),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self.text_content = ""
        self._init_ui()
        self.CenterOnParent()

    def _init_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.label = wx.StaticText(panel, label="&O que está acontecendo?")
        sizer.Add(self.label, 0, wx.ALL, 10)

        self.text_ctrl = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER
        )
        sizer.Add(self.text_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.post_btn = wx.Button(panel, wx.ID_OK, label="&Publicar")
        self.post_btn.SetDefault()
        btn_sizer.Add(self.post_btn, 0, wx.RIGHT, 10)

        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="&Cancelar")
        btn_sizer.Add(cancel_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(sizer)

        self.text_ctrl.Bind(wx.EVT_TEXT, self._on_text_changed)
        self.Bind(wx.EVT_BUTTON, self._on_submit, id=wx.ID_OK)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        wx.CallAfter(self.text_ctrl.SetFocus)

    def _on_text_changed(self, event):
        length = len(self.text_ctrl.GetValue())
        remaining = self.MAX_CHARS - length
        if remaining >= 0:
            self.SetTitle(f"Nova Publicação ({remaining} caracteres restantes)")
            self.post_btn.Enable(length > 0)
        else:
            self.SetTitle(f"Nova Publicação ({abs(remaining)} caracteres a mais!)")
            self.post_btn.Enable(False)
            sound_manager.play_max_length()

    def _on_submit(self, event):
        text = self.text_ctrl.GetValue().strip()
        if not text:
            wx.MessageBox("Digite o texto da publicação antes de enviar.", "Aviso", wx.OK | wx.ICON_WARNING, self)
            return
        if len(text) > self.MAX_CHARS:
            wx.MessageBox("O texto excede o limite de 280 caracteres.", "Limite excedido", wx.OK | wx.ICON_WARNING, self)
            return
        self.text_content = text
        self.EndModal(wx.ID_OK)

    def _on_char_hook(self, event):
        key = event.GetKeyCode()
        ctrl = event.ControlDown()
        if ctrl and key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_submit(event)
        elif key == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()

    def get_text(self) -> str:
        return self.text_content


class ReplyDialog(wx.Dialog):
    """
    Diálogo acessível para responder a uma publicação no X.
    """
    MAX_CHARS = 280

    def __init__(self, parent: wx.Window, post: Post):
        super().__init__(
            parent,
            title=f"Responder a @{post.author_username} (280 restantes)",
            size=(600, 420),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self.post = post
        self.text_content = ""
        self._init_ui()
        self.CenterOnParent()

    def _init_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Informações do post que está sendo respondido
        orig_label = wx.StaticText(panel, label=f"Em resposta a {self.post.author_name} (@{self.post.author_username}):")
        sizer.Add(orig_label, 0, wx.ALL, 10)

        self.orig_text = wx.TextCtrl(
            panel,
            value=self.post.text,
            size=(-1, 70),
            style=wx.TE_MULTILINE | wx.TE_READONLY
        )
        sizer.Add(self.orig_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Campo da resposta
        reply_label = wx.StaticText(panel, label="&Sua Resposta:")
        sizer.Add(reply_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.text_ctrl = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER
        )
        sizer.Add(self.text_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.reply_btn = wx.Button(panel, wx.ID_OK, label="&Responder")
        self.reply_btn.SetDefault()
        btn_sizer.Add(self.reply_btn, 0, wx.RIGHT, 10)

        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="&Cancelar")
        btn_sizer.Add(cancel_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(sizer)

        self.text_ctrl.Bind(wx.EVT_TEXT, self._on_text_changed)
        self.Bind(wx.EVT_BUTTON, self._on_submit, id=wx.ID_OK)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        wx.CallAfter(self.text_ctrl.SetFocus)

    def _on_text_changed(self, event):
        length = len(self.text_ctrl.GetValue())
        remaining = self.MAX_CHARS - length
        if remaining >= 0:
            self.SetTitle(f"Responder a @{self.post.author_username} ({remaining} restantes)")
            self.reply_btn.Enable(length > 0)
        else:
            self.SetTitle(f"Responder a @{self.post.author_username} ({abs(remaining)} caracteres a mais!)")
            self.reply_btn.Enable(False)
            sound_manager.play_max_length()

    def _on_submit(self, event):
        text = self.text_ctrl.GetValue().strip()
        if not text:
            wx.MessageBox("Digite o texto da sua resposta.", "Aviso", wx.OK | wx.ICON_WARNING, self)
            return
        if len(text) > self.MAX_CHARS:
            wx.MessageBox("A resposta excede o limite de 280 caracteres.", "Limite excedido", wx.OK | wx.ICON_WARNING, self)
            return
        self.text_content = text
        self.EndModal(wx.ID_OK)

    def _on_char_hook(self, event):
        key = event.GetKeyCode()
        ctrl = event.ControlDown()
        if ctrl and key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_submit(event)
        elif key == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()

    def get_text(self) -> str:
        return self.text_content


class QuoteDialog(wx.Dialog):
    """
    Diálogo acessível para citar/repostar uma publicação com comentário.
    """
    MAX_CHARS = 250

    def __init__(self, parent: wx.Window, post: Post):
        super().__init__(
            parent,
            title=f"Citar publicação de @{post.author_username} ({self.MAX_CHARS} restantes)",
            size=(600, 420),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self.post = post
        self.text_content = ""
        self._init_ui()
        self.CenterOnParent()

    def _init_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        orig_label = wx.StaticText(panel, label=f"Citando publicação de {self.post.author_name} (@{self.post.author_username}):")
        sizer.Add(orig_label, 0, wx.ALL, 10)

        self.orig_text = wx.TextCtrl(
            panel,
            value=self.post.text,
            size=(-1, 70),
            style=wx.TE_MULTILINE | wx.TE_READONLY
        )
        sizer.Add(self.orig_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        quote_label = wx.StaticText(panel, label="&Seu comentário da citação:")
        sizer.Add(quote_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.text_ctrl = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER
        )
        sizer.Add(self.text_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.quote_btn = wx.Button(panel, wx.ID_OK, label="&Publicar Citação")
        self.quote_btn.SetDefault()
        btn_sizer.Add(self.quote_btn, 0, wx.RIGHT, 10)

        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="&Cancelar")
        btn_sizer.Add(cancel_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(sizer)

        self.text_ctrl.Bind(wx.EVT_TEXT, self._on_text_changed)
        self.Bind(wx.EVT_BUTTON, self._on_submit, id=wx.ID_OK)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        wx.CallAfter(self.text_ctrl.SetFocus)

    def _on_text_changed(self, event):
        length = len(self.text_ctrl.GetValue())
        remaining = self.MAX_CHARS - length
        if remaining >= 0:
            self.SetTitle(f"Citar publicação de @{self.post.author_username} ({remaining} restantes)")
            self.quote_btn.Enable(length > 0)
        else:
            self.SetTitle(f"Citar publicação de @{self.post.author_username} ({abs(remaining)} caracteres a mais!)")
            self.quote_btn.Enable(False)
            sound_manager.play_max_length()

    def _on_submit(self, event):
        text = self.text_ctrl.GetValue().strip()
        if not text:
            wx.MessageBox("Digite seu comentário para a citação.", "Aviso", wx.OK | wx.ICON_WARNING, self)
            return
        if len(text) > self.MAX_CHARS:
            wx.MessageBox("O comentário excede o limite de caracteres.", "Limite excedido", wx.OK | wx.ICON_WARNING, self)
            return
        self.text_content = text
        self.EndModal(wx.ID_OK)

    def _on_char_hook(self, event):
        key = event.GetKeyCode()
        ctrl = event.ControlDown()
        if ctrl and key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_submit(event)
        elif key == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()

    def get_text(self) -> str:
        return self.text_content


class RetweetChoiceDialog(wx.Dialog):
    """
    Diálogo acessível para o usuário decidir entre Repostar diretamente ou Citar com comentário.
    """
    def __init__(self, parent: wx.Window, post: Post):
        super().__init__(
            parent,
            title=f"Repostar - {post.author_name}",
            size=(480, 190),
            style=wx.DEFAULT_DIALOG_STYLE
        )
        self.post = post
        self._init_ui()
        self.CenterOnParent()

    def _init_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        msg = wx.StaticText(
            panel,
            label=f"Deseja repostar diretamente a publicação de {self.post.author_name} (@{self.post.author_username}) ou adicionar um comentário?"
        )
        sizer.Add(msg, 0, wx.ALL, 15)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.retweet_btn = wx.Button(panel, wx.ID_YES, label="&Repostar Diretamente")
        self.retweet_btn.SetDefault()
        btn_sizer.Add(self.retweet_btn, 0, wx.RIGHT, 10)

        quote_btn = wx.Button(panel, wx.ID_NO, label="&Citar com Comentário...")
        btn_sizer.Add(quote_btn, 0, wx.RIGHT, 10)

        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="&Cancelar")
        btn_sizer.Add(cancel_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)
        panel.SetSizer(sizer)

        self.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_YES), id=wx.ID_YES)
        self.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_NO), id=wx.ID_NO)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        wx.CallAfter(self.retweet_btn.SetFocus)

    def _on_char_hook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()


class SendDMDialog(wx.Dialog):
    """
    Diálogo acessível para envio de mensagem direta (DM) no X.
    """
    def __init__(self, parent: wx.Window, initial_recipient: str = ""):
        super().__init__(
            parent,
            title="Enviar Mensagem Direta (DM)",
            size=(560, 360),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self.initial_recipient = initial_recipient.lstrip("@")
        self.recipient_value = ""
        self.message_value = ""
        self._init_ui()
        self.CenterOnParent()

    def _init_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        user_label = wx.StaticText(panel, label="&Destinatário (nome de usuário sem @):")
        sizer.Add(user_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.recipient_ctrl = wx.TextCtrl(panel, value=self.initial_recipient)
        sizer.Add(self.recipient_ctrl, 0, wx.EXPAND | wx.ALL, 10)

        msg_label = wx.StaticText(panel, label="&Mensagem privada:")
        sizer.Add(msg_label, 0, wx.LEFT | wx.RIGHT, 10)

        self.message_ctrl = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER
        )
        sizer.Add(self.message_ctrl, 1, wx.EXPAND | wx.ALL, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.send_btn = wx.Button(panel, wx.ID_OK, label="&Enviar DM")
        self.send_btn.SetDefault()
        btn_sizer.Add(self.send_btn, 0, wx.RIGHT, 10)

        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="&Cancelar")
        btn_sizer.Add(cancel_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(sizer)

        self.Bind(wx.EVT_BUTTON, self._on_submit, id=wx.ID_OK)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        # Se já tem destinatário, foca na mensagem; senão, no destinatário
        if self.initial_recipient:
            wx.CallAfter(self.message_ctrl.SetFocus)
        else:
            wx.CallAfter(self.recipient_ctrl.SetFocus)

    def _on_submit(self, event):
        recipient = self.recipient_ctrl.GetValue().lstrip("@").strip()
        text = self.message_ctrl.GetValue().strip()

        if not recipient:
            wx.MessageBox("Informe o nome de usuário do destinatário.", "Aviso", wx.OK | wx.ICON_WARNING, self)
            self.recipient_ctrl.SetFocus()
            return

        if not text:
            wx.MessageBox("Digite o texto da mensagem direta.", "Aviso", wx.OK | wx.ICON_WARNING, self)
            self.message_ctrl.SetFocus()
            return

        self.recipient_value = recipient
        self.message_value = text
        self.EndModal(wx.ID_OK)

    def _on_char_hook(self, event):
        key = event.GetKeyCode()
        ctrl = event.ControlDown()
        if ctrl and key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_submit(event)
        elif key == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()

    def get_data(self) -> tuple[str, str]:
        return self.recipient_value, self.message_value


class SettingsDialog(wx.Dialog):
    """
    Diálogo acessível de configurações do Accessible Timeline organizado em abas (estilo TWBlue):
    - Geral (atualizações automáticas, minimizar para a bandeja, atalhos globais)
    - Exibição e Leitura (formato de autor, formato de data, métricas, leitura de status e menções)
    - Áudio (efeitos sonoros, tema)
    - Atalhos de Teclado (visualização e restauração de atalhos)
    """
    def __init__(self, parent: wx.Window):
        super().__init__(
            parent,
            title="Configurações",
            size=(640, 480),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self._init_ui()
        self.CenterOnParent()

    def _init_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.notebook = wx.Notebook(panel)

        # Aba 1: Geral
        general_panel = wx.Panel(self.notebook)
        gen_sizer = wx.BoxSizer(wx.VERTICAL)

        self.chk_auto_updates = wx.CheckBox(
            general_panel,
            label="&Verificar atualizações automaticamente ao iniciar o aplicativo"
        )
        self.chk_auto_updates.SetValue(config_manager.get("check_updates_automatically", True))
        gen_sizer.Add(self.chk_auto_updates, 0, wx.ALL, 10)

        self.chk_hide_tray = wx.CheckBox(
            general_panel,
            label="&Minimizar para a área de notificação (bandeja do sistema) ao fechar"
        )
        self.chk_hide_tray.SetValue(config_manager.get("hide_to_tray_on_close", False))
        gen_sizer.Add(self.chk_hide_tray, 0, wx.ALL, 10)

        self.chk_global_hotkeys = wx.CheckBox(
            general_panel,
            label="Ativar &atalhos globais de segundo plano (Ctrl+Win)"
        )
        self.chk_global_hotkeys.SetValue(config_manager.get("global_hotkeys_enabled", True))
        gen_sizer.Add(self.chk_global_hotkeys, 0, wx.ALL, 10)

        general_panel.SetSizer(gen_sizer)
        self.notebook.AddPage(general_panel, "&Geral")

        # Aba 2: Exibição e Leitura
        display_panel = wx.Panel(self.notebook)
        disp_sizer = wx.BoxSizer(wx.VERTICAL)

        disp_sizer.Add(wx.StaticText(display_panel, label="&Formato de exibição do autor nas postagens:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.author_choices = [
            ("name_and_username", "Nome e Usuário (@arroba) - Ex: Maria Silva (@mariasilva)"),
            ("name_only", "Apenas Nome - Ex: Maria Silva"),
            ("username_only", "Apenas Usuário - Ex: @mariasilva"),
            ("username_and_name", "Usuário e Nome - Ex: @mariasilva (Maria Silva)"),
        ]
        self.combo_author = wx.ComboBox(
            display_panel,
            choices=[label for _, label in self.author_choices],
            style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        curr_author = config_manager.get("author_display_format", "name_and_username")
        sel_idx = next((i for i, (k, _) in enumerate(self.author_choices) if k == curr_author), 0)
        self.combo_author.SetSelection(sel_idx)
        disp_sizer.Add(self.combo_author, 0, wx.EXPAND | wx.ALL, 10)

        disp_sizer.Add(wx.StaticText(display_panel, label="&Formato de data e hora:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.time_choices = [
            ("relative", "Tempo relativo (estilo TWBlue) - Ex: 2 horas atrás"),
            ("absolute", "Data e hora exata - Ex: 17/10 14:30"),
            ("both", "Ambos - Ex: 2 horas atrás (17/10 14:30)"),
        ]
        self.combo_time = wx.ComboBox(
            display_panel,
            choices=[label for _, label in self.time_choices],
            style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        curr_time = config_manager.get("time_display_format", "relative")
        t_idx = next((i for i, (k, _) in enumerate(self.time_choices) if k == curr_time), 0)
        self.combo_time.SetSelection(t_idx)
        disp_sizer.Add(self.combo_time, 0, wx.EXPAND | wx.ALL, 10)

        disp_sizer.Add(wx.StaticText(display_panel, label="&Posição da data e hora:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.time_pos_choices = [
            ("after_text", "Após o texto da publicação (Padrão) - Ex: Autor: Post, 2 horas atrás"),
            ("before_text", "Antes do texto da publicação - Ex: Autor, 2 horas atrás: Post"),
        ]
        self.combo_time_pos = wx.ComboBox(
            display_panel,
            choices=[label for _, label in self.time_pos_choices],
            style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        curr_time_pos = config_manager.get("time_position", "after_text")
        tp_idx = next((i for i, (k, _) in enumerate(self.time_pos_choices) if k == curr_time_pos), 0)
        self.combo_time_pos.SetSelection(tp_idx)
        disp_sizer.Add(self.combo_time_pos, 0, wx.EXPAND | wx.ALL, 10)

        self.chk_metrics = wx.CheckBox(
            display_panel,
            label="Anunciar &curtidas, reposts e respostas no resumo ao navegar com setas"
        )
        self.chk_metrics.SetValue(config_manager.get("show_metrics_in_summary", True))
        disp_sizer.Add(self.chk_metrics, 0, wx.ALL, 10)

        self.chk_speak_status = wx.CheckBox(
            display_panel,
            label="&Falar alertas e mensagens da barra de status pelo leitor de tela"
        )
        self.chk_speak_status.SetValue(config_manager.get("speak_status_alerts", True))
        disp_sizer.Add(self.chk_speak_status, 0, wx.ALL, 10)

        self.chk_speak_mentions = wx.CheckBox(
            display_panel,
            label="Falar novas &menções recebidas automaticamente"
        )
        self.chk_speak_mentions.SetValue(config_manager.get("speak_new_mentions", True))
        disp_sizer.Add(self.chk_speak_mentions, 0, wx.ALL, 10)

        display_panel.SetSizer(disp_sizer)
        self.notebook.AddPage(display_panel, "&Exibição e Leitura")

        # Aba 3: Áudio
        audio_panel = wx.Panel(self.notebook)
        audio_sizer = wx.BoxSizer(wx.VERTICAL)

        self.chk_sound_enabled = wx.CheckBox(
            audio_panel,
            label="Ativar &efeitos sonoros"
        )
        self.chk_sound_enabled.SetValue(config_manager.get("sound_enabled", True))
        audio_sizer.Add(self.chk_sound_enabled, 0, wx.ALL, 10)

        audio_sizer.Add(wx.StaticText(audio_panel, label="&Pacote de sons do TWBlue:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.sound_themes = ["default", "classic", "Qwitter", "Magical Fountain", "FreakyBlue", "FightingGames"]
        self.combo_sound_theme = wx.ComboBox(
            audio_panel,
            choices=self.sound_themes,
            style=wx.CB_DROPDOWN | wx.CB_READONLY
        )
        curr_th = config_manager.get("sound_theme", "default")
        th_idx = self.sound_themes.index(curr_th) if curr_th in self.sound_themes else 0
        self.combo_sound_theme.SetSelection(th_idx)
        audio_sizer.Add(self.combo_sound_theme, 0, wx.EXPAND | wx.ALL, 10)

        audio_panel.SetSizer(audio_sizer)
        self.notebook.AddPage(audio_panel, "Á&udio")

        # Aba 4: Atalhos de Teclado
        shortcuts_panel = wx.Panel(self.notebook)
        sc_sizer = wx.BoxSizer(wx.VERTICAL)

        sc_sizer.Add(wx.StaticText(shortcuts_panel, label="Atalhos configurados no aplicativo (padrão TWBlue):"), 0, wx.ALL, 10)

        self.sc_list = wx.ListCtrl(
            shortcuts_panel,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL
        )
        self.sc_list.InsertColumn(0, "Ação", width=260)
        self.sc_list.InsertColumn(1, "Atalho", width=220)

        self._shortcuts_data = [
            ("Nova Publicação", "new_post", "Ctrl+N"),
            ("Responder", "reply", "Ctrl+R"),
            ("Repostar / Retweet", "retweet", "Ctrl+Shift+R"),
            ("Citar Publicação", "quote", "Ctrl+Shift+C"),
            ("Curtir / Descurtir", "like", "Ctrl+L"),
            ("Enviar Mensagem Direta", "send_dm", "Ctrl+D"),
            ("Linha do Tempo de Usuário", "user_timeline", "Ctrl+U"),
            ("Buscar Usuários", "search_users", "Ctrl+Shift+U"),
            ("Seguir Autor", "follow", "Ctrl+Shift+F"),
            ("Deixar de Seguir Autor", "unfollow", "Ctrl+Alt+F"),
            ("Bloquear Autor", "block", "Ctrl+Shift+B"),
            ("Atualizar Fluxo Ativo", "refresh", "F5"),
            ("Carregar Mais Postagens", "load_more", "Ctrl+M"),
            ("Ver Detalhes do Post", "details", "Enter"),
            ("Abrir Link no Navegador", "open_link", "Ctrl+Enter"),
            ("Alternar Janela do Navegador", "toggle_browser", "Ctrl+Shift+M"),
            ("Abrir Configurações", "settings", "Ctrl+P"),
            ("[Global] Ocultar/Restaurar Janela", "toggle_visibility", "Ctrl+Win+H"),
            ("[Global] Próximo Post", "next_post", "Ctrl+Win+Down"),
            ("[Global] Post Anterior", "prev_post", "Ctrl+Win+Up"),
            ("[Global] Próximo Fluxo", "next_stream", "Ctrl+Win+Right"),
            ("[Global] Fluxo Anterior", "prev_stream", "Ctrl+Win+Left"),
            ("[Global] Nova Publicação", "new_post_global", "Ctrl+Win+N"),
            ("[Global] Curtir Post", "like_global", "Ctrl+Win+L"),
            ("[Global] Copiar Texto do Post", "copy_text", "Ctrl+Win+C"),
        ]

        active_sc = config_manager.get("shortcuts", DEFAULT_SHORTCUTS)
        active_glob = config_manager.get("global_shortcuts", DEFAULT_GLOBAL_SHORTCUTS)

        for idx, (label, key, default_val) in enumerate(self._shortcuts_data):
            if key in active_sc:
                val = active_sc[key]
            elif key.replace("_global", "") in active_glob:
                val = active_glob[key.replace("_global", "")]
            else:
                val = default_val
            row = self.sc_list.InsertItem(idx, label)
            self.sc_list.SetItem(row, 1, str(val))

        sc_sizer.Add(self.sc_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.btn_reset_shortcuts = wx.Button(shortcuts_panel, label="&Restaurar Atalhos Padrão")
        self.btn_reset_shortcuts.Bind(wx.EVT_BUTTON, self._on_reset_shortcuts)
        sc_sizer.Add(self.btn_reset_shortcuts, 0, wx.ALL, 10)

        shortcuts_panel.SetSizer(sc_sizer)
        self.notebook.AddPage(shortcuts_panel, "&Atalhos")

        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 8)

        # Botões Salvar e Cancelar
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.save_btn = wx.Button(panel, wx.ID_OK, label="&Salvar")
        self.save_btn.SetDefault()
        btn_sizer.Add(self.save_btn, 0, wx.RIGHT, 10)

        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="&Cancelar")
        btn_sizer.Add(cancel_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(main_sizer)

        self.Bind(wx.EVT_BUTTON, self._on_save, id=wx.ID_OK)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    def _on_reset_shortcuts(self, event):
        config_manager.set("shortcuts", dict(DEFAULT_SHORTCUTS))
        config_manager.set("global_shortcuts", dict(DEFAULT_GLOBAL_SHORTCUTS))
        for idx, (label, key, default_val) in enumerate(self._shortcuts_data):
            self.sc_list.SetItem(idx, 1, default_val)
        wx.MessageBox("Atalhos restaurados para os padrões com sucesso!", "Informação", wx.OK | wx.ICON_INFORMATION, self)

    def _on_save(self, event):
        config_manager.set("check_updates_automatically", self.chk_auto_updates.GetValue(), auto_save=False)
        config_manager.set("hide_to_tray_on_close", self.chk_hide_tray.GetValue(), auto_save=False)
        config_manager.set("global_hotkeys_enabled", self.chk_global_hotkeys.GetValue(), auto_save=False)

        author_k = self.author_choices[self.combo_author.GetSelection()][0]
        config_manager.set("author_display_format", author_k, auto_save=False)

        time_k = self.time_choices[self.combo_time.GetSelection()][0]
        config_manager.set("time_display_format", time_k, auto_save=False)

        time_pos_k = self.time_pos_choices[self.combo_time_pos.GetSelection()][0]
        config_manager.set("time_position", time_pos_k, auto_save=False)

        config_manager.set("show_metrics_in_summary", self.chk_metrics.GetValue(), auto_save=False)
        config_manager.set("speak_status_alerts", self.chk_speak_status.GetValue(), auto_save=False)
        config_manager.set("speak_new_mentions", self.chk_speak_mentions.GetValue(), auto_save=False)

        sound_en = self.chk_sound_enabled.GetValue()
        config_manager.set("sound_enabled", sound_en, auto_save=False)
        sound_manager.enabled = sound_en

        theme_name = self.sound_themes[self.combo_sound_theme.GetSelection()]
        config_manager.set("sound_theme", theme_name, auto_save=False)
        sound_manager.set_theme(theme_name)

        config_manager.save()
        self.EndModal(wx.ID_OK)

    def _on_char_hook(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()


class UserTimelineDialog(wx.Dialog):
    """
    Diálogo acessível para visualização da linha do tempo de um usuário específico (estilo TWBlue).
    Permite ler as postagens com as setas, abrir detalhes, links, responder, repostar e curtir.
    """
    def __init__(self, parent: wx.Window, username: str, executor):
        clean_user = username.lstrip("@").strip()
        super().__init__(
            parent,
            title=f"Linha do Tempo de @{clean_user}",
            size=(850, 560),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self.username = clean_user
        self.executor = executor
        self.posts: List[Post] = []
        self._init_ui()
        self.CenterOnParent()
        wx.CallAfter(self._load_timeline)

    def _init_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.status_label = wx.StaticText(panel, label=f"Carregando publicações de @{self.username}...")
        sizer.Add(self.status_label, 0, wx.ALL, 10)

        self.list_ctrl = wx.ListCtrl(
            panel,
            style=wx.LC_REPORT | wx.LC_NO_HEADER | wx.LC_SINGLE_SEL
        )
        self.list_ctrl.InsertColumn(0, "Publicações", width=1200)
        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Botões de Ação
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_details = wx.Button(panel, label="Ver &Detalhes (Enter)")
        btn_sizer.Add(self.btn_details, 0, wx.RIGHT, 6)

        self.btn_open_link = wx.Button(panel, label="Abrir &Link (Ctrl+Enter)")
        btn_sizer.Add(self.btn_open_link, 0, wx.RIGHT, 6)

        self.btn_reply = wx.Button(panel, label="&Responder (Ctrl+R)")
        btn_sizer.Add(self.btn_reply, 0, wx.RIGHT, 6)

        self.btn_retweet = wx.Button(panel, label="Re&postar (Ctrl+Shift+R)")
        btn_sizer.Add(self.btn_retweet, 0, wx.RIGHT, 6)

        self.btn_like = wx.Button(panel, label="&Curtir (Ctrl+L)")
        btn_sizer.Add(self.btn_like, 0, wx.RIGHT, 6)

        self.btn_refresh = wx.Button(panel, label="&Atualizar (F5)")
        btn_sizer.Add(self.btn_refresh, 0, wx.RIGHT, 6)

        btn_close = wx.Button(panel, wx.ID_CANCEL, label="&Fechar (Esc)")
        btn_sizer.Add(btn_close, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(sizer)

        # Eventos
        self.btn_details.Bind(wx.EVT_BUTTON, self._on_details)
        self.btn_open_link.Bind(wx.EVT_BUTTON, self._on_open_link)
        self.btn_reply.Bind(wx.EVT_BUTTON, self._on_reply)
        self.btn_retweet.Bind(wx.EVT_BUTTON, self._on_retweet)
        self.btn_like.Bind(wx.EVT_BUTTON, self._on_like)
        self.btn_refresh.Bind(wx.EVT_BUTTON, lambda e: self._load_timeline())
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_details)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    def _load_timeline(self):
        self.status_label.SetLabel(f"Buscando publicações de @{self.username} no X...")
        self.list_ctrl.DeleteAllItems()

        def _worker():
            try:
                posts = self.executor.fetch_user_timeline(self.username)
                wx.CallAfter(self._on_timeline_loaded, posts)
            except Exception as e:
                wx.CallAfter(self._on_timeline_error, str(e))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _on_timeline_loaded(self, posts: List[Post]):
        self.posts = posts
        self.list_ctrl.DeleteAllItems()
        for idx, post in enumerate(posts):
            summary = post.to_accessible_summary()
            self.list_ctrl.InsertItem(idx, summary)

        count = len(posts)
        msg = f"{count} publicações carregadas de @{self.username}." if count > 0 else f"Nenhuma publicação encontrada para @{self.username}."
        self.status_label.SetLabel(msg)
        if count > 0:
            self.list_ctrl.Select(0)
            self.list_ctrl.Focus(0)
            self.list_ctrl.SetFocus()

    def _on_timeline_error(self, err_msg: str):
        self.status_label.SetLabel(f"Falha ao carregar publicações: {err_msg}")

    def _get_selected_post(self) -> Optional[Post]:
        idx = self.list_ctrl.GetFirstSelected()
        if 0 <= idx < len(self.posts):
            return self.posts[idx]
        return None

    def _on_details(self, event):
        post = self._get_selected_post()
        if post:
            dlg = PostDetailsDialog(self, post)
            dlg.ShowModal()
            dlg.Destroy()
            self.list_ctrl.SetFocus()

    def _on_open_link(self, event):
        post = self._get_selected_post()
        if post:
            links = post.get_all_links()
            if not links:
                wx.MessageBox("Esta publicação não possui links ou anexos.", "Aviso", wx.OK | wx.ICON_INFORMATION, self)
                return
            if len(links) == 1:
                webbrowser.open(links[0])
            else:
                dlg = SelectLinkDialog(self, links, post.author_name)
                if dlg.ShowModal() == wx.ID_OK:
                    webbrowser.open(dlg.get_selected_link())
                dlg.Destroy()
            self.list_ctrl.SetFocus()

    def _on_reply(self, event):
        post = self._get_selected_post()
        if post:
            dlg = ReplyDialog(self, post)
            if dlg.ShowModal() == wx.ID_OK:
                reply_text = dlg.get_text()
                if reply_text:
                    self.executor.run_async(
                        action_fn=lambda: self.executor.reply_to_post(post.id, reply_text, post.author_username),
                        on_success=lambda: sound_manager.play_send(),
                        on_error=lambda: sound_manager.play_send_error()
                    )
            dlg.Destroy()
            self.list_ctrl.SetFocus()

    def _on_retweet(self, event):
        post = self._get_selected_post()
        if post:
            dlg = RetweetChoiceDialog(self, post)
            res = dlg.ShowModal()
            action = dlg.action_choice
            dlg.Destroy()
            if res == wx.ID_OK:
                if action == "retweet":
                    self.executor.run_async(
                        action_fn=lambda: self.executor.retweet_post(post.id),
                        on_success=lambda: sound_manager.play_retweet(),
                        on_error=lambda: sound_manager.play_send_error()
                    )
                elif action == "quote":
                    q_dlg = QuoteDialog(self, post)
                    if q_dlg.ShowModal() == wx.ID_OK:
                        quote_text = q_dlg.get_text()
                        if quote_text:
                            self.executor.run_async(
                                action_fn=lambda: self.executor.quote_post(post.id, quote_text, post.url),
                                on_success=lambda: sound_manager.play_retweet(),
                                on_error=lambda: sound_manager.play_send_error()
                            )
                    q_dlg.Destroy()
            self.list_ctrl.SetFocus()

    def _on_like(self, event):
        post = self._get_selected_post()
        if post:
            self.executor.run_async(
                action_fn=lambda: self.executor.like_post(post.id),
                on_success=lambda: sound_manager.play_like(),
                on_error=lambda: sound_manager.play_send_error()
            )
            self.list_ctrl.SetFocus()

    def _on_char_hook(self, event):
        key = event.GetKeyCode()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()

        if ctrl and not shift and key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_open_link(None)
            return
        elif not ctrl and not shift and key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_details(None)
            return
        elif ctrl and not shift and key in (ord('R'), ord('r')):
            self._on_reply(None)
            return
        elif ctrl and shift and key in (ord('R'), ord('r')):
            self._on_retweet(None)
            return
        elif ctrl and not shift and key in (ord('L'), ord('l')):
            self._on_like(None)
            return
        elif not ctrl and not shift and key == wx.WXK_F5:
            self._load_timeline()
            return
        elif key == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()


class SearchUsersDialog(wx.Dialog):
    """
    Diálogo acessível de busca de usuários no X (estilo TWBlue).
    Permite pesquisar perfis, ver resultados em lista, seguir/deixar de seguir,
    abrir linha do tempo, enviar DM e bloquear.
    """
    def __init__(self, parent: wx.Window, executor, initial_query: str = ""):
        super().__init__(
            parent,
            title="Buscar Usuários",
            size=(720, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self.executor = executor
        self.initial_query = initial_query
        self.users: List[User] = []
        self._init_ui()
        self.CenterOnParent()

    def _init_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        search_box = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(panel, label="&Buscar usuário:")
        search_box.Add(search_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        self.query_ctrl = wx.TextCtrl(panel, value=self.initial_query, style=wx.TE_PROCESS_ENTER)
        search_box.Add(self.query_ctrl, 1, wx.EXPAND | wx.RIGHT, 6)

        self.search_btn = wx.Button(panel, label="&Pesquisar")
        self.search_btn.SetDefault()
        search_box.Add(self.search_btn, 0)

        sizer.Add(search_box, 0, wx.EXPAND | wx.ALL, 10)

        self.status_label = wx.StaticText(panel, label="Digite o nome ou @usuário e pressione Enter.")
        sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.results_list = wx.ListCtrl(
            panel,
            style=wx.LC_REPORT | wx.LC_NO_HEADER | wx.LC_SINGLE_SEL
        )
        self.results_list.InsertColumn(0, "Usuários Encontrados", width=1200)
        sizer.Add(self.results_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Botões de Ação
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_timeline = wx.Button(panel, label="Ver &Linha do Tempo")
        btn_sizer.Add(self.btn_timeline, 0, wx.RIGHT, 6)

        self.btn_follow = wx.Button(panel, label="&Seguir / Deixar de Seguir")
        btn_sizer.Add(self.btn_follow, 0, wx.RIGHT, 6)

        self.btn_dm = wx.Button(panel, label="Enviar &DM")
        btn_sizer.Add(self.btn_dm, 0, wx.RIGHT, 6)

        self.btn_block = wx.Button(panel, label="&Bloquear")
        btn_sizer.Add(self.btn_block, 0, wx.RIGHT, 6)

        close_btn = wx.Button(panel, wx.ID_CANCEL, label="&Fechar")
        btn_sizer.Add(close_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(sizer)

        # Eventos
        self.search_btn.Bind(wx.EVT_BUTTON, self._on_search)
        self.query_ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.btn_timeline.Bind(wx.EVT_BUTTON, self._on_view_timeline)
        self.btn_follow.Bind(wx.EVT_BUTTON, self._on_toggle_follow)
        self.btn_dm.Bind(wx.EVT_BUTTON, self._on_send_dm)
        self.btn_block.Bind(wx.EVT_BUTTON, self._on_block)
        self.results_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda e: self._on_view_timeline(None))
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        wx.CallAfter(self.query_ctrl.SetFocus)
        if self.initial_query:
            wx.CallAfter(self._on_search, None)

    def _on_search(self, event):
        query = self.query_ctrl.GetValue().strip()
        if not query:
            return
        self.status_label.SetLabel(f"Pesquisando usuários por '{query}' no X...")
        self.results_list.DeleteAllItems()

        def _worker():
            try:
                users = self.executor.search_users(query)
                wx.CallAfter(self._on_search_results, users)
            except Exception as e:
                wx.CallAfter(self._on_search_error, str(e))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _on_search_results(self, users: List[User]):
        self.users = users
        self.results_list.DeleteAllItems()
        for idx, u in enumerate(users):
            summary = u.to_accessible_summary()
            self.results_list.InsertItem(idx, summary)

        count = len(users)
        msg = f"{count} perfis encontrados." if count > 0 else "Nenhum usuário encontrado."
        self.status_label.SetLabel(msg)
        if count > 0:
            self.results_list.Select(0)
            self.results_list.Focus(0)
            self.results_list.SetFocus()

    def _on_search_error(self, err_msg: str):
        self.status_label.SetLabel(f"Falha na busca: {err_msg}")

    def _get_selected_user(self) -> Optional[User]:
        idx = self.results_list.GetFirstSelected()
        if 0 <= idx < len(self.users):
            return self.users[idx]
        return None

    def _on_view_timeline(self, event):
        u = self._get_selected_user()
        if u:
            parent = self.GetParent()
            if hasattr(parent, "open_user_timeline_buffer"):
                self.EndModal(wx.ID_OK)
                wx.CallAfter(parent.open_user_timeline_buffer, u.username)
            else:
                dlg = UserTimelineDialog(self, self.executor, u.username)
                try:
                    dlg.ShowModal()
                finally:
                    dlg.Destroy()
                self.results_list.SetFocus()

    def _on_toggle_follow(self, event):
        u = self._get_selected_user()
        if u:
            if u.is_following:
                action_fn = lambda: self.executor.unfollow_user(u.username)
            else:
                action_fn = lambda: self.executor.follow_user(u.username)

            def _success():
                u.is_following = not u.is_following
                idx = self.results_list.GetFirstSelected()
                if idx >= 0:
                    self.results_list.SetItem(idx, 0, u.to_accessible_summary())
                sound_manager.play_send()
                status_txt = f"Agora você está seguindo @{u.username}" if u.is_following else f"Você deixou de seguir @{u.username}"
                speech_manager.speak(status_txt)

            self.executor.run_async(action_fn, on_success=_success, on_error=lambda: sound_manager.play_send_error())

    def _on_send_dm(self, event):
        u = self._get_selected_user()
        if u:
            dlg = SendDMDialog(self, u.username)
            if dlg.ShowModal() == wx.ID_OK:
                rec, text = dlg.get_data()
                self.executor.run_async(
                    action_fn=lambda: self.executor.send_dm(rec, text),
                    on_success=lambda: sound_manager.play_send(),
                    on_error=lambda: sound_manager.play_send_error()
                )
            dlg.Destroy()
            self.results_list.SetFocus()

    def _on_block(self, event):
        u = self._get_selected_user()
        if u:
            confirm = wx.MessageBox(
                f"Tem certeza que deseja bloquear @{u.username} no X?",
                "Confirmar Bloqueio",
                wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT,
                self
            )
            if confirm == wx.YES:
                def _success():
                    u.is_blocked = True
                    idx = self.results_list.GetFirstSelected()
                    if idx >= 0:
                        self.results_list.SetItem(idx, 0, u.to_accessible_summary())
                    speech_manager.speak(f"@{u.username} foi bloqueado.")

                self.executor.run_async(
                    action_fn=lambda: self.executor.block_user(u.username),
                    on_success=_success,
                    on_error=lambda: sound_manager.play_send_error()
                )
            self.results_list.SetFocus()

    def _on_char_hook(self, event):
        key = event.GetKeyCode()
        ctrl = event.ControlDown()
        if ctrl and key in (ord('U'), ord('u')):
            self._on_view_timeline(None)
            return
        elif ctrl and key in (ord('D'), ord('d')):
            self._on_send_dm(None)
            return
        elif key == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()


class UpdateDownloadDialog(wx.Dialog):
    """
    Diálogo acessível de download e instalação da atualização do Accessible Timeline.
    Exibe barra de progresso, porcentagem e quantidade de megabytes baixados,
    permitindo cancelamento a qualquer momento com Escape ou botão Cancelar.
    """
    def __init__(self, parent: wx.Window, download_url: str, new_version: str):
        super().__init__(
            parent,
            title=f"Baixando Atualização v{new_version}",
            size=(520, 220),
            style=wx.DEFAULT_DIALOG_STYLE
        )
        self.download_url = download_url
        self.new_version = new_version
        self._cancelled = False
        self._download_success = False
        self._target_zip: Optional[str] = None
        self._last_announced_pct = -1

        self._init_ui()
        self.CenterOnParent()
        wx.CallAfter(self._start_download)

    def _init_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.status_label = wx.StaticText(
            panel,
            label=f"Baixando pacote da versão {self.new_version}. Por favor, aguarde..."
        )
        sizer.Add(self.status_label, 0, wx.ALL, 12)

        self.gauge = wx.Gauge(panel, range=100, size=(480, 25))
        sizer.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        self.progress_label = wx.StaticText(
            panel,
            label="Conectando aos servidores do GitHub..."
        )
        sizer.Add(self.progress_label, 0, wx.ALL, 12)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="&Cancelar")
        btn_sizer.Add(self.cancel_btn, 0)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 12)

        panel.SetSizer(sizer)

        self.Bind(wx.EVT_BUTTON, self._on_cancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    def _start_download(self):
        from src.core.updater import download_update_archive

        self._target_zip = os.path.join(tempfile.gettempdir(), f"AccessibleTimeline_v{self.new_version}.zip")

        def _on_progress(downloaded: int, total: int):
            if self._cancelled:
                return False
            pct = int((downloaded / total) * 100) if total > 0 else 0
            mb_down = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024) if total > 0 else 0

            def _update_ui():
                if self._cancelled or not self:
                    return
                self.gauge.SetValue(min(pct, 100))
                self.progress_label.SetLabel(f"{pct}% ({mb_down:.1f} MB de {mb_total:.1f} MB)")
                # Atualiza título periodicamente para leitura discreta de leitores de tela
                if pct // 20 != self._last_announced_pct // 20:
                    self._last_announced_pct = pct
                    self.SetTitle(f"Baixando Atualização v{self.new_version} ({pct}%)")

            wx.CallAfter(_update_ui)
            return True

        def _worker():
            success = download_update_archive(self.download_url, self._target_zip, progress_callback=_on_progress)
            self._download_success = success

            def _finish():
                if self._cancelled:
                    self.EndModal(wx.ID_CANCEL)
                    return
                if success:
                    self.EndModal(wx.ID_OK)
                else:
                    wx.MessageBox(
                        "Falha ao realizar o download da atualização.\nVerifique sua conexão de rede ou tente novamente.",
                        "Erro no Download",
                        wx.OK | wx.ICON_ERROR,
                        self
                    )
                    self.EndModal(wx.ID_CANCEL)

            wx.CallAfter(_finish)

        threading.Thread(target=_worker, daemon=True, name="UpdateDownloadThread").start()

    def _on_cancel(self, event):
        self._cancelled = True
        self.status_label.SetLabel("Cancelando download...")
        self.cancel_btn.Enable(False)

    def _on_char_hook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self._on_cancel(event)
        else:
            event.Skip()

    def get_zip_path(self) -> Optional[str]:
        return self._target_zip if self._download_success else None



