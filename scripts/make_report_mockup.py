#!/usr/bin/env python3
"""T148 반영 리포트 예시 화면(목업)을 실제 계산값으로 생성한다."""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from app.core.cluster_report import cluster_representation_report
from app.core.metrics import correlation_metrics
from app.core.relationship_causes import explain_relationship_changes
from make_screen_mockups import COLUMNS, calculate

CAUSES = {"threshold_boundary": "임계값 경계", "cluster_representation": "군집 대표화 효과",
          "outlier_exclusion": "이상치 제외 영향", "no_material_change": "유의미한 변화 없음",
          "unresolved": "확정 근거 없음"}
RESULTS = {"maintained": "유지", "weakened": "약해짐", "strengthened": "강해짐",
           "lost": "사라짐", "new": "새 관계", "absent": "관계 없음", "undefined": "정의 안 됨"}


def calculate_report():
    original, *_ = calculate()
    labels = np.digitize(original["방문"], original["방문"].quantile([.34, .68]).to_numpy())
    members = []
    for cluster, count in ((0, 12), (1, 10)):
        rows = np.flatnonzero(labels == cluster)
        members.extend([part for part in np.array_split(rows, count) if len(part)])
    report = cluster_representation_report(labels, members, minimum_targets={1: 10})
    representative_indices = [group[len(group)//2] for group in members]
    representatives = original.iloc[representative_indices].reset_index(drop=True)
    metrics = correlation_metrics(original, representatives, [], COLUMNS)
    dispersion = {}
    for i, a in enumerate(COLUMNS):
        for b in COLUMNS[i+1:]:
            base = max(float(original[a].std()*original[b].std()), 1e-9)
            within = np.mean([original.iloc[group][a].std()*original.iloc[group][b].std()
                              for group in members])
            dispersion[(a, b)] = float(within/base)
    changes = explain_relationship_changes(metrics, report, .5, dispersion_ratios=dispersion,
                                           change_tolerance=.05)
    low, high = original[["방문", "구매"]].quantile(.01), original[["방문", "구매"]].quantile(.99)
    def points(indices):
        frame = original.iloc[indices]
        return [[round(float(np.clip((row["방문"]-low["방문"])/(high["방문"]-low["방문"]),0,1)),3),
                 round(float(np.clip((row["구매"]-low["구매"])/(high["구매"]-low["구매"]),0,1)),3),
                 int(labels[index])] for index, row in frame.iterrows()]
    cloud = {"original": points(original.sample(180, random_state=148).index),
             "reduced": points(representative_indices)}
    return original, representatives, report, changes, cloud


def render_html(payload):
    report, changes = payload["report"], payload["changes"]
    rows = "".join(f'<tr><td>C{r["cluster_id"]+1}</td><td>{r["original_count"]} ({r["original_ratio"]:.1%})</td>'
                   f'<td>{r["representative_count"]} ({r["representative_ratio"]:.1%})</td>'
                   f'<td><b>{r["status"]}</b><small>{r["reason"]}</small></td></tr>' for r in report["clusters"])
    changed = [p for p in changes["pairs"] if p["result"] not in ("maintained", "absent")][:6]
    relations = "".join(f'<tr><td>{html.escape(p["column_a"])} × {html.escape(p["column_b"])}</td>'
                        f'<td>{p["original_r"]:.2f} → {p["reduced_r"]:.2f}</td><td>{RESULTS[p["result"]]}</td>'
                        f'<td>{", ".join(CAUSES[c] for c in p["causes"])}</td></tr>' for p in changed)
    colors = ["#176b9b","#b87a35","#687c45"]
    dots = {key:"".join(f'<i style="left:{4+x*91:.1f}%;bottom:{6+y*86:.1f}%;background:{colors[c]}"></i>'
                        for x,y,c in values) for key,values in payload["cloud"].items()}
    style = """*{box-sizing:border-box}body{margin:0;background:#eef3f6;color:#17212b;font:14px "Malgun Gothic",sans-serif}.page{width:min(1180px,calc(100% - 32px));margin:24px auto}.top{display:flex;justify-content:space-between;align-items:end}.tag{color:#a04b3f;font-weight:700}.flow,.panel{background:white;border:1px solid #d8e0e7;border-radius:13px;padding:17px}.flow{margin:16px 0}.flow b{color:#173b57;font-size:18px}.grid{display:grid;grid-template-columns:1fr 1.15fr;gap:12px}.clouds{display:grid;grid-template-columns:1fr 1fr;gap:8px}.cloud{height:160px;position:relative;background:#f7f9fb;border-radius:9px;overflow:hidden}.cloud b{position:absolute;z-index:2;padding:6px;font-size:11px}.cloud i{position:absolute;width:6px;height:6px;border-radius:50%}h2{font-size:16px;margin:0 0 12px}p,small{color:#66727e}.stats{font-size:20px;font-weight:800;color:#173b57}table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #e5e9ed;text-align:left;font-size:12px}td small{display:block}.relations{grid-column:1/-1}.guide{margin-top:12px;color:#66727e;font-size:12px}@media(max-width:760px){.grid{grid-template-columns:1fr}.relations{grid-column:auto}.top{align-items:start;flex-direction:column}.panel{overflow-x:auto}}"""
    return f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>축소 반영 리포트 목업</title><style>{style}</style><main class="page"><header class="top"><div><small>축소 결과 설명</small><h1>반영 리포트</h1></div><span class="tag">예시 화면(목업) · 합성 데이터</span></header><section class="flow"><b>표 데이터 → 상관행렬 → 노드·엣지 네트워크</b><p>노드=컬럼 · 엣지=|r|≥0.50 · 굵기=|r| · 빨강=양의 관계 · 파랑=음의 관계</p></section><section class="grid"><article class="panel"><h2>규모 비교</h2><div class="stats">원본 {report["original_count"]}행 → 대표 {report["representative_count"]}행</div><p>대표 1행이 평균 {report["original_count"]/report["representative_count"]:.1f}행을 설명 · 군집별 같은 색</p><div class="clouds"><div class="cloud"><b>원본</b>{dots["original"]}</div><div class="cloud"><b>대표</b>{dots["reduced"]}</div></div></article><article class="panel"><h2>군집별 반영</h2><table><thead><tr><th>군집</th><th>원본</th><th>대표</th><th>상태·사유</th></tr></thead><tbody>{rows}</tbody></table></article><article class="panel relations"><h2>관계 변화와 원인 후보</h2><table><thead><tr><th>관계</th><th>원본 r → 축소 r</th><th>결과</th><th>근거 기반 원인 후보</th></tr></thead><tbody>{relations}</tbody></table><p class="guide">원인 표시는 인과 증명이 아니라 측정값과 규칙에 근거한 후보입니다.</p></article></section></main></html>"""


def render_png(payload, path):
    report, changes = payload["report"], payload["changes"]
    im=Image.new("RGB",(1200,740),"#eef3f6"); d=ImageDraw.Draw(im)
    fp=r"C:\Windows\Fonts\malgun.ttf"; bp=r"C:\Windows\Fonts\malgunbd.ttf"
    f=ImageFont.truetype(fp,13); b=ImageFont.truetype(bp,17); title=ImageFont.truetype(bp,23)
    box=lambda a: d.rounded_rectangle(a,12,fill="white",outline="#d8e0e7")
    d.text((35,25),"축소 반영 리포트",font=title,fill="#17212b"); d.text((930,31),"예시 화면(목업) · 실제 계산",font=f,fill="#a04b3f")
    box((35,70,1165,145)); d.text((55,86),"표 데이터  →  상관행렬  →  노드·엣지 네트워크",font=b,fill="#173b57"); d.text((55,116),"노드=컬럼 · 엣지=|r|≥0.50 · 굵기=강도 · 색=부호",font=f,fill="#66727e")
    box((35,165,565,395)); d.text((55,184),f'규모 비교 · 원본 {report["original_count"]}행 → 대표 {report["representative_count"]}행',font=b,fill="#17212b")
    colors=["#176b9b","#b87a35","#687c45"]
    for offset,key,label in ((55,"original","원본"),(305,"reduced","대표")):
        d.text((offset,225),label,font=f,fill="#17212b")
        for x,y,c in payload["cloud"][key]:
            px=offset+int(x*225);py=370-int(y*125);d.ellipse((px,py,px+5,py+5),fill=colors[c])
    box((585,165,1165,395)); d.text((605,184),"군집별 반영",font=b,fill="#17212b"); d.text((610,225),"군집     원본      대표      상태 · 사유",font=f,fill="#66727e")
    for i,r in enumerate(report["clusters"]): d.text((610,262+i*38),f'C{r["cluster_id"]+1}       {r["original_count"]:>3}       {r["representative_count"]:>2}       {r["status"]} · {r["reason"]}',font=f,fill="#17212b")
    box((35,415,1165,705)); d.text((55,434),"관계 변화와 원인 후보",font=b,fill="#17212b")
    changed=[p for p in changes["pairs"] if p["result"] not in ("maintained","absent")][:5]
    for i,p in enumerate(changed): d.text((65,480+i*42),f'{p["column_a"]} × {p["column_b"]}   {p["original_r"]:.2f} → {p["reduced_r"]:.2f}   {RESULTS[p["result"]]}   {", ".join(CAUSES[c] for c in p["causes"])}',font=f,fill="#17212b")
    d.text((65,675),"원인은 인과 증명이 아니라 측정값과 규칙에 근거한 후보입니다.",font=f,fill="#66727e"); im.save(path)


def main():
    original, reduced, report, changes, cloud = calculate_report()
    payload={"report":report,"changes":changes,"cloud":cloud,
             "rows":{"original":len(original),"reduced":len(reduced)}}
    out=ROOT/"docs/images/screens"; public=ROOT/"frontend/public/samples"; out.mkdir(parents=True,exist_ok=True); public.mkdir(parents=True,exist_ok=True)
    page=render_html(payload); (out/"representation-report.html").write_text(page,encoding="utf-8"); (public/"representation-report.html").write_text(page,encoding="utf-8")
    render_png(payload,out/"representation-report.png"); (out/"representation-report.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"원본 {len(original)}행 → 대표 {len(reduced)}행 · 군집 {len(report['clusters'])}개")


if __name__ == "__main__":
    main()
