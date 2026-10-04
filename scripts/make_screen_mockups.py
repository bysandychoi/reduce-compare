#!/usr/bin/env python3
"""T147 상관관계 분석 예시 화면(목업)을 실제 계산값으로 생성한다."""
from __future__ import annotations

import html
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.metrics import correlation_metrics
from app.core.network import correlation_network
from app.core.relationships import classify_relationships, rank_correlation_pairs

COLUMNS = ["방문", "구매", "광고", "가격", "재고", "리뷰"]
THRESHOLD = .5


def calculate():
    rng = np.random.default_rng(147)
    n = 900
    visit, ad, stock = rng.normal(size=(3, n))
    original = pd.DataFrame({
        "방문": visit, "구매": .78 * visit + .48 * rng.normal(size=n),
        "광고": ad, "가격": -.62 * visit + .7 * rng.normal(size=n),
        "재고": stock, "리뷰": .55 * visit + .38 * ad + .65 * rng.normal(size=n),
    })
    pool = original[(original["방문"].abs() < 1.05) | (original["광고"] > .8)]
    reduced = pool.sample(110, random_state=147).reset_index(drop=True)
    metrics = correlation_metrics(original, reduced, [], COLUMNS, "pearson")
    ranked = rank_correlation_pairs(metrics)
    classified = classify_relationships(metrics, THRESHOLD)
    networks = {
        "original": correlation_network(COLUMNS, metrics["matrix_original"], THRESHOLD),
        "reduced": correlation_network(COLUMNS, metrics["matrix_reduced"], THRESHOLD),
    }
    return original, reduced, metrics, ranked, classified, networks


def positions():
    return {name: (210 + 135 * math.cos(-math.pi / 2 + i * math.tau / len(COLUMNS)),
                   190 + 135 * math.sin(-math.pi / 2 + i * math.tau / len(COLUMNS)))
            for i, name in enumerate(COLUMNS)}


def scatter_points(original, reduced, pair):
    a, b = pair["column_a"], pair["column_b"]
    source = original[[a, b]].sample(70, random_state=147)
    sample = reduced[[a, b]].sample(min(35, len(reduced)), random_state=147)
    both = pd.concat([source, sample])
    low, high = both.min(), both.max()
    span = (high - low).replace(0, 1)
    convert = lambda frame: [[round(35 + (row[a] - low[a]) / span[a] * 1070, 1),
                              round(130 - (row[b] - low[b]) / span[b] * 105, 1)]
                             for _, row in frame.iterrows()]
    return {"original": convert(source), "reduced": convert(sample)}


def network_svg(graph, other):
    pos = positions()
    other_pairs = {tuple(sorted((e["source"], e["target"]))) for e in other["edges"]}
    lines = []
    for edge in graph["edges"]:
        a, b = pos[edge["source"]], pos[edge["target"]]
        pair = tuple(sorted((edge["source"], edge["target"])))
        color = "#b33939" if edge["correlation"] > 0 else "#2673a8"
        dash = ' stroke-dasharray="7 5"' if pair not in other_pairs else ""
        lines.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="{color}" stroke-width="{1.5+edge["weight"]*4:.1f}"{dash}/>')
    nodes = [f'<g transform="translate({x:.1f} {y:.1f})"><circle r="25"/><text>{html.escape(name)}</text></g>'
             for name, (x, y) in pos.items()]
    return '<svg viewBox="0 0 420 380">' + "".join(lines + nodes) + "</svg>"


