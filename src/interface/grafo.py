"""Desenho esquemático da malha, sem bibliotecas gráficas adicionais."""

from __future__ import annotations

import math
from html import escape


def desenhar_malha(malha: dict, percurso: dict | None = None, trechos_bloqueados: list | None = None, locais_bloqueados: list | None = None) -> str:
    locais = malha["locais"]
    if not locais:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="100"><text x="30" y="50">Malha sem locais cadastrados.</text></svg>'
    bloqueios_t = set(trechos_bloqueados or [])
    bloqueios_l = set(locais_bloqueados or [])
    destacados = {t["id"] for t in (percurso or {}).get("trechos", [])}
    posicoes = {}
    for indice, local in enumerate(locais):
        angulo = 2 * math.pi * indice / len(locais)
        x, y = float(local.get("x", (math.cos(angulo) + 1) / 2)), float(local.get("y", (math.sin(angulo) + 1) / 2))
        if not math.isfinite(x) or not math.isfinite(y):
            x, y = 0.5, 0.5
        posicoes[local["id"]] = (100 + max(0, min(x, 1)) * 760, 80 + max(0, min(y, 1)) * 300)
    partes = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 460" role="img" aria-label="Grafo esquemático da malha logística">',
        '<title>Malha logística da PecinhasTransportes</title>',
        '<rect width="960" height="460" rx="18" fill="#fbfcfd"/>',
        '<defs>',
        '<pattern id="malha-pontos" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r=".8" fill="#dce5eb"/></pattern>',
        '<filter id="sombra-local" x="-40%" y="-40%" width="180%" height="180%"><feDropShadow dx="0" dy="4" stdDeviation="5" flood-color="#14334a" flood-opacity=".1"/></filter>',
    ]
    for nome, cor in (("normal", "#a7b8c5"), ("rota", "#d18b2b"), ("bloqueio", "#d14b50")):
        partes.append(f'<marker id="seta-{nome}" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L8,4 L0,8" fill="{cor}"/></marker>')
    partes.append('</defs>')
    partes.append('<rect x="18" y="18" width="924" height="424" rx="12" fill="url(#malha-pontos)"/>')
    for trecho in malha["trechos"]:
        origem, destino = trecho["origem_id"], trecho["destino_id"]
        if origem not in posicoes or destino not in posicoes:
            continue
        x1, y1 = posicoes[origem]
        x2, y2 = posicoes[destino]
        dx, dy = x2 - x1, y2 - y1
        comprimento = math.hypot(dx, dy) or 1
        ux, uy = dx / comprimento, dy / comprimento
        bloqueado = trecho["id"] in bloqueios_t or origem in bloqueios_l or destino in bloqueios_l or not trecho.get("operante", True)
        classe = "bloqueio" if bloqueado else "rota" if trecho["id"] in destacados else "normal"
        cor = {"bloqueio": "#d14b50", "rota": "#d18b2b", "normal": "#a7b8c5"}[classe]
        tracejado = ' stroke-dasharray="7 5"' if bloqueado else ""
        partes.append(f'<line x1="{x1+ux*32:.1f}" y1="{y1+uy*32:.1f}" x2="{x2-ux*35:.1f}" y2="{y2-uy*35:.1f}" stroke="{cor}" stroke-width="{4 if classe == "rota" else 2}"{tracejado} marker-end="url(#seta-{classe})"/>')
        mx, my = (x1+x2)/2, (y1+y2)/2
        rotulo = escape(f"{trecho['id']} · {trecho['distancia_km']:g} km")
        fundo_rotulo = "#fff5e6" if classe == "rota" else "#fff"
        texto_rotulo = "#9f641c" if classe == "rota" else "#cc5656" if bloqueado else "#5d7487"
        partes.append(f'<rect x="{mx-53:.1f}" y="{my-13:.1f}" width="106" height="25" rx="7" fill="{fundo_rotulo}" stroke="#e2e8ef"/><text x="{mx:.1f}" y="{my+4:.1f}" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-size="12" font-weight="600" fill="{texto_rotulo}">{rotulo}</text>')
    cores = {"CentroDistribuição": "#14354d", "PontoTransbordo": "#678499", "Cliente": "#287e76"}
    tipos = {"CentroDistribuição": "CENTRO DE DISTRIBUIÇÃO", "PontoTransbordo": "TRANSBORDO", "Cliente": "CLIENTE"}
    icones = {
        "CentroDistribuição": "M-12 2v12h24V2M-15 2l15-12L15 2M-5 14V4H5v10",
        "PontoTransbordo": "M-12-6H8l-4-4M8-6l-4 4M12 6H-8l4-4M-8 6l4 4",
        "Cliente": "M-10-7H10V13H-10ZM-12-7l3-6h18l3 6M-4 13V4H4v9",
    }
    for local in locais:
        x, y = posicoes[local["id"]]
        bloqueado = local["id"] in bloqueios_l or not local.get("operante", True)
        cor = "#d14b50" if bloqueado else cores.get(local["tipo"], "#17304b")
        nome = escape(str(local["nome"]).replace(" (demonstração)", "")[:32])
        tipo = escape(tipos.get(local["tipo"], str(local["tipo"])))
        icone = "M-8-8 8 8M8-8-8 8" if bloqueado else icones.get(local["tipo"], icones["Cliente"])
        partes.append(f'<g transform="translate({x:.1f} {y:.1f})"><title>{escape(str(local["nome"]))}</title><rect x="-29" y="-29" width="58" height="58" rx="15" fill="{cor}" stroke="#fff" stroke-width="3" filter="url(#sombra-local)"/><path d="{icone}" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></g>')
        partes.append(f'<text x="{x:.1f}" y="{y+47:.1f}" text-anchor="middle" font-family="Arial,sans-serif" font-size="14" font-weight="bold" fill="#17304b">{nome}</text><text x="{x:.1f}" y="{y+64:.1f}" text-anchor="middle" font-family="Arial,sans-serif" font-size="9" fill="#61738a">{tipo}</text>')
    partes.append('</svg>')
    return "".join(partes)
