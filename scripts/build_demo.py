"""Build a static, explicitly recorded demo and video from real synthetic CI evidence.

No browser capture is fabricated: the video is a motion graphic of captured spans
and verified database assertions. No live API or production data is accessed.
"""

import argparse
import hashlib
import json
import math
import shutil
from html import escape
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, FPS, DURATION = 1280, 720, 24, 60
SCENE_DURATION = 10
BG, PANEL, LINE = "#080f1d", "#111e32", "#26384e"
WHITE, MUTED, CYAN, GREEN, AMBER = (
    "#eff5ff",
    "#a9b9cf",
    "#62deed",
    "#81ecc3",
    "#ffcd87",
)
CAPTIONS = [
    "Há uma unidade no estoque. Duas compras chegam juntas. "
    "A API deve impedir uma venda duplicada.",
    "Cada compra usa sua própria sessão e transação. As duas acessam o mesmo produto.",
    "O teste segura a linha por alguns instantes. "
    "O PostgreSQL confirma duas conexões em espera e libera a barreira.",
    "Ao liberar a barreira, uma compra desconta a unidade e confirma. "
    "O estoque passa de um para zero.",
    "A outra compra retoma e lê zero. Recebe estoque insuficiente, "
    "faz rollback e não grava outra venda.",
    "O request_id liga endpoint, autenticação, permissão, lock e transação. "
    "Resultado: uma venda e estoque correto.",
]


