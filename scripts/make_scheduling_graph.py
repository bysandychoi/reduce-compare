#!/usr/bin/env python3
"""T320 합성 scheduling 데이터를 대화형 관계 그래프로 생성한다."""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_scheduling_mockup import DATA

WIDTH, HEIGHT = 1500, 960


def graph_data() -> dict:
    lot = DATA["lot"]
    equipment = DATA["equipment"]
    nodes = [{"id": lot["id"], "kind": "lot", "label": lot["id"],
              "detail": f'{lot["product"]} · {lot["operation"]} · {lot["quantity"]:,} wafers',
              "warning": False}]
    edges = []
    resource_map = {}
    spec_rows = []
    for index, machine in enumerate(equipment):
        machine_id = machine["id"]
        nodes.append({"id": machine_id, "kind": "equipment", "label": machine_id,
                      "detail": f'{machine["fit"]} · {machine["state"]}',
                      "warning": machine["fit"] == "조건부"})
        edges.append({"source": lot["id"], "target": machine_id})
        for resource_id, value, shared in machine["resources"]:
            resource_map.setdefault(resource_id, {
                "id": resource_id, "kind": "resource", "label": resource_id,
                "detail": value, "shared": shared, "warning": False,
            })
            edges.append({"source": machine_id, "target": resource_id})
        for resource_id, name, required, actual, ok in machine["specs"]:
            spec_id = f'spec:{machine_id}:{resource_id}:{name}'
            label = f'{name} · {machine_id}'
            detail = f'{resource_id} · 요구 {required} · 현재 {actual}'
            nodes.append({"id": spec_id, "kind": "spec", "label": label,
                          "detail": detail, "warning": not ok, "resource": resource_id})
            edges.append({"source": resource_id, "target": spec_id})
            spec_rows.append({"equipment_index": index, "node_id": spec_id})
    nodes.extend(resource_map.values())
    for edge in edges:
        if not any(node["id"] == edge["source"] for node in nodes):
            raise ValueError(f'연결되지 않은 source node: {edge["source"]}')
        if not any(node["id"] == edge["target"] for node in nodes):
            raise ValueError(f'연결되지 않은 target node: {edge["target"]}')
    return {"lot": lot, "nodes": nodes, "edges": edges,
            "equipment": equipment, "spec_rows": spec_rows}


def layout(data: dict) -> dict[str, tuple[float, float]]:
    equipment = data["equipment"]
    resources = list(dict.fromkeys(
        item[0] for machine in equipment for item in machine["resources"]
    ))
    specs = [row["id"] for row in data["nodes"] if row["kind"] == "spec"]
    positions = {data["lot"]["id"]: (150, HEIGHT / 2)}
    positions.update({item["id"]: (410, 230 + i * 250)
                      for i, item in enumerate(equipment)})
    positions.update({name: (800, 150 + i * 95)
                      for i, name in enumerate(resources)})
    positions.update({name: (1250, 150 + i * 82) for i, name in enumerate(specs)})
    return positions


def svg_nodes(data: dict, positions: dict) -> str:
    widths = {"lot": 220, "equipment": 230, "resource": 245, "spec": 260}
    heights = {"lot": 92, "equipment": 96, "resource": 68, "spec": 62}
    chunks = []
    for node in data["nodes"]:
        x, y = positions[node["id"]]
        width, height = widths[node["kind"]], heights[node["kind"]]
        title = html.escape(node["label"] + " · " + node["detail"], quote=True)
        label = html.escape(node["label"])
        detail = html.escape(node["detail"])
        warning = " warning" if node["warning"] else ""
        chunks.append(
            f'<g class="node {node["kind"]}{warning}" data-id="{html.escape(node["id"], quote=True)}" '
            f'tabindex="0" role="button" aria-label="{title}" transform="translate({x-width/2:.1f} {y-height/2:.1f})">'
            f'<title>{title}</title><rect width="{width}" height="{height}" rx="11"/>'
            f'<text class="node-label" x="12" y="25">{label}</text>'
            f'<text class="node-detail" x="12" y="49">{detail}</text></g>'
        )
    return "".join(chunks)


