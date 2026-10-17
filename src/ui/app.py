"""
Aplicação wxPython do Accessible Timeline.
Orquestra o ciclo de vida do aplicativo, da interface em árvore e do leitor de timeline,
distribuindo as postagens entre os stores 'Para você', 'Seguindo', 'Menções' e 'Mensagens diretas'.
"""

import logging
from typing import Dict, List
import wx
from src.core.models import Post
from src.core.timeline_store import TimelineStore
from src.core.config import config_manager
from src.platforms.x_twitter.reader import XTimelineReader
from src.platforms.x_twitter.executor import XActionExecutor
from src.ui.main_window import MainWindow
from src.audio.manager import sound_manager
from src.audio.speech import speech_manager

logger = logging.getLogger("AccessibleTimeline.App")


class AccessibleTimelineApp(wx.App):
    def OnInit(self):
        self.SetAppName("Accessible Timeline")

        # Stores independentes para cada fluxo
        self.stores: Dict[str, TimelineStore] = {
            "for_you": TimelineStore(),
            "following": TimelineStore(),
            "mentions": TimelineStore(),
            "dms": TimelineStore(),
            "sent": TimelineStore(),
        }

        self.reader = XTimelineReader()
        self.executor = XActionExecutor(browser_manager=self.reader.browser_manager)

        # Janela principal com a Árvore de fluxos, a Lista acessível e o Executor de Ações
        self.main_window = MainWindow(
            stores=self.stores,
            reader=self.reader,
            executor=self.executor
        )
        self.SetTopWindow(self.main_window)
        self.main_window.Show()

        self._has_played_ready = False

        # Roteamento de postagens por fluxo com efeitos sonoros do TWBlue
        def on_posts_received(feed_type: str, posts: List[Post]):
            target = feed_type
            if target in ("home", "for_you"):
                target = "for_you"
            elif target in ("notifications", "mentions"):
                target = "mentions"
            elif target in ("messages", "dms"):
                target = "dms"
            elif target == "sent":
                target = "sent"
            elif target.startswith("user:"):
                target = target
            elif target != "following":
                target = "for_you"

            store = self.stores.get(target)
            if store:
                added = store.add_posts(posts, prepend=True)
                if added > 0:
                    logger.info(f"{added} novas postagens adicionadas ao fluxo '{target}'.")
                    if target == "mentions":
                        sound_manager.play_mention_received()
                        if config_manager.get("speak_new_mentions", True) and posts:
                            latest = posts[0]
                            speech_manager.speak(f"Nova menção de {latest.author_name}: {latest.text}", interrupt=False)
                    elif target == "dms":
                        sound_manager.play_dm_received()
                    elif target == "sent":
                        sound_manager.play_tweet_sent()
                    else:
                        sound_manager.play_tweet_received()
                        if config_manager.get("speak_new_tweets", False) and posts:
                            latest = posts[0]
                            speech_manager.speak(f"Novo tweet de {latest.author_name}: {latest.text}", interrupt=False)

        def on_status_change(status_text: str):
            self.main_window.set_status_message(status_text)
            if "Pronto. Publicações carregadas" in status_text and not self._has_played_ready:
                self._has_played_ready = True
                sound_manager.play_ready()

        def on_account_info(account_label: str):
            self.main_window.set_account_name(account_label)

        # Inicia o leitor em thread de segundo plano
        self.reader.start(
            on_posts_received=on_posts_received,
            on_status_change=on_status_change,
            on_account_info=on_account_info
        )

        return True

    def OnExit(self):
        try:
            self.reader.stop()
        except Exception as e:
            logger.error(f"Erro ao finalizar: {e}")
        try:
            sound_manager.close()
        except Exception:
            pass
        return super().OnExit()
