"""
Módulo de verificação de atualizações do Accessible Timeline via GitHub Releases.
"""

import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from typing import Callable, Optional, Dict, Any
from src.core.version import __version__, GITHUB_OWNER, GITHUB_REPO

logger = logging.getLogger("AccessibleTimeline.Updater")


def parse_version_tuple(v_str: str) -> tuple:
    """Converte strings como 'v0.2.0', '0.2.1A' ou 'v1.0.0-dev.1' em tupla comparável."""
    cleaned = v_str.lstrip("v").strip().split("-")[0]
    parts = []
    for p in cleaned.split("."):
        m = re.match(r"^(\d+)([a-zA-Z]*)", p)
        if m:
            parts.append(int(m.group(1)))
            if m.group(2):
                parts.append(ord(m.group(2).upper()))
        else:
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
    return tuple(parts)


def check_for_updates(
    current_version: str = __version__,
    owner: str = GITHUB_OWNER,
    repo: str = GITHUB_REPO,
    timeout: int = 5
) -> Optional[Dict[str, Any]]:
    """
    Consulta o GitHub Releases para verificar se há uma nova versão disponível.
    Retorna um dicionário com detalhes da nova versão ou None se já estiver na versão mais recente.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"AccessibleTimeline/{current_version}",
            "Accept": "application/vnd.github.v3+json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read().decode("utf-8"))

        latest_tag = data.get("tag_name", "")
        if not latest_tag:
            return None

        current_tuple = parse_version_tuple(current_version)
        latest_tuple = parse_version_tuple(latest_tag)

        if latest_tuple > current_tuple:
            # Encontra link do asset .zip ou .exe se houver
            download_url = data.get("html_url", "")
            for asset in data.get("assets", []):
                name = asset.get("name", "").lower()
                if name.endswith(".zip") or name.endswith(".exe"):
                    download_url = asset.get("browser_download_url", download_url)
                    break

            return {
                "latest_version": latest_tag.lstrip("v"),
                "release_name": data.get("name", latest_tag),
                "notes": data.get("body", ""),
                "html_url": data.get("html_url", ""),
                "download_url": download_url
            }

    except Exception as e:
        logger.debug(f"Não foi possível verificar atualizações: {e}")

    return None


def get_application_directory() -> str:
    """Retorna o diretório base da instalação do aplicativo."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).parent.resolve())
    return str(Path(__file__).resolve().parent.parent.parent)


def download_update_archive(
    url: str,
    target_file: str,
    progress_callback: Optional[Callable[[int, int], Optional[bool]]] = None,
    chunk_size: int = 65536
) -> bool:
    """
    Baixa o pacote compactado da atualização a partir da URL do GitHub.
    Chama progress_callback(bytes_baixados, total_bytes).
    Se o callback retornar False, o download é cancelado.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"AccessibleTimeline/{__version__}"}
    )
    temp_target = target_file + ".part"
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            with open(temp_target, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        should_continue = progress_callback(downloaded, total_size)
                        if should_continue is False:
                            logger.info("Download cancelado pelo usuário.")
                            f.close()
                            if os.path.exists(temp_target):
                                os.remove(temp_target)
                            return False

            if os.path.exists(target_file):
                os.remove(target_file)
            os.rename(temp_target, target_file)
            logger.info(f"Download da atualização concluído com sucesso: {target_file}")
            return True
    except Exception as e:
        logger.error(f"Erro ao baixar arquivo de atualização: {e}")
        if os.path.exists(temp_target):
            try:
                os.remove(temp_target)
            except Exception:
                pass
        return False


def extract_update_archive(
    zip_path: str,
    target_extract_dir: str,
    progress_callback: Optional[Callable[[int, int], Optional[bool]]] = None
) -> Optional[str]:
    """
    Extrai o arquivo de atualização compactado para target_extract_dir utilizando o módulo zipfile.
    Se o pacote contiver uma pasta raiz única englobando os arquivos, retorna o caminho dessa subpasta;
    caso contrário, retorna target_extract_dir.
    Chama progress_callback(arquivos_extraidos, total_arquivos).
    Se o callback retornar False, cancela a extração.
    Retorna o caminho do diretório contendo os arquivos prontos, ou None em caso de falha.
    """
    os.makedirs(target_extract_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.infolist()
            total = len(members)
            for i, member in enumerate(members, 1):
                zf.extract(member, target_extract_dir)
                if progress_callback and (i % 15 == 0 or i == total):
                    should_continue = progress_callback(i, total)
                    if should_continue is False:
                        logger.info("Extração cancelada pelo usuário.")
                        return None

        # Se houver uma subpasta única na raiz contendo os arquivos (ex: AccessibleTimeline/AccessibleTimeline.exe)
        entries = os.listdir(target_extract_dir)
        if len(entries) == 1:
            single_path = os.path.join(target_extract_dir, entries[0])
            if os.path.isdir(single_path):
                return single_path

        return target_extract_dir
    except Exception as e:
        logger.error(f"Erro ao extrair pacote de atualização: {e}")
        return None


def apply_update_and_restart(
    source_dir: str,
    target_dir: str,
    current_pid: int,
    exe_name: str = "AccessibleTimeline.exe"
) -> bool:
    """
    Cria e executa um script batch desacoplado que aguarda o encerramento do processo atual,
    copia os arquivos já descompactados da pasta source_dir para target_dir (substituindo-os)
    e reinicia o Accessible Timeline.
    """
    script_path = os.path.join(tempfile.gettempdir(), f"update_at_{current_pid}.bat")
    exe_path = os.path.join(target_dir, exe_name)

    batch_content = f"""@echo off
chcp 65001 >nul
set "PID={current_pid}"
set "SOURCE_DIR={source_dir}"
set "TARGET_DIR={target_dir}"
set "EXE_PATH={exe_path}"

:: Aguarda o processo principal encerrar (com timeout de até 15 segundos)
set count=0
:wait_loop
tasklist /fi "PID eq %PID%" 2>nul | findstr /i "%PID%" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    set /a count+=1
    if %count% geq 15 (
        taskkill /f /pid %PID% >nul 2>nul
        goto wait_done
    )
    goto wait_loop
)
:wait_done

:: Aguarda 2 segundos para liberar todas as travas de DLLs e recursos em disco
timeout /t 2 /nobreak >nul

:: Garante encerramento de qualquer processo residual do browser chromium
taskkill /f /im chrome.exe /fi "WINDOWTITLE eq Accessible*" 2>nul

:: Copia os arquivos já extraídos para a pasta de destino (robocopy nativo do Windows)
robocopy "%SOURCE_DIR%" "%TARGET_DIR%" /E /IS /IT /R:5 /W:1 >nul
if errorlevel 8 (
    xcopy "%SOURCE_DIR%\\*" "%TARGET_DIR%\\" /E /Y /I /Q >nul
)

:: Remove a pasta temporária de arquivos descompactados
rmdir /s /q "%SOURCE_DIR%" 2>nul

:: Reinicia a aplicação atualizada
if exist "%EXE_PATH%" (
    start "" "%EXE_PATH%"
)

:: Auto-exclusão deste script batch auxiliar
(goto) 2>nul & del "%~f0"
"""

    try:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(batch_content)

        # Inicia o script batch em processo totalmente independente (detached)
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        subprocess.Popen(
            ["cmd.exe", "/c", script_path],
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
            shell=False
        )
        logger.info(f"Script de atualização disparado com sucesso: {script_path}")
        return True
    except Exception as e:
        logger.error(f"Falha ao disparar script de atualização: {e}")
        return False