def html_page(data: dict, positions: dict) -> str:
    encoded = json.dumps(data, ensure_ascii=False).replace("</", r"<\/")
    edges = "".join(
        f'<line class="edge" data-source="{html.escape(edge["source"], quote=True)}" '
        f'data-target="{html.escape(edge["target"], quote=True)}" '
        f'x1="{positions[edge["source"]][0]:.1f}" y1="{positions[edge["source"]][1]:.1f}" '
        f'x2="{positions[edge["target"]][0]:.1f}" y2="{positions[edge["target"]][1]:.1f}"/>'
        for edge in data["edges"]
    )
    script = """const D=JSON.parse(document.querySelector('#graph-data').textContent);
const svg=document.querySelector('#network'),status=document.querySelector('#selection');
function select(id){if(svg.dataset.selected===id){id='';delete svg.dataset.selected}else if(id){svg.dataset.selected=id}
const edges=[...svg.querySelectorAll('.edge')],nodes=[...svg.querySelectorAll('.node')],up=new Set(id?[id]:[]),down=new Set(id?[id]:[]);
let changed=true;while(changed){changed=false;for(const e of edges){const a=e.dataset.source,b=e.dataset.target;
if(up.has(b)&&!up.has(a)){up.add(a);changed=true}if(down.has(a)&&!down.has(b)){down.add(b);changed=true}}}
const active=new Set([...up,...down]);
edges.forEach(e=>{const on=active.has(e.dataset.source)&&active.has(e.dataset.target);e.classList.toggle('active',!!id&&on);e.classList.toggle('dim',!!id&&!on)});
nodes.forEach(n=>{const on=active.has(n.dataset.id);n.classList.toggle('active',!!id&&on);n.classList.toggle('dim',!!id&&!on)});
status.textContent=id?'강조 경로: '+id+' · 빈 곳 또는 선택 해제로 초기화':'전체 관계 표시'}
svg.querySelectorAll('.node').forEach(n=>{n.addEventListener('click',()=>select(n.dataset.id));
n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(n.dataset.id)}})});
document.querySelector('#reset').addEventListener('click',()=>select(''));"""
    style = """*{box-sizing:border-box}body{margin:0;background:#eef3f6;color:#17212b;font:14px "Malgun Gothic",sans-serif}.page{width:min(1500px,calc(100% - 28px));margin:22px auto}.head{display:flex;align-items:end;justify-content:space-between;gap:16px}.head h1{margin:4px 0}.sample{color:#a13b2d;font-weight:700}.summary,.toolbar,.legend{padding:13px 16px;border:1px solid #d8e0e7;border-radius:12px;background:white}.summary{margin-top:14px;background:#173b57;color:white}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:10px}.toolbar p{margin:0;color:#66727e}button{padding:8px 12px;border:1px solid #cbd7e0;border-radius:8px;background:white;color:#173b57;font:inherit;cursor:pointer}button:focus-visible,.node:focus-visible{outline:3px solid #dfa83c;outline-offset:3px}.canvas{margin-top:10px;overflow:auto;border:1px solid #d8e0e7;border-radius:13px;background:#fff}.canvas svg{display:block;width:100%;min-width:1050px;height:auto}.edge{stroke:#9aafbf;stroke-width:2.4;opacity:.78;transition:opacity .15s,stroke-width .15s}.edge.active{stroke:#176b9b;stroke-width:4.5;opacity:1}.edge.dim,.node.dim{opacity:.14}.node{cursor:pointer;transition:opacity .15s}.node rect{stroke:#b8c9d6;stroke-width:2;fill:#fff}.node.lot rect{fill:#173b57;stroke:#173b57}.node.resource rect{fill:#e8f0f8}.node.warning rect{fill:#fff0ed;stroke:#cf7568}.node.active rect{stroke:#176b9b;stroke-width:4;filter:drop-shadow(0 2px 5px #173b5740)}.node.warning.active rect{stroke:#a13b2d}.node-label{font-size:15px;font-weight:700;fill:#17212b}.node.lot .node-label{fill:white}.node-detail{font-size:11px;fill:#66727e}.node.warning .node-detail{fill:#a13b2d}.node.active{opacity:1!important}.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;color:#66727e;font-size:12px}.legend span{display:flex;align-items:center;gap:6px}.swatch{width:12px;height:12px;border:1px solid #b8c9d6;border-radius:3px;background:#e8f0f8}.swatch.warn{background:#fff0ed;border-color:#cf7568}.swatch.share{background:#e8f0f8;border-style:dashed}"""
    captions = "".join(
        f'<text class="column-label" x="{x}" y="48" text-anchor="middle">{label}</text>'
        for x, label in ((150, "Lot"), (410, "가능 설비"),
                         (800, "Resource · 공유 노드는 1개"), (1250, "연결 Spec"))
    )
    return f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Scheduling 관계 그래프</title><style>{style}</style><main class="page">
