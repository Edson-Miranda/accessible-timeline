import unittest
from datetime import datetime, timedelta
from src.core.models import User, Post, MediaItem
from src.core.config import config_manager, DEFAULT_SHORTCUTS, DEFAULT_GLOBAL_SHORTCUTS
from src.ui.main_window import parse_shortcut_to_wx


class TestUserModelAndFormatting(unittest.TestCase):
    def test_user_accessible_summary(self):
        user = User(
            id="123",
            name="Alice Silva",
            username="alicesilva",
            bio="Engenheira de software",
            followers_count=150,
            following_count=80,
            is_following=True,
            is_blocked=False,
        )
        summary = user.to_accessible_summary()
        self.assertIn("Alice Silva (@alicesilva)", summary)
        self.assertIn("[Seguindo]", summary)
        self.assertIn("Bio: Engenheira de software", summary)

    def test_post_customizable_author_display_formats(self):
        post = Post(
            id="999",
            platform="x_twitter",
            author_name="Bob Santos",
            author_username="bobsantos",
            text="Olá mundo!",
        )

        summary_name = post.to_accessible_summary(author_format="name_only")
        self.assertEqual(summary_name, "Bob Santos: Olá mundo!")

        summary_user = post.to_accessible_summary(author_format="username_only")
        self.assertEqual(summary_user, "@bobsantos: Olá mundo!")

        summary_user_name = post.to_accessible_summary(author_format="username_and_name")
        self.assertEqual(summary_user_name, "@bobsantos (Bob Santos): Olá mundo!")

        summary_both = post.to_accessible_summary(author_format="name_and_username")
        self.assertEqual(summary_both, "Bob Santos (@bobsantos): Olá mundo!")

    def test_post_customizable_time_formats(self):
        post = Post(
            id="888",
            platform="x_twitter",
            author_name="Carlos",
            author_username="carlos",
            text="Testando data",
            created_at_str="2026-10-17 14:00:00"
        )
        # Padrão: data/hora após o texto do post (estilo: edson: post, tanto tempo atrás)
        summary = post.to_accessible_summary(time_format="absolute")
        self.assertEqual("Carlos (@carlos): Testando data, 2026-10-17 14:00:00", summary)

        # Configuração alternativa: antes do texto do post
        summary_before = post.to_accessible_summary(time_format="absolute", time_position="before_text")
        self.assertEqual("Carlos (@carlos), 2026-10-17 14:00:00: Testando data", summary_before)

        # Teste com tempo relativo
        now = datetime.now()
        dt_5m = now - timedelta(minutes=5)
        post_rel = Post(
            id="889",
            platform="x_twitter",
            author_name="Edson",
            author_username="edson",
            text="Olá mundo!",
            created_at=dt_5m
        )
        summary_rel = post_rel.to_accessible_summary(time_format="relative", show_metrics=False)
        self.assertEqual("Edson (@edson): Olá mundo!, 5 minutos atrás", summary_rel)

    def test_parse_shortcut_to_wx(self):
        self.assertIsNotNone(parse_shortcut_to_wx("Ctrl+N"))
        self.assertIsNotNone(parse_shortcut_to_wx("Ctrl+Win+H"))
        self.assertIsNotNone(parse_shortcut_to_wx("Ctrl+Win+Down"))
        self.assertIsNotNone(parse_shortcut_to_wx("Ctrl+Alt+Win+Right"))
        self.assertIsNotNone(parse_shortcut_to_wx("F5"))
        self.assertIsNone(parse_shortcut_to_wx("InvalidKeyFormat"))

    def test_default_shortcuts_dictionaries(self):
        self.assertIn("new_post", DEFAULT_SHORTCUTS)
        self.assertIn("close_buffer", DEFAULT_SHORTCUTS)
        self.assertIn("author_timeline", DEFAULT_SHORTCUTS)
        self.assertIn("toggle_visibility", DEFAULT_GLOBAL_SHORTCUTS)
        self.assertIn("next_post", DEFAULT_GLOBAL_SHORTCUTS)
        self.assertIn("prev_post", DEFAULT_GLOBAL_SHORTCUTS)
        self.assertIn("next_stream", DEFAULT_GLOBAL_SHORTCUTS)
        self.assertIn("prev_stream", DEFAULT_GLOBAL_SHORTCUTS)

    def test_stream_display_name_for_user_buffer(self):
        from unittest.mock import MagicMock
        from src.ui.main_window import MainWindow
        # Mock para evitar criar UI completa
        mw = MainWindow.__new__(MainWindow)
        name = mw._get_stream_display_name("user:elonmusk")
        self.assertEqual(name, "Timeline @elonmusk")
        self.assertEqual(mw._get_stream_display_name("for_you"), "Para você")


if __name__ == "__main__":
    unittest.main()
