#!/usr/bin/env python3
"""합성 Lot-설비-Resource-Spec scheduling 목업을 생성한다 (T320)."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DATA = {
    "lot": {"id": "LOT-24017", "product": "AX7", "operation": "Etch-02",
            "quantity": 1200, "due": "14:30", "priority": "HIGH", "recipe": "R-ETCH-A7"},
    "equipment": [
        {"id": "ETCH-01", "fit": "가능", "state": "Ready", "process": 34, "setup": 0,
         "resources": [["CHAMBER-A", "Ready", False], ["GAS-CF4", "44 slm", True],
                       ["GAS-N2", "84%", True], ["OPERATOR-L2", "2명", True]],
         "specs": [["CHAMBER-A", "온도", "58~62℃", "60℃", True],
                   ["CHAMBER-A", "압력", "42~48 mTorr", "45", True],
                   ["GAS-CF4", "유량", "≥40 slm", "44", True]]},
        {"id": "ETCH-03", "fit": "가능", "state": "Setup 필요", "process": 32, "setup": 18,
         "resources": [["CHAMBER-B", "Ready", False], ["GAS-CF4", "44 slm", True],
                       ["TOOL-KIT-7", "Ready", True], ["OPERATOR-L2", "2명", True]],
         "specs": [["CHAMBER-B", "온도", "58~62℃", "59℃", True],
                   ["CHAMBER-B", "압력", "42~48 mTorr", "47", True],
                   ["TOOL-KIT-7", "Tool", "KIT-7", "KIT-7", True]]},
        {"id": "ETCH-05", "fit": "조건부", "state": "CF4 보충 필요", "process": 36, "setup": 8,
         "resources": [["CHAMBER-C", "PM 17:00", False], ["GAS-CF4", "28 slm", True],
                       ["TOOL-KIT-7", "Ready", True]],
         "specs": [["CHAMBER-C", "온도", "58~62℃", "61℃", True],
                   ["CHAMBER-C", "압력", "42~48 mTorr", "46", True],
                   ["GAS-CF4", "유량", "≥40 slm", "28", False]]},
    ],
}


def equipment_html(item: dict) -> str:
    resources = "".join(
        f'<li><b>{name}</b><span>{value}</span>{"<em>공유</em>" if shared else ""}</li>'
        for name, value, shared in item["resources"]
    )
    specs = "".join(
        f'<tr class="{"bad" if not ok else ""}"><td>{resource}</td><td>{name}</td>'
        f'<td>{required}</td><td>{actual}</td><td>{"충족" if ok else "미충족"}</td></tr>'
        for resource, name, required, actual, ok in item["specs"]
    )
    warning = " warning" if item["fit"] == "조건부" else ""
    return f"""<article class="equipment{warning}"><header><div><h2>{item["id"]}</h2>
    <span>{item["fit"]} · {item["state"]}</span></div><b>처리 {item["process"]}분<br>Setup {item["setup"]}분</b></header>
    <h3>사용 Resource</h3><ul>{resources}</ul><h3>연결 Spec</h3>
    <table><thead><tr><th>Resource</th><th>항목</th><th>요구</th><th>현재</th><th>판정</th></tr></thead>
    <tbody>{specs}</tbody></table></article>"""


def html_page() -> str:
    lot = DATA["lot"]
    cards = "".join(equipment_html(item) for item in DATA["equipment"])
    style = """*{box-sizing:border-box}body{margin:0;background:#eef3f6;color:#17212b;font:14px "Malgun Gothic",sans-serif}.page{width:min(1280px,calc(100% - 28px));margin:22px auto}.top{display:flex;justify-content:space-between;align-items:end}.tag{color:#a13b2d}.summary{margin-top:16px;padding:17px;border-radius:13px;background:#173b57;color:white}.summary h2{margin:0 0 5px}.path{display:flex;gap:8px;align-items:center;margin:13px 0;color:#66727e}.path b{padding:6px 10px;border-radius:8px;background:white;color:#173b57}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.equipment{padding:15px;background:white;border:1px solid #d8e0e7;border-radius:13px}.equipment.warning{border-color:#cf7568}.equipment header{display:flex;justify-content:space-between;gap:12px}.equipment h2,.equipment h3{margin:0}.equipment header span{color:#36765a}.equipment.warning header span,.bad td:last-child{color:#a13b2d}.equipment header>b{color:#66727e;font-size:12px;text-align:right}.equipment h3{margin-top:18px;font-size:13px}ul{display:grid;gap:7px;padding:0;list-style:none}li{display:grid;grid-template-columns:1fr auto auto;gap:7px;padding:9px;border-radius:8px;background:#f7f9fb}li span{color:#66727e}em{padding:1px 6px;border-radius:99px;background:#fff1d8;color:#755316;font-size:10px;font-style:normal}table{width:100%;border-collapse:collapse}th,td{padding:8px 4px;border-bottom:1px solid #e5e9ed;text-align:left;font-size:11px}.bad{background:#fff4f2}.compare{margin-top:12px;padding:15px;border:1px solid #d8e0e7;border-radius:13px;background:white}.compare p{color:#66727e}@media(max-width:850px){.grid{grid-template-columns:1fr}.top{align-items:start;flex-direction:column}}"""
    comparison = "".join(
        f'<tr><td>{item["id"]}</td><td>{item["fit"]}</td><td>{item["state"]}</td>'
        f'<td>{item["process"]}분</td><td>{item["setup"]}분</td><td>{len(item["resources"])}개</td></tr>'
        for item in DATA["equipment"]
    )
    return f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
    <title>Factory Scheduling 관계 목업</title><style>{style}</style><main class="page">
    <header class="top"><div><small>Factory Scheduling</small><h1>Lot → 설비 → Resource → Spec</h1></div>
    <b class="tag">예시 화면(목업) · 합성 데이터</b></header><section class="summary">
    <h2>{lot["id"]} · Product {lot["product"]}</h2><div>{lot["operation"]} · {lot["quantity"]:,} wafers · 납기 {lot["due"]}
    · 우선순위 {lot["priority"]} · Recipe {lot["recipe"]}</div></section>
    <div class="path"><b>선택 Lot 1개</b>→<b>가능 설비 {len(DATA["equipment"])}대</b>→<b>설비별 Resource</b>→<b>적용 Spec</b></div>
    <section class="grid">{cards}</section><section class="compare"><h2>설비 비교</h2>
    <p>GAS-CF4, TOOL-KIT-7, OPERATOR-L2처럼 여러 설비가 함께 쓰는 항목은 공유 Resource로 표시합니다.</p>
    <table><thead><tr><th>설비</th><th>적합성</th><th>상태</th><th>처리</th><th>Setup</th><th>Resource</th></tr></thead>
    <tbody>{comparison}</tbody></table></section></main></html>"""


def render_png(path: Path) -> None:
    im=Image.new("RGB",(1250,760),"#eef3f6");d=ImageDraw.Draw(im)
    fp=r"C:\Windows\Fonts\malgun.ttf";bp=r"C:\Windows\Fonts\malgunbd.ttf"
    f=ImageFont.truetype(fp,12);b=ImageFont.truetype(bp,16);title=ImageFont.truetype(bp,23)
    box=lambda a,fill="white",line="#d8e0e7":d.rounded_rectangle(a,12,fill=fill,outline=line)
    d.text((35,24),"Factory Scheduling 관계 탐색",font=title,fill="#17212b");d.text((985,30),"예시 화면(목업) · 합성 데이터",font=f,fill="#a13b2d")
    box((35,65,1215,130),"#173b57","#173b57");d.text((55,80),"LOT-24017 · AX7 · Etch-02 · 1,200 wafers · 납기 14:30",font=b,fill="white");d.text((55,108),"가능 설비 3대 · Recipe R-ETCH-A7",font=f,fill="#dceaf4")
    for col,item in enumerate(DATA["equipment"]):
        x=35+col*400;box((x,160,x+380,705),"white","#cf7568" if item["fit"]=="조건부" else "#d8e0e7")
        d.text((x+18,180),item["id"],font=b,fill="#17212b");d.text((x+18,210),item["fit"]+" · "+item["state"],font=f,fill="#a13b2d" if item["fit"]=="조건부" else "#36765a")
        d.text((x+18,250),"사용 Resource",font=b,fill="#17212b")
        for i,(name,value,shared) in enumerate(item["resources"]):
            y=280+i*50;box((x+18,y,x+362,y+40),"#f7f9fb");d.text((x+30,y+11),name,font=f,fill="#17212b");d.text((x+210,y+11),value+(" · 공유" if shared else ""),font=f,fill="#755316" if shared else "#66727e")
        y0=500;d.text((x+18,y0),"연결 Spec",font=b,fill="#17212b")
        for i,(resource,name,required,actual,ok) in enumerate(item["specs"]):
            y=y0+35+i*48;box((x+18,y,x+362,y+38),"white" if ok else "#fff4f2","#d8e0e7" if ok else "#cf7568");d.text((x+28,y+6),resource,font=f,fill="#17212b");d.text((x+28,y+21),name,font=f,fill="#66727e");d.text((x+165,y+10),required,font=f,fill="#66727e");d.text((x+255,y+10),actual+(" ✓" if ok else " 미충족"),font=f,fill="#36765a" if ok else "#a13b2d")
    im.save(path)


def main():
    for equipment in DATA["equipment"]:
        resource_ids = {resource[0] for resource in equipment["resources"]}
        if any(spec[0] not in resource_ids for spec in equipment["specs"]):
            raise ValueError(f'{equipment["id"]}: Spec Resource가 설비 Resource에 없습니다')
    out=ROOT/"docs/images/screens";public=ROOT/"frontend/public/samples"
    out.mkdir(parents=True,exist_ok=True);public.mkdir(parents=True,exist_ok=True)
    page=html_page();(out/"factory-scheduling.html").write_text(page,encoding="utf-8");(public/"factory-scheduling.html").write_text(page,encoding="utf-8")
    (out/"factory-scheduling.json").write_text(json.dumps(DATA,ensure_ascii=False,indent=2),encoding="utf-8")
    render_png(out/"factory-scheduling.png");print("Lot 1개 · 가능 설비 3대 · 공유 Resource 포함")


if __name__ == "__main__":
    main()
