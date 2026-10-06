# 웹 UI 데모 데이터

웹 앱에서 폴더 선택 시 `samples/web-demo` 폴더를 선택한다.

## 포함 파일

- `sales_2024_01.csv`, `sales_2024_02.csv`: 같은 15개 컬럼 구조, 각 1,500행. 병합 그룹을 확인한다.
- `customers.csv`: 다른 9개 컬럼 구조, 1,000행. 별도 그룹을 확인한다.
- `readme.txt`: 표가 아닌 텍스트를 건너뛰는지 확인한다.

매출 데이터에는 수치형·범주형 컬럼, 군집, 희소 그룹, 결측치와 이상치가 포함된다. 전체 폴더를
업로드하면 그룹 판별, 컬럼 선택, 축소 실행, 결과 점수와 그래프 영역, 축소 CSV 다운로드를 순서대로
확인할 수 있다.

## 다시 생성하기

```powershell
backend\.venv\Scripts\python.exe scripts\make_sample_data.py --rows 3000 --files 2 --out samples\web-demo --seed 7
```

생성 데이터는 고정 seed를 사용하며 실제 개인정보나 운영 데이터를 포함하지 않는다.

## Factory Scheduling 데모

공정 관계 데이터를 별도 그룹으로 업로드하려면 `samples/web-demo/factory-scheduling` 폴더를 선택한다. 기본 web-demo 폴더의 매출/고객 샘플과 섞이지 않으며, 네 CSV는 ID 컬럼으로 연결된다.

- `lots.csv`: 합성 Lot 특성 (`lot_id`)
- `equipment_options.csv`: Lot별 후보 설비와 적합성/처리 시간 (`lot_id`, `equipment_id`)
- `equipment_resources.csv`: 후보 설비의 Resource 관측값 (`lot_id`, `equipment_id`, `resource_id`)
- `resource_specs.csv`: Resource별 요구·실측 Spec과 판정. 앞의 세 ID를 참조한다.

기본 생성량은 Lot 120행, 설비 후보 360행, Resource 관계 1,320행, Spec 1,080행이다. 앱은 네 파일을 각각 별도 스키마 그룹으로 표시한다.

기준 `LOT-24017`은 T320 예시 값이며, 나머지는 로컬 데모 전용으로 결정적 규칙에 따라 만든 합성 값이다. 실제 제조/개인정보를 포함하지 않는다. CSV를 다시 만들려면 저장소 루트에서 실행한다:

```powershell
backend\.venv\Scripts\python.exe scripts\make_factory_scheduling_demo.py
```

다른 출력 위치나 Lot 수를 지정할 수도 있다:

```powershell
backend\.venv\Scripts\python.exe scripts\make_factory_scheduling_demo.py --lots 200 --out samples\web-demo\factory-scheduling
```
