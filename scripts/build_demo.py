"""Build a static, explicitly recorded demo and video from real synthetic CI evidence.

No browser capture is fabricated: the video is a motion graphic of captured spans
and verified database assertions. No live API or production data is accessed.
"""

import argparse
import hashlib
import json
import shutil
from html import escape
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, FPS, DURATION = 1280, 720, 24, 40
BG, PANEL, LINE = "#080f1d", "#111e32", "#26384e"
WHITE, MUTED, CYAN, GREEN, AMBER = (
    "#eff5ff",
    "#a9b9cf",
    "#62deed",
    "#81ecc3",
    "#ffcd87",
)
CAPTIONS = [
    "Duas compras disputam a última unidade. "
    "Esta é uma execução real com dados fictícios.",
    "O teste confirma duas conexões esperando pelo bloqueio de linha no PostgreSQL.",
    "Uma compra confirma o commit. A outra faz rollback. O estoque termina em zero.",
    "O request_id conecta autenticação, RBAC, consulta, bloqueio e transação no trace.",
    "Uma venda, um item e uma saída de estoque. "
    "Evidências e testes disponíveis no GitHub.",
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


def box(draw, rect, fill=PANEL, outline=LINE):
    draw.rounded_rectangle(rect, radius=14, fill=fill, outline=outline, width=1)


def successful_spans(data):
    request_id = next(
        r["request_id"] for r in data["responses"] if r["status_code"] == 201
    )
    return [s for s in data["spans"] if s["attributes"]["request.id"] == request_id]


def frame(data, seconds):
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(canvas)
    scene = min(4, int(seconds // 8))
    phase = min(1, (seconds % 8) / 1.5)
    label(draw, (56, 35), "STOCKFLOW", 22, CYAN, bold=True)
    label(draw, (225, 39), "/ ENGENHARIA DE BACKEND", 15, MUTED, mono=True)
    label(draw, (907, 39), "DADOS FICTÍCIOS · CI REAL", 15, GREEN)
    draw.line((56, 81, 1224, 81), fill=LINE, width=1)
    label(draw, (56, 106), f"0{scene + 1} / 05", 16, CYAN, mono=True)

    if scene == 0:
        label(draw, (56, 153), "2 compras. 1 unidade.", 68, bold=True)
        label(
            draw,
            (59, 248),
            "O estoque precisa continuar correto sob concorrência.",
            27,
            MUTED,
        )
        for index, title in enumerate(("COMPRA A", "COMPRA B")):
            x = 56 + index * 590
            box(draw, (x, 325, x + 558, 540))
            label(draw, (x + 28, 350), title, 18, CYAN, mono=True)
            label(draw, (x + 28, 391), "POST /api/v1/sales", 27, mono=True)
            label(draw, (x + 28, 446), "Quantidade: 1", 28)
            draw.rounded_rectangle(
                (x + 28, 500, x + 28 + 490 * phase, 505), radius=2, fill=CYAN
            )
        label(draw, (59, 561), "FastAPI → SQLAlchemy async → PostgreSQL", 23, MUTED)
    elif scene == 1:
        label(draw, (56, 149), "Disputa observada no banco.", 51, bold=True)
        label(
            draw,
            (58, 224),
            "Duas conexões independentes. Nenhuma sessão compartilhada.",
            25,
            MUTED,
        )
        box(draw, (56, 296, 790, 570))
        label(draw, (83, 322), "SELECT ... FROM products", 29, mono=True)
        label(draw, (83, 370), "ORDER BY id FOR UPDATE", 29, CYAN, mono=True)
        label(
            draw,
            (83, 449),
            "pg_blocking_pids(pid) → bloqueio confirmado",
            22,
            GREEN,
            mono=True,
        )
        label(draw, (83, 502), "wait_event_type = 'Lock'", 22, MUTED, mono=True)
        box(draw, (820, 296, 1224, 570))
        label(draw, (858, 320), "CONEXÕES EM ESPERA", 18, MUTED)
        label(draw, (935, 364), data["blocked_connections"], 99, CYAN, bold=True)
        label(draw, (854, 517), "Barreira liberada pelo teste", 21, MUTED)
    elif scene == 2:
        label(draw, (56, 149), "Um commit. Um rollback.", 57, bold=True)
        label(
            draw,
            (59, 232),
            "A segunda transação lê o saldo atualizado e rejeita a compra.",
            25,
            MUTED,
        )
        for index, result in enumerate(data["responses"]):
            x = 56 + index * 590
            good = result["status_code"] == 201
            accent = GREEN if good else AMBER
            box(draw, (x, 305, x + 558, 530))
            label(draw, (x + 25, 329), result["request_id"], 20, MUTED, mono=True)
            label(
                draw,
                (x + 25, 366),
                f"HTTP {result['status_code']}",
                55,
                accent,
                bold=True,
            )
            label(
                draw,
                (x + 25, 450),
                "Venda confirmada" if good else "Estoque insuficiente",
                26,
            )
        label(
            draw,
            (58, 561),
            "Saldo final: 0    /    Vendas: 1    /    Saídas de estoque: 1",
            26,
            GREEN,
        )
    elif scene == 3:
        label(draw, (56, 144), "Do endpoint até o commit.", 51, bold=True)
        spans = successful_spans(data)
        chosen = [
            s
            for s in spans
            if s["name"]
            in {
                "POST /api/v1/sales",
                "auth.authenticate",
                "auth.rbac",
                "sales.transaction",
                "sales.stock.lock",
                "sales.persist",
                "sales.transaction.commit",
            }
        ]
        start = min(s["start_ms"] for s in spans)
        duration = max(s["start_ms"] + s["duration_ms"] for s in spans) - start
        for index, span in enumerate(chosen):
            y = 245 + index * 43
            label(draw, (59, y), span["name"], 22, WHITE, mono=True)
            label(draw, (465, y), f"{span['duration_ms']:.2f} ms", 19, MUTED, mono=True)
            draw.rounded_rectangle((626, y + 8, 1218, y + 25), radius=4, fill=PANEL)
            x = 626 + 585 * (span["start_ms"] - start) / duration
            width = max(3, 585 * span["duration_ms"] / duration * phase)
            draw.rounded_rectangle(
                (x, y + 8, min(1218, x + width), y + 25), radius=3, fill=CYAN
            )
        label(
            draw,
            (59, 570),
            "Tempos reais incluem a barreira do teste; não são benchmark.",
            21,
            MUTED,
        )
    else:
        label(draw, (56, 148), "A evidência acompanha o código.", 49, bold=True)
        checks = [
            "Uma única venda e um único item persistidos",
            "Estoque final zero, sem baixa duplicada",
            "Commit e rollback no trace, com request_id",
            "Métricas sem tenant ou dados pessoais",
        ]
        for index, value in enumerate(checks):
            y = 259 + index * 60
            draw.line([(60, y + 19), (68, y + 27), (84, y + 9)], fill=GREEN, width=3)
            label(draw, (108, y), value, 27)
        label(
            draw,
            (59, 548),
            "github.com/jhonwictordev/stockflow-api",
            27,
            CYAN,
            mono=True,
        )

    draw.line((56, 627, 1224, 627), fill=LINE, width=1)
    label(
        draw,
        (56, 644),
        "Visualização de uma execução capturada · sem API pública nesta página",
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
    label(draw, (1090, 647), f"{int(seconds):02d} / 40s", 17, CYAN, mono=True)
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


def build(evidence: Path, output: Path, *, video: bool = True):
    data = json.loads(evidence.read_text(encoding="utf-8"))
    validate(data)
    output.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "demo").iterdir():
        if source.is_file():
            shutil.copy2(source, output / source.name)
    raw = evidence.read_bytes()
    (output / "evidence.json").write_bytes(raw)
    (output / "evidence.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    (output / "trace-example.svg").write_text(trace_svg(data), encoding="utf-8")
    frame(data, 2).save(output / "poster.jpg", quality=94)
    captions = (
        "WEBVTT\n\n"
        + "\n\n".join(
            f"00:00:{i * 8:02d}.000 --> 00:00:{(i + 1) * 8:02d}.000\n{caption}"
            for i, caption in enumerate(CAPTIONS)
        )
        + "\n"
    )
    (output / "captions.pt-BR.vtt").write_text(captions, encoding="utf-8")
    if video:
        writer = imageio_ffmpeg.write_frames(
            str(output / "stockflow-demo.mp4"),
            (WIDTH, HEIGHT),
            fps=FPS,
            codec="libx264",
            quality=8,
            macro_block_size=16,
            output_params=["-movflags", "+faststart"],
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