<header class="head"><div><small>Factory Scheduling</small><h1>Lot → 설비 → Resource → Spec</h1></div>
<b class="sample">SAMPLE · 예시 화면(목업)</b></header>
<section class="summary"><b>{html.escape(data["lot"]["id"])} · {html.escape(data["lot"]["product"])}</b> ·
{html.escape(data["lot"]["operation"])} · {data["lot"]["quantity"]:,} wafers · 납기 {html.escape(data["lot"]["due"])}
· Recipe {html.escape(data["lot"]["recipe"])}</section>
<section class="toolbar"><p id="selection" aria-live="polite">전체 관계 표시 · 노드를 클릭하거나 키보드로 선택하세요</p>
<button id="reset" type="button">강조 초기화</button></section>
<div class="canvas"><svg id="network" viewBox="0 0 {WIDTH} {HEIGHT}" role="group" aria-label="Lot에서 설비, 공유 Resource, Spec으로 이어지는 관계 그래프">
<style>.column-label{{font:700 15px "Malgun Gothic",sans-serif;fill:#173b57}}</style>
<g class="columns">{captions}</g><g class="edges">{edges}</g><g class="nodes">{svg_nodes(data, positions)}</g></svg></div>
<div class="legend"><span><i class="swatch"></i>Lot / 가능 설비</span>
<span><i class="swatch share"></i>공유 Resource는 한 노드로 합류</span>
<span><i class="swatch warn"></i>조건부 설비 또는 Spec 미충족</span>
<span>클릭/Enter/Space: 경로 강조</span></div>
<script id="graph-data" type="application/json">{encoded}</script><script>{script}</script></main></html>"""


def render_png(data: dict, positions: dict, path: Path) -> None:
    im = Image.new("RGB", (WIDTH, HEIGHT), "#ffffff")
    draw = ImageDraw.Draw(im)
    font_path = r"C:\Windows\Fonts\malgun.ttf"
    bold_path = r"C:\Windows\Fonts\malgunbd.ttf"
    small = ImageFont.truetype(font_path, 11)
    normal = ImageFont.truetype(bold_path, 14)
    title = ImageFont.truetype(bold_path, 23)
    draw.text((35, 20), "Lot → 설비 → 공유 Resource → Spec", font=title, fill="#17212b")
    draw.text((1150, 29), "SAMPLE · 예시 화면(목업)", font=small, fill="#a13b2d")
    draw.text((75, 72), "Lot", font=normal, fill="#173b57")
    draw.text((335, 72), "가능 설비", font=normal, fill="#173b57")
    draw.text((700, 72), "Resource · 공유 노드는 1개", font=normal, fill="#173b57")
    draw.text((1130, 72), "연결 Spec", font=normal, fill="#173b57")
    for edge in data["edges"]:
        draw.line((*positions[edge["source"]], *positions[edge["target"]]),
                  fill="#cf7568" if edge["target"].startswith("spec:") and
                  next(n for n in data["nodes"] if n["id"] == edge["target"])["warning"]
                  else "#9aafbf", width=2)
    sizes = {"lot": (220, 92), "equipment": (230, 96), "resource": (245, 68), "spec": (260, 62)}
    for node in data["nodes"]:
        x, y = positions[node["id"]]
        w, h = sizes[node["kind"]]
        x1, y1 = x-w/2, y-h/2
        warning = node["warning"]
        fill = "#173b57" if node["kind"] == "lot" else "#fff0ed" if warning else "#e8f0f8" if node["kind"] == "resource" else "white"
        outline = "#cf7568" if warning else "#b8c9d6"
        draw.rounded_rectangle((x1, y1, x1+w, y1+h), 10, fill=fill, outline=outline, width=2)
        text_color = "white" if node["kind"] == "lot" else "#17212b"
        detail_color = "#a13b2d" if warning else "#66727e"
        draw.text((x1+10, y1+8), node["label"], font=normal, fill=text_color)
        draw.text((x1+10, y1+33), node["detail"], font=small, fill=detail_color)
    im.save(path)


def main() -> None:
    data = graph_data()
    positions = layout(data)
    output = ROOT / "docs/images/screens"
    public = ROOT / "frontend/public/samples"
    output.mkdir(parents=True, exist_ok=True)
    public.mkdir(parents=True, exist_ok=True)
    page = html_page(data, positions)
    (output / "factory-scheduling-graph.html").write_text(page, encoding="utf-8")
    (public / "factory-scheduling-graph.html").write_text(page, encoding="utf-8")
    (output / "factory-scheduling-graph.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    render_png(data, positions, output / "factory-scheduling-graph.png")
    print(f'노드 {len(data["nodes"])}개 · 관계 {len(data["edges"])}개')


if __name__ == "__main__":
    main()
