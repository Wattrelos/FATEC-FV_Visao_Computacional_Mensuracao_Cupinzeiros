#!/usr/bin/env python3
"""
Gerador do Marcador Fiduciário Híbrido (ArUco + Gray Card 18%)
Projeto CupinzeiroVision - FATEC Ferraz de Vasconcelos

Gera prancha em alta resolução (300 DPI) em PNG e formato vetorial SVG,
pronto para impressão gráfica com fidelidade métrica.
"""

import os
import cv2
import numpy as np

def gerar_marcador_png(
    caminho_saida: str,
    dpi: int = 300,
    largura_cm: float = 20.0,
    altura_cm: float = 25.0,
    aruco_cm: float = 10.0,
    dict_aruco_id: int = cv2.aruco.DICT_4X4_50,
    aruco_marker_id: int = 23,
    tom_cinza_18: int = 118
):
    cm_to_inch = 1.0 / 2.54
    px_w = int(round(largura_cm * cm_to_inch * dpi))
    px_h = int(round(altura_cm * cm_to_inch * dpi))
    px_aruco = int(round(aruco_cm * cm_to_inch * dpi))

    # 1. Base cinza neutro 18% (sRGB 118, correspondente a L*=50)
    cartao = np.full((px_h, px_w, 3), tom_cinza_18, dtype=np.uint8)

    # 2. Geração da Tag ArUco nítida
    dicionario = cv2.aruco.getPredefinedDictionary(dict_aruco_id)
    aruco_mono = cv2.aruco.generateImageMarker(dicionario, aruco_marker_id, px_aruco)
    aruco_bgr = cv2.cvtColor(aruco_mono, cv2.COLOR_GRAY2BGR)

    # 3. Centralização do marcador
    offset_x = (px_w - px_aruco) // 2
    offset_y = (px_h - px_aruco) // 2
    cartao[offset_y:offset_y + px_aruco, offset_x:offset_x + px_aruco] = aruco_bgr

    # 4. Borda de corte e marcas técnicas
    cor_borda = (70, 70, 70)
    cv2.rectangle(cartao, (0, 0), (px_w - 1, px_h - 1), cor_borda, thickness=3)

    # 5. Legenda técnica de referência
    legenda = f"FATEC Ferraz | CupinzeiroVision | ArUco DICT_4X4_50 ID:{aruco_marker_id} ({aruco_cm:.0f}x{aruco_cm:.0f} cm) | Gray Card 18% ({largura_cm:.0f}x{altura_cm:.0f} cm) | 300 DPI"
    cv2.putText(
        cartao, legenda,
        (offset_x - 100, px_h - int(0.6 * cm_to_inch * dpi)),
        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (60, 60, 60), 2, cv2.LINE_AA
    )

    cv2.imwrite(caminho_saida, cartao, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    print(f"[OK] PNG 300 DPI gerado: {caminho_saida} ({px_w}x{px_h} px)")

def gerar_marcador_svg(
    caminho_saida: str,
    largura_cm: float = 20.0,
    altura_cm: float = 25.0,
    aruco_cm: float = 10.0,
    dict_aruco_id: int = cv2.aruco.DICT_4X4_50,
    aruco_marker_id: int = 23
):
    dicionario = cv2.aruco.getPredefinedDictionary(dict_aruco_id)
    # Extrai matriz 6x6 (4x4 de dados + 1 borda preta em cada extremidade)
    tamanho_grade = 4 + 2  # 6x6 para 4x4
    matriz_bits = cv2.aruco.generateImageMarker(dicionario, aruco_marker_id, tamanho_grade)

    offset_x_cm = (largura_cm - aruco_cm) / 2.0
    offset_y_cm = (altura_cm - aruco_cm) / 2.0
    tam_bloco_cm = aruco_cm / float(tamanho_grade)

    svg_linhas = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura_cm}cm" height="{altura_cm}cm" viewBox="0 0 {largura_cm} {altura_cm}">',
        f'  <!-- Fundo Gray Card 18% (sRGB #767676) -->',
        f'  <rect x="0" y="0" width="{largura_cm}" height="{altura_cm}" fill="#767676" />',
        f'  <!-- Borda de corte de 20x25 cm -->',
        f'  <rect x="0.05" y="0.05" width="{largura_cm - 0.1}" height="{altura_cm - 0.1}" fill="none" stroke="#505050" stroke-width="0.05" />',
        f'  <!-- Tag ArUco DICT_4X4_50 ID {aruco_marker_id} -->',
        f'  <g id="aruco_marker">'
    ]

    for r in range(tamanho_grade):
        for c in range(tamanho_grade):
            val = matriz_bits[r, c]
            cor = "#000000" if val == 0 else "#FFFFFF"
            bx = offset_x_cm + c * tam_bloco_cm
            by = offset_y_cm + r * tam_bloco_cm
            svg_linhas.append(
                f'    <rect x="{bx:.4f}" y="{by:.4f}" width="{tam_bloco_cm:.4f}" height="{tam_bloco_cm:.4f}" fill="{cor}" />'
            )

    svg_linhas.append('  </g>')
    # Legenda técnica
    svg_linhas.append(
        f'  <text x="{largura_cm/2}" y="{altura_cm - 0.6}" font-family="Arial, sans-serif" font-size="0.35" fill="#3a3a3a" text-anchor="middle">'
        f'FATEC Ferraz | CupinzeiroVision | ArUco 4x4 ID:{aruco_marker_id} (10x10cm) | Gray Card 18% (20x25cm)</text>'
    )
    svg_linhas.append('</svg>')

    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_linhas))
    print(f"[OK] SVG Vetorial gerado: {caminho_saida}")

if __name__ == "__main__":
    dir_atual = os.path.dirname(os.path.abspath(__file__))
    saida_png = os.path.join(dir_atual, "marcador_hibrido_20x25cm_300dpi.png")
    saida_svg = os.path.join(dir_atual, "marcador_hibrido_20x25cm.svg")
    
    gerar_marcador_png(saida_png)
    gerar_marcador_svg(saida_svg)