def font(size: int, *, mono: bool = False, bold: bool = False):
    paths = (
        [
            "C:/Windows/Fonts/consola.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        ]
        if mono
        else [
            f"C:/Windows/Fonts/{'segoeuib' if bold else 'segoeui'}.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans"
            + ("-Bold.ttf" if bold else ".ttf"),
        ]
    )
    for path in paths:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError("Install DejaVu Sans fonts to build the demonstration video")


FONTS = {}


def label(draw, xy, value, size=24, color=WHITE, *, mono=False, bold=False):
    key = (size, mono, bold)
    if key not in FONTS:
        FONTS[key] = font(size, mono=mono, bold=bold)
    draw.text(xy, str(value), font=FONTS[key], fill=color)


def centered_label(draw, rect, value, size=24, color=WHITE, *, mono=False, bold=False):
    key = (size, mono, bold)
    if key not in FONTS:
        FONTS[key] = font(size, mono=mono, bold=bold)
    text = str(value)
    bounds = draw.textbbox((0, 0), text, font=FONTS[key])
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    x = rect[0] + (rect[2] - rect[0] - width) / 2
    y = rect[1] + (rect[3] - rect[1] - height) / 2 - bounds[1]
    draw.text((x, y), text, font=FONTS[key], fill=color)


def box(draw, rect, fill=PANEL, outline=LINE):
    draw.rounded_rectangle(rect, radius=14, fill=fill, outline=outline, width=1)


def ease_out(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return 1 - (1 - value) ** 3


def motion_background(draw, seconds: float):
    """Subtle moving grid particles keep the explainer visually alive."""
    for index in range(11):
        x = int((index * 149 + seconds * (10 + index % 3 * 3)) % (WIDTH + 80)) - 40
        y = 112 + (index * 47) % 470
        radius = 2 + index % 2
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="#18304a")


def successful_spans(data):
    request_id = next(
        r["request_id"] for r in data["responses"] if r["status_code"] == 201
    )
    return [s for s in data["spans"] if s["attributes"]["request.id"] == request_id]


def frame(data, seconds):
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(canvas)
    scene = min(len(CAPTIONS) - 1, int(seconds // SCENE_DURATION))
    local_seconds = seconds % SCENE_DURATION
    enter = ease_out(local_seconds / 1.15)
    pulse = (math.sin(seconds * math.pi * 1.4) + 1) / 2
    motion_background(draw, seconds)
    label(draw, (56, 35), "STOCKFLOW", 22, CYAN, bold=True)
    label(draw, (225, 39), "/ DEMO EXPLICADA", 15, MUTED, mono=True)
    label(draw, (878, 39), "DADOS FICTÍCIOS · NARRAÇÃO PT-BR", 15, GREEN)
    draw.line((56, 81, 1224, 81), fill=LINE, width=1)
    label(draw, (56, 103), f"ETAPA {scene + 1} DE 6", 16, CYAN, mono=True)

    if scene == 0:
        label(draw, (56, 145), "O desafio", 23, CYAN, bold=True)
        label(draw, (56, 177), "2 compras. Apenas 1 unidade.", 55, bold=True)
        label(draw, (58, 250), "As duas requisições chegam juntas.", 27, MUTED)
        left_x = int(-320 + 376 * enter)
        right_x = int(WIDTH + 10 - 380 * enter)
        for x, title in ((left_x, "COMPRA A"), (right_x, "COMPRA B")):
            box(draw, (x, 330, x + 314, 470))
            centered_label(draw, (x, 346, x + 314, 383), title, 18, CYAN, mono=True)
            centered_label(draw, (x, 392, x + 314, 447), "QUER 1", 34, bold=True)
        scale = 0.92 + 0.08 * enter + 0.01 * pulse
        half_width, half_height = int(202 * scale), int(99 * scale)
        product_rect = (
            640 - half_width,
            409 - half_height,
            640 + half_width,
            409 + half_height,
        )
        box(draw, product_rect, fill="#152944", outline=CYAN)
        centered_label(draw, (438, 336, 842, 378), "ESTOQUE INICIAL", 19, MUTED)
        centered_label(draw, (438, 375, 842, 474), "1", 86, CYAN, bold=True)
        arrow_progress = ease_out(max(0, local_seconds - 1.1) / 1.1)
        left_end = int(371 + 56 * arrow_progress)
        right_end = int(909 - 56 * arrow_progress)
        draw.line((371, 400, left_end, 400), fill=CYAN, width=4)
        draw.line((909, 400, right_end, 400), fill=CYAN, width=4)
        if arrow_progress > 0.85:
            draw.polygon(((427, 400), (414, 391), (414, 409)), fill=CYAN)
            draw.polygon(((853, 400), (866, 391), (866, 409)), fill=CYAN)
        label(
            draw,
            (56, 549),
            "Objetivo: impedir duas vendas para o mesmo item.",
            26,
            WHITE,
        )
    elif scene == 1:
        label(draw, (56, 145), "1. Requisições independentes", 49, bold=True)
        label(
            draw,
            (58, 213),
            "Cada compra tem seu próprio contexto transacional.",
            26,
            MUTED,
        )
        for card_index, (x, title) in enumerate(((56, "COMPRA A"), (650, "COMPRA B"))):
            delayed = ease_out(max(0, local_seconds - card_index * 0.25) / 1.1)
            y = int(337 - 50 * delayed)
            box(draw, (x, y, x + 574, y + 213))
            label(draw, (x + 28, y + 25), title, 19, CYAN, mono=True)
            entries = (
                "1  AsyncSession própria",
                "2  Transação própria",
                "3  Mesmo produto",
            )
            for item_index, item in enumerate(entries):
                if local_seconds >= 1.4 + item_index * 1.15:
                    label(draw, (x + 28, y + 72 + item_index * 50), item, 26)
        if local_seconds >= 4.5:
            banner_y = int(600 - 65 * ease_out((local_seconds - 4.5) / 0.9))
            box(
                draw, (310, banner_y, 970, banner_y + 50), fill="#10293a", outline=GREEN
            )
            centered_label(
                draw,
                (310, banner_y, 970, banner_y + 50),
                "Nenhuma sessão é compartilhada entre as compras",
                22,
                GREEN,
                bold=True,
            )
    elif scene == 2:
        label(draw, (56, 145), "2. PostgreSQL controla a fila", 49, bold=True)
        label(
            draw,
            (58, 213),
            "O teste segura a linha e observa as duas compras esperando.",
            25,
            MUTED,
        )
        left_x = int(-320 + 376 * enter)
        right_x = int(WIDTH + 10 - 380 * enter)
        for x, title in ((left_x, "COMPRA A"), (right_x, "COMPRA B")):
            box(draw, (x, 329, x + 314, 465))
            centered_label(draw, (x, 346, x + 314, 385), title, 18, MUTED, mono=True)
            if local_seconds >= 1.2:
                wait_y = int(402 - 10 * pulse)
                centered_label(
                    draw,
                    (x, wait_y - 10, x + 314, wait_y + 40),
                    "EM ESPERA",
                    28,
                    AMBER,
                    bold=True,
                )
        lock_padding = int(4 * pulse)
        box(
            draw,
            (
                424 - lock_padding,
                284 - lock_padding,
                856 + lock_padding,
                503 + lock_padding,
            ),
            fill="#152944",
            outline=CYAN,
        )
        centered_label(draw, (424, 304, 856, 343), "LINHA DO PRODUTO", 18, MUTED)
        centered_label(draw, (424, 352, 856, 423), "LOCK", 52, CYAN, bold=True)
        centered_label(draw, (424, 436, 856, 477), "barreira controlada", 20, WHITE)
        observed = min(data["blocked_connections"], max(0, int(local_seconds - 2.2)))
        if observed:
            waiting_summary = (
                f"{observed} de {data['blocked_connections']} conexões "
                "confirmadas em espera"
            )
            label(
                draw,
                (56, 535),
                waiting_summary,
                30,
                GREEN,
                bold=True,
            )
            label(draw, (775, 541), "pg_blocking_pids()", 21, MUTED, mono=True)
    elif scene == 3:
        winner = next(r for r in data["responses"] if r["status_code"] == 201)
        label(draw, (56, 145), "3. Uma compra confirma", 49, bold=True)
        label(
            draw,
            (58, 213),
            "Depois que a barreira é liberada, uma transação vence a disputa.",
            25,
            MUTED,
        )
        steps = [
            (56, 300, "COMPRA", winner["request_id"], CYAN),
            (364, 300, "ESTOQUE", "1 → 0", WHITE),
            (672, 300, "TRANSAÇÃO", "COMMIT", GREEN),
            (980, 300, "RESPOSTA", "HTTP 201", GREEN),
        ]
        for index, (x, y, title, value, accent) in enumerate(steps):
            stage_time = 0.7 + index * 1.45
            stage_enter = ease_out((local_seconds - stage_time) / 0.75)
            if stage_enter <= 0:
                continue
            animated_y = int(y + 45 * (1 - stage_enter))
            box(draw, (x, animated_y, x + 244, animated_y + 154), outline=accent)
            centered_label(
                draw, (x, animated_y + 18, x + 244, animated_y + 53), title, 16, MUTED
            )
            centered_label(
                draw,
                (x, animated_y + 61, x + 244, animated_y + 127),
                value,
                28,
                accent,
                bold=True,
            )
            if index < len(steps) - 1 and local_seconds >= stage_time + 0.65:
                arrow_width = int(
                    44 * ease_out((local_seconds - stage_time - 0.65) / 0.55)
                )
                draw.line(
                    (x + 250, y + 77, x + 250 + arrow_width, y + 77), fill=CYAN, width=3
                )
                if arrow_width >= 42:
                    draw.polygon(
                        ((x + 294, y + 77), (x + 283, y + 69), (x + 283, y + 85)),
                        fill=CYAN,
                    )
        if local_seconds >= 6.4:
            result_y = int(536 - 30 * ease_out((local_seconds - 6.4) / 0.7))
            centered_label(
                draw,
                (56, result_y, 1224, result_y + 66),
                "1 venda · 1 item · 1 movimentação de saída",
                29,
                GREEN,
                bold=True,
            )
    elif scene == 4:
        rejected = next(r for r in data["responses"] if r["status_code"] == 422)
        label(draw, (56, 145), "4. A outra compra é recusada", 49, bold=True)
        label(
            draw,
            (58, 213),
            "Ela continua depois do commit e enxerga o saldo atualizado: zero.",
            25,
            MUTED,
        )
        steps = [
            (56, 300, "COMPRA", rejected["request_id"], CYAN),
            (364, 300, "ESTOQUE", "0", WHITE),
            (672, 300, "TRANSAÇÃO", "ROLLBACK", AMBER),
            (980, 300, "RESPOSTA", "HTTP 422", AMBER),
        ]
        for index, (x, y, title, value, accent) in enumerate(steps):
            stage_time = 0.7 + index * 1.45
            stage_enter = ease_out((local_seconds - stage_time) / 0.75)
            if stage_enter <= 0:
                continue
            animated_y = int(y + 45 * (1 - stage_enter))
            box(draw, (x, animated_y, x + 244, animated_y + 154), outline=accent)
            centered_label(
                draw, (x, animated_y + 18, x + 244, animated_y + 53), title, 16, MUTED
            )
            centered_label(
                draw,
                (x, animated_y + 61, x + 244, animated_y + 127),
                value,
                27,
                accent,
                bold=True,
            )
            if index < len(steps) - 1 and local_seconds >= stage_time + 0.65:
                arrow_width = int(
                    44 * ease_out((local_seconds - stage_time - 0.65) / 0.55)
                )
                draw.line(
                    (x + 250, y + 77, x + 250 + arrow_width, y + 77), fill=CYAN, width=3
                )
                if arrow_width >= 42:
                    draw.polygon(
                        ((x + 294, y + 77), (x + 283, y + 69), (x + 283, y + 85)),
                        fill=CYAN,
                    )
        if local_seconds >= 6.4:
            result_y = int(536 - 30 * ease_out((local_seconds - 6.4) / 0.7))
            centered_label(
                draw,
                (56, result_y, 1224, result_y + 66),
                "Nenhuma segunda venda foi gravada",
                31,
                GREEN,
                bold=True,
            )
    else:
        label(draw, (56, 145), "5. O trace prova o caminho", 49, bold=True)
        label(
            draw,
            (58, 210),
            "O mesmo request_id acompanha a requisição de ponta a ponta.",
            25,
            MUTED,
        )
        trace_steps = ["ENDPOINT", "AUTH", "RBAC", "LOCK", "COMMIT"]
        for index, value in enumerate(trace_steps):
            x = 56 + index * 238
            stage_time = 0.7 + index * 0.95
            stage_enter = ease_out((local_seconds - stage_time) / 0.65)
            if stage_enter <= 0:
                continue
            animated_y = int(342 - 40 * stage_enter)
            box(
                draw,
                (x, animated_y, x + 190, animated_y + 100),
                fill="#15243a",
                outline=CYAN,
            )
            centered_label(
                draw,
                (x, animated_y, x + 190, animated_y + 100),
                value,
                22,
                CYAN,
                mono=True,
                bold=True,
            )
            if index < len(trace_steps) - 1 and local_seconds >= stage_time + 0.55:
                arrow_width = int(
                    32 * ease_out((local_seconds - stage_time - 0.55) / 0.45)
                )
                draw.line(
                    (x + 194, 352, x + 194 + arrow_width, 352), fill=CYAN, width=3
                )
                if arrow_width >= 30:
                    draw.polygon(
                        ((x + 226, 352), (x + 217, 345), (x + 217, 359)), fill=CYAN
                    )
        if local_seconds >= 4.8:
            centered_label(
                draw,
                (56, 439, 1224, 490),
                "request_id: correlação sem expor cliente ou tenant",
                23,
                MUTED,
                mono=True,
            )
        if local_seconds >= 6.0:
            result_enter = ease_out((local_seconds - 6.0) / 0.9)
            result_y = int(590 - 72 * result_enter)
            box(
                draw, (56, result_y, 1224, result_y + 66), fill="#10293a", outline=GREEN
            )
            centered_label(
                draw,
                (56, result_y, 1224, result_y + 66),
                "RESULTADO: 1 venda · estoque 0 · nenhuma duplicidade",
                29,
                GREEN,
                bold=True,
            )

    draw.line((56, 627, 1224, 627), fill=LINE, width=1)
    label(
        draw,
        (56, 644),
        "Execução real no CI · demonstração narrada com dados fictícios",
        17,
        MUTED,
    )
    label(
        draw,
        (56, 674),
        f"PostgreSQL {data['postgres_version']} · commit {data['commit'][:7]}",
        15,
        MUTED,
        mono=True,
    )
    label(draw, (1080, 647), f"{int(seconds):02d} / {DURATION}s", 17, CYAN, mono=True)
    draw.rectangle((0, 714, int(WIDTH * seconds / DURATION), 720), fill=CYAN)
    return canvas


def trace_svg(data):
    spans = successful_spans(data)
    start = min(s["start_ms"] for s in spans)
    duration = max(s["start_ms"] + s["duration_ms"] for s in spans) - start
    height = 160 + len(spans) * 38
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" '
        f'viewBox="0 0 1100 {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Trace real de uma venda StockFlow no PostgreSQL</title>',
        '<desc id="desc">Spans da requisição que confirmou o commit, '
        "exportados de teste com dados fictícios. "
        "A duração inclui uma barreira de bloqueio controlada.</desc>",
        f'<rect width="1100" height="{height}" rx="16" fill="{BG}"/>',
        f'<g fill="{WHITE}" font-family="monospace" font-size="16">',
        '<text x="28" y="38" font-size="24">StockFlow / trace real de uma venda</text>',
        f'<text x="28" y="70" fill="{MUTED}">'
        f"PostgreSQL {escape(data['postgres_version'])} "
        f"· commit {escape(data['commit'][:7])} · request_id: "
        f"{escape(spans[0]['attributes']['request.id'])}</text>",
    ]
    for index, span in enumerate(spans):
        y = 108 + index * 38
        x = 574 + 490 * (span["start_ms"] - start) / duration
        width = max(3, 490 * span["duration_ms"] / duration)
        elements.extend(
            [
                f'<text x="28" y="{y}">{escape(span["name"])}</text>',
                f'<text x="435" y="{y}" fill="{MUTED}">'
                f"{span['duration_ms']:.2f} ms</text>",
                f'<rect x="{x:.1f}" y="{y - 13}" width="{width:.1f}" height="15" '
                f'rx="3" fill="{CYAN}"/>',
            ]
        )
    elements.append(
        f'<text x="28" y="{height - 24}" fill="{MUTED}">'
        "A espera inclui o bloqueio criado pelo teste. "
        "Não é benchmark.</text></g></svg>"
    )
    return "\n".join(elements) + "\n"


def validate(data):
    expected = {
        "data_kind": "synthetic",
        "blocked_connections": 2,
        "initial_stock": 1,
        "final_stock": 0,
        "persisted_sales": 1,
        "persisted_items": 1,
        "sale_stock_movements": 1,
        "isolation": "read committed",
    }
    if any(data.get(key) != value for key, value in expected.items()):
        raise ValueError("Synthetic evidence invariants failed; refusing to build")
    if sorted(r["status_code"] for r in data["responses"]) != [201, 422]:
        raise ValueError("Unexpected HTTP results")
    for name in ("sales.transaction.commit", "sales.transaction.rollback"):
        if sum(s["name"] == name for s in data["spans"]) != 1:
            raise ValueError("Missing transaction span evidence")
    forbidden = {
        "tenant.id",
        "tenant_id",
        "user.id",
        "customer.name",
        "product.id",
        "db.statement",
        "db.query.text",
        "http.request.header.authorization",
    }
    if any(forbidden.intersection(s["attributes"]) for s in data["spans"]):
        raise ValueError("Sensitive attributes in evidence")


def vtt_timestamp(seconds: int) -> str:
    minutes, remaining = divmod(seconds, 60)
    return f"00:{minutes:02d}:{remaining:02d}.000"


def build(evidence: Path, output: Path, *, video: bool = True):
    data = json.loads(evidence.read_text(encoding="utf-8"))
    validate(data)
    output.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "demo").iterdir():
        if source.is_file() and source.name != "narration.pt-BR.m4a":
            shutil.copy2(source, output / source.name)
    raw = evidence.read_bytes()
    (output / "evidence.json").write_bytes(raw)
    (output / "evidence.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    (output / "trace-example.svg").write_text(trace_svg(data), encoding="utf-8")
    frame(data, 2).save(output / "poster.jpg", quality=94)
    captions = (
        "WEBVTT\n\n"
        + "\n\n".join(
            f"{vtt_timestamp(i * SCENE_DURATION)} --> "
            f"{vtt_timestamp((i + 1) * SCENE_DURATION)}\n{caption}"
            for i, caption in enumerate(CAPTIONS)
        )
        + "\n"
    )
    (output / "captions.pt-BR.vtt").write_text(captions, encoding="utf-8")
    if video:
        narration = ROOT / "demo" / "narration.pt-BR.m4a"
        if not narration.is_file():
            raise FileNotFoundError("Missing Portuguese narration asset")
        writer = imageio_ffmpeg.write_frames(
            str(output / "stockflow-demo.mp4"),
            (WIDTH, HEIGHT),
            fps=FPS,
            codec="libx264",
            quality=8,
            macro_block_size=16,
            output_params=["-movflags", "+faststart"],
            audio_path=str(narration),
            audio_codec="aac",
            ffmpeg_log_level="error",
        )
        writer.send(None)
        try:
            for number in range(FPS * DURATION):
                writer.send(frame(data, number / FPS).tobytes())
        finally:
            writer.close()
    print(f"Demo built from commit {data['commit']} at {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "site")
    parser.add_argument("--skip-video", action="store_true")
    args = parser.parse_args()
    build(args.evidence, args.output_dir, video=not args.skip_video)


if __name__ == "__main__":
    main()