def render_html(payload):
    m, ranks, rel, nets = payload["metrics"], payload["ranked"], payload["classified"], payload["networks"]
    counts = rel["counts"]
    pair_rows = "".join(
        f'<li><b>{i+1}</b><span>{html.escape(p["column_a"])} × {html.escape(p["column_b"])}</span>'
        f'<strong>{p["difference"]:+.2f}</strong></li>' for i, p in enumerate(ranks["pairs"][:4]))
    chosen = ranks["pairs"][0]
    style = """*{box-sizing:border-box}body{margin:0;background:#eef3f6;color:#17212b;font:14px "Malgun Gothic",sans-serif}.page{width:min(1180px,calc(100% - 32px));margin:24px auto}.top{display:flex;justify-content:space-between;align-items:end}.tag{color:#a04b3f;font-weight:700}.tabs{display:flex;gap:6px;margin:18px 0}.tabs span{padding:7px 12px;border:1px solid #d8e0e7;border-radius:9px;background:white}.tabs .on{background:#173b57;color:white}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card,.panel{background:white;border:1px solid #d8e0e7;border-radius:13px;padding:16px}.card small{color:#66727e}.card b{display:block;margin-top:5px;font-size:24px;color:#173b57}.grid{display:grid;grid-template-columns:1fr 1fr .8fr;gap:12px;margin-top:12px}.panel h2{font-size:15px;margin:0}.panel p{color:#66727e;font-size:11px}.panel svg{width:100%;height:300px}.panel line{opacity:.8}.panel circle{fill:white;stroke:#176b9b;stroke-width:2.5}.panel text{text-anchor:middle;dominant-baseline:middle;font-size:11px;font-weight:700}.ranking{list-style:none;padding:0}.ranking li{display:grid;grid-template-columns:22px 1fr auto;gap:8px;padding:13px 0;border-bottom:1px solid #e5e9ed}.scatter{margin-top:12px}.scatter svg circle.orig{fill:#7c8794;opacity:.45}.scatter svg circle.red{fill:#176b9b;opacity:.8}.note{color:#66727e;font-size:12px}@media(max-width:760px){.cards,.grid{grid-template-columns:1fr}.top{align-items:start;flex-direction:column}.panel svg{height:auto}}"""
    scatter = "".join(f'<circle class="orig" cx="{x}" cy="{y}" r="3"/>' for x, y in payload["scatter"]["original"])
    scatter += "".join(f'<circle class="red" cx="{x}" cy="{y}" r="4"/>' for x, y in payload["scatter"]["reduced"])
    return f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>상관관계 분석 목업</title><style>{style}</style><main class="page"><header class="top"><div><small>상관관계 보존</small><h1>원본과 축소본의 관계 비교</h1></div><span class="tag">예시 화면(목업) · 합성 데이터</span></header><div class="tabs"><span class="on">Pearson</span><span>Spearman</span><span>|r| ≥ {THRESHOLD:.2f}</span></div><section class="cards"><div class="card"><small>상관 보존 점수</small><b>{m["score"]:.1f}</b></div><div class="card"><small>유지 관계</small><b>{counts["maintained"]}</b></div><div class="card"><small>사라진 관계</small><b>{counts["lost"]}</b></div><div class="card"><small>새 관계</small><b>{counts["new"]}</b></div></section><section class="grid"><article class="panel"><h2>원본 네트워크</h2><p>노드 {len(nets["original"]["nodes"])} · 엣지 {len(nets["original"]["edges"])}</p>{network_svg(nets["original"],nets["reduced"])}</article><article class="panel"><h2>축소본 네트워크</h2><p>점선은 한쪽에만 있는 관계</p>{network_svg(nets["reduced"],nets["original"])}</article><aside class="panel"><h2>차이 큰 관계</h2><ol class="ranking">{pair_rows}</ol></aside></section><section class="panel scatter"><h2>선택 쌍 산점도 · {html.escape(chosen["column_a"])} × {html.escape(chosen["column_b"])}</h2><p>원본 회색 · 축소본 파랑 · 실제 앱이 아닌 화면 설계 목업</p><svg viewBox="0 0 1140 150">{scatter}</svg></section><p class="note">고정 seed 합성 데이터 900행을 110행으로 실제 표본 축소하고 핵심 상관 함수로 계산했습니다.</p></main></html>"""


def render_png(payload, path, font_path):
    m, rel, nets = payload["metrics"], payload["classified"], payload["networks"]
    im = Image.new("RGB", (1200, 750), "#eef3f6"); d = ImageDraw.Draw(im)
    f = ImageFont.truetype(font_path, 13); b = ImageFont.truetype(font_path, 18)
    d.text((35, 24), "상관관계 분석 · 예시 화면(목업)", font=b, fill="#17212b")
    d.text((940, 28), "합성 데이터 · 실제 계산", font=f, fill="#a04b3f")
    for i,(label,active) in enumerate([("Pearson",True),("Spearman",False),(f"|r| ≥ {THRESHOLD:.2f}",False)]):
        x=35+i*105; d.rounded_rectangle((x,54,x+95,82),8,fill="#173b57" if active else "white",outline="#d8e0e7")
        d.text((x+12,60),label,font=f,fill="white" if active else "#17212b")
    cards = [("상관 보존 점수", m["score"]), ("유지 관계", rel["counts"]["maintained"]), ("사라진 관계", rel["counts"]["lost"]), ("새 관계", rel["counts"]["new"])]
    for i, (label, value) in enumerate(cards):
        x=35+i*285; d.rounded_rectangle((x,92,x+265,159),12,fill="white",outline="#d8e0e7"); d.text((x+14,105),label,font=f,fill="#66727e"); d.text((x+14,128),str(value),font=b,fill="#173b57")
    pos=positions()
    for col,(x0,title,key) in enumerate([(35,"원본 네트워크","original"),(430,"축소본 네트워크","reduced")]):
        d.rounded_rectangle((x0,177,x0+375,527),12,fill="white",outline="#d8e0e7"); d.text((x0+15,192),title,font=b,fill="#17212b")
        graph=nets[key]
        for e in graph["edges"]:
            a,bp=pos[e["source"]],pos[e["target"]]; color="#b33939" if e["correlation"]>0 else "#2673a8"
            d.line((x0+a[0]-20,a[1]+132,x0+bp[0]-20,bp[1]+132),fill=color,width=max(2,int(1+e["weight"]*4)))
        for name,(x,y) in pos.items():
            px,py=x0+x-20,y+132; d.ellipse((px-23,py-23,px+23,py+23),fill="white",outline="#176b9b",width=3); d.text((px-15,py-8),name,font=f,fill="#17212b")
    d.rounded_rectangle((825,177,1165,527),12,fill="white",outline="#d8e0e7"); d.text((842,192),"차이 큰 관계",font=b,fill="#17212b")
    for i,p in enumerate(payload["ranked"]["pairs"][:4]): d.text((842,242+i*55),f'{i+1}. {p["column_a"]} × {p["column_b"]}  {p["difference"]:+.2f}',font=f,fill="#17212b")
    d.rounded_rectangle((35,547,1165,722),12,fill="white",outline="#d8e0e7"); d.text((52,564),"선택 쌍 산점도 · 원본 회색 / 축소본 파랑",font=b,fill="#17212b")
    for x,y in payload["scatter"]["original"]: d.ellipse((x+35,y+552,x+41,y+558),fill="#7c8794")
    for x,y in payload["scatter"]["reduced"]: d.ellipse((x+35,y+552,x+43,y+560),fill="#176b9b")
    im.save(path)


def main():
    original, reduced, metrics, ranked, classified, networks = calculate()
    payload={"metrics":metrics,"ranked":ranked,"classified":classified,"networks":networks,
             "scatter":scatter_points(original,reduced,ranked["pairs"][0])}
    out=ROOT/"docs/images/screens"; public=ROOT/"frontend/public/samples"
    out.mkdir(parents=True,exist_ok=True); public.mkdir(parents=True,exist_ok=True)
    page=render_html(payload)
    (out/"correlation-analysis.html").write_text(page,encoding="utf-8")
    (public/"correlation-analysis.html").write_text(page,encoding="utf-8")
    render_png(payload,out/"correlation-analysis.png",r"C:\Windows\Fonts\malgun.ttf")
    (out/"correlation-analysis.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"원본 {len(original)}행 → 축소본 {len(reduced)}행 · 점수 {metrics['score']}")


if __name__ == "__main__":
    main()
