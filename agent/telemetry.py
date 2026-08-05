"""telemetry.py — os números do painel esquerdo, medidos de verdade.

O design system pede um bloco STATUS DO SISTEMA com quatro medidores. Na
maquete eles são fixtures: o handoff diz, com todas as letras, *"values drift
±3.5 every 2400ms"*. Sobem e descem sozinhos para a tela parecer viva.

Isso não pode entrar assim. Um número inventado na tela do Edson é a mesma
falha que o assistente inteiro foi construído para não cometer — e é também a
regra 3 do próprio design system: *"Say what is missing, never what is fine."*
Um medidor que oscila sem medir nada diz que está tudo bem sem ter olhado.

Então aqui cada número é medido, e o que não dá para medir **não aparece**.

## O que é medido, e como

- **Disco**: `shutil.disk_usage` na unidade onde o vault mora. Biblioteca
  padrão, exato.
- **RAM**: `GlobalMemoryStatusEx` via `ctypes` no Windows; `/proc/meminfo` no
  Linux. Biblioteca padrão nos dois casos.
- **CPU**: `GetSystemTimes` via `ctypes`, comparando duas leituras — é assim
  que qualquer monitor calcula percentual de uso. A primeira chamada não tem
  com o que comparar e devolve `None`, e `None` vira "—" na tela, não zero.
- **GPU**: não é medido. Não existe forma de ler GPU pela biblioteca padrão, e
  instalar um pacote para desenhar uma barra bonita seria o rabo abanando o
  cachorro. O bloco simplesmente não tem essa linha.

`psutil` resolveria tudo isto em três linhas. Foi recusado no inventário do
Mark-L ("existem monitores melhores e o assistente não é um deles") e a recusa
continua de pé: a dependência é para *desenhar um medidor*, não para o JARVIS
fazer o trabalho dele. O que dá para medir com a stdlib, mede-se; o resto fica
de fora, honestamente vazio.

Rode direto:  python -m agent.telemetry
"""

from __future__ import annotations

import ctypes
import shutil
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod

_STARTED = time.time()

# Duas leituras de CPU precisam de intervalo entre elas. Guardadas aqui.
_cpu_last: tuple[int, int] | None = None


def _pct(used: float, total: float) -> int | None:
    return round(used / total * 100) if total else None


def disk() -> dict[str, object]:
    """Uso do disco onde o vault está — não do C: por convenção."""
    roots = data_mod.vault_sources().roots
    where = roots[0].path if roots else Path.cwd()
    try:
        usage = shutil.disk_usage(where.anchor or str(where))
    except OSError as exc:
        return {"pct": None, "note": f"não li o disco: {exc}"}
    return {
        "pct": _pct(usage.used, usage.total),
        "free_gb": round(usage.free / 1024**3, 1),
        "total_gb": round(usage.total / 1024**3, 1),
        "where": where.anchor or str(where),
    }


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def ram() -> dict[str, object]:
    if sys.platform == "win32":
        status = _MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return {"pct": None, "note": "GlobalMemoryStatusEx falhou"}
        return {
            "pct": int(status.dwMemoryLoad),
            "used_gb": round((status.ullTotalPhys - status.ullAvailPhys) / 1024**3, 1),
            "total_gb": round(status.ullTotalPhys / 1024**3, 1),
        }
    try:
        fields = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            fields[key] = int(rest.strip().split()[0]) * 1024
        total, avail = fields["MemTotal"], fields["MemAvailable"]
        return {"pct": _pct(total - avail, total),
                "used_gb": round((total - avail) / 1024**3, 1),
                "total_gb": round(total / 1024**3, 1)}
    except (OSError, KeyError, ValueError, IndexError):
        return {"pct": None, "note": "sem leitura de memória nesta plataforma"}


def cpu() -> dict[str, object]:
    """Percentual de uso entre esta chamada e a anterior.

    A primeira devolve None de propósito: uma leitura só não é um percentual,
    e chutar zero seria exatamente a mentira que este arquivo existe para
    evitar. A tela mostra "—" até a segunda amostra.
    """
    global _cpu_last
    if sys.platform != "win32":
        return {"pct": None, "note": "sem leitura de CPU nesta plataforma"}

    idle, kernel, user = (ctypes.c_ulonglong(), ctypes.c_ulonglong(),
                          ctypes.c_ulonglong())
    if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return {"pct": None, "note": "GetSystemTimes falhou"}

    # kernel inclui o tempo ocioso; o total é kernel + user.
    now = (idle.value, kernel.value + user.value)
    was, _cpu_last = _cpu_last, now
    if was is None:
        return {"pct": None, "note": "primeira amostra"}
    d_idle, d_total = now[0] - was[0], now[1] - was[1]
    if d_total <= 0:
        return {"pct": None, "note": "intervalo curto demais"}
    return {"pct": max(0, min(100, round((d_total - d_idle) / d_total * 100)))}


def uptime() -> dict[str, object]:
    """Há quanto tempo este servidor está de pé. Medido, não estimado."""
    seconds = int(time.time() - _STARTED)
    hours, rest = divmod(seconds, 3600)
    return {"seconds": seconds, "label": f"{hours}h{rest // 60:02d}" if hours
            else f"{rest // 60}m{rest % 60:02d}"}


def state() -> dict[str, object]:
    """Tudo de uma vez, para uma chamada só por atualização de painel."""
    return {"cpu": cpu(), "ram": ram(), "disk": disk(), "uptime": uptime(),
            # Dito na cara para quem for desenhar o painel: não há linha de GPU
            # porque não há leitura de GPU. Um medidor a menos, zero invenção.
            "gpu": {"pct": None, "note": "sem leitura pela biblioteca padrão"}}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    cpu()                       # primeira amostra
    time.sleep(0.4)
    info = state()
    for name in ("cpu", "ram", "disk", "gpu"):
        row = info[name]                       # type: ignore[index]
        pct = row.get("pct")                   # type: ignore[union-attr]
        shown = f"{pct}%" if pct is not None else f"—  ({row.get('note', '')})"  # type: ignore[union-attr]
        print(f"  {name.upper():<6} {shown}")
    print(f"  UPTIME {info['uptime']['label']}")   # type: ignore[index]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
