"""
Modelos de dados universais para o Accessible Timeline.
Projetados para serem agnósticos de plataforma.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from src.core.config import config_manager


@dataclass
class User:
    """Representa um perfil de usuário na plataforma."""
    id: str
    name: str
    username: str
    bio: str = ""
    followers_count: int = 0
    following_count: int = 0
    is_following: bool = False
    is_blocked: bool = False
    profile_image_url: str = ""
    url: str = ""

    def to_accessible_summary(self) -> str:
        """Formata o perfil do usuário para leitura limpa por leitor de tela."""
        status_part = "[Seguindo]" if self.is_following else "[Não seguido]"
        if self.is_blocked:
            status_part = "[Bloqueado]"
        bio_part = f" • Bio: {self.bio}" if self.bio else ""
        return f"{self.name} (@{self.username}) {status_part}{bio_part}"


@dataclass
class MediaItem:
    """Representa uma mídia anexada a uma postagem."""
    media_type: str  # 'image', 'video', 'gif'
    url: str
    alt_text: Optional[str] = None


def format_relative_time(dt: Optional[datetime], now: Optional[datetime] = None) -> str:
    """
    Formata um datetime em tempo relativo amigável e acessível (estilo TWBlue):
    Exemplos:
    - 'agora há pouco' (< 45s)
    - '1 minuto atrás' / '5 minutos atrás'
    - '1 hora atrás' / '3 horas atrás'
    - 'ontem' (se 1 dia) / '4 dias atrás'
    - '1 semana atrás' / '2 semanas atrás'
    - '1 mês atrás' / '5 meses atrás'
    - '1 ano atrás' / '2 anos atrás'
    """
    if not dt:
        return ""

    if now is None:
        if dt.tzinfo is not None:
            now = datetime.now(dt.tzinfo)
        else:
            now = datetime.now()

    # Normaliza fuso horário caso um tenha e outro não
    if dt.tzinfo is not None and now.tzinfo is None:
        now = now.astimezone(dt.tzinfo)
    elif dt.tzinfo is None and now.tzinfo is not None:
        dt = dt.astimezone(now.tzinfo)

    diff_seconds = (now - dt).total_seconds()
    if diff_seconds < 45:
        return "agora há pouco"

    diff_minutes = int(diff_seconds / 60)
    if diff_minutes < 60:
        return f"{diff_minutes} minuto atrás" if diff_minutes == 1 else f"{diff_minutes} minutos atrás"

    diff_hours = int(diff_seconds / 3600)
    if diff_hours < 24:
        return f"{diff_hours} hora atrás" if diff_hours == 1 else f"{diff_hours} horas atrás"

    diff_days = int(diff_seconds / 86400)
    if diff_days < 7:
        if diff_days == 1:
            return "ontem"
        return f"{diff_days} dias atrás"

    diff_weeks = int(diff_days / 7)
    if diff_weeks < 5:
        return f"{diff_weeks} semana atrás" if diff_weeks == 1 else f"{diff_weeks} semanas atrás"

    diff_months = int(diff_days / 30)
    if diff_months < 12:
        return f"{diff_months} mês atrás" if diff_months == 1 else f"{diff_months} meses atrás"

    diff_years = int(diff_days / 365)
    return f"{diff_years} ano atrás" if diff_years == 1 else f"{diff_years} anos atrás"


@dataclass
class Post:
    """Representa uma publicação de qualquer rede social suportada."""
    id: str
    platform: str
    author_name: str
    author_username: str
    text: str
    created_at: Optional[datetime] = None
    created_at_str: str = ""
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    media_items: List[MediaItem] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    url: str = ""
    is_retweet: bool = False
    retweeted_by: Optional[str] = None
    is_reply: bool = False
    replying_to: Optional[str] = None

    @property
    def has_media(self) -> bool:
        return len(self.media_items) > 0

    @property
    def media_summary(self) -> str:
        if not self.media_items:
            return ""
        count = len(self.media_items)
        types = [m.media_type for m in self.media_items]
        if all(t == "image" for t in types):
            return f"{count} imagem" if count == 1 else f"{count} imagens"
        elif any(t == "video" for t in types):
            return "vídeo"
        elif any(t == "gif" for t in types):
            return "GIF"
        return f"{count} mídias"

    def get_all_links(self) -> List[str]:
        """
        Retorna todos os links únicos associados à publicação:
        links contidos nas entidades/texto, mídias e a URL da própria postagem.
        """
        links: List[str] = []

        # 1. URLs das entidades extraídas do tweet
        for u in self.urls:
            if u and u not in links:
                links.append(u)

        # 2. URLs detectadas no texto da postagem
        import re
        url_pattern = re.compile(r'https?://[^\s<>"\'()]+')
        for match in url_pattern.findall(self.text):
            clean = match.rstrip(".,;:!?")
            if clean and clean not in links:
                links.append(clean)

        # 3. URLs das mídias anexadas
        for m in self.media_items:
            if m.url and m.url not in links:
                links.append(m.url)

        # 4. URL da publicação no X
        if self.url and self.url not in links:
            links.append(self.url)

        return links

    def get_relative_time(self, now: Optional[datetime] = None) -> str:
        """Retorna o tempo decorrido desde a publicação em formato amigável."""
        if self.created_at:
            return format_relative_time(self.created_at, now=now)
        return self.created_at_str

    def to_accessible_summary(
        self,
        author_format: Optional[str] = None,
        time_format: Optional[str] = None,
        show_metrics: Optional[bool] = None,
        time_position: Optional[str] = None
    ) -> str:
        """
        Retorna o texto da publicação para anúncio natural na lista pelo leitor de tela.
        Suporta os formatos customizáveis de exibição do autor, data/hora e métricas (estilo TWBlue).
        """
        if author_format is None:
            author_format = config_manager.get("author_display_format", "name_and_username")
        if time_format is None:
            time_format = config_manager.get("time_display_format", "relative")
        if show_metrics is None:
            show_metrics = config_manager.get("show_metrics_in_summary", True)
        if time_position is None:
            time_position = config_manager.get("time_position", "after_text")

        # Formatação do autor
        if author_format == "name_only":
            author_str = self.author_name
        elif author_format == "username_only":
            author_str = f"@{self.author_username}"
        elif author_format == "username_and_name":
            author_str = f"@{self.author_username} ({self.author_name})"
        else:  # name_and_username (padrão)
            author_str = f"{self.author_name} (@{self.author_username})"

        # Formatação de data/hora
        rel_time = self.get_relative_time()
        if time_format == "absolute":
            time_str = self.created_at_str
        elif time_format == "both":
            if rel_time and self.created_at_str:
                time_str = f"{rel_time} ({self.created_at_str})"
            else:
                time_str = rel_time or self.created_at_str
        else:  # relative (padrão)
            time_str = rel_time or self.created_at_str

        time_part = f", {time_str}" if time_str else ""

        prefix = ""
        if self.is_retweet and self.retweeted_by:
            prefix = f"[Repost de {self.retweeted_by}] "
        elif self.is_reply and self.replying_to:
            prefix = f"[Respondendo a @{self.replying_to}] "

        clean_text = " ".join(self.text.split())

        metrics_part = ""
        if show_metrics:
            metrics = []
            if self.like_count > 0:
                metrics.append(f"{self.like_count} curtida" if self.like_count == 1 else f"{self.like_count} curtidas")
            if self.retweet_count > 0:
                metrics.append(f"{self.retweet_count} repost" if self.retweet_count == 1 else f"{self.retweet_count} reposts")
            if self.reply_count > 0:
                metrics.append(f"{self.reply_count} resposta" if self.reply_count == 1 else f"{self.reply_count} respostas")
            if self.has_media:
                metrics.append(self.media_summary)
            if metrics:
                metrics_part = f" • {', '.join(metrics)}"

        if time_position == "before_text":
            return f"{prefix}{author_str}{time_part}: {clean_text}{metrics_part}"
        else:  # after_text (padrão): autor: texto, tempo
            if clean_text:
                body = f"{clean_text}{time_part}"
            else:
                body = time_str
            return f"{prefix}{author_str}: {body}{metrics_part}"

    def to_accessible_full(self) -> str:
        """
        Retorna a publicação formatada em detalhes para diálogo ou leitura completa.
        """
        lines = []
        if self.is_retweet and self.retweeted_by:
            lines.append(f"Repostado por: {self.retweeted_by}")
        if self.is_reply and self.replying_to:
            lines.append(f"Em resposta a: @{self.replying_to}")

        lines.append(f"Autor: {self.author_name} (@{self.author_username})")
        rel_time = self.get_relative_time()
        if rel_time and self.created_at_str:
            lines.append(f"Data: {rel_time} ({self.created_at_str})")
        elif rel_time:
            lines.append(f"Data: {rel_time}")
        elif self.created_at_str:
            lines.append(f"Data/Hora: {self.created_at_str}")
        lines.append("")
        lines.append(self.text)
        lines.append("")

        metrics = []
        metrics.append(f"Curtidas: {self.like_count}")
        metrics.append(f"Repostagens: {self.retweet_count}")
        metrics.append(f"Respostas: {self.reply_count}")
        if self.has_media:
            metrics.append(f"Anexos: {self.media_summary}")
            for idx, media in enumerate(self.media_items, 1):
                alt = f" (Descrição: {media.alt_text})" if media.alt_text else ""
                lines.append(f"- Anexo {idx} [{media.media_type}]: {media.url}{alt}")
        lines.append(" | ".join(metrics))

        if self.url:
            lines.append(f"Link: {self.url}")

        return "\n".join(lines)
