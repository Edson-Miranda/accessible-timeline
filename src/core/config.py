"""
Gerenciador central de configurações persistentes do Accessible Timeline.
Armazena preferências do usuário (como verificação automática de atualizações
e efeitos sonoros) em arquivo JSON no diretório de dados da aplicação.
"""

import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger("AccessibleTimeline.Config")

DEFAULT_SHORTCUTS: Dict[str, str] = {
    "new_post": "Ctrl+N",
    "reply": "Ctrl+R",
    "retweet": "Ctrl+Shift+R",
    "quote": "Ctrl+Shift+C",
    "like": "Ctrl+L",
    "send_dm": "Ctrl+D",
    "user_timeline": "Ctrl+U",
    "close_buffer": "Ctrl+W",
    "author_timeline": "Ctrl+Alt+U",
    "search_users": "Ctrl+Shift+U",
    "follow": "Ctrl+Shift+F",
    "unfollow": "Ctrl+Alt+F",
    "block": "Ctrl+Shift+B",
    "refresh": "F5",
    "load_more": "Ctrl+M",
    "details": "Enter",
    "open_link": "Ctrl+Enter",
    "toggle_browser": "Ctrl+Shift+M",
    "settings": "Ctrl+P",
}

DEFAULT_GLOBAL_SHORTCUTS: Dict[str, str] = {
    "toggle_visibility": "Ctrl+Win+H",
    "next_post": "Ctrl+Win+Down",
    "prev_post": "Ctrl+Win+Up",
    "next_stream": "Ctrl+Alt+Win+Right",
    "prev_stream": "Ctrl+Alt+Win+Left",
    "new_post": "Alt+Win+N",
    "reply": "Ctrl+Win+R",
    "like": "Alt+Win+L",
    "copy_text": "Alt+Win+C",
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "check_updates_automatically": True,
    "sound_enabled": True,
    "sound_theme": "default",
    "speech_enabled": True,
    "speak_status_alerts": True,
    "speak_new_mentions": True,
    "speak_new_tweets": False,
    "author_display_format": "name_and_username",  # name_and_username, name_only, username_only, username_and_name
    "time_display_format": "relative",             # relative, absolute, both
    "time_position": "after_text",                 # after_text, before_text
    "show_metrics_in_summary": True,
    "hide_to_tray_on_close": False,
    "global_hotkeys_enabled": True,
    "shortcuts": DEFAULT_SHORTCUTS,
    "global_shortcuts": DEFAULT_GLOBAL_SHORTCUTS,
}


class ConfigManager:
    """Gerenciador thread-safe de configurações da aplicação."""
    _instance: Optional["ConfigManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, config_file: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return

        self._initialized = True
        self._rw_lock = threading.Lock()

        if config_file is None:
            base_dir = Path(os.environ.get("APPDATA", ".")) / "AccessibleTimeline"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.config_path = base_dir / "config.json"
        else:
            self.config_path = Path(config_file)
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

        self._settings: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        """Carrega configurações do arquivo JSON, mesclando com os padrões."""
        with self._rw_lock:
            if not self.config_path.exists():
                self._settings = dict(DEFAULT_CONFIG)
                self._save_unlocked()
                return

            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        # Mescla valores lidos com os padrões (incluindo atalhos aninhados)
                        for k, v in DEFAULT_CONFIG.items():
                            if isinstance(v, dict):
                                loaded_sub = data.get(k, {})
                                if isinstance(loaded_sub, dict):
                                    merged = dict(v)
                                    merged.update(loaded_sub)
                                    self._settings[k] = merged
                                else:
                                    self._settings[k] = dict(v)
                            else:
                                self._settings[k] = data.get(k, v)
                    else:
                        self._settings = dict(DEFAULT_CONFIG)
            except Exception as e:
                logger.warning(f"Erro ao ler configurações de {self.config_path}, restaurando padrões: {e}")
                self._settings = dict(DEFAULT_CONFIG)
                self._save_unlocked()

    def save(self):
        """Grava configurações de forma thread-safe."""
        with self._rw_lock:
            self._save_unlocked()

    def _save_unlocked(self):
        try:
            temp_path = self.config_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
            temp_path.replace(self.config_path)
            logger.debug(f"Configurações gravadas com sucesso em {self.config_path}")
        except Exception as e:
            logger.error(f"Falha ao gravar arquivo de configuração: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Obtém o valor de uma chave de configuração."""
        with self._rw_lock:
            val = self._settings.get(key)
            if val is None:
                return default if default is not None else DEFAULT_CONFIG.get(key)
            return val

    def set(self, key: str, value: Any, auto_save: bool = True):
        """Define e persiste um valor de configuração."""
        with self._rw_lock:
            self._settings[key] = value
            if auto_save:
                self._save_unlocked()


config_manager = ConfigManager()
